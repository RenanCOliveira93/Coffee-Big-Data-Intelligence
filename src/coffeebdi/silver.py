"""Bronze -> Silver: parsing, tipagem, normalização de códigos e escrita Parquet particionada.

Silver é *reconstruível*: cada função lê a bronze inteira e regrava a tabela de forma determinística
(ordenada), então reexecutar não altera o resultado (ELT idempotente).
"""
from __future__ import annotations

import io
import json
import shutil
from pathlib import Path

import duckdb
import numpy as np
import pandas as pd

from . import config
from .ibge import is_valid_municipio, normalize_municipio
from .lake import Lake
from .logging_utils import get_logger

log = get_logger("silver")


# ---------------- util: escrita Parquet ----------------
def write_parquet_dataset(df: pd.DataFrame, dest: Path, partition_by: list[str] | None = None,
                          order_by: list[str] | None = None) -> int:
    """Reescreve `dest` por completo (grava em diretório temporário e troca). Retorna nº de linhas."""
    if order_by:
        df = df.sort_values(order_by, kind="mergesort").reset_index(drop=True)
    tmp = dest.with_name(dest.name + ".__tmp")
    if tmp.exists():
        shutil.rmtree(tmp)
    tmp.parent.mkdir(parents=True, exist_ok=True)
    con = duckdb.connect()
    con.register("df", df)
    if partition_by:
        cols = ", ".join(partition_by)
        con.execute(f"COPY df TO '{tmp}' (FORMAT PARQUET, PARTITION_BY ({cols}), COMPRESSION ZSTD)")
    else:
        tmp.mkdir(parents=True)
        con.execute(f"COPY df TO '{tmp / 'part-0.parquet'}' (FORMAT PARQUET, COMPRESSION ZSTD)")
    con.close()
    if dest.exists():
        shutil.rmtree(dest)
    tmp.rename(dest)
    return len(df)


def read_table(lake: Lake, layer: str, name: str) -> pd.DataFrame:
    base = (lake.silver if layer == "silver" else lake.gold) / name
    con = duckdb.connect()
    df = con.execute(f"SELECT * FROM read_parquet('{base}/**/*.parquet', hive_partitioning=true)").df()
    con.close()
    return df


# ---------------- IBGE / PAM ----------------
def flatten_sidra(payload: list[dict]) -> pd.DataFrame:
    """JSON do SIDRA -> linhas (cod_local, nome_local, ano, var_id, raw)."""
    rows = []
    for var in payload:
        vid = int(var["id"])
        for res in var["resultados"]:
            for s in res["series"]:
                loc = s["localidade"]
                for year, val in s["serie"].items():
                    rows.append((str(loc["id"]), loc["nome"], int(year), vid, val))
    return pd.DataFrame(rows, columns=["cod_local", "nome_local", "ano", "var_id", "raw"])


def sidra_value(raw: str) -> tuple[float, str]:
    """Converte string SIDRA em (valor, qualidade). '-' = zero absoluto; '0' = zero por arredondamento;
    '..' não se aplica; '...' indisponível; 'X' suprimido (sigilo)."""
    if raw in config.SIDRA_SPECIAL:
        q = config.SIDRA_SPECIAL[raw]
        return (0.0 if q in ("zero", "zero_arredondado") else np.nan), q
    try:
        return float(raw), "ok"
    except (TypeError, ValueError):
        return np.nan, "invalido"


def _pivot_pam(long: pd.DataFrame) -> pd.DataFrame:
    vals = long["raw"].map(sidra_value)
    long = long.assign(valor=[v for v, _ in vals], q=[q for _, q in vals])
    long["var"] = long["var_id"].map(config.PAM_VARS)
    idx = ["cod_local", "nome_local", "ano", "especie"]
    # pivot (não pivot_table): preserva linhas cujos valores são todos NaN ("..."/"X"), que seriam descartadas
    wide = long.pivot(index=idx, columns="var", values="valor")
    qual = long.pivot(index=idx, columns="var", values="q").add_suffix("_q")
    out = wide.join(qual).reset_index()
    out.columns.name = None
    for v in config.PAM_VARS.values():       # garante todas as colunas
        if v not in out:
            out[v] = np.nan
            out[f"{v}_q"] = "indisponivel"
    return out


def build_pam_municipio(lake: Lake, write: bool = True) -> tuple[pd.DataFrame, pd.DataFrame]:
    """PAM municipal. Retorna (silver, rejeitados). Rejeitados = código IBGE inválido."""
    frames = []
    for key in lake.keys("ibge_pam", "pam_municipio"):
        # key = uf35_arabica_2023
        _, esp, _ = key.split("_")
        long = flatten_sidra(lake.read_json("ibge_pam", "pam_municipio", key))
        long["especie"] = esp
        frames.append(long)
    long = pd.concat(frames, ignore_index=True)
    out = _pivot_pam(long)
    # normalização/validação de códigos
    out["cod_ibge"] = out["cod_local"].map(lambda c: normalize_municipio(c) if is_valid_municipio(c) else None)
    rejects = out[out["cod_ibge"].isna()].assign(motivo="codigo_ibge_invalido")
    out = out[out["cod_ibge"].notna()].copy()
    out["uf_codigo"] = out["cod_ibge"].str[:2].astype(int)
    out["uf"] = out["uf_codigo"].map(config.UF_SIGLA)
    out["municipio"] = out["nome_local"].str.replace(r"\s-\s[A-Z]{2}$", "", regex=True)
    out["ano"] = out["ano"].astype("int32")
    out["tem_producao"] = (out["quantidade_t"].fillna(0) > 0) & (out["area_colhida_ha"].fillna(0) > 0)
    out["date_key"] = pd.to_datetime(out["ano"].astype(str) + "-01-01")
    cols = ["cod_ibge", "municipio", "uf", "uf_codigo", "ano", "date_key", "especie", *config.PAM_VARS.values(),
            *[f"{v}_q" for v in config.PAM_VARS.values()], "tem_producao"]
    out = out[cols]
    if write:
        n = write_parquet_dataset(out, lake.silver / "pam_municipio", ["especie", "ano"], ["cod_ibge", "especie", "ano"])
        if len(rejects):
            write_parquet_dataset(rejects.drop(columns=["date_key"], errors="ignore"), lake.silver / "_rejects_pam_municipio")
        log.info("silver.pam_municipio: %d linhas, %d rejeitadas", n, len(rejects))
    return out, rejects


def build_pam_uf(lake: Lake, write: bool = True) -> pd.DataFrame:
    frames = []
    for key in lake.keys("ibge_pam", "pam_uf"):
        _, esp, _ = key.split("_")
        long = flatten_sidra(lake.read_json("ibge_pam", "pam_uf", key))
        long["especie"] = esp
        frames.append(long)
    out = _pivot_pam(pd.concat(frames, ignore_index=True))
    out["uf_codigo"] = out["cod_local"].astype(int)
    out["uf"] = out["uf_codigo"].map(config.UF_SIGLA)
    out["ano"] = out["ano"].astype("int32")
    out = out.drop(columns=["cod_local", "nome_local"])
    out = out[["uf_codigo", "uf", "ano", "especie", *config.PAM_VARS.values(), *[f"{v}_q" for v in config.PAM_VARS.values()]]]
    if write:
        write_parquet_dataset(out, lake.silver / "pam_uf", ["especie"], ["uf_codigo", "especie", "ano"])
        log.info("silver.pam_uf: %d linhas", len(out))
    return out


# ---------------- Território ----------------
def build_dim_municipio(lake: Lake, write: bool = True) -> pd.DataFrame:
    from shapely.geometry import shape
    from .power import cell_id_for, cell_center

    rows = []
    for key in lake.keys("ibge_territorio", "municipios"):
        uf = int(key[2:])
        muni = lake.read_json("ibge_territorio", "municipios", key)
        mesh = lake.read_json("ibge_territorio", "malha_municipios", key)
        cent = {}
        for f in mesh["features"]:
            c = shape(f["geometry"]).centroid
            cent[str(f["properties"]["codarea"])] = (c.y, c.x)
        censo = flatten_sidra(lake.read_json("ibge_territorio", "censo2022", key))
        censo = censo.assign(v=pd.to_numeric(censo["raw"], errors="coerce"),
                             var=censo["var_id"].map(config.CENSO_VARS)).pivot(index="cod_local", columns="var", values="v")
        for m in muni:
            code = str(m["id"])
            lat, lon = cent.get(code, (np.nan, np.nan))
            mic, mes = m.get("microrregiao") or {}, (m.get("microrregiao") or {}).get("mesorregiao") or {}
            imd = m.get("regiao-imediata") or {}
            rows.append({
                "cod_ibge": normalize_municipio(code), "municipio": m["nome"], "uf_codigo": uf,
                "uf": config.UF_SIGLA.get(uf), "microrregiao": mic.get("nome"), "mesorregiao": mes.get("nome"),
                "regiao_imediata": imd.get("nome"), "lat": lat, "lon": lon,
                "area_km2": censo["area_km2"].get(code, np.nan) if "area_km2" in censo else np.nan,
                "pop_2022": censo["pop_2022"].get(code, np.nan) if "pop_2022" in censo else np.nan,
                "densidade_hab_km2": censo["densidade_hab_km2"].get(code, np.nan) if "densidade_hab_km2" in censo else np.nan,
            })
    dim = pd.DataFrame(rows)
    dim["cell_id"] = [cell_id_for(la, lo) if la == la else None for la, lo in zip(dim["lat"], dim["lon"])]
    dim["cell_lat"] = [cell_center(la, lo)[0] if la == la else np.nan for la, lo in zip(dim["lat"], dim["lon"])]
    dim["cell_lon"] = [cell_center(la, lo)[1] if la == la else np.nan for la, lo in zip(dim["lat"], dim["lon"])]
    if write:
        write_parquet_dataset(dim, lake.silver / "dim_municipio", None, ["cod_ibge"])
        log.info("silver.dim_municipio: %d linhas", len(dim))
    return dim


# ---------------- Clima ----------------
def parse_power(payload: dict, cell_id: str) -> tuple[pd.DataFrame, float]:
    """JSON do POWER -> DataFrame diário. -999 = faltante -> NaN. Retorna (df, elevação m da célula)."""
    par = payload["properties"]["parameter"]
    elev = float(payload["geometry"]["coordinates"][2])
    days = sorted(next(iter(par.values())).keys())
    df = pd.DataFrame({"date": pd.to_datetime(days, format="%Y%m%d")})
    for src, dst in (("T2M", "t2m"), ("T2M_MAX", "t2m_max"), ("T2M_MIN", "t2m_min"), ("PRECTOTCORR", "prec_mm")):
        arr = np.array([par[src][d] for d in days], dtype="float64")
        arr[arr <= -998] = np.nan
        df[dst] = arr.astype("float32")
    df.insert(0, "cell_id", cell_id)
    return df, elev


def build_clima(lake: Lake, write: bool = True) -> tuple[pd.DataFrame, pd.DataFrame]:
    frames, cells = [], {}
    for key in lake.keys("nasa_power", "daily"):
        cell_id = key.rsplit("_", 2)[0]   # cell_id contém "_"
        payload = lake.read_json("nasa_power", "daily", key)
        df, elev = parse_power(payload, cell_id)
        frames.append(df)
        cells[cell_id] = elev
    clim = pd.concat(frames, ignore_index=True).drop_duplicates(["cell_id", "date"], keep="last")
    clim["ano"] = clim["date"].dt.year.astype("int32")
    clim["mes"] = clim["date"].dt.month.astype("int8")
    cell_df = pd.DataFrame({"cell_id": list(cells), "elev_m": list(cells.values())})
    if write:
        n = write_parquet_dataset(clim, lake.silver / "clima_diario", ["ano"], ["cell_id", "date"])
        write_parquet_dataset(cell_df, lake.silver / "clima_celula", None, ["cell_id"])
        log.info("silver.clima_diario: %d linhas, %d células", n, len(cells))
    return clim, cell_df


# ---------------- Preços / macro ----------------
def parse_pink_sheet(xlsx_bytes: bytes) -> pd.DataFrame:
    d = pd.read_excel(io.BytesIO(xlsx_bytes), sheet_name="Monthly Prices", header=None)
    hdr = d.iloc[4].tolist()
    cols = {i: ("cafe_arabica_usd_kg" if "Arabica" in h else "cafe_robusta_usd_kg")
            for i, h in enumerate(hdr) if isinstance(h, str) and h.startswith("Coffee")}
    body = d.iloc[6:, [0, *cols]].copy()
    body.columns = ["periodo", *cols.values()]
    body = body[body["periodo"].astype(str).str.match(r"^\d{4}M\d{2}$")]
    body["mes_ref"] = pd.to_datetime(body["periodo"].str.replace("M", "-") + "-01")
    for c in cols.values():
        body[c] = pd.to_numeric(body[c], errors="coerce")
    return body.drop(columns="periodo").reset_index(drop=True)


def build_precos_macro(lake: Lake, write: bool = True) -> dict[str, pd.DataFrame]:
    pink = parse_pink_sheet(lake.read("worldbank", "pink_sheet", "monthly"))
    fx = []
    for k in lake.keys("bcb", "fx_diario"):
        fx.append(pd.DataFrame(lake.read_json("bcb", "fx_diario", k)))
    fx = pd.concat(fx, ignore_index=True)
    fx["data"] = pd.to_datetime(fx["data"], format="%d/%m/%Y")
    fx["brl_usd"] = pd.to_numeric(fx["valor"])
    fxm = (fx.assign(mes_ref=fx["data"].dt.to_period("M").dt.to_timestamp())
             .groupby("mes_ref", as_index=False).agg(brl_usd=("brl_usd", "mean"), n_dias=("brl_usd", "size")))
    ip = pd.DataFrame(lake.read_json("bcb", "ipca_mensal", "all"))
    ip["mes_ref"] = pd.to_datetime(ip["data"], format="%d/%m/%Y").dt.to_period("M").dt.to_timestamp()
    ip["ipca_var_pct"] = pd.to_numeric(ip["valor"])
    ip = ip.sort_values("mes_ref")[["mes_ref", "ipca_var_pct"]].drop_duplicates("mes_ref", keep="last").reset_index(drop=True)
    ip["ipca_indice"] = 100 * (1 + ip["ipca_var_pct"] / 100).cumprod()   # base arbitrária: jul/1994 = 100*(1+var)
    out = {"preco_cafe_mensal": pink, "cambio_mensal": fxm, "ipca_mensal": ip}
    if write:
        for name, df in out.items():
            write_parquet_dataset(df, lake.silver / name, None, ["mes_ref"])
        log.info("silver preços/macro: %s", {k: len(v) for k, v in out.items()})
    return out


# ---------------- CONAB ----------------
def parse_conab(xls_bytes: bytes, especie: str) -> pd.DataFrame:
    """Planilha CONAB (4 abas: área em produção [ha], área em formação [ha], produtividade [sc/ha],
    produção [mil sacas beneficiadas]) -> formato longo por UF/safra. Linhas de região/sub-região ignoradas."""
    ufs = set(config.UF_SIGLA.values())
    sheets = {"Área em produção": ("area_producao_ha", "ha"), "Área em formação": ("area_formacao_ha", "ha"),
              "Produtividade": ("produtividade_sc_ha", "sc/ha"), "Produção": ("producao_mil_sacas", "mil sacas")}
    out = []
    for sh, (ind, unit) in sheets.items():
        d = pd.read_excel(io.BytesIO(xls_bytes), sheet_name=sh, header=None, engine="xlrd")
        hdr = d.iloc[5].tolist()
        for _, r in d.iloc[6:].iterrows():
            lab = str(r.iloc[0]).strip()
            if lab not in ufs and lab != "BRASIL":
                continue
            for j in range(1, len(hdr)):
                h = str(hdr[j])
                if not h[:4].isdigit():
                    continue
                v = pd.to_numeric(r.iloc[j], errors="coerce")
                out.append({"uf": lab, "safra": int(h[:4]), "estimativa": "(" in h, "especie": especie,
                            "indicador": ind, "unidade": unit, "valor": v})
    return pd.DataFrame(out)


def build_conab(lake: Lake, write: bool = True) -> pd.DataFrame:
    df = pd.concat([parse_conab(lake.read("conab", "serie_historica_cafe", e), e) for e in config.CONAB_FILES],
                   ignore_index=True)
    df["especie"] = df["especie"].replace({"conilon": "canephora"})
    df = df.dropna(subset=["valor"])
    if write:
        write_parquet_dataset(df, lake.silver / "conab_uf", ["especie"], ["uf", "especie", "indicador", "safra"])
        log.info("silver.conab_uf: %d linhas", len(df))
    return df
