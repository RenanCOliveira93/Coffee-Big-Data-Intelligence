"""Normalização e validação de códigos IBGE de municípios.

O código de município tem 7 dígitos: 2 (UF) + 4 (município) + 1 (dígito verificador, DV).
DV: pesos 1,2,1,2,1,2 sobre os 6 primeiros dígitos; cada produto ≥ 10 tem seus dígitos somados;
DV = (10 − soma mod 10) mod 10.
Verificado manualmente: Piraju 3538808 (DV 8) e Fartura 3515400 (DV 0).
"""
from __future__ import annotations

import re

_W = (1, 2, 1, 2, 1, 2)


def check_digit(code6: str | int) -> int:
    s = str(code6).zfill(6)
    if not re.fullmatch(r"\d{6}", s):
        raise ValueError(f"código de 6 dígitos inválido: {code6!r}")
    total = 0
    for d, w in zip(s, _W):
        p = int(d) * w
        total += p // 10 + p % 10
    return (10 - total % 10) % 10


def is_valid_municipio(code) -> bool:
    """True se `code` (str/int) tem 7 dígitos e DV correto."""
    s = str(code).strip()
    return bool(re.fullmatch(r"\d{7}", s)) and check_digit(s[:6]) == int(s[6])


def normalize_municipio(code) -> str:
    """Devolve o código com 7 dígitos (string). Aceita int, str, float (ex. 3538808.0) e 6 dígitos
    (sem DV, completando-o). Levanta ValueError se não for possível."""
    if code is None:
        raise ValueError("código ausente")
    s = str(code).strip()
    if re.fullmatch(r"\d+\.0+", s):
        s = s.split(".")[0]
    if not re.fullmatch(r"\d{6,7}", s):
        raise ValueError(f"código IBGE inválido: {code!r}")
    if len(s) == 6:
        s += str(check_digit(s))
    if not is_valid_municipio(s):
        raise ValueError(f"DV inválido em {s}")
    return s


def uf_from_municipio(code) -> int:
    return int(normalize_municipio(code)[:2])
