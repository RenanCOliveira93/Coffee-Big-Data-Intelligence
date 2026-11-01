"""Utilitários para os notebooks: conexão DuckDB com views sobre o lake e estilo de gráficos."""
from __future__ import annotations

import duckdb

from . import config
from .lake import Lake

SILVER_TABLES = ["pam_municipio", "pam_uf", "dim_municipio", "clima_diario", "clima_celula", "preco_cafe_mensal",
                 "cambio_mensal", "ipca_mensal", "conab_uf"]
GOLD_TABLES = ["clima_mensal", "clima_features", "precos_anuais", "ipca_anual", "painel_cafe_arabica", "conab_vs_pam", "dq_results"]


def duck(lake: Lake | None = None) -> duckdb.DuckDBPyConnection:
    """Conexão em memória com uma view por tabela silver/gold (nome da tabela = nome da view)."""
    lake = lake or Lake()
    con = duckdb.connect()
    for layer, names in ((lake.silver, SILVER_TABLES), (lake.gold, GOLD_TABLES)):
        for n in names:
            p = layer / n
            if p.exists():
                con.execute(f"CREATE VIEW {n} AS SELECT * FROM read_parquet('{p}/**/*.parquet', hive_partitioning=true)")
    return con


def mpl_style():
    import matplotlib.pyplot as plt
    plt.rcParams.update({"figure.dpi": 110, "axes.grid": True, "grid.alpha": .25, "axes.spines.top": False,
                         "axes.spines.right": False, "axes.titlesize": 11, "axes.labelsize": 9})
    (config.OUTPUTS / "figures").mkdir(parents=True, exist_ok=True)
