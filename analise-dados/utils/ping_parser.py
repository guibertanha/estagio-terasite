"""
Parser canônico para logs de ping/estresse TX do ESP32 (firmware FROTALL v2).

Formato esperado:
    START_TEST,ALVO=<ip>,SSID=<ssid>,CHANNEL=<n>,BSSID=<mac>,RSSI_LINK=<dBm>
    <ms>,PING_BURST_OK,IP=<ip>,LATENCIA_MS=<ms>,CHANNEL=<n>,BSSID=<mac>,RSSI_LINK=<dBm>
    <ms>,PING_BURST_FAIL,REASON=<motivo>,...
    END_TEST,TOTAL_BURSTS=<n>,OK=<n>,FAILS=<n>,FAIL_RATE_PCT=<f>,LAT_AVG_MS=<f>,...

Quando END_TEST está ausente (log truncado), as métricas de resumo são
recalculadas a partir das linhas de burst — garantindo robustez para logs
coletados com desconexão abrupta.
"""

import re
import os
import glob
import numpy as np
import pandas as pd

# Regex para extrair antena/unidade/teste do nome do arquivo
# Aceita: Ping_A5_U1_T1.txt  |  PingOut_A4_U2_T2.txt  |  A5_U3_T3.txt
_REGEX_FILENAME = re.compile(r"(A\d+)_U(\d+)_T(\d+)", re.IGNORECASE)


# ---------------------------------------------------------------------------
# Utilitários de conversão
# ---------------------------------------------------------------------------

def safe_float(value) -> float:
    if value is None:
        return np.nan
    try:
        return float(value)
    except (ValueError, TypeError):
        return np.nan


def safe_int(value):
    if value is None:
        return np.nan
    try:
        return int(value)
    except (ValueError, TypeError):
        return np.nan


def parse_key_value_line(line: str) -> dict:
    """Extrai pares KEY=VALUE de uma linha de log (chaves em maiúsculas)."""
    return {k: v for k, v in re.findall(r"([A-Z_]+)=([^,\n]+)", line)}


def summarize_numeric(values) -> dict:
    """Estatísticas descritivas sobre uma coleção numérica (sem NaNs)."""
    s = pd.Series(values, dtype=float).dropna()
    if s.empty:
        return {k: np.nan for k in
                ("count", "mean", "std", "min", "max", "median", "p10", "p90")}
    return {
        "count":  int(s.count()),
        "mean":   float(s.mean()),
        "std":    float(s.std(ddof=1)) if s.count() > 1 else 0.0,
        "min":    float(s.min()),
        "max":    float(s.max()),
        "median": float(s.median()),
        "p10":    float(s.quantile(0.10)),
        "p90":    float(s.quantile(0.90)),
    }


# ---------------------------------------------------------------------------
# Extração de metadados do nome do arquivo
# ---------------------------------------------------------------------------

def extract_meta_from_filename(filepath: str) -> dict | None:
    """
    Extrai antena, unidade e teste do nome do arquivo.
    Retorna None se o nome não corresponder ao padrão esperado.
    """
    nome = os.path.basename(filepath)
    base = os.path.splitext(nome)[0]
    m = _REGEX_FILENAME.search(base)
    if not m:
        return None
    antena  = m.group(1).upper()
    unidade = f"U{m.group(2)}"
    teste   = f"T{m.group(3)}"
    return {
        "arquivo": nome,
        "basename": base,
        "antena": antena,
        "unidade": unidade,
        "teste": teste,
        "ensaio": f"{antena}_{unidade}_{teste}",
    }


# ---------------------------------------------------------------------------
# Parser de um único log
# ---------------------------------------------------------------------------

def parse_single_log(filepath: str) -> tuple[dict | None, list]:
    """
    Lê um arquivo de log de ping e retorna:
      summary_row  – dict com metadados + métricas do ensaio (ou None se vazio)
      burst_rows   – lista de dicts, um por burst

    Quando END_TEST está ausente, o summary_row é recalculado a partir dos
    burst_rows capturados (robustez para logs truncados).
    """
    meta = extract_meta_from_filename(filepath)
    if meta is None:
        return None, []

    burst_rows   = []
    summary_row  = None
    start_kv     = {}
    tempo_inicial_ms = None

    with open(filepath, "r", encoding="utf-8", errors="ignore") as f:
        linhas = f.readlines()

    for linha in linhas:
        linha = linha.strip()
        if not linha:
            continue

        if linha.startswith("START_TEST"):
            start_kv = parse_key_value_line(linha)
            continue

        if linha.startswith("END_TEST"):
            kv = parse_key_value_line(linha)
            summary_row = {
                **meta,
                "target_ip":          start_kv.get("ALVO"),
                "ssid":               start_kv.get("SSID"),
                "channel_start":      safe_int(start_kv.get("CHANNEL")),
                "bssid_start":        start_kv.get("BSSID"),
                "rssi_link_start":    safe_float(start_kv.get("RSSI_LINK")),
                "total_bursts":       safe_int(kv.get("TOTAL_BURSTS")),
                "ok_bursts":          safe_int(kv.get("OK")),
                "fail_bursts":        safe_int(kv.get("FAILS")),
                "fail_rate_pct_log":  safe_float(kv.get("FAIL_RATE_PCT")),
                "lat_avg_ms_log":     safe_float(kv.get("LAT_AVG_MS")),
                "lat_min_ms_log":     safe_float(kv.get("LAT_MIN_MS")),
                "lat_max_ms_log":     safe_float(kv.get("LAT_MAX_MS")),
                "channel_end":        safe_int(kv.get("CHANNEL")),
                "bssid_end":          kv.get("BSSID"),
                "rssi_link_end":      safe_float(kv.get("RSSI_LINK")),
            }
            continue

        if linha.startswith("START_FAIL"):
            kv = parse_key_value_line(linha)
            summary_row = {
                **meta,
                "target_ip": None, "ssid": None,
                "channel_start": np.nan, "bssid_start": None, "rssi_link_start": np.nan,
                "total_bursts": 0, "ok_bursts": 0, "fail_bursts": 0,
                "fail_rate_pct_log": np.nan, "lat_avg_ms_log": np.nan,
                "lat_min_ms_log": np.nan, "lat_max_ms_log": np.nan,
                "channel_end": np.nan, "bssid_end": None, "rssi_link_end": np.nan,
                "start_fail_reason": kv.get("REASON"),
            }
            continue

        if "PING_BURST_" in linha:
            m_time = re.match(r"^(\d+),", linha)
            tempo_abs_ms = safe_int(m_time.group(1)) if m_time else np.nan

            if tempo_inicial_ms is None and not pd.isna(tempo_abs_ms):
                tempo_inicial_ms = tempo_abs_ms

            tempo_rel_s = (
                (tempo_abs_ms - tempo_inicial_ms) / 1000.0
                if tempo_inicial_ms is not None and not pd.isna(tempo_abs_ms)
                else np.nan
            )

            kv     = parse_key_value_line(linha)
            status = "OK" if "PING_BURST_OK" in linha else "FAIL"

            burst_rows.append({
                **meta,
                "tempo_abs_ms":  tempo_abs_ms,
                "tempo_rel_s":   tempo_rel_s,
                "status":        status,
                "latencia_ms":   safe_float(kv.get("LATENCIA_MS")),
                "ip":            kv.get("IP"),
                "channel":       safe_int(kv.get("CHANNEL")),
                "bssid":         kv.get("BSSID"),
                "rssi_link_dbm": safe_float(kv.get("RSSI_LINK")),
                "reason":        kv.get("REASON"),
            })

    # Fallback: recalcula summary a partir dos bursts quando END_TEST está ausente
    if summary_row is None and burst_rows:
        df_b = pd.DataFrame(burst_rows)
        ok_df = df_b[df_b["status"] == "OK"]
        total  = len(df_b)
        ok_n   = int((df_b["status"] == "OK").sum())
        fail_n = int((df_b["status"] == "FAIL").sum())

        summary_row = {
            **meta,
            "target_ip": None, "ssid": None,
            "channel_start": np.nan, "bssid_start": None, "rssi_link_start": np.nan,
            "total_bursts":       total,
            "ok_bursts":          ok_n,
            "fail_bursts":        fail_n,
            "fail_rate_pct_log":  (100.0 * fail_n / total) if total > 0 else np.nan,
            "lat_avg_ms_log":     ok_df["latencia_ms"].mean() if not ok_df.empty else np.nan,
            "lat_min_ms_log":     ok_df["latencia_ms"].min()  if not ok_df.empty else np.nan,
            "lat_max_ms_log":     ok_df["latencia_ms"].max()  if not ok_df.empty else np.nan,
            "channel_end":        (ok_df["channel"].dropna().mode().iloc[0]
                                   if not ok_df.empty and not ok_df["channel"].dropna().empty
                                   else np.nan),
            "bssid_end":          (ok_df["bssid"].dropna().mode().iloc[0]
                                   if not ok_df.empty and not ok_df["bssid"].dropna().empty
                                   else None),
            "rssi_link_end":      ok_df["rssi_link_dbm"].mean() if not ok_df.empty else np.nan,
        }

    return summary_row, burst_rows


# ---------------------------------------------------------------------------
# Carga de todos os logs de um diretório
# ---------------------------------------------------------------------------

def parse_all_logs(log_dir: str) -> tuple[pd.DataFrame, pd.DataFrame]:
    """
    Lê todos os arquivos .txt em log_dir que correspondam ao padrão de nome.

    Retorna:
        df_summary  – uma linha por ensaio (métricas consolidadas)
        df_bursts   – uma linha por burst capturado
    """
    arquivos = sorted(glob.glob(os.path.join(log_dir, "*.txt")))
    print(f"[INFO] {len(arquivos)} arquivo(s) .txt encontrado(s) em {log_dir}")

    all_summaries = []
    all_bursts    = []
    ignorados     = []

    for arq in arquivos:
        if extract_meta_from_filename(arq) is None:
            ignorados.append(os.path.basename(arq))
            continue

        summary_row, burst_rows = parse_single_log(arq)

        if summary_row is not None:
            all_summaries.append(summary_row)
        if burst_rows:
            all_bursts.extend(burst_rows)

    if ignorados:
        print("[AVISO] Arquivos ignorados (nome fora do padrão):")
        for nome in ignorados:
            print(f"   - {nome}")

    return pd.DataFrame(all_summaries), pd.DataFrame(all_bursts)
