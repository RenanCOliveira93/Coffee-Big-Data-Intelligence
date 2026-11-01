# 11 · Exercícios

Dificuldade: ★ básico · ★★ intermediário · ★★★ avançado. Respostas esperadas apontam **onde olhar**, não números fixos (os dados são atualizados).

## Engenharia de dados

1. ★ Rode `python scripts/run_pipeline.py all` duas vezes. Compare os status da 2ª execução (`cached`/`unchanged`) e explique por que o hash não muda.
2. ★★ Mude `PAM_REFRESH_RECENT_YEARS` para 0 e para 4. Quantas chamadas de rede a 2ª execução faz em cada caso?
3. ★★ Remova uma linha do JSON bronze de um ano e rode `silver`. Qual teste de qualidade acusa o problema? Por quê?
4. ★★ Implemente `pivot_table` no lugar de `pivot` no silver e rode os testes. Qual teste falha e qual é a diferença de linhas?
5. ★★★ Adicione MG (`COFFEE_UFS=35,31`) e investigue o custo de ingestão. O que muda no painel? Quais premissas de SP (altitude, janelas, área mínima de 100 ha) não valem em MG?
6. ★★★ Escreva um conector para o INMET que **verifique TLS**. Se o certificado seguir inválido, documente a indisponibilidade em vez de contornar.

## Estatística e séries temporais

7. ★ No notebook 05, mude `first` de 2010 para 2005 e 2015. O ranking dos modelos se mantém?
8. ★★ Acrescente `media_ponderada` (0,6/0,4) e avalie contra o `naive` com o IC pareado.
9. ★★ Calcule o intervalo de 50% e 90% e compare cobertura nominal × observada.
10. ★★ Repita a análise de bienalidade com PAM 2012+ e com CONAB. Por que podem divergir?
11. ★★★ Modele a produção CONAB com SARIMA e compare com `naive_lag2` em *rolling origin*. Vale a complexidade?

## Modelagem

12. ★ Remova `preco_real_lag1` das features e compare o ridge nos dois cenários.
13. ★★ Aplique *clip* nas covariáveis de ano ao intervalo do treino. O MAE de 2018–2019 se recupera?
14. ★★ Troque `first_test` para 2019 e 2021; o XGBoost passa a bater os baselines?
15. ★★★ Acrescente uma feature de **área** relativa e outra de **proporção de área nova** (se existir). Faz diferença?
16. ★★★ Faça validação por **município retido** (*group k-fold*) e compare com a temporal. O que cada uma responde?
17. ★★ Por que sMAPE é enganoso quando o previsto é ≈ 0? Construa um exemplo.

## Benchmark

18. ★ Rode o benchmark com `BENCH_THREADS=1` e `=8`. Qual engine escala melhor?
19. ★★ Gere 100M linhas com `max_mem_gb=4` e rode `monthly_agg` em DuckDB e pandas. O pandas passa do orçamento de 8 GB?
20. ★★ Repartitione o sintético de 10M por `cell_id` e meça o filtro por ano.
21. ★★★ Projete um experimento que **justifique** o Spark (dados maiores que a RAM). O que precisaria mudar no harness?
22. ★ Por que separar `startup_s` da mediana muda a conclusão para dados pequenos?

## Interpretação

23. ★ Reescreva o resultado clima × rendimento em 3 frases para um produtor, sem usar a palavra "correlação" e sem prometer nada.
24. ★★ Um banco quer usar o modelo para limitar crédito rural. Liste 5 razões pelas quais **não** deve.
25. ★★ Diga em que condições **valeria** incorporar clima no modelo (resolução, dados, horizonte).
26. ★★★ Desenhe um estudo que **poderia** estimar efeito causal de irrigação na produtividade (designs: experimento, diferença-em-diferenças, variável instrumental). Que dados faltam?
