"""Logging do pipeline: console + arquivo rotativo em logs/pipeline.log."""
from __future__ import annotations

import logging
import sys
from logging.handlers import RotatingFileHandler

from . import config

_FMT = "%(asctime)s | %(levelname)-7s | %(name)s | %(message)s"
_configured = False


def get_logger(name: str = "coffeebdi") -> logging.Logger:
    global _configured
    root = logging.getLogger("coffeebdi")
    if not _configured:
        root.setLevel(logging.INFO)
        root.propagate = False
        sh = logging.StreamHandler(sys.stdout)
        sh.setFormatter(logging.Formatter(_FMT))
        root.addHandler(sh)
        try:
            config.LOGS.mkdir(parents=True, exist_ok=True)
            fh = RotatingFileHandler(config.LOGS / "pipeline.log", maxBytes=2_000_000, backupCount=3, encoding="utf-8")
            fh.setFormatter(logging.Formatter(_FMT))
            root.addHandler(fh)
        except OSError:
            pass
        _configured = True
    return logging.getLogger(name if name.startswith("coffeebdi") else f"coffeebdi.{name}")
