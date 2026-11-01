import numpy as np
import pandas as pd
import pytest

from coffeebdi import modeling as M


def test_metrics_known_values():
    y, p = np.array([100.0, 200.0]), np.array([110.0, 180.0])
    assert M.mae(y, p) == 15 and M.rmse(y, p) == pytest.approx(np.sqrt(250))
    assert M.smape(y, p) == pytest.approx(100 * np.mean([2 * 10 / 210, 2 * 20 / 380]))
    assert M.smape([0.0], [0.0]) == 0.0
    assert M.wape(y, p) == pytest.approx(100 * 30 / 300)


def test_expanding_folds_respect_time():
    folds = list(M.expanding_folds(list(range(2014, 2026)), 2017, 2025))
    assert [t for _, t in folds] == list(range(2017, 2026))
    assert all(max(tr) < t for tr, t in folds)


def _panel(n_mun=60, years=range(2012, 2026), seed=0):
    rng = np.random.default_rng(seed)
    rows = []
    for m in range(n_mun):
        base = rng.uniform(1000, 2000)
        for y in years:
            rows.append({"cod_ibge": f"M{m}", "ano": y, "rendimento_kg_ha": base * (1.15 if y % 2 else 0.85) + rng.normal(0, 40),
                         "area_colhida_ha": 500.0, "quantidade_t": 500.0, "lat": -22.0, "lon": -47.0, "elev_m": 600.0,
                         "elegivel_modelo": True,
                         **{c: rng.normal() for c in M.CLIMA}, "preco_real_lag1": 1000.0 + y})
    d = pd.DataFrame(rows).sort_values(["cod_ibge", "ano"])
    g = d.groupby("cod_ibge")
    for k in (1, 2, 3):
        d[f"rend_lag{k}"] = g["rendimento_kg_ha"].shift(k)
    d["area_lag1"] = g["area_colhida_ha"].shift(1)
    d["area_lag2"] = g["area_colhida_ha"].shift(2)
    reg = d.groupby("ano")["rendimento_kg_ha"].mean()
    for k in (1, 2, 3):
        d[f"rend_reg_lag{k}"] = (d["ano"] - k).map(reg)
    return d.reset_index(drop=True)


def test_backtest_no_target_leakage():
    """Alterar o alvo do ano T não pode mudar as previsões de nenhum ano ≤ T (features só usam o passado)."""
    p = _panel()
    r1 = M.backtest(p, "A", 2018, 2022, seed=1)
    p2 = p.copy()
    p2.loc[p2.ano == 2020, "rendimento_kg_ha"] += 5000.0
    r2 = M.backtest(p2.assign(), "A", 2018, 2022, seed=1)
    cols = ["ridge", "xgboost", "media_lags", "media_municipio", "naive_lag1"]
    # lags de 2021+ usam o rendimento de 2020 (esperado) — comparamos só 2018–2020
    a = r1.preds[r1.preds.ano <= 2020].sort_values(["ano", "cod_ibge"]).reset_index(drop=True)
    b = r2.preds[r2.preds.ano <= 2020].sort_values(["ano", "cod_ibge"]).reset_index(drop=True)
    # p2 foi alterado também em rend_lag* ? não: lags foram pré-computados -> rendimento alterado só afeta y de 2020
    np.testing.assert_allclose(a.loc[a.ano < 2020, cols].values, b.loc[b.ano < 2020, cols].values)
    np.testing.assert_allclose(a.loc[a.ano == 2020, cols].values, b.loc[b.ano == 2020, cols].values)
    assert (b.loc[b.ano == 2020, "y"].values - a.loc[a.ano == 2020, "y"].values == 5000).all()


def test_biennial_signal_captured_by_lag2_baseline():
    p = _panel()
    r = M.backtest(p, "A", 2018, 2025)
    t = M.score_table(M.BacktestResult("A", M.common_subset(r), r.features)).set_index("modelo")
    assert t.loc["naive_lag2", "MAE"] < t.loc["naive_lag1", "MAE"]       # série com alternância perfeita
    assert t.loc["xgboost", "MAE"] < 0.5 * t.loc["naive_lag1", "MAE"]


def test_scenario_b_uses_no_lag1():
    assert "rend_lag1" not in M.feature_list("B") and "area_lag1" not in M.feature_list("B")
    assert "rend_reg_lag1" not in M.feature_list("B")


def test_conformal_coverage_on_iid_noise():
    rng = np.random.default_rng(0)
    n = 3000
    d = pd.DataFrame({"ano": np.repeat(np.arange(2017, 2027), n // 10), "y": rng.normal(0, 1, n), "m": 0.0})
    ci = M.conformal_intervals(d, "m", alpha=0.2, min_cal=100)
    cov = M.coverage(ci)
    assert 0.76 < cov["cobertura"] < 0.84 and cov["n"] > 2000
    assert ci.loc[ci.ano == 2017, "lo"].isna().all()                     # sem calibração anterior -> sem intervalo


def test_regional_production_sums():
    res = M.BacktestResult("A", pd.DataFrame({"ano": [2020, 2020], "y": [1000, 2000], "area_ref": [100.0, 200.0],
                                              "quantidade_t": [100.0, 400.0], "m": [1000.0, 2000.0]}), [])
    out = M.regional_production(res, ["m"])
    assert out.loc[0, "obs_t"] == 500 and out.loc[0, "m"] == pytest.approx((1000 * 100 + 2000 * 200) / 1000)
