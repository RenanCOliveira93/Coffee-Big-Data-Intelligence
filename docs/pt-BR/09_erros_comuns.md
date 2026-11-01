# 09 · Erros comuns (e os que realmente aconteceram neste projeto)

Cada item tem **sintoma**, **causa** e **como evitar**. Os marcados com ⚠ ocorreram **durante a construção** e têm teste de regressão.

## Dados e ETL

### ⚠ 1. `pivot_table` descartando linhas silenciosamente
- **Sintoma:** 45 293 linhas no silver em vez de 51 040 (−5 747).
- **Causa:** `pivot_table` agrega e **elimina chaves com `NaN`**; o PAM tem valores especiais que viram NaN.
- **Evitar:** use `pivot` (sem agregação) e **compare contagens** antes e depois (`test_silver`; demo no notebook 02).

### ⚠ 2. `cell_id` com sublinhado quebrado em `split("_")`
- **Sintoma:** 80 células viraram 11.
- **Causa:** id `"<ilat>_<ilon>"` tem `_`, e latitudes negativas geram `-43_-82`.
- **Evitar:** `rsplit("_", 2)` com limite; teste de regressão.

### 3. Códigos IBGE como número
- **Sintoma:** junção que retorna zero linhas, sem erro.
- **Causa:** `int` × `str` × `float` (`3538808.0`).
- **Evitar:** `normalize_municipio` e validação do **dígito verificador**.

### ⚠ 4. Código de município errado (de memória)
- **Sintoma:** município "inexistente" ou outro município.
- **Evitar:** `is_valid_municipio`; conferir contra a API de localidades.

### 5. Tratar `-`, `..`, `X` do SIDRA como a mesma coisa
- **Sintoma:** "não produziu" vira "sem dado" (ou o contrário).
- **Evitar:** coluna `*_q` de qualidade (ver `05_decisoes_etl.md`).

### ⚠ 6. URL "estável" que envelhece (Pink Sheet)
- **Sintoma:** série de preços terminando em dezembro de 2024.
- **Causa:** a URL do arquivo muda a cada edição.
- **Evitar:** o conector **descobre** a URL na página oficial.

### 7. Chave de arquivo insegura
- **Sintoma:** `..` ou `/` na chave escapando da pasta.
- **Evitar:** sanitizar chaves (inclusive `..`) — `test_key_sanitization`.

## Tempo e modelagem

### 8. Vazamento por clima do futuro
Janelas até 31/mar de *t*; teste de auditoria nas colunas `ultima_data_usada` × `data_corte_previsao`.

### 9. Validação aleatória em série temporal
Infla o desempenho (≈ 7% no notebook 06) **sem aviso**. Use *expanding window*.

### ⚠ 10. Extrapolação do ridge com covariáveis de ano
- **Sintoma:** MAE de 1 961 kg/ha (cenário B), contra ≈ 250 dos baselines.
- **Causa:** covariáveis constantes por ano, com 3–4 valores distintos no treino; o ano de teste cai fora da faixa.
- **Evitar:** remover/limitar covariáveis de ano, usar árvores, **diagnosticar** antes de concluir "modelo ruim".

### 11. Confundir milhares de linhas com milhares de observações
Clima é do **ano × célula**: ≈ 13 observações independentes. IC por **bootstrap de anos**.

### 12. Comparar 1974 com 2025 como "tendência"
Com bienalidade, um ano alto no começo faz o rendimento "cair" 10% ponta a ponta, enquanto a média de 5 anos **sobe** 26%. Use médias móveis.

### 13. Interpretar sinal de correlação sem ver o dado
Foi preciso **reescrever** textos dos notebooks porque a expectativa ("bienalidade ⇒ correlação negativa no município") contradisse o dado (persistência municipal **positiva**, +0,23; bienalidade **estadual** de −0,66). **Escreva a interpretação depois de ver a saída**, e ancore-a nos números impressos.

### 14. Média de 2 modelos comparada por ranking com poucos anos-alvo
Use IC pareado por bootstrap dos anos-alvo (notebook 05) e reporte quando o IC inclui 0.

### 15. Intervalo "80%" sem checar a cobertura
Os erros são correlacionados no tempo: um ano atípico fura todos os municípios. Reporte a **pior** cobertura anual.

## Software e benchmark

### ⚠ 16. Colunas `bool` com NaN (pandas 3)
`coberto` precisa ser `float` para aceitar NaN (tipagem estrita).

### ⚠ 17. `np.trapz` removido (NumPy 2.4)
Fórmula manual do Gini.

### 18. Medir só o Python em engines com JVM
Subestima o Spark. Meça a **árvore de processos**.

### 19. Misturar inicialização e cálculo
Mediana sem separar `startup_s` favorece o Spark em volumes grandes e o penaliza em pequenos sem que o leitor saiba. Reporte os dois.

### 20. Dois limites de memória medidos no mesmo processo
O alocador reaproveita memória do 1º teste: o 2º parece "usar menos". Meça **cada configuração em processo próprio** (corrigido no notebook 07).

### 21. MLflow com backend de arquivos
Em versões recentes falha por padrão. Use SQLite (`sqlite:///mlflow.db`).

### 22. `curl` com colchetes
`[ ]` em URLs são interpretados como *globbing*; use `-g` ou `%5B/%5D`.

### 23. `sed -i` no macOS
A sintaxe difere do GNU; prefira editar via Python.

### 24. Desativar a verificação TLS "só para testar"
**Nunca.** O INMET foi documentado como indisponível em vez de contornado.
