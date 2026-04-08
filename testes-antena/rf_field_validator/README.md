# rf_field_validator — Firmware de Validação RF de Campo

**Spec:** N2.1 | **Target:** ESP32-WROOM-32 | **IDE:** Arduino

Firmware completo para campanha de validação de antenas Wi-Fi em
máquinas pesadas de construção civil. Implementa:

- **Perfil A (Stress):** janelas de 15 s — ping 3 s + throughput TCP 10 s + cooldown 2 s
- **Perfil B (Control):** ping contínuo WALK 2 Hz / CLOCK 1 Hz
- **CLI serial** com máquina de estados e guardrails spec N2.1
- **LittleFS** com ring buffer, flush em lote e CRC16 por linha
- **3 FreeRTOS tasks** (supervisão · medição · log)
- **Parser offline** Python + relatório HTML

---

## Dependências Arduino

Instalar via **Library Manager** (Sketch → Include Library → Manage Libraries):

| Biblioteca | Versão testada |
|---|---|
| `ESP32Ping` (ESP32Ping by marian-craciunescu) | ≥ 1.7 |

O restante usa o ESP32 Arduino Core padrão (LittleFS, FreeRTOS, WiFi, Preferences, time.h).

---

## Estrutura de arquivos

```
rf_field_validator/
├── rf_field_validator.ino   ← setup() + loop() + CLI
├── config.h                 ← credenciais Wi-Fi, pinos, limiares
├── state_machine.h/.cpp     ← estados e transições
├── csv_log.h/.cpp           ← formato CSV, ring buffer, flush
├── profile_b.h/.cpp         ← WALK / CLOCK
├── profile_a.h/.cpp         ← BURN / BURN 3x60
├── supervision.h/.cpp       ← V_IN, temperatura, link_state
└── tools/
    ├── parser.py            ← pipeline offline Python
    ├── tcp_sink.py          ← servidor TCP para throughput
    └── campaign_template.csv
```

---

## Como usar

### 1. Configurar antes de gravar

Edite `config.h`:
```cpp
#define WIFI_SSID  "MinhaRede"
#define WIFI_PASS  "SenhaAqui"
#define TCP_TARGET_HOST  "192.168.1.100"  // IP do notebook com tcp_sink.py
```

### 2. Gravar no ESP32

Abrir a pasta `rf_field_validator/` no Arduino IDE, selecionar
**ESP32 Dev Module** e fazer upload.

### 3. CLI (Serial Monitor 115200)

```
CONFIG A4 TETO OFF          # obrigatório antes de qualquer START
STATUS                      # mostra estado, RSSI, espaço livre

START_WALK                  # Fase 1, Perfil B 2 Hz
START_WALK --cold           # Fase 1, sem Wi-Fi (RSSI=-127)
START_CLOCK                 # Fase 2, Perfil B 1 Hz
  MARK NORTE                # marcador de ponto angular (só durante CLOCK)
  MARK SUL
STOP

START_BURN                  # Fases 0/3A, Perfil A, contínuo
START_BURN 3x60             # Fase 3B, 3 blocos de 60 s automático
STOP

EXPORT                      # lista arquivos de log na flash
EPOCH 1712534400            # ancoragem manual se NTP indisponível
```

### 4. Servidor de throughput (notebook)

Rodar **antes** de qualquer `START_BURN`:
```bash
python tools/tcp_sink.py --port 5201
```

### 5. Exportar logs

No Serial Monitor, digitar `EXPORT` para ver os arquivos.
Para baixar: usar **esptool** ou um sketch auxiliar de leitura serial.

Alternativamente, conectar via Wi-Fi e usar o webserver do módulo
(se o firmware de produção estiver ativo).

---

## Estrutura de campanha esperada pelo parser

```
campanha_xxx/
├── logs/           ← CSVs gerados pelo firmware
│   ├── WALK_A4_TETO_OFF_R01.csv
│   ├── CLOCK_A4_TETO_OFF_R01.csv
│   └── BURN_A4_TETO_ON_R01.csv
├── sa6/            ← capturas do analisador de espectro SA6 (opcional)
├── photos/         ← fotos de instalação
├── campaign.csv    ← metadados manuais (copiar de tools/campaign_template.csv)
└── report/         ← gerado pelo parser
```

### Rodar o parser

```bash
pip install pandas numpy   # opcional, ativa modo avançado
python tools/parser.py campanha_xxx/

# Pesos customizados:
python tools/parser.py campanha_xxx/ --weights plr=0.35,ttr=0.25,rssi=0.25,tput=0.15
```

Saída: `campanha_xxx/report/report.html` + `summary.csv`

---

## Formato CSV (N2.1)

Colunas fixas + campo `crc16` ao final de cada linha:

```
timestamp_ms, type, profile, phase, antenna, location, condition, run_id,
rssi_dbm, ping_ok, ping_latency_ms, ping_seq,
throughput_bps, plr_window,
vin_mv, temp_c, link_state, boot_count, uptime_ms,
marker, block, notes, crc16
```

| type | Significado |
|---|---|
| `S` | Amostra de medição |
| `E` | Evento (START_RUN, END_RUN, EPOCH_ANCHOR, BROWNOUT_WARNING…) |
| `M` | Marcador do operador |
| `B` | Transição de bloco BURN 3x60 |

Nome de arquivo: `[MODO]_[ANTENA]_[LOCAL]_[COND]_R[NN].csv`

---

## Guardrails implementados

| Regra | Implementação |
|---|---|
| CONFIG antes de START | `sm_cmd_start_*` retorna erro se estado != READY |
| Run duplo proibido | Estado RUNNING_* bloqueia novo START |
| Wi-Fi obrigatório | Verificado antes de START (exceto `--cold`) |
| MARK só em CLOCK | `sm_cmd_mark` verifica estado |
| boot_count persistente | NVS via `Preferences` |
| Flush incompleto | Evento `FLUSH_INCOMPLETE` no CSV se ring buffer não esvaziar em 5 s |
| Reboot detectado | boot_count incrementado na NVS a cada boot; parser detecta mudança |

---

## Limitações conhecidas

- `V_IN` requer divisor resistivo externo em `PIN_VIN_ADC` (34). Sem o hardware → `vin_mv=0`.
- Temperatura interna do ESP32 (`temprature_sens_read`) é aproximada (±5 °C).
- Throughput TCP depende do `tcp_sink.py` rodando no notebook. Sem ele → `throughput_bps=0`.
- Exportação de logs via Serial é lenta para arquivos grandes (>100 KB). Para campo: usar script de dump via UART ou adaptar para HTTP GET.
