"""Exportação e importação de execuções em ZIP (cientometria/pacote.py + Projeto).

Casos obrigatórios (numerados como no pedido): 1 ida e volta íntegra; 2 arquivo ausente;
3 arquivo alterado após a exportação; 4 hash incorreto; 5 ZIP inválido ou malformado;
6 zip bomb; 7 path traversal; 8 arquivos inesperados; 9 dados originais omitidos;
10 restauração sem recálculo; 11 reexecução com novo ID; 12 compatibilidade de versões do
pacote; 13 importações concorrentes; 14 interrupção durante a restauração.

Todos os dados são SINTÉTICOS (tests/sinteticos.py): estes testes verificam o mecanismo de
pacote, não a reprodução do artigo."""
import io
import json
import multiprocessing as mp
import os
import pathlib
import re
import shutil
import stat
import struct
import zipfile

import pytest

from cientometria import Config
from cientometria import pacote as PK
from cientometria.api import despachar
from cientometria.projetos import IntegridadeErro, Projeto, _sha_saidas
from .sinteticos import gerar

CTX = mp.get_context("fork")


# ---------------------------------------------------------------- preparação
@pytest.fixture(scope="module")
def origem(tmp_path_factory):
    """Um projeto com uma execução completa (bibliometria, gráficos, relatórios) e seus dois ZIPs."""
    base = tmp_path_factory.mktemp("pacote")
    p = Projeto.criar("Origem", raiz=base / "raiz")
    for f in sorted(pathlib.Path(gerar(str(base / "dados"))).glob("*.csv")):
        p.importar(f)
    r = p.executar(Config.original(), n_sensibilidade=20)
    saida = base / "zips"
    saida.mkdir()
    com = p.exportar_execucao(r["id"], saida, incluir_entradas=True)
    sem = p.exportar_execucao(r["id"], saida, incluir_entradas=False)
    return {"projeto": p, "id": r["id"], "pasta": p.pasta_execucao(r["id"]), "com": pathlib.Path(com["arquivo"]),
            "sem": pathlib.Path(sem["arquivo"]), "base": base}


@pytest.fixture()
def destino(tmp_path):
    return Projeto.criar("Destino", raiz=tmp_path / "raiz")


def _membros(zp):
    with zipfile.ZipFile(zp) as z:
        return {i.filename: z.read(i) for i in z.infolist()}


def _reescrever(orig, dest, alterar=None, remover=(), extra=None, manifesto=None, infos=None):
    """Copia um ZIP aplicando alterações (bytes), remoções, extras e edição do manifesto."""
    m = _membros(orig)
    for k, v in (alterar or {}).items():
        m[k] = v
    for k in remover:
        m.pop(k)
    m.update(extra or {})
    if manifesto:
        d = json.loads(m["manifesto.json"])
        manifesto(d)
        m["manifesto.json"] = json.dumps(d).encode()
    with zipfile.ZipFile(dest, "w", zipfile.ZIP_DEFLATED) as z:
        for k, v in m.items():
            z.writestr(k, v)
        for info, dados in (infos or []):
            z.writestr(info, dados)
    return dest


def _arq_exec(origem, rel):
    return f"execucao/{origem['pasta'].name}/{rel}"


def _sem_lista(p):
    return [e for e in p.execucoes()] == [] and not list((p.pasta / "execucoes").glob(".importando_*"))


# ---------------------------------------------------------------- 1. ida e volta
def test_01_ida_e_volta_integra(origem, destino):
    inv = PK.inspecionar(origem["com"])
    assert inv["ok"] and inv["problemas"] == [] and inv["avisos"] == []
    with zipfile.ZipFile(origem["com"]) as z:
        nomes = set(z.namelist())
        manp = json.loads(z.read("manifesto.json"))
    # conteúdo exigido: tudo o que a execução gravou + entradas + manifesto + leia-me
    pasta = origem["pasta"]
    for f in pasta.rglob("*"):
        if f.is_file():
            assert _arq_exec(origem, f.relative_to(pasta).as_posix()) in nomes
    for parte in ("corpus.csv", "consolidado.csv", "contagens.json", "manifesto.json", "diagnosticos/campos.csv",
                  "diagnosticos/duplicatas_para_revisao.csv", "relatorios/relatorio.pdf",
                  "relatorios/resultados.xlsx", "relatorios/relatorio_metodologico.md"):
        assert _arq_exec(origem, parte) in nomes, parte
    assert any(n.startswith(_arq_exec(origem, "bibliometria/")) for n in nomes)
    assert any(n.endswith(".png") for n in nomes)
    assert len([n for n in nomes if n.startswith("entradas/")]) == 8
    # manifesto do pacote: campos exigidos
    for chave in ("formato", "versao_formato", "exportado_em", "versao_aplicacao_exportacao", "execucao",
                  "projeto_origem", "parametros", "contagens_por_etapa", "estratos", "dependencias", "fontes",
                  "omitidos", "arquivos", "reprodutibilidade"):
        assert chave in manp, chave
    assert manp["execucao"]["id"] == origem["id"] and manp["projeto_origem"]["slug"] == "origem"
    assert manp["execucao"]["versao_metodo"] == "original-2026.01" and manp["execucao"]["modo"] == "original"
    assert set(manp["arquivos"]) == nomes - {"manifesto.json"}
    assert all(re.fullmatch(r"[0-9a-f]{64}", d["sha256"]) for d in manp["arquivos"].values())
    assert manp["reprodutibilidade"]["reexecucao_possivel_so_com_o_pacote"] is True
    # restauração: mesmo ID, mesma pasta, bytes idênticos, verificação ok, procedência registrada
    rec = destino.receber_pacote(origem["com"])
    r = destino.restaurar_pacote(rec["token"])
    assert r["estado"] == "restaurada" and r["id"] == origem["id"] and r["pasta"] == pasta.name
    nova = destino.pasta_execucao(origem["id"])
    assert _sha_saidas(nova) == _sha_saidas(pasta)
    assert (nova / "manifesto.json").read_bytes() == (pasta / "manifesto.json").read_bytes()
    assert r["verificacao"]["ok"] and r["verificacao"]["reexecucao_possivel"]
    ev = [e for e in destino.historico() if e["evento"] == "execucao_restaurada"]
    assert len(ev) == 1 and ev[0]["recalculo"] is False and ev[0]["projeto_origem"] == "origem"
    imp = json.loads((destino.pasta / "execucoes" / ".importadas" / f"{origem['id']}.json").read_text())
    assert imp["pacote_sha256"] == rec["pacote_sha256"] and imp["projeto_origem"]["slug"] == "origem"
    assert destino.execucoes()[0]["importada"] is True
    assert not list((destino.pasta / "pacotes").glob("*.zip"))      # pacote consumido
    # a origem não foi tocada pela exportação
    assert origem["projeto"].verificar_execucao(origem["id"])["ok"]


def test_01b_exportacao_reproduzivel_e_reimportavel(origem, tmp_path, destino):
    """Exportar de novo a execução restaurada gera um pacote com os mesmos arquivos."""
    destino.restaurar_pacote(destino.receber_pacote(origem["com"])["token"])
    (tmp_path / "z").mkdir()
    z2 = destino.exportar_execucao(origem["id"], tmp_path / "z")
    a, b = _membros(origem["com"]), _membros(z2["arquivo"])
    assert {k: v for k, v in a.items() if k not in ("manifesto.json", "LEIA-ME.txt")} == \
           {k: v for k, v in b.items() if k not in ("manifesto.json", "LEIA-ME.txt")}


# ---------------------------------------------------------------- 2, 3, 4, 8: integridade
def test_02_arquivo_ausente(origem, destino, tmp_path):
    zp = _reescrever(origem["com"], tmp_path / "x.zip", remover=[_arq_exec(origem, "corpus.csv")])
    inv = destino.receber_pacote(zp)
    assert not inv["ok"] and any("ausente no pacote" in p and "corpus.csv" in p for p in inv["problemas"])
    with pytest.raises(IntegridadeErro, match="integridade"):
        destino.restaurar_pacote(inv["token"])
    assert _sem_lista(destino)


def test_03_arquivo_alterado_apos_exportacao(origem, destino, tmp_path):
    alvo = _arq_exec(origem, "corpus.csv")
    dados = _membros(origem["com"])[alvo]
    zp = _reescrever(origem["com"], tmp_path / "x.zip", alterar={alvo: dados + b"\n"})
    inv = PK.inspecionar(zp)
    assert not inv["ok"] and any("alterado" in p and "corpus.csv" in p for p in inv["problemas"])
    assert [a["estado"] for a in inv["arquivos"] if a["caminho"] == alvo] == ["alterado"]
    rec = destino.receber_pacote(zp)
    with pytest.raises(IntegridadeErro):
        destino.restaurar_pacote(rec["token"])
    assert _sem_lista(destino)


def test_04_hash_incorreto_no_manifesto(origem, destino, tmp_path):
    alvo = _arq_exec(origem, "contagens.json")
    zp = _reescrever(origem["com"], tmp_path / "x.zip",
                     manifesto=lambda d: d["arquivos"][alvo].update(sha256="0" * 64))
    inv = PK.inspecionar(zp)
    assert not inv["ok"] and any("contagens.json" in p for p in inv["problemas"])
    # hash com formato inválido: o pacote é recusado já na leitura do manifesto
    zp2 = _reescrever(origem["com"], tmp_path / "y.zip", manifesto=lambda d: d["arquivos"][alvo].update(sha256="xyz"))
    with pytest.raises(PK.PacoteInvalido, match="SHA-256 inválido"):
        PK.inspecionar(zp2)


def test_04b_adulteracao_coerente_detectada_pelo_manifesto_da_execucao(origem, destino, tmp_path):
    """Quem altera um resultado E o manifesto do pacote produz um pacote 'coerente'; a restauração
    ainda detecta a diferença pelo manifesto da execução (saidas_sha256 e hash do corpus)."""
    alvo = _arq_exec(origem, "contagens.json")
    novo = b'{"corpus": 999999}'
    import hashlib
    zp = _reescrever(origem["com"], tmp_path / "x.zip", alterar={alvo: novo},
                     manifesto=lambda d: d["arquivos"][alvo].update(sha256=hashlib.sha256(novo).hexdigest()))
    rec = destino.receber_pacote(zp)
    assert rec["ok"]                                   # o pacote em si parece íntegro
    with pytest.raises(IntegridadeErro, match="não conferem com o manifesto da execução"):
        destino.restaurar_pacote(rec["token"])
    assert _sem_lista(destino)


def test_08_arquivos_inesperados(origem, destino, tmp_path):
    zp = _reescrever(origem["com"], tmp_path / "x.zip", extra={_arq_exec(origem, "extra.csv"): b"a,b\n1,2\n"})
    inv = PK.inspecionar(zp)
    assert not inv["ok"] and any("inesperado" in p and "extra.csv" in p for p in inv["problemas"])
    with pytest.raises(IntegridadeErro):
        destino.restaurar_pacote(destino.receber_pacote(zp)["token"])
    # fora da estrutura (executável, outra área, outra execução): recusado sem inventário
    for nome in ("instalar.sh", "malware.exe", "execucao/x.py", "outra/a.csv", "entradas/semhash.csv",
                 f"execucao/{origem['pasta'].name}/script.py"):
        with pytest.raises(PK.PacoteInvalido):
            PK.inspecionar(_reescrever(origem["com"], tmp_path / "y.zip", extra={nome: b"x"}))
    outra = "execucao/20200101T000000Z_aaaaaaaaaaaa/corpus.csv"
    inv = PK.inspecionar(_reescrever(origem["com"], tmp_path / "z.zip", extra={outra: b"x"},
                                     manifesto=lambda d: d["arquivos"].update({outra: {"sha256": "2d711642b726b04401627ca9fbac32f5c8530fb1903cc4db02258717921a4881"}})))
    assert not inv["ok"] and any("outra execução" in p for p in inv["problemas"])


# ---------------------------------------------------------------- 5, 6, 7: ZIP malformado ou perigoso
def test_05_zip_invalido_ou_malformado(origem, tmp_path):
    casos = {"aleatorio.zip": os.urandom(4096), "vazio.zip": b"",
             "truncado.zip": origem["com"].read_bytes()[: origem["com"].stat().st_size // 2]}
    for nome, dados in casos.items():
        (tmp_path / nome).write_bytes(dados)
        with pytest.raises(PK.PacoteInvalido):
            PK.inspecionar(tmp_path / nome)
    with pytest.raises(PK.PacoteInvalido, match="sem manifesto"):
        PK.inspecionar(_reescrever(origem["com"], tmp_path / "a.zip", remover=["manifesto.json"]))
    with pytest.raises(PK.PacoteInvalido, match="ilegível"):
        PK.inspecionar(_reescrever(origem["com"], tmp_path / "b.zip", alterar={"manifesto.json": b"{nao json"}))
    for campo in ("arquivos", "execucao", "fontes", "omitidos"):
        with pytest.raises(PK.PacoteInvalido, match=campo):
            PK.inspecionar(_reescrever(origem["com"], tmp_path / "c.zip", manifesto=lambda d, c=campo: d.pop(c)))
    with pytest.raises(PK.PacoteInvalido, match="identificação"):
        PK.inspecionar(_reescrever(origem["com"], tmp_path / "d.zip",
                                   manifesto=lambda d: d["execucao"].update(pasta="../../x")))
    # entrada corrompida (CRC) dentro de um ZIP de estrutura válida
    dados = bytearray(origem["com"].read_bytes())
    with zipfile.ZipFile(origem["com"]) as z:
        info = z.getinfo(_arq_exec(origem, "corpus.csv"))
    n_nome, n_extra = struct.unpack("<HH", dados[info.header_offset + 26: info.header_offset + 30])
    ini = info.header_offset + 30 + n_nome + n_extra        # início dos dados no cabeçalho local
    dados[ini + 10] ^= 0xFF
    (tmp_path / "crc.zip").write_bytes(bytes(dados))
    with pytest.raises(PK.PacoteInvalido, match="corrompida"):
        PK.inspecionar(tmp_path / "crc.zip")
    # duplicatas (inclusive só na caixa) e criptografia
    for nome in (_arq_exec(origem, "corpus.csv"), _arq_exec(origem, "CORPUS.csv")):
        zp = tmp_path / "dup.zip"
        shutil.copy(origem["com"], zp)
        with zipfile.ZipFile(zp, "a") as z:
            import warnings
            with warnings.catch_warnings():
                warnings.simplefilter("ignore")
                z.writestr(nome, b"x")
        with pytest.raises(PK.PacoteInvalido, match="duplicada"):
            PK.inspecionar(zp)
    # bit 0 da flag de propósito geral (criptografia) marcado no diretório central
    dados = bytearray(origem["com"].read_bytes())
    pos = dados.find(b"PK\x01\x02")
    while pos >= 0:
        n = struct.unpack("<H", dados[pos + 28: pos + 30])[0]
        if dados[pos + 46: pos + 46 + n] == b"LEIA-ME.txt":
            dados[pos + 8] |= 0x1
            break
        pos = dados.find(b"PK\x01\x02", pos + 4)
    (tmp_path / "e.zip").write_bytes(bytes(dados))
    with pytest.raises(PK.PacoteInvalido, match="criptografada"):
        PK.inspecionar(tmp_path / "e.zip")


def test_06_zip_bomb(origem, tmp_path, monkeypatch):
    nome = _arq_exec(origem, "bibliometria/bomba.csv")
    zp = _reescrever(origem["com"], tmp_path / "b.zip", extra={nome: b"0" * (60 * 1024 * 1024)})
    with pytest.raises(PK.PacoteInvalido, match="zip bomb"):
        PK.inspecionar(zp)
    # limite total descompactado e de número de entradas
    monkeypatch.setattr(PK, "MAX_DESCOMPACTADO", 1024)
    with pytest.raises(PK.PacoteInvalido, match="descompactado maior"):
        PK.inspecionar(origem["com"])
    monkeypatch.undo()
    monkeypatch.setattr(PK, "MAX_ENTRADAS", 5)
    with pytest.raises(PK.PacoteInvalido, match="entradas demais"):
        PK.inspecionar(origem["com"])
    monkeypatch.undo()
    monkeypatch.setattr(PK, "MAX_PACOTE", 1024)
    with pytest.raises(PK.PacoteInvalido, match="maior que o limite"):
        PK.inspecionar(origem["com"])


def test_06b_tamanho_declarado_falso_nao_engana_a_leitura(origem, tmp_path):
    """Cabeçalho que declara menos bytes do que a entrada tem: a leitura limitada recusa."""
    zp = tmp_path / "f.zip"
    shutil.copy(origem["com"], zp)
    alvo = _arq_exec(origem, "corpus.csv")
    with zipfile.ZipFile(zp) as z:
        info = z.getinfo(alvo)
    with zipfile.ZipFile(zp) as z:
        info.file_size = 10            # mente no diretório central (simulado em memória)
        with pytest.raises(PK.PacoteInvalido):
            PK._ler_limitado(z, info)


@pytest.mark.parametrize("nome", ["../fora.csv", "/etc/passwd", "execucao/../../fora.csv", "..\\..\\fora.csv",
                                  "C:/Windows/x.csv", "execucao//x.csv", "./manifesto.json", "entradas/.oculto.csv",
                                  "execucao/20260101T000000Z_aaaaaaaaaaaa/../../../x.csv", "nome\x00.csv"])
def test_07_path_traversal(origem, tmp_path, nome):
    alvo = tmp_path / "x.zip"
    m = _membros(origem["com"])
    with zipfile.ZipFile(alvo, "w") as z:
        for k, v in m.items():
            z.writestr(k, v)
        i = zipfile.ZipInfo("placeholder")
        i.filename = nome            # contorna a normalização do zipfile ao gravar
        z.writestr(i, b"x")
    with pytest.raises(PK.PacoteInvalido):
        PK.inspecionar(alvo)
    assert not (tmp_path.parent / "fora.csv").exists()


def test_07b_link_simbolico_e_arquivo_especial(origem, tmp_path, destino):
    for modo in (stat.S_IFLNK | 0o777, stat.S_IFCHR | 0o644, stat.S_IFIFO | 0o644):
        i = zipfile.ZipInfo(_arq_exec(origem, "graficos/link.png"))
        i.external_attr = modo << 16
        zp = _reescrever(origem["com"], tmp_path / "l.zip", infos=[(i, b"/etc/passwd")])
        with pytest.raises(PK.PacoteInvalido, match="regular"):
            PK.inspecionar(zp)
        with pytest.raises(PK.PacoteInvalido):
            destino.receber_pacote(zp)
    assert not (destino.pasta / "pacotes").exists() or not list((destino.pasta / "pacotes").glob("*.zip"))
    # o próprio pacote como link simbólico
    link = tmp_path / "link.zip"
    link.symlink_to(origem["com"])
    with pytest.raises(PK.PacoteInvalido):
        destino.receber_pacote(link)


def test_07c_extracao_nunca_escapa_do_destino(origem, tmp_path):
    """Mesmo chamando extrair() diretamente com um manifesto forjado, nomes inválidos são recusados."""
    alvo = tmp_path / "x.zip"
    m = _membros(origem["com"])
    with zipfile.ZipFile(alvo, "w") as z:
        for k, v in m.items():
            z.writestr(k, v)
        i = zipfile.ZipInfo("p")
        i.filename = "execucao/../fora.csv"
        z.writestr(i, b"x")
    (tmp_path / "dest").mkdir()
    with pytest.raises(PK.PacoteInvalido):
        PK.extrair(alvo, tmp_path / "dest", "execucao/", {"execucao/../fora.csv": {"sha256": "0" * 64}}, "execucao/")
    assert not (tmp_path / "fora.csv").exists() and not list((tmp_path / "dest").rglob("*"))


# ---------------------------------------------------------------- 9. dados originais omitidos
def test_09_dados_originais_omitidos(origem, destino):
    with zipfile.ZipFile(origem["sem"]) as z:
        nomes = z.namelist()
        manp = json.loads(z.read("manifesto.json"))
        leia = z.read("LEIA-ME.txt").decode()
    assert not [n for n in nomes if n.startswith("entradas/")]
    assert len(manp["fontes"]) == 8 and not any(f["incluido"] for f in manp["fontes"])
    assert all(re.fullmatch(r"[0-9a-f]{64}", f["sha256"]) and "licença" in f["motivo_omissao"] for f in manp["fontes"])
    assert {o["sha256"] for o in manp["omitidos"] if o["sha256"]} == {f["sha256"] for f in manp["fontes"]}
    rep = manp["reprodutibilidade"]
    assert rep["reexecucao_possivel_so_com_o_pacote"] is False and "NÃO pode ser reexecutada" in rep["declaracao"]
    assert "NÃO pode ser reexecutada" in leia and manp["fontes"][0]["sha256"] in leia
    inv = destino.receber_pacote(origem["sem"])
    assert inv["ok"] and any("NÃO pode ser reexecutada" in a for a in inv["avisos"])
    assert inv["situacao_no_projeto"]["reexecucao_possivel_apos_restaurar"] is False
    r = destino.restaurar_pacote(inv["token"])
    v = r["verificacao"]
    assert v["ok"] and v["importada"] and v["reexecucao_possivel"] is False and len(v["avisos"]) == 8
    assert destino.arquivos() == []
    with pytest.raises(ValueError, match="reexecução impossível"):
        destino.reexecutar(origem["id"])
    assert len(destino.execucoes()) == 1


def test_09b_entradas_ausentes_no_projeto_de_origem_sao_omitidas_com_motivo(tmp_path):
    p = Projeto.criar("Falta", raiz=tmp_path / "r")
    for f in sorted(pathlib.Path(gerar(str(tmp_path / "d"))).glob("*.csv"))[:2]:
        p.importar(f)
    r = p.executar(Config.corrigida(), bibliometria_=False, graficos_=False, relatorios_=False, n_sensibilidade=0)
    a = p.arquivos()[0]
    arq = p.pasta / "arquivos" / a["arquivo"]
    os.chmod(arq, 0o600)
    arq.write_text("adulterado", encoding="utf-8")
    (tmp_path / "z").mkdir()
    z = p.exportar_execucao(r["id"], tmp_path / "z")
    fontes = {f["arquivo"]: f for f in json.loads(_membros(z["arquivo"])["manifesto.json"])["fontes"]}
    assert fontes[a["nome"]]["incluido"] is False and "SHA-256" in fontes[a["nome"]]["motivo_omissao"]
    assert z["reprodutibilidade"]["reexecucao_possivel_so_com_o_pacote"] is False


# ---------------------------------------------------------------- 10. restaurar sem recalcular
def test_10_restaurar_nao_recalcula(origem, destino, monkeypatch):
    import cientometria.projetos as P

    def proibido(*a, **k):
        raise AssertionError("a restauração não pode recalcular nem reler exportações")
    for nome in ("executar_pipeline", "carregar_fontes"):
        monkeypatch.setattr(P, nome, proibido)
    monkeypatch.setattr(P.bibliometria, "analisar", proibido)
    monkeypatch.setattr(P.relatorios, "exportar", proibido)
    r = destino.restaurar_pacote(destino.receber_pacote(origem["com"])["token"])
    assert r["estado"] == "restaurada" and r["verificacao"]["ok"]
    assert [e for e in destino.historico() if e["evento"] == "execucao"] == []


# ---------------------------------------------------------------- 11. reexecutar com novo ID
def test_11_reexecutar_cria_novo_id_e_referencia_a_origem(origem, destino):
    destino.restaurar_pacote(destino.receber_pacote(origem["com"])["token"])
    antes = _sha_saidas(destino.pasta_execucao(origem["id"]))
    r = destino.reexecutar(origem["id"])
    assert r["id"] != origem["id"] and r["origem"] == origem["id"]
    man = destino.manifesto(r["id"])
    assert man["origem_execucao"]["id"] == origem["id"] and man["origem_execucao"]["importada"] is True
    assert man["versao_metodo"] == "original-2026.01" and man["rotulo"] == f"reexecução de {origem['id']}"
    assert r["comparacao"]["mesmo_corpus"] and r["comparacao"]["mesma_entrada_e_parametros"]
    assert _sha_saidas(destino.pasta_execucao(origem["id"])) == antes          # origem intacta
    assert {e["id"] for e in destino.execucoes()} == {origem["id"], r["id"]}
    ev = [e for e in destino.historico() if e["evento"] == "execucao"]
    assert ev[-1]["origem_execucao"] == origem["id"]
    # reexecutar no próprio projeto de origem também funciona e não substitui nada
    p = origem["projeto"]
    r2 = p.reexecutar(origem["id"])
    assert r2["comparacao"]["mesmo_corpus"] and p.verificar_execucao(origem["id"])["ok"]


def test_11b_reexecucao_recusa_versao_de_metodo_desconhecida(origem, destino, tmp_path):
    alvo = _arq_exec(origem, "manifesto.json")
    m = json.loads(_membros(origem["com"])[alvo])
    m["versao_metodo"] = "original-2099.01"
    m["parametros"]["metodo_versao"] = "original-2099.01"
    novo = json.dumps(m).encode()
    import hashlib
    zp = _reescrever(origem["com"], tmp_path / "v.zip", alterar={alvo: novo},
                     manifesto=lambda d: d["arquivos"][alvo].update(sha256=hashlib.sha256(novo).hexdigest()))
    r = destino.restaurar_pacote(destino.receber_pacote(zp)["token"])
    assert r["estado"] == "restaurada"                       # restaurar resultados continua possível
    with pytest.raises(ValueError, match="não existe nesta aplicação"):
        destino.reexecutar(origem["id"])


# ---------------------------------------------------------------- 12. versões do pacote
def test_12_compatibilidade_de_versoes(origem, tmp_path):
    casos = [(lambda d: d.update(versao_formato=PK.VERSAO_FORMATO + 1), "mais novo"),
             (lambda d: d.update(versao_formato=0), "inválida"),
             (lambda d: d.pop("versao_formato"), "inválida"),
             (lambda d: d.update(versao_formato="1"), "inválida"),
             (lambda d: d.update(formato="outro-formato"), "não é de um pacote")]
    for i, (f, msg) in enumerate(casos):
        with pytest.raises(PK.PacoteInvalido, match=msg):
            PK.inspecionar(_reescrever(origem["com"], tmp_path / f"v{i}.zip", manifesto=f))
    # a versão atual é aceita, e o pacote registra a versão da aplicação que o gerou
    inv = PK.inspecionar(origem["com"])
    assert inv["versao_formato"] == PK.VERSAO_FORMATO and inv["versao_aplicacao_exportacao"]
    # campos desconhecidos (acrescentados por versões futuras compatíveis) são tolerados
    inv = PK.inspecionar(_reescrever(origem["com"], tmp_path / "f.zip", manifesto=lambda d: d.update(campo_novo=1)))
    assert inv["ok"]


# ---------------------------------------------------------------- 13. importações concorrentes
def _restaurar(args):
    raiz, zp = args
    p = Projeto.abrir("destino", pathlib.Path(raiz))
    try:
        return p.restaurar_pacote(p.receber_pacote(zp)["token"])["estado"]
    except Exception as e:  # noqa: BLE001
        return f"erro: {type(e).__name__}: {e}"


def test_13_importacoes_concorrentes(origem, tmp_path):
    Projeto.criar("Destino", raiz=tmp_path / "r")
    with CTX.Pool(8) as pool:
        estados = pool.map(_restaurar, [(str(tmp_path / "r"), str(origem["com"]))] * 8)
    assert estados.count("restaurada") == 1 and estados.count("ja_existia") == 7, estados
    p = Projeto.abrir("destino", tmp_path / "r")
    assert len(p.execucoes()) == 1 and p.verificar_execucao(origem["id"])["ok"]
    assert len(p.arquivos()) == 8                       # entradas não duplicadas
    assert not list((p.pasta / "execucoes").glob(".importando_*")) and not list(p.pasta.glob(".pacote_*"))
    assert not list((p.pasta / "pacotes").glob("*.zip"))
    ev = [e["evento"] for e in p.historico()]
    assert ev.count("execucao_restaurada") == 1 and ev.count("pacote_ja_restaurado") == 7
    assert "linha_ilegivel" not in ev


def test_13b_mesmo_id_com_conteudo_diferente_e_recusado(origem, destino, tmp_path):
    destino.restaurar_pacote(destino.receber_pacote(origem["com"])["token"])
    alvo = _arq_exec(origem, "diagnosticos/campos.csv")
    novo = b"campo,ausente\nx,1\n"
    m = json.loads(_membros(origem["com"])[_arq_exec(origem, "manifesto.json")])
    import hashlib
    m["saidas_sha256"]["diagnosticos/campos.csv"] = hashlib.sha256(novo).hexdigest()
    mb = json.dumps(m).encode()

    def ed(d):
        d["arquivos"][alvo]["sha256"] = hashlib.sha256(novo).hexdigest()
        d["arquivos"][_arq_exec(origem, "manifesto.json")]["sha256"] = hashlib.sha256(mb).hexdigest()
    zp = _reescrever(origem["com"], tmp_path / "c.zip", alterar={alvo: novo, _arq_exec(origem, "manifesto.json"): mb},
                     manifesto=ed)
    inv = destino.receber_pacote(zp)
    assert inv["ok"] and inv["situacao_no_projeto"]["identica"] is False
    antes = _sha_saidas(destino.pasta_execucao(origem["id"]))
    with pytest.raises(IntegridadeErro, match="conteúdo diferente"):
        destino.restaurar_pacote(inv["token"])
    assert _sha_saidas(destino.pasta_execucao(origem["id"])) == antes


# ---------------------------------------------------------------- 14. interrupção
def test_14_interrupcao_durante_a_restauracao(origem, destino, monkeypatch):
    import cientometria.projetos as P
    original = P.PK.extrair

    def extrair_e_cair(zp, dest, prefixo, arquivos, remover):
        # grava um arquivo pela metade e "cai" no meio da extração
        (pathlib.Path(dest) / "corpus.csv").write_text("parcial", encoding="utf-8")
        raise KeyboardInterrupt("queda simulada")
    rec = destino.receber_pacote(origem["com"])
    monkeypatch.setattr(P.PK, "extrair", extrair_e_cair)
    with pytest.raises(KeyboardInterrupt):
        destino.restaurar_pacote(rec["token"])
    monkeypatch.setattr(P.PK, "extrair", original)
    assert _sem_lista(destino)                                  # nada aparece pela metade
    assert (destino.pasta / "pacotes" / f"{rec['token']}.zip").exists()   # pode tentar de novo
    r = destino.restaurar_pacote(rec["token"])
    assert r["estado"] == "restaurada" and r["verificacao"]["ok"]


def test_14b_queda_do_processo_deixa_temporarios_que_recuperar_remove(origem, destino):
    """Queda real (sem finally): pastas temporárias ficam; recuperar() as remove sem tocar resultados."""
    destino.restaurar_pacote(destino.receber_pacote(origem["com"])["token"])
    lixo = [destino.pasta / "execucoes" / f".importando_{origem['id']}_deadbeef", destino.pasta / ".pacote_deadbeef"]
    for d in lixo:
        d.mkdir()
        (d / "corpus.csv").write_text("parcial", encoding="utf-8")
    (destino.pasta / "pacotes" / ".recebendo_x").write_bytes(b"PK")
    antes = _sha_saidas(destino.pasta_execucao(origem["id"]))
    rel = destino.recuperar()
    assert not any(d.exists() for d in lixo) and len(rel["temporarios_removidos"]) == 3
    assert _sha_saidas(destino.pasta_execucao(origem["id"])) == antes and len(destino.execucoes()) == 1


# ---------------------------------------------------------------- exportação: recusas e confinamento
def test_exportacao_recusa_resultados_alterados(tmp_path):
    p = Projeto.criar("Alt", raiz=tmp_path / "r")
    for f in sorted(pathlib.Path(gerar(str(tmp_path / "d"))).glob("*.csv"))[:2]:
        p.importar(f)
    r = p.executar(Config.corrigida(), bibliometria_=False, graficos_=False, relatorios_=False, n_sensibilidade=0)
    (p.pasta_execucao(r["id"]) / "contagens.json").write_text("{}", encoding="utf-8")
    (tmp_path / "z").mkdir()
    assert p.inventario_execucao(r["id"])["exportavel"] is False
    with pytest.raises(IntegridadeErro, match="exportação recusada"):
        p.exportar_execucao(r["id"], tmp_path / "z")
    assert not list((tmp_path / "z").iterdir())


def test_exportacao_e_recebimento_confinados(origem, destino, tmp_path, monkeypatch):
    permitido = tmp_path / "permitido"
    permitido.mkdir()
    monkeypatch.setenv("CIENTOMETRIA_DIR_EXPORTACAO", str(permitido))
    with pytest.raises(ValueError, match="fora do diretório"):
        origem["projeto"].exportar_execucao(origem["id"], tmp_path)
    monkeypatch.setenv("CIENTOMETRIA_DIR_IMPORTACAO", str(permitido))
    with pytest.raises(ValueError, match="fora do diretório"):
        destino.receber_pacote(origem["com"])
    for token in ("../x", "abc", "0" * 31, "g" * 32, ""):
        with pytest.raises(ValueError, match="inválido"):
            destino.inspecionar_pacote(token)
    with pytest.raises(FileNotFoundError):
        destino.restaurar_pacote("0" * 32)


def test_inventario_e_descarte(origem, destino):
    inv = origem["projeto"].inventario_execucao(origem["id"], incluir_entradas=False)
    assert inv["exportavel"] and not inv["reexecucao_possivel_so_com_o_pacote"]
    assert not [a for a in inv["arquivos"] if a["caminho"].startswith("entradas/")]
    rec = destino.receber_pacote(origem["com"])
    assert destino.inspecionar_pacote(rec["token"])["ok"]
    destino.descartar_pacote(rec["token"])
    with pytest.raises(FileNotFoundError):
        destino.restaurar_pacote(rec["token"])
    assert destino.execucoes() == [] and destino.arquivos() == []
    assert [e["evento"] for e in destino.historico()][-2:] == ["pacote_recebido", "pacote_descartado"]


def test_api_despachar(origem, tmp_path):
    raiz = str(tmp_path / "r")
    despachar("criar_projeto", {"nome": "Api", "raiz": raiz})
    rec = despachar("receber_pacote", {"projeto": "api", "raiz": raiz, "caminho": str(origem["sem"])})
    assert rec["ok"] and rec["token"]
    r = despachar("restaurar_pacote", {"projeto": "api", "raiz": raiz, "token": rec["token"]})
    assert r["estado"] == "restaurada"
    lst = despachar("execucoes", {"projeto": "api", "raiz": raiz})["execucoes"]
    assert lst[0]["importada"] and lst[0]["projeto_origem"] == "origem"


def test_cli(origem, tmp_path, capsys):
    from cientometria.api import principal_cli
    raiz = str(tmp_path / "r")
    principal_cli(["--raiz", raiz, "projeto-criar", "Cli"])
    principal_cli(["--raiz", raiz, "verificar-pacote", str(origem["com"])])
    principal_cli(["--raiz", raiz, "importar-pacote", "cli", str(origem["com"])])
    principal_cli(["--raiz", raiz, "reexecutar", "cli", origem["id"]])
    principal_cli(["--raiz", raiz, "exportar", "cli", origem["id"], "--sem-entradas", "--saida", str(tmp_path)])
    saida = capsys.readouterr().out
    assert '"restaurada"' in saida and '"mesmo_corpus": true' in saida
    assert list(tmp_path.glob(f"execucao_{origem['id']}_cli_sem-entradas.zip"))
    ruim = _reescrever(origem["com"], tmp_path / "ruim.zip", remover=[_arq_exec(origem, "corpus.csv")])
    with pytest.raises(SystemExit) as e:
        principal_cli(["--raiz", raiz, "verificar-pacote", str(ruim)])
    assert e.value.code == 2


# ---------------------------------------------------------------- endpoints PHP
php = shutil.which("php")


@pytest.mark.skipif(not php, reason="requer php")
def test_endpoints_php(origem, tmp_path):
    import requests
    from .test_seguranca import _porta_livre, _sessao
    import subprocess
    import time
    raiz = tmp_path / "projetos"
    porta = _porta_livre()
    env = dict(os.environ, CIENTOMETRIA_PROJETOS=str(raiz), PHP_CLI_SERVER_WORKERS="2")
    proc = subprocess.Popen([php, "-d", "upload_max_filesize=64M", "-d", "post_max_size=64M", "-S",
                             f"127.0.0.1:{porta}", "router.php"], cwd=pathlib.Path(__file__).resolve().parents[1],
                            env=env, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    base = f"http://127.0.0.1:{porta}"
    try:
        for _ in range(50):
            try:
                requests.get(base + "/", timeout=1)
                break
            except requests.ConnectionError:
                time.sleep(.1)
        s, _ = _sessao(base)
        assert s.post(base + "/api.php?acao=criar_projeto", json={"nome": "Web"}).status_code == 200
        up = lambda nome, dados, projeto="web": s.post(  # noqa: E731
            base + "/api.php?acao=receber_pacote", data={"projeto": projeto}, files={"pacote": (nome, dados)})
        # sem CSRF: recusado antes de qualquer processamento
        r = requests.post(base + "/api.php?acao=receber_pacote", data={"projeto": "web"},
                          files={"pacote": ("a.zip", origem["com"].read_bytes())})
        assert r.status_code == 403
        assert up("a.php", b"<?php").status_code == 415
        assert up("a.zip", b"PK", projeto="../x").status_code == 400
        assert up("a.zip", os.urandom(100)).status_code == 422
        # caminho arbitrário via JSON não é aceito para receber/exportar
        r = s.post(base + "/api.php?acao=receber_pacote", json={"projeto": "web", "caminho": "/etc/passwd"})
        assert r.status_code == 400
        r = up("pacote.zip", origem["com"].read_bytes())
        assert r.status_code == 200, r.text
        inv = r.json()
        assert inv["ok"] and str(raiz) not in r.text and str(origem["com"]) not in r.text
        r = s.post(base + "/api.php?acao=restaurar_pacote", json={"projeto": "web", "token": inv["token"]})
        assert r.status_code == 200 and r.json()["estado"] == "restaurada"
        # exportação: devolve o ZIP, com nome controlado e SHA-256 no cabeçalho
        r = s.post(base + "/api.php?acao=exportar_execucao",
                   json={"projeto": "web", "id": origem["id"], "incluir_entradas": False, "destino": "/tmp"})
        assert r.status_code == 200 and r.headers["content-type"] == "application/zip"
        assert re.fullmatch(r'attachment; filename="execucao_[0-9a-f]{12}_web_sem-entradas\.zip"',
                            r.headers["content-disposition"])
        import hashlib
        assert hashlib.sha256(r.content).hexdigest() == r.headers["x-pacote-sha256"]
        assert PK.inspecionar(_salvar(tmp_path / "b.zip", r.content))["ok"]
        for corpo in ({"projeto": "web", "id": "../../x"}, {"projeto": "../x", "id": origem["id"]}):
            assert s.post(base + "/api.php?acao=exportar_execucao", json=corpo).status_code == 400
        r = s.post(base + "/api.php?acao=exportar_execucao", json={"projeto": "web", "id": "0" * 12})
        assert r.status_code == 422 and "erro" in r.json()
        # nenhum temporário de exportação/upload deixado para trás no projeto
        assert not list((raiz / "web").rglob(".importando_*")) and not list((raiz / "web" / "pacotes").glob("*.zip"))
    finally:
        proc.terminate()
        proc.wait(5)


def _salvar(p, dados):
    p.write_bytes(dados)
    return p


def test_leitura_limitada_de_entrada_unica(tmp_path):
    """Sanidade do leitor em blocos: lê exatamente o declarado e devolve o SHA-256 correto."""
    zp = tmp_path / "a.zip"
    with zipfile.ZipFile(zp, "w") as z:
        z.writestr("LEIA-ME.txt", b"abc" * 1000)
    with zipfile.ZipFile(zp) as z:
        sha, n = PK._ler_limitado(z, z.getinfo("LEIA-ME.txt"), io.BytesIO())
    import hashlib
    assert n == 3000 and sha == hashlib.sha256(b"abc" * 1000).hexdigest()
