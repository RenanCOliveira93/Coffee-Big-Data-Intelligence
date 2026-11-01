"""Silver -> Gold: marts analíticos em DuckDB SQL.

Janelas climáticas para o ano-colheita t (simplificações *exploratórias* da fenologia do café arábica;
a época real varia com região, altitude e cultivar). Todas terminam em 31/mar/t, ou seja, antes da data de
corte de previsão (1º de maio de t) => sem vazamento de informação do ano-alvo:
  * chuva_floracao   : soma de chuva de set–nov de t−1
  * tmean_floracao   : temperatura média de set–nov de t−1
  * chuva_granacao   : soma de chuva de dez de t−1 a mar de t
  * tmax_granacao    : média da temperatura máxima de dez de t−1 a mar de t
  * chuva_12m_pre    : soma de chuva de abr de t−1 a mar de t
  * dias_frio_inv_prev: nº de dias com T2M_MIN ≤ 4 °C em jun–ago de t−1 (grade de ~55 km: subestima geadas locais)
"""
from __future__ import annotations

import duckdb
import pandas as pd

from . import config
from .lake import Lake
from .logging_utils import get_logger
from .silver import write_parquet_dataset

log = get_logger("gold")

FRIO_LIMIAR_C = 4.0
MIN_AREA_HA = 100.0          # área colhida mínima (ano t−1 e t) para elegibilidade em modelagem
BASE_REAL_ANO = 2025          # reais constantes de 2025 (média anual do IPCA)


def _con(lake: Lake) -> duckdb.DuckDBPyConnection:
    con = duckdb.connect()
    for t in ("pam_municipio", "pam_uf", "clima_diario", "conab_uf"):
        p = lake.silver / t
        if p.exists():
            con.execute(f"CREATE VIEW {t} AS SELECT * FROM read_parquet('{p}/**/*.parquet', hive_partitioning=true)")
    for t in ("dim_municipio", "clima_celula", "preco_cafe_mensal", "cambio_mensal", "ipca_mensal"):
        p = lake.silver / t
        if p.exists():
            con.execute(f"CREATE VIEW {t} AS SELECT * FROM read_parquet('{p}/**/*.parquet')")
    return con


def build_clima_mensal(con) -> pd.DataFrame:
    return con.execute(f"""
        SELECT cell_id, ano, mes, ano*12 + mes - 1 AS mi, count(*) AS n_dias,
               sum(prec_mm) AS prec_mm, avg(t2m) AS t2m_mean, avg(t2m_max) AS tmax_mean, avg(t2m_min) AS tmin_mean,
               min(t2m_min) AS tmin_min, sum(CASE WHEN t2m_min <= {FRIO_LIMIAR_C} THEN 1 ELSE 0 END) AS dias_frio
        FROM clima_diario GROUP BY cell_id, ano, mes ORDER BY cell_id, ano, mes""").df()


def build_clima_features(con) -> pd.DataFrame:
    """Uma linha por (cell_id, ano-colheita). Janela incompleta (faltam meses) => NULL."""
    return con.execute(f"""
        WITH m AS (SELECT cell_id, ano*12 + mes - 1 AS mi, ano, count(*) AS n_dias, sum(prec_mm) AS prec,
                          avg(t2m) AS t2m, avg(t2m_max) AS tmax,
                          sum(CASE WHEN t2m_min <= {FRIO_LIMIAR_C} THEN 1 ELSE 0 END) AS frio
                   FROM clima_diario GROUP BY cell_id, ano, mes),
        y AS (SELECT DISTINCT cell_id, ano AS t FROM m)
        SELECT y.cell_id, y.t AS ano,
          CASE WHEN count(*) FILTER (WHERE m.mi BETWEEN (y.t-1)*12+8 AND (y.t-1)*12+10) = 3
               THEN sum(m.prec) FILTER (WHERE m.mi BETWEEN (y.t-1)*12+8 AND (y.t-1)*12+10) END AS chuva_floracao,
          CASE WHEN count(*) FILTER (WHERE m.mi BETWEEN (y.t-1)*12+8 AND (y.t-1)*12+10) = 3
               THEN avg(m.t2m) FILTER (WHERE m.mi BETWEEN (y.t-1)*12+8 AND (y.t-1)*12+10) END AS tmean_floracao,
          CASE WHEN count(*) FILTER (WHERE m.mi BETWEEN (y.t-1)*12+11 AND y.t*12+2) = 4
               THEN sum(m.prec) FILTER (WHERE m.mi BETWEEN (y.t-1)*12+11 AND y.t*12+2) END AS chuva_granacao,
          CASE WHEN count(*) FILTER (WHERE m.mi BETWEEN (y.t-1)*12+11 AND y.t*12+2) = 4
               THEN avg(m.tmax) FILTER (WHERE m.mi BETWEEN (y.t-1)*12+11 AND y.t*12+2) END AS tmax_granacao,
          CASE WHEN count(*) FILTER (WHERE m.mi BETWEEN (y.t-1)*12+3 AND y.t*12+2) = 12
               THEN sum(m.prec) FILTER (WHERE m.mi BETWEEN (y.t-1)*12+3 AND y.t*12+2) END AS chuva_12m_pre,
          CASE WHEN count(*) FILTER (WHERE m.mi BETWEEN (y.t-1)*12+5 AND (y.t-1)*12+7) = 3
               THEN sum(m.frio) FILTER (WHERE m.mi BETWEEN (y.t-1)*12+5 AND (y.t-1)*12+7) END AS dias_frio_inv_prev,
          make_date(y.t - 0, 3, 31) AS ultima_data_usada,
          make_date(y.t, 5, 1) AS data_corte_previsao
        FROM y JOIN m ON m.cell_id = y.cell_id AND m.mi BETWEEN (y.t-2)*12 AND y.t*12+2
        GROUP BY y.cell_id, y.t ORDER BY y.cell_id, y.t""").df()


def build_precos_anuais(con) -> pd.DataFrame:
    """Preço do arábica (indicador ICO, USD/kg) convertido em R$/saca de 60 kg, nominal e real (IPCA, base média de 2025)."""
    return con.execute(f"""
        WITH base AS (SELECT avg(ipca_indice) AS b FROM ipca_mensal WHERE year(mes_ref) = {config_base()}),
        m AS (SELECT p.mes_ref, p.cafe_arabica_usd_kg AS usd_kg, p.cafe_robusta_usd_kg AS usd_kg_robusta,
                     c.brl_usd, p.cafe_arabica_usd_kg * {config.SACA_KG} AS usd_saca,
                     p.cafe_arabica_usd_kg * {config.SACA_KG} * c.brl_usd AS brl_saca_nom,
                     p.cafe_arabica_usd_kg * {config.SACA_KG} * c.brl_usd * (SELECT b FROM base) / i.ipca_indice AS brl_saca_real
              FROM preco_cafe_mensal p JOIN cambio_mensal c USING (mes_ref) JOIN ipca_mensal i USING (mes_ref))
        SELECT year(mes_ref) AS ano, count(*) AS n_meses, avg(usd_kg) AS usd_kg_arabica, avg(usd_kg_robusta) AS usd_kg_robusta,
               avg(brl_usd) AS brl_usd, avg(brl_saca_nom) AS brl_saca_nominal, avg(brl_saca_real) AS brl_saca_real_{config_base()}
        FROM m GROUP BY 1 ORDER BY 1""").df()


def config_base() -> int:
    return BASE_REAL_ANO


def build_ipca_anual(con) -> pd.DataFrame:
    return con.execute(f"""
        SELECT year(mes_ref) AS ano, count(*) AS n_meses, avg(ipca_indice) AS ipca_indice_medio,
               avg(ipca_indice) / (SELECT avg(ipca_indice) FROM ipca_mensal WHERE year(mes_ref) = {BASE_REAL_ANO}) AS fator_nominal_para_real
        FROM ipca_mensal GROUP BY 1 ORDER BY 1""").df()


def build_painel(con, ano_min: int = 2012) -> pd.DataFrame:
    """Painel município × ano (arábica) com lags, clima, território e preço.

    Lags usam apenas anos anteriores (LAG sobre ano consecutivo). `elegivel_modelo` exige área colhida mínima
    no ano t e em t−1 (rendimento de áreas minúsculas é instável)."""
    return con.execute(f"""
        WITH a AS (
          SELECT p.cod_ibge, p.ano, p.area_colhida_ha, p.quantidade_t, p.rendimento_kg_ha, p.valor_mil_reais,
                 p.area_destinada_ha, p.tem_producao
          FROM pam_municipio p WHERE p.especie = 'arabica' AND p.ano >= {ano_min}),
        l AS (
          SELECT *,
            CASE WHEN lag(ano,1) OVER w = ano-1 THEN lag(rendimento_kg_ha,1) OVER w END AS rend_lag1,
            CASE WHEN lag(ano,2) OVER w = ano-2 THEN lag(rendimento_kg_ha,2) OVER w END AS rend_lag2,
            CASE WHEN lag(ano,3) OVER w = ano-3 THEN lag(rendimento_kg_ha,3) OVER w END AS rend_lag3,
            CASE WHEN lag(ano,2) OVER w = ano-2 THEN lag(area_colhida_ha,2) OVER w END AS area_lag2,
            CASE WHEN lag(ano,1) OVER w = ano-1 THEN lag(area_colhida_ha,1) OVER w END AS area_lag1,
            CASE WHEN lag(ano,1) OVER w = ano-1 THEN lag(quantidade_t,1) OVER w END AS prod_lag1
          FROM a WINDOW w AS (PARTITION BY cod_ibge ORDER BY ano)),
        reg AS (SELECT ano, sum(quantidade_t) * 1000 / sum(area_colhida_ha) AS rend_reg
                FROM a WHERE area_colhida_ha >= {MIN_AREA_HA} GROUP BY ano),
        pr AS (SELECT ano + 1 AS ano, brl_saca_real_{config_base()} AS preco_real_lag1,
                      usd_kg_arabica AS preco_usd_kg_lag1 FROM precos_anuais)
        SELECT l.*, d.municipio, d.uf, d.microrregiao, d.mesorregiao, d.lat, d.lon, d.area_km2, d.pop_2022,
               d.cell_id, c.elev_m,
               f.chuva_floracao, f.tmean_floracao, f.chuva_granacao, f.tmax_granacao, f.chuva_12m_pre, f.dias_frio_inv_prev,
               pr.preco_real_lag1, pr.preco_usd_kg_lag1,
               r1.rend_reg AS rend_reg_lag1, r2.rend_reg AS rend_reg_lag2, r3.rend_reg AS rend_reg_lag3,
               (l.area_colhida_ha >= {MIN_AREA_HA} AND l.area_lag1 >= {MIN_AREA_HA}
                AND l.rendimento_kg_ha IS NOT NULL AND l.rend_lag1 IS NOT NULL) AS elegivel_modelo
        FROM l
        LEFT JOIN dim_municipio d USING (cod_ibge)
        LEFT JOIN clima_celula c ON c.cell_id = d.cell_id
        LEFT JOIN clima_features f ON f.cell_id = d.cell_id AND f.ano = l.ano
        LEFT JOIN pr ON pr.ano = l.ano
        LEFT JOIN reg r1 ON r1.ano = l.ano - 1
        LEFT JOIN reg r2 ON r2.ano = l.ano - 2
        LEFT JOIN reg r3 ON r3.ano = l.ano - 3
        WHERE l.area_colhida_ha > 0
        ORDER BY l.cod_ibge, l.ano""").df()


def build_conab_vs_pam(con) -> pd.DataFrame:
    """Reconciliação UF: produção CONAB (mil sacas × 60 kg) vs. PAM/IBGE (toneladas), por espécie e ano."""
    return con.execute(f"""
        WITH c AS (SELECT uf, safra AS ano, CASE WHEN especie='canephora' THEN 'canephora' ELSE especie END AS especie,
                          valor * {config.SACA_KG} AS producao_conab_t, estimativa
                   FROM conab_uf WHERE indicador = 'producao_mil_sacas' AND uf <> 'BRASIL'),
             p AS (SELECT uf, ano, especie, quantidade_t AS producao_pam_t FROM pam_uf WHERE especie IN ('arabica','canephora'))
        SELECT c.uf, c.ano, c.especie, c.producao_conab_t, p.producao_pam_t, c.estimativa,
               (c.producao_conab_t - p.producao_pam_t) / NULLIF(p.producao_pam_t, 0) AS dif_rel
        FROM c JOIN p USING (uf, ano, especie) ORDER BY uf, especie, ano""").df()


def build_all(lake: Lake) -> dict[str, int]:
    con = _con(lake)
    out: dict[str, pd.DataFrame] = {}
    out["clima_mensal"] = build_clima_mensal(con)
    out["clima_features"] = build_clima_features(con)
    write_parquet_dataset(out["clima_mensal"], lake.gold / "clima_mensal", ["ano"], ["cell_id", "ano", "mes"])
    write_parquet_dataset(out["clima_features"], lake.gold / "clima_features", None, ["cell_id", "ano"])
    # as views abaixo dependem de tabelas gold/silver já registradas
    con.register("clima_features", out["clima_features"])
    out["precos_anuais"] = build_precos_anuais(con)
    con.register("precos_anuais", out["precos_anuais"])
    out["ipca_anual"] = build_ipca_anual(con)
    out["painel_cafe_arabica"] = build_painel(con)
    out["conab_vs_pam"] = build_conab_vs_pam(con)
    for name in ("precos_anuais", "ipca_anual", "painel_cafe_arabica", "conab_vs_pam"):
        write_parquet_dataset(out[name], lake.gold / name, None, ["ano"] if "ano" in out[name] else None)
    con.close()
    sizes = {k: len(v) for k, v in out.items()}
    log.info("gold: %s", sizes)
    return sizes
