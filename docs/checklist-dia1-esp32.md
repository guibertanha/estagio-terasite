\# CHECKLIST — Dia 1 (ESP32 + Roteador + Teste RSSI/Throughput)



\## Antes de sair de casa (2 min)

\- \[ ] Notebook carregado + fonte

\- \[ ] Cabo USB do ESP32

\- \[ ] Roteador de teste + fonte (se tiver)

\- \[ ] Gateway/caixa + antenas + fita/adesivo + abraçadeira (strain relief)

\- \[ ] Abrir pasta: C:\\Terasite\\Antenas\\



\## 1) Roteador (sem internet mesmo) — Meta: Wi-Fi controlado

\- \[ ] Ligar na tomada (WAN pode ficar vazio)

\- \[ ] Entrar no painel (IP típico: 192.168.0.1 / 192.168.1.1)

\- \[ ] Configurar:

&nbsp; - \[ ] 2.4 GHz ligado (5 GHz opcional desligar)

&nbsp; - \[ ] Canal fixo: 1 OU 6 OU 11

&nbsp; - \[ ] Largura: 20 MHz

&nbsp; - \[ ] SSID: TERASITE\_TESTE\_24G

&nbsp; - \[ ] Senha fixa (anotar)



\## 2) Notebook — preparar servidor e IP

\- \[ ] Conectar no Wi-Fi TERASITE\_TESTE\_24G

\- \[ ] Rodar: ipconfig (anotar IPv4 do notebook)

\- \[ ] Rodar servidor iPerf: iperf3 -s

\- \[ ] (Firewall já liberado 5201/TCP)



\## 3) ESP32 — identificar porta COM

\- \[ ] Conectar ESP32 no USB

\- \[ ] Abrir: Gerenciador de Dispositivos

\- \[ ] Ver em "Portas (COM e LPT)" qual COM apareceu

\- \[ ] Se aparecer "Dispositivo desconhecido":

&nbsp; - \[ ] Tirar print e instalar driver correto (CP210x ou CH340)



\## 4) ESP32 — subir firmware de teste (RSSI logger)

\- \[ ] Abrir Arduino IDE

\- \[ ] Selecionar placa ESP32 correta (Tools > Board)

\- \[ ] Selecionar porta COM correta (Tools > Port)

\- \[ ] Colar sketch RSSI logger (fornecido pelo copiloto)

\- \[ ] Upload



\## 5) Coleta de RSSI (por cenário)

Cenário = Antena + Posição + LTE(ON/OFF) + Distância

\- \[ ] Montar antena e posição (foto)

\- \[ ] Fechar caixa

\- \[ ] Abrir Serial Monitor e coletar 5 min

\- \[ ] Salvar CSV em:

&nbsp; C:\\Terasite\\Antenas\\Logs\\A?\_P?\_LTEON\_2m.csv (exemplo)

\- \[ ] Rodar análise:

&nbsp; python C:\\Terasite\\Antenas\\Scripts\\analisar\_rssi\_csv.py <caminho\_do\_csv>

\- \[ ] Preencher 1 linha no:

&nbsp; C:\\Terasite\\Antenas\\Docs\\resultados\_template\_ptbr.csv



\## 6) Throughput (quando tiver cliente iPerf)

\- \[ ] Cliente roda:

&nbsp; iperf3 -c <IP\_NOTEBOOK> -t 20

&nbsp; iperf3 -c <IP\_NOTEBOOK> -t 20 -R

\- \[ ] Registrar Mbps na planilha



\## 7) Regra de ouro (qualidade de dados)

\- \[ ] Caixa fechada SEMPRE

\- \[ ] Mesma distância e orientação (marcar chão)

\- \[ ] 3 repetições por cenário

\- \[ ] Fotos + logs + observação curta



