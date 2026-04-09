#include "supervision.h"
#include "config.h"
#include "csv_log.h"
#include "state_machine.h"
#include <WiFi.h>

// ── Estado ────────────────────────────────────────────────────
static volatile uint16_t _vin_mv    = 0;
static volatile float    _temp_c    = 0.0f;
static volatile uint8_t  _link      = 0;

// ── Leitura de tensão via ADC ─────────────────────────────────
static uint16_t _read_vin() {
#if PIN_VIN_ADC > 0
    uint32_t raw = analogReadMilliVolts(PIN_VIN_ADC);
    return (uint16_t)(raw * VIN_DIV_RATIO);
#else
    return 0;
#endif
}

void supervision_init() { /* nada */ }

void supervision_task(void* param) {
    const TickType_t period = pdMS_TO_TICKS(1000 / SUPERVISION_HZ);
    TickType_t last_wake    = xTaskGetTickCount();
    bool brownout_flagged   = false;
    bool link_was_up        = false;  // rastreia transição de link

    for (;;) {
        vTaskDelayUntil(&last_wake, period);

        _vin_mv = _read_vin();
        _link   = (WiFi.status() == WL_CONNECTED) ? 1 : 0;

        // ── Temperatura interna ──────────────────────────────
        // temperatureRead() disponível no Arduino Core ESP32 3.x
        _temp_c = temperatureRead();

        // ── Detecção de transição de link (LINK_DOWN / LINK_UP) ──
        // Emitir evento apenas na borda de transição, não a cada ciclo.
        // Os profiles não precisam mais rastrear individualmente.
        {
            bool link_now = (_link == 1);
            State s = sm_state();
            bool running = (s == State::RUNNING_WALK  || s == State::RUNNING_CLOCK ||
                            s == State::RUNNING_BURN  || s == State::RUNNING_BURN3);
            if (running) {
                if (link_was_up && !link_now) {
                    csv_write_event("LINK_DOWN");
                } else if (!link_was_up && link_now) {
                    csv_write_event("LINK_UP");
                }
            }
            link_was_up = link_now;
        }

        // ── Supervisão de brownout ───────────────────────────
        if (_vin_mv > 0 && _vin_mv < VIN_BROWNOUT_MV && !brownout_flagged) {
            State s = sm_state();
            bool running = (s == State::RUNNING_WALK  || s == State::RUNNING_CLOCK ||
                            s == State::RUNNING_BURN  || s == State::RUNNING_BURN3);
            if (running) {
                csv_write_event("BROWNOUT_WARNING");
#if BROWNOUT_AUTO_STOP
                // Aciona STOP seguro: a task de log faz o flush e encerra o arquivo
                sm_cmd_stop();
                Serial.println("[SUP] BROWNOUT — STOP automatico acionado");
#endif
            }
            brownout_flagged = true;
        }
        // Histerese: só reseta o flag quando tensão subir o suficiente
        if (_vin_mv >= VIN_BROWNOUT_MV + VIN_BROWNOUT_HYST) {
            brownout_flagged = false;
        }
    }
}

uint16_t sup_vin_mv()    { return _vin_mv;  }
float    sup_temp_c()    { return _temp_c;  }
uint8_t  sup_link_state(){ return _link;    }
