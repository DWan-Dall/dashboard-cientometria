"""Equivalência pacote × scripts originais quando há títulos ausentes de DOIS tipos (achado 11).

Com as exportações reais de jan/2026 o pacote dava 11.546 únicos e os scripts 11.547: a IEEE não
tem coluna 'Title' (no script vira NaN) e alguns registros de outras bases têm título vazio (no
script vira 'Unknown'). São grupos distintos na deduplicação por título. Os dados sintéticos do
teste de equivalência original só tinham o primeiro caso, por isso a diferença passou despercebida.
Este teste não depende do número do artigo: a referência é o comportamento dos scripts."""
import pathlib

import numpy as np
import pandas as pd
import pytest

from cientometria import Config, executar, ler_pasta
from .sinteticos import gerar
from .test_equivalencia_original import rodar_original


@pytest.fixture(scope="module")
def ambos(tmp_path_factory):
    pasta = gerar(str(tmp_path_factory.mktemp("t")))
    for arq, linhas in [("lens-export.csv", [3, 10, 25, 40]), ("scopus-sem-filtro.csv", [7, 8])]:
        p = pathlib.Path(pasta) / arq
        df = pd.read_csv(p)
        df.loc[linhas, "Title"] = np.nan
        df.to_csv(p, index=False)
    return rodar_original(pasta), executar(ler_pasta(pasta), Config.original()), pasta


def test_titulos_ausentes_de_dois_tipos_nao_se_fundem(ambos):
    ns, res, _ = ambos
    t = ns["df_consolidated"]["title"]
    assert t.isna().sum() == 1 and (t == "Unknown").sum() == 1          # o que o script original faz
    assert res.contagens["unicos"] == len(ns["df_consolidated"])
    assert res.contagens["removidos_titulo"] == res.contagens["apos_doi"] - len(ns["df_consolidated"])
    assert res.contagens["corpus"] == len(ns["df_expanded"])


def test_escore_identico_com_titulos_ausentes(ambos):
    ns, res, _ = ambos
    o, p = ns["df_analysis"].reset_index(drop=True), res.corpus.reset_index(drop=True)
    assert len(o) == len(p)
    for col in ["C_norm", "R_norm", "T_score", "A_score", "score_final_100"]:
        np.testing.assert_allclose(o[col].astype(float), p[col].astype(float), err_msg=col)
    assert list(o["fascia"]) == list(p["fascia"])


def test_variante_herda_a_correcao(ambos):
    _, orig, pasta = ambos
    var = executar(ler_pasta(pasta), Config.variante_exclusao())
    assert var.contagens["unicos"] == orig.contagens["unicos"]
