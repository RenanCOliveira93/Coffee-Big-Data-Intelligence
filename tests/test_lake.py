from pathlib import Path


def test_put_new_unchanged_updated(lake):
    st = lake.put("src", "ds", "k1", b'{"a": 1}', {"p": 1}, 1)
    assert st == "new"
    assert lake.put("src", "ds", "k1", b'{"a": 1}') == "unchanged"
    assert lake.put("src", "ds", "k1", b'{"a": 2}') == "updated"
    e = lake.get_entry("src", "ds", "k1")
    assert e["n_fetches"] == 3 and lake.read_json("src", "ds", "k1") == {"a": 2}


def test_is_fresh_and_age(lake):
    assert not lake.is_fresh("s", "d", "x")
    lake.put("s", "d", "x", b"1")
    assert lake.is_fresh("s", "d", "x")
    assert not lake.is_fresh("s", "d", "x", max_age_days=0)      # idade >= 0 => obsoleto
    assert lake.is_fresh("s", "d", "x", max_age_days=1)


def test_missing_file_is_not_fresh(lake):
    lake.put("s", "d", "x", b"1")
    Path(lake.get_entry("s", "d", "x")["path"]).unlink()
    assert not lake.is_fresh("s", "d", "x")


def test_deterministic_gzip_bytes(lake):
    lake.put("s", "d", "a", b"payload")
    b1 = Path(lake.get_entry("s", "d", "a")["path"]).read_bytes()
    lake.put("s", "d", "b", b"payload")
    assert b1 == Path(lake.get_entry("s", "d", "b")["path"]).read_bytes()   # mtime=0 -> reproduzível


def test_keys_manifest_and_runs(lake):
    from datetime import datetime
    lake.put("s", "d", "k2", b"1"); lake.put("s", "d", "k1", b"2")
    assert lake.keys("s", "d") == ["k1", "k2"]
    assert len(lake.manifest_df()) == 2
    lake.log_run("r1", "ingest", datetime(2026, 1, 1), "ok", {"n": 1})
    assert lake.runs_df().iloc[0]["status"] == "ok"


def test_key_sanitization(lake):
    p = lake.bronze_path("s", "d", "-40_-76/../x")
    assert ".." not in p.name and "/" not in p.name
