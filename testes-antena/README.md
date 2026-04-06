# testes-antena/

Firmwares Arduino/ESP32 utilizados nos ensaios de validação de antenas Wi-Fi.
Cada sketch é um projeto Arduino independente e deve ser aberto pela pasta raiz no
Arduino IDE ou PlatformIO.

## Sketches

| Pasta | Função |
|---|---|
| `rf_baseline_logger/` | Loga RSSI continuamente para ensaios baseline (condição aberta) e in-case. Conecta ao AP de referência e grava leituras a cada 1 s pela serial. |
| `rf_autonomous_logger/` | Versão autônoma do logger: armazena os dados em memória flash sem depender de conexão serial ativa durante o ensaio. |
| `rf_autonomous_ping_tx_v2/` | Transmissor de ping em rajada. Envia pacotes ICMP em burst para o AP e registra latência e taxa de falha. Usado nos ensaios da Fase 2. |

## Hardware Alvo

- **MCU:** ESP32-WROOM-32
- **Upload:** USB via porta serial (115200 baud)
- **Dependências:** apenas bibliotecas nativas do ESP32 Arduino Core

## Como Usar

1. Abra a pasta do sketch desejado no Arduino IDE (ex: `rf_baseline_logger/`)
2. Selecione a placa **ESP32 Dev Module** e a porta COM correta
3. Ajuste as credenciais do AP de referência no início do arquivo `.ino`
4. Faça o upload e monitore a saída pela Serial Monitor (115200 baud)
5. Copie os logs para `dados-brutos/` com a nomenclatura padrão (`Ax_Ux_Tx.txt`)
