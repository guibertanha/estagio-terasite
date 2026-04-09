#!/usr/bin/env python3
"""
parser.py — Pipeline offline de análise RF (spec N2.1)

Uso:
    python tools/parser.py <pasta_com_csvs> [--weights plr=0.30,ttr=0.25,rssi=0.25,tput=0.20]

    A pasta pode conter os CSVs diretamente ou numa subpasta logs/.
    Gera: <pasta>/report/report.html  e  <pasta>/report/summary.csv
"""

import os, sys, re, csv, math, json, argparse
from collections import defaultdict
from datetime import datetime
from pathlib import Path

# Força UTF-8 no stdout (necessário no Windows com terminal CP1252)
if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")

# ══════════════════════════════════════════════════════════════
#  1. INGESTÃO
# ══════════════════════════════════════════════════════════════
CSV_HEADER = [
    "timestamp_ms","type","profile","phase","antenna","location","condition","run_id",
    "rssi_dbm","ping_ok","ping_latency_ms","ping_seq",
    "throughput_bps","plr_window",
    "vin_mv","temp_c","link_state","boot_count","uptime_ms",
    "marker","block","notes",
]

FILENAME_RE = re.compile(
    r"^(WALK|CLOCK|BURN)_([A-Za-z0-9]+)_([A-Za-z0-9]+)_([A-Za-z0-9]+)_R(\d{2})\.csv$",
    re.IGNORECASE
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
    result = {"path": str(path), "rows": [], "warnings": [], "meta": {}, "status": "VALID"}

    m = FILENAME_RE.match(path.name)
    if m:
        result["meta"] = {
            "mode": m.group(1).upper(),
            "antenna": m.group(2).upper(),
            "location": m.group(3).upper(),
            "condition": m.group(4).upper(),
            "run_number": int(m.group(5)),
        }
    else:
        result["warnings"].append(f"Nome fora do padrão: {path.name}")

    crc_errors = 0
    try:
        with open(path, encoding="utf-8", errors="replace") as f:
            raw = f.read()
        # Corrige CSVs sem newline entre linhas (bug firmware: crc_field[12] truncava \n)
        raw = re.sub(r"(crc16=[0-9A-Fa-f]{4})(?=\d)", r"\1\n", raw)
        import io
        reader = csv.DictReader(io.StringIO(raw))
        for i, row in enumerate(reader, start=2):
            # CRC está em row[None] (campo extra além do header)
            extra = row.get(None) or []
            if isinstance(extra, str):
                extra = [extra]
            crc_raw = extra[0].strip() if extra else ""
            crc_val = crc_raw.replace("crc16=", "").replace("CRC16=", "").strip()

            if crc_val:
                line_body = ",".join(str(row.get(c, "") or "") for c in CSV_HEADER)
                expected = _crc16(line_body)
                if crc_val.upper() != expected:
                    crc_errors += 1

            result["rows"].append(dict(row))
    except Exception as e:
        result["warnings"].append(f"Erro de leitura: {e}")
        result["status"] = "INVALID"
        return result

    if crc_errors:
        result["warnings"].append(f"CRC inválido em {crc_errors} linha(s)")
    return result

# ══════════════════════════════════════════════════════════════
#  2. VALIDAÇÃO
# ══════════════════════════════════════════════════════════════
def validate_run(run: dict) -> dict:
    rows  = run["rows"]
    warns = run["warnings"]

    notes  = [r.get("notes", "") or "" for r in rows]
    boots  = [r.get("boot_count", "") for r in rows if r.get("boot_count", "")]
    uptimes= [int(r["uptime_ms"]) for r in rows if r.get("uptime_ms", "").strip()]

    has_start = any("START_RUN" in n for n in notes)
    has_end   = any(n in ("END_RUN", "ABORTED") for n in notes)

    if not has_start:
        warns.append("START_RUN ausente")
    if not has_end:
        warns.append("END_RUN ausente — run INCOMPLETO")
        run["status"] = "INCOMPLETE"

    unique_boots = set(boots)
    if len(unique_boots) > 1:
        warns.append(f"boot_count mudou ({unique_boots}) — REBOOT durante o run")
        run["status"] = "INVALID"

    non_mono = any(uptimes[i] < uptimes[i-1] for i in range(1, len(uptimes)))
    if non_mono:
        warns.append("uptime_ms não monotônico")

    if run["meta"]:
        first_s = next((r for r in rows if r.get("type") == "S"), None)
        if first_s:
            csv_ant = (first_s.get("antenna") or "").upper()
            meta_ant = run["meta"].get("antenna", "").upper()
            if csv_ant and meta_ant and csv_ant != meta_ant:
                warns.append(f"Antena no nome ({meta_ant}) difere do CSV ({csv_ant})")

    return run

# ══════════════════════════════════════════════════════════════
#  3. MÉTRICAS — helpers
# ══════════════════════════════════════════════════════════════
def _pct(lst, p):
    s = [x for x in lst if x is not None and not math.isnan(x)]
    if not s: return float("nan")
    s.sort()
    i = max(0, math.ceil(len(s) * p / 100) - 1)
    return s[i]

def _mean(lst):
    s = [x for x in lst if x is not None and not math.isnan(x)]
    return sum(s) / len(s) if s else float("nan")

def _median(lst):
    return _pct(lst, 50)

def _iqr(lst):
    return _pct(lst, 75) - _pct(lst, 25)

# ══════════════════════════════════════════════════════════════
#  4. AGREGAÇÃO POR PERFIL
# ══════════════════════════════════════════════════════════════
def aggregate_burn(rows: list) -> dict:
    """Perfil A (BURN 3×60): agrega RSSI, throughput, PLR por bloco."""
    blocks = defaultdict(lambda: {"rssi": [], "tput": [], "plr": []})
    for r in rows:
        if r.get("type") != "S": continue
        try:
            blk  = int(r.get("block") or 0)
            rssi = int(r.get("rssi_dbm") or -127)
            tput = int(r.get("throughput_bps") or 0)
            plr  = float(r.get("plr_window") or 0.0)
        except (ValueError, TypeError):
            continue
        blocks[blk]["rssi"].append(rssi)
        blocks[blk]["tput"].append(tput)
        blocks[blk]["plr"].append(plr)

    result = {}
    for blk, d in sorted(blocks.items()):
        result[blk] = {
            "rssi_median": _median(d["rssi"]),
            "rssi_p10":    _pct(d["rssi"], 10),
            "tput_median": _median(d["tput"]),
            "tput_p10":    _pct(d["tput"], 10),
            "plr_median":  _median(d["plr"]),
            "n":           len(d["rssi"]),
        }
    return result

def aggregate_walk(rows: list) -> dict:
    """Perfil B WALK: TTR + RSSI."""
    DISC_THRESHOLD = 3
    pings = [r for r in rows if r.get("type") == "S"]
    rssi_list, ttr_list = [], []
    consec_fail, in_disc, disc_ts = 0, False, 0.0

    for r in pings:
        ok   = int(r.get("ping_ok") or 0)
        rssi = int(r.get("rssi_dbm") or -127)
        ts   = float(r.get("timestamp_ms") or 0)
        rssi_list.append(rssi)

        if ok == 0:
            consec_fail += 1
            if consec_fail >= DISC_THRESHOLD and not in_disc:
                in_disc = True
                disc_ts = ts
        else:
            if in_disc:
                ttr_list.append((ts - disc_ts) / 1000)
            in_disc, consec_fail = False, 0

    return {
        "rssi_median":  _median(rssi_list),
        "rssi_p10":     _pct(rssi_list, 10),
        "ttr_median_s": _median(ttr_list),
        "ttr_p90_s":    _pct(ttr_list, 90),
        "disc_events":  len(ttr_list),
        "n":            len(pings),
    }

def aggregate_clock(rows: list) -> dict:
    """Perfil B CLOCK: GROUP BY marker."""
    by_marker = defaultdict(lambda: {"rssi": [], "ok": [], "lat": []})
    for r in rows:
        if r.get("type") != "S": continue
        marker = (r.get("marker") or "SEM_MARK").strip() or "SEM_MARK"
        try:
            rssi = int(r.get("rssi_dbm") or -127)
            ok   = int(r.get("ping_ok") or 0)
            lat  = float(r.get("ping_latency_ms") or 0)
        except (ValueError, TypeError):
            continue
        by_marker[marker]["rssi"].append(rssi)
        by_marker[marker]["ok"].append(ok)
        by_marker[marker]["lat"].append(lat)

    result = {}
    for mark, d in by_marker.items():
        n   = len(d["ok"])
        plr = (1 - sum(d["ok"]) / n) * 100 if n else 100.0
        result[mark] = {
            "rssi_median": _median(d["rssi"]),
            "rssi_p10":    _pct(d["rssi"], 10),
            "plr_pct":     plr,
            "lat_median":  _median(d["lat"]),
            "n":           n,
        }
    return result

# ══════════════════════════════════════════════════════════════
#  5. CONSOLIDAÇÃO (múltiplos runs → mediana)
# ══════════════════════════════════════════════════════════════
def consolidate_burn(agg_list: list) -> dict:
    if not agg_list:
        return {}
    all_blocks = set(b for a in agg_list for b in a.keys())
    result = {}
    for blk in sorted(all_blocks):
        rssi_vals = [a[blk]["rssi_p10"]    for a in agg_list if blk in a]
        tput_vals = [a[blk]["tput_median"] for a in agg_list if blk in a]
        plr_vals  = [a[blk]["plr_median"]  for a in agg_list if blk in a]
        result[blk] = {
            "rssi_p10":    _median(rssi_vals),
            "tput_median": _median(tput_vals),
            "plr_median":  _median(plr_vals),
            "n_runs":      len(rssi_vals),
        }
    return result

def consolidate_walk(agg_list: list) -> dict:
    if not agg_list:
        return {}
    return {
        "rssi_p10":     _median([a["rssi_p10"]     for a in agg_list]),
        "rssi_median":  _median([a["rssi_median"]  for a in agg_list]),
        "ttr_median_s": _median([a["ttr_median_s"] for a in agg_list]),
        "disc_events":  _median([a["disc_events"]  for a in agg_list]),
        "n_runs":       len(agg_list),
    }

def consolidate_clock(agg_list: list) -> dict:
    if not agg_list:
        return {}
    all_marks = set(m for a in agg_list for m in a.keys())
    result = {"markers": {}, "n_runs": len(agg_list)}
    for mark in sorted(all_marks):
        runs_with = [a[mark] for a in agg_list if mark in a]
        result["markers"][mark] = {
            "rssi_median": _median([r["rssi_median"] for r in runs_with]),
            "rssi_p10":    _median([r["rssi_p10"]    for r in runs_with]),
            "plr_pct":     _median([r["plr_pct"]     for r in runs_with]),
            "n_runs":      len(runs_with),
        }
    return result

# ══════════════════════════════════════════════════════════════
#  6. SCORE RF (0–100)
# ══════════════════════════════════════════════════════════════
DEFAULT_WEIGHTS = {"plr": 0.30, "ttr": 0.25, "rssi": 0.25, "tput": 0.20}

def compute_scores(antenna_metrics: dict, weights: dict) -> dict:
    """
    antenna_metrics: {ant: {rssi_p10, tput_median, plr_median, ttr_median_s}}
    Retorna {ant: score_0_100}
    """
    if not antenna_metrics:
        return {}

    def _norm_min(vals):  # menor = melhor
        lo, hi = min(vals.values()), max(vals.values())
        if hi == lo: return {k: 1.0 for k in vals}
        return {k: 1.0 - (v - lo) / (hi - lo) for k, v in vals.items()}

    def _norm_max(vals):  # maior = melhor
        lo, hi = min(vals.values()), max(vals.values())
        if hi == lo: return {k: 1.0 for k in vals}
        return {k: (v - lo) / (hi - lo) for k, v in vals.items()}

    plr_n  = _norm_min({a: d.get("plr_median",  100.0) for a, d in antenna_metrics.items()})
    ttr_n  = _norm_min({a: d.get("ttr_median_s", 999.0) for a, d in antenna_metrics.items()})
    rssi_n = _norm_max({a: d.get("rssi_p10",    -127.0) for a, d in antenna_metrics.items()})
    tput_n = _norm_max({a: d.get("tput_median",    0.0) for a, d in antenna_metrics.items()})

    scores = {}
    for ant in antenna_metrics:
        s = (weights.get("plr",  0.30) * plr_n[ant]  +
             weights.get("ttr",  0.25) * ttr_n[ant]  +
             weights.get("rssi", 0.25) * rssi_n[ant] +
             weights.get("tput", 0.20) * tput_n[ant])
        scores[ant] = round(s * 100, 1)
    return scores

# ══════════════════════════════════════════════════════════════
#  7. PIPELINE PRINCIPAL
# ══════════════════════════════════════════════════════════════
def run_pipeline(campaign_dir: Path, weights: dict):
    print(f"\nRF Field Validator — Parser N2.1")
    print(f"Campanha: {campaign_dir}\n{'─'*50}")

    # Localiza CSVs
    logs_dir = campaign_dir / "logs"
    if not logs_dir.exists():
        logs_dir = campaign_dir
    csv_files = sorted(f for f in logs_dir.glob("*.csv")
                       if FILENAME_RE.match(f.name))

    if not csv_files:
        print(f"[ERRO] Nenhum CSV válido encontrado em {logs_dir}")
        sys.exit(1)
    print(f"Arquivos encontrados: {len(csv_files)}\n")

    # Ingestão e validação
    runs = []
    for p in csv_files:
        run = ingest_file(p)
        validate_run(run)
        runs.append(run)
        n_s = sum(1 for r in run["rows"] if r.get("type") == "S")
        st  = run["status"]
        flag = "OK " if st == "VALID" else "!!!"
        print(f"  [{flag}] {p.name:45s} {n_s:3d} amostras  [{st}]")
        for w in run["warnings"]:
            print(f"        AVISO: {w}")

    valid_runs = [r for r in runs if r["status"] in ("VALID", "SUSPECT", "INCOMPLETE")]

    # Agrega por (antena, modo)
    by_ant_mode = defaultdict(list)
    for run in valid_runs:
        meta = run.get("meta", {})
        if not meta: continue
        key = (meta["antenna"], meta["mode"])
        by_ant_mode[key].append(run)

    # Consolida por antena
    consolidated = {}   # {(ant, mode): dados consolidados}
    antenna_metrics = {}  # {ant: {rssi_p10, tput_median, plr_median, ttr_median_s}}
    raw_samples = defaultdict(list)  # {ant: [todas as linhas S de todos os runs]}

    for (ant, mode), grp in sorted(by_ant_mode.items()):
        agg_list = []
        for run in grp:
            if mode == "BURN":
                agg_list.append(aggregate_burn(run["rows"]))
                for r in run["rows"]:
                    if r.get("type") == "S":
                        raw_samples[ant].append(r)
            elif mode == "WALK":
                agg_list.append(aggregate_walk(run["rows"]))
                for r in run["rows"]:
                    if r.get("type") == "S":
                        raw_samples[ant].append(r)
            elif mode == "CLOCK":
                agg_list.append(aggregate_clock(run["rows"]))

        if mode == "BURN":
            cons = consolidate_burn(agg_list)
            consolidated[(ant, mode)] = cons
            # Extrai métricas para score
            rssi_vals = [cons[b]["rssi_p10"]    for b in cons]
            tput_vals = [cons[b]["tput_median"] for b in cons]
            plr_vals  = [cons[b]["plr_median"]  for b in cons]
            if ant not in antenna_metrics:
                antenna_metrics[ant] = {"rssi_p10": -127.0, "tput_median": 0.0,
                                        "plr_median": 100.0, "ttr_median_s": 999.0}
            d = antenna_metrics[ant]
            if rssi_vals: d["rssi_p10"]    = max(d["rssi_p10"],    _median(rssi_vals))
            if tput_vals: d["tput_median"] = max(d["tput_median"], _median(tput_vals))
            if plr_vals:  d["plr_median"]  = min(d["plr_median"],  _median(plr_vals))

        elif mode == "WALK":
            cons = consolidate_walk(agg_list)
            consolidated[(ant, mode)] = cons
            if ant not in antenna_metrics:
                antenna_metrics[ant] = {"rssi_p10": -127.0, "tput_median": 0.0,
                                        "plr_median": 100.0, "ttr_median_s": 999.0}
            d = antenna_metrics[ant]
            if not math.isnan(cons.get("rssi_p10", float("nan"))):
                d["rssi_p10"] = max(d["rssi_p10"], cons["rssi_p10"])
            if not math.isnan(cons.get("ttr_median_s", float("nan"))):
                d["ttr_median_s"] = min(d["ttr_median_s"], cons["ttr_median_s"])

        elif mode == "CLOCK":
            cons = consolidate_clock(agg_list)
            consolidated[(ant, mode)] = cons
            if ant not in antenna_metrics:
                antenna_metrics[ant] = {"rssi_p10": -127.0, "tput_median": 0.0,
                                        "plr_median": 100.0, "ttr_median_s": 999.0}
            d = antenna_metrics[ant]
            marker_rssi = [v["rssi_p10"] for v in cons.get("markers", {}).values()]
            if marker_rssi:
                d["rssi_p10"] = max(d["rssi_p10"], _median(marker_rssi))

    # Score RF
    scores = compute_scores(antenna_metrics, weights)
    print(f"\nScores RF:")
    for ant, sc in sorted(scores.items(), key=lambda x: x[1], reverse=True):
        bar = "█" * int(sc / 5)
        print(f"  {ant:6s}: {sc:5.1f}  {bar}")

    # Exporta summary.csv
    report_dir = campaign_dir / "report"
    report_dir.mkdir(exist_ok=True)
    summary_path = report_dir / "summary.csv"
    with open(summary_path, "w", newline="", encoding="utf-8") as f:
        w = csv.writer(f)
        w.writerow(["antenna","score","rssi_p10_dbm","tput_median_bps","plr_median_pct","ttr_median_s"])
        for ant, d in sorted(antenna_metrics.items()):
            w.writerow([ant, scores.get(ant, ""), d["rssi_p10"], d["tput_median"],
                        d["plr_median"], d["ttr_median_s"]])
    print(f"\nSummary CSV: {summary_path}")

    # Relatório HTML
    out_html = report_dir / "report.html"
    render_report(out_html, campaign_dir.name, runs, scores,
                  antenna_metrics, consolidated, raw_samples)
    print(f"Relatório:   {out_html}")
    print(f"\nAbra o arquivo no navegador para ver os gráficos.")

# ══════════════════════════════════════════════════════════════
#  8. RELATÓRIO HTML
# ══════════════════════════════════════════════════════════════
def _nan_to_none(v):
    if v is None: return None
    try:
        return None if math.isnan(float(v)) else v
    except Exception:
        return v

def render_report(out_path: Path, campaign_name: str, runs: list,
                  scores: dict, antenna_metrics: dict,
                  consolidated: dict, raw_samples: dict):

    now = datetime.now().strftime("%d/%m/%Y %H:%M")
    sorted_ants = sorted(scores.keys(), key=lambda a: scores[a], reverse=True)

    # ── Dados para os gráficos (JSON) ──────────────────────────
    colors = ["#58a6ff","#3fb950","#f78166","#d29922","#a371f7",
              "#39d353","#ff7b72","#ffa657","#79c0ff","#56d364"]
    ant_colors = {a: colors[i % len(colors)] for i, a in enumerate(sorted_ants)}

    # RSSI e throughput por amostra (time series)
    series_data = {}
    for ant in sorted_ants:
        samples = raw_samples.get(ant, [])
        if not samples: continue
        series_data[ant] = {
            "ts":   [int(r.get("timestamp_ms") or 0) for r in samples],
            "rssi": [int(r.get("rssi_dbm") or -127) for r in samples],
            "tput": [int(r.get("throughput_bps") or 0) for r in samples],
        }

    # Métricas resumidas por antena
    summary_labels = sorted_ants
    rssi_vals  = [_nan_to_none(antenna_metrics[a]["rssi_p10"])    for a in sorted_ants]
    tput_vals  = [_nan_to_none(antenna_metrics[a]["tput_median"]) for a in sorted_ants]
    plr_vals   = [_nan_to_none(antenna_metrics[a]["plr_median"])  for a in sorted_ants]
    score_vals = [scores[a] for a in sorted_ants]

    # ── Tabela de runs ──────────────────────────────────────────
    run_rows = ""
    for run in runs:
        st = run.get("status", "?")
        color = {"VALID":"#3fb950","INCOMPLETE":"#d29922",
                 "INVALID":"#f85149","SUSPECT":"#ffa657"}.get(st, "#8b949e")
        meta = run.get("meta", {})
        mode = meta.get("mode", "?")
        ant  = meta.get("antenna", "?")
        rn   = meta.get("run_number", "?")
        n_s  = sum(1 for r in run["rows"] if r.get("type") == "S")
        warns = "; ".join(run.get("warnings", []))[:120] or "—"
        run_rows += f"""
<tr>
  <td>{Path(run['path']).name}</td>
  <td>{ant}</td><td>{mode}</td><td>R{rn:02d}</td>
  <td>{n_s}</td>
  <td style="color:{color};font-weight:700">{st}</td>
  <td style="font-size:11px;color:#8b949e">{warns}</td>
</tr>"""

    # ── Score badges ────────────────────────────────────────────
    score_badges = ""
    for rank, ant in enumerate(sorted_ants, 1):
        sc   = scores[ant]
        col  = "#3fb950" if sc >= 70 else "#d29922" if sc >= 40 else "#f85149"
        pct  = min(100, max(0, int(sc)))
        crown = " 👑" if rank == 1 else ""
        score_badges += f"""
<div style="margin-bottom:14px">
  <div style="display:flex;justify-content:space-between;align-items:center;margin-bottom:4px">
    <span style="font-weight:700;font-size:1.05em;color:#e6edf3">#{rank} {ant}{crown}</span>
    <span style="font-weight:900;font-size:1.3em;color:{col}">{sc:.1f}</span>
  </div>
  <div style="background:#21262d;border-radius:6px;height:14px;overflow:hidden">
    <div style="background:{col};height:100%;width:{pct}%;border-radius:6px;
                transition:width .6s ease"></div>
  </div>
  <div style="display:flex;gap:16px;margin-top:6px;font-size:11px;color:#8b949e">
    <span>RSSI P10: <strong style="color:#e6edf3">{antenna_metrics[ant]['rssi_p10']:.0f} dBm</strong></span>
    <span>Throughput: <strong style="color:#e6edf3">{antenna_metrics[ant]['tput_median']/1e6:.2f} Mbps</strong></span>
    <span>PLR: <strong style="color:#e6edf3">{antenna_metrics[ant]['plr_median']:.1f}%</strong></span>
  </div>
</div>"""

    # ── Monta JSON para Chart.js ────────────────────────────────
    chart_json = json.dumps({
        "antennas":      sorted_ants,
        "colors":        [ant_colors[a] for a in sorted_ants],
        "scores":        score_vals,
        "rssi":          rssi_vals,
        "tput_mbps":     [t/1e6 if t else None for t in tput_vals],
        "plr":           plr_vals,
        "series":        series_data,
    }, ensure_ascii=False)

    html = f"""<!DOCTYPE html>
<html lang="pt-BR">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
<title>Relatório RF — {campaign_name}</title>
<script src="https://cdn.jsdelivr.net/npm/chart.js@4.4.0/dist/chart.umd.min.js"></script>
<style>
*{{box-sizing:border-box;margin:0;padding:0}}
body{{background:#0d1117;color:#c9d1d9;font-family:system-ui,sans-serif;padding:20px;max-width:1100px;margin:auto}}
h1{{font-size:1.6em;font-weight:900;color:#f0f6fc;margin-bottom:4px}}
h2{{font-size:.8em;text-transform:uppercase;letter-spacing:.1em;color:#8b949e;
   margin:28px 0 12px;padding-bottom:6px;border-bottom:1px solid #21262d}}
.grid2{{display:grid;grid-template-columns:1fr 1fr;gap:16px;margin-bottom:16px}}
.grid3{{display:grid;grid-template-columns:1fr 1fr 1fr;gap:16px;margin-bottom:16px}}
.card{{background:#161b22;border:1px solid #30363d;border-radius:8px;padding:16px}}
.chart-card{{background:#161b22;border:1px solid #30363d;border-radius:8px;padding:16px;margin-bottom:16px}}
table{{width:100%;border-collapse:collapse;font-size:13px}}
th{{background:#161b22;color:#8b949e;font-size:10px;text-transform:uppercase;
   letter-spacing:.06em;padding:7px 10px;text-align:left;border-bottom:1px solid #30363d}}
td{{padding:7px 10px;border-bottom:1px solid #21262d;font-size:12px}}
tr:last-child td{{border-bottom:none}}
.tag{{display:inline-block;padding:1px 7px;border-radius:4px;font-size:10px;font-weight:700}}
footer{{margin-top:32px;font-size:11px;color:#484f58;text-align:center;padding-top:16px;
        border-top:1px solid #21262d}}
@media(max-width:700px){{.grid2,.grid3{{grid-template-columns:1fr}}}}
</style>
</head>
<body>

<div style="margin-bottom:24px">
  <h1>Relatório RF de Campo</h1>
  <p style="color:#8b949e;font-size:13px;margin-top:4px">
    Campanha: <strong style="color:#c9d1d9">{campaign_name}</strong>
    &nbsp;·&nbsp; Gerado em {now}
    &nbsp;·&nbsp; {len(runs)} runs · {len(sorted_ants)} antenas
  </p>
</div>

<h2>Ranking de Antenas — Score RF Composto</h2>
<div class="card">
  {score_badges}
  <p style="font-size:11px;color:#484f58;margin-top:8px">
    Score = 30% PLR + 25% TTR + 25% RSSI P10 + 20% Throughput (normalizado min-max entre antenas)
  </p>
</div>

<h2>Comparação de Métricas</h2>
<div class="grid3">
  <div class="card" style="text-align:center">
    <div style="font-size:11px;color:#8b949e;margin-bottom:8px">RSSI P10</div>
    <canvas id="chartRssi" height="220"></canvas>
  </div>
  <div class="card" style="text-align:center">
    <div style="font-size:11px;color:#8b949e;margin-bottom:8px">Throughput Médio</div>
    <canvas id="chartTput" height="220"></canvas>
  </div>
  <div class="card" style="text-align:center">
    <div style="font-size:11px;color:#8b949e;margin-bottom:8px">PLR Médio</div>
    <canvas id="chartPlr" height="220"></canvas>
  </div>
</div>

<h2>RSSI ao Longo do Tempo</h2>
<div class="chart-card">
  <canvas id="chartRssiTime" height="120"></canvas>
</div>

<h2>Throughput ao Longo do Tempo</h2>
<div class="chart-card">
  <canvas id="chartTputTime" height="120"></canvas>
</div>

<h2>Validação de Runs</h2>
<table>
  <tr>
    <th>Arquivo</th><th>Antena</th><th>Modo</th><th>Run</th>
    <th>Amostras</th><th>Status</th><th>Avisos</th>
  </tr>
  {run_rows}
</table>

<footer>
  RF Field Validator N2.1 · Terasite Tecnologia · {now}
</footer>

<script>
const D = {chart_json};

const FONT = {{color:'#8b949e',size:11}};
const GRID = 'rgba(48,54,61,0.8)';
Chart.defaults.color = '#8b949e';
Chart.defaults.font.family = 'system-ui,sans-serif';

function barChart(id, labels, datasets, opts={{}}) {{
  return new Chart(document.getElementById(id), {{
    type: 'bar',
    data: {{ labels, datasets }},
    options: {{
      responsive: true,
      plugins: {{ legend: {{ labels: {{ color:'#c9d1d9',font:{{size:11}} }} }} }},
      scales: {{
        x: {{ ticks: {{ color:'#8b949e',font:{{size:10}} }}, grid:{{ color:GRID }} }},
        y: {{ ...opts, ticks: {{ color:'#8b949e',font:{{size:10}} }}, grid:{{ color:GRID }} }}
      }}
    }}
  }});
}}

// RSSI P10
barChart('chartRssi', D.antennas, [{{
  label: 'RSSI P10 (dBm)',
  data: D.rssi,
  backgroundColor: D.colors.map(c => c+'99'),
  borderColor: D.colors,
  borderWidth: 2,
  borderRadius: 4,
}}], {{ min: -100, max: -40, reverse: false }});

// Throughput
barChart('chartTput', D.antennas, [{{
  label: 'Throughput médio (Mbps)',
  data: D.tput_mbps,
  backgroundColor: D.colors.map(c => c+'99'),
  borderColor: D.colors,
  borderWidth: 2,
  borderRadius: 4,
}}]);

// PLR
barChart('chartPlr', D.antennas, [{{
  label: 'PLR médio (%)',
  data: D.plr,
  backgroundColor: D.colors.map(c => c+'99'),
  borderColor: D.colors,
  borderWidth: 2,
  borderRadius: 4,
}}], {{ min: 0 }});

// Time series — RSSI
(function() {{
  const datasets = [];
  Object.entries(D.series).forEach(([ant, s], i) => {{
    if (!s.rssi || !s.rssi.length) return;
    datasets.push({{
      label: ant,
      data: s.rssi.map((v, j) => ({{x: j, y: v}})),
      borderColor: D.colors[i] || '#58a6ff',
      backgroundColor: 'transparent',
      pointRadius: 3,
      tension: 0.3,
    }});
  }});
  if (!datasets.length) return;
  new Chart(document.getElementById('chartRssiTime'), {{
    type: 'line',
    data: {{ datasets }},
    options: {{
      responsive: true,
      plugins: {{ legend: {{ labels: {{ color:'#c9d1d9',font:{{size:11}} }} }} }},
      scales: {{
        x: {{ type:'linear', title:{{display:true,text:'Amostra',color:'#8b949e'}},
              ticks:{{color:'#8b949e',font:{{size:10}}}}, grid:{{color:GRID}} }},
        y: {{ title:{{display:true,text:'RSSI (dBm)',color:'#8b949e'}},
              ticks:{{color:'#8b949e',font:{{size:10}}}}, grid:{{color:GRID}} }},
      }}
    }}
  }});
}})();

// Time series — Throughput
(function() {{
  const datasets = [];
  Object.entries(D.series).forEach(([ant, s], i) => {{
    if (!s.tput || !s.tput.length) return;
    datasets.push({{
      label: ant,
      data: s.tput.map((v, j) => ({{x: j, y: v/1e6}})),
      borderColor: D.colors[i] || '#58a6ff',
      backgroundColor: 'transparent',
      pointRadius: 3,
      tension: 0.3,
    }});
  }});
  if (!datasets.length) return;
  new Chart(document.getElementById('chartTputTime'), {{
    type: 'line',
    data: {{ datasets }},
    options: {{
      responsive: true,
      plugins: {{ legend: {{ labels: {{ color:'#c9d1d9',font:{{size:11}} }} }} }},
      scales: {{
        x: {{ type:'linear', title:{{display:true,text:'Amostra',color:'#8b949e'}},
              ticks:{{color:'#8b949e',font:{{size:10}}}}, grid:{{color:GRID}} }},
        y: {{ title:{{display:true,text:'Throughput (Mbps)',color:'#8b949e'}},
              min: 0,
              ticks:{{color:'#8b949e',font:{{size:10}}}}, grid:{{color:GRID}} }},
      }}
    }}
  }});
}})();
</script>
</body>
</html>"""

    out_path.parent.mkdir(parents=True, exist_ok=True)
    out_path.write_text(html, encoding="utf-8")

# ══════════════════════════════════════════════════════════════
#  MAIN
# ══════════════════════════════════════════════════════════════
def _parse_weights(s: str) -> dict:
    w = dict(DEFAULT_WEIGHTS)
    for part in (s or "").split(","):
        if "=" in part:
            k, v = part.split("=", 1)
            if k.strip() in w:
                w[k.strip()] = float(v.strip())
    return w

if __name__ == "__main__":
    ap = argparse.ArgumentParser(description="Parser offline RF Field Validator N2.1")
    ap.add_argument("campaign_dir",
                    help="Pasta com os CSVs (ou com subpasta logs/)")
    ap.add_argument("--weights", default="",
                    help="Ex: plr=0.30,ttr=0.25,rssi=0.25,tput=0.20")
    args = ap.parse_args()
    run_pipeline(Path(args.campaign_dir), _parse_weights(args.weights))
