#pragma once
// ============================================================
//  config.h — Parâmetros ajustáveis da bancada
//  Edite antes de gravar. Não altere outros arquivos para
//  mudar rede ou pinos.
// ============================================================

// ── Wi-Fi ────────────────────────────────────────────────────
#define WIFI_SSID       "YOUR_WIFI_SSID"
#define WIFI_PASS       "YOUR_WIFI_PASS"
#define WIFI_TIMEOUT_MS  15000

// ── Alvo TCP para throughput (Perfil A) ──────────────────────
// Rodar no notebook: python tools/tcp_sink.py
#define TCP_TARGET_HOST  "192.168.x.x"   // IP do notebook na rede de casa
#define TCP_TARGET_PORT  5201
#define TCP_BUF_SIZE     1024             // bytes por write

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
#define VIN_BROWNOUT_MV  10500    // abaixo disso → BROWNOUT_WARNING
#define SUPERVISION_HZ   1        // frequência da task de supervisão

// ── LittleFS ─────────────────────────────────────────────────
#define FS_BASE_PATH     "/logs"
#define FS_FREE_MIN_KB   64       // recusar run se espaço < isso

// ── Ring buffer ──────────────────────────────────────────────
#define RING_BUF_SLOTS   64       // número de linhas CSV em RAM
#define FLUSH_BATCH      16       // linhas por flush
#define FLUSH_INTERVAL_MS 8000    // flush forçado a cada N ms

// ── Interface Web + Botão físico ─────────────────────────────
// Acesse http://<IP-do-ESP32>/ do celular (mesma rede Wi-Fi)
#define WEB_UI_PORT      80
// GPIO do botão físico: READY→START_WALK, RUNNING_*→STOP
// Use 0 (botão BOOT do devkit) ou -1 para desabilitar
#define PIN_BUTTON       0

// ── Guardrails ───────────────────────────────────────────────
#define MAX_RUNS_PER_FILE 99
#define MARKER_MAX_LEN   8
