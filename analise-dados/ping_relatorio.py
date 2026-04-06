import os
import re
import glob
import numpy as np
import pandas as pd
import matplotlib.pyplot as plt

# =========================================================
# CONFIGURAÇÕES
# =========================================================

LOG_DIR = r"C:\Terasite\Antenas\Logs Ping"
OUTPUT_DIR = r"C:\Terasite\Antenas\Relatorio_Ping_Executivo"

os.makedirs(OUTPUT_DIR, exist_ok=True)

# Aceita nomes como:
# Ping_A4_U1_T1.txt
# PingOut_A5_U2_T2.txt
# A5_U3_T3.txt
REGEX_ARQUIVO = re.compile(r"(A\d+)_U(\d+)_T(\d+)", re.IGNORECASE)

# =========================================================
# FUNÇÕES AUXILIARES
# =========================================================

def safe_float(v):
    try:
        return float(v)
    except:
        return np.nan

def safe_int(v):
    try:
        return int(v)
    except:
        return np.nan

def parse_key_values(line):
    kv = {}
    for k, v in re.findall(r"([A-Z_]+)=([^,]+)", line):
        kv[k] = v
    return kv

def extract_meta(filepath):
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
        "antena": antena,
        "unidade": unidade,
        "teste": teste,
        "ensaio": ensaio
    }

# =========================================================
# LEITURA DOS LOGS
# =========================================================

def parse_logs():
    arquivos = sorted(glob.glob(os.path.join(LOG_DIR, "*.txt")))

    rows_summary = []
    rows_bursts = []
    ignorados = []

    for arq in arquivos:
        meta = extract_meta(arq)
        if meta is None:
            ignorados.append(os.path.basename(arq))
            continue

        tempo0 = None
        end_row = None

        with open(arq, "r", encoding="utf-8", errors="ignore") as f:
            for line in f:
                line = line.strip()
                if not line:
                    continue

                if line.startswith("END_TEST"):
                    kv = parse_key_values(line)
                    end_row = {
                        **meta,
                        "total_bursts": safe_int(kv.get("TOTAL_BURSTS")),
                        "ok_bursts": safe_int(kv.get("OK")),
                        "fail_bursts": safe_int(kv.get("FAILS")),
                        "fail_rate_pct": safe_float(kv.get("FAIL_RATE_PCT")),
                        "lat_avg_ms": safe_float(kv.get("LAT_AVG_MS")),
                        "lat_min_ms": safe_float(kv.get("LAT_MIN_MS")),
                        "lat_max_ms": safe_float(kv.get("LAT_MAX_MS")),
                        "channel": safe_int(kv.get("CHANNEL")),
                        "bssid": kv.get("BSSID"),
                        "rssi_link_end": safe_float(kv.get("RSSI_LINK")),
                    }

                elif "PING_BURST_" in line:
                    m_time = re.match(r"^(\d+),", line)
                    tempo_abs = safe_int(m_time.group(1)) if m_time else np.nan
                    if tempo0 is None and not pd.isna(tempo_abs):
                        tempo0 = tempo_abs
                    tempo_rel = ((tempo_abs - tempo0) / 1000.0) if tempo0 is not None and not pd.isna(tempo_abs) else np.nan

                    kv = parse_key_values(line)
                    status = "OK" if "PING_BURST_OK" in line else "FAIL"

                    rows_bursts.append({
                        **meta,
                        "tempo_s": tempo_rel,
                        "status": status,
                        "latencia_ms": safe_float(kv.get("LATENCIA_MS")),
                        "rssi_link_dbm": safe_float(kv.get("RSSI_LINK")),
                        "channel_burst": safe_int(kv.get("CHANNEL")),
                        "bssid_burst": kv.get("BSSID")
                    })

        # Se o END_TEST não existir, monta resumo básico a partir dos bursts
        if end_row is None:
            df_tmp = pd.DataFrame([r for r in rows_bursts if r["ensaio"] == meta["ensaio"]])
            ok_df = df_tmp[df_tmp["status"] == "OK"] if not df_tmp.empty else pd.DataFrame()

            total_bursts = len(df_tmp)
            ok_bursts = int((df_tmp["status"] == "OK").sum()) if not df_tmp.empty else 0
            fail_bursts = int((df_tmp["status"] == "FAIL").sum()) if not df_tmp.empty else 0
            fail_rate = (100.0 * fail_bursts / total_bursts) if total_bursts > 0 else np.nan

            end_row = {
                **meta,
                "total_bursts": total_bursts,
                "ok_bursts": ok_bursts,
                "fail_bursts": fail_bursts,
                "fail_rate_pct": fail_rate,
                "lat_avg_ms": ok_df["latencia_ms"].mean() if not ok_df.empty else np.nan,
                "lat_min_ms": ok_df["latencia_ms"].min() if not ok_df.empty else np.nan,
                "lat_max_ms": ok_df["latencia_ms"].max() if not ok_df.empty else np.nan,
                "channel": ok_df["channel_burst"].dropna().mode().iloc[0] if not ok_df.empty and not ok_df["channel_burst"].dropna().empty else np.nan,
                "bssid": ok_df["bssid_burst"].dropna().mode().iloc[0] if not ok_df.empty and not ok_df["bssid_burst"].dropna().empty else None,
                "rssi_link_end": ok_df["rssi_link_dbm"].mean() if not ok_df.empty else np.nan,
            }

        rows_summary.append(end_row)

    if ignorados:
        print("[AVISO] Arquivos ignorados:")
        for nome in ignorados:
            print(" -", nome)

    df_summary = pd.DataFrame(rows_summary)
    df_bursts = pd.DataFrame(rows_bursts)

    return df_summary, df_bursts

# =========================================================
# CONSOLIDAÇÕES
# =========================================================

def build_consolidated(df_summary, df_bursts):
    if df_summary.empty:
        return pd.DataFrame(), pd.DataFrame()

    # reforça métricas com base nos bursts OK
    if not df_bursts.empty:
        ok = df_bursts[df_bursts["status"] == "OK"].copy()

        rssi_by_run = ok.groupby("ensaio")["rssi_link_dbm"].agg(["mean", "std", "min", "max"]).reset_index()
        rssi_by_run.columns = ["ensaio", "rssi_mean_calc", "rssi_std_calc", "rssi_min_calc", "rssi_max_calc"]

        df_runs = df_summary.merge(rssi_by_run, on="ensaio", how="left")
    else:
        df_runs = df_summary.copy()
        df_runs["rssi_mean_calc"] = np.nan
        df_runs["rssi_std_calc"] = np.nan
        df_runs["rssi_min_calc"] = np.nan
        df_runs["rssi_max_calc"] = np.nan

    df_family = (
        df_runs.groupby("antena", dropna=False)
        .agg(
            ensaios=("ensaio", "count"),
            unidades=("unidade", pd.Series.nunique),
            fail_rate_mean=("fail_rate_pct", "mean"),
            fail_rate_std=("fail_rate_pct", "std"),
            lat_mean=("lat_avg_ms", "mean"),
            lat_std=("lat_avg_ms", "std"),
            rssi_link_mean=("rssi_mean_calc", "mean"),
            rssi_link_std=("rssi_mean_calc", "std"),
        )
        .reset_index()
        .sort_values(["fail_rate_mean", "lat_mean", "rssi_link_mean"], ascending=[True, True, False])
        .reset_index(drop=True)
    )

    df_family["ranking"] = np.arange(1, len(df_family) + 1)

    return df_runs, df_family

# =========================================================
# GRÁFICOS
# =========================================================

def color_for_antena(a):
    palette = {
        "A0": "#7f8c8d",
        "A4": "#2980b9",
        "A5": "#c0392b",
    }
    return palette.get(a, "#34495e")

def plot_fail_rate(df_runs):
    if df_runs.empty:
        return
    df = df_runs.sort_values(["antena", "unidade", "teste"])
    plt.figure(figsize=(12, 5))
    plt.bar(df["ensaio"], df["fail_rate_pct"], color=[color_for_antena(a) for a in df["antena"]])
    plt.xticks(rotation=65, ha="right")
    plt.ylabel("Taxa de falha (%)")
    plt.title("Falha por ensaio")
    plt.grid(axis="y", linestyle="--", alpha=0.4)
    plt.tight_layout()
    plt.savefig(os.path.join(OUTPUT_DIR, "01_falha_por_ensaio.png"), dpi=300, bbox_inches="tight")
    plt.close()

def plot_latency(df_runs):
    if df_runs.empty:
        return
    df = df_runs.sort_values(["antena", "unidade", "teste"])
    plt.figure(figsize=(12, 5))
    plt.bar(df["ensaio"], df["lat_avg_ms"], color=[color_for_antena(a) for a in df["antena"]])
    plt.xticks(rotation=65, ha="right")
    plt.ylabel("Latência média (ms)")
    plt.title("Latência média por ensaio")
    plt.grid(axis="y", linestyle="--", alpha=0.4)
    plt.tight_layout()
    plt.savefig(os.path.join(OUTPUT_DIR, "02_latencia_por_ensaio.png"), dpi=300, bbox_inches="tight")
    plt.close()

def plot_family_summary(df_family):
    if df_family.empty:
        return

    labels = df_family["antena"].tolist()
    fig, axes = plt.subplots(1, 3, figsize=(15, 5))

    axes[0].bar(labels, df_family["fail_rate_mean"], color=[color_for_antena(a) for a in labels])
    axes[0].set_title("Falha média (%)")
    axes[0].set_ylabel("Menor é melhor")
    axes[0].grid(axis="y", linestyle="--", alpha=0.4)

    axes[1].bar(labels, df_family["lat_mean"], color=[color_for_antena(a) for a in labels])
    axes[1].set_title("Latência média (ms)")
    axes[1].set_ylabel("Menor é melhor")
    axes[1].grid(axis="y", linestyle="--", alpha=0.4)

    axes[2].bar(labels, df_family["rssi_link_mean"], color=[color_for_antena(a) for a in labels])
    axes[2].set_title("RSSI link médio (dBm)")
    axes[2].set_ylabel("Maior é melhor")
    axes[2].grid(axis="y", linestyle="--", alpha=0.4)

    fig.suptitle("Resumo consolidado por família", fontsize=14, fontweight="bold")
    plt.tight_layout()
    plt.savefig(os.path.join(OUTPUT_DIR, "03_resumo_consolidado_familia.png"), dpi=300, bbox_inches="tight")
    plt.close()

# =========================================================
# RELATÓRIO TXT
# =========================================================

def write_report(df_runs, df_family):
    path = os.path.join(OUTPUT_DIR, "Resumo_Executivo_Ping.txt")

    with open(path, "w", encoding="utf-8") as f:
        f.write("RELATÓRIO EXECUTIVO - TESTE COMPLEMENTAR DE PING\n")
        f.write("=" * 60 + "\n\n")

        f.write("Objetivo: comparar robustez lógica do enlace sob tráfego em rajadas,\n")
        f.write("como complemento aos testes de RSSI in-case e à análise visual do SA6.\n\n")

        f.write("RESULTADO CONSOLIDADO POR ANTENA\n")
        f.write("-" * 60 + "\n")
        if df_family.empty:
            f.write("Sem dados suficientes.\n")
        else:
            for _, row in df_family.iterrows():
                fail_std = 0.0 if pd.isna(row["fail_rate_std"]) else row["fail_rate_std"]
                lat_std = 0.0 if pd.isna(row["lat_std"]) else row["lat_std"]
                rssi_std = 0.0 if pd.isna(row["rssi_link_std"]) else row["rssi_link_std"]

                f.write(
                    f"{int(row['ranking'])}. {row['antena']} | "
                    f"Ensaios={int(row['ensaios'])} | "
                    f"Unidades={int(row['unidades'])} | "
                    f"Falha média={row['fail_rate_mean']:.2f}% (std {fail_std:.2f}) | "
                    f"Latência média={row['lat_mean']:.2f} ms (std {lat_std:.2f}) | "
                    f"RSSI_LINK médio={row['rssi_link_mean']:.2f} dBm (std {rssi_std:.2f})\n"
                )

            f.write("\nCONCLUSÃO\n")
            f.write("-" * 60 + "\n")
            best = df_family.iloc[0]
            f.write(
                f"A família líder neste ensaio complementar foi {best['antena']}, "
                f"com menor combinação de falha e latência, e RSSI do link médio de "
                f"{best['rssi_link_mean']:.2f} dBm.\n"
            )
            f.write(
                "Esse resultado deve ser cruzado com os ensaios principais de RSSI in-case.\n"
            )

# =========================================================
# MAIN
# =========================================================

def main():
    print("=" * 70)
    print("RELATÓRIO EXECUTIVO - LOGS DE PING")
    print("=" * 70)

    df_summary, df_bursts = parse_logs()

    if df_summary.empty:
        print("[ERRO] Nenhum log válido encontrado.")
        print("Exemplo esperado: Ping_A4_U1_T1.txt")
        return

    df_runs, df_family = build_consolidated(df_summary, df_bursts)

    # CSVs
    df_summary.to_csv(os.path.join(OUTPUT_DIR, "01_resumo_bruto_end_test.csv"), index=False, encoding="utf-8-sig")
    df_bursts.to_csv(os.path.join(OUTPUT_DIR, "02_bursts_bruto.csv"), index=False, encoding="utf-8-sig")
    df_runs.to_csv(os.path.join(OUTPUT_DIR, "03_resumo_por_ensaio.csv"), index=False, encoding="utf-8-sig")
    df_family.to_csv(os.path.join(OUTPUT_DIR, "04_resumo_por_antena.csv"), index=False, encoding="utf-8-sig")

    # Gráficos
    plot_fail_rate(df_runs)
    plot_latency(df_runs)
    plot_family_summary(df_family)

    # TXT
    write_report(df_runs, df_family)

    print(f"[OK] Saída gerada em: {OUTPUT_DIR}")
    print("\nRanking final:")
    print(df_family[[
        "ranking", "antena", "ensaios", "unidades",
        "fail_rate_mean", "lat_mean", "rssi_link_mean"
    ]].to_string(index=False))

if __name__ == "__main__":
    main()
