"""Regressão do achado de auditoria (nov/2026): o modo 'original' do dashboard precisa
reproduzir Config.original() do pacote, inclusive na leitura das colunas e na ordem."""
import json
import pathlib
import shutil
import subprocess
import sys

import pytest

from cientometria import Config, executar, ler_pasta
from cientometria.ingestao import carregar_fontes
from cientometria.parametros import config_de_parametros
from .sinteticos import gerar

RAIZ = pathlib.Path(__file__).resolve().parents[1]


@pytest.fixture(scope="module")
def pasta(tmp_path_factory):
    return gerar(str(tmp_path_factory.mktemp("b")))


@pytest.fixture(scope="module")
def ref(pasta):
    return executar(ler_pasta(pasta), Config.original())


def _rodar(payload, tmp_path):
    p = tmp_path / "payload.json"
    p.write_text(json.dumps(payload))
    out = subprocess.run([sys.executable, str(RAIZ / "scripts" / "pipeline.py"), str(p)],
                         capture_output=True, text=True, check=True).stdout
    return json.loads(out)


def test_parametros_nao_forcam_mapeamento_tolerante():
    assert config_de_parametros({"modo": "original"}).mapeamento_tolerante is False
    assert config_de_parametros({"modo": "original"}) == Config.original()
    assert config_de_parametros({"modo": "corrigida"}) == Config.corrigida()
    assert config_de_parametros({"modo": "original", "mapeamento_tolerante": True}).personalizada()


@pytest.mark.parametrize("inverter", [False, True])
def test_dashboard_original_igual_ao_pacote_em_qualquer_ordem(pasta, ref, tmp_path, inverter):
    arqs = sorted(str(x) for x in pathlib.Path(pasta).glob("*.csv"))
    if inverter:
        arqs = arqs[::-1]
    r = _rodar({"files": arqs, "params": {"modo": "original", "n_sensibilidade": 0}}, tmp_path)
    s = r["summary"]
    assert (s["raw_records"], s["after_doi"], s["after_title"], s["thematic_selected"]) == (
        ref.contagens["registros"], ref.contagens["apos_doi"], ref.contagens["unicos"], ref.contagens["corpus"])
    assert s["core_counts"] == ref.estratos()
    assert r["config"]["mapeamento_tolerante"] is False


def test_dashboard_com_nomes_temporarios_usa_nomes_originais(pasta, ref, tmp_path):
    """O PHP grava 'upl_<id>_<nome>': o nome original vai em payload['names']."""
    arqs, nomes = [], []
    for i, f in enumerate(sorted(pathlib.Path(pasta).glob("*.csv"))[::-1]):
        destino = tmp_path / f"upl_{i:03d}abc_{f.name}"
        shutil.copy(f, destino)
        arqs.append(str(destino))
        nomes.append(f.name)
    r = _rodar({"files": arqs, "names": nomes, "params": {"modo": "original", "n_sensibilidade": 0}}, tmp_path)
    assert r["summary"]["core_counts"] == ref.estratos()
    assert [f["rotulo"] for f in r["fontes"]][:2] == ["Lens (EN)", "Lens (PT)"]


def test_carregar_fontes_original_equivale_a_ler_pasta(pasta, ref):
    arqs = sorted(pathlib.Path(pasta).glob("*.csv"), reverse=True)
    bases, fontes = carregar_fontes(arqs, Config.original())
    res = executar(bases, Config.original())
    assert res.contagens == ref.contagens
    assert list(res.corpus["score_final_100"]) == list(ref.corpus["score_final_100"])
    assert all(f.canonico and f.leitura.startswith("original") for f in fontes)


def test_ordem_nao_canonica_e_registrada(pasta, tmp_path):
    arqs = []
    for f in sorted(pathlib.Path(pasta).glob("*.csv"))[:2]:
        d = tmp_path / ("x_" + f.name)
        shutil.copy(f, d)
        arqs.append(d)
    _, fontes = carregar_fontes(arqs, Config.original())
    assert all(any("ordem de processamento" in a for a in f.avisos) for f in fontes)


def test_php_recusa_motor_r():
    texto = (RAIZ / "run_pipeline.php").read_text(encoding="utf-8")
    assert "Rscript" not in texto and "Motor R desativado" in texto


def test_interface_nao_tem_alvos_editaveis():
    """Os números do artigo não podem ser 'metas' editáveis na interface."""
    import re
    for arq in ("index.php", "triagem_rapida.php"):
        t = (RAIZ / arq).read_text(encoding="utf-8")
        for m in re.finditer(r'<input id="target\w+"[^>]*>', t):
            assert "readonly" in m.group(0), (arq, m.group(0))
