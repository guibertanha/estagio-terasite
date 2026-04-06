# Contexto Técnico do Projeto — Estágio Terasite 2026

Este documento preserva o contexto técnico e operacional do projeto para referência
futura e onboarding de novos colaboradores.

---

## A Empresa e o Produto

**Terasite Tecnologia** — empresa de IoT industrial.

**Produto:** Frotall IoT Telemetry Gateway — modelo **FRITG01LTE**

**Finalidade:** Telemetria embarcada em máquinas pesadas de linha amarela para:
- Horímetro virtual
- Monitoramento de vibração
- Rastreamento GPS
- Comunicação IoT via LTE

---

## Arquitetura do Hardware

| Componente | Modelo | Observação |
|---|---|---|
| Microcontrolador | ESP32-WROOM-32 | Wi-Fi + BT integrados |
| Modem celular | SIM7600G | LTE Cat-4 + GPS |
| IMU | LSM6DS3 | Acelerômetro + giroscópio |
| Armazenamento | Flash SPI externa | 16 MB |
| Conectores | Aptiv automotivos | Padrão linha amarela |
| Invólucro | PA66 | Proteção IP54 |
| Alimentação | 12 V / 24 V veicular | Com proteção Load Dump |

---

## Meu Trabalho no Estágio

**Foco principal:** Validação e seleção de antenas Wi-Fi para o gateway Frotall.

O invólucro PA66 do FRITG01LTE atenua o sinal Wi-Fi da antena nativa do ESP32.
O objetivo é identificar qual antena externa oferece o melhor compromisso entre
desempenho RF (RSSI, estabilidade de enlace) e robustez mecânica dentro do case.

---

## Antenas Avaliadas

| ID | Descrição | Resultado |
|----|-----------|-----------|
| A0 | Nativa PCB ESP32 (integrada) | Referência — degradação severa in-case |
| A1 | Externa cilíndrica com cabo SMA | Avaliada Fase 1 — descartada |
| A2 | Externa flexível longa | Descartada — sem vantagem mecânica |
| A3 | Externa flexível média adesiva | Avaliada Fase 1 |
| A4 | Micro antena rígida SMD | **Finalista** — melhor robustez mecânica in-case |
| A5 | Flexível FPC Molex T-Bar adesiva | **Finalista** — melhor RSSI médio in-case |

**Status atual (Fase 2):** A4 vs A5 em avaliação final. Ainda não há decisão definitiva.

---

## Metodologia de Ensaios

### Nomenclatura dos Logs
- `Ax` — identificador da antena (A0–A5)
- `Ux` — número da unidade do gateway testada (U1, U2, U3)
- `Tx` — número da tentativa/repetição (T1, T2, T3)
- `Rx` — run baseline em condição aberta
- `CASEx` — medição in-case (dentro do invólucro)

### Fase 1 — RSSI (Antenas A0, A1, A2, A3, A4)
- Medições de RSSI em condição aberta (baseline) e in-case
- Script de coleta: `testes-antena/rf_baseline_logger/`
- Análise: `analise-dados/rf_masterblaster.py`
- Resultados: `relatorios/rssi-fase1/`

### Fase 2 — RSSI + Ping (Antenas A4 e A5)
- Inclusão da A5; ensaios com múltiplas unidades e repetições
- Ensaios de ping em rajada (burst): 100 pings por rajada, várias rajadas por ensaio
- Análise qualitativa do espectro no SA6 (35–6200 MHz, IF BW 200 kHz)
  - Recursos utilizados: Max Hold, Avg trace, Waterfall, marcadores de pico
- Scripts: `analise-dados/rf_ping_masterblaster.py`, `analise-dados/ping_relatorio.py`
- Resultados: `relatorios/ping-tecnico/`, `relatorios/ping-executivo/`

---

## Instrumentação Disponível

### Analisador de Espectro SA6
- Faixa: 35–6200 MHz
- IF Bandwidth: fixo 200 kHz
- Cabo de medição: SMA RG174, 30 cm
- Recursos usados: Max Hold, Avg trace, Waterfall, marcadores
- Manual: `datasheets/instrumentacao/SA6_manual.pdf`

### Gateway ESP32 (placa de teste)
- Firmware customizado de logging autônomo
- Conecta ao AP de referência e loga RSSI a cada segundo
- Sketches: `testes-antena/`

---

## Próximos Ensaios Planejados

### Ensaios Termomecânicos (pasta: `ensaios-futuros/termomecanico/`)
Referência às máquinas da construtora (ver datasheets em `datasheets/maquinas-campo/`):
- **TM-01:** [conforme TM-001_datasheet.pdf]
- **TM-02:** [conforme TM-002_manual_instalacao.pdf]
- **TM-03:** [conforme TM-003_specalog.pdf]

### Varredura EMI/EMC (pasta: `ensaios-futuros/emi-emc/`)
- Sondas de campo próximo no SA6
- Objetivo: mapear fontes de interferência internas ao case

### Ensaios de Campo iPerf3 (pasta: `ensaios-futuros/campo/`)
- Throughput Wi-Fi real com iPerf3 nas máquinas da construtora
- Survey de posicionamento do gateway nos veículos
- Guia de operação: `docs/guia-iperf.md`

### Ensaios Destrutivos PVT/MP
- Load Dump (pico de tensão veicular)
- Brownout / Flash (queda de tensão)
- CAN Fault Injection

---

## Ambiente de Desenvolvimento

| Ferramenta | Uso |
|---|---|
| VS Code + PlatformIO | Desenvolvimento e upload do firmware ESP32 |
| Arduino IDE | Alternativa para sketches de teste |
| Python 3.x | Scripts de análise e geração de relatórios |
| Git + GitHub | Controle de versão deste repositório |

---

## Firmware Oficial Frotall

- **Localização:** `firmware-frotall/` (referência local somente leitura)
- **Branch ativa:** `3.15.0.debug`
- **Responsável:** Neilton Campos Morais
- **Regra:** não fazer push nesse repositório sem validar com o Neilton

---

## Pessoas e Papéis

| Pessoa | Papel |
|---|---|
| Guilherme Bertanha | Estagiário Eng. Mecatrônica — autor deste repositório |
| Neilton Campos Morais | Responsável pelo firmware Frotall |
