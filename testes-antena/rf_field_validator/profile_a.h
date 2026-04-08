#pragma once
#include <Arduino.h>

// ============================================================
//  profile_a.h — Perfil A: Stress Window (15 s)
//
//  Estrutura de cada janela:
//    [0–3s]   ping puro (contabiliza PLR da janela)
//    [3–13s]  throughput TCP (bytes/s contra tcp_sink.py)
//    [13–15s] cooldown / flush parcial
//
//  Saída: 1 linha S por janela com medianas/percentis agregados.
//  Para START_BURN 3x60: 3 blocos de 60 s (4 janelas cada).
// ============================================================

void profile_a_task(void* param);  // xTaskCreate target
