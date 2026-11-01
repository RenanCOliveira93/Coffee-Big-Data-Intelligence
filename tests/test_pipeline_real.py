"""Testes sobre o lake REAL (rodam só se o pipeline já foi executado nesta máquina)."""
import pandas as pd
import pytest

from coffeebdi import config, silver
from coffeebdi.lake import Lake

pytestmark = pytest.mark.skipif(not (config.LAKE / "bronze" / "ibge_pam").exists(), reason="lake real ausente")


def test_silver_rebuild_is_deterministic():
    lk = Lake()
    a, _ = silver.build_pam_municipio(lk, write=False)
    b, _ = silver.build_pam_municipio(lk, write=False)
    pd.testing.assert_frame_equal(a.sort_values(["cod_ibge", "especie", "ano"]).reset_index(drop=True),
                                  b.sort_values(["cod_ibge", "especie", "ano"]).reset_index(drop=True))


def test_pam_keys_unique_and_codes_valid():
    from coffeebdi.ibge import is_valid_municipio
    pam = silver.read_table(Lake(), "silver", "pam_municipio")
    assert not pam.duplicated(["cod_ibge", "especie", "ano"]).any()
    assert pam["cod_ibge"].map(is_valid_municipio).all()


def test_no_mixing_species_before_2012():
    pam = silver.read_table(Lake(), "silver", "pam_municipio")
    assert pam[pam.especie != "total"]["ano"].min() >= config.ESPECIE_DESAGREGADA_DESDE


def test_climate_cells_complete():
    clim = silver.read_table(Lake(), "silver", "clima_diario")
    n = clim.groupby("cell_id").size()
    assert n.nunique() == 1 and clim["cell_id"].nunique() >= 50      # regressão: cell_id com "_" colapsava células
    assert not clim.duplicated(["cell_id", "date"]).any()


def test_conab_vs_pam_same_order_of_magnitude():
    g = silver.read_table(Lake(), "gold", "conab_vs_pam")
    sp = g[(g.uf == "SP") & (g.especie == "arabica") & (~g.estimativa)]
    assert sp["dif_rel"].abs().median() < 0.2
