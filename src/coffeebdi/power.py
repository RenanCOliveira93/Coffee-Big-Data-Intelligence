"""Grade nativa do NASA POWER (MERRA-2): 0,5° de latitude × 0,625° de longitude.

Os centros das células são múltiplos de 0,5° (lat) e de 0,625° (lon); `cell_id` = "<ilat>_<ilon>".
"""
from __future__ import annotations

from . import config


def cell_index(lat: float, lon: float) -> tuple[int, int]:
    return round(lat / config.POWER_LAT_STEP), round(lon / config.POWER_LON_STEP)


def cell_id_for(lat: float, lon: float) -> str:
    i, j = cell_index(lat, lon)
    return f"{i}_{j}"


def cell_center(lat: float, lon: float) -> tuple[float, float]:
    i, j = cell_index(lat, lon)
    return i * config.POWER_LAT_STEP, j * config.POWER_LON_STEP
