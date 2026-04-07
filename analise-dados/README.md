# analise-dados

Scripts Python para análise dos dados de RF coletados nos ensaios de antenas
WiFi do projeto FROTALL (firmware ESP32).

## Como executar

### 1. Criar e ativar o ambiente virtual

```bash
# Criar o ambiente (uma vez)
python -m venv .venv

# Ativar no Windows
.venv\Scripts\activate

# Ativar no Linux/macOS
source .venv/bin/activate
```

### 2. Instalar dependências

```bash
pip install -r analise-dados/requirements.txt
```

### 3. Rodar os scripts

Execute a partir da **raiz do repositório**:

```bash
# Análise completa de RSSI (Fases 1 e 2)
python analise-dados/rf_masterblaster.py

# Análise de ping / estresse TX
python analise-dados/rf_ping_masterblaster.py

# Comparativo Baseline vs In-Case
python analise-dados/rf_attenuation_report.py
```

Os relatórios são gerados automaticamente em `relatorios/`.

---

## Pré-requisitos

```bash
pip install numpy pandas matplotlib
```

## Estrutura

```
analise-dados/
├── config.py                  # Paths centralizados (relativos ao repo)
├── utils/
│   ├── rssi_parser.py         # Parser canônico de logs de RSSI
│   └── ping_parser.py         # Parser canônico de logs de ping
├── rf_masterblaster.py        # Análise completa de RSSI (Fase 1 + Fase 2)
├── rf_ping_masterblaster.py   # Análise completa de ping / estresse TX
├── rf_attenuation_report.py   # Comparativo Baseline vs In-Case
└── _arquivo/                  # Scripts obsoletos (ver _arquivo/README.md)
```

Todos os scripts leem de `dados-brutos/` e escrevem em `relatorios/`,
ambos na raiz do repositório. Os diretórios de saída são criados
automaticamente — não é necessário criá-los manualmente.

---

## rf_masterblaster.py — Análise RSSI Completa

Carrega todos os logs de RSSI das Fases 1 e 2, calcula estatísticas por
ensaio, por família de antena e compara cenários BASE vs CASE.

**Entrada:**
- `dados-brutos/rssi-fase1/` — logs `.txt` com nomes listados em
  `FASE1_FILE_MAP` (ex.: `A0_R1.txt`, `A4_CASE1.txt`)
- `dados-brutos/rssi-fase2/` — logs `.txt` com padrão `A<n>_U<n>_T<n>.txt`
  (ex.: `A5_U2_T3.txt`)

**Saída** → `relatorios/rssi-completo/`:

| Arquivo | Conteúdo |
|---|---|
| `01_resumo_por_ensaio.csv` | Estatísticas (média, std, p10, p90…) por ensaio |
| `02_resumo_por_antena.csv` | Agregado por família × cenário |
| `03_case_vs_base.csv` | Perda in-case por antena (dB) |
| `04_amostras_brutas.csv` | Todas as leituras RSSI individuais |
| `01_rssi_medio_por_ensaio.png` | Barras com erro por ensaio |
| `02_ranking_consolidado_case.png` | Ranking das antenas em CASE |
| `03_perda_in_case.png` | Perda BASE→CASE por antena |
| `04_boxplot_case.png` | Boxplot RSSI in-case por família |
| `Resumo_Executivo.txt` | Relatório textual com ranking e observações |

**Como rodar:**

```bash
cd analise-dados
python rf_masterblaster.py
```

**Configurações relevantes no script:**

```python
INCLUIR_A2 = False   # mude para True se A2 for uma antena real
FASE1_FILE_MAP = {…} # mapeamento manual dos arquivos da Fase 1
```

---

## rf_ping_masterblaster.py — Análise de Ping / Estresse TX

Processa todos os logs de ping (firmware FROTALL v2), calculando taxa de
falha, latência e RSSI do link por ensaio, unidade e família de antena.
Inclui verificação de consistência de canal e BSSID.

**Entrada:**
- `dados-brutos/ping/` — logs `.txt` com padrão `Ping_A<n>_U<n>_T<n>.txt`
  (também aceita `PingOut_…` e `A<n>_U<n>_T<n>.txt`)

**Saída** → `relatorios/ping-tecnico/`:

| Arquivo | Conteúdo |
|---|---|
| `01_end_tests_bruto.csv` | Campos do `END_TEST` + metadados por ensaio |
| `02_bursts_bruto.csv` | Cada burst individual (latência, RSSI, canal…) |
| `03_resumo_por_ensaio.csv` | Métricas calculadas + log, por ensaio |
| `04_resumo_por_unidade.csv` | Agregado por antena × unidade |
| `05_resumo_por_familia.csv` | Ranking final por família de antena |
| `01_taxa_falha_por_ensaio.png` | Barras de falha por ensaio |
| `02_latencia_media_por_ensaio.png` | Barras de latência (±std) por ensaio |
| `03_boxplot_latencia_por_antena.png` | Boxplot de latência por família |
| `04_boxplot_rssi_link_por_antena.png` | Boxplot de RSSI do link por família |
| `05_ranking_consolidado_familias.png` | Painel 1×3: falha, latência, RSSI |
| `06_timeline_rssi_por_ensaio.png` | Série temporal RSSI por ensaio |
| `Resumo_Executivo_Ping.txt` | Ranking, alertas de consistência, veredito |

**Como rodar:**

```bash
cd analise-dados
python rf_ping_masterblaster.py
```

> **Robustez:** logs truncados (sem `END_TEST`) têm métricas recalculadas
> automaticamente a partir das linhas de burst capturadas.

---

## rf_attenuation_report.py — Comparativo Baseline vs In-Case

Compara pares específicos de arquivos (ar livre × montado no invólucro),
quantificando a perda RF in-case e classificando cada antena.

**Entrada:**
- `dados-brutos/rssi-fase1/` — pares definidos em `TARGET_MAPPING`
  (basenames sem extensão; suporta `.txt` e `.csv` automaticamente)

**Saída** → `relatorios/rssi-atenuacao/`:

| Arquivo | Conteúdo |
|---|---|
| `comparativo_incase.csv` | Tabela baseline × in-case × perda × classificação |
| `comparativo_incase.png` | Barras agrupadas com zonas de qualidade e deltas |

**Como rodar:**

```bash
cd analise-dados
python rf_attenuation_report.py
```

**Configuração de pares no script:**

```python
TARGET_MAPPING = {
    "A0 (Interna ESP)": {"baseline": "A0_R1", "incase": "A0_CASE1"},
    …  # adicione novos pares conforme necessário
}
```

**Critérios de classificação da perda:**

| Perda (dB) | Classificação |
|---|---|
| ≤ 3 | Excelente |
| ≤ 8 | Boa |
| ≤ 15 | Marginal |
| > 15 | Crítica |

---

## Convenção de nomenclatura dos logs

| Tipo | Padrão | Exemplo |
|---|---|---|
| RSSI Fase 1 | `<Antena>_<Cenário>[_sufixo].txt` | `A4_CASE1.txt`, `A4_R2.txt` |
| RSSI Fase 2 | `<Antena>_U<n>_T<n>.txt` | `A5_U2_T3.txt` |
| Ping | `Ping_<Antena>_U<n>_T<n>.txt` | `Ping_A4_U1_T1.txt` |

---

## Notas

- Todos os paths são **relativos ao repositório** via `config.py` — não há
  caminhos absolutos nos scripts. Edite `config.py` se a estrutura mudar.
- O parser RSSI canônico (`utils/rssi_parser.py`) usa regex `RSSI=(-?\d+)` e
  tolera headers do PuTTY e mensagens de boot do ESP32.
- O parser de ping (`utils/ping_parser.py`) tolera logs sem `END_TEST`
  (reconstrução automática das métricas a partir dos bursts capturados).
- Scripts obsoletos estão em `_arquivo/` com documentação dos motivos de
  descontinuação e dos scripts que os substituem.
