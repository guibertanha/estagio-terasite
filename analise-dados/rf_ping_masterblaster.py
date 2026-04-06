import os
import re
import glob
import math
import numpy as np
import pandas as pd
import matplotlib.pyplot as plt

# =========================================================
# CONFIGURAÇÕES
# =========================================================

LOG_DIR = r"C:\Terasite\Antenas\Logs Ping"
OUTPUT_DIR = r"C:\Terasite\Antenas\Relatorio_Engenharia_Ping"

os.makedirs(OUTPUT_DIR, exist_ok=True)

# Ex.: Ping_A5_U1_T1.txt, PingOut_A4_U2_T2.txt, A5_U3_T3.txt
REGEX_ARQUIVO = re.compile(r"(A\d+)_U(\d+)_T(\d+)", re.IGNORECASE)

# Preencha se quiser cruzar o resultado visual do SA6 depois
# Exemplo:
# SA6_VISUAL = {
#     "A4_U1_T1": {"obs": "banda forte, ligeiramente abaixo da A5"},
#     "A5_U1_T1": {"obs": "banda mais cheia e robusta"}
# }
SA6_VISUAL = {}

# =========================================================
# PARSERS
# =========================================================

def parse_key_value_line(line: str):
    """
    Extrai pares KEY=VALUE de uma linha.
    """
    kv = {}
    matches = re.findall(r"([A-Z_]+)=([^,]+)", line)
    for k, v in matches:
        kv[k] = v
    return kv


def safe_float(value):
    if value is None:
        return np.nan
    try:
        return float(value)
    except:
        return np.nan


def safe_int(value):
    if value is None:
        return np.nan
    try:
        return int(value)
    except:
        return np.nan


def summarize_numeric(series):
    s = pd.Series(series).dropna()
    if s.empty:
        return {
            "count": 0,
            "mean": np.nan,
            "std": np.nan,
            "min": np.nan,
            "max": np.nan,
            "median": np.nan,
            "p10": np.nan,
            "p90": np.nan
        }

    return {
        "count": int(s.count()),
        "mean": float(s.mean()),
        "std": float(s.std(ddof=1)) if s.count() > 1 else 0.0,
        "min": float(s.min()),
        "max": float(s.max()),
        "median": float(s.median()),
        "p10": float(s.quantile(0.10)),
        "p90": float(s.quantile(0.90))
    }


def extract_meta_from_filename(filepath):
    nome = os.path.basename(filepath)
    base = os.path.splitext(nome)[0]
    m = REGEX_ARQUIVO.search(base)
    if not m:
        return None

    antena = m.group(1).upper()
    unidade = f"U{m.group(2)}"
    teste = f"T{m.group(3)}"
    ensaio = f"{antena}_{unidade}_{teste}"

    return {
        "arquivo": nome,
        "basename": base,
        "antena": antena,
        "unidade": unidade,
        "teste": teste,
        "ensaio": ensaio
    }


def parse_single_log(filepath):
    meta = extract_meta_from_filename(filepath)
    if meta is None:
        return None, None, None

    burst_rows = []
    summary_row = None
    start_row = None

    tempo_inicial_ms = None

    with open(filepath, "r", encoding="utf-8", errors="ignore") as f:
        linhas = f.readlines()

    for linha in linhas:
        linha = linha.strip()

        if not linha:
            continue

        # START_TEST
        if linha.startswith("START_TEST"):
            kv = parse_key_value_line(linha)
            start_row = {
                **meta,
                "target_ip": kv.get("ALVO"),
                "ssid": kv.get("SSID"),
                "channel_start": safe_int(kv.get("CHANNEL")),
                "bssid_start": kv.get("BSSID"),
                "rssi_link_start": safe_float(kv.get("RSSI_LINK"))
            }
            continue

        # END_TEST
        if linha.startswith("END_TEST"):
            kv = parse_key_value_line(linha)
            summary_row = {
                **meta,
                "total_bursts": safe_int(kv.get("TOTAL_BURSTS")),
                "ok_bursts": safe_int(kv.get("OK")),
                "fail_bursts": safe_int(kv.get("FAILS")),
                "fail_rate_pct_log": safe_float(kv.get("FAIL_RATE_PCT")),
                "lat_avg_ms_log": safe_float(kv.get("LAT_AVG_MS")),
                "lat_min_ms_log": safe_float(kv.get("LAT_MIN_MS")),
                "lat_max_ms_log": safe_float(kv.get("LAT_MAX_MS")),
                "channel_end": safe_int(kv.get("CHANNEL")),
                "bssid_end": kv.get("BSSID"),
                "rssi_link_end": safe_float(kv.get("RSSI_LINK")),
                "sa6_obs": SA6_VISUAL.get(meta["ensaio"], {}).get("obs", "")
            }
            continue

        # START_FAIL
        if linha.startswith("START_FAIL"):
            kv = parse_key_value_line(linha)
            summary_row = {
                **meta,
                "total_bursts": 0,
                "ok_bursts": 0,
                "fail_bursts": 0,
                "fail_rate_pct_log": np.nan,
                "lat_avg_ms_log": np.nan,
                "lat_min_ms_log": np.nan,
                "lat_max_ms_log": np.nan,
                "channel_end": np.nan,
                "bssid_end": None,
                "rssi_link_end": np.nan,
                "start_fail_reason": kv.get("REASON"),
                "sa6_obs": SA6_VISUAL.get(meta["ensaio"], {}).get("obs", "")
            }
            continue

        # Linhas de bursts
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

            status = "OK" if "PING_BURST_OK" in linha else "FAIL"
            kv = parse_key_value_line(linha)

            burst_rows.append({
                **meta,
                "tempo_abs_ms": tempo_abs_ms,
                "tempo_rel_s": tempo_rel_s,
                "status": status,
                "latencia_ms": safe_float(kv.get("LATENCIA_MS")),
                "ip": kv.get("IP"),
                "channel": safe_int(kv.get("CHANNEL")),
                "bssid": kv.get("BSSID"),
                "rssi_link_dbm": safe_float(kv.get("RSSI_LINK")),
                "reason": kv.get("REASON")
            })

    return start_row, summary_row, burst_rows


def parse_all_logs():
    arquivos = sorted(glob.glob(os.path.join(LOG_DIR, "*.txt")))
    print(f"[INFO] {len(arquivos)} arquivos .txt encontrados em {LOG_DIR}")

    all_starts = []
    all_summaries = []
    all_bursts = []

    ignored = []

    for arq in arquivos:
        meta = extract_meta_from_filename(arq)
        if meta is None:
            ignored.append(os.path.basename(arq))
            continue

        start_row, summary_row, burst_rows = parse_single_log(arq)

        if start_row is not None:
            all_starts.append(start_row)
        if summary_row is not None:
            all_summaries.append(summary_row)
        if burst_rows:
            all_bursts.extend(burst_rows)

    if ignored:
        print("[AVISO] Arquivos ignorados por nome fora do padrão:")
        for nome in ignored:
            print("   -", nome)

    df_start = pd.DataFrame(all_starts)
    df_summary = pd.DataFrame(all_summaries)
    df_bursts = pd.DataFrame(all_bursts)

    return df_start, df_summary, df_bursts

# =========================================================
# CONSOLIDAÇÕES
# =========================================================

def build_run_level_metrics(df_summary, df_bursts):
    if df_bursts.empty and df_summary.empty:
        return pd.DataFrame()

    # Métricas derivadas dos bursts
    if not df_bursts.empty:
        ok_only = df_bursts[df_bursts["status"] == "OK"].copy()

        lat_group = ok_only.groupby("ensaio")["latencia_ms"].apply(list).reset_index(name="lat_list")
        rssi_group = ok_only.groupby("ensaio")["rssi_link_dbm"].apply(list).reset_index(name="rssi_list")

        lat_stats_rows = []
        for _, row in lat_group.iterrows():
            stats = summarize_numeric(row["lat_list"])
            lat_stats_rows.append({
                "ensaio": row["ensaio"],
                "lat_count_calc": stats["count"],
                "lat_mean_calc": stats["mean"],
                "lat_std_calc": stats["std"],
                "lat_min_calc": stats["min"],
                "lat_max_calc": stats["max"],
                "lat_median_calc": stats["median"],
                "lat_p10_calc": stats["p10"],
                "lat_p90_calc": stats["p90"]
            })

        rssi_stats_rows = []
        for _, row in rssi_group.iterrows():
            stats = summarize_numeric(row["rssi_list"])
            rssi_stats_rows.append({
                "ensaio": row["ensaio"],
                "rssi_count_calc": stats["count"],
                "rssi_mean_calc": stats["mean"],
                "rssi_std_calc": stats["std"],
                "rssi_min_calc": stats["min"],
                "rssi_max_calc": stats["max"],
                "rssi_median_calc": stats["median"],
                "rssi_p10_calc": stats["p10"],
                "rssi_p90_calc": stats["p90"]
            })

        df_lat_stats = pd.DataFrame(lat_stats_rows)
        df_rssi_stats = pd.DataFrame(rssi_stats_rows)
    else:
        df_lat_stats = pd.DataFrame(columns=["ensaio"])
        df_rssi_stats = pd.DataFrame(columns=["ensaio"])

    df = df_summary.copy()

    if not df_lat_stats.empty:
        df = df.merge(df_lat_stats, on="ensaio", how="left")
    if not df_rssi_stats.empty:
        df = df.merge(df_rssi_stats, on="ensaio", how="left")

    # Métricas de consistência de canal/BSSID por bursts
    if not df_bursts.empty:
        ch_cons = (
            df_bursts.groupby("ensaio")["channel"]
            .nunique(dropna=True)
            .reset_index(name="channels_seen")
        )
        bssid_cons = (
            df_bursts.groupby("ensaio")["bssid"]
            .nunique(dropna=True)
            .reset_index(name="bssids_seen")
        )
        df = df.merge(ch_cons, on="ensaio", how="left")
        df = df.merge(bssid_cons, on="ensaio", how="left")
    else:
        df["channels_seen"] = np.nan
        df["bssids_seen"] = np.nan

    df["fail_rate_pct_calc"] = np.where(
        df["total_bursts"] > 0,
        100.0 * df["fail_bursts"] / df["total_bursts"],
        np.nan
    )

    df["channel_consistent"] = df["channels_seen"].fillna(1) <= 1
    df["bssid_consistent"] = df["bssids_seen"].fillna(1) <= 1

    cols_order = [
        "arquivo", "basename", "antena", "unidade", "teste", "ensaio",
        "target_ip", "ssid",
        "channel_start", "channel_end", "channels_seen", "channel_consistent",
        "bssid_start", "bssid_end", "bssids_seen", "bssid_consistent",
        "rssi_link_start", "rssi_link_end",
        "total_bursts", "ok_bursts", "fail_bursts",
        "fail_rate_pct_log", "fail_rate_pct_calc",
        "lat_avg_ms_log", "lat_min_ms_log", "lat_max_ms_log",
        "lat_count_calc", "lat_mean_calc", "lat_std_calc", "lat_min_calc",
        "lat_max_calc", "lat_median_calc", "lat_p10_calc", "lat_p90_calc",
        "rssi_count_calc", "rssi_mean_calc", "rssi_std_calc", "rssi_min_calc",
        "rssi_max_calc", "rssi_median_calc", "rssi_p10_calc", "rssi_p90_calc",
        "sa6_obs"
    ]

    existing_cols = [c for c in cols_order if c in df.columns]
    remaining_cols = [c for c in df.columns if c not in existing_cols]
    return df[existing_cols + remaining_cols]


def build_unit_summary(df_runs):
    if df_runs.empty:
        return pd.DataFrame()

    grouped = (
        df_runs.groupby(["antena", "unidade"], dropna=False)
        .agg(
            ensaios=("ensaio", "count"),
            fail_rate_mean=("fail_rate_pct_calc", "mean"),
            fail_rate_std=("fail_rate_pct_calc", "std"),
            lat_mean=("lat_mean_calc", "mean"),
            lat_std_between_runs=("lat_mean_calc", "std"),
            rssi_link_mean=("rssi_mean_calc", "mean"),
            rssi_link_std_between_runs=("rssi_mean_calc", "std")
        )
        .reset_index()
        .sort_values(["antena", "unidade"])
    )
    return grouped


def build_family_summary(df_runs):
    if df_runs.empty:
        return pd.DataFrame()

    grouped = (
        df_runs.groupby(["antena"], dropna=False)
        .agg(
            ensaios=("ensaio", "count"),
            unidades=("unidade", pd.Series.nunique),
            fail_rate_mean=("fail_rate_pct_calc", "mean"),
            fail_rate_std=("fail_rate_pct_calc", "std"),
            lat_mean=("lat_mean_calc", "mean"),
            lat_std_between_runs=("lat_mean_calc", "std"),
            rssi_link_mean=("rssi_mean_calc", "mean"),
            rssi_link_std_between_runs=("rssi_mean_calc", "std")
        )
        .reset_index()
    )

    # Score simples para ranking: prioriza falha baixa e latência baixa
    grouped["score"] = (
        - grouped["fail_rate_mean"].fillna(999) * 4.0
        - grouped["lat_mean"].fillna(999) * 1.0
        + grouped["rssi_link_mean"].fillna(-999) * 0.25
    )

    grouped = grouped.sort_values(
        ["fail_rate_mean", "lat_mean", "rssi_link_mean"],
        ascending=[True, True, False]
    ).reset_index(drop=True)

    grouped["ranking"] = np.arange(1, len(grouped) + 1)
    return grouped

# =========================================================
# GRÁFICOS
# =========================================================

def color_for_antenna(ant):
    palette = {
        "A0": "#7f8c8d",
        "A4": "#2980b9",
        "A5": "#c0392b",
    }
    return palette.get(ant, "#34495e")


def save_bar_fail_rate_by_run(df_runs):
    if df_runs.empty:
        return

    df = df_runs.copy().sort_values(["antena", "unidade", "teste"])
    labels = df["ensaio"].tolist()
    values = df["fail_rate_pct_calc"].tolist()
    colors = [color_for_antenna(a) for a in df["antena"]]

    plt.figure(figsize=(14, 6))
    plt.bar(labels, values, color=colors)
    plt.xticks(rotation=65, ha="right")
    plt.ylabel("Taxa de falha (%)")
    plt.title("Taxa de falha por ensaio (menor é melhor)")
    plt.grid(axis="y", linestyle="--", alpha=0.4)
    plt.tight_layout()
    plt.savefig(os.path.join(OUTPUT_DIR, "01_taxa_falha_por_ensaio.png"), dpi=300, bbox_inches="tight")
    plt.close()


def save_bar_latency_by_run(df_runs):
    if df_runs.empty:
        return

    df = df_runs.copy().sort_values(["antena", "unidade", "teste"])
    labels = df["ensaio"].tolist()
    values = df["lat_mean_calc"].tolist()
    yerr = df["lat_std_calc"].fillna(0).tolist()
    colors = [color_for_antenna(a) for a in df["antena"]]

    plt.figure(figsize=(14, 6))
    plt.bar(labels, values, yerr=yerr, capsize=4, color=colors)
    plt.xticks(rotation=65, ha="right")
    plt.ylabel("Latência média por burst OK (ms)")
    plt.title("Latência média por ensaio (menor é melhor)")
    plt.grid(axis="y", linestyle="--", alpha=0.4)
    plt.tight_layout()
    plt.savefig(os.path.join(OUTPUT_DIR, "02_latencia_media_por_ensaio.png"), dpi=300, bbox_inches="tight")
    plt.close()


def save_boxplot_latency_by_antenna(df_bursts):
    if df_bursts.empty:
        return

    df = df_bursts[df_bursts["status"] == "OK"].copy()
    if df.empty:
        return

    antenna_order = (
        df.groupby("antena")["latencia_ms"]
        .mean()
        .sort_values(ascending=True)
        .index
        .tolist()
    )
    data = [df[df["antena"] == ant]["latencia_ms"].dropna().values for ant in antenna_order]

    plt.figure(figsize=(10, 6))
    plt.boxplot(data, labels=antenna_order, showmeans=True)
    plt.ylabel("Latência (ms)")
    plt.title("Distribuição de latência por família de antena")
    plt.grid(axis="y", linestyle="--", alpha=0.4)
    plt.tight_layout()
    plt.savefig(os.path.join(OUTPUT_DIR, "03_boxplot_latencia_por_antena.png"), dpi=300, bbox_inches="tight")
    plt.close()


def save_boxplot_rssi_by_antenna(df_bursts):
    if df_bursts.empty:
        return

    df = df_bursts[df_bursts["status"] == "OK"].copy()
    if df.empty:
        return

    antenna_order = (
        df.groupby("antena")["rssi_link_dbm"]
        .mean()
        .sort_values(ascending=False)
        .index
        .tolist()
    )
    data = [df[df["antena"] == ant]["rssi_link_dbm"].dropna().values for ant in antenna_order]

    plt.figure(figsize=(10, 6))
    plt.boxplot(data, labels=antenna_order, showmeans=True)
    plt.ylabel("RSSI do link visto pelo ESP (dBm)")
    plt.title("Distribuição do RSSI do link por família de antena")
    plt.grid(axis="y", linestyle="--", alpha=0.4)
    plt.tight_layout()
    plt.savefig(os.path.join(OUTPUT_DIR, "04_boxplot_rssi_link_por_antena.png"), dpi=300, bbox_inches="tight")
    plt.close()


def save_family_ranking(df_family):
    if df_family.empty:
        return

    df = df_family.copy().sort_values(
        ["fail_rate_mean", "lat_mean", "rssi_link_mean"],
        ascending=[True, True, False]
    )

    labels = df["antena"].tolist()
    fail_vals = df["fail_rate_mean"].tolist()
    lat_vals = df["lat_mean"].tolist()
    rssi_vals = df["rssi_link_mean"].tolist()

    fig, axes = plt.subplots(1, 3, figsize=(15, 5))

    axes[0].bar(labels, fail_vals, color=[color_for_antenna(a) for a in labels])
    axes[0].set_title("Falha média (%)")
    axes[0].set_ylabel("Menor é melhor")
    axes[0].grid(axis="y", linestyle="--", alpha=0.4)

    axes[1].bar(labels, lat_vals, color=[color_for_antenna(a) for a in labels])
    axes[1].set_title("Latência média (ms)")
    axes[1].set_ylabel("Menor é melhor")
    axes[1].grid(axis="y", linestyle="--", alpha=0.4)

    axes[2].bar(labels, rssi_vals, color=[color_for_antenna(a) for a in labels])
    axes[2].set_title("RSSI médio do link (dBm)")
    axes[2].set_ylabel("Maior é melhor")
    axes[2].grid(axis="y", linestyle="--", alpha=0.4)

    fig.suptitle("Resumo consolidado por família de antena", fontsize=15, fontweight="bold")
    plt.tight_layout()
    plt.savefig(os.path.join(OUTPUT_DIR, "05_ranking_consolidado_familias.png"), dpi=300, bbox_inches="tight")
    plt.close()


def save_timeline_by_run(df_bursts):
    if df_bursts.empty:
        return

    df = df_bursts[df_bursts["status"] == "OK"].copy()
    if df.empty:
        return

    ensaios = sorted(df["ensaio"].unique())
    n = len(ensaios)
    cols = 2
    rows = math.ceil(n / cols)

    fig, axes = plt.subplots(rows, cols, figsize=(14, 4 * rows), squeeze=False)

    for ax, ensaio in zip(axes.flat, ensaios):
        sub = df[df["ensaio"] == ensaio].copy().sort_values("tempo_rel_s")
        ant = sub["antena"].iloc[0]
        ax.plot(sub["tempo_rel_s"], sub["rssi_link_dbm"], linewidth=1.5, color=color_for_antenna(ant))
        ax.set_title(ensaio)
        ax.set_xlabel("Tempo relativo (s)")
        ax.set_ylabel("RSSI link (dBm)")
        ax.grid(True, linestyle="--", alpha=0.35)

    for ax in axes.flat[n:]:
        ax.axis("off")

    fig.suptitle("Timeline de RSSI do link por ensaio", fontsize=15, fontweight="bold")
    plt.tight_layout()
    plt.savefig(os.path.join(OUTPUT_DIR, "06_timeline_rssi_por_ensaio.png"), dpi=300, bbox_inches="tight")
    plt.close()

# =========================================================
# RELATÓRIO TXT
# =========================================================

def write_executive_report(df_runs, df_unit, df_family):
    path = os.path.join(OUTPUT_DIR, "Resumo_Executivo_Ping.txt")

    with open(path, "w", encoding="utf-8") as f:
        f.write("RELATÓRIO COMPLEMENTAR - ENSAIO DE PING / ESTRESSE TX\n")
        f.write("=" * 70 + "\n\n")

        f.write("1. ESCOPO\n")
        f.write("-" * 70 + "\n")
        f.write("Este relatório resume os ensaios de tráfego por ping em rajadas.\n")
        f.write("O objetivo é avaliar estabilidade lógica do enlace sob estresse,\n")
        f.write("como complemento aos testes de RSSI e à observação visual no SA6.\n\n")

        f.write("2. OBSERVAÇÃO METODOLÓGICA\n")
        f.write("-" * 70 + "\n")
        f.write("Latência e falha de bursts são métricas complementares. Elas não\n")
        f.write("substituem a medição RF física, mas ajudam a validar robustez do\n")
        f.write("link. O campo RSSI_LINK representa o RSSI do AP visto pelo ESP32,\n")
        f.write("e não uma medição reportada pelo gateway.\n\n")

        f.write("3. RANKING CONSOLIDADO POR FAMÍLIA\n")
        f.write("-" * 70 + "\n")
        if df_family.empty:
            f.write("Sem dados suficientes.\n\n")
        else:
            for _, row in df_family.iterrows():
                fail_std = 0.0 if pd.isna(row["fail_rate_std"]) else row["fail_rate_std"]
                lat_std = 0.0 if pd.isna(row["lat_std_between_runs"]) else row["lat_std_between_runs"]
                rssi_std = 0.0 if pd.isna(row["rssi_link_std_between_runs"]) else row["rssi_link_std_between_runs"]

                f.write(
                    f"{int(row['ranking'])}. {row['antena']} | "
                    f"Ensaios={int(row['ensaios'])} | "
                    f"Unidades={int(row['unidades'])} | "
                    f"Falha média={row['fail_rate_mean']:.2f}% (std {fail_std:.2f}) | "
                    f"Latência média={row['lat_mean']:.2f} ms (std {lat_std:.2f}) | "
                    f"RSSI link médio={row['rssi_link_mean']:.2f} dBm (std {rssi_std:.2f})\n"
                )
            f.write("\n")

        f.write("4. RESUMO POR UNIDADE\n")
        f.write("-" * 70 + "\n")
        if df_unit.empty:
            f.write("Sem dados suficientes.\n\n")
        else:
            for _, row in df_unit.iterrows():
                fail_std = 0.0 if pd.isna(row["fail_rate_std"]) else row["fail_rate_std"]
                lat_std = 0.0 if pd.isna(row["lat_std_between_runs"]) else row["lat_std_between_runs"]
                rssi_std = 0.0 if pd.isna(row["rssi_link_std_between_runs"]) else row["rssi_link_std_between_runs"]

                f.write(
                    f"{row['antena']}_{row['unidade']} | "
                    f"Ensaios={int(row['ensaios'])} | "
                    f"Falha média={row['fail_rate_mean']:.2f}% (std {fail_std:.2f}) | "
                    f"Latência média={row['lat_mean']:.2f} ms (std {lat_std:.2f}) | "
                    f"RSSI link médio={row['rssi_link_mean']:.2f} dBm (std {rssi_std:.2f})\n"
                )
            f.write("\n")

        f.write("5. ALERTAS DE CONSISTÊNCIA\n")
        f.write("-" * 70 + "\n")
        if df_runs.empty:
            f.write("Sem dados.\n\n")
        else:
            inconsist_ch = df_runs[~df_runs["channel_consistent"]]
            inconsist_bssid = df_runs[~df_runs["bssid_consistent"]]

            if inconsist_ch.empty and inconsist_bssid.empty:
                f.write("Todos os ensaios mantiveram consistência de canal e BSSID.\n\n")
            else:
                if not inconsist_ch.empty:
                    f.write("Ensaios com mais de um canal observado:\n")
                    for e in inconsist_ch["ensaio"].tolist():
                        f.write(f" - {e}\n")
                if not inconsist_bssid.empty:
                    f.write("Ensaios com mais de um BSSID observado:\n")
                    for e in inconsist_bssid["ensaio"].tolist():
                        f.write(f" - {e}\n")
                f.write("\n")

        f.write("6. VEREDITO DE ENGENHARIA\n")
        f.write("-" * 70 + "\n")
        if not df_family.empty:
            best = df_family.iloc[0]
            f.write(
                f"A família líder neste ensaio complementar foi {best['antena']}, "
                f"com taxa média de falha de {best['fail_rate_mean']:.2f}%, "
                f"latência média de {best['lat_mean']:.2f} ms e RSSI_LINK médio "
                f"de {best['rssi_link_mean']:.2f} dBm.\n"
            )
            f.write(
                "A decisão final deve cruzar esse resultado com os ensaios de RSSI\n"
                "in-case e com a observação visual do envelope de RF no SA6.\n"
            )
        else:
            f.write("Sem dados suficientes para conclusão.\n")

# =========================================================
# MAIN
# =========================================================

def main():
    print("=" * 72)
    print("ANÁLISE DE LOGS DE PING / ESTRESSE TX")
    print("=" * 72)

    df_start, df_summary, df_bursts = parse_all_logs()

    if df_summary.empty:
        print("[ERRO] Nenhum END_TEST válido encontrado.")
        print("Verifique os nomes dos arquivos, ex.: Ping_A4_U1_T1.txt")
        return

    df_runs = build_run_level_metrics(df_summary, df_bursts)
    df_unit = build_unit_summary(df_runs)
    df_family = build_family_summary(df_runs)

    # CSVs
    df_start.to_csv(os.path.join(OUTPUT_DIR, "01_start_tests.csv"), index=False, encoding="utf-8-sig")
    df_summary.to_csv(os.path.join(OUTPUT_DIR, "02_end_tests_bruto.csv"), index=False, encoding="utf-8-sig")
    df_bursts.to_csv(os.path.join(OUTPUT_DIR, "03_bursts_bruto.csv"), index=False, encoding="utf-8-sig")
    df_runs.to_csv(os.path.join(OUTPUT_DIR, "04_resumo_por_ensaio.csv"), index=False, encoding="utf-8-sig")
    df_unit.to_csv(os.path.join(OUTPUT_DIR, "05_resumo_por_unidade.csv"), index=False, encoding="utf-8-sig")
    df_family.to_csv(os.path.join(OUTPUT_DIR, "06_resumo_por_familia.csv"), index=False, encoding="utf-8-sig")

    # Gráficos
    save_bar_fail_rate_by_run(df_runs)
    save_bar_latency_by_run(df_runs)
    save_boxplot_latency_by_antenna(df_bursts)
    save_boxplot_rssi_by_antenna(df_bursts)
    save_family_ranking(df_family)
    save_timeline_by_run(df_bursts)

    # TXT
    write_executive_report(df_runs, df_unit, df_family)

    print(f"[OK] Saída gerada em: {OUTPUT_DIR}\n")

    print("Ranking consolidado:")
    if not df_family.empty:
        print(df_family[[
            "ranking", "antena", "ensaios", "unidades",
            "fail_rate_mean", "lat_mean", "rssi_link_mean"
        ]].to_string(index=False))
    else:
        print("Sem dados.")

if __name__ == "__main__":
    main()
