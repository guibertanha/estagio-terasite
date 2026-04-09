#include "weblog.h"
#include <freertos/FreeRTOS.h>
#include <freertos/semphr.h>
#include <stdio.h>
#include <stdarg.h>
#include <string.h>

// ── Buffer circular ───────────────────────────────────────────
static char _buf[WEBLOG_LINES][WEBLOG_LINE_LEN];
static uint8_t  _head    = 0;   // próximo índice a escrever
static uint16_t _total   = 0;   // total de linhas escritas (para o cliente saber se há novidade)
static SemaphoreHandle_t _mtx = nullptr;

void weblog_init() {
    memset(_buf, 0, sizeof(_buf));
    _mtx = xSemaphoreCreateMutex();
}

static void _push(const char* s) {
    if (!_mtx) return;
    if (xSemaphoreTake(_mtx, pdMS_TO_TICKS(50)) != pdTRUE) return;
    strncpy(_buf[_head], s, WEBLOG_LINE_LEN - 1);
    _buf[_head][WEBLOG_LINE_LEN - 1] = '\0';
    _head  = (_head + 1) % WEBLOG_LINES;
    _total++;
    xSemaphoreGive(_mtx);
}

void weblog_printf(const char* fmt, ...) {
    char tmp[WEBLOG_LINE_LEN];
    va_list args;
    va_start(args, fmt);
    vsnprintf(tmp, sizeof(tmp), fmt, args);
    va_end(args);
    Serial.print(tmp);
    _push(tmp);
}

void weblog_println(const char* s) {
    Serial.println(s);
    char tmp[WEBLOG_LINE_LEN];
    snprintf(tmp, sizeof(tmp), "%s", s);
    _push(tmp);
}

void weblog_to_json(char* out, size_t max_len) {
    if (!_mtx || !out || max_len < 16) return;
    if (xSemaphoreTake(_mtx, pdMS_TO_TICKS(100)) != pdTRUE) {
        snprintf(out, max_len, "{\"n\":0,\"lines\":[]}");
        return;
    }

    // Determina a ordem de leitura: do mais antigo ao mais novo
    uint8_t  count = (_total < WEBLOG_LINES) ? (uint8_t)_total : WEBLOG_LINES;
    uint8_t  start = (_total < WEBLOG_LINES) ? 0 : _head;

    size_t pos = 0;
    pos += snprintf(out + pos, max_len - pos, "{\"n\":%u,\"lines\":[", _total);

    for (uint8_t i = 0; i < count && pos < max_len - 4; i++) {
        uint8_t idx = (start + i) % WEBLOG_LINES;
        if (i > 0) out[pos++] = ',';
        out[pos++] = '"';
        // Escapa aspas e barras
        for (const char* p = _buf[idx]; *p && pos < max_len - 6; p++) {
            if (*p == '"' || *p == '\\') out[pos++] = '\\';
            else if (*p == '\n' || *p == '\r') { out[pos++] = '\\'; out[pos++] = 'n'; continue; }
            out[pos++] = *p;
        }
        out[pos++] = '"';
    }

    snprintf(out + pos, max_len - pos, "]}");
    xSemaphoreGive(_mtx);
}
