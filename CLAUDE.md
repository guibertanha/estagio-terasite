# CLAUDE.md — estagio-terasite

Projeto de estágio em Eng. Mecatrônica na Terasite Tecnologia.
Objetivo: validar antenas Wi-Fi externas (A41/A42/A51/A52/A53) vs interna (INT)
no gateway Frotall FRITG01LTE instalado em máquinas de construção civil.

---

## Regras obrigatórias

- **Nunca** incluir `Co-Authored-By` em commits — código aparece como exclusivo do autor.
- Commits em português, concisos, sem preamble de IA.
- Não criar arquivos desnecessários. Não refatorar código além do pedido.

---

## Estrutura do repositório

```
estagio-terasite/
├── testes-antena/rf_field_validator/   ← PROJETO PRINCIPAL (firmware + ferramentas)
│   ├── rf_field_validator.ino          ← setup() + loop() + CLI serial
│   ├── config.h                        ← ÚNICO arquivo a editar para trocar rede/pinos
│   ├── state_machine.h/.cpp            ← estados: IDLE→READY→RUNNING_*→FLUSHING
│   ├── csv_log.h/.cpp                  ← ring buffer 64 linhas, flush 2s, CRC16/linha
│   ├── profile_a.h/.cpp                ← BURN: janelas 15s (ping 3s + TCP 10s + cool 2s)
│   ├── profile_b.h/.cpp                ← WALK (2Hz) e CLOCK (1Hz)
│   ├── supervision.h/.cpp              ← V_IN (ADC34), temp (temperatureRead), link
│   ├── weblog.h/.cpp                   ← buffer circular 40 linhas → /weblog (sem Serial)
│   ├── web_ui.h/.cpp                   ← painel HTML servido do PROGMEM, porta 80
│   └── tools/
│       ├── parser.py                   ← pipeline offline: ingestão → score → HTML
│       ├── tcp_sink.py                 ← servidor TCP descarta tudo (alvo throughput)
│       └── sync.py                     ← baixa CSVs do ESP32 + roda parser
├── datasheets/                         ← PDFs das antenas e máquinas
├── dados-brutos/                       ← RSSI e ping de fases anteriores (legacy)
└── relatorios/                         ← relatórios de fases anteriores (legacy)
```

---

## Spec atual: N3.0

### Estados da máquina

```
IDLE → (CONFIG) → READY → (START_WALK/CLOCK/BURN) → RUNNING_* → (STOP) → FLUSHING → READY
```

- `FLUSHING`: task de log chama `csv_close_run()` e volta READY automaticamente
- `BROWNOUT_AUTO_STOP 1`: supervision aciona `sm_cmd_stop()` se V_IN < 10500 mV

### Perfil A — BURN (profile_a.cpp)

Cada janela de 15 s:
- `[0–3s]` ping puro → PLR, RSSI P10 (selection sort parcial), lat_avg
- `[3–13s]` TCP 10 s → throughput via `uint64_t` (evita overflow)
- `[13–15s]` cooldown: `csv_flush_batch()` + delay
- Buffer TCP estático `_tcp_buf[4096]` (não ocupa stack da task)
- BURN 3x60: 3 blocos de 60 s, eventos tipo B, LED pisca entre blocos

### Perfil B — WALK/CLOCK (profile_b.cpp)

- WALK: 2 Hz, sem MARK, cold start permite RSSI=-127 sem Wi-Fi
- CLOCK: 1 Hz, aceita `MARK <label>` (máx 8 chars), agrupa por marker no parser
- LINK_DOWN/LINK_UP: emitido **só pela supervision** na borda de transição (não duplica por ciclo)

### CSV (spec §2.6)

```
timestamp_ms, type, profile, phase, antenna, location, condition, run_id,
rssi_dbm, ping_ok, ping_latency_ms, ping_seq,
throughput_bps, plr_window,
vin_mv, temp_c, link_state, boot_count, uptime_ms,
marker, block, notes, crc16=XXXX
```

- `type`: S (amostra) / E (evento) / M (marker) / B (bloco)
- `phase`: F0 (baseline) / F1 (WALK) / F2 (CLOCK) / F3A (motor OFF) / F3B (motor RUN)
- CRC16 CCITT-FALSE calculado sobre a linha sem o campo crc16
- Nome de arquivo: `[MODO]_[ANT]_[LOC]_[COND]_R[NN].csv`
- `g_flush_incomplete`: bool global, setado se flush_all() encerra com dados na fila

### Flush / integridade

- `FLUSH_INTERVAL_MS 2000` — flush forçado a cada 2 s (era 8 s)
- `FLUSH_BATCH 16` — flush por lote quando ring ≥ 16 linhas
- `csv_flush_all(5000)` — chamado no STOP, timeout 5 s
- `g_flush_incomplete` exibido no painel web como banner amarelo

### Weblog (weblog.h/.cpp)

- Buffer circular 40×96 chars, mutex FreeRTOS
- `weblog_printf()` / `weblog_println()` → Serial E buffer simultaneamente
- GET `/weblog` retorna JSON `{n, lines[]}` — painel faz polling a cada 3 s
- Cores no terminal web: verde [OK], amarelo [WARN]/LINK_DOWN, vermelho [ERR]/BROWNOUT

### Painel web (web_ui.cpp)

- GET `/` → página HTML completa do PROGMEM
- GET `/status` → JSON com: state, cfg, fname, rssi, temp_c, samples, ring, vin_mv, flash_kb, flash_warn, flush_warn, ntp, elapsed_ms, block, blocks_done
- GET `/weblog` → JSON do buffer de log
- GET `/logs` → lista de arquivos
- GET `/download?f=` → stream CSV
- POST `/cmd` → actions: config, start_walk, start_walk_cold, start_clock, start_burn, start_burn3, stop, mark
- STOP web: **2 toques de confirmação** (evita parada por vibração)
- Botão físico PIN_BUTTON=0: toque curto = START_WALK (READY), pressão ≥ 1500 ms = STOP (RUNNING_*)
- `web_ui_try_init()` inicia painel quando WiFi sobe após boot (chamado no loop())
- `flash_warn`: flash_kb < `FS_WARN_KB (128)` → número fica vermelho no painel

### config.h — parâmetros ajustáveis

| Define | Valor | Descrição |
|--------|-------|-----------|
| `WIFI_SSID/PASS` | — | Rede de campo |
| `TCP_TARGET_HOST` | — | IP do notebook com tcp_sink.py |
| `TCP_BUF_SIZE` | 4096 | Buffer TCP (maior = throughput mais preciso) |
| `FLUSH_INTERVAL_MS` | 2000 | Flush forçado (ms) |
| `BROWNOUT_AUTO_STOP` | 1 | 1=STOP automático em brownout |
| `VIN_BROWNOUT_MV` | 10500 | Threshold brownout (mV) |
| `VIN_BROWNOUT_HYST` | 500 | Histerese reset flag (mV) |
| `BTN_STOP_HOLD_MS` | 1500 | Pressão longa para STOP (ms) |
| `FS_WARN_KB` | 128 | Flash livre mínimo para aviso |
| `PIN_VIN_ADC` | 34 | ADC divisor de tensão (-1 = desabilitado) |

### Tasks FreeRTOS (todas no core 1)

| Task | Stack | Prio | Função |
|------|-------|------|--------|
| `sup` | 2048 | 5 | supervision: V_IN, temp, link (1 Hz) |
| `profB` | 4096 | 3 | WALK/CLOCK ping |
| `profA` | 6144 | 3 | BURN janelas 15s |
| `log` | 4096 | 1 | flush ring buffer, fechar run em FLUSHING |

---

## Ferramentas Python

### parser.py

Pipeline: `ingest_file()` → `validate_run()` → `aggregate_*()` → `consolidate_*()` → `compute_scores()` → `render_report()`

- `compute_scores()` retorna `(scores_dict, eff_weights)` — TTR redistribuído se sem WALK
- Pesos default: PLR 30% / TTR 25% / RSSI 25% / Tput 20%
- Score 0–100 min-max normalizado
- Relatório HTML: banner vencedor, radar 5 eixos, heatmap, distribuição RSSI, time series

### Fluxo de campo

```bash
# 1. Antes de ir ao campo — gravar firmware com config.h correto

# 2. No notebook — deixar rodando (para BURN)
python tools/tcp_sink.py --port 5201

# 3. Celular abre http://<IP_ESP32>/ e controla os testes

# 4. Ao terminar
python tools/sync.py <IP_ESP32>          # baixa CSVs + roda parser
# ou acessar painel web → Baixar todos → logs.zip
```

---

## Próxima fase (futura)

Melhoria do firmware oficial Frotall em `c:/Users/Guilherme Bertanha/Downloads/frotall-firmware-3.15.0.debug/`

Problemas identificados: `std::string` em tasks FreeRTOS, sem validação de `xTaskCreate`/semáforos, race conditions no BLE.
Abordagem: branch separada, por módulo, um de cada vez.

---

## Dependência Arduino

- `ESP32Ping` (marian-craciunescu) ≥ 1.7 — instalar via Library Manager
- Arduino Core ESP32 3.x (Espressif) — `temperatureRead()` disponível nessa versão
