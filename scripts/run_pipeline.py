"""CLI do pipeline. Ex.: python scripts/run_pipeline.py all --ufs 35"""
import argparse
import json
import sys

from coffeebdi import config, pipeline
from coffeebdi.lake import Lake


def main():
    ap = argparse.ArgumentParser(description="Coffee Big Data Intelligence: pipeline bronze/silver/gold")
    ap.add_argument("step", choices=["ingest", "silver", "gold", "dq", "all"], nargs="?", default="all")
    ap.add_argument("--ufs", default=",".join(map(str, config.UFS)), help="códigos IBGE de UF, separados por vírgula")
    ap.add_argument("--include-current-year", action="store_true", help="inclui bloco aberto do clima (ano corrente)")
    ap.add_argument("--skip-conab", action="store_true")
    ap.add_argument("--no-strict", action="store_true", help="DQ com erro não aborta")
    a = ap.parse_args()
    ufs = [int(x) for x in a.ufs.split(",") if x]
    lake = Lake()
    if a.step == "all":
        out = pipeline.run_all(lake, ufs, a.include_current_year, strict=not a.no_strict, skip_conab=a.skip_conab)
    elif a.step == "ingest":
        out = pipeline.run_ingest(lake, ufs, a.include_current_year, a.skip_conab)
    elif a.step == "silver":
        out = pipeline.run_silver(lake)
    elif a.step == "gold":
        out = pipeline.run_gold(lake)
    else:
        out = pipeline.run_dq(lake).to_dict("records")
    print(json.dumps(out, indent=2, default=str)[:4000])


if __name__ == "__main__":
    sys.exit(main())
