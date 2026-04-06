"""
Análise Comparativa de Perda In-Case RF (Baseline vs Invólucro).

Quantifica a perda total de desempenho RF causada pela condição montada
no invólucro (case + posição + geometria + interação com a PCB),
comparando RSSI médio entre cenário baseline (ar livre) e in-case.

Nota: o delta calculado representa a penalidade total da condição montada,
e não apenas a atenuação intrínseca do material (PA66).
"""

import os
import numpy as np
import pandas as pd
import matplotlib.pyplot as plt

from config import FASE1_DIR, OUTPUT_ATENUACAO as OUTPUT_DIR
from utils.rssi_parser import extract_rssi_samples, summarize_samples, resolve_existing_file

# ============================================================
# CONFIGURAÇÃO
# ============================================================

os.makedirs(OUTPUT_DIR, exist_ok=True)

# Pares (baseline, in-case) a comparar.
# Chaves são rótulos legíveis; valores são basenames dos arquivos em FASE1_DIR.
TARGET_MAPPING = {
    "A0 (Interna ESP)": {"baseline": "A0_R1",   "incase": "A0_CASE1"},
    "A1 (Referência)":  {"baseline": "A1_R1",   "incase": "A1_CASE1"},
    "A3 (Intermed.)":   {"baseline": "A3_R1",   "incase": "A3_CASE1"},
    "A4 (Unidade 1)":   {"baseline": "A4_R1",   "incase": "A4_CASE1"},
    "A4 (Unidade 2)":   {"baseline": "A4_R2",   "incase": "A4_CASE3_antDif"},
}

# ============================================================
# FUNÇÕES AUXILIARES
# ============================================================

def get_stats(basename: str) -> dict | None:
    """
    Resolve o arquivo a partir do basename (sem extensão),
    extrai amostras RSSI e retorna estatísticas.
    Retorna None se o arquivo não existir.
    """
    filepath = resolve_existing_file(str(FASE1_DIR / basename))
    if filepath is None:
        return None

    parsed = extract_rssi_samples(filepath)
    stats  = summarize_samples(parsed["samples"])

    return {
        "filepath":    filepath,
        "mean":        stats["mean"]   if stats["n"] > 0 else None,
        "std":         stats["std"]    if stats["n"] > 0 else None,
        "min":         stats["min"]    if stats["n"] > 0 else None,
        "max":         stats["max"]    if stats["n"] > 0 else None,
        "n":           stats["n"],
        "disconnects": parsed["disconnects"],
    }


def classify_loss(loss_db: float) -> str:
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
    print("\n" + "=" * 79)
    print(" RELATÓRIO TÉCNICO: PERDA DE DESEMPENHO RF NO INVÓLUCRO (BASELINE vs IN-CASE)")
    print("=" * 79)
    print("Obs.: delta = penalidade total da condição montada,")
    print("      não apenas atenuação intrínseca do material PA66.\n")

    results = []

    for label, paths in TARGET_MAPPING.items():
        base_stats  = get_stats(paths["baseline"])
        incase_stats = get_stats(paths["incase"])

        for tag, s in (("baseline", base_stats), ("in-case", incase_stats)):
            if s is None:
                print(f"[ERRO] Arquivo {tag} não encontrado para: {label}")
                break
            if s["mean"] is None:
                print(f"[ERRO] Sem amostras RSSI válidas no {tag} de: {label}")
                break
        else:
            loss_db = base_stats["mean"] - incase_stats["mean"]
            verdict = classify_loss(loss_db)

            results.append({
                "Antena":               label,
                "Baseline_Arquivo":     os.path.basename(base_stats["filepath"]),
                "Baseline_Media_dBm":   base_stats["mean"],
                "Baseline_Std_dB":      base_stats["std"],
                "Baseline_Min_dBm":     base_stats["min"],
                "Baseline_Max_dBm":     base_stats["max"],
                "Baseline_Amostras":    base_stats["n"],
                "Baseline_Desconexoes": base_stats["disconnects"],
                "InCase_Arquivo":       os.path.basename(incase_stats["filepath"]),
                "InCase_Media_dBm":     incase_stats["mean"],
                "InCase_Std_dB":        incase_stats["std"],
                "InCase_Min_dBm":       incase_stats["min"],
                "InCase_Max_dBm":       incase_stats["max"],
                "InCase_Amostras":      incase_stats["n"],
                "InCase_Desconexoes":   incase_stats["disconnects"],
                "Perda_InCase_dB":      loss_db,
                "Classificacao":        verdict,
            })

            print(f"[{label}]")
            for tag, s in (("Baseline", base_stats), ("In-Case", incase_stats)):
                print(f"  {tag}:")
                print(f"    Arquivo       : {os.path.basename(s['filepath'])}")
                print(f"    Média RSSI    : {s['mean']:.2f} dBm")
                print(f"    Desvio Padrão : {s['std']:.2f} dB")
                print(f"    Faixa         : {s['min']:.0f} a {s['max']:.0f} dBm")
                print(f"    Amostras      : {s['n']}")
                print(f"    Desconexões   : {s['disconnects']}")
            print(f"  Resultado:")
            print(f"    Perda In-Case : {loss_db:.2f} dB")
            print(f"    Classificação : {verdict}\n")

    if not results:
        print("[ERRO] Não há dados suficientes para gerar relatório.")
        return

    # CSV
    df = (pd.DataFrame(results)
          .sort_values("Perda_InCase_dB", ascending=True)
          .reset_index(drop=True))

    csv_path = str(OUTPUT_DIR / "comparativo_incase.csv")
    df.to_csv(csv_path, index=False, encoding="utf-8-sig")
    print(f"[OK] CSV salvo em: {csv_path}")

    # Gráfico
    _plot_comparison(df)


def _plot_comparison(df: pd.DataFrame):
    labels       = df["Antena"].tolist()
    baseline_vals = df["Baseline_Media_dBm"].tolist()
    incase_vals  = df["InCase_Media_dBm"].tolist()
    loss_vals    = df["Perda_InCase_dB"].tolist()
    baseline_std = df["Baseline_Std_dB"].tolist()
    incase_std   = df["InCase_Std_dB"].tolist()

    x     = np.arange(len(labels))
    width = 0.36

    fig, ax = plt.subplots(figsize=(15, 8))

    rects1 = ax.bar(x - width / 2, baseline_vals, width,
                    label="Baseline (Sem Case)",
                    color="#2980b9", yerr=baseline_std, capsize=5, alpha=0.92)
    rects2 = ax.bar(x + width / 2, incase_vals, width,
                    label="In-Case (Montado no Invólucro)",
                    color="#c0392b", yerr=incase_std, capsize=5, alpha=0.92)

    ax.set_ylabel("RSSI Médio (dBm)", fontsize=12)
    ax.set_title("Comparativo de Desempenho RF: Baseline vs In-Case",
                 fontsize=16, fontweight="bold", pad=18)
    ax.set_xticks(x)
    ax.set_xticklabels(labels, fontsize=11)
    ax.legend(loc="lower left", fontsize=11)

    # Escala dinâmica com margem
    all_vals = [v for v in baseline_vals + incase_vals if v is not None]
    if all_vals:
        ymin = min(all_vals) - 10
        ymax = max(all_vals) + 10
        ax.set_ylim(ymin, ymax)

    ax.grid(axis="y", linestyle="--", alpha=0.4)

    # Faixas de qualidade
    ax.axhspan(-50, ax.get_ylim()[1], color="#2ecc71", alpha=0.08)
    ax.axhspan(-67, -50,              color="#f1c40f", alpha=0.08)
    ax.axhspan(ax.get_ylim()[0], -67, color="#e74c3c", alpha=0.08)

    # Valores nas barras
    for rect in list(rects1) + list(rects2):
        h = rect.get_height()
        ax.annotate(f"{h:.1f}",
                    xy=(rect.get_x() + rect.get_width() / 2, h),
                    xytext=(0, 3), textcoords="offset points",
                    ha="center", va="bottom", fontsize=9)

    # Delta entre barras
    for i, loss in enumerate(loss_vals):
        mid_y = incase_vals[i] + 4
        ax.annotate(f"Perda\n{loss:.1f} dB",
                    xy=(x[i], mid_y), ha="center", va="bottom",
                    fontsize=9, fontweight="bold", color="white",
                    bbox=dict(facecolor="black", alpha=0.65,
                              edgecolor="none", boxstyle="round,pad=0.25"))

    plt.tight_layout()
    img_path = str(OUTPUT_DIR / "comparativo_incase.png")
    plt.savefig(img_path, dpi=300, bbox_inches="tight")
    plt.close()
    print(f"[OK] Gráfico salvo em: {img_path}")
    print("=" * 79 + "\n")


if __name__ == "__main__":
    generate_comparative_report()
