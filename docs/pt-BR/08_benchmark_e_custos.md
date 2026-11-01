# 08 · Benchmark de engines e custos computacionais

> **Todos os números abaixo** vêm de `outputs/benchmark_results.json` (execução registrada) e do notebook 07. **Dados sintéticos (1M, 10M, 50M) não representam café.** A linha `REAL` usa o clima diário real do projeto (759 760 linhas).

## 1. Metodologia

| Item | Decisão |
|---|---|
| Isolamento | um **subprocesso por (engine, operação, tamanho)** |
| Tempo | mediana de *k* repetições de **ler + calcular + escrever Parquet** (7 em REAL, 5 em 1M, 3 em 10M, 2 em 50M — menos repetições onde cada uma é cara) |
| Inicialização | `startup_s` medido **à parte**; para Spark, criação da sessão + 1ª ação |
| Memória | **pico de RSS da árvore de processos** (inclui a JVM), amostrado a cada 50 ms |
| Orçamento | 8 GB e 4 threads para todas; o harness **mata** o processo se estourar |
| Paridade | cada resultado é gravado em Parquet; **checksums** conferidos entre engines (`parity_issues` vazio) |
| pandas | lê só as colunas necessárias (`pyarrow`), `date_as_object=False` — sem desvantagem artificial |
| Máquina | macOS 15, arm64, 14 núcleos, 38,7 GB de RAM, Python 3.11.9, pandas 3.1.0, Polars 2.1.0, DuckDB 2.0.0, PySpark 4.3.0 |

Operações: `filter_count`, `monthly_agg`, `join_agg`, `rolling_30d`.

## 2. Tempos medianos (segundos)

| Operação | Tamanho | pandas | Polars | DuckDB | Spark |
|---|---|---:|---:|---:|---:|
| filter_count | REAL | 0,004 | 0,001 | 0,012 | 0,213 |
| | 50M | 0,223 | 0,053 | 0,095 | 1,033 |
| monthly_agg | REAL | 0,021 | 0,008 | 0,018 | 0,254 |
| | 50M | 1,243 | 0,338 | 0,415 | 2,610 |
| join_agg | REAL | 0,039 | 0,006 | 0,016 | 0,332 |
| | 50M | 2,258 | 0,336 | 0,307 | 1,398 |
| rolling_30d | REAL | 0,064 | 0,018 | 0,040 | 0,616 |
| | 50M | 5,346 | 1,437 | 1,742 | 23,397 |

(Tabela completa por tamanho no notebook 07.)

**Razão mediana vs. a mais rápida** (todas as operações e tamanhos): Polars 1,0 · DuckDB 2,2 · pandas 3,7 · Spark 22,0.

## 3. Inicialização

| Engine | mediana de `startup_s` |
|---|---:|
| DuckDB | 0,04 s |
| Polars | 0,08 s |
| pandas | 0,28 s (importação) |
| **Spark** | **3,34 s** (JVM + sessão) |

No volume REAL, a inicialização do Spark equivale a ≈ 5–16× o tempo de **uma operação**.

## 4. Memória: custo por linha e extrapolação (**estimativa**)

Ajuste linear `pico = a + b·linhas` com 3 pontos (1M, 10M, 50M) por (engine, operação):

| Operação | pandas (bytes/linha) | Polars | DuckDB | Spark |
|---|---:|---:|---:|---:|
| filter_count | 18 | 3 | 2 | 28 |
| monthly_agg | 106 | 9 | 9 | 18 |
| join_agg | 98 | 10 | 6 | 17 |
| rolling_30d | 120 | 53 | 31 | 31 |

**Linhas no orçamento de 8 GB (milhões, EXTRAPOLADO):** pandas 63–422; Polars 149–2 583; DuckDB 248–3 522; Spark 226–385 (**não confiável para Spark**: o RSS reflete o *heap* da JVM e há *spill* em disco).

> **Aviso:** extrapolação linear com 3 pontos. Serve para **ordem de grandeza**, não para dimensionar infraestrutura.

## 5. Particionamento Parquet (10M linhas sintéticas)

| Layout | Arquivos | filtro `ano=2015` | leitura total |
|---|---:|---:|---:|
| arquivo único | 1 | 17,4 ms | 18,9 ms |
| partição `ano` | 14 | **7,4 ms** | 25,4 ms |
| partição `ano/mês` | 165 | 12,8 ms | 27,0 ms |

A partição por `ano` acelera o filtro por pruning e deixa a leitura total um pouco mais lenta; `ano/mês` já mostra o custo de **arquivos pequenos**. Tempos de milissegundos: efeito **qualitativo**.

## 6. Custos computacionais do pipeline real

| Etapa | Custo observado |
|---|---|
| ingestão completa (rede) | dominada por latência das APIs; PAM + NASA POWER em paralelo (4 *workers*) |
| reexecução da ingestão | segundos (tudo `cached`/`unchanged`; só a janela recente é rebuscada) |
| silver + gold | segundos (DuckDB sobre ≈ 0,8M linhas) |
| 8 notebooks | ≈ 1–13 s cada (o maior: notebook 06, com vários *backtests* de Ridge/XGBoost) |
| backtests A + B | ≈ 2–3 s |
| espaço | bronze ≈ 17 MB, silver ≈ 7 MB, gold ≈ 1 MB; benchmarks sintéticos ≈ 0,6 GB em `data/bench/` |

**Custo escondido nº 1:** o benchmark sintético de 50M ocupa ≈ 500 MB em disco e leva dezenas de segundos para regerar — fora do `git`.
**Custo escondido nº 2:** o Spark exige **Java** (o projeto detecta ou usa um JDK local em `.tools/`).

## 7. Conclusões defensáveis

1. Para o volume **real**, qualquer engine local resolve em milissegundos; **Spark é custo sem benefício** (JVM de ~3 s).
2. Até **50M linhas sintéticas** em um nó de 14 núcleos, **Polars/DuckDB** lideram; pandas é mais lento e gasta mais memória; Spark **não ficou à frente** em nenhum caso.
3. Isso **não** diz que Spark seja ruim: o cenário em que ele se justifica (dados maiores que a RAM, cluster) **não foi medido**.

## 8. Limites

Uma única máquina; SSD local; dados sintéticos de distribuição simples; 4 operações; threads fixas em 4. Resultados podem inverter com outros dados, disco ou escala.
