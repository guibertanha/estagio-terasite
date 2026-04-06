/**
 * @file    rf_baseline_logger.ino
 * @brief   Firmware de coleta de telemetria RSSI (Baseline) para homologação de antenas.
 * @details Conecta a uma rede de teste e exporta os dados de potência de sinal via Serial (formato CSV).
 * @author  Guilherme Bertanha
 */

#include <WiFi.h>

// Credenciais da rede de teste (Ambiente Controlado)
const char* TEST_SSID = "Andreia Sala";
const char* TEST_PASS = "andreia2021";

// Parametros de amostragem
const unsigned long SAMPLE_INTERVAL_MS = 1000;
unsigned long lastSampleTime = 0;

// Exporta a telemetria mantendo compatibilidade com os scripts de parser em Python
static void logTelemetry(const char* tag) {
  Serial.print(millis());
  Serial.print(",");
  Serial.print(tag);
  Serial.print(",IP=");
  Serial.print(WiFi.localIP());
  Serial.print(",RSSI=");
  Serial.println(WiFi.RSSI());
}

// Interrupcoes de rede para registro de eventos (Queda/Reconexao)
void onWiFiEvent(WiFiEvent_t event) {
  switch (event) {
    case ARDUINO_EVENT_WIFI_STA_CONNECTED:
      logTelemetry("CONNECTED");
      break;
    case ARDUINO_EVENT_WIFI_STA_GOT_IP:
      logTelemetry("GOT_IP");
      break;
    case ARDUINO_EVENT_WIFI_STA_DISCONNECTED:
      logTelemetry("DISCONNECTED");
      break;
    default:
      break;
  }
}

void setup() {
  Serial.begin(115200);
  delay(500);

  // Cabecalho do log CSV
  Serial.println("ms,event,IP,RSSI");

  WiFi.mode(WIFI_STA);
  WiFi.onEvent(onWiFiEvent);

  WiFi.begin(TEST_SSID, TEST_PASS);

  // Timeout de conexao configurado para 20 segundos
  unsigned long startTime = millis();
  while (WiFi.status() != WL_CONNECTED && (millis() - startTime) < 20000) {
    delay(200);
  }

  if (WiFi.status() == WL_CONNECTED) {
    logTelemetry("START_OK");
  } else {
    Serial.println("START_FAIL");
  }
}

void loop() {
  if (millis() - lastSampleTime >= SAMPLE_INTERVAL_MS) {
    lastSampleTime = millis();

    if (WiFi.status() == WL_CONNECTED) {
      logTelemetry("RSSI");
    } else {
      logTelemetry("NO_LINK");
      WiFi.reconnect();
    }
  }
}