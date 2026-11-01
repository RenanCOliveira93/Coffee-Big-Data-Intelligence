"""Executa os notebooks (in-place, com saídas). Uso: python scripts/run_notebooks.py [filtro ...]"""
import sys
import time
from pathlib import Path

import nbformat
from nbclient import NotebookClient

NB_DIR = Path(__file__).resolve().parents[1] / "notebooks"


def main(filters):
    ok, fail = [], []
    for p in sorted(NB_DIR.glob("*.ipynb")):
        if filters and not any(f in p.name for f in filters):
            continue
        nb = nbformat.read(p, as_version=4)
        t0 = time.time()
        try:
            NotebookClient(nb, timeout=1800, kernel_name="python3", resources={"metadata": {"path": str(NB_DIR)}}).execute()
            nbformat.write(nb, p)
            ok.append(p.name); print(f"OK    {p.name} ({time.time() - t0:.1f}s)")
        except Exception as e:  # noqa: BLE001
            fail.append(p.name); print(f"FALHA {p.name}: {str(e)[-1500:]}")
    print(f"\n{len(ok)} ok, {len(fail)} falha(s)")
    return 1 if fail else 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
