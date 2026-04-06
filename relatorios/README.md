# relatorios/

Outputs gerados pelos scripts de análise: CSVs consolidados, gráficos PNG e sumários
em texto. Estes arquivos são **gerados automaticamente** pelos scripts de `analise-dados/`
a partir dos logs de `dados-brutos/`.

> Se você precisar reproduzir ou atualizar os resultados, rode os scripts em
> `analise-dados/` — não edite os arquivos desta pasta manualmente.

## Subpastas

### rssi-fase1/
Resultados da análise RSSI da Fase 1 (antenas A0–A4).
Gerado por: `analise-dados/rf_masterblaster.py`

| Arquivo | Conteúdo |
|---|---|
| `01_resumo_por_ensaio.csv` | RSSI médio, std e contagem por ensaio individual |
| `01_rssi_medio_por_ensaio.png` | Gráfico de barras: RSSI médio por ensaio |
| `02_resumo_por_antena.csv` | Estatísticas agregadas por antena |
| `02_ranking_consolidado_case.png` | Ranking das antenas in-case |
| `03_case_vs_base.csv` | Delta RSSI entre condição in-case e baseline |
| `03_perda_in_case.png` | Visualização da atenuação introduzida pelo case |
| `04_amostras_brutas.csv` | Todas as amostras brutas consolidadas |
| `04_boxplot_case.png` | Boxplot comparativo in-case por antena |
| `Resumo_Executivo.txt` | Sumário textual com ranking final |

### ping-tecnico/
Análise completa dos ensaios de ping (versão engenharia — 2 ensaios por antena).
Gerado por: `analise-dados/rf_ping_masterblaster.py`

| Arquivo | Conteúdo |
|---|---|
| `01_start_tests.csv` | Metadados de início dos ensaios |
| `02_end_tests_bruto.csv` | Dados brutos de fim de ensaio |
| `03_bursts_bruto.csv` | Dados brutos por rajada de ping |
| `04_resumo_por_ensaio.csv` | Latência média, taxa de falha e RSSI por ensaio |
| `05_resumo_por_unidade.csv` | Agregação por unidade do gateway |
| `06_resumo_por_familia.csv` | Agregação por família (antena) |
| `01_taxa_falha_por_ensaio.png` | Taxa de falha de ping por ensaio |
| `02_latencia_media_por_ensaio.png` | Latência média por ensaio |
| `03_boxplot_latencia_por_antena.png` | Boxplot de latência por antena |
| `04_boxplot_rssi_link_por_antena.png` | Boxplot de RSSI de enlace por antena |
| `05_ranking_consolidado_familias.png` | Ranking final consolidado |
| `06_timeline_rssi_por_ensaio.png` | Série temporal do RSSI por ensaio |
| `Resumo_Executivo_Ping.txt` | Sumário textual com ranking final de ping |

### ping-executivo/
Versão condensada para apresentação executiva.
Gerado por: `analise-dados/ping_relatorio.py`
