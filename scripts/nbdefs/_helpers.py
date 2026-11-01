"""Helpers para construir notebooks com nbformat."""
import nbformat as nbf

SETUP = '''import warnings
warnings.filterwarnings("ignore")

import numpy as np
import pandas as pd
import matplotlib.pyplot as plt

from coffeebdi import config, silver, modeling as M, quality
from coffeebdi.lake import Lake
from coffeebdi.nbutils import duck, mpl_style

pd.set_option("display.width", 200); pd.set_option("display.max_columns", 40); pd.set_option("display.float_format", "{:,.2f}".format)
mpl_style()
lake = Lake()
con = duck(lake)
def q(sql):
    """Executa SQL (DuckDB) sobre as tabelas silver/gold e devolve DataFrame."""
    return con.execute(sql).df()
FIG = config.OUTPUTS / "figures"'''


class NB:
    def __init__(self):
        self.nb = nbf.v4.new_notebook()
        self.nb.metadata["kernelspec"] = {"display_name": "Python 3", "language": "python", "name": "python3"}

    def md(self, text):
        self.nb.cells.append(nbf.v4.new_markdown_cell(text.strip("\n")))
        return self

    def code(self, text):
        self.nb.cells.append(nbf.v4.new_code_cell(text.strip("\n")))
        return self

    def save(self, path):
        nbf.write(self.nb, path)
