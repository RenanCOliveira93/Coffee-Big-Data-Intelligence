"""Sessão Spark local com limites explícitos de memória e threads; localiza o JDK."""
from __future__ import annotations

import os
import shutil
from pathlib import Path

from . import config


def find_java_home() -> str | None:
    jh = os.environ.get("JAVA_HOME")
    if jh and (Path(jh) / "bin" / "java").exists():
        return jh
    for cand in sorted(config.TOOLS.glob("jdk/*/Contents/Home")) + sorted(config.TOOLS.glob("jdk/*")):
        if (cand / "bin" / "java").exists():
            return str(cand)
    java = shutil.which("java")
    if java:
        # no macOS /usr/bin/java é um stub: confirma que existe runtime de verdade
        import subprocess
        r = subprocess.run([java, "-version"], capture_output=True, text=True)
        if r.returncode == 0:
            return os.path.dirname(os.path.dirname(os.path.realpath(java)))
    return None


def java_available() -> bool:
    return find_java_home() is not None


def get_spark(threads: int = 4, mem_gb: float = 4.0, app: str = "coffeebdi", shuffle_partitions: int | None = None):
    jh = find_java_home()
    if not jh:
        raise RuntimeError("Java não encontrado: instale um JDK 17/21 ou defina JAVA_HOME (veja README).")
    os.environ["JAVA_HOME"] = jh
    from pyspark.sql import SparkSession
    b = (SparkSession.builder.master(f"local[{threads}]").appName(app)
         .config("spark.driver.memory", f"{max(1, int(mem_gb))}g")
         .config("spark.ui.enabled", "false")
         .config("spark.sql.shuffle.partitions", str(shuffle_partitions or max(8, threads * 2)))
         .config("spark.sql.session.timeZone", "UTC")
         .config("spark.sql.parquet.compression.codec", "zstd")
         .config("spark.sql.execution.arrow.pyspark.enabled", "false"))
    return b.getOrCreate()
