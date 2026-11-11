"""Auditoria dos resultados de uma execução (docs/AUDITORIA_RESULTADOS_BIBLIOMETRICOS.md).

Parte A — invariantes de uma execução exportada (pasta `relatorios/` + `relatorio_metodologico.md`).
Ative com CIENTOMETRIA_RESULTADOS_EXECUCAO=/caminho/da/pasta. Não versione essa pasta (corpus derivado
de exportações licenciadas).

Parte B — defeitos confirmados na auditoria da execução 052b2a400fc1, registrados como xfail ESTRITO:
o teste descreve o comportamento correto e falha hoje; quando o defeito for corrigido o xfail passa a
"XPASS" e o CI acusa, para que o teste seja promovido a teste normal. Nenhum deles altera o método
original-2026.01: todos tratam das análises bibliométricas descritivas.
"""
import json
import os
import pathlib
import re

import numpy as np
import pandas as pd
import pytest

from cientometria import Config, bibliometria as B
from cientometria.entrada import normalizar_estendido
from cientometria.manifesto import hash_tabela
from cientometria.nucleo import classificar

PASTA = os.environ.get("CIENTOMETRIA_RESULTADOS_EXECUCAO")
ORDEM = ["lens-export.csv", "lens-export-port.csv", "scopus-sem-filtro.csv", "scopus-com-filtro.csv",
         "scopus-port.csv", "ieee-export.csv", "SciELO.csv", "SciELO-port.csv"]
precisa_execucao = pytest.mark.skipif(not PASTA, reason="defina CIENTOMETRIA_RESULTADOS_EXECUCAO")


def _csv(nome, **kw):
    return pd.read_csv(pathlib.Path(PASTA) / f"{nome}.csv", keep_default_na=False, na_values=[""], **kw)


@pytest.fixture(scope="module")
def corpus():
    return pd.read_csv(pathlib.Path(PASTA) / "corpus.csv")


# =============================================================== Parte A — invariantes
@precisa_execucao
def test_corpus_pertence_a_execucao(corpus):
    """O hash recalculado do corpus exportado coincide com o registrado no relatório metodológico."""
    md = (pathlib.Path(PASTA) / "relatorio_metodologico.md").read_text(encoding="utf-8")
    esperado = re.search(r"Hash do corpus: `([0-9a-f]{64})`", md).group(1)
    p = json.loads((pathlib.Path(PASTA) / "parametros.json").read_text(encoding="utf-8"))
    c = pd.read_csv(pathlib.Path(PASTA) / "corpus.csv", keep_default_na=False, dtype=str)
    for col in ["year", "citations", "C_norm", "R_norm", "T_score", "A_score", "score_final_100", "linha_origem"]:
        c[col] = pd.to_numeric(c[col], errors="coerce")
    c["title"] = c["title"].str.replace(r"^'(?=[=+\-@])", "", regex=True)       # desfaz a neutralização de fórmulas
    c = c.assign(_o=c["arquivo_origem"].map(ORDEM.index)).sort_values(["_o", "linha_origem"]).reset_index(drop=True)
    w = p["pesos"]
    c["score_final"] = w[0] * c.C_norm + w[1] * c.R_norm + w[2] * c.T_score + w[3] * c.A_score
    assert hash_tabela(c) == esperado


@precisa_execucao
def test_triagem_internamente_consistente(corpus):
    k = _csv("contagens").iloc[0]
    assert k.registros - k.removidos_etapa_doi == k.apos_doi and k.apos_doi - k.removidos_titulo == k.unicos
    assert k.sem_doi + k.duplicatas_doi == k.removidos_etapa_doi and k.corpus == len(corpus)
    c = corpus
    assert np.allclose((c.citations - c.citations.min()) / (c.citations.max() - c.citations.min()), c.C_norm)
    y = c.year
    assert np.allclose(y.apply(lambda v: (v - y.min()) / (y.max() - y.min()) if pd.notna(v) else 0), c.R_norm)
    s = .35 * c.C_norm + .2 * c.R_norm + .3 * c.T_score + .15 * c.A_score
    assert ((((s - s.min()) / (s.max() - s.min()) * 100).round(2) - c.score_final_100).abs() <= 0.011).all()
    assert (classificar(c.score_final_100, Config.original()) == c.fascia).all()
    assert _csv("estratos").iloc[0].to_dict() == c.fascia.value_counts().to_dict()
    assert set(_csv("nucleo_a").doi) == set(c[c.fascia == "Núcleo A"].doi)


@precisa_execucao
def test_producao_anual_e_escores_por_ano(corpus):
    pa = _csv("bib_producao_anual")
    assert pa.n_documentos.sum() + corpus.year.isna().sum() == len(corpus)   # sem ano ficam fora da série
    por_ano = corpus.dropna(subset=["year"]).groupby(corpus.year.dropna().astype(int))
    m = pa.set_index("ano").join(por_ano.agg(n=("year", "size"), cit=("citations", "sum")), how="left").fillna(0)
    assert (m.n_documentos == m.n).all() and (m.citacoes_total == m.cit).all()
    sc = _csv("bib_scores_por_ano").set_index("ano")
    rec = corpus.dropna(subset=["year"]).assign(ano=lambda x: x.year.astype(int)).groupby("ano")[sc.columns].mean().round(4)
    assert np.allclose(sc.values, rec.loc[sc.index].values)


@precisa_execucao
def test_periodicos_e_bradford(corpus):
    pe = _csv("bib_periodicos")
    src = corpus.source.dropna()
    src = src[~src.str.lower().isin(["", "unknown", "nan"])]
    assert pe.n_documentos.sum() == len(src)
    assert ((pe.n_documentos.cumsum() / pe.n_documentos.sum() * 100).round(1) == pe.pct_acumulado).all()


@precisa_execucao
def test_redes_coerentes():
    import networkx as nx
    ed, no = _csv("bib_coautoria_arestas"), _csv("bib_coautoria_nos")
    g = nx.Graph()
    g.add_weighted_edges_from(ed.itertuples(index=False))
    n = no.set_index("autor")
    assert len(no) == g.number_of_nodes() and all(n.grau[k] == v for k, v in g.degree())
    assert (ed.autor_1 < ed.autor_2).all()
    assert no.intermediacao_nucleo.notna().sum() <= 60                     # só o núcleo (top 60) tem intermediação
    fq = _csv("bib_coocorrencia_frequencia")
    f = dict(zip(fq.termo, fq.n_documentos))
    ce = _csv("bib_coocorrencia_arestas")
    assert all(w <= min(f[a], f[b]) for a, b, w in ce.itertuples(index=False))
    rf = _csv("bib_cocitacao_referencias_mais_citadas", dtype={"referencia": str})
    fr = dict(zip(rf.referencia, rf.n_documentos))
    cc = _csv("bib_cocitacao_arestas", dtype={"ref_1": str, "ref_2": str})
    assert all(w <= min(fr[a], fr[b]) for a, b, w in cc.itertuples(index=False))


@precisa_execucao
def test_mapa_tematico_recalculado():
    import networkx as nx
    ed, cl, mp = _csv("bib_coocorrencia_arestas"), _csv("bib_coocorrencia_clusters"), _csv("bib_coocorrencia_mapa_tematico")
    g = nx.Graph()
    g.add_weighted_edges_from(ed.itertuples(index=False))
    for k, gr in cl.groupby("cluster"):
        M = set(gr.termo)
        dentro = [d["weight"] for u, v, d in g.edges(M, data=True) if u in M and v in M]
        fora = [d["weight"] for u, v, d in g.edges(M, data=True) if (u in M) != (v in M)]
        linha = mp[mp.cluster == k].iloc[0]
        assert linha.centralidade == sum(fora) and abs(linha.densidade - (np.mean(dentro) if dentro else 0)) < 1e-9


@precisa_execucao
def test_tecnologias_denominadores():
    """Frequência = documentos com a tecnologia (pode somar mais que o corpus);
    percentual anual = menções da categoria / menções do ano (não documentos)."""
    ta, tp = _csv("bib_tecnologias_por_ano"), _csv("bib_tecnologias_percentual_por_ano")
    cats = [c for c in ta.columns if c != "ano"]
    den = ta[cats].sum(axis=1)
    rec = ta[cats].div(den.replace(0, np.nan), axis=0).fillna(0).mul(100).round(2)
    assert np.allclose(rec.values, tp[cats].values)


@precisa_execucao
def test_sobreposicao_coerente():
    m = _csv("bib_sobreposicao_bases_matriz").set_index("base")
    n = _csv("bib_sobreposicao_bases_por_numero_de_bases")
    assert (m.values == m.values.T).all()
    assert np.trace(m.values) == (n.n_bases * n.n_obras).sum()            # cada obra conta uma vez por base


@precisa_execucao
def test_xlsx_igual_aos_csv():
    x = pd.ExcelFile(pathlib.Path(PASTA) / "resultados.xlsx")
    for aba in x.sheet_names:
        nome = next((p.stem for p in pathlib.Path(PASTA).glob("*.csv") if p.stem[:31] == aba and "(" not in p.stem), None)
        assert nome, aba
        pd.testing.assert_frame_equal(pd.read_excel(x, aba, keep_default_na=False, na_values=[""]), _csv(nome),
                                      check_dtype=False, check_exact=False, rtol=1e-9)


# =============================================================== Parte B — defeitos confirmados
@pytest.mark.xfail(strict=True, raises=AssertionError, reason="AR-01: coluna de autores da Lens ('Author/s') não está nos aliases; "
                                       "na execução 052b2a400fc1 os 1.604 documentos de origem Lens ficaram sem autor")
def test_autores_da_lens_sao_lidos():
    lens = pd.DataFrame({"Lens ID": ["1"], "Title": ["Flood forecasting"], "Author/s": ["Ana Silva; Bruno Souza"]})
    assert normalizar_estendido(lens, "Lens (EN)", "lens")["authors"].notna().all()


@pytest.mark.xfail(strict=True, raises=AssertionError, reason="AR-02: marcadores 'null'/'undefined' das exportações viram autor/referência")
def test_marcadores_de_ausencia_nao_viram_entidades():
    df = pd.DataFrame({"authors": ["Silva, A.; null; Souza, B.", "null; Lee, C."],
                       "references": ["undefined; Ref A 2018", "undefined; Ref B 2019"], "title": ["a", "b"]})
    autores = set(B.autores(df)["frequencia"].autor)
    refs = set(B.cocitacao(df, min_citacoes=1)["referencias_mais_citadas"].referencia)
    assert "null" not in autores and "undefined" not in refs


@pytest.mark.xfail(strict=True, raises=AssertionError, reason="AR-03: acoplamento identifica documentos pelos 80 primeiros caracteres do "
                                       "título; títulos com o mesmo prefixo se fundem e geram auto-laços")
def test_acoplamento_usa_identificador_unico():
    base = "A" * 80
    df = pd.DataFrame({"title": [base + " versão 1", base + " versão 2"], "references": ["R1; R2", "R1; R2"]})
    ar = B.acoplamento(df)["arestas"]
    assert len(ar) == 1 and (ar.doc_1 != ar.doc_2).all()


@pytest.mark.xfail(strict=True, raises=AssertionError, reason="AR-04: dicionário de tecnologias casa a palavra comum 'attention' "
                                       "(135 documentos marcados como Attention; 8 títulos citam o mecanismo)")
def test_tecnologia_attention_exige_mecanismo():
    df = pd.DataFrame({"title": ["Floods have attracted attention"], "abstract": [""], "keywords": [""], "year": [2020]})
    assert "Attention" not in B.detectar_tecnologias(df).iloc[0]


@pytest.mark.xfail(strict=True, raises=AssertionError, reason="AR-05: ano sem nenhuma menção aparece como 0% em todas as categorias "
                                       "(deveria ser ausente; 0/0 não é 0%)")
def test_percentual_de_ano_sem_mencoes_e_ausente():
    df = pd.DataFrame({"title": ["LSTM model", "No technique here", "CNN model"], "year": [2000, 2001, 2002],
                       "abstract": ["", "", ""], "keywords": ["", "", ""]})
    pct = B.tecnologias(df)["percentual_por_ano"].set_index("ano")
    assert pct.loc[2001].isna().all()


@pytest.mark.xfail(strict=True, raises=AssertionError, reason="AR-06: 'cobertura' informa só se a análise rodou, não quantos documentos "
                                       "do corpus têm o campo (autores: 463/2.068 apareceu como 'sim')")
def test_cobertura_informa_documentos_com_o_campo():
    df = pd.DataFrame({"title": ["a", "b", "c"], "year": [2020, 2021, 2022], "authors": ["X; Y", None, None]})
    cob = B.analisar(df)["cobertura"]
    assert "documentos_com_campo" in cob.columns
