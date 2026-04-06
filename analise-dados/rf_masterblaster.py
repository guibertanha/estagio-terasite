import os
import re
import numpy as np
import pandas as pd
import matplotlib.pyplot as plt

# =========================================================
# CONFIGURACAO
# =========================================================

FASE1_DIR = r"C:\Terasite\Antenas\Logs RSSI fase 1"
FASE2_DIR = r"C:\Terasite\Antenas\Logs RSSI fase 2"
OUTPUT_DIR = r"C:\Terasite\Antenas\Relatorio_Daily"

os.makedirs(OUTPUT_DIR, exist_ok=True)

# Se A2 for uma antena real, mude para True
INCLUIR_A2 = False

# Fase 1: mapeamento manual
FASE1_FILE_MAP = {
    "A0_CASE1": {"antena": "A0", "unidade": "U1", "fase": "Fase 1", "cenario": "CASE", "teste": "T1"},
    "A0_R1":    {"antena": "A0", "unidade": "U1", "fase": "Fase 1", "cenario": "BASE", "teste": "T1"},

    "A1_CASE1": {"antena": "A1", "unidade": "U1", "fase": "Fase 1", "cenario": "CASE", "teste": "T1"},
    "A1_R1":    {"antena": "A1", "unidade": "U1", "fase": "Fase 1", "cenario": "BASE", "teste": "T1"},
    "A1_R2":    {"antena": "A1", "unidade": "U2", "fase": "Fase 1", "cenario": "BASE", "teste": "T1"},
    "A1_R3":    {"antena": "A1", "unidade": "U3", "fase": "Fase 1", "cenario": "BASE", "teste": "T1"},

    "A2_R1":    {"antena": "A2", "unidade": "U1", "fase": "Fase 1", "cenario": "BASE", "teste": "T1"},
    "A2_R2":    {"antena": "A2", "unidade": "U2", "fase": "Fase 1", "cenario": "BASE", "teste": "T1"},
    "A2_R3":    {"antena": "A2", "unidade": "U3", "fase": "Fase 1", "cenario": "BASE", "teste": "T1"},

    "A3_CASE1": {"antena": "A3", "unidade": "U1", "fase": "Fase 1", "cenario": "CASE", "teste": "T1"},
    "A3_R1":    {"antena": "A3", "unidade": "U1", "fase": "Fase 1", "cenario": "BASE", "teste": "T1"},
    "A3_R2":    {"antena": "A3", "unidade": "U2", "fase": "Fase 1", "cenario": "BASE", "teste": "T1"},
    "A3_R3":    {"antena": "A3", "unidade": "U3", "fase": "Fase 1", "cenario": "BASE", "teste": "T1"},

    "A4_CASE1":         {"antena": "A4", "unidade": "U1", "fase": "Fase 1", "cenario": "CASE", "teste": "T1"},
    "A4_CASE2":         {"antena": "A4", "unidade": "U2", "fase": "Fase 1", "cenario": "CASE", "teste": "T1"},
    "A4_CASE3_antDif":  {"antena": "A4", "unidade": "U2", "fase": "Fase 1", "cenario": "CASE_ALT", "teste": "T2"},
    "A4_R1":            {"antena": "A4", "unidade": "U1", "fase": "Fase 1", "cenario": "BASE", "teste": "T1"},
    "A4_R2":            {"antena": "A4", "unidade": "U2", "fase": "Fase 1", "cenario": "BASE", "teste": "T1"},
    "A4_R3":            {"antena": "A4", "unidade": "U3", "fase": "Fase 1", "cenario": "BASE", "teste": "T1"},
}

# Fase 2: nomes tipo A4_U1_T1, A5_U3_T2...
FASE2_REGEX = re.compile(r"^(A\d+)_U(\d+)_T(\d+)$", re.IGNORECASE)

DISCONNECT_TAGS = ("DISCONNECTED", "NO_WIFI", "START_FAIL")

# =========================================================
# UTILIDADES
# =========================================================

def resolve_existing_file(directory, basename):
    candidates = [
        os.path.join(directory, basename),
        os.path.join(directory, basename + ".txt"),
        os.path.join(directory, basename + ".csv"),
    ]
    for path in candidates:
        if os.path.exists(path):
            return path
    return None

def should_include_antenna(antenna):
    if antenna == "A2" and not INCLUIR_A2:
        return False
    return True

def extract_rssi_samples(filepath):
    samples = []
    disconnects = 0
    total_lines = 0
    channels = []
    bssids = set()

    with open(filepath, "r", encoding="utf-8", errors="ignore") as f:
        for line in f:
            total_lines += 1
            line = line.strip()

            if any(tag in line for tag in DISCONNECT_TAGS):
                disconnects += 1

            m_rssi = re.search(r"RSSI=(-?\d+)", line)
            if m_rssi:
                samples.append(int(m_rssi.group(1)))

            m_ch = re.search(r"CHANNEL=([0-9]+)", line)
            if m_ch:
                channels.append(int(m_ch.group(1)))

            m_bssid = re.search(r"BSSID=([0-9A-Fa-f:]+)", line)
            if m_bssid:
                bssids.add(m_bssid.group(1).upper())

    return {
        "samples": samples,
        "disconnects": disconnects,
        "total_lines": total_lines,
        "channels": channels,
        "bssids": sorted(list(bssids))
    }

def summarize_samples(samples):
    if len(samples) == 0:
        return {
            "n": 0,
            "mean": np.nan,
            "std": np.nan,
            "min": np.nan,
            "max": np.nan,
            "median": np.nan,
            "p10": np.nan,
            "p90": np.nan
        }

    arr = np.array(samples, dtype=float)
    return {
        "n": len(arr),
        "mean": float(np.mean(arr)),
        "std": float(np.std(arr, ddof=1)) if len(arr) > 1 else 0.0,
        "min": float(np.min(arr)),
        "max": float(np.max(arr)),
        "median": float(np.median(arr)),
        "p10": float(np.percentile(arr, 10)),
        "p90": float(np.percentile(arr, 90))
    }

def run_label(row):
    return f"{row['antena']}_{row['unidade']}_{row['cenario']}_{row['teste']}"

# =========================================================
# CARGA DA FASE 1
# =========================================================

def load_fase1():
    rows = []
    raw_rows = []

    for basename, meta in FASE1_FILE_MAP.items():
        if not should_include_antenna(meta["antena"]):
            continue

        filepath = resolve_existing_file(FASE1_DIR, basename)
        if filepath is None:
            continue

        parsed = extract_rssi_samples(filepath)
        stats = summarize_samples(parsed["samples"])

        row = {
            "arquivo": os.path.basename(filepath),
            "basename": basename,
            "fase": meta["fase"],
            "antena": meta["antena"],
            "unidade": meta["unidade"],
            "cenario": meta["cenario"],
            "teste": meta["teste"],
            "disconnects": parsed["disconnects"],
            "total_lines": parsed["total_lines"],
            "canal_medio": float(np.mean(parsed["channels"])) if parsed["channels"] else np.nan,
            "bssids": "; ".join(parsed["bssids"]),
            **stats
        }
        rows.append(row)

        for i, sample in enumerate(parsed["samples"], start=1):
            raw_rows.append({
                "fase": meta["fase"],
                "antena": meta["antena"],
                "unidade": meta["unidade"],
                "cenario": meta["cenario"],
                "teste": meta["teste"],
                "arquivo": os.path.basename(filepath),
                "sample_idx": i,
                "rssi": sample
            })

    return pd.DataFrame(rows), pd.DataFrame(raw_rows)

# =========================================================
# CARGA DA FASE 2
# =========================================================

def load_fase2():
    rows = []
    raw_rows = []

    for fname in os.listdir(FASE2_DIR):
        filepath = os.path.join(FASE2_DIR, fname)
        if not os.path.isfile(filepath):
            continue

        base = os.path.splitext(fname)[0]
        m = FASE2_REGEX.match(base)
        if not m:
            continue

        antenna = m.group(1).upper()
        if not should_include_antenna(antenna):
            continue

        unidade = f"U{m.group(2)}"
        teste = f"T{m.group(3)}"

        parsed = extract_rssi_samples(filepath)
        stats = summarize_samples(parsed["samples"])

        row = {
            "arquivo": fname,
            "basename": base,
            "fase": "Fase 2",
            "antena": antenna,
            "unidade": unidade,
            "cenario": "CASE",
            "teste": teste,
            "disconnects": parsed["disconnects"],
            "total_lines": parsed["total_lines"],
            "canal_medio": float(np.mean(parsed["channels"])) if parsed["channels"] else np.nan,
            "bssids": "; ".join(parsed["bssids"]),
            **stats
        }
        rows.append(row)

        for i, sample in enumerate(parsed["samples"], start=1):
            raw_rows.append({
                "fase": "Fase 2",
                "antena": antenna,
                "unidade": unidade,
                "cenario": "CASE",
                "teste": teste,
                "arquivo": fname,
                "sample_idx": i,
                "rssi": sample
            })

    return pd.DataFrame(rows), pd.DataFrame(raw_rows)

# =========================================================
# ANALISES
# =========================================================

def build_summary_by_run(df_runs):
    if df_runs.empty:
        return df_runs
    df = df_runs.copy()
    df["label"] = df.apply(run_label, axis=1)
    return df.sort_values(["antena", "unidade", "cenario", "teste", "fase"])

def build_summary_by_antenna(df_runs):
    if df_runs.empty:
        return pd.DataFrame()

    summary = (
        df_runs
        .groupby(["antena", "cenario"], dropna=False)
        .agg(
            ensaios=("arquivo", "count"),
            media_rssi=("mean", "mean"),
            std_entre_ensaios=("mean", "std"),
            melhor_ensaio=("mean", "max"),
            pior_ensaio=("mean", "min"),
            media_std_interna=("std", "mean"),
            media_disconnects=("disconnects", "mean"),
            amostras_totais=("n", "sum")
        )
        .reset_index()
    )

    summary["ranking"] = summary["media_rssi"].rank(ascending=False, method="dense")
    return summary.sort_values(["cenario", "media_rssi"], ascending=[True, False])

def build_case_vs_base(df_runs):
    if df_runs.empty:
        return pd.DataFrame()

    base = (
        df_runs[df_runs["cenario"] == "BASE"]
        .groupby("antena")
        .agg(base_media=("mean", "mean"))
        .reset_index()
    )

    case = (
        df_runs[df_runs["cenario"] == "CASE"]
        .groupby("antena")
        .agg(case_media=("mean", "mean"))
        .reset_index()
    )

    merged = pd.merge(base, case, on="antena", how="inner")
    merged["perda_case_db"] = merged["base_media"] - merged["case_media"]
    return merged.sort_values("perda_case_db", ascending=True)

def build_case_family_ranking(df_runs):
    case_runs = df_runs[df_runs["cenario"] == "CASE"].copy()
    if case_runs.empty:
        return pd.DataFrame()

    family = (
        case_runs
        .groupby("antena")
        .agg(
            ensaios=("arquivo", "count"),
            media_case=("mean", "mean"),
            std_entre_ensaios=("mean", "std"),
            melhor_case=("mean", "max"),
            pior_case=("mean", "min"),
            disconnects_medios=("disconnects", "mean")
        )
        .reset_index()
        .sort_values("media_case", ascending=False)
    )
    family["ranking_case"] = np.arange(1, len(family) + 1)
    return family

# =========================================================
# GRAFICOS
# =========================================================

def save_plot_runs(df_runs):
    if df_runs.empty:
        return

    df = build_summary_by_run(df_runs)

    plt.figure(figsize=(18, 8))
    plt.bar(df["label"], df["mean"], yerr=df["std"], capsize=4)
    plt.xticks(rotation=75, ha="right")
    plt.ylabel("RSSI médio (dBm)")
    plt.title("RSSI médio por ensaio")
    plt.grid(axis="y", linestyle="--", alpha=0.4)
    plt.tight_layout()
    plt.savefig(os.path.join(OUTPUT_DIR, "01_rssi_medio_por_ensaio.png"), dpi=300, bbox_inches="tight")
    plt.close()

def save_plot_case_ranking(df_case_family):
    if df_case_family.empty:
        return

    plt.figure(figsize=(10, 6))
    plt.bar(df_case_family["antena"], df_case_family["media_case"], yerr=df_case_family["std_entre_ensaios"], capsize=5)
    plt.ylabel("RSSI médio em CASE (dBm)")
    plt.title("Ranking consolidado das antenas em CASE")
    plt.grid(axis="y", linestyle="--", alpha=0.4)
    plt.tight_layout()
    plt.savefig(os.path.join(OUTPUT_DIR, "02_ranking_consolidado_case.png"), dpi=300, bbox_inches="tight")
    plt.close()

def save_plot_case_vs_base(df_case_base):
    if df_case_base.empty:
        return

    plt.figure(figsize=(10, 6))
    plt.bar(df_case_base["antena"], df_case_base["perda_case_db"])
    plt.ylabel("Perda In-Case (dB)")
    plt.title("Perda média de desempenho: BASE vs CASE")
    plt.grid(axis="y", linestyle="--", alpha=0.4)
    plt.tight_layout()
    plt.savefig(os.path.join(OUTPUT_DIR, "03_perda_in_case.png"), dpi=300, bbox_inches="tight")
    plt.close()

def save_plot_boxplot(df_raw):
    if df_raw.empty:
        return

    case_raw = df_raw[df_raw["cenario"] == "CASE"].copy()
    if case_raw.empty:
        return

    antenna_order = (
        case_raw.groupby("antena")["rssi"]
        .mean()
        .sort_values(ascending=False)
        .index
        .tolist()
    )

    data = [case_raw[case_raw["antena"] == ant]["rssi"].values for ant in antenna_order]

    plt.figure(figsize=(12, 7))
    plt.boxplot(data, labels=antenna_order, showmeans=True)
    plt.ylabel("RSSI (dBm)")
    plt.title("Distribuição de RSSI em CASE por família de antena")
    plt.grid(axis="y", linestyle="--", alpha=0.4)
    plt.tight_layout()
    plt.savefig(os.path.join(OUTPUT_DIR, "04_boxplot_case.png"), dpi=300, bbox_inches="tight")
    plt.close()

# =========================================================
# RELATORIO TEXTO
# =========================================================

def write_text_report(df_case_family, df_case_base, df_runs):
    report_path = os.path.join(OUTPUT_DIR, "Resumo_Executivo.txt")

    with open(report_path, "w", encoding="utf-8") as f:
        f.write("RESUMO EXECUTIVO - COMPARATIVO DE ANTENAS WIFI\n")
        f.write("=" * 60 + "\n\n")

        f.write("1. Ranking consolidado em CASE\n")
        f.write("-" * 60 + "\n")
        if df_case_family.empty:
            f.write("Sem dados.\n\n")
        else:
            for _, row in df_case_family.iterrows():
                f.write(
                    f"{int(row['ranking_case'])}. {row['antena']} | "
                    f"RSSI medio CASE = {row['media_case']:.2f} dBm | "
                    f"Ensaios = {int(row['ensaios'])} | "
                    f"Std entre ensaios = {0 if pd.isna(row['std_entre_ensaios']) else row['std_entre_ensaios']:.2f}\n"
                )
            f.write("\n")

        f.write("2. Perda BASE vs CASE\n")
        f.write("-" * 60 + "\n")
        if df_case_base.empty:
            f.write("Sem dados de BASE e CASE suficientes.\n\n")
        else:
            for _, row in df_case_base.iterrows():
                f.write(
                    f"{row['antena']} | BASE = {row['base_media']:.2f} dBm | "
                    f"CASE = {row['case_media']:.2f} dBm | "
                    f"Perda = {row['perda_case_db']:.2f} dB\n"
                )
            f.write("\n")

        f.write("3. Observacoes automaticas\n")
        f.write("-" * 60 + "\n")
        if not df_case_family.empty:
            best = df_case_family.iloc[0]
            worst = df_case_family.iloc[-1]

            f.write(
                f"Melhor familia em CASE: {best['antena']} "
                f"com RSSI medio de {best['media_case']:.2f} dBm.\n"
            )
            f.write(
                f"Pior familia em CASE: {worst['antena']} "
                f"com RSSI medio de {worst['media_case']:.2f} dBm.\n"
            )

        # Destacar A4 e A5 se existirem
        case_only = df_case_family.set_index("antena") if not df_case_family.empty else pd.DataFrame()
        if isinstance(case_only, pd.DataFrame) and "A4" in case_only.index and "A5" in case_only.index:
            a4 = case_only.loc["A4", "media_case"]
            a5 = case_only.loc["A5", "media_case"]
            delta = a5 - a4
            if delta > 0:
                f.write(f"A5 superou A4 em CASE por {delta:.2f} dB na media consolidada.\n")
            else:
                f.write(f"A4 superou A5 em CASE por {abs(delta):.2f} dB na media consolidada.\n")

        f.write("\n4. Ensaios carregados\n")
        f.write("-" * 60 + "\n")
        if df_runs.empty:
            f.write("Nenhum ensaio carregado.\n")
        else:
            f.write(f"Total de ensaios analisados: {len(df_runs)}\n")
            f.write(f"Total de familias de antena: {df_runs['antena'].nunique()}\n")
            f.write(f"Fases presentes: {', '.join(sorted(df_runs['fase'].dropna().unique()))}\n")

# =========================================================
# MAIN
# =========================================================

def main():
    print("=" * 70)
    print("ANALISE CONSOLIDADA DE ANTENAS WIFI - FASE 1 + FASE 2")
    print("=" * 70)

    df_f1_runs, df_f1_raw = load_fase1()
    df_f2_runs, df_f2_raw = load_fase2()

    df_runs = pd.concat([df_f1_runs, df_f2_runs], ignore_index=True)
    df_raw = pd.concat([df_f1_raw, df_f2_raw], ignore_index=True)

    if df_runs.empty:
        print("[ERRO] Nenhum log encontrado.")
        return

    df_summary_runs = build_summary_by_run(df_runs)
    df_summary_ant = build_summary_by_antenna(df_runs)
    df_case_base = build_case_vs_base(df_runs)
    df_case_family = build_case_family_ranking(df_runs)

    # CSVs
    df_summary_runs.to_csv(os.path.join(OUTPUT_DIR, "01_resumo_por_ensaio.csv"), index=False, encoding="utf-8-sig")
    df_summary_ant.to_csv(os.path.join(OUTPUT_DIR, "02_resumo_por_antena.csv"), index=False, encoding="utf-8-sig")
    df_case_base.to_csv(os.path.join(OUTPUT_DIR, "03_case_vs_base.csv"), index=False, encoding="utf-8-sig")
    df_raw.to_csv(os.path.join(OUTPUT_DIR, "04_amostras_brutas.csv"), index=False, encoding="utf-8-sig")

    # Graficos
    save_plot_runs(df_runs)
    save_plot_case_ranking(df_case_family)
    save_plot_case_vs_base(df_case_base)
    save_plot_boxplot(df_raw)

    # Relatorio texto
    write_text_report(df_case_family, df_case_base, df_runs)

    print(f"[OK] Relatorio salvo em: {OUTPUT_DIR}")
    print("\nTop ranking em CASE:")
    if not df_case_family.empty:
        print(df_case_family[["ranking_case", "antena", "media_case", "std_entre_ensaios", "ensaios"]].to_string(index=False))
    else:
        print("Sem dados de CASE suficientes.")

if __name__ == "__main__":
    main()
