"""
Script de Análise de Telemetria RF (Série Temporal - Latência de Ping)
Objetivo: Processar e visualizar a estabilidade da rede (Latência) ao longo do tempo
com as antenas sob estresse de Flood Ping.
"""

import pandas as pd
import matplotlib.pyplot as plt
import os

# Configuração do novo diretório de logs de Ping
LOG_DIR = r"C:\Terasite\Antenas\Logs\Log Pings"

# Dicionário de arquivos (ajuste os nomes conforme você salvou)
target_files = {
    'A0 (Interna ESP)': 'Ping_A0',
    'A1 (Referência)': 'Ping_A1',
    'A3 (Intermediária)': 'Ping_A3',
    'A4 (Compacta)': 'Ping_A4'
}

def read_latency_data(filepath):
    # Função robusta para lidar com a ocultação de extensão do Windows
    if not os.path.exists(filepath):
        filepath += '.txt'
        if not os.path.exists(filepath):
            # Tenta também .csv caso tenha salvo com essa extensão
            filepath = filepath.replace('.txt', '.csv')
            if not os.path.exists(filepath):
                return []

    samples = []
    with open(filepath, 'r', encoding='utf-8', errors='ignore') as file:
        for line in file:
            # Filtra apenas as linhas de sucesso que contêm o valor da latência
            if 'PING_BURST_OK' in line and 'LATENCIA_MS=' in line:
                try:
                    val = float(line.split('LATENCIA_MS=')[-1].strip())
                    samples.append(val)
                except ValueError:
                    continue
    return samples

def plot_time_series():
    plt.figure(figsize=(12, 7))
    print("\n========================================================")
    print(" ANÁLISE TEMPORAL: ESTABILIDADE DE LATÊNCIA (TESTE DE ESTRESSE)")
    print("========================================================")

    for label, filename in target_files.items():
        full_path = os.path.join(LOG_DIR, filename)
        latency_samples = read_latency_data(full_path)

        if not latency_samples:
            print(f"[AVISO] Dados ausentes para: {label} ({filename})")
            continue

        series = pd.Series(latency_samples)
        mean_val = series.mean()
        std_val = series.std()

        print(f"[INFO] {label}: Latência Média = {mean_val:.2f} ms | Oscilação (StdDev) = {std_val:.2f}")

        # Plotagem da série temporal
        plt.plot(latency_samples, label=f"{label} (Média: {mean_val:.1f} ms)", linewidth=1.5, alpha=0.85)

    # Configurações visuais do gráfico (Padrão Executivo)
    plt.title('Estabilidade de Latência Wi-Fi no Tempo (Estresse Frotall)', fontsize=14, fontweight='bold')
    plt.xlabel('Rajadas de Ping (Progresso do Teste)', fontsize=12)
    plt.ylabel('Latência de Resposta (ms)', fontsize=12)

    # Ajuste da legenda para o topo, já que na latência o gráfico fica espremido embaixo
    plt.legend(loc='upper left', fontsize=10)
    plt.grid(True, linestyle='--', alpha=0.6)

    # Zonas de Qualidade de Latência (Invertido em relação ao RSSI: Menor é melhor)
    plt.axhspan(0, 40, color='#2ecc71', alpha=0.15)    # Zona Verde (Excelente - < 40ms)
    plt.axhspan(40, 100, color='#f1c40f', alpha=0.15)  # Zona Amarela (Marginal - 40ms a 100ms)
    plt.axhspan(100, 200, color='#e74c3c', alpha=0.15) # Zona Vermelha (Crítica - > 100ms)

    # Trava o eixo Y para o gráfico não ficar "dançando" (ajustado para limites normais de ping)
    plt.ylim(0, 150)

    plt.tight_layout()
    print("========================================================")

    # Salva a imagem silenciosamente na mesma pasta para evitar que o Windows abra o "Salvar Como"
    caminho_imagem = os.path.join(LOG_DIR, "Grafico_Série_Temporal_Pings.png")
    plt.savefig(caminho_imagem, dpi=300, bbox_inches='tight')
    print(f"[SUCESSO] Gráfico salvo automaticamente em: {caminho_imagem}")

    # Abre o visualizador padrão também (comportamento original do seu código)
    plt.show()

if __name__ == "__main__":
    plot_time_series()
