# Dashboard RF — Validação de Antenas Wi-Fi

Dashboard interativo para apresentação dos resultados da campanha de
validação de antenas Wi-Fi do gateway **Frotall FRITG01LTE**
(ESP32-WROOM-32 · invólucro PA66 IP54).

## Pré-requisitos

```bash
pip install plotly pandas numpy
```

## Como gerar o dashboard

Execute a partir da raiz do repositório:

```bash
python relatorios/dashboard-rf/generate_dashboard.py
```

O arquivo `dashboard_rf.html` (~4 MB) será gerado na mesma pasta.
Ele é **autossuficiente e funciona offline** — sem necessidade de internet.

## Abrir no navegador

```bash
# Windows
start relatorios\dashboard-rf\dashboard_rf.html

# Linux / macOS
xdg-open relatorios/dashboard-rf/dashboard_rf.html
```

## Seções do dashboard

| Seção | Conteúdo |
|---|---|
| **Hero** | Vencedora + KPIs em 3 segundos de leitura |
| **Scores** | Cards + velocímetros 0–100 por antena |
| **Ranking** | Barras RSSI in-case + radar multidimensional |
| **Atenuação** | Baseline vs in-case + perda em dB por antena |
| **Série temporal** | RSSI ao longo do tempo (amostras brutas + suavização) |
| **Ping** | Latência (box plot) + RSSI vs latência (scatter) + mapa de calor |
| **Metodologia** | Descrição dos ensaios para credibilidade técnica |
| **Próximos passos** | Roadmap TM-01/02/03, EMI-01, RF-03, PVT-01 |
| **Veredicto** | Recomendação final com justificativa |

## Algoritmo de score (0–100)

| Dimensão | Peso | Critério |
|---|---|---|
| RSSI médio in-case | 40% | Maior RSSI = melhor |
| Robustez ao invólucro (Δ baseline→case) | 30% | Menor perda = melhor |
| Estabilidade (σ in-case) | 20% | Menor desvio = melhor |
| Taxa de falha no ping | 10% | Menor falha = melhor |

> **A5** não possui baseline dedicado na Fase 1; nesse caso os pesos são
> redistribuídos para RSSI (55%) + σ (30%) + ping (15%).

## Fontes de dados

O script lê automaticamente os CSVs processados:

```
relatorios/
├── rssi-completo/  (ou rssi-fase1/ como fallback)
│   ├── 02_resumo_por_antena.csv   ← RSSI médio e σ por antena/cenário
│   ├── 03_case_vs_base.csv        ← perda de atenuação do invólucro
│   └── 04_amostras_brutas.csv     ← série temporal de RSSI
├── rssi-atenuacao/
│   └── comparativo_incase.csv     ← análise por unidade
└── ping-tecnico/
    ├── 02_bursts_bruto.csv        ← latência por burst
    └── 05_resumo_por_familia.csv  ← resumo por antena
```

Todos os valores conhecidos estão embutidos como fallback caso
algum CSV não esteja disponível.
