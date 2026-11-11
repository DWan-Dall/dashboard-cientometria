"""Comparação com os resultados ORIGINAIS do R (analise-aprofundada-v3, cientometria_master.R v2.3).

Requer dados não versionados:
  CIENTOMETRIA_CORPUS_PUBLICADO=/…/dados/DB_Cientometria_COMPLETA.csv   (o CSV que o R leu)
  CIENTOMETRIA_RESULTADOS_R=/…/resultados_cientometria

Duas camadas:
1. `compat_r` (réplica das regras do R) deve reproduzir os CSVs do R EXATAMENTE — prova
   que o porte entendeu cada regra.
2. `bibliometria` (padrão da plataforma) difere do R só onde a definição foi mudada de
   propósito; cada diferença é verificada aqui e documentada em MIGRATION.md.

Co-citação, acoplamento e áreas temáticas NÃO podem ser comparados: o corpus publicado
não tem referências citadas nem área temática, e o R não calculou essas análises.
"""
import os
import pathlib

import numpy as np
import pandas as pd
import pytest

from cientometria import bibliometria as B
from cientometria import compat_r as C
from cientometria.consolidacao import sobreposicao

CORPUS = os.environ.get("CIENTOMETRIA_CORPUS_PUBLICADO")
RES = os.environ.get("CIENTOMETRIA_RESULTADOS_R")
pytestmark = pytest.mark.skipif(not (CORPUS and RES and CORPUS.lower().endswith(".csv")),
                                reason="defina CIENTOMETRIA_CORPUS_PUBLICADO (.csv) e CIENTOMETRIA_RESULTADOS_R")


@pytest.fixture(scope="module")
def bruto():
    return pd.read_csv(CORPUS)


@pytest.fixture(scope="module")
def d(bruto):
    return C.preparar(bruto)


def r(caminho):
    return pd.read_csv(pathlib.Path(RES) / caminho)


def contagens_iguais(py, rr, chave, valor="n"):
    a, b = dict(zip(py[chave], py[valor])), dict(zip(rr[chave], rr[valor]))
    assert a == b, {k: (a.get(k), b.get(k)) for k in set(a) | set(b) if a.get(k) != b.get(k)}


def pares(df, a, b, n):
    return {frozenset((x, y)): v for x, y, v in df[[a, b, n]].itertuples(index=False)}


# ------------------------------------------------------------ 1. réplica exata do R
def test_r_bases(d):
    contagens_iguais(C.bases(d), r("02_bases/01-registros-por-base.csv"), "base")


def test_r_areas_sao_estratos(d):
    contagens_iguais(C.areas(d), r("03_areas/01-frequencia-areas.csv"), "fascia")


def test_r_periodicos(d):
    contagens_iguais(C.periodicos(d), r("04_periodicos/01-ranking-periodicos.csv"), "journal_consolidado")


def test_r_paises(d):
    contagens_iguais(C.paises(d), r("05_paises/01-publicacoes-por-pais.csv"), "country")


def test_r_autores_e_coautoria(d):
    contagens_iguais(C.autores(d), r("06_coautoria/02-frequencia-autores.csv"), "author")
    assert pares(C.coautoria(d), "author_1", "author_2", "peso") == pares(
        r("06_coautoria/03-arestas-coautoria.csv"), "author_1", "author_2", "peso")
    forte = r("06_coautoria/06-arestas-coautoria-peso-min-2.csv")
    assert (C.coautoria(d)["peso"] >= 2).sum() == len(forte) == 1582
    resumo = dict(r("06_coautoria/08-resumo-coautoria.csv").values)
    assert resumo["Autores únicos"] == len(C.autores(d)) and resumo["Arestas totais"] == len(C.coautoria(d))


def test_r_palavras_chave_coocorrencia_e_clusters(d):
    kw = C.palavras_chave(d)
    assert kw["fonte"] == "technologies"          # author/index_keywords vazias no corpus publicado
    contagens_iguais(kw["frequencia"], r("07_palavras_chave/01-frequencia-palavras-chave.csv"), "keyword")
    assert pares(kw["arestas"], "keyword_1", "keyword_2", "n") == pares(
        r("07_palavras_chave/03-rede-coocorrencia-arestas.csv"), "keyword_1", "keyword_2", "n")
    cl, rcl = C.clusters(kw["arestas"]), r("08_estrutura_tematica/01-clusters-termos.csv")
    assert set(cl["keyword"]) == set(rcl["keyword"]) and cl["cluster"].nunique() == rcl["cluster"].nunique() == 1


@pytest.mark.parametrize("arquivo,coluna,nossa", [("01-artigos-por-ano", "n_artigos", "n_artigos"),
                                                   ("02-citacoes-por-ano", "total_citacoes", "total_citacoes"),
                                                   ("03-media-citacoes-por-ano", "media_citacoes", "media_citacoes")])
def test_r_series_temporais(d, arquivo, coluna, nossa):
    rr, s = r(f"09_series_temporais/{arquivo}.csv"), C.series(d)
    assert list(rr["year"]) == list(s["year"])
    np.testing.assert_allclose(rr[coluna].astype(float), s[nossa].astype(float), equal_nan=True)


def test_r_scores_por_ano_usaram_o_A_corrompido(d):
    rr = r("10_scores/01-scores-medios-por-ano.csv")
    m = rr.merge(C.scores(d), on=["year", "score"], suffixes=("_r", "_py"))
    assert len(m) == len(rr) == 140
    np.testing.assert_allclose(m["media_r"], m["media_py"])
    a = m[m["score"] == "A"]
    assert a["media_r"].max() > 1          # médias de A* > 1: o R leu 875/625 (separador decimal)


def test_r_tecnologias_por_ano(d):
    rr = r("11_tecnologias/01-frequencia-tecnologias-por-ano.csv")
    m = rr.merge(C.tecnologias(d), on=["year", "categoria"], suffixes=("_r", "_py"))
    assert len(m) == len(rr) and (m["frequencia_r"] == m["frequencia_py"]).all()


def test_r_sobreposicao(d):
    so = C.sobreposicao(d)
    assert pares(so["matriz"], "base_1", "base_2", "n_compartilhados") == pares(
        r("12_sobreposicao_bases/01-matriz-sobreposicao-bases.csv"), "base_1", "base_2", "n_compartilhados")
    contagens_iguais(so["por_numero_de_bases"], r("12_sobreposicao_bases/06-resumo-artigos-por-numero-de-bases.csv"),
                     "n_bases", "n_artigos")


# ------------------------------------------------------------ 2. padrão da plataforma × R
def test_padrao_coautoria_igual_ao_r(bruto):
    """Separador ',' (detectado) e mesmas arestas; autores únicos difere em 1 (ponto final removido)."""
    c = B.coautoria(bruto)
    assert len(c["arestas"]) == 19628 and int((c["arestas"]["peso"] >= 2).sum()) == 1582
    assert B.autores(bruto)["resumo"]["autores_unicos"].iloc[0] == 6758


def test_padrao_producao_anual_difere_so_nos_anos_vazios(bruto):
    p, rr = B.producao_anual(bruto), r("09_series_temporais/01-artigos-por-ano.csv")
    m = rr.merge(p, left_on="year", right_on="ano")
    assert (m["n_artigos"].fillna(0) == m["n_documentos"]).all()        # NA no R = 0 aqui
    assert m["n_artigos"].isna().sum() == (m["n_documentos"] == 0).sum() == 9


def test_padrao_periodicos_difere_so_por_caixa(bruto):
    """O padrão agrupa variações de caixa ('Journal of …' × 'Journal Of …')."""
    df = bruto.rename(columns={"journal_consolidado": "source"})
    p = B.periodicos(df)
    rr = r("04_periodicos/01-ranking-periodicos.csv")
    assert p["n_documentos"].sum() == rr["n"].sum()
    agr = rr.assign(k=rr["journal_consolidado"].map(lambda x: C.squish(x).lower())).groupby("k")["n"].sum()
    assert sorted(agr.values) == sorted(p["n_documentos"].values)


def test_padrao_paises_conta_documentos_e_normaliza_nomes(bruto):
    """R conta afiliações; o padrão conta cada país uma vez por documento e unifica nomes (USA→United States)."""
    p = dict(zip(*B.paises(bruto)[["pais", "n_documentos"]].values.T))
    rr = dict(r("05_paises/01-publicacoes-por-pais.csv").values)
    assert rr["China"] == 364 and p["China"] < rr["China"]                 # documento ≤ afiliações
    assert "USA" in rr and "United States" in p and "USA" not in p
    assert sum(p.values()) < sum(rr.values())


def test_padrao_tecnologias_mesmas_mencoes(bruto):
    t = B.tecnologias(bruto)
    rr = r("11_tecnologias/01-frequencia-tecnologias-por-ano.csv")
    tot_r = rr.groupby("categoria")["frequencia"].sum()
    tot_py = t["por_ano"].drop(columns="ano").sum()
    # o padrão deduplica tecnologias repetidas no mesmo registro; o R não
    for cat in tot_r.index:
        assert tot_py[cat] <= tot_r[cat]
    assert (tot_r - tot_py).abs().sum() / tot_r.sum() < 0.01


def test_padrao_sobreposicao_igual_ao_r(bruto):
    linhas = []
    for _, x in bruto.iterrows():
        for b in str(x["source_database"]).split(";"):
            linhas.append({"title": x["title"], "doi": x["doi"], "source_db": b.strip()})
    m = sobreposicao(pd.DataFrame(linhas))["matriz"].set_index("base")
    rr = r("12_sobreposicao_bases/01-matriz-sobreposicao-bases.csv")
    for b1, b2, n in rr.values:
        assert m.loc[b1, b2] == n, (b1, b2)


def test_padrao_scores_com_A_correto_difere_do_r_so_em_A(bruto):
    rr = r("10_scores/01-scores-medios-por-ano.csv").pivot(index="year", columns="score", values="media")
    corrigido = bruto.assign(A_score=bruto["A_score"].where(bruto["A_score"] <= 1, bruto["A_score"] / 1000))
    s = B.scores_por_ano(corrigido).set_index("ano")
    comuns = s.index.intersection(rr.index)
    for col, letra in [("C_norm", "C"), ("R_norm", "R"), ("T_score", "T")]:
        np.testing.assert_allclose(s.loc[comuns, col], rr.loc[comuns, letra], atol=1e-4)
    assert (s.loc[comuns, "A_score"] <= 1).all() and (rr.loc[comuns, "A"] > 1).any()


def test_analises_sem_dados_no_corpus_publicado(bruto):
    cob = B.analisar(bruto.rename(columns={"journal_consolidado": "source"}))["cobertura"].set_index("analise")
    for a in ("cocitacao", "acoplamento", "areas"):
        assert cob.loc[a, "executada"] == "não"
