"""Modelagem de previsão: baselines, regressão, XGBoost, validação temporal e intervalos conformes.

Princípios anti-vazamento:
  * validação *expanding window* por ano-alvo (treino: anos < T; teste: ano T);
  * features do ano T só usam informação disponível até a data de corte (clima até mar/T; preço médio de T−1;
    lags de rendimento de acordo com o cenário);
  * imputação/escala ajustadas apenas no treino (Pipeline);
  * nenhuma codificação de município baseada no alvo.
Cenários de informação:
  A — 'com histórico imediato': rendimento de T−1 conhecido (produtor/cooperativa com dados próprios).
  B — 'público estrito': PAM de T−1 ainda não publicado em 1º/mai/T; só lags ≥ 2.
"""
from __future__ import annotations

from dataclasses import dataclass

import numpy as np
import pandas as pd

CLIMA = ["chuva_floracao", "tmean_floracao", "chuva_granacao", "tmax_granacao", "chuva_12m_pre", "dias_frio_inv_prev"]
ESTATICAS = ["elev_m", "lat", "lon"]

SCENARIOS = {
    "A": {"lags": ["rend_lag1", "rend_lag2"], "regional": ["rend_reg_lag1", "rend_reg_lag2"], "area": "area_lag1", "naive": {"naive_lag1": "rend_lag1", "naive_lag2": "rend_lag2"},
          "mean": ["rend_lag1", "rend_lag2"]},
    "B": {"lags": ["rend_lag2", "rend_lag3"], "regional": ["rend_reg_lag2", "rend_reg_lag3"], "area": "area_lag2", "naive": {"naive_lag2": "rend_lag2", "naive_lag3": "rend_lag3"},
          "mean": ["rend_lag2", "rend_lag3"]},
}


# ---------------- métricas ----------------
def mae(y, p) -> float:
    return float(np.mean(np.abs(np.asarray(y) - np.asarray(p))))


def rmse(y, p) -> float:
    return float(np.sqrt(np.mean((np.asarray(y) - np.asarray(p)) ** 2)))


def smape(y, p) -> float:
    """sMAPE (%) = 100/n Σ 2|y−ŷ| / (|y|+|ŷ|); termos com denominador 0 contam 0."""
    y, p = np.asarray(y, float), np.asarray(p, float)
    den = np.abs(y) + np.abs(p)
    with np.errstate(divide="ignore", invalid="ignore"):
        r = np.where(den == 0, 0.0, 2 * np.abs(y - p) / den)
    return float(100 * np.mean(r))


def wape(y, p) -> float:
    """WAPE (%) = Σ|y−ŷ| / Σ|y| (erro ponderado pelo volume)."""
    y, p = np.asarray(y, float), np.asarray(p, float)
    return float(100 * np.abs(y - p).sum() / np.abs(y).sum())


# ---------------- dados ----------------
def prepare(panel: pd.DataFrame, scenario: str) -> pd.DataFrame:
    sc = SCENARIOS[scenario]
    d = panel[panel["elegivel_modelo"]].copy()
    need = sc["lags"] + [sc["area"]]
    d = d.dropna(subset=need + ["rendimento_kg_ha"])
    return d.reset_index(drop=True)


def feature_list(scenario: str, with_price: bool = True, with_regional: bool = True,
                 with_clima: bool = True) -> list[str]:
    sc = SCENARIOS[scenario]
    return (sc["lags"] + [sc["area"]] + (sc["regional"] if with_regional else []) + (CLIMA if with_clima else [])
            + ESTATICAS + (["preco_real_lag1"] if with_price else []))


def expanding_folds(years: list[int], first_test: int, last_test: int):
    ys = sorted(set(years))
    for t in range(first_test, last_test + 1):
        if t in ys and any(y < t for y in ys):
            yield [y for y in ys if y < t], t


def make_models(seed: int = 0):
    from sklearn.impute import SimpleImputer
    from sklearn.linear_model import RidgeCV
    from sklearn.pipeline import make_pipeline
    from sklearn.preprocessing import StandardScaler
    from xgboost import XGBRegressor
    ridge = make_pipeline(SimpleImputer(strategy="median"), StandardScaler(), RidgeCV(alphas=np.logspace(-2, 3, 20)))
    xgb = XGBRegressor(n_estimators=300, max_depth=3, learning_rate=0.05, subsample=0.8, colsample_bytree=0.8,
                       min_child_weight=5, reg_lambda=2.0, random_state=seed, n_jobs=2, tree_method="hist")
    return {"ridge": ridge, "xgboost": xgb}


@dataclass
class BacktestResult:
    scenario: str
    preds: pd.DataFrame            # cod_ibge, ano, y, area_ref, <modelo>...
    features: list[str]


def backtest(panel: pd.DataFrame, scenario: str = "A", first_test: int = 2017, last_test: int = 2025,
             with_price: bool = True, seed: int = 0, models: dict | None = None, with_regional: bool = True,
             with_clima: bool = True) -> BacktestResult:
    sc = SCENARIOS[scenario]
    d = prepare(panel, scenario)
    feats = feature_list(scenario, with_price, with_regional, with_clima)
    d = d.dropna(subset=[c for c in feats if c.startswith("rend_reg")]) if with_regional else d
    out = []
    for train_years, t in expanding_folds(d["ano"].unique().tolist(), first_test, last_test):
        tr, te = d[d["ano"].isin(train_years)], d[d["ano"] == t]
        if len(tr) < 100 or te.empty:
            continue
        res = te[["cod_ibge", "ano", "rendimento_kg_ha", sc["area"], "quantidade_t"]].rename(
            columns={"rendimento_kg_ha": "y", sc["area"]: "area_ref"}).copy()
        for name, col in sc["naive"].items():
            res[name] = te[col].values
        res["media_lags"] = te[sc["mean"]].mean(axis=1).values
        # baseline "média do município no treino" (nível, sem sazonalidade bienal): só com dados do treino
        mean_tr = tr.groupby("cod_ibge")["rendimento_kg_ha"].mean()
        res["media_municipio"] = te["cod_ibge"].map(mean_tr).fillna(tr["rendimento_kg_ha"].mean()).values
        for name, m in (models or make_models(seed)).items():
            from sklearn.base import clone
            mm = clone(m)
            mm.fit(tr[feats], tr["rendimento_kg_ha"])
            res[name] = mm.predict(te[feats])
        out.append(res)
    return BacktestResult(scenario, pd.concat(out, ignore_index=True), feats)


def score_table(res: BacktestResult, by_year: bool = False) -> pd.DataFrame:
    p = res.preds
    mods = [c for c in p.columns if c not in ("cod_ibge", "ano", "y", "area_ref", "quantidade_t")]
    rows = []
    groups = p.groupby("ano") if by_year else [("todos", p)]
    for g, d in groups:
        for m in mods:
            ok = d[m].notna()
            rows.append({"grupo": g, "modelo": m, "n": int(ok.sum()), "MAE": mae(d.y[ok], d[m][ok]),
                         "RMSE": rmse(d.y[ok], d[m][ok]), "sMAPE_%": smape(d.y[ok], d[m][ok])})
    return pd.DataFrame(rows)


def common_subset(res: BacktestResult) -> pd.DataFrame:
    """Linhas em que TODOS os modelos têm previsão (comparação justa)."""
    p = res.preds
    mods = [c for c in p.columns if c not in ("cod_ibge", "ano", "y", "area_ref", "quantidade_t")]
    return p.dropna(subset=mods)


# ---------------- intervalos (conformal split, resíduos de dobras anteriores) ----------------
def conformal_intervals(preds: pd.DataFrame, model: str, alpha: float = 0.2, min_cal: int = 100) -> pd.DataFrame:
    """Para cada ano de teste T, o quantil (1−α) dos |resíduos| de TODAS as dobras anteriores (< T)
    define o intervalo ŷ ± q. Cobertura marginal ≈ 1−α se resíduos forem permutáveis — o que NÃO é garantido em
    séries temporais com mudança de regime; reporte a cobertura empírica."""
    d = preds.dropna(subset=[model]).copy()
    d["res_abs"] = (d["y"] - d[model]).abs()
    lo, hi = [], []
    for i, r in d.iterrows():
        cal = d.loc[d["ano"] < r["ano"], "res_abs"]
        if len(cal) < min_cal:
            lo.append(np.nan); hi.append(np.nan); continue
        k = int(np.ceil((len(cal) + 1) * (1 - alpha)))
        q = np.sort(cal.values)[min(k, len(cal)) - 1]
        lo.append(r[model] - q); hi.append(r[model] + q)
    d["lo"], d["hi"] = lo, hi
    inside = ((d["y"] >= d["lo"]) & (d["y"] <= d["hi"])).astype(float)
    d["coberto"] = inside.where(d["lo"].notna(), np.nan)
    return d


def coverage(d: pd.DataFrame) -> dict:
    ok = d["lo"].notna()
    return {"n": int(ok.sum()), "cobertura": float(d.loc[ok, "coberto"].mean()),
            "largura_media": float((d.loc[ok, "hi"] - d.loc[ok, "lo"]).mean())}


# ---------------- agregado regional (produção) ----------------
def regional_production(res: BacktestResult, models: list[str]) -> pd.DataFrame:
    """Produção prevista (t) = Σ rendimento_prev × área_ref / 1000 vs. observada, por ano (municípios elegíveis)."""
    p = res.preds.copy()
    rows = []
    for ano, d in p.groupby("ano"):
        obs = d["quantidade_t"].sum()
        row = {"ano": ano, "n_municipios": len(d), "obs_t": obs}
        for m in models:
            ok = d[m].notna()
            row[m] = (d.loc[ok, m] * d.loc[ok, "area_ref"]).sum() / 1000
            row[f"{m}_erro_%"] = 100 * (row[m] - d.loc[ok, "quantidade_t"].sum()) / d.loc[ok, "quantidade_t"].sum()
        rows.append(row)
    return pd.DataFrame(rows)
