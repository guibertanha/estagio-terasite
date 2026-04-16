#include "profile_a.h"
#include "config.h"
#include "csv_log.h"
#include "state_machine.h"
#include "supervision.h"
#include "weblog.h"
#include <WiFi.h>
#include <WiFiClient.h>
#include <ESPping.h>
#include <esp_wifi.h>

#define PING_PHASE_MS    3000
#define TPUT_PHASE_MS   10000
#define COOL_PHASE_MS    2000
#define WINDOW_MS       (PING_PHASE_MS + TPUT_PHASE_MS + COOL_PHASE_MS)  // 15000

#define BLOCK_DURATION_MS  60000UL   // 60 s por bloco em 3x60

// ── RSSI via esp_wifi_sta_get_ap_info ────────────────────────
static int8_t _rssi() {
    wifi_ap_record_t info;
    if (esp_wifi_sta_get_ap_info(&info) == ESP_OK) return info.rssi;
    return -127;
}

// ── Fase de ping (3 s): coleta amostras, retorna PLR, RSSI P10 e latência média ──
struct PingStats { float plr; int8_t rssi_p10; uint32_t ok; uint32_t total; float lat_avg_ms; };

static PingStats _run_ping_phase() {
    IPAddress target;
#ifdef PING_TARGET
    target.fromString(PING_TARGET);
#else
    target = WiFi.gatewayIP();
#endif

    const int MAX_SAMPLES = 60;
    int8_t rssi_buf[MAX_SAMPLES];
    uint32_t ok = 0, total = 0;
    float lat_sum = 0.0f;
    uint32_t end = millis() + PING_PHASE_MS;

    while (millis() < end && total < (uint32_t)MAX_SAMPLES) {
        bool hit = Ping.ping(target, 1);
        if (hit) {
            ok++;
            lat_sum += Ping.averageTime();
        }
        rssi_buf[total] = _rssi();
        total++;
        vTaskDelay(pdMS_TO_TICKS(50));
    }

    // P10 do RSSI (ordena parcialmente via selection sort)
    uint32_t n = total;
    if (n > 1) {
        uint32_t p10_idx = n / 10;
        for (uint32_t i = 0; i <= p10_idx && i < n; i++) {
            uint32_t min_i = i;
            for (uint32_t j = i + 1; j < n; j++)
                if (rssi_buf[j] < rssi_buf[min_i]) min_i = j;
            int8_t tmp = rssi_buf[i]; rssi_buf[i] = rssi_buf[min_i]; rssi_buf[min_i] = tmp;
        }
    }

    PingStats s;
    s.ok         = ok;
    s.total      = total;
    s.plr        = total > 0 ? (float)(total - ok) / total * 100.0f : 100.0f;
    s.rssi_p10   = (n > 0) ? rssi_buf[n / 10] : -127;
    s.lat_avg_ms = (ok > 0) ? lat_sum / ok : 0.0f;
    return s;
}

// ── Fase de throughput TCP (10 s) ────────────────────────────
// Buffer estático — 4 KB no heap global, não na stack da task.
static uint8_t _tcp_buf[TCP_BUF_SIZE];

static uint32_t _run_tput_phase() {
    WiFiClient client;
    if (!client.connect(g_tcp_host, TCP_TARGET_PORT)) {
        // Servidor tcp_sink.py inacessível — degrada (tput=0), run continua normalmente
        weblog_printf("[BURN] tcp_sink %s:%d inacessível — tput=0, run continua\n",
                      g_tcp_host, TCP_TARGET_PORT);
        vTaskDelay(pdMS_TO_TICKS(TPUT_PHASE_MS));
        return 0;
    }

    memset(_tcp_buf, 0xAA, sizeof(_tcp_buf));

    uint32_t bytes_sent = 0;
    uint32_t end = millis() + TPUT_PHASE_MS;
    uint8_t  zero_streak = 0;   // writes consecutivos retornando 0 → TCP travado/morto

    while (millis() < end) {
        if (!client.connected() || WiFi.status() != WL_CONNECTED) {
            weblog_println("[BURN] link TCP perdido mid-stream — tput parcial");
            break;
        }
        size_t written = client.write(_tcp_buf, TCP_BUF_SIZE);
        if (written > 0) {
            bytes_sent += written;
            zero_streak = 0;
        } else {
            // 10 ciclos seguidos sem enviar → conexão travada silenciosamente
            if (++zero_streak >= 10) {
                weblog_println("[BURN] TCP sem progresso — encerrando fase tput");
                break;
            }
        }
        vTaskDelay(pdMS_TO_TICKS(1));
    }
    client.stop();

    // bps = bytes × 8 / 10 s — usa uint64_t para evitar overflow com buffers grandes
    return (uint32_t)((uint64_t)bytes_sent * 8 / 10);
}

// ── Uma janela completa de 15 s ───────────────────────────────
static CsvRow _run_window(uint32_t seq) {
    PingStats ps = _run_ping_phase();

    uint32_t tput = 0;
    if (WiFi.status() == WL_CONNECTED)
        tput = _run_tput_phase();

    // Cooldown: flush parcial + delay
    csv_flush_batch();
    vTaskDelay(pdMS_TO_TICKS(COOL_PHASE_MS));

    CsvRow r = csv_make_sample(ps.rssi_p10, ps.ok > 0 ? 1 : 0, ps.lat_avg_ms, seq,
                               tput, ps.plr);
    r.vin_mv     = sup_vin_mv();
    r.temp_c     = sup_temp_c();
    r.link_state = sup_link_state();
    return r;
}

// ── Task principal ────────────────────────────────────────────
void profile_a_task(void* param) {
    static uint32_t seq = 0;

    for (;;) {
        State st = sm_state();

        if (st != State::RUNNING_BURN && st != State::RUNNING_BURN3) {
            vTaskDelay(pdMS_TO_TICKS(100));
            seq = 0;
            continue;
        }

        if (WiFi.status() != WL_CONNECTED) {
            // supervision já emite LINK_DOWN/LINK_UP — só espera o tempo da janela
            vTaskDelay(pdMS_TO_TICKS(WINDOW_MS));
            continue;
        }

        // ── BURN simples (contínuo até STOP) ──────────────────
        if (st == State::RUNNING_BURN) {
            CsvRow r = _run_window(seq++);
            csv_ring_push(r);
            uint32_t n = ++sm_ctx()->samples;
            weblog_printf("[BURN] #%lu  RSSI %d dBm  tput %.1f Mbps  PLR %.1f%%\n",
                          (unsigned long)n, (int)r.rssi_dbm,
                          r.throughput_bps / 1e6f, r.plr_window);
            continue;
        }

        // ── BURN 3x60 ─────────────────────────────────────────
        if (st == State::RUNNING_BURN3) {
            RunContext* ctx = sm_ctx();
            CsvRow r = _run_window(seq++);
            csv_ring_push(r);
            ctx->samples++;
            weblog_printf("[BURN3] Bloco %u/3  #%lu  RSSI %d dBm  tput %.1f Mbps\n",
                          ctx->active_block, (unsigned long)ctx->samples,
                          (int)r.rssi_dbm, r.throughput_bps / 1e6f);

            uint32_t elapsed_block = millis() - ctx->block_start_ms;
            if (elapsed_block >= BLOCK_DURATION_MS) {
                ctx->blocks_done++;
                if (ctx->blocks_done >= 3) {
                    weblog_println("[BURN3] 3 blocos completos — encerrando...");
                    sm_finish_burn3();
                } else {
                    uint8_t next_block = ctx->blocks_done + 1;
                    csv_write_block_event(next_block);
                    weblog_printf("[BURN3] Bloco %u/3 iniciado\n", next_block);

                    // Feedback visual: pisca LED rapidamente entre blocos
                    for (int i = 0; i < 6; i++) {
                        digitalWrite(PIN_LED, i % 2);
                        vTaskDelay(pdMS_TO_TICKS(150));
                    }
                    ctx->block_start_ms = millis();
                }
            }
        }
    }
}
