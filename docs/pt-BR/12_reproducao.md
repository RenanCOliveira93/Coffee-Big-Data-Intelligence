# 12 · Reprodução: comandos passo a passo

Testado em macOS (arm64) com Python 3.11.9. As ingestões precisam de **internet** (APIs do IBGE, NASA POWER, BCB; arquivos da CONAB e do Banco Mundial).

## 1. Ambiente

```bash
cd 02-Coffee-Big-Data-Intelligence
python3.11 -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt
pip install -e .
cp .env.example .env        # ajuste se necessário
```

**Java (apenas para PySpark):** instale um JDK 17+ ou deixe o projeto detectar/usar `.tools/jdk` (`spark_utils.find_java_home`). Sem Java, os testes marcados `spark` são **pulados** automaticamente; no benchmark, exclua o Spark com `--engines pandas,polars,duckdb`.

## 2. Pipeline de dados

```bash
python scripts/run_pipeline.py all --ufs 35            # ingest + silver + gold + qualidade (SP)
python scripts/run_pipeline.py ingest                   # só ingestão (idempotente)
python scripts/run_pipeline.py silver
python scripts/run_pipeline.py gold
python scripts/run_pipeline.py dq                       # só testes de qualidade
python scripts/run_pipeline.py all --ufs 35,31          # expandir para MG (veja ressalvas)
```

Opções: `--include-current-year` (bloco aberto do clima), `--skip-conab`, `--no-strict` (alerta mas não aborta em erro de qualidade).

Resultados em `data/lake/{bronze,silver,gold,_meta}`; logs em `logs/pipeline.log`.

## 3. Notebooks

```bash
python scripts/build_notebooks.py        # gera notebooks/*.ipynb a partir de scripts/nbdefs/
python scripts/run_notebooks.py          # executa todos
python scripts/run_notebooks.py 05 06    # executa apenas alguns
```

Figuras em `outputs/figures/`.

## 4. Benchmark

```bash
python scripts/run_benchmark.py          # gera sintéticos, roda a matriz e o experimento de partição
python scripts/run_benchmark.py --sizes 1M --engines pandas,polars,duckdb --out benchmark_leve.json   # versão leve, sem Java
# outras opções: --threads, --mem-gb, --gen-mem-gb (teto de memória do gerador), --timeout
```

Gera `data/bench/synthetic/SYNTH_clima_{1M,10M,50M}.parquet`, `outputs/benchmark_results.json` e `outputs/benchmark_partition.json`. O de 50M ocupa ≈ 500 MB. **O notebook 07 lê `outputs/benchmark_results.json` e espera as 4 engines e os 4 rótulos** — por isso a versão leve grava em outro arquivo (`--out`); a execução completa sobrescreve o resultado registrado. Para só estimar o impacto de memória do gerador, veja a seção 7 do notebook 07.

```python
from coffeebdi import synth
synth.generate(10_000_000, "data/bench/synthetic/meu.parquet", seed=1, max_mem_gb=1.0)
```

## 5. Testes

```bash
pytest -q                                # suíte completa
pytest -q -m "not spark"                 # sem Java
pytest tests/test_ingest_idempotent.py -q
```

Os testes usam **amostras reais mínimas** em `tests/fixtures/` e **rede simulada**; `test_pipeline_real.py` valida o lago local e é **pulado** se ele não existir (rode o pipeline antes).

## 6. MLflow (opcional)

```bash
pip install mlflow
USE_MLFLOW=1 python scripts/run_notebooks.py 06
mlflow ui --backend-store-uri sqlite:///mlflow.db
```

## 7. Variáveis de ambiente

| Variável | Padrão | Efeito |
|---|---|---|
| `COFFEE_UFS` | `35` | UFs ingeridas (códigos IBGE) |
| `POWER_START_YEAR` / `POWER_END_YEAR` | 2000 / 2025 | janela de clima |
| `PAM_START_YEAR` | 1974 | início da série PAM |
| `PAM_REFRESH_RECENT_YEARS` | 2 | anos recentes rebuscados |
| `BENCH_THREADS` | 4 | threads por engine |
| `BENCH_MEM_GB` | 8 | orçamento de memória do benchmark |
| `JAVA_HOME` | vazio | JDK para o Spark |
| `USE_MLFLOW` | 0 | registra experimentos |

## 8. Problemas frequentes

| Sintoma | Causa provável | Solução |
|---|---|---|
| falha de TLS em alguma fonte | certificado da fonte | **não** desative a verificação; documente a indisponibilidade |
| Spark não inicia | Java ausente | defina `JAVA_HOME` ou rode sem Spark |
| Pink Sheet "terminando em 2024" | URL antiga | atualize o projeto (o conector descobre a URL) |
| MLflow `MlflowException` sobre filestore | backend de arquivos descontinuado | use `sqlite:///mlflow.db` (já é o padrão do projeto) |
| notebook sem dados | pipeline não rodou | `python scripts/run_pipeline.py all` |

## 9. Licença dos dados

`data/` **não é versionado** nem redistribuído (CONAB: CC BY-ND; licenças do Banco Mundial e do BCB não confirmadas). Cada pessoa gera o lago localmente a partir das fontes originais. Veja `13_limitacoes_e_licencas.md`.
