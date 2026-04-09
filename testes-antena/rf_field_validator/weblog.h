#pragma once
#include <Arduino.h>

// ============================================================
//  weblog.h — Buffer circular de log exposto via /weblog
//  Captura as mesmas mensagens do Serial para o painel web.
//  Thread-safe via mutex FreeRTOS.
// ============================================================

#define WEBLOG_LINES   40    // linhas no buffer circular
#define WEBLOG_LINE_LEN 96   // caracteres por linha (inclui \0)

void weblog_init();

// Equivalente a Serial.printf — grava no Serial E no buffer web
void weblog_printf(const char* fmt, ...) __attribute__((format(printf, 1, 2)));

// Equivalente a Serial.println
void weblog_println(const char* s);

// Serializa o buffer como JSON para o endpoint /weblog
// out: buffer destino, max_len: tamanho máximo
void weblog_to_json(char* out, size_t max_len);
