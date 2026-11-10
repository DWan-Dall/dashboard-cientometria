"""Persistência: concorrência, falhas durante a execução, integridade dos arquivos originais,
recuperação após queda e consistência dos manifestos."""
import multiprocessing as mp
import os
import pathlib

import pytest

from cientometria import Config
from cientometria.projetos import IntegridadeErro, Projeto
from .sinteticos import gerar

CTX = mp.get_context("fork")
RAPIDO = dict(bibliometria_=False, graficos_=False, relatorios_=False, n_sensibilidade=0, revisao_duplicatas=False)


def _importar(args):
    raiz, i, mesmo = args
    p = pathlib.Path(raiz) / f"orig_{i}.csv"
    conteudo = "Title,DOI\nflood same,10.1/x\n" if mesmo else f"Title,DOI\nflood {i},10.1/{i}\n"
    p.write_text(conteudo, encoding="utf-8")
    return Projeto.abrir("conc", pathlib.Path(raiz) / "p").importar(p, nome="mesmo.csv" if mesmo else None)["id"]


def _criar(args):
    raiz, _ = args
    return Projeto.criar("Mesmo Nome", raiz=pathlib.Path(raiz)).pasta.name


def _executar(args):
    raiz, modo = args
    return Projeto.abrir("exec", pathlib.Path(raiz)).executar(Config.do_modo(modo), **RAPIDO)["id"]


@pytest.fixture()
def projeto_sint(tmp_path):
    pasta = gerar(str(tmp_path / "b"))
    p = Projeto.criar("Persist", raiz=tmp_path / "raiz")
    for f in sorted(pathlib.Path(pasta).glob("*.csv")):
        p.importar(f)
    return p


# ---------------------------------------------------------------- concorrência
def test_importacoes_simultaneas_nao_perdem_registros(tmp_path):
    Projeto.criar("conc", raiz=tmp_path / "p")
    with CTX.Pool(16) as pool:
        ids = pool.map(_importar, [(str(tmp_path), i, False) for i in range(64)])
    p = Projeto.abrir("conc", tmp_path / "p")
    assert len(set(ids)) == 64 and len(p.arquivos()) == 64
    eventos = [e for e in p.historico() if e["evento"] == "arquivo_importado"]
    assert len(eventos) == 64 and not [e for e in p.historico() if e["evento"] == "linha_ilegivel"]
    assert p.verificar_integridade() == []
    assert not list((p.pasta / "arquivos").glob(".importando_*"))


def test_mesmo_arquivo_importado_em_paralelo_gera_um_registro(tmp_path):
    Projeto.criar("conc", raiz=tmp_path / "p")
    with CTX.Pool(12) as pool:
        ids = pool.map(_importar, [(str(tmp_path), i, True) for i in range(24)])
    p = Projeto.abrir("conc", tmp_path / "p")
    assert len(set(ids)) == 1 and len(p.arquivos()) == 1


def test_criacao_simultanea_de_projetos_com_mesmo_nome(tmp_path):
    with CTX.Pool(10) as pool:
        slugs = pool.map(_criar, [(str(tmp_path / "r"), i) for i in range(20)])
    assert len(set(slugs)) == 20


def test_execucoes_simultaneas_no_mesmo_projeto(tmp_path):
    pasta = gerar(str(tmp_path / "b"))
    p = Projeto.criar("exec", raiz=tmp_path / "r")
    for f in sorted(pathlib.Path(pasta).glob("*.csv")):
        p.importar(f)
    with CTX.Pool(4) as pool:
        ids = pool.map(_executar, [(str(tmp_path / "r"), m) for m in ["original", "original", "corrigida", "variante_exclusao"]])
    assert len(set(ids)) == 4 and len(p.execucoes()) == 4
    assert all(p.verificar_execucao(i)["ok"] for i in ids)
    hashes = {e["id"]: e["hash_corpus"] for e in p.execucoes()}
    assert hashes[ids[0]] == hashes[ids[1]]          # mesma entrada e modo -> mesmo corpus


# ---------------------------------------------------------------- falhas
def test_falha_durante_execucao_nao_deixa_resultado_parcial(projeto_sint, monkeypatch):
    p = projeto_sint
    boa = p.executar(Config.original(), **RAPIDO)
    import cientometria.projetos as mod

    def explode(*a, **k):
        raise RuntimeError("falha simulada nos gráficos")
    monkeypatch.setattr(mod.graficos, "gerar_todos", explode)
    with pytest.raises(RuntimeError, match="simulada"):
        p.executar(Config.original(), bibliometria_=False, n_sensibilidade=0, revisao_duplicatas=False)
    assert [e["id"] for e in p.execucoes()] == [boa["id"]]
    falhas = list((p.pasta / "execucoes" / ".falhas").iterdir())
    assert len(falhas) == 1 and "falha simulada" in (falhas[0] / "erro.txt").read_text()
    assert p.historico()[-1]["evento"] == "execucao_falhou"
    assert not list((p.pasta / "execucoes").glob(".em_andamento_*"))
    assert p.verificar_execucao(boa["id"])["ok"]


def test_recuperacao_apos_queda(projeto_sint):
    p = projeto_sint
    boa = p.executar(Config.original(), **RAPIDO)
    # simula uma queda: execução pela metade, importação pela metade, linha de histórico truncada
    meio = p.pasta / "execucoes" / ".em_andamento_0123456789ab"
    meio.mkdir()
    (meio / "corpus.csv").write_text("parcial")
    (meio / "manifesto.json").write_text("{}")
    (p.pasta / "arquivos" / ".importando_xyz").write_text("parcial")
    with open(p.pasta / "historico.jsonl", "a") as f:
        f.write('{"quando": "2026-11-10", "evento": "exec')
    assert [e["id"] for e in p.execucoes()] == [boa["id"]]   # parcial nunca é listada
    rel = p.recuperar()
    assert rel["execucoes_interrompidas"] == ["0123456789ab"]
    assert ".importando_xyz" in rel["temporarios_removidos"]
    assert any("ilegíveis" in x for x in rel["problemas"])
    assert (p.pasta / "execucoes" / ".falhas" / "interrompida_0123456789ab" / "erro.txt").exists()
    assert p.verificar_execucao(boa["id"])["ok"]
    nova = p.executar(Config.original(), **RAPIDO)            # o projeto segue utilizável
    assert nova["manifesto"]["hash_corpus"] == boa["manifesto"]["hash_corpus"]


def test_registro_corrompido_e_reconstrucao(projeto_sint):
    p = projeto_sint
    antes = {a["sha256"] for a in p.arquivos()}
    (p.pasta / "arquivos.json").write_text('[{"id": "abc", ')
    with pytest.raises(IntegridadeErro, match="corrompido"):
        p.arquivos()
    lista = p.reconstruir_registro()
    assert {a["sha256"] for a in lista} == antes
    assert list(p.pasta.glob("arquivos.json.corrompido-*"))
    assert p.verificar_integridade() == []


# ---------------------------------------------------------------- integridade
def test_arquivo_original_alterado_impede_execucao(projeto_sint):
    p = projeto_sint
    alvo = p.pasta / "arquivos" / p.arquivos()[0]["arquivo"]
    os.chmod(alvo, 0o644)
    alvo.write_text(alvo.read_text() + "\nlinha,adulterada\n")
    probs = p.verificar_integridade()
    assert len(probs) == 1 and "SHA-256" in probs[0]["problema"]
    with pytest.raises(IntegridadeErro):
        p.executar(Config.original(), **RAPIDO)
    os.chmod(alvo, 0o644)
    alvo.unlink()
    assert "ausente" in p.verificar_integridade()[0]["problema"]


def test_importacao_preserva_bytes_do_original(projeto_sint, tmp_path):
    import hashlib
    origem = tmp_path / "bytes.csv"
    origem.write_bytes(b"Title,DOI\r\n\"Previs\xc3\xa3o, enchentes\",10.1/q\r\n")
    reg = projeto_sint.importar(origem)
    copia = projeto_sint.pasta / "arquivos" / reg["arquivo"]
    assert copia.read_bytes() == origem.read_bytes()
    assert hashlib.sha256(copia.read_bytes()).hexdigest() == reg["sha256"]


# ---------------------------------------------------------------- manifestos
def test_manifesto_consistente_e_saidas_verificaveis(projeto_sint):
    p = projeto_sint
    r = p.executar(Config.corrigida(), n_sensibilidade=50)
    man = p.manifesto(r["id"])
    assert man["saidas_sha256"] and "corpus.csv" in man["saidas_sha256"]
    assert "relatorios/relatorio.pdf" in man["saidas_sha256"]
    v = p.verificar_execucao(r["id"])
    assert v["ok"], v["problemas"]
    pasta = pathlib.Path(r["pasta"])
    with open(pasta / "corpus.csv", "a") as f:
        f.write("linha,extra\n")
    (pasta / "graficos" / "intruso.png").write_bytes(b"x")
    v = p.verificar_execucao(r["id"])
    assert not v["ok"]
    texto = " ".join(v["problemas"])
    assert "corpus.csv" in texto and "intruso.png" in texto


def test_manifesto_recuperado_reconstroi_a_configuracao(projeto_sint):
    p = projeto_sint
    cfg = Config.variante_exclusao().com(pesos=(0.4, 0.2, 0.25, 0.15))
    r = p.executar(cfg, **RAPIDO)
    assert Config.de_dict(p.manifesto(r["id"])["parametros"]) == cfg
    rep = p.reproduzir(r["id"])
    assert rep["mesmo_corpus"] and rep["mesma_entrada_e_parametros"]


def test_execucao_concluida_nunca_e_sobrescrita(projeto_sint, tmp_path):
    p = projeto_sint
    r = p.executar(Config.original(), **RAPIDO)
    antes = {k: v for k, v in p.manifesto(r["id"])["saidas_sha256"].items()}
    extra = tmp_path / "novo.csv"
    extra.write_text("Title,DOI,Abstract\nFlood forecasting LSTM,10.99/z,rainfall\n")
    p.importar(extra)
    p.executar(Config.original(), **RAPIDO)
    p.remover_arquivo(p.arquivos()[0]["id"])
    assert p.manifesto(r["id"])["saidas_sha256"] == antes
    assert p.verificar_execucao(r["id"])["ok"]
