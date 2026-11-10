"""Regressão: importação, processamento (4 modos × 2 cenários) e contrato da API.

O retrato esperado (tests/regressao/esperado.json) foi gerado com dados SINTÉTICOS. Se este
teste falhar, o resultado do processamento mudou: só atualize o retrato
(`python tests/regressao/gerar_esperado.py`) se a mudança for intencional e documentada
(nova versão do método). Isso não valida a reprodução do artigo."""
import json
import pathlib

import pytest

from cientometria import Config
from cientometria.api import despachar
from .regressao.gerar_esperado import CENARIOS, gerar_tudo
from .sinteticos import gerar

ESPERADO = json.loads((pathlib.Path(__file__).parent / "regressao" / "esperado.json").read_text(encoding="utf-8"))


@pytest.fixture(scope="module")
def atual():
    return json.loads(json.dumps(gerar_tudo(), ensure_ascii=False, sort_keys=True))


@pytest.mark.parametrize("cenario", sorted(CENARIOS))
@pytest.mark.parametrize("modo", ["original", "variante_exclusao", "corrigida", "corrigida_v1"])
def test_processamento_inalterado(atual, cenario, modo):
    a, e = atual[cenario][modo], ESPERADO[cenario][modo]
    assert a["versao_metodo"] == e["versao_metodo"]
    assert a["contagens"] == e["contagens"]
    assert a["estratos"] == e["estratos"]
    assert a["top10_doi"] == e["top10_doi"]
    assert a["soma_escore"] == pytest.approx(e["soma_escore"], abs=1e-6)
    assert a["hash_corpus"] == e["hash_corpus"], "corpus diferente do retrato (valores, ordem ou colunas)"


@pytest.mark.parametrize("cenario", sorted(CENARIOS))
def test_importacao_inalterada(atual, cenario):
    assert atual[cenario]["importacao"] == ESPERADO[cenario]["importacao"]


# ------------------------------------------------------------ contrato da API (Python)
@pytest.fixture(scope="module")
def api(tmp_path_factory):
    raiz = str(tmp_path_factory.mktemp("raiz"))
    pasta = gerar(str(tmp_path_factory.mktemp("b")))
    p = despachar("criar_projeto", {"raiz": raiz, "nome": "Contrato"})["projeto"]["slug"]
    arqs = [{"caminho": str(f), "nome": f.name} for f in sorted(pathlib.Path(pasta).glob("*.csv"))]
    imp = despachar("importar", {"raiz": raiz, "projeto": p, "arquivos": arqs})
    chama = lambda acao, **kw: despachar(acao, {"raiz": raiz, "projeto": p, **kw})  # noqa: E731
    return chama, imp


CHAVES_EXECUCAO = {"manifesto", "pasta", "corpus", "diagnosticos", "limitacoes", "campos", "duplicatas_para_revisao",
                   "bibliometria", "graficos", "relatorios"}


def test_contrato_api(api):
    chama, imp = api
    assert {"importados", "arquivos"} <= set(imp) and len(imp["arquivos"]) == 8
    assert {"projeto", "arquivos", "execucoes", "historico"} <= set(chama("projeto"))
    d = chama("diagnosticar", params={"modo": "original"})
    assert {"fontes", "campos", "limitacoes"} <= set(d) and len(d["fontes"]) == 8
    e1 = chama("executar", params={"modo": "original", "n_sensibilidade": 50})
    assert CHAVES_EXECUCAO <= set(e1)
    assert e1["manifesto"]["estratos"] == ESPERADO["padrao"]["original"]["estratos"]
    e2 = chama("executar", params={"modo": "corrigida", "n_sensibilidade": 0})
    lista = chama("execucoes")["execucoes"]
    assert [x["id"] for x in lista] == [e1["manifesto"]["id"], e2["manifesto"]["id"]]
    assert CHAVES_EXECUCAO <= set(chama("execucao", id=e1["manifesto"]["id"]))
    c = chama("comparar", a=e1["manifesto"]["id"], b=e2["manifesto"]["id"])
    assert {"mesma_entrada_e_parametros", "mesmo_corpus", "contagens", "estratos", "parametros", "nucleo_a"} <= set(c)
    assert c["mesma_entrada_e_parametros"] is False
    rep = chama("reproduzir", id=e1["manifesto"]["id"])
    assert rep["mesmo_corpus"] and rep["mesma_entrada_e_parametros"]
    assert chama("verificar_execucao", id=e1["manifesto"]["id"])["ok"] is True
    m = chama("comparar_modos")["modos"]
    assert set(m) == {"original", "variante_exclusao", "corrigida"}
    assert m["original"]["estratos"] == ESPERADO["padrao"]["original"]["estratos"]
    assert chama("atualizar_projeto", campos={"descricao": "nova"})["projeto"]["descricao"] == "nova"
    assert chama("remover_arquivo", id=imp["arquivos"][0]["id"])["arquivos"][0]["ativo"] is False


@pytest.mark.parametrize("acao,dados,erro", [
    ("projeto", {"projeto": "../x"}, ValueError), ("execucao", {"id": "../../x"}, ValueError),
    ("acao_inexistente", {}, ValueError), ("executar", {"params": {"modo": "inventado"}}, ValueError),
    ("executar", {"params": {"weights": {"c": 1, "r": 1, "t": 1, "a": 1}}}, ValueError),
])
def test_api_rejeita_entradas_invalidas(api, acao, dados, erro, tmp_path):
    chama, _ = api
    with pytest.raises(erro):
        chama(acao, **dados) if acao != "projeto" else despachar(acao, {"raiz": str(tmp_path), **dados})


def test_modo_original_continua_identico_aos_scripts_de_referencia():
    """Atalho explícito: o retrato do modo original deve coincidir com o teste de equivalência."""
    from .test_equivalencia_original import rodar_original
    import tempfile
    from cientometria import executar, ler_pasta
    with tempfile.TemporaryDirectory() as d:
        pasta = gerar(d)
        ns = rodar_original(pasta)
        r = executar(ler_pasta(pasta), Config.original())
    assert len(ns["df_expanded"]) == r.contagens["corpus"] == ESPERADO["padrao"]["original"]["contagens"]["corpus"]
