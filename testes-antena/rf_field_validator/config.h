#pragma once
// ============================================================
//  config.h — Parâmetros ajustáveis da bancada
//  Spec N3.0 — Terasite 2026
//  Edite antes de gravar. Não altere outros arquivos para
//  mudar rede ou pinos.
// ============================================================

// ── Wi-Fi ────────────────────────────────────────────────────
#define WIFI_SSID       "YOUR_WIFI_SSID"
#define WIFI_PASS       "YOUR_WIFI_PASS"
#define WIFI_TIMEOUT_MS  15000

// ── Alvo TCP para throughput (Perfil A) ──────────────────────
// Rodar no notebook: python tools/tcp_sink.py
// No campo: verifique o IP do notebook com `ipconfig` (Windows) ou `ip a` (Linux).
// Cenário típico: notebook no Hotspot do celular, ESP32 a 3-10 m da máquina.
// Use watch.py para gerenciar o tcp_sink automaticamente durante a sessão.
#define TCP_TARGET_HOST  "192.168.x.x"   // << ALTERAR antes de ir ao campo
#define TCP_TARGET_PORT  5201
#define TCP_BUF_SIZE     4096             // bytes por write (maior = throughput mais preciso)

// ── Alvo ping (Perfil B) ─────────────────────────────────────
// Deixe comentado para usar o gateway Wi-Fi automaticamente.
// Descomente e preencha para forçar um IP específico:
// #define PING_TARGET  "192.168.x.x"

// ── Hardware ─────────────────────────────────────────────────
#define PIN_LED          2        // LED interno (active high)
#define PIN_VIN_ADC      34       // Divisor de tensão (0 = desabilitado)
#define VIN_DIV_RATIO    11.0f    // (R1+R2)/R2 do divisor
#define VIN_ADC_REF_MV   3300     // tensão de referência ADC em mV

// ── Limiares de supervisão ───────────────────────────────────
#define VIN_BROWNOUT_MV    10500  // abaixo disso → BROWNOUT_WARNING
#define VIN_BROWNOUT_HYST    500  // histerese para reset do flag (mV)
#define SUPERVISION_HZ       1    // frequência da task de supervisão

// Acionar STOP automático quando tensão cair abaixo de VIN_BROWNOUT_MV.
// O run é encerrado com segurança (flush completo) antes de uma possível queda.
// Defina como 0 para apenas logar o warning sem parar o run.
#define BROWNOUT_AUTO_STOP   1

// ── LittleFS ─────────────────────────────────────────────────
#define FS_BASE_PATH     "/logs"
#define FS_FREE_MIN_KB   64       // recusar run se espaço < isso
#define FS_WARN_KB       128      // alerta visual no painel quando flash < isso

// ── Ring buffer ──────────────────────────────────────────────
#define RING_BUF_SLOTS   64       // número de linhas CSV em RAM
#define FLUSH_BATCH      16       // linhas por flush
#define FLUSH_INTERVAL_MS 2000    // flush forçado a cada N ms (era 8000)

// ── Interface Web + Botão físico ─────────────────────────────
// Acesse http://<IP-do-ESP32>/ do celular (mesma rede Wi-Fi)
#define WEB_UI_PORT      80
// GPIO do botão físico: READY → START_WALK (toque curto)
//                       RUNNING_* → STOP (segurar >= BTN_STOP_HOLD_MS)
// Use 0 (botão BOOT do devkit) ou -1 para desabilitar
#define PIN_BUTTON         0
#define BTN_STOP_HOLD_MS   1500   // ms de pressão necessários para acionar STOP

// ── Guardrails ───────────────────────────────────────────────
#define MAX_RUNS_PER_FILE 99
#define MARKER_MAX_LEN   8
