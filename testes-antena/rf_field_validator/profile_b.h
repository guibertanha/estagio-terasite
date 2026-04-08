#pragma once
#include <Arduino.h>

// ============================================================
//  profile_b.h — Perfil B: WALK (2 Hz) e CLOCK (1 Hz)
//  Ping contínuo sem throughput.
//  Cada amostra → linha S no CSV com herança de contexto.
// ============================================================

void profile_b_task(void* param);  // xTaskCreate target
// A task detecta o modo (WALK/CLOCK) pelo sm_state() e adapta a frequência.
