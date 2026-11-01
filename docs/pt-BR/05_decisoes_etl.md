# 05 · Decisões de ETL e transformações

Cada transformação abaixo vem com **o quê**, **por quê** e **como falha**. Código em `src/coffeebdi/`.

## 1. Valores especiais do SIDRA

| Símbolo | Significado | Tratamento no silver |
|---|---|---|
| `-` | zero absoluto | número 0; `*_q = "zero"` |
| `0` | zero por arredondamento | número 0; `*_q = "zero_arredondado"` |
| `..` | não se aplica | NULL; `*_q = "nao_se_aplica"` |
| `...` | indisponível | NULL; `*_q = "indisponivel"` |
| `X` | suprimido por sigilo | NULL; `*_q = "suprimido"` |

**Por quê:** converter `-` e `..` indistintamente para NaN apagaria a diferença entre "não produziu" e "dado inexistente". **Falha típica:** `pd.to_numeric(errors="coerce")` sem tratar símbolos.

## 2. Código IBGE de município

- 7 dígitos: UF (2) + município (4) + **dígito verificador** (1).
- DV: pesos `1,2,1,2,1,2` sobre os 6 primeiros dígitos; cada produto ≥ 10 tem os dígitos somados; `DV = (10 − soma mod 10) mod 10`.
  - Exemplo: Piraju `353880|8`; Fartura `351540|0`.
- `normalize_municipio` aceita `int`, `str`, `float` (`3538808.0`) e 6 dígitos (completa o DV) e devolve sempre **texto de 7 dígitos**.
- **Por quê:** o mesmo código aparece como `int`, `str` ou `float` (`3538808.0`, comum após `read_csv` com NaN) e uma junção `int × str` não casa nenhuma linha, **sem erro**. (Códigos IBGE de município nunca começam com zero, pois o código de UF vai de 11 a 53.) **Falha típica:** código de município errado de memória (ocorreu no Projeto 01; o teste `is_valid_municipio` pega).

## 3. Chaves de tempo

- PAM: `ano` (int) e `date_key` (31/dez).
- Clima: `date`; `mi = ano × 12 + mes − 1` para aritmética de janelas sem erro de virada de ano.
- **Por quê:** comparar "mês 12 de *t*−1 com mês 1 de *t*" por (ano, mês) exige lógica condicional; com `mi` vira `BETWEEN`.

## 4. Pivot do PAM

O JSON do SIDRA é **longo** (uma linha por variável). O silver pivota para colunas com `DataFrame.pivot` (não `pivot_table`).

**Erro real encontrado:** `pivot_table` faz agregação e **descartou 5 747 linhas** (45 293 em vez de 51 040) por tratar `NaN` como chave ausente. O notebook 02 mostra o contraste e há teste de regressão.

## 5. Idempotência da ingestão

| Elemento | Decisão |
|---|---|
| chave de requisição | determinística (`uf35_arabica_2023`); `..` e caracteres inseguros são substituídos |
| escrita | arquivo temporário + `rename` atômico |
| compressão | `gzip` com `mtime=0` ⇒ mesmos bytes para o mesmo conteúdo |
| comparação | `sha256` do payload |
| status | `new` / `cached` / `unchanged` / `updated` |
| janela | os últimos `PAM_REFRESH_RECENT_YEARS` anos do PAM são sempre rebuscados |
| manifesto | `n_fetches`, `first_fetched_at`, `last_fetched_at` |

**Testes** (`tests/test_ingest_idempotent.py`, com a rede simulada): (a) a 1ª ingestão cria 10 itens; a 2ª refaz **apenas** os anos da janela de atualização (2013–2014), todos `unchanged`, e o restante vem de `cached`; (b) se a fonte revisa um dado recente, só ele vira `updated` (`n_fetches = 2`) e o ano fora da janela permanece intocado (`n_fetches = 1`); (c) os blocos de clima, uma vez baixados, não são rebuscados.

## 6. Silver determinística

`write_parquet_dataset` grava em diretório temporário e **troca** o destino; reexecutar o silver produz os mesmos dados sem arquivos órfãos.

## 7. Partições Parquet

| Tabela | Partição | Razão |
|---|---|---|
| `pam_municipio`, `pam_uf`, `conab_uf` | `especie` | filtro quase universal (nunca misturar espécies) |
| `clima_diario` | `ano` | filtro por período; 26 partições |
| demais | sem partição | volume desprezível |

**Evitado:** partição por município (645) ou por `ano/mês` (165 arquivos) — o benchmark (seção 6 do notebook 07) mostra o efeito dos arquivos pequenos.

## 8. Células de clima

- Grade nativa do MERRA-2: 0,5° × 0,625°. Cada município recebe o `cell_id` da **célula que contém o centroide**.
- Só as células com municípios produtores são buscadas (80 células para SP).
- `cell_id = "<ilat>_<ilon>"`: **tem sublinhado**. Parse com `rsplit("_", 2)`. **Erro real:** um `split("_")` simples colapsou 80 células em 11; há teste de regressão.

## 9. Janelas fenológicas sem vazamento

- Todas terminam em 31/mar de *t*; a **data de corte** de previsão é 1º/mai de *t*.
- A tabela guarda `ultima_data_usada` e `data_corte_previsao`; o teste exige `ultima_data_usada < data_corte_previsao` em **todas** as linhas.
- Janela com mês faltante ⇒ NULL.

## 10. Preço

1. `brl_saca_nominal = usd_kg × 60 × brl_usd` (média mensal; depois média anual dos meses).
2. `brl_saca_real_2025 = brl_saca_nominal × (IPCA médio 2025 ÷ IPCA do mês)`.
3. No painel: `preco_real_lag1` = valor do **ano anterior** (o preço do próprio ano *t* não é conhecido em 1º/mai).

## 11. Elegibilidade para modelagem (`elegivel_modelo`)

Área colhida ≥ 100 ha em *t* e *t*−1 **e** rendimentos de *t* e *t*−1 conhecidos. **Por quê:** rendimentos de áreas muito pequenas são dominados por arredondamento e estimativas; incluí-los infla o erro percentual sem informar nada agronômico. **Custo:** exclui municípios pequenos; as conclusões valem para **produtores com área relevante**.

## 12. Separação de espécies

`especie ∈ {total, arabica, canephora}`. O painel é **apenas arábica** e começa em 2012. Antes de 2012 só existe "total"; **não se tenta desagregar** (seria inventar dado).

## 13. Logs

`logging_utils.get_logger` escreve no console e em `logs/pipeline.log` (rotativo). Cada etapa do pipeline registra início, fim, contagens e status no manifesto (`runs`).

## Comparação de engines

pandas, Polars, DuckDB e Spark estão **comparados em desempenho e resultado** no benchmark (ver `08_benchmark_e_custos.md`). No pipeline, o gold usa DuckDB (SQL), e a modelagem usa pandas/scikit-learn.
