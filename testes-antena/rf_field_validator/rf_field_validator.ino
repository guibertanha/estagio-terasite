/**
 * @file    rf_field_validator.ino
 * @brief   Firmware de validação RF de campo — Frotall FRITG01LTE
 * @version N3.0
 *
 * Fases: F0 (baseline), F1 (WALK), F2 (CLOCK), F3A/3B (BURN)
 * Perfil A: Stress Window 15s (ping 3s + throughput TCP 10s + cooldown 2s)
 * Perfil B: ping contínuo WALK (2Hz) / CLOCK (1Hz)
 *
 * CLI via Serial (115200):
 *   CONFIG <antena> <local> <condicao>
 *   START_WALK [--cold]
 *   START_CLOCK
 *   START_BURN
 *   START_BURN 3x60
 *   MARK <label>          (somente durante CLOCK)
 *   STOP
 *   STATUS
 *   EXPORT                (lista arquivos de log)
 *   EPOCH <unix_ts>       (ancoragem manual se sem NTP)
 *
 * Hardware: ESP32-WROOM-32, LittleFS, FreeRTOS nativo
 * Dependências Arduino: ESPping (instalar via Library Manager)
 */

#include <Arduino.h>
#include <WiFi.h>
#include <LittleFS.h>
#include <time.h>
#include <esp_wifi.h>

#include "config.h"
#include "state_machine.h"
#include "csv_log.h"
#include "supervision.h"
#include "profile_b.h"
#include "profile_a.h"
#include "web_ui.h"

// ── Task handles ─────────────────────────────────────────────
static TaskHandle_t _task_log    = nullptr;
static TaskHandle_t _task_profb  = nullptr;
static TaskHandle_t _task_profa  = nullptr;
static TaskHandle_t _task_sup    = nullptr;

// ── Buffer CLI ────────────────────────────────────────────────
#define CLI_BUF_SIZE 128
static char   _cli_buf[CLI_BUF_SIZE];
static uint8_t _cli_len = 0;

// ── NTP ───────────────────────────────────────────────────────
// g_epoch_anchored é definido em web_ui.cpp (extern em web_ui.h)
static void _try_ntp() {
    if (WiFi.status() != WL_CONNECTED) return;
    configTime(0, 0, "pool.ntp.org", "time.nist.gov");
    struct tm tm_info;
    uint32_t t0 = millis();
    while (!getLocalTime(&tm_info) && millis() - t0 < 5000)
        delay(200);
    if (getLocalTime(&tm_info)) {
        time_t now = mktime(&tm_info);
        csv_write_epoch_anchor((uint32_t)now);
        g_epoch_anchored = true;
        Serial.printf("[NTP] EPOCH_ANCHOR=%lu\n", (unsigned long)now);
    }
}

// ── Task de log (prioridade baixa) ───────────────────────────
static void _task_log_fn(void* p) {
    for (;;) {
        State st = sm_state();

        // Flush por lote quando atingir FLUSH_BATCH
        if ((st == State::RUNNING_WALK  || st == State::RUNNING_CLOCK ||
             st == State::RUNNING_BURN  || st == State::RUNNING_BURN3) &&
            csv_ring_count() >= FLUSH_BATCH) {
            csv_flush_batch();
        }

        // Flush forçado por tempo (FLUSH_INTERVAL_MS — agora 2 s)
        static uint32_t last_timed = 0;
        if (millis() - last_timed >= FLUSH_INTERVAL_MS) {
            if (csv_ring_count() > 0) csv_flush_batch();
            last_timed = millis();
        }

        // FLUSHING: fechar run e voltar para READY
        if (st == State::FLUSHING) {
            csv_close_run(false);
            RunContext* ctx = sm_ctx();
            sm_cmd_config(ctx->antenna, ctx->location, ctx->condition);
            Serial.println("[OK] Run encerrado. READY para novo START_*");
            if (g_flush_incomplete) {
                Serial.println("[WARN] FLUSH_INCOMPLETE — verifique o CSV");
            }
            digitalWrite(PIN_LED, LOW);
        }

        vTaskDelay(pdMS_TO_TICKS(50));
    }
}

// ── Parsing de comandos CLI ───────────────────────────────────
static void _process_cli(const char* line) {
    static char buf[CLI_BUF_SIZE];
    strncpy(buf, line, sizeof(buf)-1);
    buf[sizeof(buf)-1] = '\0';

    char* tok = strtok(buf, " \t\r\n");
    if (!tok) return;

    // ── CONFIG ───────────────────────────────────────────────
    if (strcasecmp(tok, "CONFIG") == 0) {
        char* ant = strtok(nullptr, " \t\r\n");
        char* loc = strtok(nullptr, " \t\r\n");
        char* cnd = strtok(nullptr, " \t\r\n");
        if (!ant || !loc || !cnd) {
            Serial.println("[ERR] Uso: CONFIG <antena> <local> <condicao>");
            return;
        }
        const char* err = sm_cmd_config(ant, loc, cnd);
        if (err) Serial.printf("[ERR] %s\n", err);
        else     Serial.printf("[OK] CONFIG aceito: %s %s %s\n", ant, loc, cnd);
        return;
    }

    // ── START_WALK ────────────────────────────────────────────
    if (strcasecmp(tok, "START_WALK") == 0) {
        char* flag = strtok(nullptr, " \t\r\n");
        bool cold = (flag && strcasecmp(flag, "--cold") == 0);
        const char* err = sm_cmd_start_walk(cold);
        if (err) Serial.printf("[ERR] %s\n", err);
        else {
            if (!g_epoch_anchored) _try_ntp();
            digitalWrite(PIN_LED, HIGH);
            Serial.printf("[OK] START_WALK%s — arquivo: %s\n",
                          cold ? " (cold)" : "",
                          csv_current_filename().c_str());
        }
        return;
    }

    // ── START_CLOCK ───────────────────────────────────────────
    if (strcasecmp(tok, "START_CLOCK") == 0) {
        const char* err = sm_cmd_start_clock();
        if (err) Serial.printf("[ERR] %s\n", err);
        else {
            if (!g_epoch_anchored) _try_ntp();
            digitalWrite(PIN_LED, HIGH);
            Serial.printf("[OK] START_CLOCK — arquivo: %s\n",
                          csv_current_filename().c_str());
        }
        return;
    }

    // ── START_BURN ────────────────────────────────────────────
    if (strcasecmp(tok, "START_BURN") == 0) {
        char* flag = strtok(nullptr, " \t\r\n");
        bool three = (flag && strcasecmp(flag, "3x60") == 0);
        const char* err = sm_cmd_start_burn(three);
        if (err) Serial.printf("[ERR] %s\n", err);
        else {
            if (!g_epoch_anchored) _try_ntp();
            digitalWrite(PIN_LED, HIGH);
            Serial.printf("[OK] START_BURN%s — arquivo: %s\n",
                          three ? " 3x60" : "",
                          csv_current_filename().c_str());
        }
        return;
    }

    // ── MARK ──────────────────────────────────────────────────
    if (strcasecmp(tok, "MARK") == 0) {
        char* label = strtok(nullptr, " \t\r\n");
        if (!label) { Serial.println("[ERR] Uso: MARK <label>"); return; }
        const char* err = sm_cmd_mark(label);
        if (err) Serial.printf("[ERR] %s\n", err);
        else     Serial.printf("[OK] MARK=%s\n", label);
        return;
    }

    // ── STOP ──────────────────────────────────────────────────
    if (strcasecmp(tok, "STOP") == 0) {
        const char* err = sm_cmd_stop();
        if (err) Serial.printf("[ERR] %s\n", err);
        else     Serial.println("[OK] Flush em andamento...");
        return;
    }

    // ── STATUS ────────────────────────────────────────────────
    if (strcasecmp(tok, "STATUS") == 0) {
        const char* state_str[] = {
            "IDLE","READY","RUNNING_WALK","RUNNING_CLOCK",
            "RUNNING_BURN","RUNNING_BURN3","FLUSHING"
        };
        State st  = sm_state();
        RunContext* ctx = sm_ctx();

        wifi_ap_record_t ap_info;
        int8_t rssi = -127;
        if (esp_wifi_sta_get_ap_info(&ap_info) == ESP_OK) rssi = ap_info.rssi;

        Serial.printf("Estado     : %s\n", state_str[(int)st]);
        Serial.printf("CONFIG     : ant=%s loc=%s cond=%s\n",
                      ctx->antenna, ctx->location, ctx->condition);
        Serial.printf("Run #      : R%02u | amostras=%lu\n",
                      ctx->run_number, (unsigned long)ctx->samples);
        Serial.printf("Uptime     : %lu s\n", millis() / 1000);
        Serial.printf("RSSI link  : %d dBm\n", (int)rssi);
        Serial.printf("Temperatura: %.1f C\n", sup_temp_c());
        Serial.printf("V_IN       : %u mV\n", sup_vin_mv());
        Serial.printf("Flash livre: %lu KB\n", (unsigned long)csv_free_kb());
        Serial.printf("Ring buffer: %u linhas pendentes\n", csv_ring_count());
        Serial.printf("EPOCH NTP  : %s\n", g_epoch_anchored ? "ok" : "nao ancorado");
        Serial.printf("WiFi       : %s\n", WiFi.status() == WL_CONNECTED ? "conectado" : "desconectado");
        if (g_flush_incomplete)
            Serial.println("[WARN] FLUSH_INCOMPLETE no ultimo run");
        if (st != State::IDLE && st != State::READY)
            Serial.printf("Arquivo    : %s\n", csv_current_filename().c_str());
        return;
    }

    // ── EXPORT ────────────────────────────────────────────────
    if (strcasecmp(tok, "EXPORT") == 0) {
        File root = LittleFS.open(FS_BASE_PATH);
        if (!root || !root.isDirectory()) {
            Serial.println("[INFO] Nenhum log encontrado.");
            return;
        }
        Serial.println("[LOGS]");
        File f = root.openNextFile();
        while (f) {
            Serial.printf("  %s  (%lu bytes)\n", f.name(), (unsigned long)f.size());
            f = root.openNextFile();
        }
        return;
    }

    // ── EPOCH <unix_ts> ───────────────────────────────────────
    if (strcasecmp(tok, "EPOCH") == 0) {
        char* ts_str = strtok(nullptr, " \t\r\n");
        if (!ts_str) { Serial.println("[ERR] Uso: EPOCH <unix_timestamp>"); return; }
        uint32_t ts = (uint32_t)strtoul(ts_str, nullptr, 10);
        csv_write_epoch_anchor(ts);
        g_epoch_anchored = true;
        Serial.printf("[OK] EPOCH_ANCHOR=%lu (manual)\n", (unsigned long)ts);
        return;
    }

    Serial.printf("[ERR] Comando desconhecido: %s\n", tok);
}

// ── Leitura incremental do Serial ────────────────────────────
static void _cli_poll() {
    while (Serial.available()) {
        char c = (char)Serial.read();
        if (c == '\r') continue;
        if (c == '\n') {
            _cli_buf[_cli_len] = '\0';
            if (_cli_len > 0) _process_cli(_cli_buf);
            _cli_len = 0;
        } else if (_cli_len < CLI_BUF_SIZE - 1) {
            _cli_buf[_cli_len++] = c;
        }
    }
}

// ── LED de heartbeat ─────────────────────────────────────────
// IDLE/READY: pisca lento (1 Hz)
// FLUSHING:   pisca médio (4 Hz) — indica atividade de escrita
// RUNNING_*:  LED controlado pela task de perfil (fica aceso)
static void _led_heartbeat() {
    static uint32_t last_blink = 0;
    static bool led_on = false;
    State st = sm_state();

    uint32_t period;
    if (st == State::FLUSHING)
        period = 250;
    else if (st == State::IDLE || st == State::READY)
        period = 1000;
    else
        return;  // RUNNING_*: LED gerenciado pelo start (fica HIGH)

    if (millis() - last_blink >= period) {
        led_on = !led_on;
        digitalWrite(PIN_LED, led_on ? HIGH : LOW);
        last_blink = millis();
    }
}

// ── setup() ──────────────────────────────────────────────────
void setup() {
    Serial.begin(115200);
    delay(500);

    pinMode(PIN_LED, OUTPUT);
    digitalWrite(PIN_LED, LOW);

    Serial.println("\n\n╔══════════════════════════════════════════╗");
    Serial.println("║  RF Field Validator  N3.0                ║");
    Serial.println("║  Frotall FRITG01LTE  — Terasite 2026     ║");
    Serial.println("╚══════════════════════════════════════════╝");
    Serial.println("Comandos: CONFIG | START_WALK | START_CLOCK | START_BURN | MARK | STOP | STATUS | EXPORT | EPOCH");

    // ── LittleFS ─────────────────────────────────────────────
    if (!LittleFS.begin(true)) {
        Serial.println("[FATAL] LittleFS falhou. Verifique particao.");
        while (true) delay(1000);
    }
    Serial.printf("[FS] LittleFS ok. Livre: %lu KB\n", (unsigned long)csv_free_kb());
    if (csv_free_kb() < FS_WARN_KB) {
        Serial.printf("[WARN] Flash baixo: %lu KB (limite de aviso: %d KB)\n",
                      (unsigned long)csv_free_kb(), FS_WARN_KB);
    }

    // ── Wi-Fi (STA, reconexão automática habilitada) ──────────
    WiFi.mode(WIFI_STA);
    WiFi.setAutoReconnect(true);
    WiFi.begin(WIFI_SSID, WIFI_PASS);
    Serial.printf("[WiFi] Conectando a %s...\n", WIFI_SSID);
    uint32_t wt = millis();
    while (WiFi.status() != WL_CONNECTED && millis() - wt < WIFI_TIMEOUT_MS) {
        delay(250);
        Serial.print(".");
    }
    Serial.println();
    if (WiFi.status() == WL_CONNECTED) {
        Serial.printf("[WiFi] OK. IP=%s RSSI=%d dBm\n",
                      WiFi.localIP().toString().c_str(), WiFi.RSSI());
        _try_ntp();
    } else {
        Serial.println("[WiFi] Sem conexao no boot. Tentando reconectar em background...");
        Serial.println("       Use START_WALK --cold para operar sem WiFi.");
    }

    // ── Ring buffer + state machine ───────────────────────────
    csv_ring_init();
    sm_init();
    supervision_init();

    // ── Interface Web (só se WiFi disponível no boot) ─────────
    if (WiFi.status() == WL_CONNECTED) {
        web_ui_init();
    } else {
        Serial.println("[Web] Painel indisponivel — sera iniciado ao reconectar.");
    }

    // ── Tasks FreeRTOS ────────────────────────────────────────
    xTaskCreatePinnedToCore(supervision_task, "sup",  2048, nullptr, 5, &_task_sup,   1);
    xTaskCreatePinnedToCore(profile_b_task,   "profB", 4096, nullptr, 3, &_task_profb, 1);
    xTaskCreatePinnedToCore(profile_a_task,   "profA", 6144, nullptr, 3, &_task_profa, 1);
    xTaskCreatePinnedToCore(_task_log_fn,     "log",   4096, nullptr, 1, &_task_log,   1);

    Serial.println("[OK] Tasks iniciadas. IDLE — aguardando CONFIG.");
}

// ── loop() — CLI, web server, heartbeat e reconexão WiFi ─────
void loop() {
    _cli_poll();

    // Inicia o painel web assim que o WiFi conectar (caso tenha falhado no boot)
    web_ui_try_init();

    // Se WiFi reconectou e NTP ainda não foi ancorado, tenta agora
    static bool _ntp_pending = false;
    if (!g_epoch_anchored && WiFi.status() == WL_CONNECTED) {
        if (!_ntp_pending) {
            _ntp_pending = true;  // evita tentar em cada ciclo do loop
            _try_ntp();
            _ntp_pending = false;
        }
    }

    web_ui_handle();
    _led_heartbeat();
    delay(5);
}
