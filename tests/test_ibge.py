import pytest

from coffeebdi.ibge import check_digit, is_valid_municipio, normalize_municipio, uf_from_municipio


def test_check_digit_known_municipios():
    assert check_digit("353880") == 8      # Piraju 3538808
    assert check_digit("351540") == 0      # Fartura 3515400


@pytest.mark.parametrize("code,ok", [("3538808", True), (3538808, True), ("3538807", False), ("353880", False), ("abc", False)])
def test_is_valid(code, ok):
    assert is_valid_municipio(code) is ok


def test_normalize_variants():
    assert normalize_municipio("3538808") == "3538808"
    assert normalize_municipio(3538808.0) == "3538808"
    assert normalize_municipio("3538808.0") == "3538808"
    assert normalize_municipio("353880") == "3538808"          # sem DV: completa
    assert uf_from_municipio("3538808") == 35


@pytest.mark.parametrize("bad", ["3538807", "12", None, "35388088"])
def test_normalize_rejects(bad):
    with pytest.raises(ValueError):
        normalize_municipio(bad)


def test_pirassununga_is_not_piraju():
    assert is_valid_municipio("3539301") and normalize_municipio("3539301") != "3538808"
