# 06 · Qualidade de dados

Testes em `src/coffeebdi/quality.py`, executados pelo pipeline (`run_dq`) e gravados em `gold/dq_results`. **Severidade `error`** interrompe o pipeline (modo estrito); **`warn`** registra e segue.

## Verificações implementadas

| Verificação | O que garante |
|---|---|
| `not_null` | colunas obrigatórias preenchidas |
| `unique_key` | chave única (ex.: `cod_ibge + especie + ano`) |
| `in_range` | faixa física plausível (chuva 0–500 mm/dia; T2M −10 a 45 °C; …) |
| `valid_ibge` | dígito verificador do código de município |
| `referential` | todo município do PAM existe em `dim_municipio` |
| `min_rows` | tamanho mínimo (ex.: ≥ 500 linhas elegíveis) |
| `consecutive_years` | série completa (ex.: arábica 2012–2025, sem buracos) |
| `yield_consistency` | `rendimento ≈ produção ÷ área` (tolerância de 2%) |
| `repeated_yield` | fração de pares ano-a-ano com **rendimento idêntico** |
| `freshness` | existe dado do ano mais recente esperado |

## Resultado da última execução (25 verificações)

- **22 passaram.**
- **3 alertas (`warn`) não passaram** — todos de **natureza dos dados**, não de erro do pipeline:

| Alerta | Resultado | Interpretação |
|---|---|---|
| `range: rendimento ≤ 6 000 kg/ha` (todas as espécies) | 13 linhas fora | valores atípicos na fonte; para **arábica** vale a verificação de erro (≤ 6 000) e **passa** |
| `rendimento_consistente (tol 2%)` | 2 de 25 661 linhas | divergência entre rendimento informado e produção ÷ área |
| `rendimento_repetido_ano_a_ano (≤ 25%)` | **1 518 de 3 938 pares (≈ 38,5%)** | o rendimento do município **repete exatamente** o do ano anterior; sinal forte de **estimativa administrativa** |

## O achado de qualidade mais importante: rendimentos repetidos

Em arábica, ≈ 38,5% dos pares consecutivos (município, ano) têm **rendimento idêntico** ao do ano anterior, e metade dos valores é **múltiplo de 100 kg/ha**. Isso é compatível com **estimativas** e **não** com medições independentes a cada safra. Consequências:

1. **Previsão municipal tem teto de qualidade** — o "ruído" está no próprio alvo.
2. **Correlações com clima ficam atenuadas.**
3. **"Repetir o ano anterior" é um baseline muito forte.**
4. O projeto **não corrige** esses valores (seria inventar); apenas os sinaliza e discute no notebook 02.

## Decisões de severidade

| Decisão | Motivo |
|---|---|
| rendimento > 6 000 kg/ha é `warn` para todas as espécies | o limite foi calibrado para arábica; outras espécies/total podem ter faixa diferente. Vira **erro** só para arábica 2012+ |
| limiar de repetição em 25% | limiar fixado após observar a distribuição; é **parâmetro**, não verdade |
| `freshness` é `warn` | atraso de publicação não deve derrubar o pipeline |

## Boas práticas aplicadas

- Testes de qualidade **na camada onde o risco nasce** (silver) e na camada de consumo (gold).
- Resultado **persistido** (`dq_results`) para auditoria, não só impresso.
- Cada verificação retorna `n_failed` e `n_total`: **fração**, não só "passou/falhou".
- Testes unitários cobrem o **próprio verificador** (`tests/test_quality.py`): um verificador que nunca falha não protege nada.
