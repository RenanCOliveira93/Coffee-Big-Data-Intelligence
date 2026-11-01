"""Gera dados sintéticos (se faltarem), recorta os dados reais e roda o benchmark de engines.

Uso: python scripts/run_benchmark.py [--sizes 1M,10M,50M] [--threads 4] [--mem-gb 8] [--engines pandas,polars,duckdb,spark]
Resultados: outputs/benchmark_results.json (+ .parquet) e outputs/benchmark_partition.json
SINTÉTICO != volume real: o resultado separa explicitamente os dois.
"""
import argparse
import json
import sys
import time
from pathlib import Path

import duckdb
import pandas as pd

from coffeebdi import bench, config, synth
from coffeebdi.lake import Lake


def partition_experiment(src: Path, workdir: Path, reps: int = 5) -> dict:
    """Efeito do particionamento Parquet em hive: filtro ano=2015 com e sem partição, e o custo de 'arquivos pequenos'."""
    out = {}
    workdir.mkdir(parents=True, exist_ok=True)
    con = duckdb.connect()
    con.execute("SET threads=4")
    for name, cols in (("ano", "ano"), ("ano_mes", "ano, mes")):
        d = workdir / f"part_{name}"
        if not d.exists():
            con.execute(f"COPY (SELECT * FROM read_parquet('{src}')) TO '{d}' (FORMAT PARQUET, PARTITION_BY ({cols}), COMPRESSION ZSTD)")
        out[f"n_arquivos_{name}"] = sum(1 for _ in d.rglob("*.parquet"))
    def timeit(sql):
        ts = []
        for _ in range(reps):
            t = time.perf_counter(); con.execute(sql).fetchall(); ts.append(time.perf_counter() - t)
        return sorted(ts)[len(ts) // 2]
    f = f"read_parquet('{src}')"
    out["arquivo_unico_filtro_ano"] = timeit(f"SELECT sum(prec_mm) FROM {f} WHERE ano = 2015")
    out["arquivo_unico_scan_total"] = timeit(f"SELECT sum(prec_mm) FROM {f}")
    for name in ("ano", "ano_mes"):
        g = f"read_parquet('{workdir / ('part_' + name)}/**/*.parquet', hive_partitioning=true)"
        out[f"part_{name}_filtro_ano"] = timeit(f"SELECT sum(prec_mm) FROM {g} WHERE ano = 2015")
        out[f"part_{name}_scan_total"] = timeit(f"SELECT sum(prec_mm) FROM {g}")
    return out


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--sizes", default="1M,10M,50M")
    ap.add_argument("--engines", default=",".join(bench.ENGINES))
    ap.add_argument("--threads", type=int, default=config.BENCH_THREADS)
    ap.add_argument("--mem-gb", type=float, default=config.BENCH_MEM_GB)
    ap.add_argument("--gen-mem-gb", type=float, default=2.0, help="teto de memória do GERADOR")
    ap.add_argument("--timeout", type=int, default=1500)
    ap.add_argument("--out", default="benchmark_results.json", help="arquivo em outputs/ (o notebook 07 lê benchmark_results.json)")
    a = ap.parse_args()
    sizes = [s for s in a.sizes.split(",") if s]
    engines = a.engines.split(",")
    sources, gen_info = [], {}
    for lab in sizes:
        p = config.SYNTH / f"SYNTH_clima_{lab}.parquet"
        if not p.exists():
            gen_info[lab] = synth.generate(synth.SIZES[lab], p, max_mem_gb=a.gen_mem_gb)
        sources.append((lab, p, p.with_name(p.stem + "_dim_cell.parquet")))
    real = synth.export_real_for_benchmark(Lake())
    sources.append(("REAL", Path(real["path"]), Path(real["dim_path"])))
    reps = {"1M": 5, "10M": 3, "50M": 2, "REAL": 7}
    df = bench.run_matrix(sources, engines, threads=a.threads, mem_gb=a.mem_gb, reps_by_label=reps, timeout_s=a.timeout,
                          log=lambda s: print(s, flush=True))
    out = {"system": bench.system_info(), "config": {"threads": a.threads, "mem_gb": a.mem_gb, "engines": engines},
           "real_rows": real["rows"], "real_cells": real["cells"], "parity_issues": bench.parity_check(df),
           "results": json.loads(df.drop(columns=["sums"]).to_json(orient="records"))}
    config.OUTPUTS.mkdir(exist_ok=True)
    (config.OUTPUTS / a.out).write_text(json.dumps(out, indent=2))
    if "10M" in sizes:
        part = partition_experiment(config.SYNTH / "SYNTH_clima_10M.parquet", config.SYNTH / "part10M")
        (config.OUTPUTS / "benchmark_partition.json").write_text(json.dumps(part, indent=2))
        print(json.dumps(part, indent=2))
    print("PARIDADE:", out["parity_issues"])
    print("FIM benchmark")


if __name__ == "__main__":
    sys.exit(main())
