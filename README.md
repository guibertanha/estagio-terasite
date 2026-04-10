# Estágio Terasite — Validação de Antenas Wi-Fi (FRITG01LTE)

Repositório de estágio em Engenharia Mecatrônica na **Terasite Tecnologia**.  
Objetivo: selecionar a melhor antena Wi-Fi externa para o gateway IoT **Frotall FRITG01LTE**,
instalado em máquinas de construção civil (escavadeiras, motoniveladoras, compactadoras).

---

## Contexto

O Frotall é um gateway de telemetria embarcada (ESP32-WROOM-32 + SIM7600G LTE + Flash SPI 16 MB)
instalado em máquinas de linha amarela. A antena Wi-Fi interna (INT) opera dentro de um invólucro
PA66 com proteção IP54, em ambiente com vibração intensa, EMI do motor e variação de tensão.

O objetivo é determinar se alguma das antenas externas (A41, A42, A51, A52, A53) supera a INT
em condições reais de campo, usando métricas objetivas: RSSI, PLR, throughput TCP e TTR.

---

## Antenas Avaliadas

| ID | Tipo | Status | Score bancada |
|----|------|--------|---------------|
| INT | Interna (baseline) | A testar | — |
| A41 | Externa | Testada (bancada 09/04) | 57.2 |
| A42 | Externa | Testada (bancada 09/04) | 52.8 |
| A51 | Externa | Testada (bancada 09/04) | 76.7 |
| A52 | Externa | Testada (bancada 09/04) | 67.8 |
| A53 | Externa | Testada (bancada 09/04) | **100.0** |

Score relativo à campanha: 100 = melhor antena testada, 0 = pior.
INT ainda não incluída — será o baseline de comparação no teste de campo.

---

## Estrutura do Repositório

```
estagio-terasite/
├── testes-antena/
│   └── rf_field_validator/     <- PROJETO PRINCIPAL
│       ├── rf_field_validator.ino
│       ├── config.h            <- único arquivo a editar por campanha
│       ├── profile_a.h/.cpp    <- BURN: ping 3s + TCP 10s + cooldown 2s
│       ├── profile_b.h/.cpp    <- WALK (2Hz) e CLOCK (1Hz com marcadores)
│       ├── csv_log.h/.cpp      <- ring buffer, flush 2s, CRC16/linha
│       ├── state_machine.h/.cpp
│       ├── supervision.h/.cpp  <- V_IN, temperatura, link edge-triggered
│       ├── weblog.h/.cpp       <- terminal de logs via browser
│       ├── web_ui.h/.cpp       <- painel HTML completo na porta 80
│       ├── campanhas/          <- dados coletados por data
│       │   └── YYYY-MM-DD/
│       │       ├── BURN_A53_MESA_DES_R01.csv
│       │       └── report/
│       │           ├── report.html
│       │           └── summary.csv
│       └── tools/
│           ├── parser.py       <- pipeline offline: ingestao -> score -> HTML
│           ├── tcp_sink.py     <- servidor TCP para medir throughput
│           └── sync.py         <- baixa CSVs do ESP32 + roda parser
├── datasheets/
│   ├── antenas/                <- PDFs das antenas
│   ├── instrumentacao/         <- SA6 spectrum analyzer manual
│   └── maquinas-campo/         <- datasheets das maquinas
├── dados-brutos/               <- dados de fases anteriores (legacy)
└── relatorios/                 <- relatorios de fases anteriores (legacy)
```

---

## Modos de Teste

| Modo | Cadência | Uso |
|------|----------|-----|
| **BURN** | Janelas 15s (ping 3s + TCP 10s + cool 2s) | Throughput e RSSI em condicao estacionaria |
| **WALK** | 2 Hz continuo | TTR (tempo de reconexao) ao mover pela area |
| **CLOCK** | 1 Hz com marcadores de posicao | Mapeamento RSSI por ponto do ambiente |
| **BURN 3x60** | 3 blocos de 60s | Estabilidade ao longo do tempo |

---

## Pipeline de Analise

```bash
# No notebook — necessario para medir throughput BURN
python tools/tcp_sink.py --port 5201

# Celular acessa http://<IP_ESP32>/ para controlar os testes

# Ao terminar — baixa CSVs e gera relatorio HTML
python tools/sync.py <IP_ESP32>
# ou: painel web -> Baixar todos -> logs.zip
# depois: python tools/parser.py campanhas/YYYY-MM-DD
```

O relatorio HTML inclui: banner vencedor, radar multidimensional, heatmap de metricas,
distribuicao RSSI (P10-P90), time series por janela BURN e comparacao por marcador CLOCK.

---

## Score RF

```
Score = 40% PLR + 33% RSSI P10 + 27% Throughput   (TTR excluido quando sem desconexoes WALK)
```

Normalizacao min-max entre as antenas da campanha. Requer INT na mesma pasta para comparacao valida.

---

## Instrumentacao

- **SA6** — Analisador de espectro portatil 35-6200 MHz, piso -100 dBm, com gerador de rastreamento
  - Uso: varredura em 2,4 GHz antes e depois de ligar o motor para quantificar EMI
- **ESP32-WROOM-32** com firmware rf_field_validator (este repositorio)

---

## Cronograma

| Mes | Atividade |
|-----|-----------|
| 2-3 | Testes de bancada (em andamento — falta INT) |
| 3-4 | Analise de resultados de bancada |
| 4 | **Testes em campo** (proxima semana) |
| 4-5 | Otimizacao do firmware e reteste |
| 6-7 | Estudo comparativo e relatorio final |

---

## Autor

**Guilherme Bertanha** — Estagiario Eng. Mecatronica  
Terasite Tecnologia · Frotall FRITG01LTE
