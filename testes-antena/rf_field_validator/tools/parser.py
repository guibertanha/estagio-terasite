#!/usr/bin/env python3
"""
parser.py — Pipeline offline de análise RF (spec N2.1)

Uso:
    python tools/parser.py <pasta_com_csvs> [--weights plr=0.30,ttr=0.25,rssi=0.25,tput=0.20]

    A pasta pode conter os CSVs diretamente ou numa subpasta logs/.
    Gera: <pasta>/report/report.html  e  <pasta>/report/summary.csv
"""

import sys, re, csv, math, json, argparse, statistics
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
        rssi = d["rssi"]
        tput = d["tput"]
        result[blk] = {
            "rssi_median": _median(rssi),
            "rssi_p10":    _pct(rssi, 10),
            "rssi_p90":    _pct(rssi, 90),
            "rssi_min":    min(rssi) if rssi else float("nan"),
            "rssi_max":    max(rssi) if rssi else float("nan"),
            "rssi_std":    statistics.stdev(rssi) if len(rssi) > 1 else 0.0,
            "tput_median": _median(tput),
            "tput_p10":    _pct(tput, 10),
            "plr_median":  _median(d["plr"]),
            "n":           len(rssi),
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
        g = [a[blk] for a in agg_list if blk in a]
        result[blk] = {
            "rssi_p10":    _median([x["rssi_p10"]    for x in g]),
            "rssi_p90":    _median([x["rssi_p90"]    for x in g]),
            "rssi_median": _median([x["rssi_median"] for x in g]),
            "rssi_min":    _median([x["rssi_min"]    for x in g]),
            "rssi_max":    _median([x["rssi_max"]    for x in g]),
            "rssi_std":    _median([x["rssi_std"]    for x in g]),
            "tput_median": _median([x["tput_median"] for x in g]),
            "tput_p10":    _median([x["tput_p10"]    for x in g]),
            "plr_median":  _median([x["plr_median"]  for x in g]),
            "n_runs":      len(g),
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

# Valor sentinela que indica "sem dados" (nunca houve WALK para medir TTR)
_TTR_NODATA = 999.0
_TTR_NODATA_THRESHOLD = 998.0

def compute_scores(antenna_metrics: dict, weights: dict) -> tuple:
    """
    antenna_metrics: {ant: {rssi_p10, tput_median, plr_median, ttr_median_s}}
    Retorna (scores_dict, effective_weights_dict) onde:
      - scores_dict = {ant: score_0_100}
      - effective_weights_dict = pesos efetivamente usados (TTR excluído se ausente)
    """
    if not antenna_metrics:
        return {}, weights

    def _norm_min(vals):  # menor = melhor
        lo, hi = min(vals.values()), max(vals.values())
        if hi == lo: return {k: 1.0 for k in vals}
        return {k: 1.0 - (v - lo) / (hi - lo) for k, v in vals.items()}

    def _norm_max(vals):  # maior = melhor
        lo, hi = min(vals.values()), max(vals.values())
        if hi == lo: return {k: 1.0 for k in vals}
        return {k: (v - lo) / (hi - lo) for k, v in vals.items()}

    # Verifica se alguma antena tem dados de TTR (requer WALK)
    ttr_vals = {a: d.get("ttr_median_s", _TTR_NODATA) for a, d in antenna_metrics.items()}
    has_ttr = any(v < _TTR_NODATA_THRESHOLD for v in ttr_vals.values())

    plr_n  = _norm_min({a: d.get("plr_median",  100.0) for a, d in antenna_metrics.items()})
    rssi_n = _norm_max({a: d.get("rssi_p10",    -127.0) for a, d in antenna_metrics.items()})
    tput_n = _norm_max({a: d.get("tput_median",    0.0) for a, d in antenna_metrics.items()})

    # Se não há dados de TTR, redistribui o peso para os demais eixos proporcionalmente
    if has_ttr:
        ttr_n = _norm_min(ttr_vals)
        eff_weights = dict(weights)
    else:
        ttr_n = {a: 0.0 for a in antenna_metrics}
        w_ttr = weights.get("ttr", 0.25)
        total_rest = sum(weights.get(k, 0) for k in ("plr", "rssi", "tput"))
        if total_rest > 0:
            factor = (total_rest + w_ttr) / total_rest
        else:
            factor = 1.0
        eff_weights = {
            "plr":  round(weights.get("plr",  0.30) * factor, 4),
            "ttr":  0.0,
            "rssi": round(weights.get("rssi", 0.25) * factor, 4),
            "tput": round(weights.get("tput", 0.20) * factor, 4),
        }

    scores = {}
    for ant in antenna_metrics:
        s = (eff_weights.get("plr",  0.30) * plr_n[ant]  +
             eff_weights.get("ttr",  0.25) * ttr_n[ant]  +
             eff_weights.get("rssi", 0.25) * rssi_n[ant] +
             eff_weights.get("tput", 0.20) * tput_n[ant])
        scores[ant] = round(s * 100, 1)
    return scores, eff_weights

# ══════════════════════════════════════════════════════════════
#  7. PIPELINE PRINCIPAL
# ══════════════════════════════════════════════════════════════
def run_pipeline(campaign_dir: Path, weights: dict):
    print(f"\nRF Field Validator — Parser N2.1")
    print(f"Campanha: {campaign_dir}\n{'─'*50}")

    # Localiza CSVs — tenta pasta direta, logs/ ou recursivo em subpastas
    logs_dir = campaign_dir / "logs"
    if not logs_dir.exists():
        logs_dir = campaign_dir

    csv_files = sorted(f for f in logs_dir.glob("*.csv")
                       if FILENAME_RE.match(f.name))

    # Sem CSVs diretos → varre subpastas (modo multi-campanha)
    if not csv_files:
        csv_files = sorted(f for f in logs_dir.rglob("*.csv")
                           if FILENAME_RE.match(f.name)
                           and "report" not in f.parts)

    if not csv_files:
        print(f"[ERRO] Nenhum CSV válido encontrado em {logs_dir}")
        sys.exit(1)

    n_camps = len(set(f.parent for f in csv_files))
    if n_camps > 1:
        print(f"Modo multi-campanha: {n_camps} pasta(s), {len(csv_files)} arquivo(s) total\n")
    else:
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
                antenna_metrics[ant] = {
                    "rssi_p10": -127.0, "rssi_p90": -127.0, "rssi_median": -127.0,
                    "rssi_min": -127.0, "rssi_max": -127.0, "rssi_std": 0.0,
                    "tput_median": 0.0, "tput_p10": 0.0,
                    "plr_median": 100.0, "ttr_median_s": 999.0,
                }
            d = antenna_metrics[ant]
            if rssi_vals: d["rssi_p10"]    = max(d["rssi_p10"],    _median(rssi_vals))
            if tput_vals: d["tput_median"] = max(d["tput_median"], _median(tput_vals))
            if plr_vals:  d["plr_median"]  = min(d["plr_median"],  _median(plr_vals))
            for field in ("rssi_p90","rssi_median","rssi_min","rssi_max","tput_p10"):
                vals = [cons[b][field] for b in cons if field in cons[b]]
                if vals: d[field] = _median(vals)
            std_vals = [cons[b]["rssi_std"] for b in cons if "rssi_std" in cons[b]]
            if std_vals: d["rssi_std"] = _mean(std_vals)

        elif mode == "WALK":
            cons = consolidate_walk(agg_list)
            consolidated[(ant, mode)] = cons
            if ant not in antenna_metrics:
                antenna_metrics[ant] = {
                    "rssi_p10": -127.0, "rssi_p90": -127.0, "rssi_median": -127.0,
                    "rssi_min": -127.0, "rssi_max": -127.0, "rssi_std": 0.0,
                    "tput_median": 0.0, "tput_p10": 0.0,
                    "plr_median": 100.0, "ttr_median_s": 999.0,
                }
            d = antenna_metrics[ant]
            if not math.isnan(cons.get("rssi_p10", float("nan"))):
                d["rssi_p10"] = max(d["rssi_p10"], cons["rssi_p10"])
            if not math.isnan(cons.get("ttr_median_s", float("nan"))):
                d["ttr_median_s"] = min(d["ttr_median_s"], cons["ttr_median_s"])

        elif mode == "CLOCK":
            cons = consolidate_clock(agg_list)
            consolidated[(ant, mode)] = cons
            if ant not in antenna_metrics:
                antenna_metrics[ant] = {
                    "rssi_p10": -127.0, "rssi_p90": -127.0, "rssi_median": -127.0,
                    "rssi_min": -127.0, "rssi_max": -127.0, "rssi_std": 0.0,
                    "tput_median": 0.0, "tput_p10": 0.0,
                    "plr_median": 100.0, "ttr_median_s": 999.0,
                }
            d = antenna_metrics[ant]
            marker_rssi = [v["rssi_p10"] for v in cons.get("markers", {}).values()]
            if marker_rssi:
                d["rssi_p10"] = max(d["rssi_p10"], _median(marker_rssi))

    # Score RF
    scores, eff_weights = compute_scores(antenna_metrics, weights)
    print(f"\nScores RF (pesos: PLR={eff_weights['plr']:.0%} TTR={eff_weights['ttr']:.0%} RSSI={eff_weights['rssi']:.0%} Tput={eff_weights['tput']:.0%}):")
    if eff_weights.get("ttr", 0) == 0:
        print("  [INFO] TTR excluido do score (sem dados de WALK)")
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
    render_report(out_html, campaign_dir.name, runs, scores, eff_weights,
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
                  scores: dict, eff_weights: dict, antenna_metrics: dict,
                  consolidated: dict, raw_samples: dict):

    now = datetime.now().strftime("%d/%m/%Y %H:%M")
    sorted_ants = sorted(scores.keys(), key=lambda a: scores[a], reverse=True)

    # ── Cores por antena ───────────────────────────────────────
    colors = ["#58a6ff","#3fb950","#f78166","#d29922","#a371f7",
              "#39d353","#ff7b72","#ffa657","#79c0ff","#56d364"]
    ant_colors = {a: colors[i % len(colors)] for i, a in enumerate(sorted_ants)}

    # ── Radar chart (5 eixos normalizados 0-100) ───────────────
    def _norm_radar(vals, higher_better=True):
        clean = {k: float(v) for k, v in vals.items()
                 if v is not None and not math.isnan(float(v))}
        if not clean:
            return {k: 50.0 for k in vals}
        lo, hi = min(clean.values()), max(clean.values())
        if hi == lo:
            return {k: 100.0 for k in vals}
        n = {k: (v - lo) / (hi - lo) for k, v in clean.items()}
        if not higher_better:
            n = {k: 1.0 - v for k, v in n.items()}
        return {k: round(n.get(k, 0.5) * 100, 1) for k in vals}

    rssi_r = _norm_radar({a: antenna_metrics[a]["rssi_p10"]    for a in sorted_ants})
    tput_r = _norm_radar({a: antenna_metrics[a]["tput_median"] for a in sorted_ants})
    conn_r = _norm_radar({a: antenna_metrics[a]["plr_median"]  for a in sorted_ants}, False)
    stab_r = _norm_radar({a: antenna_metrics[a]["rssi_std"]    for a in sorted_ants}, False)
    cons_r = _norm_radar({a: antenna_metrics[a]["tput_p10"] /
                            max(antenna_metrics[a]["tput_median"], 1)
                          for a in sorted_ants})
    radar_json = json.dumps({
        "labels": ["RSSI", "Throughput", "Conectividade", "Estabilidade", "Consistência"],
        "datasets": [
            {"label": a,
             "data":  [rssi_r[a], tput_r[a], conn_r[a], stab_r[a], cons_r[a]],
             "color": ant_colors[a]}
            for a in sorted_ants
        ]
    }, ensure_ascii=False)

    # ── Heatmap matrix ─────────────────────────────────────────
    def _cell(val, norm_0_1, fmt):
        if math.isnan(float(val if val is not None else float("nan"))):
            return '<td style="color:#484f58">—</td>'
        if norm_0_1 >= 0.66:
            bg, fg = "#1a4731", "#3fb950"
        elif norm_0_1 >= 0.33:
            bg, fg = "#2d2016", "#d29922"
        else:
            bg, fg = "#3d1616", "#f85149"
        return f'<td style="background:{bg};color:{fg};font-weight:700">{fmt(val)}</td>'

    heatmap_rows = ""
    rssi_n  = _norm_radar({a: antenna_metrics[a]["rssi_p10"]    for a in sorted_ants})
    tput_n  = _norm_radar({a: antenna_metrics[a]["tput_median"] for a in sorted_ants})
    plr_n   = _norm_radar({a: antenna_metrics[a]["plr_median"]  for a in sorted_ants}, False)
    stab_n  = _norm_radar({a: antenna_metrics[a]["rssi_std"]    for a in sorted_ants}, False)
    score_n = _norm_radar({a: scores[a] for a in sorted_ants})
    medals  = ["🥇", "🥈", "🥉"]
    for rank, ant in enumerate(sorted_ants, 1):
        m = antenna_metrics[ant]
        medal = medals[rank - 1] if rank <= 3 else f"#{rank}"
        heatmap_rows += (
            f"<tr>"
            f"<td style='font-weight:700;color:#e6edf3'>{medal} {ant}</td>"
            + _cell(m["rssi_p10"],    rssi_n[ant]  / 100, lambda v: f"{v:.0f} dBm")
            + _cell(m["tput_median"], tput_n[ant]  / 100, lambda v: f"{v/1e6:.2f} Mbps")
            + _cell(m["plr_median"],  plr_n[ant]   / 100, lambda v: f"{v:.1f}%")
            + _cell(m["rssi_std"],    stab_n[ant]  / 100, lambda v: f"σ {v:.1f} dB")
            + _cell(scores[ant],      score_n[ant] / 100, lambda v: f"{v:.1f}")
            + "</tr>"
        )

    # ── Distribuição RSSI (barras de range) ────────────────────
    rssi_all = [antenna_metrics[a]["rssi_p10"] for a in sorted_ants
                if not math.isnan(antenna_metrics[a]["rssi_p10"])]
    r_lo = min(rssi_all) - 5 if rssi_all else -100
    r_hi = max(rssi_all) + 5 if rssi_all else -40
    r_span = max(r_hi - r_lo, 1)

    def _pct_pos(v):
        return round((v - r_lo) / r_span * 100, 1)

    dist_rows = ""
    for ant in sorted_ants:
        m   = antenna_metrics[ant]
        col = ant_colors[ant]
        v_min = m.get("rssi_min",    m["rssi_p10"])
        v_p10 = m["rssi_p10"]
        v_med = m.get("rssi_median", m["rssi_p10"])
        v_p90 = m.get("rssi_p90",    m["rssi_p10"])
        v_max = m.get("rssi_max",    m["rssi_p10"])
        left  = _pct_pos(v_min)
        w_tot = _pct_pos(v_max) - left
        p10_l = _pct_pos(v_p10) - left
        p90_w = _pct_pos(v_p90) - _pct_pos(v_p10)
        med_l = _pct_pos(v_med) - left
        dist_rows += f"""
<div style="display:flex;align-items:center;gap:10px;margin-bottom:8px">
  <span style="width:36px;text-align:right;font-size:.85em;color:#e6edf3;
               font-weight:700">{ant}</span>
  <div style="flex:1;position:relative;height:22px;background:#0d1117;
              border-radius:4px;overflow:hidden">
    <div style="position:absolute;left:{left}%;width:{w_tot}%;height:100%;
                background:{col}22;border-radius:4px"></div>
    <div style="position:absolute;left:{left+p10_l}%;width:{p90_w}%;height:100%;
                background:{col}88"></div>
    <div style="position:absolute;left:{left+med_l}%;width:3px;height:100%;
                background:#f0f6fc"></div>
  </div>
  <span style="width:56px;font-size:.82em;color:#8b949e">{v_med:.0f} dBm</span>
</div>"""

    # ── Banner do vencedor ─────────────────────────────────────
    winner_html = ""
    if sorted_ants:
        w   = sorted_ants[0]
        m   = antenna_metrics[w]
        sc  = scores[w]
        col = ant_colors[w]
        runner = sorted_ants[1] if len(sorted_ants) > 1 else None
        gap = f"+{sc - scores[runner]:.1f} pts vs {runner}" if runner else ""
        winner_html = f"""
<div style="background:linear-gradient(135deg,#1a4731 0%,#161b22 100%);
            border:1px solid #238636;border-radius:10px;padding:20px 24px;
            margin-bottom:16px;display:flex;align-items:center;gap:20px">
  <div style="font-size:3em;line-height:1">🏆</div>
  <div style="flex:1">
    <div style="font-size:.72em;text-transform:uppercase;letter-spacing:.12em;
                color:#3fb950;margin-bottom:2px">Melhor antena</div>
    <div style="font-size:2.2em;font-weight:900;color:#f0f6fc;
                line-height:1.1">{w}</div>
    <div style="color:#3fb950;font-weight:700;margin-top:4px">
      Score RF: {sc:.1f} / 100
      <span style="color:#484f58;font-weight:400;font-size:.85em;
                   margin-left:8px">{gap}</span>
    </div>
  </div>
  <div style="text-align:right;line-height:2;font-size:.85em">
    <div style="color:#8b949e">RSSI P10
      <strong style="color:#e6edf3">{m['rssi_p10']:.0f} dBm</strong></div>
    <div style="color:#8b949e">Throughput
      <strong style="color:#e6edf3">{m['tput_median']/1e6:.2f} Mbps</strong></div>
    <div style="color:#8b949e">PLR
      <strong style="color:#e6edf3">{m['plr_median']:.1f}%</strong></div>
    <div style="color:#8b949e">Estabilidade
      <strong style="color:#e6edf3">σ {m['rssi_std']:.1f} dB</strong></div>
  </div>
</div>"""

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
body{{background:#0d1117;color:#c9d1d9;font-family:system-ui,sans-serif;
     padding:20px;max-width:1100px;margin:auto}}
h1{{font-size:1.6em;font-weight:900;color:#f0f6fc;margin-bottom:4px}}
h2{{font-size:.75em;text-transform:uppercase;letter-spacing:.12em;color:#8b949e;
    margin:28px 0 12px;padding-bottom:6px;border-bottom:1px solid #21262d}}
.grid2{{display:grid;grid-template-columns:1fr 1fr;gap:16px;margin-bottom:16px}}
.grid3{{display:grid;grid-template-columns:1fr 1fr 1fr;gap:16px;margin-bottom:16px}}
.card{{background:#161b22;border:1px solid #30363d;border-radius:8px;padding:16px}}
.chart-card{{background:#161b22;border:1px solid #30363d;border-radius:8px;
             padding:16px;margin-bottom:16px}}
table{{width:100%;border-collapse:collapse;font-size:13px}}
th{{background:#161b22;color:#8b949e;font-size:10px;text-transform:uppercase;
    letter-spacing:.06em;padding:8px 10px;text-align:left;
    border-bottom:1px solid #30363d}}
td{{padding:8px 10px;border-bottom:1px solid #21262d;font-size:12px}}
tr:last-child td{{border-bottom:none}}
tr:hover td{{background:#1c2128}}
footer{{margin-top:32px;font-size:11px;color:#484f58;text-align:center;
        padding-top:16px;border-top:1px solid #21262d}}
@media(max-width:700px){{.grid2,.grid3{{grid-template-columns:1fr}}}}
</style>
</head>
<body>

<div style="margin-bottom:24px">
  <h1>&#x1F4E1; Relatório RF de Campo</h1>
  <p style="color:#8b949e;font-size:13px;margin-top:4px">
    Campanha: <strong style="color:#c9d1d9">{campaign_name}</strong>
    &nbsp;·&nbsp; Gerado em {now}
    &nbsp;·&nbsp; {len(runs)} runs &nbsp;·&nbsp; {len(sorted_ants)} antenas
  </p>
</div>

{winner_html}

<h2>Ranking — Score RF Composto</h2>
<div class="grid2">
  <div class="card">
    {score_badges}
    <p style="font-size:10px;color:#484f58;margin-top:8px">
      Score = {eff_weights['plr']:.0%} PLR + {eff_weights['ttr']:.0%} TTR + {eff_weights['rssi']:.0%} RSSI P10 + {eff_weights['tput']:.0%} Throughput (min-max)
    </p>
  </div>
  <div class="card" style="display:flex;flex-direction:column;align-items:center">
    <div style="font-size:11px;color:#8b949e;margin-bottom:8px;align-self:flex-start">
      Perfil multidimensional</div>
    <canvas id="chartRadar" style="max-height:280px"></canvas>
  </div>
</div>

<h2>Tabela Comparativa</h2>
<div class="card" style="padding:0;overflow:hidden">
<table>
  <tr>
    <th>Antena</th>
    <th>RSSI P10</th>
    <th>Throughput</th>
    <th>PLR</th>
    <th>Estabilidade</th>
    <th>Score</th>
  </tr>
  {heatmap_rows}
</table>
</div>

<h2>Distribuição RSSI por Antena</h2>
<div class="card">
  <div style="display:flex;gap:20px;font-size:10px;color:#484f58;
              margin-bottom:12px;align-items:center">
    <span>&#9646; Range total</span>
    <span style="opacity:.8">&#9646; P10 – P90</span>
    <span style="background:#f0f6fc;width:3px;height:10px;display:inline-block"></span>
    <span>Mediana</span>
  </div>
  {dist_rows}
  <div style="display:flex;justify-content:space-between;
              font-size:10px;color:#484f58;margin-top:4px">
    <span>{r_lo:.0f} dBm</span><span>{r_hi:.0f} dBm</span>
  </div>
</div>

<h2>Comparação de Métricas</h2>
<div class="grid3">
  <div class="card" style="text-align:center">
    <div style="font-size:11px;color:#8b949e;margin-bottom:8px">RSSI P10 (dBm)</div>
    <canvas id="chartRssi" height="220"></canvas>
  </div>
  <div class="card" style="text-align:center">
    <div style="font-size:11px;color:#8b949e;margin-bottom:8px">Throughput Médio</div>
    <canvas id="chartTput" height="220"></canvas>
  </div>
  <div class="card" style="text-align:center">
    <div style="font-size:11px;color:#8b949e;margin-bottom:8px">PLR Médio (%)</div>
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
<div class="card" style="padding:0;overflow:hidden">
<table>
  <tr>
    <th>Arquivo</th><th>Antena</th><th>Modo</th><th>Run</th>
    <th>Amostras</th><th>Status</th><th>Avisos</th>
  </tr>
  {run_rows}
</table>
</div>

<footer>
  RF Field Validator N2.1 · Terasite Tecnologia · {now}
</footer>

<script>
const D = {chart_json};
const R = {radar_json};

const FONT = {{color:'#8b949e',size:11}};
const GRID = 'rgba(48,54,61,0.8)';
Chart.defaults.color = '#8b949e';
Chart.defaults.font.family = 'system-ui,sans-serif';

// Radar chart
new Chart(document.getElementById('chartRadar'), {{
  type: 'radar',
  data: {{
    labels: R.labels,
    datasets: R.datasets.map(d => ({{
      label: d.label,
      data: d.data,
      borderColor: d.color,
      backgroundColor: d.color + '22',
      pointBackgroundColor: d.color,
      pointRadius: 4,
      borderWidth: 2,
    }}))
  }},
  options: {{
    responsive: true,
    plugins: {{ legend: {{ labels: {{ color:'#c9d1d9', font:{{size:11}} }} }} }},
    scales: {{
      r: {{
        min: 0, max: 100,
        ticks: {{ display: false }},
        grid: {{ color: GRID }},
        pointLabels: {{ color:'#8b949e', font:{{size:11}} }},
        angleLines: {{ color: GRID }},
      }}
    }}
  }}
}});

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
