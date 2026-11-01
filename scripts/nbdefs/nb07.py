from ._helpers import NB, SETUP


def build():
    n = NB()
    n.md("""
# 07 · Benchmark de engines: pandas × Polars × DuckDB × PySpark

**Coffee Big Data Intelligence**

> **Aviso central — leia antes de qualquer número:** este notebook separa **dois mundos**.
> **(1) Volume REAL** da cafeicultura/clima do projeto: **centenas de milhares de linhas**, cabe em qualquer notebook.
> **(2) Volume SINTÉTICO** (1M, 10M, 50M linhas): gerado aleatoriamente **apenas** para medir como as engines escalam. **Não representa volume real de café.** Chamar uma tabela pequena de *Big Data* só porque foi processada com Spark seria desonesto; por isso a pergunta aqui é: **a partir de qual escala o custo de uma engine distribuída se justifica?**

## Objetivos
1. Mostrar o **volume real** do projeto e quanto ele pesa em disco/memória.
2. Comparar as quatro engines em 4 operações, com **paridade de resultados** verificada.
3. Medir **tempo, pico de memória e custo de inicialização**, por processo isolado.
4. Estimar (**rotulado como extrapolação**) quando cada engine esgota um orçamento de memória.
5. Quantificar o efeito do **particionamento Parquet** e do problema de *arquivos pequenos*.
6. Demonstrar o gerador sintético com **limite de memória**.
""")
    n.code(SETUP + """
import json, tempfile, time
from pathlib import Path
import psutil
from coffeebdi import synth, bench""")
    n.md("""
## 1. Volume REAL do projeto

Contagem de linhas das tabelas efetivamente usadas (lago de dados local) e tamanho em disco por camada.
""")
    n.code("""
tabs = ["pam_municipio", "pam_uf", "dim_municipio", "conab_uf", "preco_cafe_mensal", "cambio_mensal", "ipca_mensal", "clima_diario",
        "clima_mensal", "clima_features", "painel_cafe_arabica"]
vol = pd.DataFrame([{"tabela": t, "linhas": int(q(f"select count(*) n from {t}").n[0]), "colunas": len(q(f"select * from {t} limit 0").columns)} for t in tabs]).set_index("tabela")
def du(p):
    p = Path(p); return sum(f.stat().st_size for f in p.rglob("*") if f.is_file()) / 1e6 if p.exists() else float("nan")
print("Tamanho em disco (MB):", {k: round(du(getattr(config, k)), 1) for k in ("BRONZE", "SILVER", "GOLD")})
print(f"Maior tabela real: {vol.linhas.idxmax()} com {vol.linhas.max():,} linhas")
vol
""")
    n.md("""
**Como ler:** a maior tabela é o **clima diário** (80 células × ~9 500 dias). Tudo o mais tem milhares de linhas. Para café, o gargalo **não** é volume — é **qualidade, cobertura e número efetivo de safras**. O notebook 04 mostra que o número de observações *independentes* é ≈ 13 anos, não 1 663 linhas.
""")
    n.md("""
## 2. Metodologia do benchmark

| Item | Decisão | Por quê |
|---|---|---|
| Isolamento | **um subprocesso por (engine, operação, tamanho)** | evita cache e memória residual de uma engine contaminar a outra |
| Tempo | mediana de *k* repetições de **ler + calcular + escrever Parquet** | inclui I/O, que domina em colunar |
| Inicialização | medida **à parte** (`startup_s`) e fora da mediana | JVM/Spark tem custo fixo que a mediana esconderia |
| Memória | **pico de RSS da árvore de processos** (inclui a JVM) | medir só o Python subestimaria o Spark |
| Orçamento | 8 GB e 4 threads para todos; processo é **morto** se estourar | comparação justa em hardware idêntico |
| Paridade | resultados salvos em Parquet e **checksum** comparado entre engines | velocidade sem resultado igual não vale nada |
| pandas | lê **só as colunas necessárias**, `date_as_object=False` | evita desvantagem artificial por má prática |

Operações: `filter_count` (filtro + contagem por ano), `monthly_agg` (agregação célula×ano×mês), `join_agg` (junção com dimensão + agregação por UF×ano), `rolling_30d` (janela móvel de 30 dias por célula; a mais cara).
""")
    n.code("""
R = json.load(open(config.OUTPUTS / "benchmark_results.json"))
res = pd.DataFrame(R["results"])
print("Máquina:", R["system"]); print("Configuração:", R["config"])
print(f"Dados reais usados: {R['real_rows']:,} linhas, {R['real_cells']} células")
print("Divergências de paridade entre engines:", R["parity_issues"] or "nenhuma")
print("Status das execuções:", res.status.value_counts().to_dict())
ORDEM = ["REAL", "1M", "10M", "50M"]; ENG = ["pandas", "polars", "duckdb", "spark"]; OPS = bench.OPS
res["label"] = pd.Categorical(res.label, ORDEM, ordered=True)
""")
    n.md("""
## 3. Tempo por operação

Tempo mediano (tabela em milissegundos; gráfico em segundos) de uma execução completa, **excluindo** a inicialização da engine.
""")
    n.code("""
T = res.pivot_table(index=["op", "label"], columns="engine", values="median_s", observed=True)[ENG]
print("Tempo mediano em MILISSEGUNDOS:"); display((1000 * T).round(1))
fig, axs = plt.subplots(1, 4, figsize=(14, 3.2), sharey=True)
cores = {"pandas": "#8d6e63", "polars": "#00897b", "duckdb": "#f9a825", "spark": "#c62828"}
for a, op in zip(axs, OPS):
    t = T.loc[op].loc[ORDEM]
    for e in ENG: a.plot(range(len(t)), t[e], "o-", color=cores[e], label=e)
    a.set_xticks(range(len(t))); a.set_xticklabels(t.index); a.set_yscale("log"); a.set_title(op, fontsize=9)
axs[0].set_ylabel("mediana (s, escala log)"); axs[0].legend(fontsize=7)
plt.tight_layout(); plt.savefig(FIG / "07_tempos.png"); plt.show()
""")
    n.md("""
**Como ler:** escala **logarítmica**. REAL (≈0,76M linhas) fica no extremo esquerdo, ao lado de 1M. Duas observações verificáveis nos números: (i) em REAL, as engines locais terminam entre ~1 e ~65 ms; (ii) em nenhum tamanho testado (até 50M) o Spark ficou mais rápido que as engines locais **nesta máquina de nó único**. Isso **não** significa que Spark seja ruim: ele foi projetado para **dados maiores que a memória de uma máquina** e para **clusters**, o que **não foi testado aqui** (e não pode ser concluído a partir deste experimento).
""")
    n.md("""
### 3.1 Aceleração relativa (quanto mais lenta é cada engine em relação à mais rápida?)

Razão = tempo da engine / menor tempo entre as engines, na mesma operação e tamanho. Valores próximos de 1 = empate técnico.
""")
    n.code("""
RATIO = T.div(T.min(axis=1), axis=0)
display(RATIO.round(1))
print("Razão mediana por engine (todas as operações e tamanhos):"); print(RATIO.median().round(1).to_string())
""")
    n.md("""
**Como ler:** em tempos de milissegundos (REAL, 1M), razões como "5×" correspondem a diferenças de **frações de segundo** — irrelevantes para o usuário. A razão só importa quando o tempo absoluto importa: observe 50M e `rolling_30d`.

## 4. Memória e custo de inicialização
""")
    n.code("""
P = res.pivot_table(index=["op", "label"], columns="engine", values="peak_rss_gb", observed=True)[ENG]
display(P.round(2))
S = res.groupby(["engine"]).startup_s.median().round(2)
print("Mediana do tempo de inicialização (s):", S.to_dict())
""")
    n.md("""
**Como ler:** `peak_rss_gb` é o pico da **árvore de processos**. Duas fontes de custo fixo: a JVM (Spark paga ~3 s e centenas de MB **mesmo para dados minúsculos**) e a importação das bibliotecas Python. Em REAL, a inicialização do Spark equivale a **~5 a ~16 vezes** o tempo de uma operação (seção 5).

### 4.1 Extrapolação do uso de memória (**ESTIMATIVA, não medição**)

Com 3 tamanhos sintéticos (1M, 10M, 50M) ajusta-se, por (engine, operação), uma reta `pico = a + b · linhas`. Isso permite estimar **qual tamanho estouraria um orçamento de memória** — **extrapolação linear com 3 pontos**: serve para ordem de grandeza, não para planejamento fino. O RSS do Spark reflete a política de *heap* da JVM e ele pode fazer *spill* em disco: a reta **não** é um limite real para ele (e seu valor extrapolado menor que o de DuckDB/Polars não significa que processe menos dados).
""")
    n.code("""
rows = []
NR = {"1M": 1e6, "10M": 1e7, "50M": 5e7}
for (e, op), g in res[res.label.isin(NR)].groupby(["engine", "op"], observed=True):
    x = np.array([NR[l] for l in g.label]); y = g.peak_rss_gb.values
    b, a = np.polyfit(x, y, 1); r2 = np.corrcoef(x, y)[0, 1] ** 2
    budget = R["config"]["mem_gb"]
    rows.append({"engine": e, "op": op, "bytes/linha (b)": b * 1e9, "base_GB (a)": a, "R²": r2,
                 "linhas no orçamento de 8 GB (milhões, EXTRAPOLADO)": (budget - a) / b / 1e6 if b > 0 else np.inf})
ext = pd.DataFrame(rows).set_index(["op", "engine"]).sort_index()
ext.round(2)
""")
    n.md("""
**Como ler:** `bytes/linha` é a inclinação da reta (custo marginal por linha); `base_GB` é o custo fixo. Um R² baixo ou um limite estimado muito diferente do medido sinalizam que a reta é **inadequada**. Em pandas, as quatro operações têm o menor limite estimado (63–422 milhões de linhas; `rolling_30d`, `monthly_agg` e `join_agg` ficam em ~63–78 milhões): é onde o processo seria morto primeiro pelo orçamento do harness, comportamento esperado de quem carrega tudo em RAM com cópias intermediárias.

## 5. Real × sintético: o que o benchmark permite concluir?
""")
    n.code("""
real = res[res.label == "REAL"].pivot_table(index="op", columns="engine", values="median_s", observed=True)[ENG]
fator = 50_000_000 / R["real_rows"]
print(f"O maior conjunto sintético (50M) tem {fator:,.0f}× as linhas do conjunto REAL ({R['real_rows']:,}).")
print("\\nREAL — tempo mediano (ms):"); display((1000 * real).round(1))
ini = res.groupby("engine").startup_s.median()
razao = pd.DataFrame({e: ini[e] / real[e] for e in ENG}).round(1)
print("Inicialização da engine ÷ tempo de UMA operação no REAL (por operação):"); display(razao)
""")
    n.md("""
**Conclusão defensável (e só ela):**

1. Para o volume **real** deste projeto, **pandas, Polars ou DuckDB** resolvem tudo em milissegundos. **Spark é custo sem benefício** nesse volume (a inicialização equivale a ~5–16 vezes o tempo de uma operação; para pandas e Polars, só importar a biblioteca já custa de ~4 a ~65 vezes o cálculo de uma operação em REAL).
2. Para **tabelas sintéticas de até 50M linhas em uma máquina de 14 núcleos e ~39 GB**, as engines locais continuam à frente. O ponto de virada do Spark **não foi atingido**; ele estaria em volumes maiores que a memória de um nó ou em cluster — **cenário não medido**.
3. **DuckDB e Polars** ficaram consistentemente entre as mais rápidas e com pouca memória, por serem colunares, vetorizadas e com execução *lazy*/pushdown. pandas funciona, mas carrega os dados em RAM e tem o maior custo de memória por linha (≈18–120 bytes/linha contra ≈2–52 de DuckDB/Polars).

Um projeto de café só passaria a precisar de engine distribuída se agregasse **séries de alta resolução** (ex.: milhões de pontos por talhão/sensor, imagens de satélite por pixel e data) — dados que **este projeto não usa**.

## 6. Particionamento Parquet (hive) e o problema dos arquivos pequenos

Experimento com 10M linhas sintéticas: filtro por `ano = 2015` e leitura total, em (a) arquivo único, (b) particionado por `ano` (14 arquivos), (c) particionado por `ano, mes` (165 arquivos).
""")
    n.code("""
pt = json.load(open(config.OUTPUTS / "benchmark_partition.json"))
part = pd.DataFrame({
    "layout": ["arquivo único", "partição ano", "partição ano/mês"],
    "arquivos": [1, pt["n_arquivos_ano"], pt["n_arquivos_ano_mes"]],
    "filtro ano=2015 (ms)": 1000 * np.array([pt["arquivo_unico_filtro_ano"], pt["part_ano_filtro_ano"], pt["part_ano_mes_filtro_ano"]]),
    "leitura total (ms)": 1000 * np.array([pt["arquivo_unico_scan_total"], pt["part_ano_scan_total"], pt["part_ano_mes_scan_total"]])}).set_index("layout")
part.round(1)
""")
    n.md("""
**Como ler:** a partição por `ano` acelera o **filtro** que usa essa coluna (o motor pula arquivos inteiros — *partition pruning*) e deixa a **leitura total** ligeiramente mais lenta (mais arquivos para abrir). Particionar por `ano/mês` (165 arquivos) fica **pior que por `ano`** nos dois testes (ainda melhor que o arquivo único no filtro, mas com a leitura total mais lenta): é o início do problema dos **arquivos pequenos**, que se agrava com mais partições. Regra prática: arquivos de dezenas a centenas de MB e partições por colunas de **baixa cardinalidade** usadas em filtros. **Os tempos aqui são de milissegundos**; o efeito é qualitativo — com dados reais deste projeto, particionar é **desnecessário** e mantido só como prática demonstrativa (por UF/ano nas tabelas silver).

## 7. Gerador sintético com limite de memória

O gerador escreve em **blocos**: o pico de memória depende do tamanho do bloco, **não** do total de linhas. O parâmetro `max_mem_gb` define o bloco (25% do limite, máx. 5M linhas).
""")
    n.code("""
print("Linhas por bloco conforme o limite de memória:")
print(pd.Series({f"{g} GB": synth.chunk_rows_for_memory(g) for g in (0.1, 0.5, 2, 8, 32)}, name="linhas/bloco").to_string())
import subprocess, sys
SRC = str(Path(synth.__file__).resolve().parents[1])
rows = []
with tempfile.TemporaryDirectory() as td:
    for lim in (0.1, 0.5, 2.0):
        code = f"from coffeebdi import synth; i = synth.generate(10_000_000, r'{td}/s_{lim}.parquet', seed=1, max_mem_gb={lim}); print(i['bytes'], i['seconds'])"
        p = subprocess.Popen([sys.executable, "-I", "-c", code], env={**__import__("os").environ, "PYTHONPATH": SRC}, stdout=subprocess.PIPE, stderr=subprocess.DEVNULL, text=True)
        ps = psutil.Process(p.pid); peak = 0
        while p.poll() is None:
            try: peak = max(peak, ps.memory_info().rss)
            except psutil.Error: break
            time.sleep(0.01)
        by, sec = p.stdout.read().split()[-2:]
        rows.append({"limite max_mem_gb": lim, "linhas/bloco": synth.chunk_rows_for_memory(lim), "arquivo (MB)": int(by) / 1e6, "tempo (s)": float(sec), "pico RSS do processo (MB)": peak / 1e6})
pd.DataFrame(rows).set_index("limite max_mem_gb").round(1)
""")
    n.md("""
**Como ler:** cada limite roda em **processo próprio** (medir dois limites no mesmo processo se confunde com a memória que o alocador já reservou). Compare `pico RSS` com `linhas/bloco`: bloco menor ⇒ pico menor (aqui ≈325 → 489 → 604 MB), **sem custo mensurável de tempo** nesta máquina (≈1,4 s nos três casos). Atenção: o sorteio aleatório é feito por bloco, então tamanhos de bloco diferentes geram dados *diferentes* (o determinismo vale para o par semente + limite de memória, e o tamanho do arquivo varia ~7%). O gerador respeita o **orçamento** pedido; o RSS inclui o interpretador e as bibliotecas (≈100–200 MB fixos), então para limites muito pequenos o piso é o próprio Python. O arquivo traz o metadado Parquet `synthetic=true`, para que nenhum leitor confunda este dado com volume real. **Nunca** apresente estes números como produção cafeeira.

## 8. Reexecução ao vivo (opcional, 1M linhas)

Para validar a **reprodutibilidade**: repete-se, agora, `filter_count` e `monthly_agg` em 1M linhas para as três engines locais (Spark fica de fora: seu custo de inicialização já foi medido nas seções 3–4). Diferenças pequenas em relação à tabela da seção 3 refletem **ruído da máquina** (outros processos, térmica).
""")
    n.code("""
src = config.SYNTH / "SYNTH_clima_1M.parquet"
if src.exists():
    live = []
    for op in ("filter_count", "monthly_agg"):
        for e in ("pandas", "polars", "duckdb"):
            r = bench.run_one(e, op, src, src.with_name(src.stem + "_dim_cell.parquet"), threads=4, mem_gb=8.0, reps=5, timeout_s=300)
            live.append({"op": op, "engine": e, "status": r["status"], "mediana ao vivo (s)": r.get("median_s", np.nan)})
    live = pd.DataFrame(live).merge(res[res.label == "1M"][["op", "engine", "median_s"]].rename(columns={"median_s": "mediana gravada (s)"}), on=["op", "engine"])
    display(live.round(4))
else:
    print("Arquivo sintético 1M ausente — gere com: python scripts/run_benchmark.py (não afeta o restante do projeto).")
""")
    n.md("""
## 9. Resumo interpretativo

| Pergunta | Resposta | Evidência / limite |
|---|---|---|
| O projeto é "Big Data" em volume? | **Não**: ≈0,76M linhas na maior tabela | seção 1 |
| Qual engine usar para os dados reais? | qualquer uma local; DuckDB/Polars por ergonomia e memória | seção 3, 5 |
| Spark é mais rápido em 50M? | **Não** nesta máquina de nó único | seção 3; cluster **não testado** |
| Quando faria sentido Spark? | dados maiores que a RAM ou cluster; **não medido aqui** | seção 5 |
| Particionar ajuda? | ajuda filtros pela coluna de partição; arquivos pequenos prejudicam | seção 6 (milissegundos) |
| As engines dão o mesmo resultado? | sim, checksum igual em todas as execuções | seção 2 |

**Limites do benchmark:** uma única máquina (macOS, arm64, 14 núcleos, ~39 GB); dados sintéticos com distribuição simples; 4 operações; SSD local. Resultados em outro hardware, com disco em rede ou dados com chaves de alta cardinalidade **podem inverter** o ranking.

## Exercícios
1. Gere um sintético de 100M linhas com `max_mem_gb=4` e rode `monthly_agg` em DuckDB e pandas: o pandas ultrapassa o orçamento de 8 GB? O que o harness registra?
2. Rode o benchmark com `BENCH_THREADS=1` e `=8`: qual engine escala melhor com threads?
3. Reparticione o sintético de 10M por `cell_id` (alta cardinalidade) e meça o filtro por ano. O que acontece?
4. Por que medir `startup_s` separado da mediana muda a conclusão para dados pequenos?
5. A extrapolação linear de memória é confiável para `rolling_30d` em Spark? Justifique.
""")
    return n
