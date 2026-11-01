"""Configuração central (caminhos, constantes das fontes, parâmetros por variável de ambiente)."""
from __future__ import annotations

import os
from pathlib import Path

from dotenv import load_dotenv

ROOT = Path(__file__).resolve().parents[2]
load_dotenv(ROOT / ".env")

DATA = ROOT / "data"
LAKE = DATA / "lake"
BRONZE, SILVER, GOLD, META = LAKE / "bronze", LAKE / "silver", LAKE / "gold", LAKE / "_meta"
BENCH = DATA / "bench"
SYNTH = BENCH / "synthetic"      # SINTÉTICO: nunca é volume real da cafeicultura
BENCH_REAL = BENCH / "real"       # recorte dos dados reais no mesmo esquema do benchmark
OUTPUTS = ROOT / "outputs"
LOGS = ROOT / "logs"
TOOLS = ROOT / ".tools"


def _ints(s: str) -> list[int]:
    return [int(x) for x in s.replace(" ", "").split(",") if x]


UFS = _ints(os.getenv("COFFEE_UFS", "35"))
POWER_START_YEAR = int(os.getenv("POWER_START_YEAR", "2000"))
POWER_END_YEAR = int(os.getenv("POWER_END_YEAR", "2025"))
PAM_START_YEAR = int(os.getenv("PAM_START_YEAR", "1974"))
PAM_REFRESH_RECENT_YEARS = int(os.getenv("PAM_REFRESH_RECENT_YEARS", "2"))
BENCH_THREADS = int(os.getenv("BENCH_THREADS", "4"))
BENCH_MEM_GB = float(os.getenv("BENCH_MEM_GB", "8"))
USE_MLFLOW = os.getenv("USE_MLFLOW", "0") == "1"

# --- IBGE SIDRA / PAM (lavouras permanentes) ---
SIDRA_BASE = "https://servicodados.ibge.gov.br/api/v3/agregados"
PAM_TABLE = 1613
PAM_CLASSIF = 82                       # "Produto das lavouras permanentes"
ESPECIES = {"total": 2723, "arabica": 31619, "canephora": 31620}   # categorias da classificação 82
ESPECIE_ID_TO_NAME = {v: k for k, v in ESPECIES.items()}
ESPECIE_DESAGREGADA_DESDE = 2012       # Arábica/Canephora só existem a partir de 2012 (verificado na API)
PAM_VARS = {2313: "area_destinada_ha", 216: "area_colhida_ha", 214: "quantidade_t",
            112: "rendimento_kg_ha", 215: "valor_mil_reais"}
CENSO_TABLE = 4714                     # Censo 2022: área, população, densidade
CENSO_VARS = {6318: "area_km2", 93: "pop_2022", 614: "densidade_hab_km2"}

# Códigos especiais da API do IBGE (convenção SIDRA)
SIDRA_SPECIAL = {"-": "zero", "0": "zero_arredondado", "..": "nao_se_aplica", "...": "indisponivel", "X": "suprimido"}

# --- Clima: NASA POWER ---
POWER_URL = "https://power.larc.nasa.gov/api/temporal/daily/point"
POWER_PARAMS = ("T2M", "T2M_MAX", "T2M_MIN", "PRECTOTCORR")
POWER_LAT_STEP, POWER_LON_STEP = 0.5, 0.625   # grade nativa (MERRA-2)

# --- Preços / macro ---
WB_PINK_URL = ("https://thedocs.worldbank.org/en/doc/5d903e848db1d1b83e0ec8f744e55570-0350012021/"
               "related/CMO-Historical-Data-Monthly.xlsx")
BCB_URL = "https://api.bcb.gov.br/dados/serie/bcdata.sgs.{code}/dados"
BCB_FX_CODE = 1        # Taxa de câmbio livre, dólar (venda), diária
BCB_IPCA_CODE = 433    # IPCA, variação mensal (%)

# --- CONAB ---
CONAB_BASE = "https://www.gov.br/conab/pt-br/atuacao/informacoes-agropecuarias/safras/series-historicas/cafe"
CONAB_FILES = {"arabica": "arabica/cafearabicaseriehist.xls", "conilon": "conilon/cafeconilonseriehist.xls"}
SACA_KG = 60.0

UF_SIGLA = {11: "RO", 12: "AC", 13: "AM", 14: "RR", 15: "PA", 16: "AP", 17: "TO", 21: "MA", 22: "PI", 23: "CE",
            24: "RN", 25: "PB", 26: "PE", 27: "AL", 28: "SE", 29: "BA", 31: "MG", 32: "ES", 33: "RJ", 35: "SP",
            41: "PR", 42: "SC", 43: "RS", 50: "MS", 51: "MT", 52: "GO", 53: "DF"}
