"""Gera exportações SINTÉTICAS (não são dados reais) com as colunas dos arquivos originais.
Servem para testar o código sem redistribuir exportações licenciadas."""
import os
import numpy as np
import pandas as pd

TEMAS = ["flood prediction", "flood forecasting", "flooding", "flood risk", "enchentes", "flood susceptibility"]
METODOS = ["machine learning", "LSTM", "random forest", "deep learning", "CNN", "neural network", "ensemble", "regression"]
DADOS = ["rainfall", "satellite", "river discharge", "remote sensing", "water level", "DEM", "sentinel", "tabular"]
RUIDO = ["damage assessment", "dam break", "flood insurance", "levee design", "urban planning", "flood myth", "soil", "economy"]
CTX = ["urban", "coastal", "basin", "city", "mountain"]
SAIDA = ["prediction", "mapping", "early warning", "assessment", "classification"]


def _linha(rng, i, prefixo):
    t, m, d, r, c, s = (rng.choice(x) for x in (TEMAS, METODOS, DADOS, RUIDO, CTX, SAIDA))
    titulo = f"{s.title()} of {t} using {m} {i % 97} {prefixo}" if rng.random() < .6 else f"{t.title()} study {i} {prefixo}"
    resumo = f"We study {t} with {m} and {d} in a {c} area. Related: {r}." if rng.random() < .8 else ""
    kw = f"{t}; {m}; {d}" if rng.random() < .7 else ""
    doi = f"10.{1000 + (i % 40)}/x{i % 300}" if rng.random() < .85 else ""
    return titulo, resumo, kw, doi, int(rng.integers(1992, 2027)), int(rng.pareto(1.2) * 3)


def gerar(pasta, n=300, seed=7):
    rng = np.random.default_rng(seed)
    os.makedirs(pasta, exist_ok=True)

    def df_de(prefixo, cols, k):
        L = [_linha(rng, int(rng.integers(0, 4000)), prefixo) for _ in range(k)]
        T, R, K, D, Y, C = zip(*L)
        data = {cols["title"]: T, cols["year"]: Y, cols["abstract"]: R, cols["doi"]: D}
        if cols.get("keywords"):
            data[cols["keywords"]] = K
        if cols.get("citations"):
            data[cols["citations"]] = C
        return pd.DataFrame(data)

    lens = dict(title="Title", year="Publication Year", abstract="Abstract", keywords="Keywords",
                citations="Citing Works Count", doi="DOI")
    scop = dict(title="Title", year="Year", abstract="Abstract", citations="Cited by", doi="DOI")  # sem 'Keywords'
    ieee = dict(title="Document Title", year="Publication Year", abstract="Abstract",
                keywords="Author Keywords", citations="Article Citation Count", doi="DOI")  # colunas reais do IEEE
    scie = dict(title="Título", year="Ano", abstract="Resumo", doi="DOI")
    arquivos = {
        "lens-export.csv": (lens, n), "lens-export-port.csv": (lens, n // 10),
        "scopus-sem-filtro.csv": (scop, n), "scopus-com-filtro.csv": (scop, n // 2),
        "scopus-port.csv": (scop, n // 10), "ieee-export.csv": (ieee, n // 3),
        "SciELO.csv": (scie, 5), "SciELO-port.csv": (scie, 8),
    }
    for arq, (cols, k) in arquivos.items():
        df_de(arq[:4], cols, k).to_csv(os.path.join(pasta, arq), index=False)
    return pasta
