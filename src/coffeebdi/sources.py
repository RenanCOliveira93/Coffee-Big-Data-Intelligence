"""Conectores HTTP das fontes externas. Só buscam bytes; não gravam nada (a ingestão grava na bronze).

Segurança: a verificação TLS fica SEMPRE ligada. Fontes com cadeia de certificado problemática
(ex.: INMET/portal CONAB antigo, verificado em 2026-10-31) não têm conector; veja docs/pt-BR/02_fontes_de_dados.md.
"""
from __future__ import annotations

import re
import time
from datetime import date

import requests

from . import config
from .logging_utils import get_logger

log = get_logger("sources")
_UA = {"User-Agent": "coffeebdi/0.1 (research pipeline)"}
_session = requests.Session()
_session.headers.update(_UA)


def http_get(url: str, params: dict | None = None, timeout: int = 180, retries: int = 4, backoff: float = 2.0) -> requests.Response:
    last: Exception | None = None
    for i in range(retries):
        try:
            r = _session.get(url, params=params, timeout=timeout)
            if r.status_code in (429, 500, 502, 503, 504):
                raise requests.HTTPError(f"HTTP {r.status_code}", response=r)
            r.raise_for_status()
            return r
        except requests.RequestException as e:  # noqa: PERF203
            last = e
            wait = backoff ** i
            log.warning("GET falhou (%s) tentativa %d/%d; aguardando %.0fs", e, i + 1, retries, wait)
            time.sleep(wait)
    raise RuntimeError(f"falha ao buscar {url}: {last}")


# ---------------- IBGE ----------------
def sidra_available_years(table: int = config.PAM_TABLE) -> list[int]:
    r = http_get(f"{config.SIDRA_BASE}/{table}/periodos").json()
    return sorted(int(p["id"]) for p in r)


def sidra_pam(locality: str, especie: str, year: int) -> bytes:
    """PAM (tabela 1613) para uma espécie e um ano. `locality` ex.: 'N6[N3[35]]', 'N3[all]', 'N1[all]'."""
    vars_ = "|".join(str(v) for v in config.PAM_VARS)
    url = f"{config.SIDRA_BASE}/{config.PAM_TABLE}/periodos/{year}/variaveis/{vars_}"
    r = http_get(url, params={"localidades": locality,
                              "classificacao": f"{config.PAM_CLASSIF}[{config.ESPECIES[especie]}]"})
    return r.content


def sidra_censo(uf: int) -> bytes:
    vars_ = "|".join(str(v) for v in config.CENSO_VARS)
    url = f"{config.SIDRA_BASE}/{config.CENSO_TABLE}/periodos/2022/variaveis/{vars_}"
    return http_get(url, params={"localidades": f"N6[N3[{uf}]]"}).content


def ibge_municipios(uf: int) -> bytes:
    return http_get(f"https://servicodados.ibge.gov.br/api/v1/localidades/estados/{uf}/municipios").content


def ibge_malha_uf(uf: int) -> bytes:
    return http_get(f"https://servicodados.ibge.gov.br/api/v3/malhas/estados/{uf}",
                    params={"intrarregiao": "municipio", "formato": "application/vnd.geo+json",
                            "qualidade": "minima"}).content


# ---------------- NASA POWER ----------------
def power_daily(lat: float, lon: float, start: str, end: str) -> bytes:
    """Série diária (AG community) de um ponto/célula. `start`/`end` em YYYYMMDD."""
    return http_get(config.POWER_URL, params={
        "parameters": ",".join(config.POWER_PARAMS), "community": "AG", "longitude": f"{lon:.3f}",
        "latitude": f"{lat:.3f}", "start": start, "end": end, "format": "JSON"}, timeout=240).content


# ---------------- Preços / macro ----------------
def discover_pink_sheet_url() -> str:
    """O link do Pink Sheet muda a cada edição (hash no caminho); descobre-o na página oficial."""
    html = http_get("https://www.worldbank.org/en/research/commodity-markets").text
    m = re.findall(r'https://thedocs\.worldbank\.org/[^"\']*CMO-Historical-Data-Monthly\.xlsx', html)
    if not m:
        raise RuntimeError("link do Pink Sheet não encontrado na página do Banco Mundial")
    return m[0]


def pink_sheet() -> tuple[bytes, str]:
    url = discover_pink_sheet_url()
    return http_get(url).content, url


def bcb_sgs(code: int, start: date, end: date) -> bytes:
    """Série SGS do BCB no intervalo (séries diárias: janela ≤ 10 anos)."""
    return http_get(config.BCB_URL.format(code=code), params={
        "formato": "json", "dataInicial": start.strftime("%d/%m/%Y"), "dataFinal": end.strftime("%d/%m/%Y")}).content


# ---------------- CONAB ----------------
def conab_xls(especie: str) -> bytes:
    return http_get(f"{config.CONAB_BASE}/{config.CONAB_FILES[especie]}/@@download/file").content
