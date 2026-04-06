# analise-dados/

Scripts Python para processamento dos logs brutos, geração de gráficos e relatórios.

## Scripts

| Arquivo | Função |
|---|---|
| `rf_masterblaster.py` | Pipeline principal de análise RSSI. Lê todos os logs de `dados-brutos/rssi-fase*/`, calcula estatísticas (média, std, perda in-case) e gera os gráficos e CSVs de `relatorios/rssi-fase1/`. |
| `rf_baseline_stats.py` | Análise estatística focada nos dados de baseline (condição aberta). |
| `rf_attenuation_report.py` | Calcula e visualiza a atenuação introduzida pelo invólucro PA66 (delta RSSI baseline → in-case). |
| `rf_incase_timeseries.py` | Plota a série temporal do RSSI in-case por antena para visualização de estabilidade. |
| `rf_ping_masterblaster.py` | Pipeline de análise dos ensaios de ping. Lê os logs de `dados-brutos/ping/`, calcula latência, taxa de falha e RSSI de enlace, gera outputs em `relatorios/ping-tecnico/`. |
| `ping_relatorio.py` | Gerador do relatório executivo de ping (`relatorios/ping-executivo/`). |

## Templates

| Arquivo | Uso |
|---|---|
| `template_resultados.csv` | Template padrão em pt-BR com separador `;` para registro manual de resultados. |
| `template_resultados_legado.csv` | Versão legada com separador `,` (mantida para compatibilidade). |

## Como Executar

```bash
# Criar ambiente virtual (apenas na primeira vez)
python -m venv .venv
.venv\Scripts\activate   # Windows

# Instalar dependências
pip install pandas matplotlib numpy

# Rodar a análise RSSI completa
python rf_masterblaster.py

# Rodar a análise de ping
python rf_ping_masterblaster.py
```

Os outputs são gerados diretamente nas subpastas correspondentes de `relatorios/`.

## Convenção de Nomenclatura dos Logs

Os scripts esperam que os logs estejam nomeados conforme:
- `Ax_Ux_Tx.txt` — onde `A` = antena, `U` = unidade, `T` = tentativa
- Exemplo: `A4_U2_T3.txt`, `A5_U1_T1.txt`
