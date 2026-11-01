import json

import numpy as np
import pandas as pd
import pytest

from coffeebdi import config, silver


def test_sidra_value_special_codes():
    assert silver.sidra_value("123") == (123.0, "ok")
    assert silver.sidra_value("-") == (0.0, "zero")
    assert silver.sidra_value("0") == (0.0, "zero_arredondado")
    for raw, q in (("..", "nao_se_aplica"), ("...", "indisponivel"), ("X", "suprimido")):
        v, qq = silver.sidra_value(raw)
        assert np.isnan(v) and qq == q
    assert silver.sidra_value("abc")[1] == "invalido"


def test_flatten_and_pivot_real_sample(sidra_sample):
    long = silver.flatten_sidra(sidra_sample)
    assert set(long["cod_local"]) == {"3538808", "3537008"}
    long["especie"] = "arabica"
    w = silver._pivot_pam(long)
    assert set(config.PAM_VARS.values()) <= set(w.columns)
    pedre = w[w.cod_local == "3537008"].iloc[0]
    assert pedre["area_colhida_ha"] > 0 and pedre["quantidade_t"] > 0


def test_pivot_keeps_all_nan_rows():
    """Regressão: pivot_table descartava linhas com todos os valores '...' (indisponíveis)."""
    payload = [{"id": str(v), "resultados": [{"series": [
        {"localidade": {"id": "3538808", "nome": "Piraju - SP"}, "serie": {"2020": "..."}}]}]} for v in config.PAM_VARS]
    long = silver.flatten_sidra(payload)
    long["especie"] = "arabica"
    w = silver._pivot_pam(long)
    assert len(w) == 1 and w["quantidade_t_q"].iloc[0] == "indisponivel"


def test_parse_power_missing_and_elevation(power_sample):
    df, elev = silver.parse_power(power_sample, "-40_-77")
    assert len(df) == 31 and elev > 0
    assert df["prec_mm"].dtype == np.float32 and (df["prec_mm"].dropna() >= 0).all()
    bad = json.loads(json.dumps(power_sample))
    first = next(iter(bad["properties"]["parameter"]["T2M"]))
    bad["properties"]["parameter"]["T2M"][first] = -999
    df2, _ = silver.parse_power(bad, "x")
    assert df2["t2m"].isna().sum() == 1


def test_cell_id_with_underscore_roundtrip():
    key = "-40_-76_20000101_20091231"
    assert key.rsplit("_", 2)[0] == "-40_-76"


def test_write_parquet_dataset_is_idempotent(tmp_path):
    df = pd.DataFrame({"a": [3, 1, 2], "ano": [2020, 2021, 2020]})
    dest = tmp_path / "t"
    silver.write_parquet_dataset(df, dest, ["ano"], ["a"])
    first = sorted(p.relative_to(dest).as_posix() for p in dest.rglob("*.parquet"))
    silver.write_parquet_dataset(df, dest, ["ano"], ["a"])
    assert first == sorted(p.relative_to(dest).as_posix() for p in dest.rglob("*.parquet"))
    import duckdb
    got = duckdb.sql(f"select a, ano from read_parquet('{dest}/**/*.parquet', hive_partitioning=true) order by a").df()
    assert got["a"].tolist() == [1, 2, 3]
    # partição obsoleta é removida na reescrita
    silver.write_parquet_dataset(df[df.ano == 2020], dest, ["ano"], ["a"])
    assert not (dest / "ano=2021").exists()


def test_parse_pink_sheet_structure():
    # planilha mínima no layout do Pink Sheet (cabeçalho na linha 4, unidades na 5, dados desde a 6)
    import io
    rows = [[None] * 3 for _ in range(4)]
    rows += [[None, "Coffee, Arabica", "Coffee, Robusta"], [None, "($/kg)", "($/kg)"],
             ["1960M01", 0.94, 0.7], ["1960M02", "..", 0.69]]
    buf = io.BytesIO()
    with pd.ExcelWriter(buf, engine="openpyxl") as w:
        pd.DataFrame(rows).to_excel(w, sheet_name="Monthly Prices", header=False, index=False)
    out = silver.parse_pink_sheet(buf.getvalue())
    assert list(out["mes_ref"]) == [pd.Timestamp("1960-01-01"), pd.Timestamp("1960-02-01")]
    assert np.isnan(out.loc[1, "cafe_arabica_usd_kg"]) and out.loc[0, "cafe_robusta_usd_kg"] == 0.7
