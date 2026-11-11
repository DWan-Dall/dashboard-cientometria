"""Análises bibliométricas sobre um conjunto pequeno com resultado conhecido."""
import pandas as pd

from cientometria import bibliometria as B

DF = pd.DataFrame({
    "title": ["A flood LSTM", "B random forest flood", "C CNN", "D no tech"],
    "abstract": ["deep learning", "", "convolutional", ""],
    "keywords": ["", "", "", ""],
    "year": [2020, 2020, 2022, None],
    "citations": [10, 0, 5, 1],
    "source": ["Water", "water", "Journal of Hydrology", None],
    "authors": ["Silva, A.; Souza, B.", "Silva, A.; Lee, C.", "Lee, C.", None],
    "affiliations": ["Univ Sao Paulo, Sao Paulo, Brazil; MIT, Cambridge, USA", "Univ X, Seoul, South Korea", None, None],
    "author_keywords": ["Flood; LSTM", "flood; random forest", "flood; lstm", None],
    "references": ["Ref One 2018, DOI 10.1000/r1; Ref Two 2019", "Ref One 2018, DOI 10.1000/R1; Ref Three", "Ref Two 2019", None],
    "subject_area": ["Water Science; Engineering", "Engineering", None, None],
    "fascia": ["Núcleo A", "Núcleo B", "Periférico", "Descarte"],
})


def test_producao_anual_completa_anos():
    p = B.producao_anual(DF)
    assert list(p["ano"]) == [2020, 2021, 2022] and list(p["n_documentos"]) == [2, 0, 1]


def test_autores_usam_ponto_e_virgula():
    a = B.autores(DF)
    assert a["resumo"]["autores_unicos"].iloc[0] == 3 and a["resumo"]["separador"].iloc[0] == ";"
    assert dict(zip(a["frequencia"].autor, a["frequencia"].n_documentos))["Silva, A"] == 2


def test_coautoria():
    c = B.coautoria(DF)
    pares = {(r.autor_1, r.autor_2): r.peso for r in c["arestas"].itertuples()}
    assert pares == {("Silva, A", "Souza, B"): 1, ("Lee, C", "Silva, A"): 1}


def test_paises_e_periodicos():
    p = dict(zip(*B.paises(DF)[["pais", "n_documentos"]].values.T))
    assert p == {"Brazil": 1, "United States": 1, "South Korea": 1}
    per = B.periodicos(DF)
    assert per.iloc[0]["periodico"] == "Water" and per.iloc[0]["n_documentos"] == 2


def test_areas_nao_sao_estratos():
    assert set(B.areas(DF)["area"]) == {"Water Science", "Engineering"}
    assert set(B.estratos(DF)["estrato"]) == {"Núcleo A", "Núcleo B", "Periférico", "Descarte"}


def test_coocorrencia_cocitacao_acoplamento():
    k = B.coocorrencia(DF, min_freq=1, min_peso=1)
    pares = {(r.termo_1, r.termo_2): r.peso for r in k["arestas"].itertuples()}
    assert pares[("flood", "lstm")] == 2            # caixa normalizada
    assert set(k["clusters"]["termo"]) == {"flood", "lstm", "random forest"}
    cc = B.cocitacao(DF, min_citacoes=1)
    top = cc["referencias_mais_citadas"].iloc[0]
    assert top["referencia"] == "doi:10.1000/r1" and top["n_documentos"] == 2
    ac = B.acoplamento(DF)["arestas"]
    assert len(ac) == 2 and ac["peso"].max() == 1


def test_tecnologias_por_dicionario():
    t = B.tecnologias(DF)
    f = dict(zip(t["frequencia"].tecnologia, t["frequencia"].n_documentos))
    assert f["LSTM"] == 2 and f["CNN"] == 1 and f["Random Forest"] == 1 and f["Deep Learning"] == 1
    assert B.categoria_tecnologia("XGBoost") == "Ensemble"


def test_cobertura_explica_o_que_nao_rodou():
    r = B.analisar(DF[["title", "year"]])
    cob = r["cobertura"].set_index("analise")
    assert cob.loc["producao_anual", "executada"] == "sim"
    assert cob.loc["cocitacao", "executada"] == "não" and "referências" in cob.loc["cocitacao", "observacao"]
