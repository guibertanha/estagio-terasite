# _arquivo — Scripts arquivados

Esta pasta contém scripts que foram **substituídos** durante a refatoração de
`analise-dados/` (abril/2026). Estão preservados apenas para referência
histórica e **não devem ser executados** — os caminhos hardcoded apontam para
o ambiente de desenvolvimento original e as funcionalidades foram absorvidas
pelos scripts ativos.

---

## ping_relatorio.py

**Por que foi arquivado:** Redundância com `rf_ping_masterblaster.py`. Ambos
liam os mesmos arquivos de ping, produziam os mesmos tipos de saída (CSV,
PNG, TXT) e compartilhavam ~80% do código. As únicas diferenças eram:

- Menos gráficos (3 vs 6)
- Sem resumo por unidade (`build_unit_summary`)
- Sem checagem de consistência de canal/BSSID
- Apontava para `OUTPUT_DIR = Relatorio_Ping_Executivo` em vez de
  `Relatorio_Engenharia_Ping`

**Substituído por:** `../rf_ping_masterblaster.py`

O único recurso útil deste script — o *fallback* que recalcula métricas
quando `END_TEST` está ausente — foi incorporado em
`../utils/ping_parser.py:parse_single_log()`.

---

## rf_baseline_stats.py

**Por que foi arquivado:** Subconjunto das funcionalidades do
`rf_masterblaster.py`. Processava apenas arquivos de baseline (`A*_R*`),
usava `pd.read_csv()` como parser (abordagem diferente do regex canônico) e
produzia saída apenas no terminal, sem CSV ou PNG.

Problemas adicionais:
- `LOG_DIR` apontava para `C:\Terasite\Antenas\Logs` (inexistente no repo)
- Não calculava p90, máximo, BSSID ou canal

**Substituído por:** `../rf_masterblaster.py` (carrega baseline via
`FASE1_FILE_MAP`, cenário `"BASE"`, e gera todas as métricas inclusive p90)

---

## rf_incase_timeseries.py

**Por que foi arquivado:** Script de visualização pontual desenvolvido no
início do projeto, com nomenclatura de arquivos desatualizada. Problemas:

- `target_files` hardcoded com nomes antigos (`Ping_A0`, `Ping_A1`, etc.),
  incompatíveis com a estrutura atual (`Ping_A0_U1_T1.txt`)
- Suportava apenas uma run por antena; sem estrutura multi-unidade/multi-teste
- `LOG_DIR` apontava para `C:\Terasite\Antenas\Logs\Log Pings`
- Eixo Y fixo em `[0, 150]` ms — corta outliers sem aviso
- `plt.ylim` e `plt.show()` hardcoded
- Sem saída CSV

**Substituído por:** `../rf_ping_masterblaster.py` —
função `save_timeline_by_run()`, que gera subplots por ensaio para todos os
arquivos na pasta `dados-brutos/ping/`, com escala dinâmica.
