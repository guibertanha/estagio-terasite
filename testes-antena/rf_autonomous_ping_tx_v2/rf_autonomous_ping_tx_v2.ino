/**
 * @file    rf_autonomous_ping_tx_v2.ino
 * @brief   Firmware de estresse TX + latência para ESP32 via LittleFS.
 * @details Gera tráfego Wi-Fi em rajadas de ping contra o gateway local para:
 *          1) excitar o rádio e facilitar observação no SA6
 *          2) registrar latência e falhas de rajada em log
 *
 * Uso:
 * - Alimentar por bateria/fonte para teste autônomo
 * - Depois usar PuTTY/Serial para exportar o log
 */

#include <WiFi.h>
#include <LittleFS.h>
#include <ESPping.h>   

// ======================================================
// CONFIGURAÇÕES DA BANCADA
// ======================================================
const char* WIFI_SSID = "AP 101 - 2.4GHz";
const char* WIFI_PASS = "guilherme2";

const char* LOG_FILE_PATH = "/log_ping.txt";

// Tráfego
const int PINGS_PER_BURST = 5;
const unsigned long BURST_INTERVAL_MS = 50;
const int MAX_BURSTS = 300;               // ~3 minutos

// CLI e conexão
const unsigned long CLI_TIMEOUT_MS = 10000;
const unsigned long WIFI_CONNECT_TIMEOUT_MS = 15000;

IPAddress gatewayIP;

// Estado
bool isLoggingActive = false;
int currentBurstCount = 0;
int failCount = 0;
int successCount = 0;

// Estatísticas de latência
float latencySum = 0.0f;
float latencyMin = 0.0f;
float latencyMax = 0.0f;
bool latencyStatsStarted = false;

// ======================================================
// FUNÇÕES AUXILIARES
// ======================================================

void resetStats() {
  currentBurstCount = 0;
  failCount = 0;
  successCount = 0;
  latencySum = 0.0f;
  latencyMin = 0.0f;
  latencyMax = 0.0f;
  latencyStatsStarted = false;
}

void updateLatencyStats(float latencyMs) {
  if (!latencyStatsStarted) {
    latencyMin = latencyMs;
    latencyMax = latencyMs;
    latencyStatsStarted = true;
  } else {
    if (latencyMs < latencyMin) latencyMin = latencyMs;
    if (latencyMs > latencyMax) latencyMax = latencyMs;
  }

  latencySum += latencyMs;
}

float getAverageLatency() {
  if (successCount <= 0) return 0.0f;
  return latencySum / (float)successCount;
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
    Serial.println("[ERROR] Falha ao abrir o log para escrita.");
    return;
  }

  logFile.println(line);
  logFile.close();
}

void clearLogData() {
  if (LittleFS.exists(LOG_FILE_PATH)) {
    LittleFS.remove(LOG_FILE_PATH);
  }
  Serial.println("[OK] Log apagado. Reinicie a placa para nova coleta.");
}

void exportLogData() {
  File logFile = LittleFS.open(LOG_FILE_PATH, FILE_READ);
  if (!logFile) {
    Serial.println("[INFO] Nenhum log encontrado.");
    return;
  }

  Serial.println("\n--- INICIO DO LOG DE ESTRESSE ---");
  while (logFile.available()) {
    Serial.write(logFile.read());
  }
  Serial.println("--- FIM DO LOG DE ESTRESSE ---");
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

  Serial.print("[INFO] Caminho: ");
  Serial.println(LOG_FILE_PATH);
  Serial.print("[INFO] Tamanho (bytes): ");
  Serial.println(size);
}

bool connectWiFi() {
  WiFi.mode(WIFI_STA);
  WiFi.begin(WIFI_SSID, WIFI_PASS);

  unsigned long startMs = millis();
  Serial.print("Conectando ao WiFi");

  while (WiFi.status() != WL_CONNECTED &&
         (millis() - startMs) < WIFI_CONNECT_TIMEOUT_MS) {
    delay(250);
    Serial.print(".");
  }

  Serial.println();
  return (WiFi.status() == WL_CONNECTED);
}

void appendStartLine() {
  String line = "";
  line += "START_TEST";
  line += ",ALVO=";
  line += gatewayIP.toString();
  line += ",SSID=";
  line += WIFI_SSID;
  line += ",CHANNEL=";
  line += WiFi.channel();
  line += ",BSSID=";
  line += getBSSIDString();
  line += ",RSSI_LINK=";
  line += WiFi.RSSI();

  appendRawLine(line);
}

void appendSummaryLine() {
  float failRate = 0.0f;
  if (currentBurstCount > 0) {
    failRate = (100.0f * (float)failCount) / (float)currentBurstCount;
  }

  String line = "END_TEST";
  line += ",TOTAL_BURSTS=" + String(currentBurstCount);
  line += ",OK=" + String(successCount);
  line += ",FAILS=" + String(failCount);
  line += ",FAIL_RATE_PCT=" + String(failRate, 2);
  line += ",LAT_AVG_MS=" + String(getAverageLatency(), 2);
  line += ",LAT_MIN_MS=" + String(latencyStatsStarted ? latencyMin : 0.0f, 2);
  line += ",LAT_MAX_MS=" + String(latencyStatsStarted ? latencyMax : 0.0f, 2);
  line += ",CHANNEL=" + String(WiFi.channel());
  line += ",BSSID=" + getBSSIDString();
  line += ",RSSI_LINK=" + String(WiFi.status() == WL_CONNECTED ? WiFi.RSSI() : 0);

  appendRawLine(line);
}

// ======================================================
// SETUP
// ======================================================

void setup() {
  Serial.begin(115200);
  delay(1000);

  if (!LittleFS.begin(true)) {
    Serial.println("[FATAL] Falha no LittleFS.");
    return;
  }

  resetStats();

  Serial.println("\n\n=== FROTALL: TESTE DE TX + LATENCIA (SA6) V2 ===");
  Serial.println("Comandos (10s):");
  Serial.println(" [d] - Exportar log");
  Serial.println(" [c] - Apagar log");
  Serial.println(" [i] - Info do log");
  Serial.println(" Timeout -> inicia teste autonomo");

  unsigned long bootTime = millis();
  bool userInteracted = false;

  while (millis() - bootTime < CLI_TIMEOUT_MS) {
    if (Serial.available()) {
      char cmd = Serial.read();

      if (cmd == 'd' || cmd == 'D') {
        exportLogData();
        userInteracted = true;
        while (true) delay(100);
      } else if (cmd == 'c' || cmd == 'C') {
        clearLogData();
        userInteracted = true;
        while (true) delay(100);
      } else if (cmd == 'i' || cmd == 'I') {
        printLogInfo();
        userInteracted = true;
        while (true) delay(100);
      }
    }
  }

  if (!userInteracted) {
    Serial.println("\n[INFO] Iniciando modo autonomo de estresse TX...");
    appendRawLine("");
    appendRawLine("############################################################");
    appendRawLine("# NOVO ENSAIO");
    appendRawLine("############################################################");

    if (!connectWiFi()) {
      appendRawLine("START_FAIL,REASON=WIFI_TIMEOUT");
      Serial.println("[ERROR] Falha na conexao WiFi (timeout).");
      return;
    }

    gatewayIP = WiFi.gatewayIP();

    Serial.println("[OK] Conectado!");
    Serial.print("[INFO] Gateway: ");
    Serial.println(gatewayIP);
    Serial.print("[INFO] Canal: ");
    Serial.println(WiFi.channel());
    Serial.print("[INFO] BSSID: ");
    Serial.println(getBSSIDString());
    Serial.print("[INFO] RSSI do link: ");
    Serial.println(WiFi.RSSI());

    appendStartLine();
    isLoggingActive = true;
  }
}

// ======================================================
// LOOP PRINCIPAL
// ======================================================

void loop() {
  if (!isLoggingActive) return;

  if (currentBurstCount >= MAX_BURSTS) {
    appendSummaryLine();
    isLoggingActive = false;

    Serial.println("\n[INFO] Teste finalizado.");
    Serial.print("[INFO] Bursts OK: ");
    Serial.println(successCount);
    Serial.print("[INFO] Bursts FAIL: ");
    Serial.println(failCount);
    Serial.print("[INFO] Latencia media: ");
    Serial.println(getAverageLatency(), 2);
    Serial.println("[INFO] Pode abrir a caixa e exportar o log.");
    return;
  }

  if (WiFi.status() != WL_CONNECTED) {
    failCount++;
    currentBurstCount++;

    String line = String(millis());
    line += ",PING_BURST_FAIL";
    line += ",IP=NA";
    line += ",LATENCIA_MS=NA";
    line += ",REASON=WIFI_DISCONNECTED";
    appendRawLine(line);

    Serial.println("TX FALHA | WiFi desconectado");
    delay(BURST_INTERVAL_MS);
    return;
  }

  bool success = Ping.ping(gatewayIP, PINGS_PER_BURST);
  float latencia = Ping.averageTime();

  String logLine = String(millis()) + ",";

  if (success) {
    successCount++;
    updateLatencyStats(latencia);

    logLine += "PING_BURST_OK";
    logLine += ",IP=" + gatewayIP.toString();
    logLine += ",LATENCIA_MS=" + String(latencia, 2);
    logLine += ",CHANNEL=" + String(WiFi.channel());
    logLine += ",BSSID=" + getBSSIDString();
    logLine += ",RSSI_LINK=" + String(WiFi.RSSI());

    Serial.print("TX OK | Latencia: ");
    Serial.print(latencia, 2);
    Serial.println(" ms");
  } else {
    failCount++;

    logLine += "PING_BURST_FAIL";
    logLine += ",IP=" + gatewayIP.toString();
    logLine += ",LATENCIA_MS=NA";
    logLine += ",CHANNEL=" + String(WiFi.channel());
    logLine += ",BSSID=" + getBSSIDString();
    logLine += ",RSSI_LINK=" + String(WiFi.RSSI());

    Serial.println("TX FALHA | Pacote perdido");
  }

  appendRawLine(logLine);
  currentBurstCount++;

  delay(BURST_INTERVAL_MS);
}