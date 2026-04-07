import os
import math
import numpy as np
import pandas as pd
import matplotlib.pyplot as plt

from config import PING_DIR, OUTPUT_PING as OUTPUT_DIR
from utils.ping_parser import parse_all_logs, summarize_numeric

# =========================================================
# CONFIGURAÇÕES
# =========================================================

os.makedirs(OUTPUT_DIR, exist_ok=True)

# =========================================================
# CONSOLIDAÇÕES
# =========================================================

def _p10(s): return s.quantile(0.10)
def _p90(s): return s.quantile(0.90)


def build_run_level_metrics(df_summary: pd.DataFrame,
                             df_bursts: pd.DataFrame) -> pd.DataFrame:
    """
    Enriquece df_summary com estatísticas calculadas diretamente dos bursts:
    latência (OK only), RSSI do link (OK only), consistência de canal/BSSID.
    """
    if df_summary.empty:
        return pd.DataFrame()

    df = df_summary.copy()

    if not df_bursts.empty:
        ok = df_bursts[df_bursts["status"] == "OK"].copy()

        # Estatísticas de latência por ensaio
        lat_stats = (
            ok.groupby("ensaio")["latencia_ms"]
            .agg(
                lat_count_calc="count",
                lat_mean_calc="mean",
                lat_std_calc="std",
                lat_min_calc="min",
                lat_max_calc="max",
                lat_median_calc="median",
                lat_p10_calc=_p10,
                lat_p90_calc=_p90,
            )
            .reset_index()
        )

        # Estatísticas de RSSI do link por ensaio
        rssi_stats = (
            ok.groupby("ensaio")["rssi_link_dbm"]
            .agg(
                rssi_count_calc="count",
                rssi_mean_calc="mean",
                rssi_std_calc="std",
                rssi_min_calc="min",
                rssi_max_calc="max",
                rssi_median_calc="median",
                rssi_p10_calc=_p10,
                rssi_p90_calc=_p90,
            )
            .reset_index()
        )

        # Consistência de canal e BSSID
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

        df = (df
              .merge(lat_stats,   on="ensaio", how="left")
              .merge(rssi_stats,  on="ensaio", how="left")
              .merge(ch_cons,     on="ensaio", how="left")
              .merge(bssid_cons,  on="ensaio", how="left"))
    else:
        for col in ("lat_count_calc", "lat_mean_calc", "lat_std_calc",
                    "lat_min_calc", "lat_max_calc", "lat_median_calc",
                    "lat_p10_calc", "lat_p90_calc",
                    "rssi_count_calc", "rssi_mean_calc", "rssi_std_calc",
                    "rssi_min_calc", "rssi_max_calc", "rssi_median_calc",
                    "rssi_p10_calc", "rssi_p90_calc",
                    "channels_seen", "bssids_seen"):
            df[col] = np.nan

    df["fail_rate_pct_calc"] = np.where(
        df["total_bursts"] > 0,
        100.0 * df["fail_bursts"] / df["total_bursts"],
        np.nan,
    )
    df["channel_consistent"] = df["channels_seen"].fillna(1) <= 1
    df["bssid_consistent"]   = df["bssids_seen"].fillna(1) <= 1

    cols_order = [
        "arquivo", "basename", "antena", "unidade", "teste", "ensaio",
        "target_ip", "ssid",
        "channel_start", "channel_end", "channels_seen", "channel_consistent",
        "bssid_start", "bssid_end", "bssids_seen", "bssid_consistent",
        "rssi_link_start", "rssi_link_end",
        "total_bursts", "ok_bursts", "fail_bursts",
        "fail_rate_pct_log", "fail_rate_pct_calc",
        "lat_avg_ms_log", "lat_min_ms_log", "lat_max_ms_log",
        "lat_count_calc", "lat_mean_calc", "lat_std_calc",
        "lat_min_calc", "lat_max_calc", "lat_median_calc",
        "lat_p10_calc", "lat_p90_calc",
        "rssi_count_calc", "rssi_mean_calc", "rssi_std_calc",
        "rssi_min_calc", "rssi_max_calc", "rssi_median_calc",
        "rssi_p10_calc", "rssi_p90_calc",
    ]
    existing  = [c for c in cols_order if c in df.columns]
    remaining = [c for c in df.columns if c not in existing]
    return df[existing + remaining]


def build_unit_summary(df_runs: pd.DataFrame) -> pd.DataFrame:
    if df_runs.empty:
        return pd.DataFrame()

    return (
        df_runs.groupby(["antena", "unidade"], dropna=False)
        .agg(
            ensaios=("ensaio", "count"),
            fail_rate_mean=("fail_rate_pct_calc", "mean"),
            fail_rate_std=("fail_rate_pct_calc", "std"),
            lat_mean=("lat_mean_calc", "mean"),
            lat_std_between_runs=("lat_mean_calc", "std"),
            rssi_link_mean=("rssi_mean_calc", "mean"),
            rssi_link_std_between_runs=("rssi_mean_calc", "std"),
        )
        .reset_index()
        .sort_values(["antena", "unidade"])
    )


def build_family_summary(df_runs: pd.DataFrame) -> pd.DataFrame:
    if df_runs.empty:
        return pd.DataFrame()

    grouped = (
        df_runs.groupby("antena", dropna=False)
        .agg(
            ensaios=("ensaio", "count"),
            unidades=("unidade", pd.Series.nunique),
            fail_rate_mean=("fail_rate_pct_calc", "mean"),
            fail_rate_std=("fail_rate_pct_calc", "std"),
            lat_mean=("lat_mean_calc", "mean"),
            lat_std_between_runs=("lat_mean_calc", "std"),
            rssi_link_mean=("rssi_mean_calc", "mean"),
            rssi_link_std_between_runs=("rssi_mean_calc", "std"),
        )
        .reset_index()
        .sort_values(
            ["fail_rate_mean", "lat_mean", "rssi_link_mean"],
            ascending=[True, True, False],
        )
        .reset_index(drop=True)
    )
    grouped["ranking"] = np.arange(1, len(grouped) + 1)
    return grouped


# =========================================================
# GRÁFICOS
# =========================================================

def _color(ant):
    return {"A0": "#7f8c8d", "A4": "#2980b9", "A5": "#c0392b"}.get(ant, "#34495e")


def save_bar_fail_rate_by_run(df_runs):
    if df_runs.empty:
        return

    df = df_runs.sort_values(["antena", "unidade", "teste"])
    plt.figure(figsize=(14, 6))
    plt.bar(df["ensaio"], df["fail_rate_pct_calc"],
            color=[_color(a) for a in df["antena"]])
    plt.xticks(rotation=65, ha="right")
    plt.ylabel("Taxa de falha (%)")
    plt.title("Taxa de falha por ensaio (menor é melhor)")
    plt.grid(axis="y", linestyle="--", alpha=0.4)
    plt.tight_layout()
    plt.savefig(str(OUTPUT_DIR / "01_taxa_falha_por_ensaio.png"), dpi=300, bbox_inches="tight")
    plt.close()


def save_bar_latency_by_run(df_runs):
    if df_runs.empty:
        return

    df = df_runs.sort_values(["antena", "unidade", "teste"])
    plt.figure(figsize=(14, 6))
    plt.bar(df["ensaio"], df["lat_mean_calc"],
            yerr=df["lat_std_calc"].fillna(0),
            capsize=4,
            color=[_color(a) for a in df["antena"]])
    plt.xticks(rotation=65, ha="right")
    plt.ylabel("Latência média por burst OK (ms)")
    plt.title("Latência média por ensaio (menor é melhor)")
    plt.grid(axis="y", linestyle="--", alpha=0.4)
    plt.tight_layout()
    plt.savefig(str(OUTPUT_DIR / "02_latencia_media_por_ensaio.png"), dpi=300, bbox_inches="tight")
    plt.close()


def save_boxplot_latency_by_antenna(df_bursts):
    if df_bursts.empty:
        return

    df = df_bursts[df_bursts["status"] == "OK"].copy()
    if df.empty:
        return

    antenna_order = (
        df.groupby("antena")["latencia_ms"]
        .mean().sort_values().index.tolist()
    )
    data = [df[df["antena"] == ant]["latencia_ms"].dropna().values for ant in antenna_order]

    plt.figure(figsize=(10, 6))
    plt.boxplot(data, tick_labels=antenna_order, showmeans=True)
    plt.ylabel("Latência (ms)")
    plt.title("Distribuição de latência por família de antena")
    plt.grid(axis="y", linestyle="--", alpha=0.4)
    plt.tight_layout()
    plt.savefig(str(OUTPUT_DIR / "03_boxplot_latencia_por_antena.png"), dpi=300, bbox_inches="tight")
    plt.close()


def save_boxplot_rssi_by_antenna(df_bursts):
    if df_bursts.empty:
        return

    df = df_bursts[df_bursts["status"] == "OK"].copy()
    if df.empty:
        return

    antenna_order = (
        df.groupby("antena")["rssi_link_dbm"]
        .mean().sort_values(ascending=False).index.tolist()
    )
    data = [df[df["antena"] == ant]["rssi_link_dbm"].dropna().values for ant in antenna_order]

    plt.figure(figsize=(10, 6))
    plt.boxplot(data, tick_labels=antenna_order, showmeans=True)
    plt.ylabel("RSSI do link visto pelo ESP (dBm)")
    plt.title("Distribuição do RSSI do link por família de antena")
    plt.grid(axis="y", linestyle="--", alpha=0.4)
    plt.tight_layout()
    plt.savefig(str(OUTPUT_DIR / "04_boxplot_rssi_link_por_antena.png"), dpi=300, bbox_inches="tight")
    plt.close()


def save_family_ranking(df_family):
    if df_family.empty:
        return

    df = df_family.sort_values(
        ["fail_rate_mean", "lat_mean", "rssi_link_mean"],
        ascending=[True, True, False],
    )
    labels    = df["antena"].tolist()
    fail_vals = df["fail_rate_mean"].tolist()
    lat_vals  = df["lat_mean"].tolist()
    rssi_vals = df["rssi_link_mean"].tolist()
    colors    = [_color(a) for a in labels]

    fig, axes = plt.subplots(1, 3, figsize=(15, 5))
    for ax, vals, title, ylabel in zip(
        axes,
        [fail_vals, lat_vals, rssi_vals],
        ["Falha média (%)", "Latência média (ms)", "RSSI médio do link (dBm)"],
        ["Menor é melhor", "Menor é melhor", "Maior é melhor"],
    ):
        ax.bar(labels, vals, color=colors)
        ax.set_title(title)
        ax.set_ylabel(ylabel)
        ax.grid(axis="y", linestyle="--", alpha=0.4)

    fig.suptitle("Resumo consolidado por família de antena", fontsize=15, fontweight="bold")
    plt.tight_layout()
    plt.savefig(str(OUTPUT_DIR / "05_ranking_consolidado_familias.png"), dpi=300, bbox_inches="tight")
    plt.close()


def save_timeline_by_run(df_bursts):
    if df_bursts.empty:
        return

    df = df_bursts[df_bursts["status"] == "OK"].copy()
    if df.empty:
        return

    ensaios = sorted(df["ensaio"].unique())
    n    = len(ensaios)
    cols = 2
    rows = math.ceil(n / cols)

    fig, axes = plt.subplots(rows, cols, figsize=(14, 4 * rows), squeeze=False)

    for ax, ensaio in zip(axes.flat, ensaios):
        sub = df[df["ensaio"] == ensaio].sort_values("tempo_rel_s")
        ant = sub["antena"].iloc[0]
        ax.plot(sub["tempo_rel_s"], sub["rssi_link_dbm"],
                linewidth=1.5, color=_color(ant))
        ax.set_title(ensaio)
        ax.set_xlabel("Tempo relativo (s)")
        ax.set_ylabel("RSSI link (dBm)")
        ax.grid(True, linestyle="--", alpha=0.35)

    for ax in axes.flat[n:]:
        ax.axis("off")

    fig.suptitle("Timeline de RSSI do link por ensaio", fontsize=15, fontweight="bold")
    plt.tight_layout()
    plt.savefig(str(OUTPUT_DIR / "06_timeline_rssi_por_ensaio.png"), dpi=300, bbox_inches="tight")
    plt.close()


# =========================================================
# RELATÓRIO TXT
# =========================================================

def write_executive_report(df_runs, df_unit, df_family):
    path = str(OUTPUT_DIR / "Resumo_Executivo_Ping.txt")

    with open(path, "w", encoding="utf-8") as f:
        f.write("RELATÓRIO COMPLEMENTAR - ENSAIO DE PING / ESTRESSE TX\n")
        f.write("=" * 70 + "\n\n")

        f.write("1. ESCOPO\n" + "-" * 70 + "\n")
        f.write("Este relatório resume os ensaios de tráfego por ping em rajadas.\n"
                "Objetivo: avaliar estabilidade lógica do enlace sob estresse,\n"
                "como complemento aos testes de RSSI e à observação visual no SA6.\n\n")

        f.write("2. OBSERVAÇÃO METODOLÓGICA\n" + "-" * 70 + "\n")
        f.write("Latência e falha de bursts são métricas complementares. Elas não\n"
                "substituem a medição RF física, mas ajudam a validar robustez do\n"
                "link. O campo RSSI_LINK representa o RSSI do AP visto pelo ESP32,\n"
                "e não uma medição reportada pelo gateway.\n\n")

        f.write("3. RANKING CONSOLIDADO POR FAMÍLIA\n" + "-" * 70 + "\n")
        if df_family.empty:
            f.write("Sem dados suficientes.\n\n")
        else:
            for _, row in df_family.iterrows():
                fail_std = 0.0 if pd.isna(row["fail_rate_std"]) else row["fail_rate_std"]
                lat_std  = 0.0 if pd.isna(row["lat_std_between_runs"]) else row["lat_std_between_runs"]
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

        f.write("4. RESUMO POR UNIDADE\n" + "-" * 70 + "\n")
        if df_unit.empty:
            f.write("Sem dados suficientes.\n\n")
        else:
            for _, row in df_unit.iterrows():
                fail_std = 0.0 if pd.isna(row["fail_rate_std"]) else row["fail_rate_std"]
                lat_std  = 0.0 if pd.isna(row["lat_std_between_runs"]) else row["lat_std_between_runs"]
                rssi_std = 0.0 if pd.isna(row["rssi_link_std_between_runs"]) else row["rssi_link_std_between_runs"]
                f.write(
                    f"{row['antena']}_{row['unidade']} | "
                    f"Ensaios={int(row['ensaios'])} | "
                    f"Falha média={row['fail_rate_mean']:.2f}% (std {fail_std:.2f}) | "
                    f"Latência média={row['lat_mean']:.2f} ms (std {lat_std:.2f}) | "
                    f"RSSI link médio={row['rssi_link_mean']:.2f} dBm (std {rssi_std:.2f})\n"
                )
            f.write("\n")

        f.write("5. ALERTAS DE CONSISTÊNCIA\n" + "-" * 70 + "\n")
        if df_runs.empty:
            f.write("Sem dados.\n\n")
        else:
            inconsist_ch    = df_runs[~df_runs["channel_consistent"]]
            inconsist_bssid = df_runs[~df_runs["bssid_consistent"]]
            if inconsist_ch.empty and inconsist_bssid.empty:
                f.write("Todos os ensaios mantiveram consistência de canal e BSSID.\n\n")
            else:
                if not inconsist_ch.empty:
                    f.write("Ensaios com mais de um canal observado:\n")
                    for e in inconsist_ch["ensaio"]:
                        f.write(f" - {e}\n")
                if not inconsist_bssid.empty:
                    f.write("Ensaios com mais de um BSSID observado:\n")
                    for e in inconsist_bssid["ensaio"]:
                        f.write(f" - {e}\n")
                f.write("\n")

        f.write("6. VEREDITO DE ENGENHARIA\n" + "-" * 70 + "\n")
        if not df_family.empty:
            best = df_family.iloc[0]
            f.write(
                f"A família líder neste ensaio complementar foi {best['antena']}, "
                f"com taxa média de falha de {best['fail_rate_mean']:.2f}%, "
                f"latência média de {best['lat_mean']:.2f} ms e RSSI_LINK médio "
                f"de {best['rssi_link_mean']:.2f} dBm.\n"
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

    df_summary, df_bursts = parse_all_logs(str(PING_DIR))

    if df_summary.empty:
        print("[ERRO] Nenhum END_TEST válido encontrado.")
        print("Verifique os nomes dos arquivos, ex.: Ping_A4_U1_T1.txt")
        return

    df_runs   = build_run_level_metrics(df_summary, df_bursts)
    df_unit   = build_unit_summary(df_runs)
    df_family = build_family_summary(df_runs)

    # CSVs
    df_summary.to_csv(str(OUTPUT_DIR / "01_end_tests_bruto.csv"),    index=False, encoding="utf-8-sig")
    df_bursts.to_csv( str(OUTPUT_DIR / "02_bursts_bruto.csv"),       index=False, encoding="utf-8-sig")
    df_runs.to_csv(   str(OUTPUT_DIR / "03_resumo_por_ensaio.csv"),  index=False, encoding="utf-8-sig")
    df_unit.to_csv(   str(OUTPUT_DIR / "04_resumo_por_unidade.csv"), index=False, encoding="utf-8-sig")
    df_family.to_csv( str(OUTPUT_DIR / "05_resumo_por_familia.csv"), index=False, encoding="utf-8-sig")

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
        print(df_family[["ranking", "antena", "ensaios", "unidades",
                          "fail_rate_mean", "lat_mean", "rssi_link_mean"]].to_string(index=False))
    else:
        print("Sem dados.")


if __name__ == "__main__":
    main()
