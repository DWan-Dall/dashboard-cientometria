"""Projetos, imutabilidade das execuções, manifesto e consistência entre execuções."""
import json
import pathlib
import subprocess
import sys

import pytest

from cientometria import Config
from cientometria.manifesto import comparar
from cientometria.projetos import Projeto
from .sinteticos import gerar

RAIZ = pathlib.Path(__file__).resolve().parents[1]
CAMPOS_MANIFESTO = {"id", "data_hora_utc", "versao_aplicacao", "versao_metodo", "modo", "fontes", "parametros",
                    "pesos", "cortes", "regras_exclusao", "contagens", "estratos", "resultados_finais",
                    "dependencias", "hash_corpus", "impressao_digital_entrada", "criterios_consolidacao"}


@pytest.fixture(scope="module")
def projeto(tmp_path_factory):
    raiz = tmp_path_factory.mktemp("proj")
    pasta = gerar(str(tmp_path_factory.mktemp("b")))
    p = Projeto.criar("Teste de Projeto", "desc", ["Lens", "Scopus"], raiz=raiz)
    for f in sorted(pathlib.Path(pasta).glob("*.csv")):
        p.importar(f)
    return p


def test_importacao_idempotente_e_imutavel(projeto, tmp_path):
    n = len(projeto.arquivos())
    primeiro = projeto.arquivos()[0]
    original = projeto.pasta / "arquivos" / primeiro["arquivo"]
    projeto.importar(original, nome=primeiro["nome"])
    assert len(projeto.arquivos()) == n


def test_execucao_gera_manifesto_completo(projeto):
    r = projeto.executar(Config.original(), n_sensibilidade=50, graficos_=False, relatorios_=False)
    m = r["manifesto"]
    assert CAMPOS_MANIFESTO <= set(m)
    assert all(len(f["sha256"]) == 64 for f in m["fontes"])
    assert m["versao_metodo"] == "original-2026.01" and not m["configuracao_personalizada"]
    assert (pathlib.Path(r["pasta"]) / "manifesto.json").exists()


def test_nova_importacao_nao_altera_execucao_anterior(projeto, tmp_path):
    r1 = projeto.executar(Config.original(), n_sensibilidade=0, bibliometria_=False, graficos_=False, relatorios_=False)
    antes = (pathlib.Path(r1["pasta"]) / "corpus.csv").read_bytes()
    extra = tmp_path / "extra.csv"
    extra.write_text("Title,Year,DOI,Abstract\nFlood forecasting with LSTM,2024,10.99/new,rainfall\n", encoding="utf-8")
    projeto.importar(extra)
    r2 = projeto.executar(Config.original(), n_sensibilidade=0, bibliometria_=False, graficos_=False, relatorios_=False)
    assert (pathlib.Path(r1["pasta"]) / "corpus.csv").read_bytes() == antes
    assert r2["manifesto"]["contagens"]["registros"] == r1["manifesto"]["contagens"]["registros"] + 1
    assert projeto.manifesto(r1["id"])["contagens"] == r1["manifesto"]["contagens"]
    c = projeto.comparar(r1["id"], r2["id"])
    assert "extra.csv" in c["arquivos"] and not c["mesma_entrada_e_parametros"]
    projeto.remover_arquivo([a for a in projeto.arquivos() if a["nome"] == "extra.csv"][0]["id"])


def test_consistencia_entre_execucoes_e_reproducao(projeto):
    a = projeto.executar(Config.variante_exclusao(), n_sensibilidade=0, bibliometria_=False, graficos_=False,
                         relatorios_=False)
    b = projeto.executar(Config.variante_exclusao(), n_sensibilidade=0, bibliometria_=False, graficos_=False,
                         relatorios_=False)
    c = comparar(a["manifesto"], b["manifesto"])
    assert c["mesma_entrada_e_parametros"] and c["mesmo_corpus"] and not c["contagens"]
    rep = projeto.reproduzir(a["id"])
    assert rep["mesmo_corpus"] and rep["mesma_entrada_e_parametros"]


def test_parametros_personalizados_ficam_registrados(projeto):
    cfg = Config.original().com(pesos=(0.25, 0.25, 0.25, 0.25))
    m = projeto.executar(cfg, n_sensibilidade=0, bibliometria_=False, graficos_=False, relatorios_=False)["manifesto"]
    assert m["configuracao_personalizada"] and "pesos" in m["alteracoes_em_relacao_a_receita"]


def test_relatorios_completos(projeto):
    r = projeto.executar(Config.original(), n_sensibilidade=0)
    pasta = pathlib.Path(r["pasta"])
    for f in ["relatorios/resultados.xlsx", "relatorios/relatorio.pdf", "relatorios/relatorio_metodologico.md",
              "relatorios/parametros.json", "relatorios/csv/corpus.csv", "graficos/01-fluxo.png",
              "bibliometria/cobertura.csv", "diagnosticos/campos.csv", "diagnosticos/duplicatas_para_revisao.csv"]:
        assert (pasta / f).exists(), f
    md = (pasta / "relatorios/relatorio_metodologico.md").read_text(encoding="utf-8")
    assert r["manifesto"]["id"] in md and "original-2026.01" in md
    assert json.loads((pasta / "relatorios/parametros.json").read_text())["pesos"] == [0.35, 0.2, 0.3, 0.15]


def test_historico_append_only(projeto):
    eventos = [e["evento"] for e in projeto.historico()]
    assert eventos[0] == "projeto_criado" and "execucao" in eventos and "arquivo_importado" in eventos


def test_api_json(projeto):
    payload = projeto.pasta.parent / "p.json"
    payload.write_text(json.dumps({"raiz": str(projeto.pasta.parent), "projeto": projeto.pasta.name}))
    out = subprocess.run([sys.executable, "-m", "cientometria.api", "execucoes", str(payload)], cwd=RAIZ,
                         capture_output=True, text=True, check=True).stdout
    assert len(json.loads(out)["execucoes"]) >= 1
    ruim = subprocess.run([sys.executable, "-m", "cientometria.api", "acao_inexistente", str(payload)], cwd=RAIZ,
                          capture_output=True, text=True)
    assert ruim.returncode == 1 and "erro" in json.loads(ruim.stdout)
