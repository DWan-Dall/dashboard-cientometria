"""Exportação e importação de uma execução como .zip (cientometria/pacote.py).

Cobre: ida e volta (exportar → importar → verificar_execucao ok), com e sem as exportações de
entrada; pacote adulterado (arquivo alterado, acrescentado, removido, manifesto sem hashes, corpus
alterado com hashes recalculados); caminhos perigosos ('..', absolutos, '\\', links simbólicos);
bomba de descompactação (limite declarado e tamanho falsificado no cabeçalho); ID repetido; e a
superfície HTTP (CSRF, extensão, limite, download). Ver docs/SEGURANCA.md, V11."""
import io
import json
import os
import pathlib
import re
import stat
import struct
import zipfile

import pytest

from cientometria import Config
from cientometria.pacote import PacoteInvalido, exportar, importar
from cientometria.projetos import IntegridadeErro, Projeto
from .sinteticos import gerar
from .test_seguranca import _sessao, precisa_php, servidor  # noqa: F401 — fixture reutilizada


# ---------------------------------------------------------------- utilitários
@pytest.fixture(scope="module")
def origem(tmp_path_factory):
    """Projeto com uma execução completa (gráficos e relatórios incluídos)."""
    raiz = tmp_path_factory.mktemp("raiz_origem")
    p = Projeto.criar("Origem", raiz=raiz)
    for f in sorted(pathlib.Path(gerar(str(tmp_path_factory.mktemp("b")))).glob("*.csv")):
        p.importar(f)
    r = p.executar(Config.original(), n_sensibilidade=50, rotulo="para exportar")
    return p, r["id"]


@pytest.fixture(scope="module")
def pacote_zip(origem, tmp_path_factory):
    p, id_ = origem
    destino = tmp_path_factory.mktemp("zips")
    info = exportar(p, id_, destino)
    return destino / info["arquivo"], info


@pytest.fixture()
def destino(tmp_path):
    return Projeto.criar("Destino", raiz=tmp_path / "raiz")


def _membros(caminho):
    with zipfile.ZipFile(caminho) as z:
        return [(zi, z.read(zi)) for zi in z.infolist()]


def _reescrever(origem_zip, saida, alterar=None, remover=(), extras=()):
    """Copia um .zip mudando/omitindo membros. `alterar`: função (nome, bytes) -> bytes."""
    with zipfile.ZipFile(saida, "w", zipfile.ZIP_DEFLATED) as z:
        for zi, dados in _membros(origem_zip):
            if zi.filename in remover:
                continue
            z.writestr(zi, alterar(zi.filename, dados) if alterar else dados)
        for item in extras:
            if isinstance(item, zipfile.ZipInfo):
                z.writestr(item, b"x")
            else:
                z.writestr(item[0], item[1])
    return saida


def _sem_residuos(projeto):
    execs = projeto.pasta / "execucoes"
    assert projeto.execucoes() == []
    assert not list(execs.glob(".importando_*"))
    assert not (execs / ".importadas").exists() or not list((execs / ".importadas").iterdir())


def _pasta(caminho_zip):
    return next(zi.filename.split("/")[0] for zi, _ in _membros(caminho_zip) if "/" in zi.filename
                and not zi.filename.startswith("entradas/"))


# ---------------------------------------------------------------- ida e volta
def test_ida_e_volta_verifica_ok(pacote_zip, origem, destino):
    caminho, info = pacote_zip
    p, id_ = origem
    nomes = [zi.filename for zi, _ in _membros(caminho)]
    pasta = info["pasta"]
    for obrig in ("manifesto.json", "corpus.csv", "consolidado.csv", "contagens.json",
                  "diagnosticos/diagnosticos.json", "bibliometria/cobertura.csv", "graficos/01-fluxo.png",
                  "relatorios/resultados.xlsx", "relatorios/relatorio_metodologico.md"):
        assert f"{pasta}/{obrig}" in nomes, obrig
    assert "LEIA-ME.txt" in nomes and "SHA256SUMS.txt" in nomes
    assert not any(n.startswith("entradas/") for n in nomes)      # padrão: sem dados licenciados

    r = importar(destino, caminho)
    assert r["id"] == id_ and r["verificacao"]["ok"] is True, r["verificacao"]
    assert r["verificacao"]["importada"] is True and r["verificacao"]["avisos"]  # entradas não incluídas
    v = destino.verificar_execucao(id_)
    assert v["ok"] and v["problemas"] == []
    # byte a byte igual à pasta de origem; somente leitura
    a, b = p.pasta_execucao(id_), destino.pasta_execucao(id_)
    arqs = sorted(x.relative_to(a) for x in a.rglob("*") if x.is_file())
    assert arqs == sorted(x.relative_to(b) for x in b.rglob("*") if x.is_file())
    for rel in arqs:
        assert (a / rel).read_bytes() == (b / rel).read_bytes()
        assert (b / rel).stat().st_mode & 0o777 == 0o444
    # marcada como importada na lista e no histórico
    ex = destino.execucoes()
    assert len(ex) == 1 and ex[0]["importada"] is True and ex[0]["id"] == id_
    assert any(e["evento"] == "execucao_importada" and e["id"] == id_ for e in destino.historico())
    assert not any(x.get("importada") for x in p.execucoes())
    # reproduzir uma execução importada sem entradas: erro explicativo, nada é criado
    with pytest.raises(ValueError, match="importada"):
        destino.reproduzir(id_)


def test_leia_me_e_somas(pacote_zip, origem, tmp_path):
    caminho, info = pacote_zip
    p, id_ = origem
    man = p.manifesto(id_)
    with zipfile.ZipFile(caminho) as z:
        leia = z.read("LEIA-ME.txt").decode("utf-8")
        somas = z.read("SHA256SUMS.txt").decode("utf-8")
        z.extractall(tmp_path / "x")
    for esperado in (id_, man["versao_metodo"], man["versao_aplicacao"], man["hash_corpus"],
                     info["sha256_manifesto"], "sha256sum -c SHA256SUMS.txt", "NÃO (padrão)"):
        assert esperado in leia, esperado
    # equivalente ao `sha256sum -c`: toda linha confere
    import hashlib
    linhas = somas.strip().splitlines()
    assert len(linhas) == len(man["saidas_sha256"]) + 1
    for linha in linhas:
        sha, rel = linha.split("  ", 1)
        assert hashlib.sha256((tmp_path / "x" / rel).read_bytes()).hexdigest() == sha, rel


def test_ida_e_volta_com_entradas(origem, destino, tmp_path):
    p, id_ = origem
    info = exportar(p, id_, tmp_path, incluir_entradas=True)
    assert info["arquivo"].endswith("_com_entradas.zip") and info["entradas_incluidas"] == 8
    with zipfile.ZipFile(tmp_path / info["arquivo"]) as z:
        assert "SIM (8 arquivo(s)" in z.read("LEIA-ME.txt").decode()
        assert len([n for n in z.namelist() if n.startswith("entradas/")]) == 8
    r = importar(destino, tmp_path / info["arquivo"])
    assert r["verificacao"]["ok"] and r["verificacao"]["avisos"] == []
    # entrada importada adulterada depois: verificar_execucao acusa
    ent = next((destino.pasta / "execucoes" / ".importadas" / r["pasta"] / "entradas").iterdir())
    os.chmod(ent, 0o644)
    ent.write_bytes(ent.read_bytes() + b"\n")
    v = destino.verificar_execucao(id_)
    assert not v["ok"] and any("entrada importada alterada" in x for x in v["problemas"])


def test_reexportar_execucao_importada(origem, destino, tmp_path):
    p, id_ = origem
    info = exportar(p, id_, tmp_path / "a", incluir_entradas=True)
    importar(destino, tmp_path / "a" / info["arquivo"])
    de_novo = exportar(destino, id_, tmp_path / "b", incluir_entradas=True)
    terceiro = Projeto.criar("Terceiro", raiz=destino.pasta.parent)
    assert importar(terceiro, tmp_path / "b" / de_novo["arquivo"])["verificacao"]["ok"]


# ---------------------------------------------------------------- adulteração
def _corpus_alterado(nome, dados):
    """Altera o título do primeiro registro (coluna coberta por hash_corpus)."""
    if nome.count("/") == 1 and nome.endswith("/corpus.csv"):
        cab, resto = dados.split(b"\n", 1)
        assert b",title," in cab
        return cab + b"\n" + resto.replace(b"flood", b"fl00d", 1)
    return dados


@pytest.mark.parametrize("caso", ["corpus_alterado", "relatorio_alterado", "png_alterado", "arquivo_acrescentado",
                                  "arquivo_removido", "manifesto_ausente", "manifesto_sem_hashes",
                                  "corpus_alterado_com_hashes_recalculados"])
def test_pacote_adulterado_e_recusado(pacote_zip, destino, tmp_path, caso):
    caminho, info = pacote_zip
    pasta = info["pasta"]
    saida = tmp_path / "adulterado.zip"
    if caso == "corpus_alterado":
        _reescrever(caminho, saida, _corpus_alterado)
    elif caso == "relatorio_alterado":
        _reescrever(caminho, saida, lambda n, d: d + b"\n" if n.endswith("relatorio_metodologico.md") else d)
    elif caso == "png_alterado":
        _reescrever(caminho, saida, lambda n, d: d[:-1] + bytes([d[-1] ^ 1]) if n.endswith("01-fluxo.png") else d)
    elif caso == "arquivo_acrescentado":
        _reescrever(caminho, saida, extras=[(f"{pasta}/relatorios/extra.csv", b"a,b\n1,2\n")])
    elif caso == "arquivo_removido":
        _reescrever(caminho, saida, remover={f"{pasta}/relatorios/resultados.xlsx"})
    elif caso == "manifesto_ausente":       # o cenário da auditoria: relatórios sem manifesto
        _reescrever(caminho, saida, remover={f"{pasta}/manifesto.json"})
    elif caso == "manifesto_sem_hashes":
        def sem(n, d):
            if n.endswith("/manifesto.json"):
                m = json.loads(d)
                m.pop("saidas_sha256")
                return json.dumps(m).encode()
            return d
        _reescrever(caminho, saida, sem)
    else:
        # adulterador cuidadoso: altera o corpus e recalcula o SHA-256 no manifesto. O hash do corpus
        # (recalculado a partir de corpus.csv) denuncia a alteração.
        import hashlib
        novo = {}

        def alt(n, d):
            if n.count("/") == 1 and n.endswith("/corpus.csv"):
                d = _corpus_alterado(n, d)
                novo["sha"] = hashlib.sha256(d).hexdigest()
            return d
        _reescrever(caminho, tmp_path / "meio.zip", alt)

        def man(n, d):
            if n.endswith("/manifesto.json"):
                m = json.loads(d)
                m["saidas_sha256"]["corpus.csv"] = novo["sha"]
                return json.dumps(m).encode()
            return d
        _reescrever(tmp_path / "meio.zip", saida, man)
    with pytest.raises((IntegridadeErro, PacoteInvalido)) as e:
        importar(destino, saida)
    if caso == "corpus_alterado_com_hashes_recalculados":
        assert "hash do corpus" in str(e.value)
    _sem_residuos(destino)


def test_entrada_que_nao_consta_do_manifesto_e_recusada(pacote_zip, destino, tmp_path):
    caminho, _ = pacote_zip
    saida = _reescrever(caminho, tmp_path / "x.zip", extras=[("entradas/abc__lens-export.csv", b"Title\nx\n")])
    with pytest.raises(IntegridadeErro, match="não consta do manifesto"):
        importar(destino, saida)
    _sem_residuos(destino)


def test_exportacao_recusa_execucao_adulterada(origem, tmp_path):
    p, _ = origem
    # execução própria (não altera a do módulo)
    r = p.executar(Config.original(), n_sensibilidade=0, bibliometria_=False, graficos_=False, relatorios_=False,
                   revisao_duplicatas=False)
    c = pathlib.Path(r["pasta"]) / "contagens.json"
    c.write_text(c.read_text() + " ")
    with pytest.raises(IntegridadeErro, match="não conferem"):
        exportar(p, r["id"], tmp_path)
    assert not list(tmp_path.iterdir())


# ---------------------------------------------------------------- caminhos perigosos
def _zip_com_nome(caminho_zip, saida, nome, conteudo=b"x", modo=None):
    zi = zipfile.ZipInfo(nome)
    if modo is not None:
        zi.create_system = 3
        zi.external_attr = modo << 16
    with zipfile.ZipFile(saida, "w") as z:
        for zi0, dados in _membros(caminho_zip):
            z.writestr(zi0, dados)
        z.writestr(zi, conteudo)
    return saida


@pytest.mark.parametrize("nome", ["../fora.txt", "../../../../tmp/fora.txt", "/tmp/fora.txt", "{p}/../../fora.txt",
                                  "{p}/relatorios/../../../fora.txt", "C:/fora.txt", "{p}\\..\\fora.txt",
                                  "{p}/./x.csv", "{p}//x.csv", "entradas/sub/x.csv", "outra/x.csv",
                                  "{p}/.oculto", "{p}/n\u00e3o.csv", "x.txt"])
def test_caminho_perigoso_e_recusado(pacote_zip, destino, tmp_path, nome):
    caminho, info = pacote_zip
    nome = nome.replace("{p}", info["pasta"])
    saida = _zip_com_nome(caminho, tmp_path / "perigoso.zip", nome)
    with pytest.raises(PacoteInvalido):
        importar(destino, saida)
    _sem_residuos(destino)
    assert not (tmp_path / "fora.txt").exists() and not pathlib.Path("/tmp/fora.txt").exists()
    assert not (destino.pasta.parent / "fora.txt").exists()


@pytest.mark.parametrize("onde", ["{p}/relatorios/link.csv", "entradas/link.csv"])
def test_link_simbolico_no_zip_e_recusado(pacote_zip, destino, tmp_path, onde):
    caminho, info = pacote_zip
    saida = _zip_com_nome(caminho, tmp_path / "link.zip", onde.replace("{p}", info["pasta"]),
                          b"../../../../../../etc/passwd", modo=stat.S_IFLNK | 0o777)
    with pytest.raises(PacoteInvalido, match="link simbólico"):
        importar(destino, saida)
    _sem_residuos(destino)


def test_arquivo_especial_e_duas_pastas_recusados(pacote_zip, destino, tmp_path):
    caminho, info = pacote_zip
    saida = _zip_com_nome(caminho, tmp_path / "fifo.zip", f"{info['pasta']}/fifo", modo=stat.S_IFIFO | 0o644)
    with pytest.raises(PacoteInvalido, match="especial"):
        importar(destino, saida)
    outra = "20200101T000000Z_0123456789ab/manifesto.json"
    saida = _zip_com_nome(caminho, tmp_path / "duas.zip", outra, b"{}")
    with pytest.raises(PacoteInvalido, match="exatamente uma pasta"):
        importar(destino, saida)
    # nome duplicado (só a caixa difere)
    saida = _zip_com_nome(caminho, tmp_path / "dup.zip", f"{info['pasta']}/CORPUS.csv")
    with pytest.raises(PacoteInvalido, match="duplicado"):
        importar(destino, saida)
    _sem_residuos(destino)


def test_pacote_por_link_simbolico_ou_fora_do_diretorio_permitido(pacote_zip, destino, tmp_path, monkeypatch):
    caminho, _ = pacote_zip
    link = tmp_path / "link.zip"
    link.symlink_to(caminho)
    with pytest.raises(PacoteInvalido):
        importar(destino, link)
    permitido = tmp_path / "up"
    permitido.mkdir()
    monkeypatch.setenv("CIENTOMETRIA_DIR_IMPORTACAO", str(permitido))
    with pytest.raises(ValueError, match="fora do diretório"):
        importar(destino, caminho)
    nao_zip = permitido / "x.zip"
    nao_zip.write_bytes(b"isto nao e zip")
    with pytest.raises(PacoteInvalido, match="não é um .zip"):
        importar(destino, nao_zip)
    _sem_residuos(destino)


# ---------------------------------------------------------------- bomba de descompactação
def test_zip_bomba_recusado_antes_de_extrair(pacote_zip, destino, tmp_path, monkeypatch):
    caminho, info = pacote_zip
    monkeypatch.setenv("CIENTOMETRIA_MAX_MB_DESCOMPACTADO", "8")
    bomba = _reescrever(caminho, tmp_path / "bomba.zip",
                        extras=[(f"{info['pasta']}/relatorios/zeros.csv", b"0" * (64 * 1024 * 1024))])
    assert bomba.stat().st_size < 3 * 1024 * 1024        # 64 MiB de zeros cabem em poucos KiB
    with pytest.raises(PacoteInvalido, match="excede o limite"):
        importar(destino, bomba)
    _sem_residuos(destino)


def test_zip_bomba_com_tamanho_falsificado_no_cabecalho(pacote_zip, destino, tmp_path):
    """O cabeçalho declara 10 bytes, mas o membro descompacta 32 MiB: a extração conta os bytes reais."""
    caminho, info = pacote_zip
    nome = f"{info['pasta']}/relatorios/zeros.csv"
    bomba = _reescrever(caminho, tmp_path / "bomba.zip", extras=[(nome, b"0" * (32 * 1024 * 1024))])
    dados = bytearray(bomba.read_bytes())
    alvo = nome.encode()
    real = 32 * 1024 * 1024
    trocas = 0
    for assinatura, desl_tam, desl_nome in ((b"PK\x03\x04", 22, 30), (b"PK\x01\x02", 24, 46)):
        for m in re.finditer(re.escape(assinatura), dados):
            i = m.start()
            if dados[i + desl_nome:i + desl_nome + len(alvo)] == alvo:
                assert struct.unpack_from("<I", dados, i + desl_tam)[0] == real
                struct.pack_into("<I", dados, i + desl_tam, 10)
                trocas += 1
    assert trocas == 2
    bomba.write_bytes(bytes(dados))
    with zipfile.ZipFile(bomba) as z:
        assert z.getinfo(nome).file_size == 10
    with pytest.raises(PacoteInvalido):
        importar(destino, bomba)
    _sem_residuos(destino)


def test_limite_de_membros_e_de_tamanho_do_zip(pacote_zip, destino, tmp_path, monkeypatch):
    caminho, _ = pacote_zip
    monkeypatch.setenv("CIENTOMETRIA_MAX_MEMBROS_ZIP", "10")
    with pytest.raises(PacoteInvalido, match="membros"):
        importar(destino, caminho)
    monkeypatch.delenv("CIENTOMETRIA_MAX_MEMBROS_ZIP")
    monkeypatch.setenv("CIENTOMETRIA_MAX_MB_ZIP", "1")
    with pytest.raises(PacoteInvalido, match="excede o limite"):
        importar(destino, caminho)
    _sem_residuos(destino)


# ---------------------------------------------------------------- ID repetido
def test_id_repetido_nao_sobrescreve(pacote_zip, origem, destino, tmp_path):
    caminho, info = pacote_zip
    p, id_ = origem
    importar(destino, caminho)
    pasta = destino.pasta_execucao(id_)
    antes = {x: x.read_bytes() for x in pasta.rglob("*") if x.is_file()}
    # mesmo ID, conteúdo diferente (e coerente): continua recusado
    outro = _reescrever(caminho, tmp_path / "outro.zip",
                        lambda n, d: d.replace(b"para exportar", b"OUTRO") if n.endswith("manifesto.json") else d)
    for z in (caminho, outro):
        with pytest.raises(FileExistsError, match="nada foi importado nem sobrescrito"):
            importar(destino, z)
    assert {x: x.read_bytes() for x in pasta.rglob("*") if x.is_file()} == antes
    assert len(destino.execucoes()) == 1
    assert len([e for e in destino.historico() if e["evento"] == "execucao_importada"]) == 1
    # no projeto de origem (onde a execução foi gerada) também é recusado
    with pytest.raises(FileExistsError):
        importar(p, caminho)
    assert not list((p.pasta / "execucoes").glob(".importando_*"))


def test_recuperar_remove_importacao_interrompida(destino):
    tmp = destino.pasta / "execucoes" / ".importando_abc"
    (tmp / "x").mkdir(parents=True)
    (tmp / "x" / "a.csv").write_text("a")
    os.chmod(tmp / "x" / "a.csv", 0o444)
    rel = destino.recuperar()
    assert ".importando_abc" in rel["temporarios_removidos"] and not tmp.exists()


def test_cli_exportar_e_importar(origem, tmp_path):
    import subprocess
    import sys
    p, id_ = origem
    raiz = p.pasta.parent
    base = [sys.executable, "-m", "cientometria", "--raiz", str(raiz)]
    out = subprocess.run(base + ["exportar-execucao", p.pasta.name, id_, "--destino", str(tmp_path)],
                         capture_output=True, text=True, check=True)
    arq = tmp_path / json.loads(out.stdout)["arquivo"]
    Projeto.criar("Cli", raiz=raiz)
    out = subprocess.run(base + ["importar-execucao", "cli", str(arq)], capture_output=True, text=True, check=True)
    assert json.loads(out.stdout)["verificacao"]["ok"] is True
    out = subprocess.run(base + ["verificar-execucao", "cli", id_], capture_output=True, text=True, check=True)
    assert json.loads(out.stdout)["ok"] is True


# ---------------------------------------------------------------- HTTP (PHP)
@pytest.fixture(scope="module")
def web_execucao(servidor, tmp_path_factory):  # noqa: F811
    base, raiz = servidor
    s, _ = _sessao(base)
    assert s.post(base + "/api.php?acao=criar_projeto", json={"nome": "Zip Web"}).status_code == 200
    pasta = gerar(str(tmp_path_factory.mktemp("bz")))
    arquivos = [("files[]", (f.name, f.read_bytes())) for f in sorted(pathlib.Path(pasta).glob("*.csv"))]
    assert s.post(base + "/api.php?acao=importar", data={"projeto": "zip-web"}, files=arquivos).status_code == 200
    r = s.post(base + "/api.php?acao=executar", json={"projeto": "zip-web", "params": {"modo": "original",
                                                                                       "n_sensibilidade": 0}})
    assert r.status_code == 200, r.text[:300]
    return base, raiz, r.json()["manifesto"]["id"]


@precisa_php
def test_http_exportar_e_importar(web_execucao, tmp_path):
    import requests
    base, raiz, id_ = web_execucao
    s, _ = _sessao(base)
    # exige CSRF e POST
    assert requests.post(base + "/api.php?acao=exportar_execucao", json={"projeto": "zip-web", "id": id_}
                         ).status_code == 403
    assert s.get(base + "/api.php?acao=exportar_execucao").status_code == 405
    # parâmetros validados antes do Python
    for corpo in ({"projeto": "../zip-web", "id": id_}, {"projeto": "zip-web", "id": "../../x"},
                  {"projeto": "zip-web", "id": id_ + "/.."}):
        assert s.post(base + "/api.php?acao=exportar_execucao", json=corpo).status_code == 400
    r = s.post(base + "/api.php?acao=exportar_execucao", json={"projeto": "zip-web", "id": id_})
    assert r.status_code == 200 and r.headers["Content-Type"] == "application/zip"
    assert re.fullmatch(r'attachment; filename="\d{8}T\d{6}Z_[0-9a-f]{12}\.zip"', r.headers["Content-Disposition"])
    assert r.headers["X-Cientometria-Entradas"] == "0"
    z = zipfile.ZipFile(io.BytesIO(r.content))
    assert not any(n.startswith("entradas/") for n in z.namelist())
    import hashlib
    assert hashlib.sha256(r.content).hexdigest() == r.headers["X-Cientometria-Sha256"]
    # o .zip temporário não fica no disco nem dentro do projeto
    assert not list(pathlib.Path(raiz).rglob("*.zip"))
    com = s.post(base + "/api.php?acao=exportar_execucao", json={"projeto": "zip-web", "id": id_,
                                                                 "incluir_entradas": True})
    assert com.headers["X-Cientometria-Entradas"] == "8"
    # incluir_entradas só com booleano verdadeiro
    texto = s.post(base + "/api.php?acao=exportar_execucao", json={"projeto": "zip-web", "id": id_,
                                                                   "incluir_entradas": "true"})
    assert texto.headers["X-Cientometria-Entradas"] == "0"

    s.post(base + "/api.php?acao=criar_projeto", json={"nome": "Zip Destino"})
    up = lambda nome, dados, proj="zip-destino": s.post(  # noqa: E731
        base + "/api.php?acao=importar_execucao", data={"projeto": proj}, files={"files[]": (nome, dados)})
    assert requests.post(base + "/api.php?acao=importar_execucao", data={"projeto": "zip-destino"},
                         files={"files[]": ("a.zip", r.content)}).status_code == 403
    assert up("execucao.csv", r.content).status_code == 415             # só .zip
    assert up("a.zip", r.content, "../zip-destino").status_code == 400
    ok = up("../../evil.zip", r.content)
    assert ok.status_code == 200, ok.text[:300]
    j = ok.json()
    assert j["verificacao"]["ok"] is True and j["execucoes"][0]["importada"] is True
    assert j["importacao"]["arquivo_zip"] == "evil.zip"
    assert str(raiz) not in ok.text
    # repetido: recusado, nada sobrescrito
    rep = up("b.zip", com.content)
    assert rep.status_code == 422 and "nada foi importado nem sobrescrito" in rep.json()["erro"]
    # adulterado
    buf = io.BytesIO()
    with zipfile.ZipFile(io.BytesIO(r.content)) as zi, zipfile.ZipFile(buf, "w", zipfile.ZIP_DEFLATED) as zo:
        for m in zi.infolist():
            d = zi.read(m)
            zo.writestr(m, d + b" " if m.filename.endswith("contagens.json") else d)
    s.post(base + "/api.php?acao=criar_projeto", json={"nome": "Zip Outro"})
    ruim = up("x.zip", buf.getvalue(), "zip-outro")
    assert ruim.status_code == 422 and "não conferem" in ruim.json()["erro"]
    assert s.post(base + "/api.php?acao=execucoes", json={"projeto": "zip-outro"}).json()["execucoes"] == []
    # erro de exportação volta como JSON
    e = s.post(base + "/api.php?acao=exportar_execucao", json={"projeto": "zip-web", "id": "0" * 12})
    assert e.status_code == 422 and "não encontrada" in e.json()["erro"]


@precisa_php
def test_http_limites_e_temporarios_removidos(tmp_path):
    """CIENTOMETRIA_MAX_MB_ZIP aplicado no PHP (antes de chegar ao Python) e nenhum upload esquecido no
    diretório temporário quando a requisição é recusada no meio (V12: exit() do PHP não executa finally)."""
    import subprocess
    import time
    import requests
    from .test_seguranca import RAIZ, _porta_livre, php
    porta = _porta_livre()
    env = dict(os.environ, CIENTOMETRIA_PROJETOS=str(tmp_path / "p"), CIENTOMETRIA_DIR_UPLOAD=str(tmp_path / "u"),
               CIENTOMETRIA_MAX_MB_ZIP="1")
    proc = subprocess.Popen([php, "-d", "upload_max_filesize=64M", "-d", "post_max_size=64M", "-S",
                             f"127.0.0.1:{porta}", "router.php"], cwd=RAIZ, env=env,
                            stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    base = f"http://127.0.0.1:{porta}"
    try:
        for _ in range(50):
            try:
                requests.get(base + "/", timeout=1)
                break
            except requests.ConnectionError:
                time.sleep(.1)
        s, _ = _sessao(base)
        s.post(base + "/api.php?acao=criar_projeto", json={"nome": "L"})
        r = s.post(base + "/api.php?acao=importar_execucao", data={"projeto": "l"},
                   files={"files[]": ("a.zip", os.urandom(2 * 1024 * 1024))})
        assert r.status_code == 413
        dois = [("files[]", ("a.zip", b"PK")), ("files[]", ("b.zip", b"PK"))]
        assert s.post(base + "/api.php?acao=importar_execucao", data={"projeto": "l"}, files=dois).status_code == 413
        # V12: o 1º arquivo (exportação licenciada) já tinha sido movido quando o 2º foi recusado
        r = s.post(base + "/api.php?acao=importar", data={"projeto": "l"},
                   files=[("files[]", ("lens-export.csv", b"Title,DOI\nLICENCIADO,10.1/a\n")),
                          ("files[]", ("x.php", b"<?php"))])
        assert r.status_code == 415
        assert not [x for x in (tmp_path / "u").rglob("*") if x.is_file()]   # temporários removidos
    finally:
        proc.terminate()
        proc.wait(5)
