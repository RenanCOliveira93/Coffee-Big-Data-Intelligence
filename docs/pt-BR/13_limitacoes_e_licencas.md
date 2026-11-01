# 13 · Limitações, dependências externas e licenças

## 1. Status das dependências externas (o que **não** ficou 100%)

| Item | Status | Observação |
|---|---|---|
| IBGE SIDRA (PAM), localidades, Censo 2022 | ✅ funcionando | verificado em outubro de 2026 |
| NASA POWER | ✅ funcionando | 80 células de SP |
| CONAB (gov.br) | ✅ funcionando com TLS verificado | domínio antigo falhou em TLS |
| Banco Mundial (Pink Sheet) | ✅ funcionando | URL descoberta pela página; **licença não confirmada** |
| BCB SGS | ✅ funcionando | **termos não verificados em detalhe** |
| **INMET** | ❌ **indisponível** | falha de **verificação TLS**; **não** foi contornada (política do projeto) |
| **Preço ao produtor** | ❌ não incluído | nenhuma fonte com metodologia e acesso confirmados dentro do projeto |
| PySpark | ✅ com Java | sem Java, os testes `spark` são pulados e o benchmark deve excluir o Spark (`--engines`) |
| MLflow | ✅ opcional | exige SQLite como backend |
| Earth Engine / MapBiomas | n/a neste projeto | só no Projeto 01 |

## 2. Limitações metodológicas

1. **Dados oficiais são estimativas** (PAM) com repetição (≈ 38,5% de pares idênticos em arábica).
2. **≈ 13 safras independentes** para qualquer relação com clima.
3. **Clima de reanálise (~55 km)**: não vê geada local, relevo ou microclima; o município herda a célula.
4. **Altitude da célula** ≠ altitude da lavoura.
5. **Sem manejo, poda, idade, cultivar, solo ou custos.**
6. **Preço internacional convertido** ≠ preço pago ao produtor.
7. **Arábica 2012+.** Antes, só "total"; não se desagrega.
8. **Escopo SP.** Conclusões não se transferem a MG/ES nem ao conilon.
9. **Elegibilidade** (área ≥ 100 ha) exclui pequenos produtores.
10. **Modelos** não batem baselines simples; intervalos têm cobertura variável por ano.
11. **Benchmark em uma máquina**, com dados sintéticos de distribuição simples; **cenário distribuído não medido**.
12. **Estimativa CONAB 2026** é estimativa; não foi validada (a safra não fechou).

## 3. O que este projeto **não** afirma

- Que café é um problema de *Big Data*.
- Que clima causa (ou não) produtividade.
- Que o Spark é inferior em geral.
- Que as previsões sirvam para crédito, seguro ou investimento sem validação adicional.

## 4. Licenças

| Fonte | Licença / termos | Consequência no projeto |
|---|---|---|
| IBGE | dados abertos; termos **não revisados juridicamente aqui** | citar a fonte |
| NASA POWER | acesso livre; recomendada citação; termos **não revisados em detalhe** | citar a fonte |
| CONAB | **CC BY-ND** (atribuição; sem obras derivadas) | **não redistribuir** derivados; lago fora do git |
| Banco Mundial (Pink Sheet) | **não confirmada** | não redistribuir; usar localmente |
| BCB | **não verificada** | idem |

**Política:** `data/lake`, `data/bench` e `mlflow.db` estão no `.gitignore`. O repositório contém **código, documentação e amostras mínimas de teste** (fixtures reais pequenas, apenas para testes unitários). **Confira os termos de cada fonte** antes de publicar dados derivados.

O **código** deste projeto pode ser licenciado conforme a política da sua organização (nenhuma licença de código foi definida aqui).

## 5. Riscos de uso indevido

| Uso | Risco |
|---|---|
| decisão de crédito com base no modelo | erro de previsão ≈ 15% (sMAPE) municipal; sem poder de discriminar anos de ruptura |
| ranking de regiões sem IC | sobreposição de ICs |
| "tendência" a partir de dois anos | bienalidade |
| tratar a série sintética como café | **falso**; veja `03_volume_real_vs_sintetico.md` |

## 6. Trabalhos futuros

1. Conector INMET quando o TLS da fonte for corrigido; comparar estações × grade.
2. Preço ao produtor com metodologia verificada.
3. Dados de propriedade (talhão) para testar causalidade com desenho adequado.
4. Expansão para MG e ES, com revisão das premissas de elegibilidade e janelas.
5. Benchmark em cluster ou com dados maiores que a RAM para localizar o ponto de virada do Spark.
6. Imagens de satélite (integração com o Projeto 01 – AgroGeo Analytics) para áreas e idade dos talhões.
