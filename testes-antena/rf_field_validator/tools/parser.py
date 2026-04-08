#!/usr/bin/env python3
"""
parser.py — Pipeline offline de análise RF (spec N2.1)

Uso:
    python tools/parser.py <campanha_dir> [--weights plr=0.30,ttr=0.25,rssi=0.25,tput=0.20]

Saída:
    <campanha_dir>/report/report.html
    <campanha_dir>/report/summary.csv

Pipeline:
    Ingestão → Validação → Split profile → Agregação → Consolidação → Score RF → Relatório
"""

import os, sys, re, json, csv, math, argparse, warnings
from collections import defaultdict
from datetime import datetime
from pathlib import Path

# ── Dependências opcionais ────────────────────────────────────
try:
    import pandas as pd
    import numpy as np
    HAS_PANDAS = True
except ImportError:
    HAS_PANDAS = False
    warnings.warn("pandas/numpy ausentes — usando modo básico (sem gráficos avançados)")

# ══════════════════════════════════════════════════════════════
#  1. INGESTÃO
# ══════════════════════════════════════════════════════════════
LOG_COLS = [
    "timestamp_ms","type","profile","phase","antenna","location","condition","run_id",
    "rssi_dbm","ping_ok","ping_latency_ms","ping_seq",
    "throughput_bps","plr_window",
    "vin_mv","temp_c","link_state","boot_count","uptime_ms",
    "marker","block","notes","crc16"
]

FILENAME_RE = re.compile(
    r"^(WALK|CLOCK|BURN)_([A-Za-z0-9]+)_([A-Za-z0-9]+)_([A-Za-z0-9]+)_R(\d{2})\.csv$"
)

def _crc16(s: str) -> str:
    crc = 0xFFFF
    for c in s.encode():
        crc ^= c << 8
        for _ in range(8):
            crc = (crc << 1) ^ 0x1021 if crc & 0x8000 else crc << 1
        crc &= 0xFFFF
    return f"{crc:04X}"

def ingest_file(path: Path) -> dict:
    """
    Lê um arquivo CSV do firmware e retorna dict com:
      rows     : lista de dicts (uma por linha)
      warnings : lista de strings
      meta     : dict extraído do nome de arquivo
    """
    result = {"path": str(path), "rows": [], "warnings": [], "meta": {}, "status": "VALID"}
    m = FILENAME_RE.match(path.name)
    if m:
        result["meta"] = {
            "mode": m.group(1), "antenna": m.group(2),
            "location": m.group(3), "condition": m.group(4),
            "run_number": int(m.group(5))
        }
    else:
        result["warnings"].append(f"SUSPECT: nome de arquivo fora do padrão: {path.name}")
        result["status"] = "SUSPECT"

    try:
        with open(path, encoding="utf-8", errors="replace") as f:
            reader = csv.DictReader(f)
            for i, row in enumerate(reader, start=2):
                # Verifica CRC16 se presente
                crc_field = row.get("crc16", "")
                if crc_field:
                    # reconstrói a linha sem o campo crc16
                    line_without_crc = ",".join(
                        str(row.get(c, "")) for c in LOG_COLS[:-1]
                    )
                    expected = _crc16(line_without_crc)
                    if crc_field.strip().upper() != expected:
                        result["warnings"].append(
                            f"CRC_MISMATCH linha {i}: got {crc_field} expected {expected}"
                        )
                result["rows"].append(dict(row))
    except Exception as e:
        result["warnings"].append(f"READ_ERROR: {e}")
        result["status"] = "INVALID"

    return result

# ══════════════════════════════════════════════════════════════
#  2. VALIDAÇÃO
# ══════════════════════════════════════════════════════════════
VIN_BROWNOUT_MV = 10500

def validate_run(run: dict) -> dict:
    """Valida um run e preenche run['status'] e run['validation']"""
    rows  = run["rows"]
    warns = run["warnings"]
    val   = {"checks": []}
    run["validation"] = val

    def _check(name, ok, msg=""):
        val["checks"].append({"name": name, "ok": ok, "msg": msg})
        if not ok:
            warns.append(f"{name}: {msg}")

    types  = [r.get("type","")  for r in rows]
    notes  = [r.get("notes","") for r in rows]
    boots  = [r.get("boot_count","") for r in rows if r.get("boot_count","")]
    uptimes= [int(r.get("uptime_ms",0) or 0) for r in rows if r.get("uptime_ms","")]
    vins   = [int(r.get("vin_mv",0) or 0) for r in rows if r.get("vin_mv","") and r.get("vin_mv","") != "0"]

    # START_RUN + END_RUN presentes
    has_start = any(n == "START_RUN" for n in notes)
    has_end   = any(n in ("END_RUN","ABORTED") for n in notes)
    _check("START_RUN",  has_start, "evento START_RUN ausente")
    _check("END_RUN",    has_end,   "evento END_RUN ausente → run INCOMPLETE")
    if not has_end: run["status"] = "INCOMPLETE"

    # boot_count constante
    unique_boots = set(boots)
    _check("BOOT_COUNT", len(unique_boots) <= 1,
           f"boot_count variou: {unique_boots} → INVALID_REBOOT")
    if len(unique_boots) > 1:
        run["status"] = "INVALID"
        run["invalid_reason"] = "INVALID_REBOOT"

    # uptime monotônico
    non_mono = any(uptimes[i] < uptimes[i-1] for i in range(1, len(uptimes)))
    _check("UPTIME_MONO", not non_mono, "uptime_ms não monotônico")

    # brownout
    brownout = any(0 < v < VIN_BROWNOUT_MV for v in vins)
    if brownout:
        warns.append("BROWNOUT_WARNING: vin_mv abaixo do limiar em algum momento")
        run["brownout"] = True

    # nome vs metadados CSV
    if run["meta"]:
        first_s = next((r for r in rows if r.get("type") == "S"), None)
        if first_s:
            csv_ant = first_s.get("antenna","")
            meta_ant = run["meta"].get("antenna","")
            if csv_ant and meta_ant and csv_ant.upper() != meta_ant.upper():
                warns.append(f"SUSPECT: antena no nome ({meta_ant}) difere do CSV ({csv_ant})")
                if run["status"] == "VALID": run["status"] = "SUSPECT"

    return run

# ══════════════════════════════════════════════════════════════
#  3. AGREGAÇÃO POR PERFIL
# ══════════════════════════════════════════════════════════════
def _pct(lst, p):
    if not lst: return float("nan")
    s = sorted(lst)
    i = max(0, int(len(s) * p / 100) - 1)
    return s[i]

def _median(lst):
    return _pct(lst, 50)

def aggregate_profile_a(rows: list) -> dict:
    """Perfil A (BURN): agrega por bloco."""
    blocks = defaultdict(lambda: {"plr":[], "tput":[], "rssi":[], "lat":[]})
    for r in rows:
        if r.get("type") != "S": continue
        blk = int(r.get("block") or 0)
        try:
            plr  = float(r.get("plr_window") or 0)
            tput = int(r.get("throughput_bps") or 0)
            rssi = int(r.get("rssi_dbm") or -127)
            lat  = float(r.get("ping_latency_ms") or 0)
        except ValueError:
            continue
        blocks[blk]["plr"].append(plr)
        blocks[blk]["tput"].append(tput)
        blocks[blk]["rssi"].append(rssi)
        blocks[blk]["lat"].append(lat)

    result = {}
    for blk, d in blocks.items():
        result[blk] = {
            "plr_median":  _median(d["plr"]),
            "tput_median": _median(d["tput"]),
            "rssi_p10":    _pct(d["rssi"], 10),
            "lat_p90":     _pct(d["lat"], 90),
            "n":           len(d["plr"]),
        }
    return result

def aggregate_profile_b_walk(rows: list) -> dict:
    """Perfil B WALK: máquina de estados TTR."""
    DISC_THRESHOLD = 3  # pings falhos consecutivos para considerar desconectado
    events = []
    consecutive_fail = 0
    in_disconnect = False
    disc_start_idx  = None

    pings = [r for r in rows if r.get("type") == "S"]
    rssi_list = []
    ttr_list  = []

    for i, r in enumerate(pings):
        ok = int(r.get("ping_ok") or 0)
        rssi = int(r.get("rssi_dbm") or -127)
        ts   = float(r.get("timestamp_ms") or 0)
        rssi_list.append(rssi)

        if ok == 0:
            consecutive_fail += 1
            if consecutive_fail >= DISC_THRESHOLD and not in_disconnect:
                in_disconnect  = True
                disc_start_idx = i - DISC_THRESHOLD + 1
                disc_start_ts  = float(pings[disc_start_idx].get("timestamp_ms") or 0)
                rssi_at_disc   = rssi_list[disc_start_idx] if disc_start_idx < len(rssi_list) else -127
        else:
            if in_disconnect:
                ttr_ms = ts - disc_start_ts
                events.append({
                    "disc_ts": disc_start_ts,
                    "recov_ts": ts,
                    "ttr_ms": ttr_ms,
                    "rssi_at_disc": rssi_at_disc,
                    "recovered": True,
                })
                ttr_list.append(ttr_ms / 1000)  # em segundos
            in_disconnect    = False
            consecutive_fail = 0

    # desconexão sem recuperação
    if in_disconnect:
        events.append({
            "disc_ts": disc_start_ts,
            "recov_ts": None,
            "ttr_ms": None,
            "rssi_at_disc": rssi_at_disc,
            "recovered": False,
        })

    return {
        "ttr_min_s":    min(ttr_list) if ttr_list else float("nan"),
        "ttr_max_s":    max(ttr_list) if ttr_list else float("nan"),
        "ttr_median_s": _median(ttr_list),
        "disc_events":  len(events),
        "unrecovered":  sum(1 for e in events if not e["recovered"]),
        "rssi_median":  _median(rssi_list),
        "rssi_p10":     _pct(rssi_list, 10),
        "events":       events,
    }

def aggregate_profile_b_clock(rows: list) -> dict:
    """Perfil B CLOCK: GROUP BY marker."""
    by_marker = defaultdict(lambda: {"rssi":[], "ok":[], "lat":[]})
    for r in rows:
        if r.get("type") != "S": continue
        marker = r.get("marker","") or "NO_MARK"
        try:
            rssi = int(r.get("rssi_dbm") or -127)
            ok   = int(r.get("ping_ok")  or 0)
            lat  = float(r.get("ping_latency_ms") or 0)
        except ValueError:
            continue
        by_marker[marker]["rssi"].append(rssi)
        by_marker[marker]["ok"].append(ok)
        by_marker[marker]["lat"].append(lat)

    result = {}
    for mark, d in by_marker.items():
        n   = len(d["ok"])
        plr = (1 - sum(d["ok"]) / n) * 100 if n > 0 else 100.0
        result[mark] = {
            "rssi_median": _median(d["rssi"]),
            "rssi_p10":    _pct(d["rssi"], 10),
            "rssi_sigma":  (
                math.sqrt(sum((x - _median(d["rssi"]))**2 for x in d["rssi"]) / n)
                if n > 1 else 0.0
            ),
            "plr_pct": plr,
            "n": n,
        }
    return result

# ══════════════════════════════════════════════════════════════
#  4. CONSOLIDAÇÃO (3 RUNS → MEDIANA + IQR)
# ══════════════════════════════════════════════════════════════
def consolidate(runs_agg: list, profile: str) -> dict:
    """
    runs_agg: lista de dicts agregados (1 por run válido)
    Retorna mediana + IQR das métricas principais + status de dados
    """
    if not runs_agg:
        return {"data_status": "INSUFFICIENT_DATA"}

    valid = [r for r in runs_agg if r is not None]
    n = len(valid)

    if n == 0:
        return {"data_status": "INSUFFICIENT_DATA"}
    if n == 1:
        status = "SINGLE_RUN_WARNING"
    elif n == 2:
        status = "TWO_RUNS_WARNING"
    else:
        status = "OK"

    def _med_iqr(vals):
        vals = [v for v in vals if v is not None and not math.isnan(float(v))]
        if not vals: return float("nan"), float("nan")
        med = _median(vals)
        q1  = _pct(vals, 25)
        q3  = _pct(vals, 75)
        return med, q3 - q1

    result = {"data_status": status, "n_runs": n}

    if profile == "A":
        for blk in set(blk for r in valid for blk in r.keys() if isinstance(blk, int)):
            blk_data = [r.get(blk, {}) for r in valid]
            result[f"block{blk}_plr_med"],  result[f"block{blk}_plr_iqr"]  = _med_iqr([d.get("plr_median")  for d in blk_data])
            result[f"block{blk}_tput_med"], result[f"block{blk}_tput_iqr"] = _med_iqr([d.get("tput_median") for d in blk_data])
            result[f"block{blk}_rssi_p10"], _                               = _med_iqr([d.get("rssi_p10")    for d in blk_data])

    elif profile == "B_WALK":
        result["ttr_median_s"], result["ttr_iqr_s"] = _med_iqr([r.get("ttr_median_s") for r in valid])
        result["rssi_p10"],     _                    = _med_iqr([r.get("rssi_p10")     for r in valid])
        result["disc_events_med"], _                 = _med_iqr([r.get("disc_events")  for r in valid])

    elif profile == "B_CLOCK":
        # consolida por marker
        all_marks = set(m for r in valid for m in r.keys() if isinstance(m, str) and m != "data_status")
        result["markers"] = {}
        for m in all_marks:
            result["markers"][m] = {
                "rssi_median_med": _median([r[m]["rssi_median"] for r in valid if m in r]),
                "rssi_p10_med":    _median([r[m]["rssi_p10"]    for r in valid if m in r]),
                "plr_med":         _median([r[m]["plr_pct"]     for r in valid if m in r]),
            }

    return result

# ══════════════════════════════════════════════════════════════
#  5. SCORE RF
# ══════════════════════════════════════════════════════════════
def compute_score(antenna_data: dict, weights: dict) -> dict:
    """
    antenna_data: {antenna: {plr, ttr, rssi_p10, tput}}
    weights: {plr, ttr, rssi, tput}
    Retorna {antenna: score_0_100}
    """
    metrics = {"plr": {}, "ttr": {}, "rssi": {}, "tput": {}}
    for ant, d in antenna_data.items():
        metrics["plr"][ant]  = d.get("plr",  100.0)
        metrics["ttr"][ant]  = d.get("ttr",  999.0)
        metrics["rssi"][ant] = d.get("rssi", -127.0)
        metrics["tput"][ant] = d.get("tput", 0.0)

    def _norm_min(vals):  # menor = melhor → normaliza para 0–1 onde 1 = melhor
        lo, hi = min(vals.values()), max(vals.values())
        if hi == lo: return {k: 1.0 for k in vals}
        return {k: 1.0 - (v - lo) / (hi - lo) for k, v in vals.items()}

    def _norm_max(vals):  # maior = melhor
        lo, hi = min(vals.values()), max(vals.values())
        if hi == lo: return {k: 1.0 for k in vals}
        return {k: (v - lo) / (hi - lo) for k, v in vals.items()}

    n_plr  = _norm_min(metrics["plr"])
    n_ttr  = _norm_min(metrics["ttr"])
    n_rssi = _norm_max(metrics["rssi"])
    n_tput = _norm_max(metrics["tput"])

    scores = {}
    for ant in antenna_data:
        s = (weights.get("plr",  0.30) * n_plr.get(ant,  0) +
             weights.get("ttr",  0.25) * n_ttr.get(ant,  0) +
             weights.get("rssi", 0.25) * n_rssi.get(ant, 0) +
             weights.get("tput", 0.20) * n_tput.get(ant, 0))
        scores[ant] = round(s * 100, 1)

    return scores

# ══════════════════════════════════════════════════════════════
#  6. LIMIARES PASS/FAIL
# ══════════════════════════════════════════════════════════════
THRESHOLDS = {
    "F0":  {"plr": {"pass": 2.0,   "fail": 5.0}},
    "F1":  {"ttr": {"pass": 5.0,   "fail": 10.0}},
    "F2":  {"rssi_p10": {"pass": -80.0, "fail": -85.0, "dir": "max"},
            "plr":      {"pass": 5.0,   "fail": 10.0}},
    "F3A": {"delta_plr": {"pass": 3.0, "fail": 10.0}},
    "F3B": {"plr_block3": {"pass": 5.0, "fail": 10.0},
            "tput_block3": {"pass": 1e6, "fail": 5e5, "dir": "max"}},
}

def pass_fail(phase: str, metrics: dict) -> dict:
    th = THRESHOLDS.get(phase, {})
    result = {}
    for metric, limits in th.items():
        val = metrics.get(metric)
        if val is None or math.isnan(float(val if val is not None else float("nan"))):
            result[metric] = "NO_DATA"
            continue
        direction = limits.get("dir", "min")  # min = menor é melhor
        if direction == "min":
            if val < limits["pass"]:   result[metric] = "PASS"
            elif val >= limits["fail"]: result[metric] = "FAIL"
            else:                       result[metric] = "MARGINAL"
        else:
            if val > limits["pass"]:   result[metric] = "PASS"
            elif val <= limits["fail"]: result[metric] = "FAIL"
            else:                       result[metric] = "MARGINAL"
    return result

# ══════════════════════════════════════════════════════════════
#  7. DETECÇÃO ENVIRONMENT_SHIFTED (REF_START vs REF_END)
# ══════════════════════════════════════════════════════════════
RSSI_SHIFT_THRESHOLD = 3.0  # dB

def check_env_shift(ref_start_rows, ref_end_rows) -> dict:
    def _mean_rssi(rows):
        vals = [int(r.get("rssi_dbm",-127)) for r in rows
                if r.get("type") == "S" and r.get("rssi_dbm","")]
        return sum(vals) / len(vals) if vals else None

    rs = _mean_rssi(ref_start_rows)
    re = _mean_rssi(ref_end_rows)
    if rs is None or re is None:
        return {"status": "NO_REF", "delta_db": None}
    delta = abs(re - rs)
    return {
        "status": "ENVIRONMENT_SHIFTED" if delta >= RSSI_SHIFT_THRESHOLD else "STABLE",
        "delta_db": round(delta, 2),
        "ref_start_rssi": round(rs, 2),
        "ref_end_rssi": round(re, 2),
    }

# ══════════════════════════════════════════════════════════════
#  8. RELATÓRIO HTML
# ══════════════════════════════════════════════════════════════
def render_report(campaign_dir: Path, results: dict, scores: dict, out_path: Path):
    now = datetime.now().strftime("%d/%m/%Y %H:%M")
    campaign_name = campaign_dir.name

    # Tabela de runs
    run_rows_html = ""
    for run in results["runs"]:
        status = run.get("status","?")
        color  = {"VALID":"#22c55e","INCOMPLETE":"#f59e0b","INVALID":"#ef4444",
                  "SUSPECT":"#f97316"}.get(status, "#94a3b8")
        warns  = "; ".join(run.get("warnings",[]))[:120]
        run_rows_html += f"""
<tr>
  <td>{Path(run['path']).name}</td>
  <td style="color:{color};font-weight:700">{status}</td>
  <td style="font-size:11px;color:#64748b">{warns}</td>
</tr>"""

    # Tabela de scores
    score_rows_html = ""
    sorted_scores = sorted(scores.items(), key=lambda x: x[1], reverse=True)
    for rank, (ant, score) in enumerate(sorted_scores, 1):
        bar = int(score)
        score_rows_html += f"""
<tr>
  <td style="font-weight:700">#{rank}</td>
  <td style="font-weight:700;color:#f1f5f9">{ant}</td>
  <td>
    <div style="background:#1f2937;border-radius:4px;height:18px;width:200px;display:inline-block;vertical-align:middle">
      <div style="background:{'#22c55e' if score>=70 else '#f59e0b' if score>=40 else '#ef4444'};height:100%;width:{bar}%;border-radius:4px"></div>
    </div>
    <span style="margin-left:8px;font-weight:700;color:#f1f5f9">{score:.1f}</span>
  </td>
</tr>"""

    # JSON de dados para gráficos inline
    chart_data = json.dumps({
        "scores": dict(sorted_scores),
        "env_shift": results.get("env_shift", {}),
    })

    html = f"""<!DOCTYPE html>
<html lang="pt-BR">
<head>
<meta charset="UTF-8">
<title>Relatório RF — {campaign_name}</title>
<style>
*{{box-sizing:border-box;margin:0;padding:0}}
body{{background:#0a0f1e;color:#e2e8f0;font-family:Inter,system-ui,sans-serif;padding:2rem}}
h1{{font-size:1.8rem;font-weight:900;color:#f1f5f9;margin-bottom:.3rem}}
h2{{font-size:1.1rem;font-weight:700;color:#94a3b8;text-transform:uppercase;
   letter-spacing:.08em;margin:2rem 0 .8rem;border-bottom:1px solid #1f2937;padding-bottom:.4rem}}
table{{width:100%;border-collapse:collapse;margin-bottom:1rem}}
th{{background:#111827;color:#94a3b8;font-size:11px;text-transform:uppercase;
   letter-spacing:.07em;padding:.5rem .75rem;text-align:left}}
td{{padding:.45rem .75rem;border-bottom:1px solid #1f2937;font-size:13px}}
.card{{background:#111827;border:1px solid #1f2937;border-radius:10px;padding:1.2rem;
      margin-bottom:1rem}}
.badge{{display:inline-block;padding:2px 8px;border-radius:4px;font-size:10px;
       font-weight:700;text-transform:uppercase}}
.ok{{background:rgba(34,197,94,.15);color:#22c55e}}
.warn{{background:rgba(245,158,11,.15);color:#f59e0b}}
.fail{{background:rgba(239,68,68,.15);color:#ef4444}}
footer{{margin-top:3rem;font-size:11px;color:#374151;text-align:center}}
</style>
</head>
<body>
<h1>Relatório RF de Campo</h1>
<p style="color:#64748b;margin-bottom:2rem">
  Campanha: <strong style="color:#e2e8f0">{campaign_name}</strong> &nbsp;·&nbsp;
  Gerado em {now} &nbsp;·&nbsp;
  {len(results['runs'])} runs processados
</p>

<h2>1. Resumo Executivo</h2>
<div class="card">
  {'<span class="badge ok">Ambiente estável</span>' if results.get('env_shift',{}).get('status')=='STABLE'
   else '<span class="badge warn">Verificar deslocamento de ambiente</span>'}
  &nbsp;
  {'&nbsp;Δ RSSI turno: ' + str(results.get('env_shift',{}).get('delta_db','—')) + ' dB' if results.get('env_shift',{}).get('delta_db') is not None else ''}
  <p style="margin-top:.8rem;color:#94a3b8;font-size:13px">
    Antena com maior score:
    <strong style="color:#22c55e;font-size:1.2rem">
      {sorted_scores[0][0] if sorted_scores else '—'}
    </strong>
    ({sorted_scores[0][1]:.1f} pts)
  </p>
</div>

<h2>2. Ranking RF (Score Composto)</h2>
<table>
  <tr><th>Rank</th><th>Antena</th><th>Score 0–100</th></tr>
  {score_rows_html}
</table>

<h2>3. Validação de Runs</h2>
<table>
  <tr><th>Arquivo</th><th>Status</th><th>Avisos</th></tr>
  {run_rows_html}
</table>

<h2>4. Referência de Turno</h2>
<div class="card">
{f"""
  <p>REF_START RSSI médio: <strong>{results['env_shift'].get('ref_start_rssi','—')} dBm</strong></p>
  <p>REF_END RSSI médio: <strong>{results['env_shift'].get('ref_end_rssi','—')} dBm</strong></p>
  <p>Delta: <strong>{results['env_shift'].get('delta_db','—')} dB</strong> →
    <span class="badge {'ok' if results['env_shift'].get('status')=='STABLE' else 'warn'}">
      {results['env_shift'].get('status','—')}
    </span>
  </p>
""" if results.get('env_shift') else '<p style="color:#64748b">Sem runs de referência nesta campanha.</p>'}
</div>

<h2>5. Dados de Agregação</h2>
<div class="card">
  <pre style="font-size:11px;color:#94a3b8;overflow:auto;max-height:400px">{json.dumps(results.get('aggregated',{}), indent=2, ensure_ascii=False)}</pre>
</div>

<footer>
  RF Field Validator N2.1 · Terasite Tecnologia · {now}
</footer>
<script>
const DATA = {chart_data};
console.log("Chart data:", DATA);
</script>
</body>
</html>"""

    out_path.parent.mkdir(parents=True, exist_ok=True)
    out_path.write_text(html, encoding="utf-8")
    print(f"  Relatório: {out_path}")

# ══════════════════════════════════════════════════════════════
#  9. PIPELINE PRINCIPAL
# ══════════════════════════════════════════════════════════════
def run_pipeline(campaign_dir: Path, weights: dict):
    print(f"\nPipeline RF — {campaign_dir}\n{'─'*50}")

    logs_dir = campaign_dir / "logs"
    if not logs_dir.exists():
        print("[WARN] Diretório logs/ não encontrado. Tentando raiz.")
        logs_dir = campaign_dir

    csv_files = sorted(logs_dir.glob("*.csv"))
    print(f"  Arquivos encontrados: {len(csv_files)}")

    # Carrega campaign.csv se existir
    campaign_meta = {}
    camp_csv = campaign_dir / "campaign.csv"
    if camp_csv.exists():
        with open(camp_csv, encoding="utf-8") as f:
            for row in csv.DictReader(f):
                campaign_meta[row.get("run_id","")] = row

    # Ingestão + validação
    runs = []
    for p in csv_files:
        run = ingest_file(p)
        validate_run(run)
        runs.append(run)
        st = run["status"]
        n  = len([r for r in run["rows"] if r.get("type") == "S"])
        print(f"  [{st:12s}] {p.name}  ({n} amostras S, {len(run['warnings'])} avisos)")

    # Referência de turno
    ref_start, ref_end = [], []
    for run in runs:
        for r in run["rows"]:
            if r.get("notes") == "REF_START": ref_start.append(r)
            if r.get("notes") == "REF_END":   ref_end.append(r)
    env_shift = check_env_shift(ref_start, ref_end)
    if env_shift["status"] == "ENVIRONMENT_SHIFTED":
        print(f"  [WARN] ENVIRONMENT_SHIFTED Δ={env_shift['delta_db']} dB")
    elif env_shift["status"] == "STABLE":
        print(f"  [OK] Ambiente estável Δ={env_shift['delta_db']} dB")

    # Agregação por antena e perfil
    from itertools import groupby
    aggregated = {}
    antenna_scores_input = {}

    valid_runs = [r for r in runs if r["status"] in ("VALID","SUSPECT")]

    # Agrupa por (antena, modo)
    by_ant_mode = defaultdict(list)
    for run in valid_runs:
        meta = run["meta"]
        if not meta: continue
        key = (meta.get("antenna","?"), meta.get("mode","?"))
        by_ant_mode[key].append(run)

    for (ant, mode), grp in by_ant_mode.items():
        agg_list = []
        for run in grp:
            rows_s = [r for r in run["rows"] if r.get("type") == "S"]
            if mode == "BURN":
                agg_list.append(aggregate_profile_a(run["rows"]))
            elif mode == "WALK":
                agg_list.append(aggregate_profile_b_walk(run["rows"]))
            elif mode == "CLOCK":
                agg_list.append(aggregate_profile_b_clock(run["rows"]))

        profile_key = {"BURN":"A","WALK":"B_WALK","CLOCK":"B_CLOCK"}.get(mode,"?")
        cons = consolidate(agg_list, profile_key)
        aggregated[f"{ant}_{mode}"] = cons

        # Extrai métricas para score RF
        if ant not in antenna_scores_input:
            antenna_scores_input[ant] = {"plr":100.0,"ttr":999.0,"rssi":-127.0,"tput":0.0}

        d = antenna_scores_input[ant]
        if mode == "BURN":
            # usa bloco 0 (sem bloco) ou bloco 3 (3x60) como referência
            ref_blk = cons.get("block3_plr_med") or cons.get("block0_plr_med")
            if ref_blk is not None and not math.isnan(ref_blk):
                d["plr"] = min(d["plr"], ref_blk)
            ref_tput = cons.get("block3_tput_med") or cons.get("block0_tput_med")
            if ref_tput is not None and not math.isnan(ref_tput):
                d["tput"] = max(d["tput"], ref_tput)
        elif mode == "WALK":
            ttr = cons.get("ttr_median_s", float("nan"))
            if not math.isnan(ttr): d["ttr"] = min(d["ttr"], ttr)
            rssi = cons.get("rssi_p10", -127.0)
            if rssi > d["rssi"]: d["rssi"] = rssi
        elif mode == "CLOCK":
            # RSSI P10 consolidado de todos os markers
            all_rssi = [v["rssi_p10_med"] for v in (cons.get("markers") or {}).values()
                        if v.get("rssi_p10_med") is not None]
            if all_rssi:
                med_rssi = _median(all_rssi)
                if med_rssi > d["rssi"]: d["rssi"] = med_rssi

    scores = compute_score(antenna_scores_input, weights) if antenna_scores_input else {}
    if scores:
        print("\n  Scores RF:")
        for ant, sc in sorted(scores.items(), key=lambda x: x[1], reverse=True):
            print(f"    {ant}: {sc:.1f} pts")

    # Exporta summary.csv
    report_dir = campaign_dir / "report"
    report_dir.mkdir(exist_ok=True)

    summary_path = report_dir / "summary.csv"
    with open(summary_path, "w", newline="", encoding="utf-8") as f:
        w = csv.writer(f)
        w.writerow(["antenna","score","plr","ttr_s","rssi_p10","tput_bps"])
        for ant, d in antenna_scores_input.items():
            w.writerow([ant, scores.get(ant,""), d["plr"], d["ttr"], d["rssi"], d["tput"]])
    print(f"  Summary CSV: {summary_path}")

    results = {
        "runs": runs,
        "env_shift": env_shift,
        "aggregated": aggregated,
    }

    render_report(campaign_dir, results, scores, report_dir / "report.html")
    print(f"\nConcluído. Abrir: {report_dir / 'report.html'}")

# ══════════════════════════════════════════════════════════════
#  MAIN
# ══════════════════════════════════════════════════════════════
def _parse_weights(s: str) -> dict:
    w = {"plr": 0.30, "ttr": 0.25, "rssi": 0.25, "tput": 0.20}
    if not s: return w
    for part in s.split(","):
        if "=" in part:
            k, v = part.split("=", 1)
            if k.strip() in w:
                w[k.strip()] = float(v.strip())
    return w

if __name__ == "__main__":
    ap = argparse.ArgumentParser(description="Parser offline RF Field Validator N2.1")
    ap.add_argument("campaign_dir", help="Diretório da campanha (contém logs/)")
    ap.add_argument("--weights", default="", help="Pesos: plr=0.30,ttr=0.25,rssi=0.25,tput=0.20")
    args = ap.parse_args()

    run_pipeline(Path(args.campaign_dir), _parse_weights(args.weights))
