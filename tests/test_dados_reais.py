"""Testes com DADOS REAIS (não versionados: as exportações têm licença das bases).

Ative com variáveis de ambiente:

  CIENTOMETRIA_EXPORTACOES_ORIGINAIS=/caminho/pasta   (os 8 CSVs exportados em jan/2026)
  CIENTOMETRIA_CORPUS_PUBLICADO=/caminho/DB_Cientometria_COMPLETA.csv (ou .xlsx)

Leia as falhas como ACHADOS: os números históricos são referências a verificar, não metas.
Se `test_numeros_historicos` falhar, investigue e documente em docs/AUDITORIA.md; não
altere o método para fazê-lo passar.
"""
import os
import pathlib

import numpy as np
import pytest

from cientometria import Config, executar, ler_pasta
from cientometria.auditoria import REFERENCIAS_HISTORICAS, comparar_com_referencia, verificar_corpus_publicado
from cientometria.entrada import BASES_ESPERADAS

EXPORT = os.environ.get("CIENTOMETRIA_EXPORTACOES_ORIGINAIS")
CORPUS = os.environ.get("CIENTOMETRIA_CORPUS_PUBLICADO")

precisa_export = pytest.mark.skipif(not EXPORT, reason="defina CIENTOMETRIA_EXPORTACOES_ORIGINAIS")
precisa_corpus = pytest.mark.skipif(not CORPUS, reason="defina CIENTOMETRIA_CORPUS_PUBLICADO")


# ---------------------------------------------------------------- exportações originais
@pytest.fixture(scope="module")
def originais():
    faltam = [a for a in BASES_ESPERADAS if not (pathlib.Path(EXPORT) / a).exists()]
    assert not faltam, f"arquivos ausentes: {faltam}"
    from .test_equivalencia_original import rodar_original
    return rodar_original(EXPORT), executar(ler_pasta(EXPORT), Config.original())


@precisa_export
def test_pacote_reproduz_os_scripts_originais_nos_dados_reais(originais):
    """Equivalência pacote × scripts originais (referencia/) sobre as exportações reais."""
    ns, res = originais
    assert res.contagens["unicos"] == len(ns["df_consolidated"])
    assert res.contagens["corpus"] == len(ns["df_expanded"])
    o, p = ns["df_analysis"].reset_index(drop=True), res.corpus.reset_index(drop=True)
    for col in ["C_norm", "R_norm", "T_score", "A_score", "score_final_100"]:
        np.testing.assert_allclose(o[col].astype(float), p[col].astype(float), err_msg=col)
    assert list(o["fascia"]) == list(p["fascia"])


@precisa_export
def test_numeros_historicos(originais):
    """16.845 → 11.547 → 2.068 → 13/494/1.508/53 (referência histórica, não meta)."""
    _, res = originais
    tab = comparar_com_referencia(res)
    print("\n" + tab.to_string(index=False))
    assert tab["confere"].all(), "Divergência com as referências históricas: investigar e documentar."


@precisa_export
def test_dashboard_original_igual_ao_pacote_nos_dados_reais(originais, tmp_path):
    from cientometria.ingestao import carregar_fontes
    _, ref = originais
    arqs = sorted(pathlib.Path(EXPORT).glob("*.csv"), reverse=True)
    bases, _ = carregar_fontes([a for a in arqs if a.name in BASES_ESPERADAS], Config.original())
    assert executar(bases, Config.original()).contagens == ref.contagens


@precisa_export
def test_modos_documentam_a_diferenca(originais):
    _, orig = originais
    bases = ler_pasta(EXPORT)
    var = executar(bases, Config.variante_exclusao())
    assert var.contagens["unicos"] == orig.contagens["unicos"]       # só a exclusão muda
    assert var.contagens["corpus"] >= orig.contagens["corpus"]


# ---------------------------------------------------------------- corpus publicado
@precisa_corpus
def test_corpus_publicado_consistencia_interna():
    v = verificar_corpus_publicado(CORPUS)
    n = v["linhas"]
    assert n == REFERENCIAS_HISTORICAS["corpus"]
    assert v["estratos"] == {k: REFERENCIAS_HISTORICAS[k] for k in ["Núcleo A", "Núcleo B", "Periférico", "Descarte"]}
    assert v["C_norm_confere"] == n and v["R_norm_confere"] == n          # fórmulas de C* e R*
    assert v["escore_confere_com_A_corrigido"] == n                      # fórmula do escore e min–max
    assert v["estrato_confere"] == n                                     # cortes 70/50/30
    # T*/A* só podem divergir para cima: o arquivo não traz as palavras-chave usadas na triagem
    assert v["T_sem_palavras_chave"]["publicado_menor"] == 0
    assert v["A_sem_palavras_chave"]["publicado_menor"] == 0


@precisa_corpus
def test_corpus_publicado_achados_documentados():
    """Fixa os achados da auditoria (docs/AUDITORIA.md). Se mudarem, o arquivo mudou."""
    v = verificar_corpus_publicado(CORPUS)
    if pathlib.Path(CORPUS).suffix.lower() == ".csv":
        assert v["A_score_valores_anomalos"] == [625.0, 875.0]      # 0,625/0,875 corrompidos (separador decimal)
    assert v["doi_duplicado_so_na_caixa"] == 27
