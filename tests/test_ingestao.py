"""Ingestão: formatos, identificação da base, entradas incompletas e leitura original."""
import pandas as pd
import pytest

from cientometria import Config, executar
from cientometria.ingestao import carregar_fontes, detectar_tipo, ler_arquivo, ler_bibtex, ler_ris, ler_wos_texto

LINHAS = [
    {"Title": "Flood forecasting with LSTM networks", "Year": 2021, "Abstract": "We use rainfall data and deep learning.",
     "Author Keywords": "flood forecasting; lstm", "DOI": "10.1/a", "Cited by": 10, "Source title": "Water",
     "Authors": "Silva A.; Souza B."},
    {"Title": "Flood susceptibility mapping using random forest", "Year": 2020, "Abstract": "Satellite and GIS in a basin.",
     "Author Keywords": "susceptibility", "DOI": "", "Cited by": 3, "Source title": "Remote Sensing",
     "Authors": "Lee C."},
]


def test_csv_tsv_ponto_e_virgula_xlsx(tmp_path):
    df = pd.DataFrame(LINHAS)
    df.to_csv(tmp_path / "a.csv", index=False)
    df.to_csv(tmp_path / "b.tsv", index=False, sep="\t")
    df.to_csv(tmp_path / "c.txt", index=False, sep=";")
    df.to_excel(tmp_path / "d.xlsx", index=False)
    for nome in ("a.csv", "b.tsv", "c.txt", "d.xlsx"):
        lido, formato, _ = ler_arquivo(tmp_path / nome)
        assert len(lido) == 2, nome
        assert lido.loc[0, "Title"].startswith("Flood forecasting"), nome
        assert int(lido.loc[0, "Cited by"]) == 10, nome


def test_codificacao_latin1_e_linha_malformada(tmp_path):
    p = tmp_path / "x.csv"
    p.write_bytes('Title,Year,DOI\n"Previsão de enchentes",2020,10.1/z\n"ok",2021,10.1/y,EXTRA,EXTRA\n'.encode("latin-1"))
    avisos = []
    df, _, _ = ler_arquivo(p, estrategia="robusta", avisos=avisos)
    assert df.loc[0, "Title"] == "Previsão de enchentes"
    assert any("codificação" in a for a in avisos)
    assert any("malformada" in a for a in avisos)


def test_leitura_original_falha_como_no_original(tmp_path):
    """No modo original, um CSV que pd.read_csv não lê vira base vazia (comportamento de jan/2026)."""
    p = tmp_path / "lens-export.csv"
    p.write_text('Title,DOI\n"a",1\n"b",2,3\n', encoding="utf-8")
    df, _, leitura = ler_arquivo(p, estrategia="original")
    assert len(df) == 0 and leitura.startswith("original")


RIS = """TY  - JOUR
TI  - Deep learning for flood prediction
AU  - Silva, A.
AU  - Souza, B.
PY  - 2022/03/01
AB  - Rainfall and LSTM.
KW  - flood prediction
KW  - lstm
DO  - 10.5/RIS1
JO  - Journal of Hydrology
ER  -
TY  - JOUR
TI  - Second record without DOI
PY  - 2019
ER  -
"""

BIB = """@article{k1,
  title = {Flood {Forecasting} with {CNN}},
  author = {Silva, Ana and Souza, Bruno},
  year = {2023},
  journal = "Water",
  doi = {10.9/BIB1},
  keywords = {flood forecasting; cnn},
  abstract = {Using satellite data, {nested} braces.},
  note = {Cited by: 12}
}
@inproceedings{k2,
  title = "Another one",
  year = 2018,
  booktitle = {Conf}
}
"""

WOS = """FN Clarivate Analytics Web of Science
VR 1.0
PT J
AU Silva, A
   Souza, B
TI Flood forecasting using machine
   learning
SO WATER
DE flood; machine learning
AB Rainfall based model.
C1 [Silva, A] Univ Sao Paulo, Sao Paulo, Brazil.
CR Mosavi A, 2018, WATER, V10, P1536, DOI 10.3390/w10111536
TC 5
PY 2020
DI 10.1/WOS1
UT WOS:000000001
ER

EF
"""


def test_ris_bibtex_wos(tmp_path):
    (tmp_path / "x.ris").write_text(RIS, encoding="utf-8")
    (tmp_path / "x.bib").write_text(BIB, encoding="utf-8")
    (tmp_path / "x.txt").write_text(WOS, encoding="utf-8")
    r = ler_ris(tmp_path / "x.ris")
    assert len(r) == 2 and r.loc[0, "DOI"] == "10.5/RIS1" and r.loc[0, "Year"] == 2022
    assert r.loc[0, "Authors"] == "Silva, A.; Souza, B." and r.loc[0, "Author Keywords"] == "flood prediction; lstm"
    b = ler_bibtex(tmp_path / "x.bib")
    assert len(b) == 2 and b.loc[0, "Title"] == "Flood Forecasting with CNN"
    assert b.loc[0, "Authors"] == "Silva, Ana; Souza, Bruno" and b.loc[1, "Year"] == 2018
    assert b.loc[0, "DOI"] == "10.9/BIB1" and "nested" in b.loc[0, "Abstract"]
    w = ler_wos_texto(tmp_path / "x.txt")
    assert len(w) == 1 and w.loc[0, "TI"] == "Flood forecasting using machine learning"
    assert w.loc[0, "AU"] == "Silva, A; Souza, B" and w.loc[0, "DI"] == "10.1/WOS1"
    # os três chegam ao corpus pela triagem com o mapeamento de extensão
    bases, fontes = carregar_fontes([tmp_path / "x.ris", tmp_path / "x.bib", tmp_path / "x.txt"], Config.corrigida())
    assert [f.tipo for f in fontes] == ["ris", "bibtex", "wos"]
    res = executar(bases, Config.corrigida())
    assert res.contagens["registros"] == 5
    assert set(res.bruto["title"]) >= {"Deep learning for flood prediction", "Flood Forecasting with CNN"}


@pytest.mark.parametrize("colunas,esperado", [
    (["Lens ID", "Title", "Citing Works Count"], "lens"),
    (["Authors", "Title", "Year", "Source title", "Cited by", "Link", "EID"], "scopus"),
    (["Document Title", "Authors", "Article Citation Count", "IEEE Terms"], "ieee"),
    (["PT", "AU", "TI", "SO", "PY", "UT"], "wos"),
    (["id", "display_name", "publication_year", "cited_by_count", "doi"], "openalex"),
    (["Título", "Resumo", "Ano"], "scielo"),
    (["qualquer", "coisa"], "generico"),
])
def test_deteccao_por_colunas(colunas, esperado):
    assert detectar_tipo(pd.DataFrame(columns=colunas), "exportacao.csv")[0] == esperado


def test_entradas_incompletas(tmp_path):
    """Sem DOI, sem título, sem resumo, arquivo vazio: nada quebra e tudo é diagnosticado."""
    pd.DataFrame({"Title": ["Flood forecasting with LSTM and rainfall"], "Year": [2020]}).to_csv(tmp_path / "a.csv", index=False)
    pd.DataFrame({"Abstract": ["flood prediction with deep learning and satellite"], "DOI": ["10.1/q"]}).to_csv(
        tmp_path / "b.csv", index=False)
    (tmp_path / "c.csv").write_text("", encoding="utf-8")
    for cfg in (Config.original(), Config.corrigida()):
        bases, fontes = carregar_fontes(sorted(tmp_path.glob("*.csv")), cfg)
        assert any("vazio" in " ".join(f.avisos) for f in fontes)
        res = executar(bases, cfg)
        assert res.contagens["registros"] == 2
        if cfg.manter_sem_doi:
            assert res.contagens["unicos"] == 2
        else:  # original: o registro sem DOI é descartado
            assert res.contagens["unicos"] == 1 and res.contagens["sem_doi"] == 1


def test_todos_vazios_da_erro_claro(tmp_path):
    (tmp_path / "c.csv").write_text("", encoding="utf-8")
    bases, _ = carregar_fontes([tmp_path / "c.csv"], Config.original())
    with pytest.raises(ValueError, match="Nenhum registro"):
        executar(bases, Config.original())
