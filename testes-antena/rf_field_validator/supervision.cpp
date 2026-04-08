#include "supervision.h"
#include "config.h"
#include "csv_log.h"
#include "state_machine.h"
#include <WiFi.h>

// ── Estado ────────────────────────────────────────────────────
static volatile uint16_t _vin_mv = 0;
static volatile uint8_t  _link   = 0;

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

    for (;;) {
        vTaskDelayUntil(&last_wake, period);

        _vin_mv = _read_vin();
        _link   = (WiFi.status() == WL_CONNECTED) ? 1 : 0;

        if (_vin_mv > 0 && _vin_mv < VIN_BROWNOUT_MV && !brownout_flagged) {
            State s = sm_state();
            if (s == State::RUNNING_WALK  || s == State::RUNNING_CLOCK ||
                s == State::RUNNING_BURN  || s == State::RUNNING_BURN3) {
                csv_write_event("BROWNOUT_WARNING");
            }
            brownout_flagged = true;
        }
        if (_vin_mv >= VIN_BROWNOUT_MV) brownout_flagged = false;
    }
}

uint16_t sup_vin_mv()    { return _vin_mv; }
float    sup_temp_c()    { return 0.0f;    }  // não disponível no Arduino Core 3.x
uint8_t  sup_link_state(){ return _link;   }
