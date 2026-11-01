# 07 · Modelagem, estatística e equações

> Todos os números citados vêm dos notebooks 03–06 e 08 executados sobre os dados reais. Onde um valor é descrito como "nesta execução", ele pode mudar se as fontes forem atualizadas.

## 1. Definições

- **Alvo:** rendimento municipal de arábica, *y<sub>i,t</sub>* (kg/ha), município *i*, ano-colheita *t*.
- **Painel:** 1 663 linhas elegíveis, 167 municípios, 13 anos (2013–2025).
- **Número efetivo de observações para clima:** ≈ **13** (o clima de uma célula é o mesmo para todos os seus municípios e varia por ano). As 1 663 linhas **não são** 1 663 observações independentes.

## 2. Cenários de informação e data de corte

A previsão é feita em **1º de maio de *t***.

| Cenário | Lags de rendimento | Motivo |
|---|---|---|
| **A** | *t*−1, *t*−2 | produtor/cooperativa com dado próprio |
| **B** | *t*−2, *t*−3 | **público estrito**: a PAM de *t*−1 só sai por volta de setembro de *t* |

Features: lags, área defasada, rendimento regional defasado, 6 features climáticas (até 31/mar de *t*), altitude/lat/lon da célula, preço real defasado (*t*−1). Todas **conhecidas na data de corte**.

## 3. Anti-vazamento (*leakage*)

| Risco | Defesa | Teste |
|---|---|---|
| clima do futuro | janelas terminam em 31/mar de *t* | `ultima_data_usada < data_corte_previsao` em todas as linhas |
| alvo em feature | lags usam `LAG` sobre anos anteriores consecutivos | `test_modeling`: nenhuma feature contém o alvo |
| validação aleatória | *expanding window* por ano | demonstração no notebook 06 (seção 7) |
| imputação/escala vendo o teste | `Pipeline` ajustado só no treino | por construção |
| codificação por alvo | nenhuma codificação de município baseada no alvo | por construção |

## 4. Validação temporal (*expanding window*)

Para cada ano-alvo *T* ∈ {2017,…,2025}: treino = anos < *T*; teste = ano *T*. Métricas agregadas sobre o **conjunto comum** de linhas em que todos os modelos têm previsão.

## 5. Modelos

| Modelo | Definição |
|---|---|
| `naive_lagk` | ŷ<sub>i,T</sub> = y<sub>i,T−k</sub> |
| `media_lags` | média dos lags disponíveis no cenário |
| `media_municipio` | média histórica do município **no treino** |
| `ridge` | `SimpleImputer(mediana)` → `StandardScaler` → `RidgeCV` (α ∈ [10⁻², 10³], 20 valores) |
| `xgboost` | 300 árvores, profundidade 3, taxa 0,05, `subsample` 0,8, `colsample_bytree` 0,8, `min_child_weight` 5, `reg_lambda` 2 |

**Ridge:** minimiza Σ(y − Xβ)² + α‖β‖², com β estimado no treino padronizado.

**Por que o ridge pode explodir:** covariáveis de **ano** (preço defasado, rendimento regional) têm 1 valor por ano; no início, o treino tem 3–4 valores distintos. Se o ano de teste fica fora dessa faixa, a previsão linear **extrapola** (observado: ŷ ≈ −10 000 kg/ha em 2019 no cenário B, com preço de teste 929 abaixo do mínimo visto, 958). Árvores não extrapolam.

## 6. Métricas

Para *n* observações, *y<sub>j</sub>* real e *ŷ<sub>j</sub>* previsto:

- **MAE** = (1/n) Σ |y<sub>j</sub> − ŷ<sub>j</sub>|
- **RMSE** = √[(1/n) Σ (y<sub>j</sub> − ŷ<sub>j</sub>)²]
- **sMAPE** = (100/n) Σ 2|y<sub>j</sub> − ŷ<sub>j</sub>| / (|y<sub>j</sub>| + |ŷ<sub>j</sub>|)  (termos com denominador 0 contam 0)
- **WAPE** = 100 · Σ|y<sub>j</sub> − ŷ<sub>j</sub>| / Σ|y<sub>j</sub>|

**Cuidados:** sMAPE é instável com valores próximos de 0; MAPE simples explode com rendimentos baixos; RMSE amplifica outliers; WAPE pondera por volume.

## 7. Resultados (cenário A, 1 080 linhas, 2017–2025)

| Modelo | MAE (kg/ha) | RMSE | sMAPE (%) |
|---|---:|---:|---:|
| `media_lags` | 218,7 | 354,5 | 14,5 |
| `xgboost` | 235,2 | 353,0 | 15,6 |
| `media_municipio` | 239,2 | 364,2 | 15,9 |
| `naive_lag1` | 241,5 | 418,9 | 15,8 |
| `naive_lag2` | 252,8 | 419,2 | 17,1 |
| `ridge` | 426,4 | 618,3 | 28,7 |

**Cenário B (1 079 linhas):** `media_municipio` 234,4 · `naive_lag2` 253,0 · `media_lags` 256,1 · `xgboost` 264,1 · `naive_lag3` 323,1 · `ridge` 1 961,2.

**Leitura:** nenhum modelo treinado supera o melhor baseline em MAE. O XGBoost empata em RMSE no cenário A. **A persistência já explica quase tudo o que é previsível.**

## 8. Incerteza: intervalos conformes por divisão (split conformal)

Para o ano *T*, com *R* = conjunto de |resíduos| de **todas as dobras anteriores** (|R| = *m*), o quantil de nível (1−α) é o ⌈(m+1)(1−α)⌉-ésimo menor valor *q*; o intervalo é ŷ ± *q*.

Cobertura marginal ≈ 1−α **exige trocabilidade**, que **não vale** em séries com mudança de regime. Por isso **medimos** a cobertura empírica: nesta execução, ≈ 80% no total (nominal 80%), mas **por ano** de ≈ 65% (2021) a ≈ 87% (2018).

## 9. Agregado regional

Produção prevista (t) = Σ<sub>i</sub> ŷ<sub>i</sub> · área<sub>i</sub> / 1000. Erro absoluto médio anual no estado (municípios elegíveis): XGBoost ≈ 6,9% · média de lags ≈ 7,7% · `naive_lag1` ≈ 14,0%. Anos de safra alta/baixa (2018, 2024) têm viés de −14% a −17%.

## 10. Séries temporais agregadas (CONAB arábica SP, 2001–2025)

- **Variação log:** *d<sub>t</sub>* = ln P<sub>t</sub> − ln P<sub>t−1</sub>.
- **Alternância:** fração de anos com sinal(*d<sub>t</sub>*) ≠ sinal(*d<sub>t−1</sub>*). CONAB: ≈ 91%; PAM total 2001–25: ≈ 87%.
- **ACF:** ρ<sub>k</sub> = Cov(r<sub>t</sub>, r<sub>t−k</sub>)/Var(r), com *r* o resíduo da tendência linear do log. CONAB: ρ<sub>1</sub> ≈ −0,64, ρ<sub>2</sub> ≈ +0,70 (banda de ruído ±1,96/√n ≈ ±0,39).
- **Rolling origin (2010–2025):** MAE `naive_lag2` 608 < `ar2` 654 < `ets_amort` 805 < `media_2` 814 < `media_5` 832 < `naive` 1 318 (mil sacas). Todos superam o `naive` com IC pareado excluindo 0; entre os demais, as diferenças **não** são distinguíveis com 16 anos-alvo.

## 11. Associação clima × rendimento (notebook 04)

- **Anomalias:** *y*′ = y − ȳ<sub>município</sub>; *x*′ = x − x̄<sub>célula</sub>.
- **Correlação de postos (Spearman)** entre *x*′ e *y*′.
- **Bootstrap por blocos de ano:** reamostra os **13 anos** com reposição (a unidade independente), 500 réplicas, IC 95% por percentis (notebook 08 usa 300).
- **Leave-one-year-out:** estabilidade do sinal removendo cada ano.
- **Correlação parcial (Spearman)** controlando a anomalia do ano anterior.
- **Resultado:** nenhuma das 6 features tem IC95% que exclua 0 (|ρ| ≤ 0,09).

**Por que não "p-valor" com 1 663 linhas:** as linhas não são independentes (células e anos compartilhados); o p-valor ingênuo seria **enganosamente pequeno**.

## 12. Concentração e desigualdade

- **HHI** = 10 000 · Σ s<sub>i</sub>², s<sub>i</sub> = participação do município *i* na produção (≈ 230–330 em 2012–2025: baixa concentração municipal).
- **Gini** (notebook 03): fórmula manual via ordenação (`np.trapz` foi removido no NumPy 2.4).

## 13. Intervalos de confiança regionais (notebook 08)

Rendimento da região = 1000 · Σ produção / Σ área (municípios × 5 anos). IC por **bootstrap de municípios** (1 000 réplicas): reamostra municípios da região com reposição e recalcula a razão de somas.

## 14. O que **não** se pode concluir

1. **Causalidade** a partir de qualquer correlação.
2. Que o clima "não importa" (o resultado nulo reflete resolução, ruído e poucos anos).
3. Que o XGBoost é "melhor" ou "pior" em geral: com ≈ 9 anos-alvo e alvo ruidoso, a evidência é fraca.
4. Que os números do SP valem para outros estados ou para o conilon.

## 15. MLflow (opcional)

`USE_MLFLOW=1` registra parâmetros e métricas de cada (cenário, modelo) em `mlflow.db` (SQLite). O backend de arquivos `./mlruns` foi **descontinuado** nas versões recentes do MLflow (a execução falha por padrão); o projeto usa SQLite. Sem a variável, o projeto **não depende** do MLflow.
