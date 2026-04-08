#include "csv_log.h"
#include "config.h"
#include "state_machine.h"
#include <LittleFS.h>
#include <freertos/FreeRTOS.h>
#include <freertos/queue.h>
#include <freertos/semphr.h>

// ── Ring buffer via FreeRTOS queue ───────────────────────────
static QueueHandle_t _ring  = nullptr;
static SemaphoreHandle_t _fs_mutex = nullptr;

// ── Estado de arquivo ─────────────────────────────────────────
static char    _filename[64]  = {};
static File    _file;
static bool    _file_open     = false;
static uint32_t _last_flush_ms = 0;

// ── CRC16 (CCITT-FALSE) ───────────────────────────────────────
static uint16_t crc16(const uint8_t* data, size_t len) {
    uint16_t crc = 0xFFFF;
    for (size_t i = 0; i < len; i++) {
        crc ^= (uint16_t)data[i] << 8;
        for (int b = 0; b < 8; b++)
            crc = (crc & 0x8000) ? (crc << 1) ^ 0x1021 : crc << 1;
    }
    return crc;
}

// ── CSV header ────────────────────────────────────────────────
static const char* CSV_HEADER =
    "timestamp_ms,type,profile,phase,antenna,location,condition,run_id,"
    "rssi_dbm,ping_ok,ping_latency_ms,ping_seq,"
    "throughput_bps,plr_window,"
    "vin_mv,temp_c,link_state,boot_count,uptime_ms,"
    "marker,block,notes\n";

// ── Serializa uma CsvRow para string (sem \n final) ──────────
static String _row_to_str(const CsvRow& r) {
    char buf[256];
    snprintf(buf, sizeof(buf),
        "%lu,%s,%s,%s,%s,%s,%s,%s,"
        "%d,%u,%.2f,%lu,"
        "%lu,%.4f,"
        "%u,%.1f,%u,%lu,%lu,"
        "%s,%u,%s",
        (unsigned long)r.timestamp_ms,
        r.type, r.profile, r.phase,
        r.antenna, r.location, r.condition, r.run_id,
        (int)r.rssi_dbm, r.ping_ok, r.ping_latency_ms, (unsigned long)r.ping_seq,
        (unsigned long)r.throughput_bps, r.plr_window,
        r.vin_mv, r.temp_c, r.link_state,
        (unsigned long)r.boot_count, (unsigned long)r.uptime_ms,
        r.marker, r.block, r.notes
    );
    return String(buf);
}

// ── Grava linha + CRC no arquivo ─────────────────────────────
// Formato: <csv_line>,crc16=XXXX\n
// Permite ao parser validar cada linha individualmente.
static void _write_line(const CsvRow& r) {
    if (!_file_open) return;
    String line = _row_to_str(r);
    uint16_t crc = crc16((const uint8_t*)line.c_str(), line.length());
    char crc_field[12];
    snprintf(crc_field, sizeof(crc_field), ",crc16=%04X\n", crc);
    _file.print(line);
    _file.print(crc_field);
}

// ── Ring buffer ───────────────────────────────────────────────
void csv_ring_init() {
    _ring     = xQueueCreate(RING_BUF_SLOTS, sizeof(CsvRow));
    _fs_mutex = xSemaphoreCreateMutex();
}

bool csv_ring_push(const CsvRow& row) {
    if (!_ring) return false;
    return xQueueSend(_ring, &row, 0) == pdTRUE;
}

bool csv_ring_pop(CsvRow* out) {
    if (!_ring) return false;
    return xQueueReceive(_ring, out, 0) == pdTRUE;
}

uint16_t csv_ring_count() {
    if (!_ring) return 0;
    return (uint16_t)uxQueueMessagesWaiting(_ring);
}

// ── Nome de arquivo ───────────────────────────────────────────
// Formato spec: [MODE]_[ANTENA]_[LOCAL]_[CONDICAO]_[RUN].csv
static void _build_filename() {
    RunContext* ctx = sm_ctx();
    const char* mode_str;
    switch (ctx->mode) {
        case RunMode::WALK:  mode_str = "WALK";  break;
        case RunMode::CLOCK: mode_str = "CLOCK"; break;
        case RunMode::BURN:  mode_str = "BURN";  break;
        default:             mode_str = "UNKN";  break;
    }
    snprintf(_filename, sizeof(_filename),
             "%s/%s_%s_%s_%s_R%02u.csv",
             FS_BASE_PATH,
             mode_str,
             ctx->antenna,
             ctx->location,
             ctx->condition,
             ctx->run_number);
}

// ── run_id (nome sem extensão) ─────────────────────────────────
static void _build_run_id(char* out, size_t maxlen) {
    RunContext* ctx = sm_ctx();
    const char* mode_str;
    switch (ctx->mode) {
        case RunMode::WALK:  mode_str = "WALK";  break;
        case RunMode::CLOCK: mode_str = "CLOCK"; break;
        case RunMode::BURN:  mode_str = "BURN";  break;
        default:             mode_str = "UNKN";  break;
    }
    snprintf(out, maxlen, "%s_%s_%s_%s_R%02u",
             mode_str,
             ctx->antenna,
             ctx->location,
             ctx->condition,
             ctx->run_number);
}

// ── Preenche campos de contexto em uma row ────────────────────
static void _fill_ctx(CsvRow& r) {
    RunContext* ctx = sm_ctx();
    r.timestamp_ms = millis();
    r.boot_count   = ctx->boot_count;
    r.uptime_ms    = millis();
    strncpy(r.antenna,   ctx->antenna,   sizeof(r.antenna)-1);
    strncpy(r.location,  ctx->location,  sizeof(r.location)-1);
    strncpy(r.condition, ctx->condition, sizeof(r.condition)-1);
    strncpy(r.marker,    ctx->active_marker, sizeof(r.marker)-1);
    r.block = ctx->active_block;
    _build_run_id(r.run_id, sizeof(r.run_id));

    // profile e phase por modo
    switch (ctx->mode) {
        case RunMode::WALK:
            strncpy(r.profile, "B", sizeof(r.profile)-1);
            strncpy(r.phase,  "F1", sizeof(r.phase)-1);
            break;
        case RunMode::CLOCK:
            strncpy(r.profile, "B", sizeof(r.profile)-1);
            strncpy(r.phase,  "F2", sizeof(r.phase)-1);
            break;
        case RunMode::BURN:
            strncpy(r.profile, "A", sizeof(r.profile)-1);
            // fase detectada pela condição
            if (strcmp(ctx->condition, "OFF") == 0)
                strncpy(r.phase, "F0", sizeof(r.phase)-1);
            else if (strcmp(ctx->condition, "ON") == 0)
                strncpy(r.phase, "F3A", sizeof(r.phase)-1);
            else
                strncpy(r.phase, "F3B", sizeof(r.phase)-1);
            break;
        default:
            strncpy(r.profile, "-", sizeof(r.profile)-1);
            strncpy(r.phase,   "-", sizeof(r.phase)-1);
    }
}

// ── Abrir run ─────────────────────────────────────────────────
void csv_open_run() {
    if (!LittleFS.begin(true)) return;
    LittleFS.mkdir(FS_BASE_PATH);

    _build_filename();

    if (xSemaphoreTake(_fs_mutex, pdMS_TO_TICKS(1000)) != pdTRUE) return;
    _file = LittleFS.open(_filename, FILE_WRITE);
    if (_file) {
        _file_open = true;
        _file.print(CSV_HEADER);

        // linha E START_RUN
        CsvRow r = {};
        _fill_ctx(r);
        strncpy(r.type,  "E", sizeof(r.type)-1);
        strncpy(r.notes, "START_RUN", sizeof(r.notes)-1);
        r.ping_ok = 0;
        _write_line(r);
        _file.flush();
    }
    xSemaphoreGive(_fs_mutex);
    _last_flush_ms = millis();
}

// ── Fechar run ────────────────────────────────────────────────
void csv_close_run(bool aborted) {
    if (!_file_open) return;
    csv_flush_all(5000);

    if (xSemaphoreTake(_fs_mutex, pdMS_TO_TICKS(1000)) != pdTRUE) return;
    CsvRow r = {};
    _fill_ctx(r);
    strncpy(r.type, "E", sizeof(r.type)-1);
    strncpy(r.notes, aborted ? "ABORTED" : "END_RUN", sizeof(r.notes)-1);
    _write_line(r);
    _file.flush();
    _file.close();
    _file_open = false;
    xSemaphoreGive(_fs_mutex);
}

// ── Eventos ───────────────────────────────────────────────────
void csv_write_event(const char* notes, const char* phase) {
    CsvRow r = {};
    _fill_ctx(r);
    strncpy(r.type,  "E", sizeof(r.type)-1);
    strncpy(r.notes, notes, sizeof(r.notes)-1);
    if (phase) strncpy(r.phase, phase, sizeof(r.phase)-1);
    csv_ring_push(r);
}

void csv_write_marker_event(const char* label) {
    CsvRow r = {};
    _fill_ctx(r);
    strncpy(r.type,   "M", sizeof(r.type)-1);
    strncpy(r.marker, label, sizeof(r.marker)-1);
    strncpy(r.notes,  label, sizeof(r.notes)-1);
    csv_ring_push(r);
}

void csv_write_block_event(uint8_t block_num) {
    RunContext* ctx = sm_ctx();
    ctx->active_block = block_num;
    CsvRow r = {};
    _fill_ctx(r);
    strncpy(r.type, "B", sizeof(r.type)-1);
    char bn[10];
    snprintf(bn, sizeof(bn), "BLOCK%u", block_num);
    strncpy(r.notes, bn, sizeof(r.notes)-1);
    csv_ring_push(r);
}

void csv_write_epoch_anchor(uint32_t unix_ts) {
    CsvRow r = {};
    _fill_ctx(r);
    strncpy(r.type, "E", sizeof(r.type)-1);
    char buf[32];
    snprintf(buf, sizeof(buf), "EPOCH_ANCHOR unix=%lu", (unsigned long)unix_ts);
    strncpy(r.notes, buf, sizeof(r.notes)-1);
    csv_ring_push(r);
}

// ── Flush em lote ─────────────────────────────────────────────
uint16_t csv_flush_batch() {
    if (!_file_open || !_ring) return 0;
    if (xSemaphoreTake(_fs_mutex, pdMS_TO_TICKS(200)) != pdTRUE) return 0;

    uint16_t written = 0;
    CsvRow row;
    while (written < FLUSH_BATCH && xQueueReceive(_ring, &row, 0) == pdTRUE) {
        _write_line(row);
        written++;
    }
    if (written > 0) _file.flush();
    xSemaphoreGive(_fs_mutex);
    _last_flush_ms = millis();
    return written;
}

// ── Flush total com timeout ───────────────────────────────────
void csv_flush_all(uint32_t timeout_ms) {
    uint32_t deadline = millis() + timeout_ms;
    CsvRow row;
    while (millis() < deadline) {
        bool got = false;
        if (xSemaphoreTake(_fs_mutex, pdMS_TO_TICKS(200)) == pdTRUE) {
            if (xQueueReceive(_ring, &row, 0) == pdTRUE) {
                _write_line(row);
                got = true;
            }
            xSemaphoreGive(_fs_mutex);
        }
        if (!got) {
            if (xSemaphoreTake(_fs_mutex, pdMS_TO_TICKS(100)) == pdTRUE) {
                _file.flush();
                xSemaphoreGive(_fs_mutex);
            }
            break;
        }
    }
    // se ainda há dados na fila após timeout → FLUSH_INCOMPLETE
    if (csv_ring_count() > 0) {
        if (xSemaphoreTake(_fs_mutex, pdMS_TO_TICKS(200)) == pdTRUE) {
            CsvRow fe = {};
            RunContext* ctx = sm_ctx();
            strncpy(fe.type,  "E",                sizeof(fe.type)-1);
            strncpy(fe.notes, "FLUSH_INCOMPLETE", sizeof(fe.notes)-1);
            strncpy(fe.antenna,   ctx->antenna,   sizeof(fe.antenna)-1);
            strncpy(fe.location,  ctx->location,  sizeof(fe.location)-1);
            strncpy(fe.condition, ctx->condition, sizeof(fe.condition)-1);
            fe.timestamp_ms = millis();
            fe.boot_count   = ctx->boot_count;
            fe.uptime_ms    = millis();
            _build_run_id(fe.run_id, sizeof(fe.run_id));
            _write_line(fe);
            _file.flush();
            xSemaphoreGive(_fs_mutex);
        }
    }
}

String csv_current_filename() { return String(_filename); }

uint32_t csv_free_kb() {
    return LittleFS.totalBytes() > LittleFS.usedBytes()
        ? (LittleFS.totalBytes() - LittleFS.usedBytes()) / 1024
        : 0;
}

// ── Helper linha S ────────────────────────────────────────────
CsvRow csv_make_sample(int8_t rssi, uint8_t ok, float lat_ms, uint32_t seq,
                       uint32_t tput_bps, float plr) {
    CsvRow r = {};
    _fill_ctx(r);
    strncpy(r.type, "S", sizeof(r.type)-1);
    r.rssi_dbm        = rssi;
    r.ping_ok         = ok;
    r.ping_latency_ms = lat_ms;
    r.ping_seq        = seq;
    r.throughput_bps  = tput_bps;
    r.plr_window      = plr;
    return r;
}
