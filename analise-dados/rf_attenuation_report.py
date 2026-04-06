"""
Script de Análise Comparativa de Perda In-Case RF (Baseline vs Invólucro)
Objetivo: Quantificar a perda total de desempenho RF causada pela condição
montada no invólucro (case + posição + geometria interna + interação com a PCB),
comparando RSSI médio entre cenário baseline (ar livre) e in-case.

Autor: Guilherme Bertanha
Versão revisada: ChatGPT
"""

import os
import numpy as np
import pandas as pd
import matplotlib.pyplot as plt

# ============================================================
# CONFIGURAÇÃO DE CAMINHOS E MAPEAMENTO DE DADOS
# ============================================================

LOG_DIR = r"C:\Terasite\Antenas\Logs"

TARGET_MAPPING = {
    'A0 (Interna ESP)': {'Baseline': 'A0_R1', 'InCase': 'A0_CASE1'},
    'A1 (Referência)':  {'Baseline': 'A1_R1', 'InCase': 'A1_CASE1'},
    'A3 (Intermed.)':   {'Baseline': 'A3_R1', 'InCase': 'A3_CASE1'},
    'A4 (Unidade 1)':   {'Baseline': 'A4_R1', 'InCase': 'A4_CASE1'},
    'A4 (Unidade 2)':   {'Baseline': 'A4_R2', 'InCase': 'A4_CASE3_antDif'}  # Validação de lote / cenário alternativo
}

OUTPUT_CSV = os.path.join(LOG_DIR, "Resumo_Comparativo_InCase.csv")
OUTPUT_IMG = os.path.join(LOG_DIR, "Grafico_Comparativo_InCase.png")

# Tags que indicam problemas de conectividade
DISCONNECT_TAGS = ("DISCONNECTED", "NO_WIFI", "START_FAIL")

# ============================================================
# FUNÇÕES AUXILIARES
# ============================================================

def resolve_filepath(basepath: str):
    """
    Resolve automaticamente arquivos sem extensão, .txt ou .csv.
    Retorna o caminho válido ou None.
    """
    candidates = [
        basepath,
        basepath + ".txt",
        basepath + ".csv"
    ]

    for path in candidates:
        if os.path.exists(path):
            return path

    return None


def parse_log_file(filepath: str):
    """
    Lê o arquivo e extrai:
    - amostras de RSSI
    - contagem de eventos de desconexão/falha
    - número total de linhas lidas
    """
    rssi_samples = []
    disconnect_count = 0
    total_lines = 0

    with open(filepath, "r", encoding="utf-8", errors="ignore") as file:
        for line in file:
            total_lines += 1
            line = line.strip()

            # Conta eventos problemáticos
            if any(tag in line for tag in DISCONNECT_TAGS):
                disconnect_count += 1

            # Extrai RSSI se existir
            if "RSSI=" in line:
                try:
                    value_str = line.split("RSSI=")[-1].strip()
                    value = int(value_str)
                    rssi_samples.append(value)
                except ValueError:
                    continue

    return {
        "rssi_samples": rssi_samples,
        "disconnect_count": disconnect_count,
        "total_lines": total_lines
    }


def calculate_stats(file_basepath: str):
    """
    Calcula estatísticas do log:
    - média, std, min, max, n
    - desconexões
    """
    filepath = resolve_filepath(file_basepath)
    if filepath is None:
        return None

    parsed = parse_log_file(filepath)
    samples = parsed["rssi_samples"]

    if not samples:
        return {
            "filepath": filepath,
            "mean": None,
            "std": None,
            "min": None,
            "max": None,
            "n": 0,
            "disconnects": parsed["disconnect_count"],
            "total_lines": parsed["total_lines"]
        }

    arr = np.array(samples, dtype=float)

    return {
        "filepath": filepath,
        "mean": float(np.mean(arr)),
        "std": float(np.std(arr, ddof=1)) if len(arr) > 1 else 0.0,
        "min": int(np.min(arr)),
        "max": int(np.max(arr)),
        "n": int(len(arr)),
        "disconnects": int(parsed["disconnect_count"]),
        "total_lines": int(parsed["total_lines"])
    }


def classify_loss(loss_db: float):
    """
    Classificação qualitativa simples da perda in-case.
    """
    if loss_db <= 3:
        return "Excelente"
    elif loss_db <= 8:
        return "Boa"
    elif loss_db <= 15:
        return "Marginal"
    else:
        return "Crítica"


# ============================================================
# GERAÇÃO DO RELATÓRIO
# ============================================================

def generate_comparative_report():
    results = []

    print("\n===============================================================================")
    print(" RELATÓRIO TÉCNICO: PERDA DE DESEMPENHO RF NO INVÓLUCRO (BASELINE vs IN-CASE)")
    print("===============================================================================")
    print("Obs.: O delta calculado representa a penalidade total da condição montada")
    print("      no invólucro, e não apenas a atenuação intrínseca do material PA66.\n")

    for label, paths in TARGET_MAPPING.items():
        baseline_base = os.path.join(LOG_DIR, paths["Baseline"])
        incase_base = os.path.join(LOG_DIR, paths["InCase"])

        baseline_stats = calculate_stats(baseline_base)
        incase_stats = calculate_stats(incase_base)

        if baseline_stats is None:
            print(f"[ERRO] Arquivo baseline não encontrado para: {label}")
            continue

        if incase_stats is None:
            print(f"[ERRO] Arquivo in-case não encontrado para: {label}")
            continue

        if baseline_stats["mean"] is None:
            print(f"[ERRO] Sem amostras RSSI válidas no baseline de: {label}")
            continue

        if incase_stats["mean"] is None:
            print(f"[ERRO] Sem amostras RSSI válidas no in-case de: {label}")
            continue

        # Perda positiva e intuitiva
        loss_db = baseline_stats["mean"] - incase_stats["mean"]
        verdict = classify_loss(loss_db)

        result_row = {
            "Antena": label,

            "Baseline_Arquivo": os.path.basename(baseline_stats["filepath"]),
            "Baseline_Media_dBm": baseline_stats["mean"],
            "Baseline_Std_dB": baseline_stats["std"],
            "Baseline_Min_dBm": baseline_stats["min"],
            "Baseline_Max_dBm": baseline_stats["max"],
            "Baseline_Amostras": baseline_stats["n"],
            "Baseline_Desconexoes": baseline_stats["disconnects"],

            "InCase_Arquivo": os.path.basename(incase_stats["filepath"]),
            "InCase_Media_dBm": incase_stats["mean"],
            "InCase_Std_dB": incase_stats["std"],
            "InCase_Min_dBm": incase_stats["min"],
            "InCase_Max_dBm": incase_stats["max"],
            "InCase_Amostras": incase_stats["n"],
            "InCase_Desconexoes": incase_stats["disconnects"],

            "Perda_InCase_dB": loss_db,
            "Classificacao": verdict
        }

        results.append(result_row)

        print(f"[{label}]")
        print(f"  Baseline:")
        print(f"    Arquivo       : {result_row['Baseline_Arquivo']}")
        print(f"    Média RSSI    : {baseline_stats['mean']:.2f} dBm")
        print(f"    Desvio Padrão : {baseline_stats['std']:.2f} dB")
        print(f"    Faixa         : {baseline_stats['min']} a {baseline_stats['max']} dBm")
        print(f"    Amostras      : {baseline_stats['n']}")
        print(f"    Desconexões   : {baseline_stats['disconnects']}")

        print(f"  In-Case:")
        print(f"    Arquivo       : {result_row['InCase_Arquivo']}")
        print(f"    Média RSSI    : {incase_stats['mean']:.2f} dBm")
        print(f"    Desvio Padrão : {incase_stats['std']:.2f} dB")
        print(f"    Faixa         : {incase_stats['min']} a {incase_stats['max']} dBm")
        print(f"    Amostras      : {incase_stats['n']}")
        print(f"    Desconexões   : {incase_stats['disconnects']}")

        print(f"  Resultado:")
        print(f"    Perda In-Case : {loss_db:.2f} dB")
        print(f"    Classificação : {verdict}\n")

    if not results:
        print("[ERRO] Não há dados suficientes para gerar relatório.")
        return

    # ------------------------------------------------------------
    # SALVA CSV RESUMO
    # ------------------------------------------------------------
    df = pd.DataFrame(results)
    df_sorted = df.sort_values(by="Perda_InCase_dB", ascending=True).reset_index(drop=True)
    df_sorted.to_csv(OUTPUT_CSV, index=False, encoding="utf-8-sig")

    print("-------------------------------------------------------------------------------")
    print(f"[OK] Resumo CSV salvo em: {OUTPUT_CSV}")
    print("-------------------------------------------------------------------------------")

    # ------------------------------------------------------------
    # GRÁFICO
    # ------------------------------------------------------------
    labels = df_sorted["Antena"].tolist()
    baseline_vals = df_sorted["Baseline_Media_dBm"].tolist()
    incase_vals = df_sorted["InCase_Media_dBm"].tolist()
    loss_vals = df_sorted["Perda_InCase_dB"].tolist()
    baseline_std = df_sorted["Baseline_Std_dB"].tolist()
    incase_std = df_sorted["InCase_Std_dB"].tolist()

    x = np.arange(len(labels))
    width = 0.36

    fig, ax = plt.subplots(figsize=(15, 8))

    color_baseline = "#2980b9"
    color_incase = "#c0392b"

    rects1 = ax.bar(
        x - width / 2,
        baseline_vals,
        width,
        label="Baseline (Sem Case)",
        color=color_baseline,
        yerr=baseline_std,
        capsize=5,
        alpha=0.92
    )

    rects2 = ax.bar(
        x + width / 2,
        incase_vals,
        width,
        label="In-Case (Montado no Invólucro)",
        color=color_incase,
        yerr=incase_std,
        capsize=5,
        alpha=0.92
    )

    ax.set_ylabel("RSSI Médio (dBm)", fontsize=12)
    ax.set_title(
        "Comparativo de Desempenho RF: Baseline vs In-Case",
        fontsize=16,
        fontweight="bold",
        pad=18
    )
    ax.set_xticks(x)
    ax.set_xticklabels(labels, fontsize=11)
    ax.legend(loc="lower left", fontsize=11)

    # Escala típica de RSSI
    ax.set_ylim(-80, -20)

    # Grade
    ax.grid(axis="y", linestyle="--", alpha=0.4)

    # Faixas de qualidade visuais
    ax.axhspan(-50, -20, color="#2ecc71", alpha=0.08)
    ax.axhspan(-67, -50, color="#f1c40f", alpha=0.08)
    ax.axhspan(-80, -67, color="#e74c3c", alpha=0.08)

    # Valores nas barras
    for rect in rects1:
        h = rect.get_height()
        ax.annotate(
            f"{h:.1f}",
            xy=(rect.get_x() + rect.get_width() / 2, h),
            xytext=(0, 3),
            textcoords="offset points",
            ha="center",
            va="bottom",
            fontsize=9
        )

    for rect in rects2:
        h = rect.get_height()
        ax.annotate(
            f"{h:.1f}",
            xy=(rect.get_x() + rect.get_width() / 2, h),
            xytext=(0, 3),
            textcoords="offset points",
            ha="center",
            va="bottom",
            fontsize=9
        )

    # Delta / perda entre barras
    for i, loss in enumerate(loss_vals):
        mid_y = incase_vals[i] + 4
        ax.annotate(
            f"Perda\n{loss:.1f} dB",
            xy=(x[i], mid_y),
            ha="center",
            va="bottom",
            fontsize=9,
            fontweight="bold",
            color="white",
            bbox=dict(
                facecolor="black",
                alpha=0.65,
                edgecolor="none",
                boxstyle="round,pad=0.25"
            )
        )

    plt.tight_layout()
    plt.savefig(OUTPUT_IMG, dpi=300, bbox_inches="tight")

    print(f"[OK] Gráfico salvo em: {OUTPUT_IMG}")
    print("===============================================================================\n")

    plt.show()


if __name__ == "__main__":
    generate_comparative_report()
