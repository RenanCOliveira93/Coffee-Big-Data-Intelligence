# 03 · Volume real × benchmark sintético

> **Princípio do projeto:** não faz sentido chamar uma tabela pequena de *Big Data* só porque foi processada com Spark. Esta página separa, de forma explícita, **o que é dado real** do que é **dado sintético gerado para teste de desempenho**.

## 1. Volume REAL (lago de dados local)

| Tabela | Linhas | Observação |
|---|---:|---|
| `clima_diario` (silver) | **759 760** | 80 células × ~9 500 dias (2000–2025) — **a maior tabela real** |
| `pam_municipio` | 51 040 | município × espécie × ano |
| `clima_mensal` | 24 960 | agregação do clima |
| `painel_cafe_arabica` | 4 398 | 1 663 linhas **elegíveis** à modelagem |
| `clima_features` | 2 080 | célula × ano |
| `pam_uf`, `conab_uf` | 2 160 / 1 812 | |
| demais | < 1 000 | preços, câmbio, IPCA, dimensões |

Tamanho em disco (Parquet/JSON compactado): bronze ≈ 17 MB, silver ≈ 7 MB, gold ≈ 1 MB.

**Conclusão:** o volume real é de **centenas de milhares de linhas**, algo que pandas, Polars ou DuckDB processam em **milissegundos a dezenas de milissegundos**. O desafio de dados deste projeto é **qualidade, cobertura e poucos anos independentes** (≈ 13 safras), não volume.

## 2. Benchmark SINTÉTICO (opcional)

| Rótulo | Linhas | Para quê |
|---|---:|---|
| 1M | 1 000 000 | ponto de partida |
| 10M | 10 000 000 | |
| 50M | 50 000 000 | ≈ 66× o volume real |

- **Gerador:** `coffeebdi.synth.generate(n_rows, caminho, seed, max_mem_gb)`.
- **Esquema:** espelha `silver.clima_diario` (`cell_id`, `date`, `ano`, `mes`, `t2m_max`, `t2m_min`, `prec_mm`) + dimensão de células (`uf`, `altitude_m`).
- **Distribuição:** temperatura com sazonalidade senoidal + diferença entre células + ruído; chuva por mistura "dia chuvoso" × gama. **Não reproduz** o clima real; serve só para dar volume e cardinalidade realistas.
- **Memória:** o gerador escreve em **blocos**; `max_mem_gb` define o tamanho do bloco (25% do limite, até 5M linhas). O pico depende do bloco, não do total.
- **Determinismo:** fixados `seed` **e** `max_mem_gb`, o resultado é idêntico. Mudar o limite muda o tamanho do bloco e, com ele, a ordem dos sorteios (dados diferentes).
- **Rotulagem:** o arquivo Parquet traz o metadado `synthetic=true`, e os arquivos ficam em `data/bench/synthetic/` com prefixo `SYNTH_`.

## 3. Como o projeto evita confusão

1. Nomes de arquivo e pastas distintos (`SYNTH_*` × `REAL_*`).
2. Metadado Parquet `synthetic=true`.
3. No notebook 07, as tabelas trazem a coluna `label` (`REAL`, `1M`, `10M`, `50M`) e o texto repete que os sintéticos **não representam café**.
4. O README e esta página trazem o aviso.

## 4. O que o benchmark permite concluir

- Como o **tempo** e a **memória** de cada engine crescem com o número de linhas (em hardware e operações específicos).
- Quanto custa a **inicialização** de uma engine (JVM do Spark: ~3 s).
- Efeito do **particionamento** e dos **arquivos pequenos**.

## 5. O que o benchmark **não** permite concluir

- Que o **Spark seja pior** em geral: não foi testado em cluster nem com dados maiores que a RAM.
- Que **café** seja um problema de Big Data.
- Que os tempos valham em outro hardware, com disco em rede ou dados com chaves de alta cardinalidade.

Resultados completos em `docs/pt-BR/08_benchmark_e_custos.md` e `notebooks/07_benchmark_bigdata.ipynb`.
