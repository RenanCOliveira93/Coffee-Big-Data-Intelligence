import numpy as np
import pandas as pd

from coffeebdi import quality as q


def test_not_null_unique_range():
    df = pd.DataFrame({"k": [1, 1, 2], "v": [1.0, np.nan, 5.0]})
    assert not q.unique_key(df, "t", ["k"]).passed
    assert q.not_null(df, "t", ["v"])[0].n_failed == 1
    assert q.in_range(df, "t", "v", 0, 4).n_failed == 1
    assert q.in_range(df, "t", "v", 0, 10).passed


def test_valid_ibge_and_referential():
    f = pd.DataFrame({"cod_ibge": ["3538808", "3538807"]})
    assert q.valid_ibge(f, "t").n_failed == 1
    dim = pd.DataFrame({"cod_ibge": ["3538808"]})
    assert q.referential(f, dim, "t", "cod_ibge").n_failed == 1


def test_consecutive_years_detects_hole():
    df = pd.DataFrame({"k": ["a", "a", "a", "b", "b"], "ano": [2012, 2013, 2014, 2012, 2014]})
    r = q.consecutive_years(df, "t", "k")
    assert r.n_failed == 1 and r.n_total == 2


def test_yield_consistency_and_repeated():
    df = pd.DataFrame({"cod_ibge": ["1"] * 4, "ano": [2020, 2021, 2022, 2023], "area_colhida_ha": [100.0] * 4,
                       "quantidade_t": [150.0, 150.0, 150.0, 300.0], "rendimento_kg_ha": [1500, 1500, 1500, 1500]})
    assert q.yield_consistency(df, "t", 0.02).n_failed == 1          # 300 t/100 ha = 3000 ≠ 1500
    r = q.repeated_yield(df, "t", thr=0.5)
    assert not r.passed and "100.0%" in r.detail


def test_freshness_summary():
    df = pd.DataFrame({"ano": [2024, 2025]})
    res = [q.freshness(df, "t", "ano", 2025), q.freshness(df, "t", "ano", 2026, severity="error")]
    s = q.summarize(res)
    assert s == {"n_checks": 2, "n_failed_error": 1, "n_failed_warn": 0}
