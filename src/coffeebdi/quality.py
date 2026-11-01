"""Testes de qualidade de dados (data quality) com severidade e relatório.

Cada checagem devolve um `CheckResult`. Severidade 'error' reprova o pipeline (quando `strict`);
'warn' registra um achado que exige atenção, mas não impede o uso (ex.: rendimento repetido).
"""
from __future__ import annotations

from dataclasses import asdict, dataclass

import numpy as np
import pandas as pd

from .ibge import is_valid_municipio
from .logging_utils import get_logger

log = get_logger("quality")


@dataclass
class CheckResult:
    table: str
    check: str
    severity: str          # 'error' | 'warn' | 'info'
    passed: bool
    n_failed: int
    n_total: int
    detail: str = ""


def _r(table, check, severity, bad, total, detail="") -> CheckResult:
    return CheckResult(table, check, severity, bool(bad == 0), int(bad), int(total), detail)


def not_null(df: pd.DataFrame, table: str, cols: list[str], severity="error") -> list[CheckResult]:
    return [_r(table, f"not_null:{c}", severity, df[c].isna().sum(), len(df)) for c in cols]


def unique_key(df: pd.DataFrame, table: str, keys: list[str], severity="error") -> CheckResult:
    return _r(table, f"unique:{'+'.join(keys)}", severity, df.duplicated(keys).sum(), len(df))


def in_range(df: pd.DataFrame, table: str, col: str, lo=None, hi=None, severity="error") -> CheckResult:
    s = df[col].dropna()
    bad = ((s < lo) if lo is not None else False) | ((s > hi) if hi is not None else False)
    return _r(table, f"range:{col}[{lo},{hi}]", severity, int(np.sum(bad)), len(s))


def valid_ibge(df: pd.DataFrame, table: str, col="cod_ibge", severity="error") -> CheckResult:
    return _r(table, f"ibge_code_valid:{col}", severity, (~df[col].map(is_valid_municipio)).sum(), len(df))


def referential(fact: pd.DataFrame, dim: pd.DataFrame, table: str, key: str, severity="error") -> CheckResult:
    miss = ~fact[key].isin(dim[key])
    return _r(table, f"fk:{key}", severity, miss.sum(), len(fact))


def min_rows(df: pd.DataFrame, table: str, n: int, severity="error") -> CheckResult:
    return _r(table, f"min_rows>={n}", severity, 0 if len(df) >= n else 1, len(df), f"linhas={len(df)}")


def consecutive_years(df: pd.DataFrame, table: str, key: str, year="ano", expected: tuple[int, int] | None = None,
                      severity="error") -> CheckResult:
    """Verifica se cada chave tem todos os anos do intervalo esperado (sem buracos de chave temporal)."""
    lo, hi = expected or (int(df[year].min()), int(df[year].max()))
    n_expected = hi - lo + 1
    cnt = df.groupby(key)[year].nunique()
    return _r(table, f"anos_completos:{key}[{lo}-{hi}]", severity, int((cnt != n_expected).sum()), len(cnt))


def yield_consistency(df: pd.DataFrame, table: str, tol: float = 0.02, severity="warn") -> CheckResult:
    """rendimento (kg/ha) ≈ quantidade (t) × 1000 / área colhida (ha). IBGE arredonda → tolerância relativa."""
    d = df[(df["area_colhida_ha"] > 0) & (df["quantidade_t"] > 0) & df["rendimento_kg_ha"].notna()]
    calc = d["quantidade_t"] * 1000 / d["area_colhida_ha"]
    rel = (calc - d["rendimento_kg_ha"]).abs() / d["rendimento_kg_ha"]
    return _r(table, f"rendimento_consistente(tol={tol:.0%})", severity, int((rel > tol).sum()), len(d),
              f"mediana do erro relativo = {rel.median():.4f}")


def repeated_yield(df: pd.DataFrame, table: str, thr: float = 0.5, severity="warn") -> CheckResult:
    """Fração de pares consecutivos (mesmo município) com rendimento *idêntico*. Valores altos sugerem
    estimativa administrativa repetida, não medição independente a cada ano."""
    d = df[df["rendimento_kg_ha"] > 0].sort_values(["cod_ibge", "ano"])
    prev = d.groupby("cod_ibge")["rendimento_kg_ha"].shift(1)
    same_year = d.groupby("cod_ibge")["ano"].diff() == 1
    pairs = same_year & prev.notna()
    frac = float((d.loc[pairs, "rendimento_kg_ha"] == prev[pairs]).mean()) if pairs.any() else np.nan
    return CheckResult(table, f"rendimento_repetido_ano_a_ano(<= {thr:.0%})", severity, bool(frac <= thr), int(frac * pairs.sum()),
                       int(pairs.sum()), f"fração idêntica ao ano anterior = {frac:.1%}")


def freshness(df: pd.DataFrame, table: str, col: str, min_value, severity="warn") -> CheckResult:
    mx = df[col].max()
    return CheckResult(table, f"freshness:{col}>={min_value}", severity, bool(mx >= min_value), 0 if mx >= min_value else 1, 1,
                       f"máximo={mx}")


def to_frame(results: list[CheckResult]) -> pd.DataFrame:
    return pd.DataFrame([asdict(r) for r in results])


def summarize(results: list[CheckResult]) -> dict:
    df = to_frame(results)
    return {"n_checks": len(df), "n_failed_error": int(((~df.passed) & (df.severity == "error")).sum()),
            "n_failed_warn": int(((~df.passed) & (df.severity == "warn")).sum())}
