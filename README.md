# Estágio Terasite — Validação de Antenas Wi-Fi (FRITG01LTE)

Repositório de trabalho do estágio de Engenharia Mecatrônica na **Terasite Tecnologia**.
Contém os dados, scripts, relatórios e documentação produzidos durante a validação e
seleção de antenas Wi-Fi para o gateway IoT **Frotall FRITG01LTE**.

---

## Contexto

O Frotall é um gateway de telemetria embarcada para máquinas pesadas de linha amarela
(ESP32-WROOM-32 + SIM7600G LTE + LSM6DS3 + Flash SPI 16 MB). Uma das atividades de
validação é a seleção da antena Wi-Fi com melhor desempenho dentro do invólucro PA66
(proteção IP54) em condições reais de campo.

Para o contexto técnico completo do projeto, consulte [CONTEXTO.md](./CONTEXTO.md).

---

## Antenas Avaliadas

| ID | Descrição | Status |
|----|-----------|--------|
| A0 | Antena nativa do módulo ESP32 (integrada PCB) | Referência baseline |
| A1 | Externa cilíndrica com cabo | Descartada — ganho insuficiente in-case |
| A2 | Externa flexível longa | Descartada — sem vantagem mecânica |
| A3 | Externa flexível média adesiva | Avaliada na Fase 1 |
| A4 | Micro antena rígida SMD | **Finalista** — melhor robustez mecânica in-case |
| A5 | Flexível FPC Molex T-Bar adesiva | **Finalista** — melhor RSSI in-case |

---

## Estrutura do Repositório

```
estagio-terasite/
├── testes-antena/        # Firmwares Arduino/ESP32 usados nos ensaios
├── analise-dados/        # Scripts Python de processamento e visualização
├── dados-brutos/         # Logs brutos dos ensaios (RSSI e Ping)
│   ├── rssi-fase1/       # Fase 1: A0, A1, A2, A3, A4 (sem A5)
│   ├── rssi-fase2/       # Fase 2: A4 vs A5 com múltiplas unidades
│   └── ping/             # Ensaios de estabilidade de enlace (ping em rajada)
├── relatorios/           # Outputs das análises (CSVs, PNGs, sumários)
│   ├── rssi-fase1/       # Relatório técnico RSSI Fase 1
│   ├── ping-tecnico/     # Relatório técnico de ping (versão engenharia)
│   └── ping-executivo/   # Sumário executivo dos ensaios de ping
├── ensaios-futuros/      # Planejamento dos próximos ciclos de ensaios
│   ├── termomecanico/    # TM-01, TM-02, TM-03
│   ├── emi-emc/          # Varreduras com o analisador SA6
│   └── campo/            # iPerf3 em máquinas reais
├── datasheets/           # Documentação técnica de componentes e equipamentos
│   ├── antenas/
│   ├── instrumentacao/
│   └── maquinas-campo/
├── fotos/                # Fotos das antenas e dos ensaios
│   └── antenas/
├── docs/                 # Procedimentos, checklists e guias operacionais
│   └── relatorios-anteriores/
├── firmware-frotall/     # Referência ao firmware oficial (somente leitura)
└── CONTEXTO.md           # Contexto técnico completo do projeto
```

---

## Fases de Ensaio Realizadas

### Fase 1 — RSSI Baseline e In-Case (A0, A1, A2, A3, A4)
- Medições de RSSI em condição aberta (baseline) e dentro do invólucro PA66
- Antenas A0, A1, A2, A3 e A4
- Resultados em: `relatorios/rssi-fase1/`

### Fase 2 — RSSI Comparativo A4 vs A5 + Ping
- Inclusão da A5 (FPC Molex T-Bar)
- Ensaios com múltiplas unidades (U1, U2, U3) e repetições (T1, T2, T3)
- Ensaios de ping em rajada para estabilidade de enlace
- Análise qualitativa do espectro no SA6 (35–6200 MHz)
- Resultados em: `relatorios/ping-tecnico/` e `relatorios/ping-executivo/`

---

## Próximos Passos

- [ ] Ensaios termomecânicos (TM-01, TM-02, TM-03)
- [ ] Varredura EMI/EMC com sondas de campo próximo no SA6
- [ ] Ensaios de RF em campo com iPerf3 em máquinas reais
- [ ] Survey de posicionamento do gateway nas máquinas da construtora
- [ ] Ensaios destrutivos PVT/MP (Load Dump, Brownout/Flash, CAN Fault Injection)

---

## Instrumentação Utilizada

- Analisador de espectro **SA6** (35–6200 MHz, IF BW fixo 200 kHz)
  - Recursos: Max Hold, Avg trace, Waterfall, marcadores
  - Cabo: SMA RG174 30 cm
- ESP32-WROOM-32 com firmware customizado (`testes-antena/`)

---

## Informações do Repositório

- **Autor:** Guilherme Bertanha — Estagiário Eng. Mecatrônica
- **Empresa:** Terasite Tecnologia
- **Produto:** Frotall IoT Telemetry Gateway (FRITG01LTE)
- **Firmware oficial (somente leitura):** gerenciado por Neilton Campos Morais
