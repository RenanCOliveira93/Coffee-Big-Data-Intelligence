import json

from coffeebdi import ingest, sources


def _fake_payload(year, rev=0):
    return json.dumps([{"id": "214", "resultados": [{"series": [
        {"localidade": {"id": "3538808", "nome": "Piraju - SP"}, "serie": {str(year): str(100 + rev)}}]}]}]).encode()


def test_incremental_ingest_is_idempotent(lake, monkeypatch):
    calls = []
    monkeypatch.setattr(sources, "sidra_available_years", lambda *a, **k: [2011, 2012, 2013, 2014])

    def fake(locality, especie, year):
        calls.append((locality, especie, year))
        return _fake_payload(year)
    monkeypatch.setattr(sources, "sidra_pam", fake)

    r1 = ingest.ingest_pam(lake, ufs=[35], since=2011, refresh_recent=2, include_uf_level=False)
    assert r1["new"] == 10 == len(calls)      # 2011 só "total" (1) + 2012–2014 × 3 espécies (9)
    n_first = len(calls)
    calls.clear()
    r2 = ingest.ingest_pam(lake, ufs=[35], since=2011, refresh_recent=2, include_uf_level=False)
    # só os 2 anos mais recentes (2013, 2014) são re-consultados; o resto vem do cache
    assert {y for _, _, y in calls} == {2013, 2014}
    assert r2["cached"] > 0 and r2["unchanged"] == len(calls) and "new" not in r2
    assert n_first > len(calls)


def test_revision_updates_only_changed(lake, monkeypatch):
    monkeypatch.setattr(sources, "sidra_available_years", lambda *a, **k: [2013, 2014])
    monkeypatch.setattr(sources, "sidra_pam", lambda loc, esp, y: _fake_payload(y))
    ingest.ingest_pam(lake, ufs=[35], since=2013, refresh_recent=1, include_uf_level=False)
    monkeypatch.setattr(sources, "sidra_pam", lambda loc, esp, y: _fake_payload(y, rev=5))   # IBGE revisou os dados
    r = ingest.ingest_pam(lake, ufs=[35], since=2013, refresh_recent=1, include_uf_level=False)
    assert r["updated"] > 0 and r["cached"] > 0
    assert lake.get_entry("ibge_pam", "pam_municipio", "uf35_total_2014")["n_fetches"] == 2
    assert lake.get_entry("ibge_pam", "pam_municipio", "uf35_total_2013")["n_fetches"] == 1   # fora da janela: intacto


def test_power_blocks_cached(lake, monkeypatch):
    n = []
    monkeypatch.setattr(sources, "power_daily", lambda lat, lon, s, e: (n.append((s, e)), b"{}")[1])
    cells = [("-46_-79", -23.0, -49.375), ("-40_-76", -20.0, -47.5)]
    ingest.ingest_power(lake, cells, start_year=2000, end_year=2025)
    assert len(n) == 2 * 3
    n.clear()
    r = ingest.ingest_power(lake, cells, start_year=2000, end_year=2025)
    assert n == [] and r["cached"] == 6
