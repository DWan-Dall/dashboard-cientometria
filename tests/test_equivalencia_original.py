"""Teste de equivalência (golden master): o pacote em modo 'original' deve produzir
EXATAMENTE os mesmos resultados que os scripts originais (referencia/fase2..5),
executados sem modificação sobre as mesmas exportações."""
import io, os, contextlib, pathlib
import numpy as np
import pandas as pd
import pytest
from cientometria import Config, executar, ler_pasta
from .sinteticos import gerar

RAIZ = pathlib.Path(__file__).resolve().parents[1]


def rodar_original(pasta):
    """Executa as fases originais (fase 1 reescrita como no notebook) e devolve o namespace."""
    ns = {"pd": pd, "np": np}
    ns["os"] = os
    cwd = os.getcwd()
    os.chdir(pasta)
    try:
        def carregar(arq):
            try:
                return pd.read_csv(arq)
            except Exception:
                return pd.DataFrame()
        ns.update(lens_en=carregar("lens-export.csv"), lens_pt=carregar("lens-export-port.csv"),
                  scopus_all=carregar("scopus-sem-filtro.csv"), scopus_filtered=carregar("scopus-com-filtro.csv"),
                  scopus_pt=carregar("scopus-port.csv"), ieee=carregar("ieee-export.csv"),
                  scielo_en=carregar("SciELO.csv"), scielo_pt=carregar("SciELO-port.csv"))
        with contextlib.redirect_stdout(io.StringIO()):
            for f in ["fase2_normalizacao", "fase3_filtros", "fase4_escore", "fase5_fascias"]:
                exec(compile((RAIZ / "referencia" / f"{f}.py").read_text(encoding="utf-8"), f, "exec"), ns)
    finally:
        os.chdir(cwd)
    return ns


@pytest.fixture(scope="module")
def ambos(tmp_path_factory):
    pasta = gerar(str(tmp_path_factory.mktemp("bases")))
    ns = rodar_original(pasta)
    res = executar(ler_pasta(pasta), Config.original())
    return ns, res


def test_contagens_do_fluxo(ambos):
    ns, res = ambos
    assert res.contagens["unicos"] == len(ns["df_consolidated"])
    assert res.contagens["corpus"] == len(ns["df_expanded"])
    assert res.contagens["nucleo_obrigatorio"] == len(ns["df_core"])


def test_escore_identico(ambos):
    ns, res = ambos
    o = ns["df_analysis"].reset_index(drop=True)
    p = res.corpus.reset_index(drop=True)
    assert len(o) == len(p) > 50
    for col in ["C_norm", "R_norm", "T_score", "A_score", "score_final_100"]:
        np.testing.assert_allclose(o[col].astype(float), p[col].astype(float), err_msg=col)
    assert list(o["fascia"]) == list(p["fascia"])
    # no original, título ausente vira NaN (desalinhamento de índice); no pacote, 'Unknown'. Mesmo efeito na dedup.
    assert list(o["title"].fillna("Unknown")) == list(p["title"])


def test_estratos_tem_mais_de_uma_classe(ambos):
    _, res = ambos
    assert sum(1 for v in res.estratos().values() if v > 0) >= 2
