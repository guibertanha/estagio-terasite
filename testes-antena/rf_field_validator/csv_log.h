#pragma once
#include <Arduino.h>
#include "state_machine.h"

// ============================================================
//  csv_log.h — Estrutura CSV, ring buffer, flush protegido
// ============================================================

// ── Linha CSV (alocada em RAM, flushed para flash) ───────────
// Colunas fixas da spec §2.6
struct CsvRow {
    uint32_t timestamp_ms;
    char     type[2];         // S / E / M / B
    char     profile[2];      // A / B / -
    char     phase[4];        // F0/F1/F2/F3A/F3B/-
    char     antenna[6];      // ex: "A5.2" — bate com RunContext.antenna
    char     location[8];     // ex: "GUARITA" — bate com RunContext.location
    char     condition[5];    // ex: "RUN" — bate com RunContext.condition
    char     run_id[32];

    int8_t   rssi_dbm;
    uint8_t  ping_ok;         // 0 ou 1
    float    ping_latency_ms;
    uint32_t ping_seq;

    uint32_t throughput_bps;
    float    plr_window;

    uint16_t vin_mv;
    float    temp_c;
    uint8_t  link_state;      // 0=desconectado 1=conectado

    uint32_t boot_count;
    uint32_t uptime_ms;

    char     marker[9];       // max 8 + \0
    uint8_t  block;           // 0/1/2/3
    char     notes[48];
};

// ── Ring buffer (thread-safe via FreeRTOS queue) ─────────────
void     csv_ring_init();
bool     csv_ring_push(const CsvRow& row);   // chamado pelas tasks de medição
bool     csv_ring_pop(CsvRow* out);          // chamado pela task de log
uint16_t csv_ring_count();

// ── Controle de arquivo ──────────────────────────────────────
void csv_open_run();    // cria arquivo, grava header + E START_RUN
void csv_close_run(bool aborted);  // grava E END_RUN, fecha arquivo

// ── Eventos especiais ─────────────────────────────────────────
void csv_write_event(const char* notes, const char* phase = "-");
void csv_write_marker_event(const char* label);
void csv_write_block_event(uint8_t block_num);
void csv_write_epoch_anchor(uint32_t unix_ts);

// ── Flush ────────────────────────────────────────────────────
// Retorna número de linhas gravadas. Chamada pela task de log.
uint16_t csv_flush_batch();
void     csv_flush_all(uint32_t timeout_ms = 5000);

// Flag setada quando csv_flush_all() encerra com dados ainda na fila.
// Resetada no início de cada csv_open_run(). Exposta para o painel web.
extern bool g_flush_incomplete;

// ── Status ───────────────────────────────────────────────────
String   csv_current_filename();
uint32_t csv_free_kb();

// ── Próximo run number disponível (ignora arquivos apagados) ──
// Varre o LittleFS e retorna o menor R que não tem arquivo ainda.
uint8_t csv_next_run_number(const char* ant, const char* loc,
                            const char* cnd, RunMode mode);

// ── Helper para construir linha S ───────────────────────────
CsvRow csv_make_sample(int8_t rssi, uint8_t ok, float lat_ms, uint32_t seq,
                       uint32_t tput_bps = 0, float plr = 0.0f);
