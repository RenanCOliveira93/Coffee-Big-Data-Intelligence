"""Gerador SINTÉTICO de séries climáticas diárias em escala (1M, 10M, 50M linhas) para BENCHMARK.

!!! Estes dados NÃO representam volume real da cafeicultura. Servem apenas para medir como engines de
processamento se comportam com mais linhas. O volume real do projeto está em `docs/pt-BR/03_volume_real_vs_sintetico.md`.

Esquema (espelha `silver.clima_diario`): cell_id:int32, date:date32, ano:int16, mes:int8, t2m_max, t2m_min, prec_mm:float32.
Layout: ordenado por (cell_id, date), `DAYS_PER_CELL` dias por célula -> n_cells = n_rows / DAYS_PER_CELL.
Memória: gera em blocos (`chunk_rows`) e escreve incrementalmente em Parquet; o pico depende do bloco, não do total.
"""
from __future__ import annotations

import time
from pathlib import Path

import numpy as np
import pyarrow as pa
import pyarrow.parquet as pq

from . import config
from .logging_utils import get_logger

log = get_logger("synth")

DAYS_PER_CELL = 5000
START = np.datetime64("2005-01-01")
SIZES = {"1M": 1_000_000, "10M": 10_000_000, "50M": 50_000_000}
N_UF = 8

SCHEMA = pa.schema([
    ("cell_id", pa.int32()), ("date", pa.date32()), ("ano", pa.int16()), ("mes", pa.int8()),
    ("t2m_max", pa.float32()), ("t2m_min", pa.float32()), ("prec_mm", pa.float32()),
], metadata={b"synthetic": b"true", b"purpose": b"benchmark only - not real coffee data"})


def bytes_per_row_in_memory() -> int:
    return 4 + 4 + 2 + 1 + 4 + 4 + 4 + 8 * 2   # colunas + temporários do gerador (estimativa conservadora)


def chunk_rows_for_memory(max_mem_gb: float, fraction: float = 0.25) -> int:
    """Linhas por bloco para que o gerador use no máximo `fraction` de `max_mem_gb`."""
    rows = int(max_mem_gb * 1e9 * fraction / bytes_per_row_in_memory())
    rows = max(DAYS_PER_CELL, min(rows, 5_000_000))
    return (rows // DAYS_PER_CELL) * DAYS_PER_CELL


def generate(n_rows: int, out_path: Path | str, seed: int = 42, max_mem_gb: float = 2.0,
             days_per_cell: int = DAYS_PER_CELL) -> dict:
    """Gera `n_rows` (arredondado para múltiplo de days_per_cell) e a tabela dimensão de células."""
    out_path = Path(out_path)
    out_path.parent.mkdir(parents=True, exist_ok=True)
    n_cells = max(1, n_rows // days_per_cell)
    total = n_cells * days_per_cell
    chunk_cells = max(1, chunk_rows_for_memory(max_mem_gb) // days_per_cell)
    rng = np.random.default_rng(seed)
    days = START + np.arange(days_per_cell).astype("timedelta64[D]")
    date32 = days.astype("datetime64[D]").astype("int32")
    years = days.astype("datetime64[Y]").astype(int) + 1970
    months = (days.astype("datetime64[M]").astype(int) % 12) + 1
    doy = (days - days.astype("datetime64[Y]")).astype(int)
    season = np.cos(2 * np.pi * (doy - 15) / 365.25)          # máx. em jan
    t0 = time.time()
    with pq.ParquetWriter(out_path, SCHEMA, compression="zstd") as w:
        for c0 in range(0, n_cells, chunk_cells):
            cs = np.arange(c0, min(c0 + chunk_cells, n_cells), dtype="int32")
            k = len(cs)
            base = rng.normal(0, 1.5, (k, 1))                   # diferença entre células
            tmax = 27 + base + 4 * season + rng.normal(0, 1.2, (k, days_per_cell))
            tmin = tmax - (8 + rng.gamma(4, 0.5, (k, days_per_cell)))
            wet = rng.random((k, days_per_cell)) < (0.25 + 0.2 * season)
            prec = np.where(wet, rng.gamma(0.7, 14, (k, days_per_cell)), 0.0)
            tbl = pa.table({
                "cell_id": np.repeat(cs, days_per_cell),
                "date": pa.array(np.tile(date32, k), type=pa.date32()),
                "ano": np.tile(years.astype("int16"), k), "mes": np.tile(months.astype("int8"), k),
                "t2m_max": tmax.astype("float32").ravel(), "t2m_min": tmin.astype("float32").ravel(),
                "prec_mm": prec.astype("float32").ravel(),
            }, schema=SCHEMA)
            w.write_table(tbl, row_group_size=1_000_000)
    dim_path = out_path.with_name(out_path.stem + "_dim_cell.parquet")
    dim = pa.table({"cell_id": np.arange(n_cells, dtype="int32"),
                    "uf": pa.array([f"UF{i % N_UF}" for i in range(n_cells)]),
                    "altitude_m": rng.uniform(100, 1200, n_cells).astype("float32")})
    pq.write_table(dim, dim_path, compression="zstd")
    info = {"rows": total, "cells": n_cells, "path": str(out_path), "dim_path": str(dim_path),
            "bytes": out_path.stat().st_size, "seconds": round(time.time() - t0, 1), "synthetic": True}
    log.info("SINTÉTICO gerado: %s", info)
    return info


def export_real_for_benchmark(lake, out_path: Path | str | None = None) -> dict:
    """Recorte dos dados REAIS de clima (silver) no mesmo esquema do benchmark (cell_id → inteiro)."""
    import duckdb
    out_path = Path(out_path or config.BENCH_REAL / "REAL_clima_bench.parquet")
    out_path.parent.mkdir(parents=True, exist_ok=True)
    con = duckdb.connect()
    src = f"read_parquet('{lake.silver / 'clima_diario'}/**/*.parquet', hive_partitioning=true)"
    con.execute(f"""
        COPY (SELECT dense_rank() OVER (ORDER BY cell_id) - 1 AS cell_id, "date",
                     CAST(ano AS SMALLINT) AS ano, CAST(mes AS TINYINT) AS mes,
                     t2m_max, t2m_min, prec_mm
              FROM {src} ORDER BY cell_id, "date") TO '{out_path}' (FORMAT PARQUET, COMPRESSION ZSTD)""")
    n_cells = con.execute(f"SELECT count(DISTINCT cell_id) FROM {src}").fetchone()[0]
    dim_path = out_path.with_name(out_path.stem + "_dim_cell.parquet")
    con.execute(f"""
        COPY (SELECT dense_rank() OVER (ORDER BY cell_id) - 1 AS cell_id, 'UF35' AS uf, CAST(elev_m AS FLOAT) AS altitude_m
              FROM read_parquet('{lake.silver / 'clima_celula'}/**/*.parquet') ORDER BY cell_id)
        TO '{dim_path}' (FORMAT PARQUET)""")
    rows = con.execute(f"SELECT count(*) FROM read_parquet('{out_path}')").fetchone()[0]
    con.close()
    return {"rows": rows, "cells": n_cells, "path": str(out_path), "dim_path": str(dim_path), "synthetic": False}
