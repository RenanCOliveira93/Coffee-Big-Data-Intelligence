"""Gera os 8 notebooks em notebooks/. Uso: python scripts/build_notebooks.py"""
import importlib
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))

OUT = Path(__file__).resolve().parents[1] / "notebooks"
NAMES = ["01_exploracao_fontes", "02_limpeza_qualidade", "03_eda_cafeicultura", "04_clima_produtividade",
         "05_series_temporais", "06_previsao_producao", "07_benchmark_bigdata", "08_insights_negocio"]
OUT.mkdir(exist_ok=True)
for name in NAMES:
    try:
        mod = importlib.import_module(f"nbdefs.nb{name[:2]}")
    except ModuleNotFoundError:
        print("(definição ausente)", name)
        continue
    mod.build().save(OUT / f"{name}.ipynb")
    print("gerado", name)
