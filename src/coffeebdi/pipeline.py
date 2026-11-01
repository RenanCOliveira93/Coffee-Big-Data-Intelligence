"""Orquestração do pipeline bronze -> silver -> gold, com qualidade e registro de execução.

Uso (CLI): python scripts/run_pipeline.py [ingest|silver|gold|dq|all] [--ufs 35,31] [--include-current-year]
"""
from __future__ import annotations

import uuid

import pandas as pd

from . import config, gold, ingest, quality, silver
from .lake import Lake
from .logging_utils import get_logger
from .silver import read_table, write_parquet_dataset

log = get_logger("pipeline")


def run_ingest(lake: Lake, ufs=None, include_current_year=False, skip_conab=False) -> dict:
    ufs = ufs or config.UFS
    out = {"territorio": dict(ingest.ingest_territory(lake, ufs)), "pam": dict(ingest.ingest_pam(lake, ufs))}
    cells = ingest.producing_cells(lake)
    out["power"] = dict(ingest.ingest_power(lake, cells, include_current_year=include_current_year))
    out["precos_macro"] = dict(ingest.ingest_prices_macro(lake))
    if not skip_conab:
        out["conab"] = dict(ingest.ingest_conab(lake))
    return out


def run_silver(lake: Lake) -> dict:
    pam, rej = silver.build_pam_municipio(lake)
    uf = silver.build_pam_uf(lake)
    dim = silver.build_dim_municipio(lake)
    clim, cells = silver.build_clima(lake)
    macro = silver.build_precos_macro(lake)
    conab = silver.build_conab(lake) if "arabica" in lake.keys("conab", "serie_historica_cafe") else pd.DataFrame()
    return {"pam_municipio": len(pam), "rejeitados": len(rej), "pam_uf": len(uf), "dim_municipio": len(dim),
            "clima_diario": len(clim), "celulas": len(cells), "conab_uf": len(conab),
            **{k: len(v) for k, v in macro.items()}}


def run_gold(lake: Lake) -> dict:
    return gold.build_all(lake)


def run_dq(lake: Lake, strict: bool = False) -> pd.DataFrame:
    pam = read_table(lake, "silver", "pam_municipio")
    dim = read_table(lake, "silver", "dim_municipio")
    clim = read_table(lake, "silver", "clima_diario")
    painel = read_table(lake, "gold", "painel_cafe_arabica")
    ar = pam[pam["especie"] == "arabica"]
    res: list[quality.CheckResult] = []
    res += quality.not_null(pam, "silver.pam_municipio", ["cod_ibge", "ano", "especie"])
    res += [quality.unique_key(pam, "silver.pam_municipio", ["cod_ibge", "especie", "ano"]),
            quality.valid_ibge(pam, "silver.pam_municipio"),
            quality.referential(pam, dim, "silver.pam_municipio", "cod_ibge"),
            quality.in_range(pam, "silver.pam_municipio", "area_colhida_ha", 0, None),
            quality.in_range(pam, "silver.pam_municipio", "quantidade_t", 0, None),
            quality.in_range(pam, "silver.pam_municipio", "rendimento_kg_ha", 0, 6000, severity="warn"),
            quality.in_range(pam[(pam.especie == "arabica")], "silver.pam_municipio[arabica]", "rendimento_kg_ha", 0, 6000),
            quality.consecutive_years(pam[pam.especie == "arabica"], "silver.pam_municipio[arabica]", "cod_ibge",
                                      expected=(config.ESPECIE_DESAGREGADA_DESDE, int(pam.ano.max()))),
            quality.yield_consistency(pam, "silver.pam_municipio"),
            quality.repeated_yield(ar, "silver.pam_municipio[arabica]", thr=0.25),
            quality.freshness(pam, "silver.pam_municipio", "ano", config.POWER_END_YEAR)]
    res += [quality.unique_key(dim, "silver.dim_municipio", ["cod_ibge"]), quality.valid_ibge(dim, "silver.dim_municipio"),
            *quality.not_null(dim, "silver.dim_municipio", ["lat", "lon", "cell_id"])]
    res += [quality.unique_key(clim, "silver.clima_diario", ["cell_id", "date"]),
            quality.in_range(clim, "silver.clima_diario", "t2m", -10, 45),
            quality.in_range(clim, "silver.clima_diario", "prec_mm", 0, 500),
            quality.in_range(clim, "silver.clima_diario", "t2m_min", -15, 40)]
    res += [quality.unique_key(painel, "gold.painel_cafe_arabica", ["cod_ibge", "ano"]),
            quality.min_rows(painel[painel.elegivel_modelo], "gold.painel_cafe_arabica[elegivel]", 500)]
    df = quality.to_frame(res)
    write_parquet_dataset(df, lake.gold / "dq_results", None, ["table", "check"])
    summ = quality.summarize(res)
    log.info("DQ: %s", summ)
    for r in res:
        if not r.passed:
            log.warning("DQ %-6s %s %s (%d/%d) %s", r.severity.upper(), r.table, r.check, r.n_failed, r.n_total, r.detail)
    if strict and summ["n_failed_error"]:
        raise RuntimeError(f"DQ reprovou: {summ}")
    return df


def run_all(lake: Lake | None = None, ufs=None, include_current_year=False, strict=True, skip_conab=False) -> dict:
    lake = lake or Lake()
    run_id = uuid.uuid4().hex[:8]
    summary: dict = {"run_id": run_id}
    for step, fn in (("ingest", lambda: run_ingest(lake, ufs, include_current_year, skip_conab)),
                     ("silver", lambda: run_silver(lake)), ("gold", lambda: run_gold(lake)),
                     ("dq", lambda: quality.summarize([quality.CheckResult(**r) for r in run_dq(lake, strict).to_dict("records")]))):
        t0 = ingest.now_utc()
        try:
            summary[step] = fn()
            lake.log_run(run_id, step, t0, "ok", summary[step])
        except Exception as e:  # noqa: BLE001
            lake.log_run(run_id, step, t0, "failed", {"error": str(e)})
            log.exception("etapa %s falhou", step)
            raise
    return summary
