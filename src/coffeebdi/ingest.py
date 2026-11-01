"""Ingestão incremental e idempotente para a camada bronze."""
from __future__ import annotations

import json
from concurrent.futures import ThreadPoolExecutor
from datetime import date, datetime, timezone
from collections import Counter

from . import config, sources
from .lake import Lake
from .logging_utils import get_logger

log = get_logger("ingest")


def _run_tasks(tasks, workers: int = 4) -> Counter:
    """tasks: lista de callables que devolvem status str. Executa em paralelo e conta resultados."""
    c: Counter = Counter()
    with ThreadPoolExecutor(max_workers=workers) as ex:
        for st in ex.map(lambda f: f(), tasks):
            c[st] += 1
    return c


def _n_records_sidra(payload: bytes) -> int:
    try:
        d = json.loads(payload)
        return sum(len(v["resultados"][0]["series"]) for v in d)
    except Exception:  # noqa: BLE001
        return -1


def ingest_pam(lake: Lake, ufs: list[int] | None = None, since: int | None = None,
               refresh_recent: int | None = None, include_uf_level: bool = True) -> Counter:
    """PAM/SIDRA 1613 para café. Chave = (nível, espécie, ano). Anos já ingeridos são pulados,
    exceto os `refresh_recent` mais recentes (o IBGE revisa dados recentes)."""
    ufs = ufs or config.UFS
    since = since or config.PAM_START_YEAR
    refresh_recent = config.PAM_REFRESH_RECENT_YEARS if refresh_recent is None else refresh_recent
    years = [y for y in sources.sidra_available_years() if y >= since]
    last_year = max(years)
    log.info("PAM: anos disponíveis %d–%d", years[0], last_year)

    def one(dataset: str, key: str, locality: str, especie: str, year: int):
        def f():
            recent = year > last_year - refresh_recent
            if not recent and lake.is_fresh("ibge_pam", dataset, key):
                return "cached"
            payload = sources.sidra_pam(locality, especie, year)
            return lake.put("ibge_pam", dataset, key, payload,
                            {"locality": locality, "especie": especie, "ano": year}, _n_records_sidra(payload))
        return f

    tasks = []
    for year in years:
        especies = ["total"] + (["arabica", "canephora"] if year >= config.ESPECIE_DESAGREGADA_DESDE else [])
        for esp in especies:
            for uf in ufs:
                tasks.append(one("pam_municipio", f"uf{uf}_{esp}_{year}", f"N6[N3[{uf}]]", esp, year))
            if include_uf_level:
                tasks.append(one("pam_uf", f"N3all_{esp}_{year}", "N3[all]", esp, year))
    res = _run_tasks(tasks)
    log.info("PAM ingest: %s", dict(res))
    return res


def ingest_territory(lake: Lake, ufs: list[int] | None = None) -> Counter:
    """Municípios (localidades), malha (centróides) e Censo 2022. Dados estáveis: não reingere se já existem."""
    ufs = ufs or config.UFS
    c: Counter = Counter()
    for uf in ufs:
        for ds, fn, ext in (("municipios", sources.ibge_municipios, "json.gz"),
                            ("malha_municipios", sources.ibge_malha_uf, "json.gz"),
                            ("censo2022", sources.sidra_censo, "json.gz")):
            key = f"uf{uf}"
            if lake.is_fresh("ibge_territorio", ds, key):
                c["cached"] += 1
                continue
            c[lake.put("ibge_territorio", ds, key, fn(uf), {"uf": uf}, ext=ext)] += 1
    log.info("Território ingest: %s", dict(c))
    return c


def ingest_power(lake: Lake, cells: list[tuple[str, float, float]], start_year: int | None = None,
                 end_year: int | None = None, include_current_year: bool = False, workers: int = 4) -> Counter:
    """NASA POWER diário por célula da grade. Blocos fechados (2000–2009, 2010–2019, 2020–end) são imutáveis;
    com `include_current_year`, um bloco aberto do ano seguinte a `end_year` até ~10 dias atrás é
    reconsultado se tiver mais de 7 dias (latência do POWER)."""
    start_year = start_year or config.POWER_START_YEAR
    end_year = end_year or config.POWER_END_YEAR
    edges = sorted({start_year, *[y for y in (2010, 2020) if start_year < y <= end_year]})
    blocks = []
    for i, a in enumerate(edges):
        b = (edges[i + 1] - 1) if i + 1 < len(edges) else end_year
        blocks.append((f"{a}0101", f"{b}1231"))

    def task(cell_id, lat, lon, s, e, max_age=None):
        def f():
            key = f"{cell_id}_{s}_{e}"
            if lake.is_fresh("nasa_power", "daily", key, max_age):
                return "cached"
            return lake.put("nasa_power", "daily", key, sources.power_daily(lat, lon, s, e),
                            {"cell_id": cell_id, "lat": lat, "lon": lon, "start": s, "end": e})
        return f

    tasks = [task(cid, lat, lon, s, e) for cid, lat, lon in cells for s, e in blocks]
    if include_current_year:
        s = f"{end_year + 1}0101"
        e = date.fromordinal(date.today().toordinal() - 10).strftime("%Y%m%d")  # latência do POWER
        if e > s:
            tasks += [task(cid, lat, lon, s, e, max_age=7) for cid, lat, lon in cells]
    res = _run_tasks(tasks, workers)
    log.info("POWER ingest (%d células, %d blocos): %s", len(cells), len(blocks), dict(res))
    return res


def ingest_prices_macro(lake: Lake) -> Counter:
    """Pink Sheet (descobre URL; grava só se o hash mudar), câmbio diário por ano e IPCA mensal."""
    c: Counter = Counter()
    payload, url = sources.pink_sheet()
    c[lake.put("worldbank", "pink_sheet", "monthly", payload, {"url": url}, ext="xlsx")] += 1
    this_year = date.today().year
    for y in range(1999, this_year + 1):
        key = f"fx_{y}"
        if y < this_year and lake.is_fresh("bcb", "fx_diario", key):
            c["cached"] += 1
            continue
        end = date(y, 12, 31) if y < this_year else date.today()
        c[lake.put("bcb", "fx_diario", key, sources.bcb_sgs(config.BCB_FX_CODE, date(y, 1, 1), end), {"year": y})] += 1
    c[lake.put("bcb", "ipca_mensal", "all", sources.bcb_sgs(config.BCB_IPCA_CODE, date(1994, 7, 1), date.today()), {})] += 1
    log.info("Preços/macro ingest: %s", dict(c))
    return c


def ingest_conab(lake: Lake) -> Counter:
    c: Counter = Counter()
    for esp in config.CONAB_FILES:
        c[lake.put("conab", "serie_historica_cafe", esp, sources.conab_xls(esp), {"especie": esp}, ext="xls")] += 1
    log.info("CONAB ingest: %s", dict(c))
    return c


def now_utc() -> datetime:
    return datetime.now(timezone.utc).replace(tzinfo=None)


def producing_cells(lake: Lake) -> list[tuple[str, float, float]]:
    """Células POWER que contêm ao menos um município com área colhida de café > 0 em algum ano do PAM."""
    from .silver import build_pam_municipio, build_dim_municipio
    pam, _ = build_pam_municipio(lake, write=False)
    prod = pam.loc[(pam["area_colhida_ha"].fillna(0) > 0) | (pam["quantidade_t"].fillna(0) > 0), "cod_ibge"].unique()
    dim = build_dim_municipio(lake, write=False)
    sel = dim[dim["cod_ibge"].isin(prod)].drop_duplicates("cell_id")
    return sorted((r.cell_id, float(r.cell_lat), float(r.cell_lon)) for r in sel.itertuples())
