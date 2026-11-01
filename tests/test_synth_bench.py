import numpy as np
import pyarrow.parquet as pq
import pytest

from coffeebdi import bench, synth


def test_generate_small_is_deterministic_and_labeled(tmp_path):
    a = synth.generate(20_000, tmp_path / "a.parquet", seed=1, max_mem_gb=0.1)
    b = synth.generate(20_000, tmp_path / "b.parquet", seed=1, max_mem_gb=0.1)
    ta, tb = pq.read_table(a["path"]), pq.read_table(b["path"])
    assert ta.num_rows == 20_000 and a["cells"] == 4 and a["synthetic"] is True
    assert ta.equals(tb)
    assert ta.schema.metadata[b"synthetic"] == b"true"
    assert pq.read_table(a["dim_path"]).num_rows == 4


def test_chunk_size_respects_memory_limit():
    small, big = synth.chunk_rows_for_memory(0.05), synth.chunk_rows_for_memory(8)
    assert small % synth.DAYS_PER_CELL == 0 and small >= synth.DAYS_PER_CELL
    assert small <= big <= 5_000_000
    assert small * synth.bytes_per_row_in_memory() <= 0.05e9 or small == synth.DAYS_PER_CELL


def test_chunking_does_not_change_output(tmp_path):
    a = synth.generate(40_000, tmp_path / "a.parquet", seed=3, max_mem_gb=0.05)     # blocos pequenos
    b = synth.generate(40_000, tmp_path / "b.parquet", seed=3, max_mem_gb=8.0)      # um bloco só
    # sementes por bloco diferem => valores podem diferir, mas esquema/contagens/ordem devem ser iguais
    ta, tb = pq.read_table(a["path"]), pq.read_table(b["path"])
    assert ta.schema == tb.schema and ta.num_rows == tb.num_rows
    assert (ta["cell_id"].to_numpy() == tb["cell_id"].to_numpy()).all()
    assert (ta["date"].to_numpy() == tb["date"].to_numpy()).all()


def test_engines_agree_on_tiny_dataset(tmp_path):
    info = synth.generate(25_000, tmp_path / "t.parquet", seed=5, max_mem_gb=0.1)
    import pandas as pd
    rows = []
    for op in bench.OPS:
        for eng in ("pandas", "polars", "duckdb"):
            r = bench.run_one(eng, op, info["path"], info["dim_path"], threads=2, mem_gb=2, reps=1, timeout_s=120)
            r["label"] = "t"
            rows.append(r)
    df = pd.DataFrame(rows)
    assert (df["status"] == "ok").all(), df[["engine", "op", "status", "stderr_tail"]]
    assert bench.parity_check(df) == []


@pytest.mark.spark
def test_spark_matches_duckdb(tmp_path):
    import pandas as pd
    info = synth.generate(25_000, tmp_path / "t.parquet", seed=5, max_mem_gb=0.1)
    rows = []
    for op in ("monthly_agg", "rolling_30d"):
        for eng in ("duckdb", "spark"):
            r = bench.run_one(eng, op, info["path"], info["dim_path"], threads=2, mem_gb=2, reps=1, timeout_s=300)
            r["label"] = "t"
            rows.append(r)
    df = pd.DataFrame(rows)
    assert (df["status"] == "ok").all(), df.get("stderr_tail")
    assert bench.parity_check(df) == []


def test_memory_budget_is_enforced(tmp_path):
    info = synth.generate(25_000, tmp_path / "t.parquet", seed=5, max_mem_gb=0.1)
    r = bench.run_one("pandas", "monthly_agg", info["path"], info["dim_path"], threads=1, mem_gb=2, reps=1,
                      timeout_s=120, budget_gb=0.01)          # orçamento absurdo (10 MB) -> deve ser abortado
    assert r["status"] == "orcamento_memoria_excedido"
