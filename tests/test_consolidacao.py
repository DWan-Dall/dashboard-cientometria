"""Deduplicação, ausência de DOI, duplicatas e versões dos modos."""
import pandas as pd

from cientometria import Config, executar
from cientometria.consolidacao import correspondencias_duvidosas, normalizar_doi, sobreposicao


def _base(linhas):
    return pd.DataFrame(linhas, columns=["Title", "Year", "Abstract", "Keywords", "Citing Works Count", "DOI", "Source Title"])


T = "flood forecasting with lstm"
A = "rainfall and river data with deep learning"


def _bases():
    lens = _base([[T, 2020, A, "", 5, "10.1029/2019WR027038", "W"],
                  ["Flood prediction using random forest", 2021, A, "", 1, "", "W"],
                  ["Unknown thing", 2019, "", "", 0, "", "W"]])
    lens2 = _base([[T.upper() + " ", 2020, A, "", 7, "10.1029/2019wr027038", "W"],     # mesmo DOI, outra caixa
                   ["Flood prediction using random forest", 2021, A, "", 2, "10.5/x", "W"],  # mesmo título, com DOI
                   ["Flood forecasting with LSTM: a case study", 2022, A, "", 0, "https://doi.org/10.7/ZZ", "W"]])
    return {"Lens (EN)": (lens, "lens"), "Lens (PT)": (lens2, "lens")}


def test_normalizar_doi():
    assert normalizar_doi(" https://doi.org/10.1029/2019WR027038. ") == "10.1029/2019wr027038"
    assert normalizar_doi("doi:10.5/X") == "10.5/x"
    assert normalizar_doi(None) == "" and normalizar_doi(float("nan")) == ""


def test_original_descarta_sem_doi_e_nao_normaliza():
    r = executar(_bases(), Config.original())
    c = r.contagens
    assert c["registros"] == 6 and c["sem_doi"] == 2
    assert c["duplicatas_doi"] == 0           # DOIs que diferem na caixa NÃO são duplicatas no original
    assert c["apos_doi"] == 4
    assert c["removidos_titulo"] == 1          # mas o título (lower+strip) colapsa os dois
    assert c["unicos"] == 3


def test_corrigida_2_normaliza_doi_e_v1_preservada():
    r2 = executar(_bases(), Config.corrigida())
    r1 = executar(_bases(), Config.corrigida_v1())
    assert r2.contagens["duplicatas_doi"] == 1 and r1.contagens["duplicatas_doi"] == 0
    assert r2.cfg.metodo_versao == "corrigida-2" and r1.cfg.metodo_versao == "corrigida-1"
    # registros sem DOI mantidos; 'Unknown thing' não colapsa com nada
    assert r2.contagens["unicos"] == 4 and r1.contagens["unicos"] == 4


def test_proveniencia_registra_todas_as_bases():
    r = executar(_bases(), Config.corrigida())
    lin = r.consolidado[r.consolidado["doi"].str.lower() == "10.1029/2019wr027038"]
    assert lin["bases_encontradas"].iloc[0] == "Lens (EN); Lens (PT)" and lin["n_bases"].iloc[0] == 2
    assert {"arquivo_origem", "linha_origem"} <= set(r.bruto.columns)


def test_pares_duvidosos_para_revisao():
    r = executar(_bases(), Config.corrigida_v1())
    pares = correspondencias_duvidosas(r.bruto, limiar=80)
    motivos = set(pares["motivo"])
    assert "DOI igual após normalização" in motivos
    assert (pares["decisao"] == "").all()     # nunca decidido automaticamente


def test_sobreposicao():
    r = executar(_bases(), Config.corrigida())
    s = sobreposicao(r.bruto)
    m = s["matriz"].set_index("base")
    assert m.loc["Lens (EN)", "Lens (PT)"] >= 1
    assert s["por_numero_de_bases"]["n_obras"].sum() >= 4


def test_variantes_nao_mudam_o_original():
    """Novas opções desligadas não podem alterar o original (protege o golden master)."""
    a = executar(_bases(), Config.original())
    b = executar(_bases(), Config.original().com(normalizar_doi=False))
    assert a.contagens == b.contagens
