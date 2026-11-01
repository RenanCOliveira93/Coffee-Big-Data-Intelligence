"""Testes de features climáticas: janelas corretas e ausência de vazamento (nada depois de 31/mar/t)."""
import duckdb
import numpy as np
import pandas as pd
import pytest

from coffeebdi import gold


def _daily(spikes=None, years=(2018, 2019, 2020)):
    d = pd.DataFrame({"date": pd.date_range(f"{years[0]}-01-01", f"{years[-1]}-12-31")})
    d["cell_id"] = "c1"
    d["prec_mm"] = np.float32(1.0)
    d["t2m"] = np.float32(20.0)
    d["t2m_max"] = np.float32(28.0)
    d["t2m_min"] = np.float32(12.0)
    for (a, b), (col, val) in (spikes or {}).items():
        m = (d["date"] >= a) & (d["date"] <= b)
        d.loc[m, col] = np.float32(val)
    d["ano"] = d["date"].dt.year
    d["mes"] = d["date"].dt.month
    return d


def _features(d):
    con = duckdb.connect()
    con.register("clima_diario", d)
    return gold.build_clima_features(con).set_index("ano")


def test_windows_with_constant_rain():
    f = _features(_daily())
    r = f.loc[2019]
    assert r["chuva_floracao"] == pytest.approx(91.0)      # set(30)+out(31)+nov(30) × 1 mm
    assert r["chuva_granacao"] == pytest.approx(121.0)     # dez(31)+jan(31)+fev(28)+mar(31) de 2018/19 -> 31+31+28+31
    assert r["chuva_12m_pre"] == pytest.approx(365.0)
    assert r["tmax_granacao"] == pytest.approx(28.0)
    assert r["dias_frio_inv_prev"] == 0


def test_no_leakage_after_march_of_target_year():
    base = _features(_daily())
    # chuva forte em mai–dez/2019: não pode alterar NENHUMA feature de 2019
    leak = _features(_daily({("2019-04-01", "2019-12-31"): ("prec_mm", 500.0)}))
    cols = ["chuva_floracao", "tmean_floracao", "chuva_granacao", "tmax_granacao", "chuva_12m_pre", "dias_frio_inv_prev"]
    pd.testing.assert_series_equal(base.loc[2019, cols], leak.loc[2019, cols])
    # …mas set–nov/2018 (florada do ano-colheita 2019) deve alterar chuva_floracao de 2019
    flor = _features(_daily({("2018-10-01", "2018-10-31"): ("prec_mm", 100.0)}))
    assert flor.loc[2019, "chuva_floracao"] > base.loc[2019, "chuva_floracao"] + 2000
    assert flor.loc[2020, "chuva_floracao"] == base.loc[2020, "chuva_floracao"]


def test_frio_counts_winter_before_harvest():
    f = _features(_daily({("2018-07-01", "2018-07-10"): ("t2m_min", 2.0)}))
    assert f.loc[2019, "dias_frio_inv_prev"] == 10


def test_incomplete_window_is_null():
    f = _features(_daily())
    assert pd.isna(f.loc[2018, "chuva_floracao"])          # set–nov/2017 ausentes
    assert f.loc[2019, "ultima_data_usada"] == pd.Timestamp("2019-03-31")
    assert f.loc[2019, "data_corte_previsao"] == pd.Timestamp("2019-05-01")
    assert (f["ultima_data_usada"] < f["data_corte_previsao"]).all()
