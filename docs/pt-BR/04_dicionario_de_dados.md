# 04 · Dicionário de dados

Esquemas conferidos diretamente no lago de dados (`DESCRIBE` do DuckDB). Convenções: `*_ha` hectares; `*_t` toneladas; `rendimento_kg_ha` quilos por hectare; `*_q` qualidade do valor SIDRA (`ok`, `zero`, `zero_arredondado`, `nao_se_aplica`, `indisponivel`, `suprimido`).

## SILVER

### `pam_municipio` — PAM por município (partição `especie`)
| Coluna | Tipo | Descrição |
|---|---|---|
| `cod_ibge` | texto(7) | código do município (2 UF + 4 + DV), **validado** |
| `municipio`, `uf`, `uf_codigo` | texto/int | nome e UF |
| `date_key` | data | 31/dez do ano de referência |
| `ano` | int | ano de referência da pesquisa |
| `especie` | texto | `total` \| `arabica` \| `canephora` (arábica/canephora só a partir de 2012) |
| `area_destinada_ha` | número | área destinada à colheita |
| `area_colhida_ha` | número | área efetivamente colhida |
| `quantidade_t` | número | produção em toneladas |
| `rendimento_kg_ha` | número | rendimento médio informado (≈ produção ÷ área colhida) |
| `valor_mil_reais` | número | valor da produção em mil R$ (preços correntes do ano) |
| `*_q` | texto | qualidade/valor especial SIDRA de cada medida |
| `tem_producao` | bool | `quantidade_t > 0` |

Chave única: `(cod_ibge, especie, ano)`.

### `pam_uf` — PAM por UF (partição `especie`)
Mesmas medidas, nível `uf_codigo`/`uf`. Chave: `(uf_codigo, especie, ano)`.

### `dim_municipio` — dimensão territorial
`cod_ibge` (PK), `municipio`, `uf`, `uf_codigo`, `microrregiao`, `mesorregiao`, `regiao_imediata`, `lat`, `lon` (centroide), `area_km2`, `pop_2022`, `densidade_hab_km2` (Censo 2022), `cell_id` (célula NASA POWER que contém o centroide), `cell_lat`, `cell_lon`.

### `clima_diario` — NASA POWER (partição `ano`)
| Coluna | Descrição |
|---|---|
| `cell_id` | `"<ilat>_<ilon>"` — **contém `_`**; o parse usa `rsplit("_", 2)` |
| `date` | dia |
| `t2m`, `t2m_max`, `t2m_min` | temperatura do ar a 2 m (°C): média, máxima, mínima |
| `prec_mm` | precipitação corrigida (mm/dia) |
| `ano`, `mes` | derivadas de `date` |

Chave única: `(cell_id, date)`.

### `clima_celula`
`cell_id`, `elev_m` (altitude da célula reportada pelo NASA POWER; **não** é a altitude da lavoura).

### `conab_uf`
`uf`, `safra` (ano inicial), `especie`, `indicador` (`producao_mil_sacas`, `area_producao_ha`, `area_formacao_ha`, `produtividade_sc_ha`), `unidade`, `valor`, `estimativa` (`True` na safra em andamento).

### `preco_cafe_mensal`, `cambio_mensal`, `ipca_mensal`
| Tabela | Colunas |
|---|---|
| `preco_cafe_mensal` | `mes_ref`, `cafe_arabica_usd_kg`, `cafe_robusta_usd_kg` |
| `cambio_mensal` | `mes_ref`, `brl_usd` (média mensal), `n_dias` |
| `ipca_mensal` | `mes_ref`, `ipca_var_pct`, `ipca_indice` (índice encadeado a partir da variação mensal, **base arbitrária**; só razões entre datas têm sentido) |

## GOLD

### `painel_cafe_arabica` — município × ano (arábica, 2012+)
| Grupo | Colunas | Observação |
|---|---|---|
| chaves | `cod_ibge`, `ano` | único |
| alvo e medidas | `rendimento_kg_ha`, `area_colhida_ha`, `quantidade_t`, `valor_mil_reais`, `area_destinada_ha`, `tem_producao` | |
| lags (só passado) | `rend_lag1..3`, `area_lag1`, `area_lag2`, `prod_lag1` | `LAG` sobre **ano consecutivo**; NULL se faltar ano |
| regional | `rend_reg_lag1..3` | rendimento do estado nos anos anteriores (municípios com área ≥ 100 ha) |
| clima | `chuva_floracao`, `tmean_floracao`, `chuva_granacao`, `tmax_granacao`, `chuva_12m_pre`, `dias_frio_inv_prev` | janelas que terminam em 31/mar de *t* |
| território | `municipio`, `uf`, `microrregiao`, `mesorregiao`, `lat`, `lon`, `area_km2`, `pop_2022`, `cell_id`, `elev_m` | |
| preço | `preco_real_lag1`, `preco_usd_kg_lag1` | média do ano *t*−1 (R$/saca real de 2025; US$/kg) |
| elegibilidade | `elegivel_modelo` | área colhida ≥ 100 ha em *t* e *t*−1, e rendimentos de *t* e *t*−1 conhecidos |

### `clima_features` — célula × ano-colheita
Janelas fenológicas (hipóteses exploratórias) e **trilha de auditoria**: `ultima_data_usada` e `data_corte_previsao` (1º/mai de *t*). Teste automatizado exige `ultima_data_usada < data_corte_previsao`.

| Feature | Janela | Definição |
|---|---|---|
| `chuva_floracao` | set–nov de *t*−1 | soma de `prec_mm` |
| `tmean_floracao` | set–nov de *t*−1 | média de `t2m` |
| `chuva_granacao` | dez *t*−1 – mar *t* | soma de `prec_mm` |
| `tmax_granacao` | dez *t*−1 – mar *t* | média de `t2m_max` |
| `chuva_12m_pre` | abr *t*−1 – mar *t* | soma de `prec_mm` |
| `dias_frio_inv_prev` | jun–ago *t*−1 | dias com `t2m_min ≤ 4 °C` |

Janela com meses faltantes ⇒ **NULL** (nunca soma parcial silenciosa).

### `clima_mensal`
`cell_id`, `ano`, `mes`, `mi` (mês-índice), `n_dias`, `prec_mm` (soma), `t2m_mean`, `tmax_mean`, `tmin_mean`, `tmin_min`, `dias_frio`.

### `precos_anuais`
`ano`, `n_meses`, `usd_kg_arabica`, `usd_kg_robusta`, `brl_usd`, `brl_saca_nominal` (= US$/kg × 60 × R$/US$), `brl_saca_real_2025` (deflacionado pelo IPCA para reais de 2025).

### `ipca_anual`
`ano`, `n_meses`, `ipca_indice_medio`, `fator_nominal_para_real` (índice médio de 2025 ÷ índice médio do ano).

### `conab_vs_pam`
`uf`, `ano`, `especie`, `producao_conab_t`, `producao_pam_t`, `estimativa`, `dif_rel` = (CONAB − PAM) ÷ PAM. Diferenças são **esperadas** (metodologias diferentes).

### `dq_results`
`table`, `check`, `severity` (`error`/`warn`), `passed`, `n_failed`, `n_total`, `detail`.

## Notas de interpretação

- **`rendimento_kg_ha` é um valor informado**, não recalculado; as inconsistências com produção ÷ área aparecem como alertas.
- **Clima é da célula**, não do município: todos os municípios da mesma célula têm o mesmo valor.
- **Preço é internacional convertido**, não preço ao produtor.
