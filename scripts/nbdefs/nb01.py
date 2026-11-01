from ._helpers import NB, SETUP


def build():
    n = NB()
    n.md("""
# 01 · Exploração das fontes de dados

**Coffee Big Data Intelligence** — cafeicultura brasileira (foco inicial: São Paulo)

## Perguntas que o projeto quer responder
1. Quais regiões têm maior **produtividade** de café?
2. Como a **produção** evoluiu?
3. Qual a relação entre **clima** e produtividade? (associação, **não** causalidade)
4. É possível **prever** a produção de uma região com dados históricos?

## Princípio deste notebook
Antes de qualquer análise, **investigar cada fonte**: o que mede, em que granularidade e unidade, com que atualização, sob qual licença e quais são seus limites — e **medir o volume real** dos dados. Datas de verificação: **2026-10-31**.

> **Big Data?** O volume real deste projeto é pequeno (veja a seção 5). Usamos DuckDB/Spark para demonstrar uma arquitetura que *escala* e **medimos quando ela compensa** (notebook 07) — sem chamar de "Big Data" uma tabela pequena só porque passou pelo Spark.
""")
    n.code(SETUP)
    n.md("""
## 1. Catálogo das fontes (verificado)

| Fonte | O que fornece | Granularidade | Unidade | Atualização | Licença / termos | Acesso verificado | Uso no projeto |
|---|---|---|---|---|---|---|---|
| **IBGE SIDRA – PAM, tabela 1613** (lavouras permanentes) | área destinada à colheita, área colhida, quantidade produzida, rendimento médio, valor da produção | município × ano; UF; Brasil | ha, t, kg/ha, mil R$ | anual (1974–2025 na data da verificação) | dados públicos do IBGE (cite a fonte) | ✅ API v3 | **base do estudo** |
| **IBGE Malhas e Localidades; Censo 2022 (tabela 4714)** | municípios, microrregião, centróide, área, população | município | km², hab. | estável / decenal | dados públicos do IBGE | ✅ API | **indicadores territoriais** |
| **NASA POWER** (reanálise MERRA-2/GEOS) | T2M, T2M_MAX, T2M_MIN, PRECTOTCORR | grade 0,5°×0,625° (~55×65 km), diário | °C, mm/dia | defasagem de dias a meses | dados abertos da NASA (cite *NASA POWER*) | ✅ API | **clima** (cobertura completa e homogênea) |
| **CONAB – séries históricas do café** | área, produtividade e produção por UF (arábica e conilon) | UF × safra | ha, sc/ha, mil sacas | 4 levantamentos por ano | conteúdo do site sob **CC BY-ND 3.0** (sem derivações) | ✅ XLS | **validação cruzada por UF** (não redistribuímos) |
| **Banco Mundial – Pink Sheet** | preço do café (indicador ICO) arábica e robusta | mensal, internacional | US$/kg | mensal (link muda a cada edição) | **não confirmei a licença** (página de termos gerais indica uso não comercial para materiais; `datasets` têm termos próprios) | ✅ XLSX | **preço de referência internacional** |
| **BCB – SGS** (séries 1 e 433) | câmbio (dólar, venda) e IPCA mensal | diário / mensal | R$/US$, % | diária/mensal | termos não confirmados em fonte oficial; API pública sem chave | ✅ JSON | converter em R$/saca e deflacionar |
| **INMET** (dados históricos de estações automáticas) | estações em superfície, horário | estação | vários | anual (zip) | termos não descritos na página | ❌ **falha de certificado TLS** neste ambiente | **não usado**; NASA POWER cobre a lacuna |

Detalhes e justificativas: `docs/pt-BR/02_fontes_de_dados.md`.

**Por que não usamos preço da CEPEA/ESALQ?** Preço brasileiro é o ideal para o produtor, mas o pedido foi usar *"preços somente de fontes com metodologia e acesso confirmados"*. A metodologia do indicador ICO está descrita no próprio arquivo do Banco Mundial (aba *Description*); para CEPEA não confirmei acesso programático e termos. Limitação: o preço ICO é **internacional**, não o preço pago ao produtor em Piraju.
""")
    n.md("""
## 2. Metadados da PAM direto da API (opcional: precisa de internet)
""")
    n.code("""
import requests
try:
    meta = requests.get(f"{config.SIDRA_BASE}/{config.PAM_TABLE}/metadados", timeout=30).json()
    print(meta["nome"]); print("Periodicidade:", meta["periodicidade"])
    print(pd.DataFrame([(v["id"], v["nome"], v["unidade"][:45]) for v in meta["variaveis"]], columns=["id", "variável", "unidade"]))
    cafe = [c for cl in meta["classificacoes"] for c in cl["categorias"] if "afé" in c["nome"]]
    print(pd.DataFrame(cafe)[["id", "nome"]])
except Exception as e:
    print("Sem internet; metadados não consultados:", e)
""")
    n.md("""
**Leitura:** a classificação 82 traz três categorias de café: *Total*, *Arábica* e *Canephora* (conilon + robusta). A PAM mede **ano civil** de referência. Unidades: hectares, toneladas, kg/ha e mil reais (moeda corrente da época; para valores anteriores a 1994 há outras moedas — por isso o `valor` só é usado de 1994 em diante).
""")
    n.md("""
## 3. Quando existe separação arábica × canephora?
Regra do projeto: **não misturar espécies quando houver desagregação confiável**. Verificamos, na API, a partir de que ano as categorias separadas existem.
""")
    n.code("""
esp = q('''
SELECT especie, min(ano) AS primeiro_ano, max(ano) AS ultimo_ano, count(DISTINCT ano) AS anos,
       count(DISTINCT cod_ibge) AS municipios, sum(quantidade_t) AS producao_total_t
FROM pam_municipio GROUP BY especie ORDER BY especie''')
esp
""")
    n.code("""
sp_esp = q('''
SELECT ano, especie, sum(quantidade_t) AS t FROM pam_municipio WHERE ano >= 2012 GROUP BY 1, 2''').pivot(index="ano", columns="especie", values="t")
sp_esp["canephora_%_do_total"] = 100 * sp_esp["canephora"] / sp_esp["total"]
print("Participação do canephora na produção paulista (%):", sp_esp["canephora_%_do_total"].round(3).describe()[["min", "max"]].to_dict())
sp_esp.tail(3)
""")
    n.md("""
**Interpretação:** a desagregação **só existe a partir de 2012**. Em São Paulo, o canephora é desprezível (fração muito pequena do total), então para SP-2012+ tratamos o café como **arábica** usando a categoria própria. Para 1974–2011 só há *Total* — séries longas aparecem rotuladas como "total (espécies não separadas)" e **não** servem para afirmar nada sobre arábica isoladamente. Em outras UFs (ES, RO) o canephora domina e a separação é essencial.
""")
    n.md("""
## 4. O payload bruto (bronze) e suas peculiaridades
A camada **bronze** guarda a resposta da API exatamente como veio (comprimida), com hash e metadados no manifesto. Veja uma amostra e a codificação de valores especiais do SIDRA.
""")
    n.code("""
key = "uf35_arabica_2023"
payload = lake.read_json("ibge_pam", "pam_municipio", key)
print("variáveis no payload:", [(v["id"], v["variavel"]) for v in payload])
raw = silver.flatten_sidra(payload)
raw.head(8)
""")
    n.code("""
print("Valores brutos especiais (texto) no payload de", key)
print(raw["raw"].where(raw["raw"].isin(list(config.SIDRA_SPECIAL)), "numérico").value_counts())
print()
print(pd.Series(config.SIDRA_SPECIAL, name="significado interpretado pelo pipeline"))
""")
    n.md("""
**Atenção a esta armadilha comum:** o SIDRA devolve **texto**, não número. `'-'` significa *zero absoluto* (município sem café), `'...'` *dado não disponível* e `'X'` *omitido por sigilo*. Tratar `'-'` como ausente (NaN) ou `'...'` como zero **distorce médias e rankings**. A silver converte cada código e guarda a qualidade em colunas `*_q`.
""")
    n.md("""
## 5. Volume real × benchmark sintético

Esta é a tabela mais importante do notebook: **quanto dado real o projeto tem**.
""")
    n.code("""
man = lake.manifest_df()
man["fonte"] = man["source"] + "/" + man["dataset"]
vol = man.groupby("fonte").agg(requisicoes=("request_key", "size"), mb_brutos=("bytes", lambda s: s.sum() / 1e6)).reset_index()
rows = {
    "pam_municipio (silver)": q("select count(*) from pam_municipio").iloc[0, 0],
    "clima_diario (silver)": q("select count(*) from clima_diario").iloc[0, 0],
    "painel município×ano (gold)": q("select count(*) from painel_cafe_arabica").iloc[0, 0],
    "clima_mensal (gold)": q("select count(*) from clima_mensal").iloc[0, 0],
}
display(vol.round(2))
real = pd.DataFrame({"tabela": list(rows), "linhas_reais": list(rows.values())})
real["comparação"] = real["linhas_reais"].map(lambda n: f"{n/1e6:.3f} M linhas")
real
""")
    n.code("""
tot_mb = vol["mb_brutos"].sum()
print(f"Dados REAIS brutos (todas as fontes, SP): ≈ {tot_mb:,.0f} MB; maior tabela: {max(rows.values()):,} linhas.")
print("Benchmarks SINTÉTICOS (notebook 07): 1M, 10M e 50M de linhas — gerados por synth.py, NÃO são dados da cafeicultura.")
print(f"50M / maior tabela real = {50_000_000/max(rows.values()):.0f}×")
""")
    n.md("""
**Conclusão da seção:** o dado real é **pequeno** (cabe em memória de um notebook; processá-lo com Spark seria *overhead* puro). O ganho dos engines escaláveis só aparece em volumes muito maiores — que **simulamos** de forma explícita e separada no notebook 07. A **expansão nacional** (`--ufs 31,32,41,…`) multiplicaria o PAM por ~10×, ainda sem tornar o problema "Big Data".
""")
    n.md("""
## 6. Proveniência: o manifesto da ingestão
""")
    n.code("""
m = lake.manifest_df()
m[["source", "dataset", "request_key", "bytes", "n_fetches", "last_fetched_at"]].groupby(["source", "dataset"]).agg(
    arquivos=("request_key", "size"), bytes=("bytes", "sum"), reingestoes_max=("n_fetches", "max"), ultima=("last_fetched_at", "max"))
""")
    n.md("""
**Como ler:** `reingestoes_max > 1` marca conjuntos reconsultados (p. ex. os 2 anos mais recentes do PAM, que o IBGE revisa). O resto vem do cache — ingestão **incremental e idempotente** (detalhada no notebook 02).

## 7. Exercícios
1. Qual a primeira safra com café *canephora* em algum município paulista? E qual município mais produz canephora em SP?
2. Consulte a API para o Espírito Santo (UF 32): a participação do canephora muda a conclusão da seção 3? (Dica: `python scripts/run_pipeline.py ingest --ufs 32`.)
3. Compare, em kB, o tamanho do payload bruto de um ano do PAM-SP com a tabela silver correspondente. O que explica a diferença?
""")
    return n
