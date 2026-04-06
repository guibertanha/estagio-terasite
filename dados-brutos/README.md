# dados-brutos/

Logs brutos dos ensaios, exatamente como coletados no campo — sem processamento.
Nunca edite os arquivos nesta pasta; eles são a fonte de verdade dos experimentos.

## Estrutura

```
dados-brutos/
├── rssi-fase1/    # Fase 1: antenas A0, A1, A2, A3, A4 (sem A5)
├── rssi-fase2/    # Fase 2: comparativo A4 vs A5
└── ping/          # Ensaios de ping em rajada (Fase 2)
```

## Nomenclatura dos Arquivos

| Sufixo | Significado |
|---|---|
| `Rx` | Run baseline — antena em condição aberta (sem invólucro) |
| `CASEx` | Medição in-case — antena dentro do invólucro PA66 |
| `Ux` | Número da unidade do gateway testada (U1, U2, U3) |
| `Tx` | Número da tentativa/repetição do ensaio (T1, T2, T3) |

Exemplos: `A4_R1.txt`, `A4_CASE1.txt`, `A5_U2_T3.txt`, `Ping_A4_U1_T2.txt`

## rssi-fase1/

- Antenas testadas: A0 (ref), A1, A2, A3, A4
- Cada antena tem de 1 a 3 runs baseline (`_R1`, `_R2`, `_R3`) e 1 a 3 medições in-case (`_CASE1`, etc.)
- Arquivos são texto simples com uma amostra de RSSI por linha (dBm)
- Nota: A4 possui uma medição especial `A4_CASE3_antDif.txt` com antena diferente, para referência

## rssi-fase2/

- Antenas testadas: A4 e A5
- 3 unidades (U1, U2, U3) × 3 tentativas (T1, T2, T3) por antena
- A5 possui dados das 3 unidades; A4 possui U1 e U2 (U3 não realizada)

## ping/

- Antenas testadas: A0 (ref), A4, A5
- Formato: múltiplas rajadas de 100 pings cada
- Cada linha registra: número do ping, latência (ms), status (sucesso/falha), RSSI do enlace (dBm)
