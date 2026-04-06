# ensaios-futuros/

Planejamento e coleta de dados dos próximos ciclos de ensaios.
As subpastas estão criadas e prontas para receber procedimentos, dados e resultados
conforme os ensaios forem realizados.

## Subpastas

### termomecanico/
Ensaios termomecânicos nas máquinas da construtora (TM-01, TM-02, TM-03).
- Objetivo: avaliar o desempenho e a integridade mecânica das antenas finalistas
  (A4 e A5) sob vibração, choque e variação de temperatura em campo.
- Referência: `datasheets/maquinas-campo/`

### emi-emc/
Varreduras de EMI/EMC com sondas de campo próximo no analisador SA6.
- Objetivo: mapear fontes de interferência eletromagnética internas ao invólucro
  PA66 (conversor DC-DC, modem SIM7600G, barramento CAN) que possam degradar o sinal Wi-Fi.
- Equipamento: SA6 + sondas de campo próximo + cabo SMA RG174

### campo/
Ensaios de RF em campo real com iPerf3 nas máquinas da construtora.
- Objetivo: validar throughput e cobertura Wi-Fi com o gateway instalado na posição
  definitiva na máquina, em condição operacional.
- Inclui: survey de posicionamento, mapeamento de cobertura e ensaios de carga.
- Guia de operação: `docs/guia-iperf.md`
