"""Segurança: isolamento de projetos, validação de arquivos, API PHP (CSRF, origem,
autenticação, roteamento) e acesso a relatórios.

Os testes HTTP sobem `php -S` com router.php numa porta livre e são pulados se o PHP
não estiver instalado."""
import io
import os
import pathlib
import re
import shutil
import socket
import subprocess
import time
import zipfile

import pytest

from cientometria import Config
from cientometria.ingestao import ArquivoInvalido, validar_conteudo
from cientometria.projetos import Projeto
from .sinteticos import gerar

RAIZ = pathlib.Path(__file__).resolve().parents[1]


# ---------------------------------------------------------------- Python
@pytest.fixture()
def proj(tmp_path):
    return Projeto.criar("Seguro", raiz=tmp_path / "raiz")


@pytest.mark.parametrize("slug", ["../raiz/seguro", "..", "a/b", "/etc", "Seguro", "", "x" * 90, "seguro\x00"])
def test_slug_invalido_rejeitado(proj, slug):
    with pytest.raises(ValueError):
        Projeto.abrir(slug, proj.pasta.parent)


@pytest.mark.parametrize("id_", ["../../x", "abc", "0123456789ab/..", "*", ""])
def test_id_de_execucao_invalido(proj, id_):
    with pytest.raises(ValueError):
        proj.pasta_execucao(id_)


def test_importacao_confinada_ao_diretorio_permitido(proj, tmp_path, monkeypatch):
    fora = tmp_path / "fora.csv"
    fora.write_text("Title,DOI\nflood,10.1/a\n", encoding="utf-8")
    permitido = tmp_path / "upload"
    permitido.mkdir()
    monkeypatch.setenv("CIENTOMETRIA_DIR_IMPORTACAO", str(permitido))
    with pytest.raises(ValueError, match="fora do diretório"):
        proj.importar(fora)
    link = permitido / "link.csv"
    link.symlink_to(fora)
    with pytest.raises((ValueError, ArquivoInvalido)):
        proj.importar(link)
    ok = permitido / "ok.csv"
    shutil.copy(fora, ok)
    assert proj.importar(ok)["nome"] == "ok.csv"


def test_conteudo_incompativel_com_extensao(tmp_path):
    casos = {"bin.csv": b"\x00\x01\x02ELF", "falso.xlsx": b"isto nao e zip", "falso.xls": b"PK\x03\x04",
             "vazio.ris": b"", "script.php": b"<?php echo 1;"}
    for nome, conteudo in casos.items():
        (tmp_path / nome).write_bytes(conteudo)
        with pytest.raises(ArquivoInvalido):
            validar_conteudo(tmp_path / nome)


def test_xlsx_bomba_de_compressao(tmp_path):
    p = tmp_path / "bomba.xlsx"
    with zipfile.ZipFile(p, "w", zipfile.ZIP_DEFLATED) as z:
        z.writestr("[Content_Types].xml", "<Types/>")
        z.writestr("xl/sheet.xml", b"0" * (50 * 1024 * 1024))  # 50 MB de zeros -> razão enorme
    with pytest.raises(ArquivoInvalido, match="descompactado"):
        validar_conteudo(p)


def test_nome_de_arquivo_saneado(proj, tmp_path):
    p = tmp_path / "x.csv"
    p.write_text("Title,DOI\nflood,10.1/a\n", encoding="utf-8")
    reg = proj.importar(p, nome="../../../etc/passwd.csv")
    assert reg["nome"] == "passwd.csv" and "/" not in reg["arquivo"]
    assert (proj.pasta / "arquivos" / reg["arquivo"]).resolve().parent == (proj.pasta / "arquivos").resolve()


def test_arquivo_importado_fica_somente_leitura(proj, tmp_path):
    p = tmp_path / "x.csv"
    p.write_text("Title,DOI\nflood,10.1/a\n", encoding="utf-8")
    reg = proj.importar(p)
    modo = (proj.pasta / "arquivos" / reg["arquivo"]).stat().st_mode & 0o777
    assert modo == 0o444


def test_sensibilidade_limitada(proj, tmp_path):
    pasta = gerar(str(tmp_path / "b"))
    for f in sorted(pathlib.Path(pasta).glob("*.csv")):
        proj.importar(f)
    r = proj.executar(Config.original(), n_sensibilidade=10 ** 9, bibliometria_=False, graficos_=False,
                      relatorios_=False, revisao_duplicatas=False)
    import json
    d = json.loads((pathlib.Path(r["pasta"]) / "diagnosticos" / "diagnosticos.json").read_text())
    assert d["sensibilidade_pesos"]["n"] == 20000


# ---------------------------------------------------------------- HTTP (PHP)
php = shutil.which("php")
precisa_php = pytest.mark.skipif(not php, reason="php não instalado")


def _porta_livre():
    with socket.socket() as s:
        s.bind(("127.0.0.1", 0))
        return s.getsockname()[1]


@pytest.fixture(scope="module")
def servidor(tmp_path_factory):
    raiz = tmp_path_factory.mktemp("projetos")
    porta = _porta_livre()
    env = dict(os.environ, CIENTOMETRIA_PROJETOS=str(raiz), CIENTOMETRIA_DIR_UPLOAD=str(tmp_path_factory.mktemp("up")))
    proc = subprocess.Popen([php, "-d", "upload_max_filesize=64M", "-d", "post_max_size=64M", "-S",
                             f"127.0.0.1:{porta}", "router.php"], cwd=RAIZ, env=env,
                            stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    base = f"http://127.0.0.1:{porta}"
    import requests
    for _ in range(50):
        try:
            requests.get(base + "/", timeout=1)
            break
        except requests.ConnectionError:
            time.sleep(.1)
    yield base, raiz
    proc.terminate()
    proc.wait(5)


def _sessao(base):
    import requests
    s = requests.Session()
    r = s.get(base + "/")
    token = re.search(r'name="csrf-token" content="([0-9a-f]+)"', r.text).group(1)
    s.headers.update({"X-CSRF-Token": token, "Origin": base})
    return s, r


@precisa_php
def test_cabecalhos_de_seguranca(servidor):
    base, _ = servidor
    s, r = _sessao(base)
    csp = r.headers["Content-Security-Policy"]
    assert "script-src 'nonce-" in csp and "unsafe-inline" not in csp.split("script-src")[1].split(";")[0]
    assert r.headers["X-Frame-Options"] == "DENY" and r.headers["X-Content-Type-Options"] == "nosniff"
    ck = r.headers["Set-Cookie"].lower()
    assert "httponly" in ck and "samesite=strict" in ck
    nonce = re.search(r"'nonce-([^']+)'", csp).group(1)
    assert f'<script nonce="{nonce}">' in r.text and 'onclick="' not in r.text


@precisa_php
@pytest.mark.parametrize("caminho", ["/projetos/", "/.git/HEAD", "/cientometria/config.py", "/tests/sinteticos.py",
                                     "/seguranca.php", "/router.php", "/scripts/pipeline.py", "/README.md",
                                     "/tmp_uploads/x", "/%2e%2e/etc/passwd"])
def test_roteador_nao_serve_arquivos_internos(servidor, caminho):
    import requests
    assert requests.get(servidor[0] + caminho).status_code == 404


@precisa_php
def test_csrf_e_origem(servidor):
    import requests
    base, _ = servidor
    sem = requests.post(base + "/api.php?acao=listar_projetos", json={})
    assert sem.status_code == 403 and "CSRF" in sem.json()["erro"]
    s, _ = _sessao(base)
    assert s.post(base + "/api.php?acao=listar_projetos", json={}).status_code == 200
    ruim = s.post(base + "/api.php?acao=listar_projetos", json={}, headers={"Origin": "http://evil.example"})
    assert ruim.status_code == 403
    errado = s.post(base + "/api.php?acao=listar_projetos", json={}, headers={"X-CSRF-Token": "0" * 64})
    assert errado.status_code == 403
    assert s.get(base + "/api.php?acao=listar_projetos").status_code == 405
    assert s.post(base + "/api.php?acao=inexistente", json={}).status_code == 400


@precisa_php
def test_traversal_e_upload_pela_api(servidor, tmp_path):
    base, raiz = servidor
    s, _ = _sessao(base)
    assert s.post(base + "/api.php?acao=criar_projeto", json={"nome": "Web"}).status_code == 200
    r = s.post(base + "/api.php?acao=projeto", json={"projeto": "../" + raiz.name + "/web"})
    assert r.status_code == 422 and "inválido" in r.json()["erro"]
    assert str(raiz) not in r.text
    # importar com caminho arbitrário via JSON não é possível (só via upload)
    r = s.post(base + "/api.php?acao=importar", json={"projeto": "web", "arquivos": [{"caminho": "/etc/passwd"}]})
    assert r.status_code == 400
    up = lambda nome, dados: s.post(base + "/api.php?acao=importar", data={"projeto": "web"},  # noqa: E731
                                    files={"files[]": (nome, io.BytesIO(dados))})
    assert up("x.php", b"<?php phpinfo();").status_code == 415
    assert up("binario.csv", b"\x00\x01ELF").status_code == 422
    assert up("../../evil.csv", b"Title,DOI\nflood,10.1/a\n").status_code == 200
    assert not list(pathlib.Path(raiz).rglob("evil.csv"))
    assert list(pathlib.Path(raiz).glob("web/arquivos/*__evil.csv"))
    r = s.post(base + "/api.php?acao=importar", data={"projeto": "../x"}, files={"files[]": ("a.csv", b"T\n1\n")})
    assert r.status_code == 400


@precisa_php
def test_relatorios_so_por_caminho_valido(servidor, tmp_path):
    import requests
    base, raiz = servidor
    s, _ = _sessao(base)
    s.post(base + "/api.php?acao=criar_projeto", json={"nome": "Rel"})
    pasta = gerar(str(tmp_path / "b"))
    arquivos = [("files[]", (f.name, f.read_bytes())) for f in sorted(pathlib.Path(pasta).glob("*.csv"))]
    assert s.post(base + "/api.php?acao=importar", data={"projeto": "rel"}, files=arquivos).status_code == 200
    r = s.post(base + "/api.php?acao=executar", json={"projeto": "rel", "params": {"modo": "original",
                                                                                   "n_sensibilidade": 0}})
    assert r.status_code == 200, r.text[:300]
    ex = r.json()["pasta"]
    url = base + "/arquivo.php"
    ok = s.get(url, params={"projeto": "rel", "execucao": ex, "caminho": "graficos/01-fluxo.png"})
    assert ok.status_code == 200 and ok.headers["Content-Type"] == "image/png"
    for c in ["graficos/../manifesto.json", "../../rel/arquivos.json", "manifesto.json", "relatorios/csv/../../corpus.csv",
              "graficos/01-fluxo.png%00.json"]:
        assert s.get(url, params={"projeto": "rel", "execucao": ex, "caminho": c}).status_code == 400, c
    assert s.get(url, params={"projeto": "../rel", "execucao": ex, "caminho": "graficos/01-fluxo.png"}).status_code == 400
    # verificação de integridade da execução pela API
    v = s.post(base + "/api.php?acao=verificar_execucao", json={"projeto": "rel", "id": r.json()["manifesto"]["id"]})
    assert v.json()["ok"] is True
    # arquivos de projeto nunca são servidos diretamente
    assert requests.get(base + f"/projetos/rel/execucoes/{ex}/corpus.csv").status_code == 404


@precisa_php
def test_triagem_rapida_sem_arquivos_no_webroot(servidor, tmp_path):
    base, _ = servidor
    s, _ = _sessao(base)
    s.get(base + "/triagem_rapida.php")
    pasta = gerar(str(tmp_path / "b"))
    arquivos = [("files[]", (f.name, f.read_bytes())) for f in sorted(pathlib.Path(pasta).glob("*.csv"))]
    r = s.post(base + "/run_pipeline.php", data={"engine": "r", "params": "{}"}, files=arquivos)
    assert r.status_code == 400 and "Motor R" in r.json()["erro"]
    r = s.post(base + "/run_pipeline.php", data={"engine": "python", "params": '{"modo":"original","n_sensibilidade":0}'},
               files=arquivos)
    assert r.status_code == 200 and r.json()["summary"]["core_counts"]["Núcleo A"] == 3
    assert not (RAIZ / "tmp_uploads").exists() or not any((RAIZ / "tmp_uploads").rglob("*.csv"))


@precisa_php
def test_autenticacao_basic(tmp_path):
    import requests
    hash_ = subprocess.run([php, "-r", "echo password_hash('s3nha-forte', PASSWORD_DEFAULT);"],
                           capture_output=True, text=True, check=True).stdout
    porta = _porta_livre()
    env = dict(os.environ, CIENTOMETRIA_PROJETOS=str(tmp_path), CIENTOMETRIA_USUARIO="pesquisa",
               CIENTOMETRIA_SENHA_HASH=hash_)
    proc = subprocess.Popen([php, "-S", f"127.0.0.1:{porta}", "router.php"], cwd=RAIZ, env=env,
                            stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    try:
        base = f"http://127.0.0.1:{porta}"
        for _ in range(50):
            try:
                r = requests.get(base + "/", timeout=1)
                break
            except requests.ConnectionError:
                time.sleep(.1)
        assert r.status_code == 401
        assert requests.get(base + "/", auth=("pesquisa", "errada")).status_code == 401
        assert requests.get(base + "/", auth=("pesquisa", "s3nha-forte")).status_code == 200
        assert requests.get(base + "/arquivo.php", params={"projeto": "x"}).status_code == 401
    finally:
        proc.terminate()
        proc.wait(5)


def test_interface_escapa_dados_dos_arquivos():
    """Títulos/DOIs vêm de arquivos enviados: nunca inseridos como HTML sem escape."""
    t = (RAIZ / "triagem_rapida.php").read_text(encoding="utf-8")
    assert "${r.title" not in t and "escapeHtml(r.title" in t
    i = (RAIZ / "index.php").read_text(encoding="utf-8")
    assert 'onclick="' not in i and "data-acao=" in i


def test_biblioteca_js_local_com_sri():
    """Chart.js empacotado com versão fixa; a página referencia o SHA-384 do arquivo (SRI)."""
    import base64
    import hashlib
    js = (RAIZ / "vendor" / "chart-4.4.1.umd.js").read_bytes()
    sri = "sha384-" + base64.b64encode(hashlib.sha384(js).digest()).decode()
    t = (RAIZ / "triagem_rapida.php").read_text(encoding="utf-8")
    assert f'integrity="{sri}"' in t and "cdn.jsdelivr" not in t


@precisa_php
def test_roteador_serve_so_a_biblioteca_empacotada(servidor):
    import requests
    base, _ = servidor
    r = requests.get(base + "/vendor/chart-4.4.1.umd.js")
    assert r.status_code == 200 and r.headers["Content-Type"].startswith("application/javascript")
    assert requests.get(base + "/vendor/LICENSE-chartjs.md").status_code == 404
