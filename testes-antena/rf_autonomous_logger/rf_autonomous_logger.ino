/**
 * @file    rf_autonomous_logger_standard.ino
 * @brief   Firmware padrão de telemetria RSSI para ESP32 via LittleFS.
 * @details Coleta RSSI em modo autônomo, registra eventos de conexão e gera
 * resumo final. O nome do ensaio deve ser definido no arquivo salvo no PC
 * via PuTTY, para evitar regravar a placa a cada teste.
 * @author  Guilherme Bertanha
 * @revision ChatGPT
 */

#include <WiFi.h>
#include <LittleFS.h>

// ======================================================
// CONFIGURAÇÕES FIXAS
// ======================================================

const char* WIFI_SSID = "AP 101 - 2.4GHz";
const char* WIFI_PASS = "guilherme2";

const char* LOG_FILE_PATH = "/log_rf.csv";

const unsigned long SAMPLE_INTERVAL_MS = 1000;   // 1 amostra por segundo
const int MAX_SAMPLES = 180;                     // 3 minutos
const unsigned long CLI_TIMEOUT = 10000;         // 10 segundos
const unsigned long WIFI_CONNECT_TIMEOUT_MS = 15000;

// ======================================================
// CONTROLE DE ESTADO
// ======================================================

bool isLoggingActive = false;
bool statsStarted = false;

int currentSampleCount = 0;
unsigned long lastSampleTime = 0;

// Estatísticas RSSI
long rssiSum = 0;
int rssiMin = 0;
int rssiMax = 0;
int validRssiSamples = 0;

// Eventos
int disconnectCount = 0;
int reconnectAttempts = 0;

// ======================================================
// FUNÇÕES AUXILIARES
// ======================================================

void resetStats() {
  rssiSum = 0;
  rssiMin = 0;
  rssiMax = 0;
  validRssiSamples = 0;

  disconnectCount = 0;
  reconnectAttempts = 0;

  currentSampleCount = 0;
  lastSampleTime = 0;
  statsStarted = false;
}

void updateRssiStats(int rssi) {
  if (!statsStarted) {
    rssiMin = rssi;
    rssiMax = rssi;
    statsStarted = true;
  } else {
    if (rssi < rssiMin) rssiMin = rssi;
    if (rssi > rssiMax) rssiMax = rssi;
  }

  rssiSum += rssi;
  validRssiSamples++;
}

float getAverageRssi() {
  if (validRssiSamples == 0) return 0.0;
  return (float)rssiSum / (float)validRssiSamples;
}

String getBSSIDString() {
  uint8_t* bssid = WiFi.BSSID();
  if (bssid == nullptr) return "NA";

  char buffer[18];
  snprintf(
    buffer, sizeof(buffer),
    "%02X:%02X:%02X:%02X:%02X:%02X",
    bssid[0], bssid[1], bssid[2], bssid[3], bssid[4], bssid[5]
  );
  return String(buffer);
}

void appendRawLine(const String& line) {
  File logFile = LittleFS.open(LOG_FILE_PATH, FILE_APPEND);
  if (!logFile) {
    Serial.println("[ERROR] Falha ao abrir arquivo para escrita.");
    return;
  }

  logFile.println(line);
  logFile.close();
}

void appendTelemetry(const char* tag, bool includeRssi = true) {
  String line = "";

  line += millis();
  line += ",";
  line += "TAG=";
  line += tag;
  line += ",";
  line += "SSID=";
  line += WIFI_SSID;
  line += ",";
  line += "IP=";
  line += WiFi.localIP().toString();
  line += ",";
  line += "STATUS=";
  line += (WiFi.status() == WL_CONNECTED ? "CONNECTED" : "DISCONNECTED");

  if (WiFi.status() == WL_CONNECTED) {
    line += ",";
    line += "CHANNEL=";
    line += WiFi.channel();
    line += ",";
    line += "BSSID=";
    line += getBSSIDString();
  } else {
    line += ",CHANNEL=NA,BSSID=NA";
  }

  if (includeRssi && WiFi.status() == WL_CONNECTED) {
    int rssi = WiFi.RSSI();
    line += ",";
    line += "RSSI=";
    line += rssi;
    updateRssiStats(rssi);
  } else {
    line += ",RSSI=NA";
  }

  appendRawLine(line);
}

void appendSummary() {
  String line = "";

  line += millis();
  line += ",";
  line += "TAG=SUMMARY";
  line += ",";
  line += "SAMPLES_TOTAL=";
  line += currentSampleCount;
  line += ",";
  line += "RSSI_VALID_SAMPLES=";
  line += validRssiSamples;
  line += ",";
  line += "RSSI_AVG=";
  line += String(getAverageRssi(), 2);
  line += ",";
  line += "RSSI_MIN=";
  line += (validRssiSamples > 0 ? String(rssiMin) : "NA");
  line += ",";
  line += "RSSI_MAX=";
  line += (validRssiSamples > 0 ? String(rssiMax) : "NA");
  line += ",";
  line += "DISCONNECTS=";
  line += disconnectCount;
  line += ",";
  line += "RECONNECT_ATTEMPTS=";
  line += reconnectAttempts;

  appendRawLine(line);
}

void writeHeaderIfNeeded() {
  if (LittleFS.exists(LOG_FILE_PATH)) return;

  File logFile = LittleFS.open(LOG_FILE_PATH, FILE_WRITE);
  if (!logFile) {
    Serial.println("[ERROR] Falha ao criar arquivo de log.");
    return;
  }

  logFile.println("# LOG RF FROTALL");
  logFile.println("# Salve cada dump com nome do ensaio no PC (ex.: A4_U1_CASE_T1.txt)");
  logFile.println("# Formato: ms, KEY=VALUE, KEY=VALUE...");
  logFile.close();
}

void exportLogData() {
  File logFile = LittleFS.open(LOG_FILE_PATH, FILE_READ);
  if (!logFile) {
    Serial.println("[INFO] Nenhum dado de telemetria encontrado.");
    return;
  }

  Serial.println("\n--- INICIO DO LOG DE TELEMETRIA ---");
  while (logFile.available()) {
    Serial.write(logFile.read());
  }
  Serial.println("--- FIM DO LOG DE TELEMETRIA ---");
  logFile.close();
}

void printLogInfo() {
  if (!LittleFS.exists(LOG_FILE_PATH)) {
    Serial.println("[INFO] Arquivo de log inexistente.");
    return;
  }

  File logFile = LittleFS.open(LOG_FILE_PATH, FILE_READ);
  if (!logFile) {
    Serial.println("[ERROR] Falha ao abrir arquivo para info.");
    return;
  }

  size_t size = logFile.size();
  logFile.close();

  Serial.println("[INFO] Arquivo de log encontrado.");
  Serial.print("[INFO] Caminho: ");
  Serial.println(LOG_FILE_PATH);
  Serial.print("[INFO] Tamanho (bytes): ");
  Serial.println(size);
}

void clearLogData() {
  if (LittleFS.exists(LOG_FILE_PATH)) {
    LittleFS.remove(LOG_FILE_PATH);
  }
  Serial.println("[OK] Log apagado. Reinicie para nova coleta.");
}

bool connectWiFi() {
  WiFi.mode(WIFI_STA);
  WiFi.begin(WIFI_SSID, WIFI_PASS);

  unsigned long startMs = millis();
  while (WiFi.status() != WL_CONNECTED && (millis() - startMs) < WIFI_CONNECT_TIMEOUT_MS) {
    delay(200);
  }

  return (WiFi.status() == WL_CONNECTED);
}

// ======================================================
// CALLBACK WIFI
// ======================================================

void onWiFiEvent(WiFiEvent_t event) {
  if (event == ARDUINO_EVENT_WIFI_STA_DISCONNECTED) {
    disconnectCount++;
    if (isLoggingActive) {
      appendTelemetry("DISCONNECTED", false);
    }
  }
}

// ======================================================
// SETUP
// ======================================================

void setup() {
  Serial.begin(115200);
  delay(1000);

  if (!LittleFS.begin(true)) {
    Serial.println("[FATAL] Falha na montagem do LittleFS.");
    return;
  }

  writeHeaderIfNeeded();
  resetStats();

  Serial.println("\n\n=== SISTEMA DE TELEMETRIA RF FROTALL ===");
  Serial.println("Comandos disponiveis (10s):");
  Serial.println(" [d] - Exportar log");
  Serial.println(" [c] - Apagar log");
  Serial.println(" [i] - Info do log");
  Serial.println(" Timeout -> inicia coleta autonoma");

  unsigned long bootTime = millis();
  bool userInteracted = false;

  while (millis() - bootTime < CLI_TIMEOUT) {
    if (Serial.available()) {
      char command = Serial.read();

      if (command == 'd' || command == 'D') {
        exportLogData();
        userInteracted = true;
        while (true) { delay(100); }

      } else if (command == 'c' || command == 'C') {
        clearLogData();
        userInteracted = true;
        while (true) { delay(100); }

      } else if (command == 'i' || command == 'I') {
        printLogInfo();
        userInteracted = true;
        while (true) { delay(100); }
      }
    }
  }

  if (!userInteracted) {
    Serial.println("\n[INFO] Timeout atingido. Iniciando coleta autonoma...");

    appendRawLine("");
    appendRawLine("############################################################");
    appendRawLine("# NOVO ENSAIO");
    appendRawLine("############################################################");

    WiFi.onEvent(onWiFiEvent);

    if (connectWiFi()) {
      appendTelemetry("START_OK", true);
      isLoggingActive = true;

      Serial.println("[INFO] WiFi conectado.");
      Serial.print("[INFO] IP: ");
      Serial.println(WiFi.localIP());
      Serial.print("[INFO] Canal: ");
      Serial.println(WiFi.channel());
      Serial.print("[INFO] BSSID: ");
      Serial.println(getBSSIDString());
      Serial.println("[INFO] Gravacao em Flash iniciada.");
    } else {
      appendTelemetry("START_FAIL", false);
      Serial.println("[ERROR] Falha na conexao WiFi.");
      isLoggingActive = true; // segue tentando reconectar
    }
  }
}

// ======================================================
// LOOP
// ======================================================

void loop() {
  if (!isLoggingActive) return;

  unsigned long now = millis();
  if (now - lastSampleTime < SAMPLE_INTERVAL_MS) return;

  lastSampleTime = now;

  if (WiFi.status() == WL_CONNECTED) {
    appendTelemetry("RSSI", true);
  } else {
    appendTelemetry("NO_WIFI", false);
    reconnectAttempts++;
    WiFi.reconnect();
  }

  currentSampleCount++;

  if (currentSampleCount >= MAX_SAMPLES) {
    appendTelemetry("END_TEST", false);
    appendSummary();

    isLoggingActive = false;

    Serial.println("[INFO] Fim da coleta.");
    Serial.print("[INFO] Amostras totais: ");
    Serial.println(currentSampleCount);
    Serial.print("[INFO] RSSI validos: ");
    Serial.println(validRssiSamples);
    Serial.print("[INFO] RSSI medio: ");
    Serial.println(getAverageRssi(), 2);
    Serial.print("[INFO] RSSI min: ");
    Serial.println(validRssiSamples > 0 ? rssiMin : 0);
    Serial.print("[INFO] RSSI max: ");
    Serial.println(validRssiSamples > 0 ? rssiMax : 0);
    Serial.print("[INFO] Desconexoes: ");
    Serial.println(disconnectCount);
    Serial.print("[INFO] Tentativas de reconexao: ");
    Serial.println(reconnectAttempts);
  }
}