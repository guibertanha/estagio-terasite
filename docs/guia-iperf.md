\# iPerf3 — Guia rápido (Terasite)



\## Servidor (no notebook)

iperf3 -s



\## Cliente (no dispositivo)

Upload (cliente -> servidor):

iperf3 -c <IP\_DO\_NOTEBOOK> -t 20



Download (servidor -> cliente):

iperf3 -c <IP\_DO\_NOTEBOOK> -t 20 -R



\## Porta

Padrão: 5201/TCP (regra de entrada liberada no firewall do notebook)



\## Dicas

\- Rodar 3 vezes por cenário e registrar média

\- Manter AP 2.4GHz em canal fixo e 20 MHz



