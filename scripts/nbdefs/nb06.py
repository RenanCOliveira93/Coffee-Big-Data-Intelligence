from ._helpers import NB, SETUP


def build():
    n = NB()
    n.md("""
# 06 · Previsão de produtividade municipal

**Coffee Big Data Intelligence**

> **Aviso central:** o alvo é o **rendimento (kg/ha) de café arábica por município e ano**, em SP. Os dados são **estimativas administrativas** (PAM) com ~13 safras úteis. Regras do jogo: validação **temporal**, **sem vazamento**, e todo modelo complexo precisa **bater baselines simples** para merecer uso.

## Objetivos
1. Montar dois **cenários de informação** realistas (A: dado próprio de T−1; B: apenas dados públicos).
2. Comparar baselines, regressão regularizada e XGBoost com MAE, RMSE e sMAPE.
3. Fazer **ablações** (o que cada grupo de features acrescenta?).
4. Medir **incerteza** com intervalos conformes e verificar a cobertura.
5. Demonstrar o **vazamento** que a validação aleatória causaria.
6. Agregar para **produção regional** e discutir o que o erro municipal significa.

## Cenários de informação
| Cenário | Quem usa | Lags de rendimento | Motivo |
|---|---|---|---|
| **A** | produtor/cooperativa com dado próprio | T−1, T−2 | o rendimento de T−1 é conhecido em 1º/mai/T |
| **B** | analista com dados **públicos estritos** | T−2, T−3 | a PAM de T−1 só sai por volta de setembro de T |

**Data de corte da previsão: 1º/mai de T.** Clima só até 31/mar de T; preço médio real de T−1; imputação e escala ajustadas **só no treino** (`Pipeline`).
""")
    n.code(SETUP + """
import time""")
    n.code("""
panel = q("select * from painel_cafe_arabica")
elig = panel[panel.elegivel_modelo]
print(f"Painel: {len(panel):,} linhas | elegíveis (área ≥ {M.__dict__.get('MIN_AREA_HA', 100)} ha etc.): {len(elig):,} | municípios: {elig.cod_ibge.nunique()} | anos: {elig.ano.min()}–{elig.ano.max()}")
for sc in "AB":
    d = M.prepare(panel, sc)
    print(f"Cenário {sc}: {len(d):,} linhas utilizáveis | anos {d.ano.min()}–{d.ano.max()} | features: {len(M.feature_list(sc))}")
print("\\nFeatures do cenário A:", M.feature_list("A"))
""")
    n.md("""
## 1. Validação temporal *expanding window*

Para cada ano-alvo *T* (2017–2025): **treino = todos os anos < T**; **teste = ano T**. O primeiro fold tem só 3 anos de treino — por isso as primeiras dobras são ruidosas.

Métricas (ŷ previsto, y real):

- **MAE** = (1/n) Σ |y − ŷ|, em kg/ha.
- **RMSE** = √[(1/n) Σ (y − ŷ)²]: penaliza erros grandes (sensível a outliers).
- **sMAPE** = (100/n) Σ 2|y − ŷ| / (|y| + |ŷ|).
- **WAPE** = 100 Σ|y − ŷ| / Σ|y| (ponderado pelo volume).

**Comparação justa:** só as linhas em que **todos** os modelos produzem previsão (`common_subset`).
""")
    n.code("""
t0 = time.time()
resA = M.backtest(panel, "A"); resB = M.backtest(panel, "B")
print(f"backtests A e B: {time.time()-t0:.1f}s")
def tabela(res):
    c = M.common_subset(res); s = M.score_table(M.BacktestResult(res.scenario, c, res.features))
    s["WAPE_%"] = [M.wape(c.y, c[m]) for m in s.modelo]
    return s.set_index("modelo").drop(columns=["grupo"]).sort_values("MAE").round(1)
print("Cenário A — rendimento de T−1 disponível"); display(tabela(resA))
print("Cenário B — apenas dados públicos estritos"); display(tabela(resB))
""")
    n.code("""
fig, ax = plt.subplots(1, 2, figsize=(11, 3.4), sharey=True)
for a, (res, tt) in zip(ax, [(resA, "Cenário A"), (resB, "Cenário B")]):
    t = tabela(res)
    cols = ["#00897b" if m in ("ridge", "xgboost") else "#bcaaa4" for m in t.index]
    a.barh(t.index[::-1], t.MAE[::-1], color=cols[::-1]); a.set_title(tt); a.set_xlabel("MAE (kg/ha)")
plt.suptitle("Verde = modelos treinados; cinza = baselines sem treino", y=1.03, fontsize=9)
plt.tight_layout(); plt.savefig(FIG / "06_comparacao_modelos.png"); plt.show()
""")
    n.md("""
**Como ler:** compare cada modelo treinado (verde) com o melhor baseline (cinza). Um modelo só "ganha" se seu MAE for **claramente** menor que o do melhor baseline.

**Resultado nesta execução:** nenhum modelo treinado bate o melhor baseline em MAE (cenário A: XGBoost 235 × `media_lags` 219 kg/ha; cenário B: XGBoost 264 × `media_municipio` 234 kg/ha). No cenário A o XGBoost empata em RMSE (353 × 355). Ou seja: **a persistência já explica quase tudo o que é previsível** com estes dados — resultado legítimo, não falha do projeto.

**Baselines:** `naive_lag1/2/3` repetem o rendimento de T−1/T−2/T−3; `media_lags` faz a média dos lags disponíveis; `media_municipio` usa a média histórica do município no treino. São **difíceis de bater** porque o rendimento municipal da PAM é muito persistente (estimativas repetidas — notebook 02).

**Atenção ao `ridge`:** se o seu erro for muito maior que o dos baselines, **não é "o modelo ruim"** — é um defeito de extrapolação, investigado na seção 3.
""")
    n.md("""
## 2. Erro por ano-alvo

Médias globais escondem o comportamento ano a ano. Abaixo, o MAE por safra de teste para o XGBoost, o ridge e os principais baselines (cenário A).
""")
    n.code("""
by = M.score_table(M.BacktestResult("A", M.common_subset(resA), resA.features), by_year=True)
pv = by.pivot(index="grupo", columns="modelo", values="MAE")
display(pv.round(0))
fig, ax = plt.subplots(figsize=(9, 3.2))
for m, col in zip(["media_lags", "naive_lag1", "xgboost", "ridge"], ["#8d6e63", "#bcaaa4", "#00897b", "#c62828"]):
    ax.plot(pv.index, pv[m], "o-", color=col, label=m)
ax.set(xlabel="ano-alvo", ylabel="MAE (kg/ha)", title="MAE por safra (cenário A)"); ax.legend(fontsize=8); ax.set_ylim(0, pv.drop(columns="ridge").max().max() * 1.6)
plt.tight_layout(); plt.savefig(FIG / "06_mae_por_ano.png"); plt.show()
""")
    n.md("""
**Como ler:** anos atípicos afetam **todos** os modelos juntos (o erro sobe para todos). O eixo vertical foi truncado para o `ridge` não achatar as demais curvas; o valor real do ridge está na tabela.

## 3. Por que o `ridge` falha em certas dobras? Extrapolação de covariáveis de ano

`preco_real_lag1`, `rend_reg_lag*` têm **um único valor por ano** (são iguais para todos os municípios). No treino das primeiras dobras há apenas **3–4 valores distintos** dessas variáveis; o modelo linear ajusta uma inclinação em cima de poucos pontos. Quando o ano de teste traz um valor **fora da faixa vista**, a previsão linear **extrapola**; árvores (XGBoost) não extrapolam: saturam no último valor visto.
""")
    n.code("""
dB = M.prepare(panel, "B")
rows = []
for t in range(2017, 2026):
    tr, te = dB[dB.ano < t], dB[dB.ano == t]
    if te.empty: continue
    rows.append({"ano_teste": t, "anos_no_treino": tr.ano.nunique(), "preço treino min": tr.preco_real_lag1.min(), "preço treino max": tr.preco_real_lag1.max(),
                 "preço teste": te.preco_real_lag1.iloc[0], "fora da faixa?": not (tr.preco_real_lag1.min() <= te.preco_real_lag1.iloc[0] <= tr.preco_real_lag1.max())})
ext = pd.DataFrame(rows).set_index("ano_teste")
byB = M.score_table(M.BacktestResult("B", M.common_subset(resB), resB.features), by_year=True).pivot(index="grupo", columns="modelo", values="MAE")
ext["MAE ridge (B)"] = byB.ridge; ext["MAE xgboost (B)"] = byB.xgboost
ext.round(0)
""")
    n.md("""
**Como ler:** onde `fora da faixa? = True` e o MAE do ridge explode, a causa é **extrapolação linear** de uma covariável de ano. Não é "má sorte": é uma propriedade do desenho (poucos anos, covariável constante entre municípios). Observe também que o fora-da-faixa em 2021–2023 **não** explodiu o erro: com mais anos no treino a inclinação fica mais estável. **Remédios:** remover as covariáveis de ano (as ablações abaixo mostram o ridge voltando a ~230 kg/ha no cenário A sem `rend_reg_lag*` e sem clima), usar árvores, ou limitar (*clip*) ao intervalo do treino (exercício 1).

## 4. Ablações: o que cada grupo de features acrescenta?

Variantes: **completo**; **sem regional** (sem `rend_reg_lag*`); **sem clima**; **sem clima e sem regional**. O MAE é medido no mesmo conjunto de linhas.
""")
    n.code("""
variants = {"completo": {}, "sem_regional": dict(with_regional=False), "sem_clima": dict(with_clima=False),
            "sem_clima_sem_regional": dict(with_clima=False, with_regional=False), "sem_preco": dict(with_price=False)}
rows = []
for sc in "AB":
    base = M.backtest(panel, sc)
    best_base = M.common_subset(base)
    bl = min(M.mae(best_base.y, best_base[c]) for c in best_base.columns if c.startswith(("naive", "media")))
    for nm, kw in variants.items():
        r = M.backtest(panel, sc, **kw); c = M.common_subset(r)
        rows.append({"cenário": sc, "variante": nm, "n": len(c), "MAE ridge": M.mae(c.y, c.ridge), "MAE xgboost": M.mae(c.y, c.xgboost),
                     "melhor baseline (MAE)": bl})
abl = pd.DataFrame(rows).set_index(["cenário", "variante"])
abl.round(1)
""")
    n.md("""
**Como ler:** diferenças de poucos kg/ha entre variantes **não são interpretáveis** com este *n*. Procure efeitos grandes e consistentes entre os dois modelos e os dois cenários. Se tirar o clima **não piora** o erro, isso é **resultado** (o clima de grade de 55 km, sem informação de manejo, não acrescenta previsão além da persistência), e não uma falha a esconder. Lembre: municípios da mesma célula compartilham o mesmo clima, e só há 9 anos-alvo; o número efetivo de observações climáticas independentes é bem menor que 1 000.
""")
    n.md("""
## 5. Incerteza: intervalos conformes (split, por dobras anteriores)

Para cada ano *T*, o intervalo de nível 80% é ŷ ± q, com *q* o quantil de **|resíduos| de todas as dobras anteriores a T** (corrigido por (n+1)). Garantia teórica de cobertura **marginal ≈ 80%** exige trocabilidade — que **não vale** em séries com mudança de regime. Por isso **medimos a cobertura empírica** por ano.
""")
    n.code("""
rows = []
for sc, res in (("A", resA), ("B", resB)):
    c = M.common_subset(res)
    for m in ["xgboost", "media_lags" if sc == "A" else "media_municipio", "naive_lag1" if sc == "A" else "naive_lag2"]:
        ci = M.conformal_intervals(c, m, alpha=0.2); cv = M.coverage(ci)
        rows.append({"cenário": sc, "modelo": m, "linhas com intervalo": cv["n"], "cobertura (nominal 80%)": 100 * cv["cobertura"], "largura média (kg/ha)": cv["largura_media"]})
cob = pd.DataFrame(rows).set_index(["cenário", "modelo"]); display(cob.round(1))
ci = M.conformal_intervals(M.common_subset(resA), "xgboost", alpha=0.2)
porano = ci.dropna(subset=["lo"]).groupby("ano").coberto.mean() * 100
fig, ax = plt.subplots(figsize=(8, 3)); ax.bar(porano.index, porano.values, color="#a1887f"); ax.axhline(80, color="k", ls="--", lw=1)
ax.set(ylabel="% de municípios cobertos", xlabel="ano-alvo", title="Cobertura empírica por ano — XGBoost (cenário A)")
plt.tight_layout(); plt.savefig(FIG / "06_cobertura.png"); plt.show()
""")
    n.md("""
**Como ler:** a cobertura média ficou próxima do nominal (≈80%), mas **por ano** variou de ≈65% (2021) a ≈87% (2018): os erros são **correlacionados** entre municípios no mesmo ano, e um ano atípico fura o intervalo de muitos municípios ao mesmo tempo. Em decisão de risco, use a **pior** cobertura anual, não a média.

## 6. Produção regional (agregação de municípios)

Produção prevista = Σ (rendimento previsto × área de referência) / 1000, para os municípios elegíveis. Erros municipais de sinais opostos **se compensam** na soma — o erro regional costuma ser **menor** que o municipal em termos relativos.
""")
    n.code("""
reg = M.regional_production(resA, ["xgboost", "media_lags", "naive_lag1"])
display(reg.round(1))
print("Erro regional absoluto médio (%):", {m: round(reg[f"{m}_erro_%"].abs().mean(), 1) for m in ["xgboost", "media_lags", "naive_lag1"]})
""")
    n.md("""
**Como ler:** o erro regional absoluto médio é ≈6,9% (XGBoost) e ≈14,0% (`naive_lag1`), contra ≈15% de sMAPE municipal: a agregação compensa erros de sinais opostos. Mas os anos de safra alta/baixa (2018, 2024) continuam subestimados em −14% a −17%: o erro é **sistemático**, não aleatório. O `_erro_%` é o viés da produção regional prevista. Use-o com cuidado: o painel cobre só municípios **elegíveis** (área ≥ limiar e histórico completo), e **não** toda a produção paulista.

## 7. Por que validação aleatória é enganosa (vazamento temporal)

Demonstração: o **mesmo** XGBoost, com as mesmas features do cenário A, avaliado por **K-fold aleatório** (linhas de qualquer ano em treino e teste) e pela validação temporal. Na validação aleatória, o treino contém o **ano seguinte** e municípios vizinhos do mesmo ano, e o modelo "olha o futuro".
""")
    n.code("""
from sklearn.model_selection import KFold
from sklearn.base import clone
dA = M.prepare(panel, "A"); fA = M.feature_list("A"); dA = dA.dropna(subset=[c for c in fA if c.startswith("rend_reg")])
xg = M.make_models(0)["xgboost"]
test_years = dA[dA.ano >= 2017]
maes_rand = []
for tr_i, te_i in KFold(5, shuffle=True, random_state=0).split(dA):
    mm = clone(xg).fit(dA.iloc[tr_i][fA], dA.iloc[tr_i].rendimento_kg_ha)
    te = dA.iloc[te_i]; te = te[te.ano >= 2017]
    maes_rand.append(M.mae(te.rendimento_kg_ha, mm.predict(te[fA])))
c = M.common_subset(resA)
print(f"MAE com K-fold ALEATÓRIO (linhas de teste de 2017+): {np.mean(maes_rand):.0f} kg/ha")
print(f"MAE com validação TEMPORAL honesta (2017+):          {M.mae(c.y, c.xgboost):.0f} kg/ha")
""")
    n.md("""
**Como ler:** a validação aleatória dá erro **menor** (≈7% aqui), na direção esperada. A diferença é modesta neste caso porque os lags de rendimento já carregam a persistência; ela seria maior com alvos mais dependentes da vizinhança temporal. O ponto metodológico permanece: o otimismo é injetado **sem** que você perceba. Em projetos reais esse otimismo vira "modelo que funcionou em teste e falhou em produção". **Nunca** use K-fold aleatório em dados com estrutura temporal.

## 8. O que o XGBoost usou? (com muita cautela)

Importância por *gain* mostra quais variáveis as árvores usaram, **não** o que causa o rendimento. Variáveis correlacionadas dividem importância; covariáveis de ano (poucos valores) podem ser usadas como "identificador de ano".
""")
    n.code("""
dtr = dA[dA.ano < 2025]; mm = clone(xg).fit(dtr[fA], dtr.rendimento_kg_ha)
imp = pd.Series(mm.get_booster().get_score(importance_type="gain")).reindex(fA).fillna(0).sort_values()
fig, ax = plt.subplots(figsize=(7, 4)); ax.barh(imp.index, imp.values, color="#8d6e63"); ax.set_xlabel("importância (gain)")
ax.set_title("XGBoost (cenário A, treino < 2025)"); plt.tight_layout(); plt.savefig(FIG / "06_importancia_xgb.png"); plt.show()
print((100 * imp[::-1] / imp.sum()).round(1).head(6).to_string())
""")
    n.md("""
**Como ler:** os dois lags de rendimento somam ≈43% do *gain* (e `rend_lag2` pesa mais que `rend_lag1`, compatível com a alternância bienal vista no notebook 05): o modelo está basicamente **aprendendo persistência** — coerente com os baselines serem competitivos. Não leia "chuva importa X%": a importância depende do modelo e dos dados, e **não é efeito causal**.

## 9. Registro de experimentos (MLflow, opcional)

Com `USE_MLFLOW=1` e a biblioteca instalada, as métricas dos cenários são registradas em `mlflow.db` (SQLite; ignorado pelo git — o backend de arquivos `mlruns/` foi descontinuado nas versões recentes do MLflow). Sem a variável, esta etapa é pulada: **o projeto não depende de MLflow**.
""")
    n.code("""
if config.USE_MLFLOW:
    import mlflow
    mlflow.set_tracking_uri(f"sqlite:///{config.ROOT / 'mlflow.db'}"); mlflow.set_experiment("coffee-bdi-previsao")
    for sc, res in (("A", resA), ("B", resB)):
        t = tabela(res)
        for m, r in t.iterrows():
            with mlflow.start_run(run_name=f"{sc}-{m}"):
                mlflow.log_params({"cenario": sc, "modelo": m, "n_features": len(res.features)})
                mlflow.log_metrics({"MAE": r.MAE, "RMSE": r.RMSE, "sMAPE": r["sMAPE_%"], "WAPE": r["WAPE_%"]})
    print("Registrado em", config.ROOT / "mlflow.db", "(visualizar: mlflow ui --backend-store-uri sqlite:///mlflow.db)")
else:
    print("USE_MLFLOW não definido: registro de experimentos pulado (definido em .env ou ambiente).")
""")
    n.md("""
## 10. Resumo interpretativo

| Pergunta | Evidência | Limite |
|---|---|---|
| Modelo treinado bate baseline simples? | seção 1 (compare verde × cinza) | ~1 000 linhas, poucos anos distintos |
| Clima melhora a previsão? | seção 4 (ablações) | clima de grade ~55 km; ano compartilhado entre municípios |
| Os intervalos são confiáveis? | seção 5: cobertura **por ano** | erros correlacionados no tempo |
| Validação aleatória é segura? | seção 7 | **não**: infla o desempenho |
| O erro regional é menor que o municipal? | seção 6 | só municípios elegíveis |

## Exercícios
1. Restrinja o `ridge` com *clip* nas covariáveis de ano e refaça a seção 3: o erro de 2018–2019 desaparece?
2. Altere `first_test` para 2019 e 2021: o ranking entre XGBoost e baselines muda?
3. Acrescente um baseline `media_lags_ponderada` e compare com o XGBoost via MAE por ano.
4. Troque `alpha` por 0,1 e 0,5 e compare cobertura nominal × observada.
5. Por que o erro de sMAPE pode ser enganoso quando o rendimento previsto é próximo de zero?
""")
    return n
