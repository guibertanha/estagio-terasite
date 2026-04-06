"""
Script de Análise de Telemetria RF (Baseline - Ar Livre)
Objetivo: Processar logs brutos de RSSI do ESP32, remover anomalias e calcular
estatísticas de performance (Média, Desvio Padrão e P10) para ranqueamento de antenas.
Autor: Guilherme Bertanha
"""

import pandas as pd
import glob
import os
import numpy as np

# Configuração de caminhos
LOG_DIR = r"C:\Terasite\Antenas\Logs"

def process_baseline_logs(log_directory):
    file_pattern = os.path.join(log_directory, 'A*_R*')
    log_files = glob.glob(file_pattern)

    if not log_files:
        print("[ERRO] Nenhum arquivo de log encontrado no diretorio especificado.")
        return

    raw_results = []

    for file_path in log_files:
        filename = os.path.basename(file_path).replace('.txt', '')

        try:
            parts = filename.split('_')
            if len(parts) < 2:
                continue
            antenna_id = parts[0].upper()
            run_id = parts[1].upper()
        except Exception:
            continue

        # Leitura e higienização dos dados CSV
        df = pd.read_csv(file_path, names=['ms', 'event', 'ip', 'rssi_raw'], on_bad_lines='skip', engine='python')

        # Contagem de quedas de link
        drop_count = len(df[df['event'].isin(['DISCONNECTED', 'NO_LINK', 'NO_WIFI'])])

        # Filtro apenas para leituras de sinal válidas
        df_valid = df[df['event'] == 'RSSI'].copy()
        if df_valid.empty:
            continue

        # Extração do valor numérico do RSSI
        df_valid['rssi_val'] = df_valid['rssi_raw'].astype(str).str.replace('RSSI=', '').astype(float)
        rssi_series = df_valid['rssi_val']

        raw_results.append({
            'Antena': antenna_id,
            'Amostra': run_id,
            'Media_dBm': round(rssi_series.mean(), 2),
            'Oscilacao_StdDev': round(rssi_series.std(), 2),
            'Pior_Caso_P10': round(np.percentile(rssi_series, 10), 2),
            'Minimo_dBm': rssi_series.min(),
            'Quedas_Link': drop_count
        })

    if not raw_results:
        print("[AVISO] Arquivos encontrados, mas nenhum dado valido para processar.")
        return

    df_results = pd.DataFrame(raw_results)

    # Agrupamento para média final das antenas
    df_summary = df_results.groupby('Antena').mean(numeric_only=True).reset_index()
    df_summary = df_summary.round({'Media_dBm': 2, 'Oscilacao_StdDev': 2, 'Pior_Caso_P10': 2, 'Minimo_dBm': 2, 'Quedas_Link': 0})

    # Critério de desempate: Maior sinal no pior caso (P10) e menor oscilação (StdDev)
    df_summary = df_summary.sort_values(by=['Pior_Caso_P10', 'Oscilacao_StdDev'], ascending=[False, True])

    # Saída formatada para relatório de terminal
    print("\n========================================================")
    print(" RELATÓRIO DE PERFORMANCE RF - BASELINE (AR LIVRE)")
    print("========================================================\n")
    print("--- DADOS BRUTOS POR AMOSTRA (RUN) ---")
    print(df_results.to_string(index=False))

    print("\n--- RANKING FINAL CONSOLIDADO ---")
    print(df_summary.to_string(index=False))
    print("\n[INFO] Criterio de ranqueamento: Resiliencia em pior cenario (P10) seguido por estabilidade (StdDev).")
    print("========================================================\n")

if __name__ == "__main__":
    process_baseline_logs(LOG_DIR)
