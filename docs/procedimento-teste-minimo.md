\# Procedimento — Teste mínimo (Wi-Fi 2.4 GHz in-box)



\## Objetivo

Comparar antenas (in-box, PA66) com métricas: RSSI médio, variação (std), disconnects.



\## Setup do AP (roteador)

\- 2.4 GHz apenas (se possível)

\- Canal fixo: 1 OU 6 OU 11 (escolher 1)

\- Largura: 20 MHz

\- SSID fixo e senha fixa



Registrar aqui:

\- SSID:

\- Canal:

\- Largura:

\- Local:

\- Distância (m):



\## Variáveis de teste

\- Antena: A1/A2/...

\- Posição interna: P1/P2/P3

\- LTE: OFF / ON (quando aplicável)

\- Distância: 2 m e 10 m (ou perto/limite)



\## Procedimento por cenário (5 minutos)

1\) Montar antena + posição + strain relief

2\) Fechar caixa

3\) Ligar dispositivo e iniciar log serial

4\) Rodar 5 minutos

5\) Salvar log CSV: A?\_P?\_LTE?\_Xm.csv

6\) Rodar script: analisar\_rssi\_csv.py e registrar métricas no resultados\_template.csv

7\) Foto do posicionamento interno (antes de fechar) + foto da bancada (distância)



\## Saídas/Artefatos

\- Logs: C:\\Terasite\\Antenas\\Logs\\

\- Fotos: C:\\Terasite\\Antenas\\Fotos\\

\- Planilha (CSV): C:\\Terasite\\Antenas\\Docs\\resultados\_template.csv



\## Critérios de decisão (simples)

\- Melhor RSSI médio (menos negativo) ganha pontos

\- Menor variação (std) ganha pontos

\- Menos disconnects é obrigatório

\- Se LTE ON derruba muito: investigar roteamento/posição e re-testar



