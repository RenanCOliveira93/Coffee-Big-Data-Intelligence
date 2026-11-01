"""Lake local: camada bronze imutável + manifesto idempotente (DuckDB) + registro de execuções.

Idempotência: cada requisição tem uma `request_key` determinística. Reingerir a mesma chave
- é *pulado* (status "cached") se já existe e não está obsoleto;
- se refeito e o hash do conteúdo (sha256) é igual, nada é reescrito ("unchanged");
- se o conteúdo mudou (revisão do IBGE, p. ex.), o arquivo é substituído atomicamente ("updated").
"""
from __future__ import annotations

import gzip
import hashlib
import json
import os
import threading
from datetime import datetime, timezone
from pathlib import Path

import duckdb

from . import config
from .logging_utils import get_logger

log = get_logger("lake")

_DDL = """
CREATE TABLE IF NOT EXISTS manifest (
  source VARCHAR, dataset VARCHAR, request_key VARCHAR, path VARCHAR, sha256 VARCHAR,
  bytes BIGINT, n_records BIGINT, params_json VARCHAR, first_fetched_at TIMESTAMP, last_fetched_at TIMESTAMP,
  n_fetches INTEGER, PRIMARY KEY (source, dataset, request_key));
CREATE TABLE IF NOT EXISTS runs (
  run_id VARCHAR, step VARCHAR, started_at TIMESTAMP, ended_at TIMESTAMP, status VARCHAR, details_json VARCHAR);
"""


def _now() -> datetime:
    return datetime.now(timezone.utc).replace(tzinfo=None)


class Lake:
    def __init__(self, root: Path | str | None = None):
        self.root = Path(root) if root else config.LAKE
        self.bronze = self.root / "bronze"
        self.silver = self.root / "silver"
        self.gold = self.root / "gold"
        self.meta_dir = self.root / "_meta"
        for d in (self.bronze, self.silver, self.gold, self.meta_dir):
            d.mkdir(parents=True, exist_ok=True)
        self._lock = threading.Lock()
        self._con = duckdb.connect(str(self.meta_dir / "meta.duckdb"))
        self._con.execute(_DDL)

    # -------- bronze --------
    def bronze_path(self, source: str, dataset: str, key: str, ext: str = "json.gz") -> Path:
        safe = "".join(c if c.isalnum() or c in "-_." else "_" for c in key).replace("..", "_")
        return self.bronze / source / dataset / f"{safe}.{ext}"

    def get_entry(self, source: str, dataset: str, key: str) -> dict | None:
        with self._lock:
            r = self._con.execute(
                "SELECT path, sha256, bytes, n_records, last_fetched_at, n_fetches FROM manifest "
                "WHERE source=? AND dataset=? AND request_key=?", [source, dataset, key]).fetchone()
        if not r:
            return None
        return dict(zip(["path", "sha256", "bytes", "n_records", "last_fetched_at", "n_fetches"], r))

    def is_fresh(self, source: str, dataset: str, key: str, max_age_days: float | None = None) -> bool:
        e = self.get_entry(source, dataset, key)
        if not e or not Path(e["path"]).exists():
            return False
        if max_age_days is None:
            return True
        return (_now() - e["last_fetched_at"]).total_seconds() < max_age_days * 86400

    def put(self, source: str, dataset: str, key: str, payload: bytes, params: dict | None = None,
            n_records: int | None = None, ext: str = "json.gz") -> str:
        """Grava payload na bronze. Retorna 'new' | 'unchanged' | 'updated'."""
        sha = hashlib.sha256(payload).hexdigest()
        path = self.bronze_path(source, dataset, key, ext)
        path.parent.mkdir(parents=True, exist_ok=True)
        existing = self.get_entry(source, dataset, key)
        if existing and existing["sha256"] == sha and path.exists():
            status = "unchanged"
        else:
            tmp = path.with_suffix(path.suffix + f".tmp{os.getpid()}")
            data = gzip.compress(payload, mtime=0) if ext.endswith(".gz") else payload
            tmp.write_bytes(data)
            os.replace(tmp, path)  # atômico
            status = "updated" if existing else "new"
        with self._lock:
            now = _now()
            if existing:
                self._con.execute(
                    "UPDATE manifest SET path=?, sha256=?, bytes=?, n_records=?, params_json=?, last_fetched_at=?, "
                    "n_fetches=n_fetches+1 WHERE source=? AND dataset=? AND request_key=?",
                    [str(path), sha, len(payload), n_records, json.dumps(params or {}, sort_keys=True), now,
                     source, dataset, key])
            else:
                self._con.execute(
                    "INSERT INTO manifest VALUES (?,?,?,?,?,?,?,?,?,?,1)",
                    [source, dataset, key, str(path), sha, len(payload), n_records,
                     json.dumps(params or {}, sort_keys=True), now, now])
        log.info("bronze %s/%s/%s -> %s (%d bytes)", source, dataset, key, status, len(payload))
        return status

    def read(self, source: str, dataset: str, key: str) -> bytes:
        e = self.get_entry(source, dataset, key)
        if not e:
            raise KeyError(f"{source}/{dataset}/{key} não ingerido")
        raw = Path(e["path"]).read_bytes()
        return gzip.decompress(raw) if e["path"].endswith(".gz") else raw

    def read_json(self, source: str, dataset: str, key: str):
        return json.loads(self.read(source, dataset, key))

    def keys(self, source: str, dataset: str) -> list[str]:
        with self._lock:
            rows = self._con.execute(
                "SELECT request_key FROM manifest WHERE source=? AND dataset=? ORDER BY 1", [source, dataset]).fetchall()
        return [r[0] for r in rows]

    def manifest_df(self):
        with self._lock:
            return self._con.execute("SELECT * FROM manifest ORDER BY source, dataset, request_key").df()

    # -------- runs --------
    def log_run(self, run_id: str, step: str, started_at: datetime, status: str, details: dict | None = None):
        with self._lock:
            self._con.execute("INSERT INTO runs VALUES (?,?,?,?,?,?)",
                              [run_id, step, started_at, _now(), status, json.dumps(details or {}, default=str)])

    def runs_df(self):
        with self._lock:
            return self._con.execute("SELECT * FROM runs ORDER BY started_at").df()

    def close(self):
        with self._lock:
            self._con.close()
