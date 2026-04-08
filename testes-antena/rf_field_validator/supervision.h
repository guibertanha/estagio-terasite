#pragma once
#include <Arduino.h>

// ============================================================
//  supervision.h — Task de supervisão (1 Hz, alta prioridade)
//  Monitora: V_IN, temperatura interna, uptime, link_state
//  Injeta eventos no ring buffer quando necessário.
// ============================================================

void supervision_init();
void supervision_task(void* param);   // xTaskCreate target

// Leituras atuais (lidas pelas tasks de medição para preencher CsvRow)
uint16_t sup_vin_mv();
float    sup_temp_c();
uint8_t  sup_link_state();  // 0=desconectado, 1=conectado
