# ensaios-futuros/emi-emc/

Varreduras de EMI/EMC com sondas de campo próximo no analisador SA6.

## Objetivo

Mapear as fontes de interferência eletromagnética dentro do invólucro PA66 do
FRITG01LTE que possam degradar o sinal Wi-Fi da antena, incluindo:
- Conversor DC-DC (ruído de chaveamento)
- Modem SIM7600G (harmônicos LTE)
- Barramento CAN

## Equipamento Necessário

- Analisador de espectro SA6 (35–6200 MHz)
- Sondas de campo próximo (magnética H e elétrica E)
- Cabo SMA RG174 30 cm
- Gateway FRITG01LTE montado e energizado (12 V)

## Procedimento Previsto

1. Gateway ligado sem antena Wi-Fi conectada
2. Varredura de 35 MHz a 6200 MHz com sonda H em modo Max Hold
3. Aproximar sonda de cada componente e registrar picos
4. Repetir com gateway dentro do invólucro fechado
5. Comparar com baseline (ambiente sem o gateway)

## Status

- [ ] Sondas disponíveis para uso
- [ ] Procedimento detalhado elaborado
- [ ] Varreduras realizadas
- [ ] Análise concluída
