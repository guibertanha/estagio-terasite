#pragma once

// ============================================================
//  web_ui.h — Interface web + botão físico para uso em campo
//
//  O ESP32 serve uma página HTML em http://<IP-do-ESP32>/
//  O celular/tablet conecta na mesma rede Wi-Fi sendo testada
//  e acessa o painel de controle sem cabo USB.
//
//  Botão físico (PIN_BUTTON em config.h):
//    - READY     → START_WALK
//    - RUNNING_* → STOP
// ============================================================

void web_ui_init();      // chamar no setup() após WiFi e sm_init()
void web_ui_try_init();  // chamar no loop() — inicializa se WiFi subiu e ainda não foi iniciado
void web_ui_handle();    // chamar no loop()

// Flag de ancoragem NTP — compartilhada com rf_field_validator.ino
extern bool g_epoch_anchored;
