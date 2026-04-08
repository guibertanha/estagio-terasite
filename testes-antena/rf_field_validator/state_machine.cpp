#include "state_machine.h"
#include "config.h"
#include "csv_log.h"
#include <Preferences.h>

// ── Estado global ─────────────────────────────────────────────
static State     _state = State::IDLE;
static RunContext _ctx   = {};
static Preferences _prefs;

// ── boot_count persistente via NVS ───────────────────────────
static uint32_t _load_boot_count() {
    _prefs.begin("rfval", false);
    uint32_t bc = _prefs.getUInt("boot_count", 0) + 1;
    _prefs.putUInt("boot_count", bc);
    _prefs.end();
    return bc;
}

static uint8_t _load_run_number(const char* key) {
    _prefs.begin("rfval", false);
    uint8_t rn = _prefs.getUChar(key, 0) + 1;
    if (rn > MAX_RUNS_PER_FILE) rn = 1;
    _prefs.putUChar(key, rn);
    _prefs.end();
    return rn;
}

// ── Helpers de validação ─────────────────────────────────────
static bool _valid_id(const char* s, uint8_t maxlen) {
    if (!s || strlen(s) == 0 || strlen(s) > maxlen) return false;
    for (const char* p = s; *p; p++) {
        if (!isalnum(*p) && *p != '_') return false;
    }
    return true;
}

static bool _wifi_up() {
    return WiFi.status() == WL_CONNECTED;
}

// ── API ───────────────────────────────────────────────────────
void sm_init() {
    _state = State::IDLE;
    memset(&_ctx, 0, sizeof(_ctx));
    _ctx.boot_count = _load_boot_count();
}

State sm_state()      { return _state; }
RunContext* sm_ctx()  { return &_ctx; }

// CONFIG <antena> <local> <condicao>
const char* sm_cmd_config(const char* antenna, const char* location, const char* condition) {
    if (_state == State::RUNNING_WALK  ||
        _state == State::RUNNING_CLOCK ||
        _state == State::RUNNING_BURN  ||
        _state == State::RUNNING_BURN3 ||
        _state == State::FLUSHING)
        return "ERR_RUN_ACTIVE: pare o run antes de reconfigurar";

    if (!_valid_id(antenna,  3)) return "ERR_INVALID: antena deve ser alfanum, max 3 chars (ex: A4)";
    if (!_valid_id(location, 5)) return "ERR_INVALID: local deve ser alfanum, max 5 chars (ex: TETO)";
    if (!_valid_id(condition,3)) return "ERR_INVALID: condicao deve ser alfanum, max 3 chars (ex: OFF)";

    strncpy(_ctx.antenna,   antenna,   sizeof(_ctx.antenna)   - 1);
    strncpy(_ctx.location,  location,  sizeof(_ctx.location)  - 1);
    strncpy(_ctx.condition, condition, sizeof(_ctx.condition) - 1);
    _ctx.antenna[sizeof(_ctx.antenna)-1]   = '\0';
    _ctx.location[sizeof(_ctx.location)-1] = '\0';
    _ctx.condition[sizeof(_ctx.condition)-1] = '\0';

    _state = State::READY;
    return nullptr; // sucesso
}

// START_WALK [--cold]
const char* sm_cmd_start_walk(bool cold) {
    if (_state != State::READY)
        return "ERR_NOT_READY: execute CONFIG primeiro";
    if (_state == State::RUNNING_WALK ||
        _state == State::RUNNING_CLOCK ||
        _state == State::RUNNING_BURN  ||
        _state == State::RUNNING_BURN3)
        return "ERR_RUN_ACTIVE: já há um run em andamento";
    if (!cold && !_wifi_up())
        return "ERR_NO_WIFI: sem Wi-Fi. Use START_WALK --cold para ignorar";

    _ctx.mode       = RunMode::WALK;
    _ctx.cold_start = cold;
    _ctx.samples    = 0;
    _ctx.active_block  = 0;
    _ctx.active_marker[0] = '\0';
    _ctx.start_ms   = millis();

    // gera run_number único por cenário
    char key[20];
    snprintf(key, sizeof(key), "rn_%s_%s_%s",
             _ctx.antenna, _ctx.location, _ctx.condition);
    _ctx.run_number = _load_run_number(key);

    csv_open_run();  // cria arquivo, grava header + E START_RUN

    _state = State::RUNNING_WALK;
    return nullptr;
}

// START_CLOCK
const char* sm_cmd_start_clock() {
    if (_state != State::READY)
        return "ERR_NOT_READY: execute CONFIG primeiro";
    if (_state == State::RUNNING_WALK ||
        _state == State::RUNNING_CLOCK ||
        _state == State::RUNNING_BURN  ||
        _state == State::RUNNING_BURN3)
        return "ERR_RUN_ACTIVE: já há um run em andamento";
    if (!_wifi_up())
        return "ERR_NO_WIFI: Wi-Fi necessário para CLOCK";

    _ctx.mode      = RunMode::CLOCK;
    _ctx.cold_start = false;
    _ctx.samples   = 0;
    _ctx.active_block  = 0;
    _ctx.active_marker[0] = '\0';
    _ctx.start_ms  = millis();

    char key[20];
    snprintf(key, sizeof(key), "rn_%s_%s_%s",
             _ctx.antenna, _ctx.location, _ctx.condition);
    _ctx.run_number = _load_run_number(key);

    csv_open_run();

    _state = State::RUNNING_CLOCK;
    return nullptr;
}

// START_BURN [3x60]
const char* sm_cmd_start_burn(bool three_blocks) {
    if (_state != State::READY)
        return "ERR_NOT_READY: execute CONFIG primeiro";
    if (_state == State::RUNNING_WALK ||
        _state == State::RUNNING_CLOCK ||
        _state == State::RUNNING_BURN  ||
        _state == State::RUNNING_BURN3)
        return "ERR_RUN_ACTIVE: já há um run em andamento";
    if (!_wifi_up())
        return "ERR_NO_WIFI: Wi-Fi necessário para BURN";

    _ctx.mode        = RunMode::BURN;
    _ctx.cold_start  = false;
    _ctx.samples     = 0;
    _ctx.active_block   = three_blocks ? 1 : 0;
    _ctx.blocks_done    = 0;
    _ctx.block_start_ms = millis();
    _ctx.active_marker[0] = '\0';
    _ctx.start_ms    = millis();

    char key[20];
    snprintf(key, sizeof(key), "rn_%s_%s_%s",
             _ctx.antenna, _ctx.location, _ctx.condition);
    _ctx.run_number = _load_run_number(key);

    csv_open_run();

    if (three_blocks) {
        csv_write_block_event(1); // linha B BLOCK1
        _state = State::RUNNING_BURN3;
    } else {
        _state = State::RUNNING_BURN;
    }
    return nullptr;
}

// MARK <label> — somente em CLOCK
const char* sm_cmd_mark(const char* label) {
    if (_state != State::RUNNING_CLOCK)
        return "ERR_NOT_CLOCK: MARK so aceito durante START_CLOCK";
    if (!_valid_id(label, MARKER_MAX_LEN))
        return "ERR_INVALID: label alfanumerico+underscore, max 8 chars";

    strncpy(_ctx.active_marker, label, MARKER_MAX_LEN);
    _ctx.active_marker[MARKER_MAX_LEN] = '\0';

    csv_write_marker_event(label);
    return nullptr;
}

// STOP
const char* sm_cmd_stop() {
    if (_state == State::IDLE || _state == State::READY)
        return "ERR_NOT_RUNNING: nenhum run ativo";
    if (_state == State::FLUSHING)
        return "ERR_FLUSHING: flush em andamento, aguarde";

    _state = State::FLUSHING;
    // flush completo com timeout 5 s — executado pela task de log
    // ela chama csv_close_run() e volta para READY
    return nullptr;
}

// Chamado pelo runner quando BURN3 encerra automaticamente
void sm_finish_burn3() {
    if (_state == State::RUNNING_BURN3) {
        _state = State::FLUSHING;
    }
}
