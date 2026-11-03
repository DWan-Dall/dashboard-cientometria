import json, subprocess, sys, pathlib
import pytest
from cientometria import Config, executar, ler_pasta, robustez, diagnostico, validacao
from .sinteticos import gerar

RAIZ = pathlib.Path(__file__).resolve().parents[1]


@pytest.fixture(scope="module")
def bases(tmp_path_factory):
    return ler_pasta(gerar(str(tmp_path_factory.mktemp("b"))))


@pytest.fixture(scope="module")
def orig(bases):
    return executar(bases, Config.original())


def test_modo_corrigido_nao_descarta_registros_sem_doi(bases, orig):
    cor = executar(bases, Config.corrigida())
    assert cor.contagens["unicos"] > orig.contagens["unicos"]
    assert orig.contagens["removidos_etapa_doi"] == orig.contagens["sem_doi"] + orig.contagens["duplicatas_doi"]


def test_mapeamento_tolerante_le_titulos_do_ieee(bases):
    orig = executar(bases, Config.original())
    tol = executar(bases, Config.original().com(mapeamento_tolerante=True))
    ieee_o = (orig.bruto.source_db == "IEEE Xplore") & (orig.bruto.title == "Unknown")
    ieee_t = (tol.bruto.source_db == "IEEE Xplore") & (tol.bruto.title == "Unknown")
    assert ieee_o.sum() > 0 and ieee_t.sum() == 0


def test_variante_so_muda_exclusao(bases, orig):
    var = executar(bases, Config.variante_exclusao())
    assert var.contagens["unicos"] == orig.contagens["unicos"]
    assert var.contagens["corpus"] >= orig.contagens["corpus"]


def test_exclusao_palavra_inteira_nao_pega_damage():
    from cientometria.nucleo import excluido
    assert excluido("damage assessment of floods", "", Config.original())
    assert not excluido("damage assessment of floods", "", Config.variante_exclusao())
    assert excluido("a dam break model", "", Config.variante_exclusao())


def test_sensibilidade_reprodutivel(orig):
    a = robustez.sensibilidade_pesos(orig, n=300, seed=1)
    b = robustez.sensibilidade_pesos(orig, n=300, seed=1)
    assert a == b and a["k_referencia"] == orig.estratos()["Núcleo A"]


def test_tabela_referencia(bases, orig):
    var = executar(bases, Config.variante_exclusao())
    t = robustez.tabela_referencia(orig, var)
    assert len(t) == orig.estratos()["Núcleo A"]


def test_diagnosticos(bases, orig):
    d = diagnostico.exclusao_por_trecho(orig)
    assert d["excluidos_so_por_trecho"] <= d["excluidos"] <= d["candidatos"]
    assert diagnostico.perdas_no_fluxo(orig)["registros_sem_doi_descartados"] == orig.contagens["sem_doi"]
    assert len(diagnostico.colunas_nao_lidas(bases)) >= 4


def test_validacao_externa(orig):
    alvo = orig.corpus.iloc[0]["title"]
    t = validacao.validar_referencias({1: alvo, 2: "um titulo que nao existe em lugar nenhum xyz"}, orig)
    assert t.loc[t.ref == 1, "no_corpus"].iloc[0] == "sim"
    assert t.loc[t.ref == 2, "recuperada"].iloc[0] == "não"


def test_cli_do_dashboard_mantem_o_contrato_json(tmp_path):
    pasta = gerar(str(tmp_path / "b"))
    arquivos = sorted(str(p) for p in pathlib.Path(pasta).glob("*.csv"))
    payload = tmp_path / "p.json"
    payload.write_text(json.dumps({"files": arquivos, "params": {"modo": "original", "n_sensibilidade": 50}}))
    out = subprocess.run([sys.executable, str(RAIZ / "scripts" / "pipeline.py"), str(payload)],
                         capture_output=True, text=True, check=True).stdout
    r = json.loads(out)
    for k in ["summary", "top_articles", "dedup_removed", "plot_urls", "used_params", "extras"]:
        assert k in r
    assert r["summary"]["after_title"] > 0 and r["modo"] == "original"
