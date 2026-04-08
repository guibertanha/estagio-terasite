#include "profile_b.h"
#include "config.h"
#include "csv_log.h"
#include "state_machine.h"
#include "supervision.h"
#include <WiFi.h>
#include <ESPping.h>

// ── Resolve alvo de ping ──────────────────────────────────────
static IPAddress _ping_target() {
#ifdef PING_TARGET
    IPAddress ip;
    ip.fromString(PING_TARGET);
    return ip;
#else
    return WiFi.gatewayIP();
#endif
}

// ── RSSI via esp_wifi_sta_get_ap_info (igual ao firmware prod) ─
static int8_t _rssi() {
    wifi_ap_record_t info;
    if (esp_wifi_sta_get_ap_info(&info) == ESP_OK) return info.rssi;
    return -127;
}

// ── Preenche campos de supervisão na row ──────────────────────
static void _fill_sup(CsvRow& r) {
    r.vin_mv     = sup_vin_mv();
    r.temp_c     = sup_temp_c();
    r.link_state = sup_link_state();
}

void profile_b_task(void* param) {
    static uint32_t seq = 0;

    for (;;) {
        State st = sm_state();

        if (st != State::RUNNING_WALK && st != State::RUNNING_CLOCK) {
            vTaskDelay(pdMS_TO_TICKS(100));
            seq = 0;
            continue;
        }

        // Frequência: WALK=2Hz (500ms) | CLOCK=1Hz (1000ms)
        uint32_t period_ms = (st == State::RUNNING_WALK) ? 500 : 1000;
        uint32_t t0 = millis();

        // Wi-Fi desconectado durante run
        if (WiFi.status() != WL_CONNECTED) {
            // cold start permite continuar sem Wi-Fi (só para WALK)
            if (!sm_ctx()->cold_start) {
                // emite evento de link caído e continua (não cancela o run)
                csv_write_event("LINK_DOWN");
            }
            CsvRow r = csv_make_sample(-127, 0, 0.0f, seq++);
            _fill_sup(r);
            csv_ring_push(r);
            vTaskDelay(pdMS_TO_TICKS(period_ms));
            continue;
        }

        IPAddress target = _ping_target();
        bool ok = Ping.ping(target, 1);
        float lat = ok ? Ping.averageTime() : 0.0f;

        CsvRow r = csv_make_sample(_rssi(), ok ? 1 : 0, lat, seq++);
        _fill_sup(r);
        csv_ring_push(r);
        sm_ctx()->samples++;

        // Respeita período exato
        uint32_t elapsed = millis() - t0;
        if (elapsed < period_ms)
            vTaskDelay(pdMS_TO_TICKS(period_ms - elapsed));
    }
}
