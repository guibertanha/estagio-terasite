#pragma once
#include <Arduino.h>
#include <WiFi.h>
#include "config.h"

// ============================================================
//  state_machine.h — Máquina de estados central
// ============================================================

// ── Estados ──────────────────────────────────────────────────
enum class State : uint8_t {
    IDLE,          // aguardando CONFIG
    READY,         // CONFIG recebido, aguardando START_*
    RUNNING_WALK,
    RUNNING_CLOCK,
    RUNNING_BURN,
    RUNNING_BURN3, // START_BURN 3x60
    FLUSHING,      // STOP recebido, aguardando flush
};

// ── Modos (para nome de arquivo e CSV) ───────────────────────
enum class RunMode : uint8_t { NONE, WALK, CLOCK, BURN };

// ── Alvo TCP configurável em runtime (padrão = TCP_TARGET_HOST de config.h) ─
extern char g_tcp_host[64];

// ── Contexto do run ativo ────────────────────────────────────
struct RunContext {
    char antenna[6];     // ex: "A5.2"
    char location[8];    // ex: "CAMPO"
    char condition[5];   // ex: "RUN"
    RunMode mode;
    uint8_t  run_number; // 1..99 (incrementa por arquivo CSV)
    uint32_t start_ms;
    uint32_t samples;
    uint32_t boot_count;

    // herança de contexto (spec §2.5)
    char active_marker[MARKER_MAX_LEN + 1];
    uint8_t active_block;  // 0=sem bloco, 1/2/3

    // burn 3x60
    uint32_t block_start_ms;
    uint8_t  blocks_done;

    // cold start (WALK --cold)
    bool cold_start;
};

// ── API pública ──────────────────────────────────────────────
void sm_init();
State sm_state();
RunContext* sm_ctx();

// Retorna nullptr se aceito, ou mensagem de erro
const char* sm_cmd_config(const char* antenna, const char* location, const char* condition);
const char* sm_cmd_start_walk(bool cold);
const char* sm_cmd_start_clock();
const char* sm_cmd_start_burn(bool three_blocks);
const char* sm_cmd_mark(const char* label);
const char* sm_cmd_stop();

// Chamada pelo runner quando 3x60 encerra automaticamente
void sm_finish_burn3();
