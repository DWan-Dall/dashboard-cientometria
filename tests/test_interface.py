"""Regressão da INTERFACE com navegador real (Chromium via Playwright) contra `php -S router.php`.

Cobre o fluxo completo do dashboard modular e da triagem rápida, conferindo que nenhum erro de
JavaScript, violação de CSP ou script injetado ocorre. Pulado se PHP ou Playwright não estiverem
instalados (no CI ambos são instalados)."""
import os
import pathlib
import shutil
import socket
import subprocess
import time

import pytest

from .sinteticos import gerar

RAIZ = pathlib.Path(__file__).resolve().parents[1]
php = shutil.which("php")
try:
    from playwright.sync_api import expect, sync_playwright
except ImportError:  # pragma: no cover
    sync_playwright = None

# Os testes NÃO desligam o CSP (bypass_csp): esperas usam localizadores (expect) e consultas pelo
# protocolo do navegador, porque o CSP da aplicação bloqueia eval — como deve.


def _esperar(pg, js, timeout=60):
    """Espera uma condição consultando a página periodicamente (sem eval na página)."""
    fim = time.time() + timeout
    while time.time() < fim:
        if pg.evaluate(js):
            return
        pg.wait_for_timeout(250)
    raise AssertionError(f"condição não satisfeita em {timeout}s: {js}")

pytestmark = pytest.mark.skipif(not (php and sync_playwright), reason="requer php e playwright")


def _porta():
    with socket.socket() as s:
        s.bind(("127.0.0.1", 0))
        return s.getsockname()[1]


@pytest.fixture(scope="module")
def base(tmp_path_factory):
    import requests
    porta = _porta()
    env = dict(os.environ, CIENTOMETRIA_PROJETOS=str(tmp_path_factory.mktemp("projetos")),
               CIENTOMETRIA_DIR_UPLOAD=str(tmp_path_factory.mktemp("up")), PHP_CLI_SERVER_WORKERS="4")
    proc = subprocess.Popen([php, "-d", "upload_max_filesize=64M", "-d", "post_max_size=64M", "-S",
                             f"127.0.0.1:{porta}", "router.php"], cwd=RAIZ, env=env,
                            stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    url = f"http://127.0.0.1:{porta}"
    for _ in range(50):
        try:
            requests.get(url, timeout=1)
            break
        except requests.ConnectionError:
            time.sleep(.1)
    yield url
    proc.terminate()
    proc.wait(5)


@pytest.fixture(scope="module")
def navegador():
    with sync_playwright() as p:
        b = p.chromium.launch()
        yield b
        b.close()


@pytest.fixture()
def pagina(navegador):
    ctx = navegador.new_context(viewport={"width": 1400, "height": 1000})
    pg = ctx.new_page()
    pg.erros = []
    pg.on("pageerror", lambda e: pg.erros.append(f"pageerror: {e}"))
    pg.on("console", lambda m: pg.erros.append(f"console: {m.text}") if m.type == "error" else None)
    pg.on("dialog", lambda d: (pg.erros.append(f"dialog: {d.message}"), d.dismiss()))
    yield pg
    ctx.close()


@pytest.fixture(scope="module")
def sinteticos(tmp_path_factory):
    return sorted(str(p) for p in pathlib.Path(gerar(str(tmp_path_factory.mktemp("s")))).glob("*.csv"))


def _kpi(pg, rotulo):
    return pg.locator(f".kpi:has(.l:text-is('{rotulo}')) .v").first.text_content()


def test_fluxo_completo_do_dashboard(base, pagina, sinteticos):
    pg = pagina
    pg.goto(base + "/")
    # nome com marcação HTML: deve aparecer como texto, sem criar elemento
    pg.fill("#pNome", "<b id=injetado>Projeto UI</b>")
    pg.fill("#pDesc", "<img src=x onerror=window.__xss=1>")
    pg.click("#btCriar")
    expect(pg.locator("#projAtual")).to_contain_text("Projeto UI")
    assert pg.locator("#injetado").count() == 0
    assert pg.text_content("#projAtual") == "<b id=injetado>Projeto UI</b>"
    # importação
    pg.click("nav >> text=2. Importação")
    pg.set_input_files("#fArquivos", sinteticos)
    pg.click("#btImportar")
    expect(pg.locator("#tbArquivos tbody tr")).to_have_count(8, timeout=60000)
    # diagnóstico
    pg.click("#btDiag")
    pg.wait_for_selector("#diagOut table")
    assert "nome canônico do procedimento original" in pg.text_content("#diagOut")
    # triagem
    pg.click("nav >> text=3. Triagem")
    pg.click("#btExec")
    expect(pg.locator("#tStatus")).to_contain_text("concluído", timeout=180000)
    assert (_kpi(pg, "Núcleo A"), _kpi(pg, "Núcleo B"), _kpi(pg, "Periférico"), _kpi(pg, "Descarte")) == ("3", "19", "56", "49")
    assert pg.locator("#triagemOut .tag", has_text="original-2026.01").count() == 1
    # robustez: comparar modos
    pg.click("nav >> text=4. Robustez")
    pg.click("#btModos")
    pg.wait_for_selector("#modosOut table", timeout=180000)
    assert "corrigida" in pg.text_content("#modosOut")
    # bibliometria e gráficos
    pg.click("nav >> text=5. Análises")
    opcoes = pg.locator("#bSel option").all_text_contents()
    assert "cobertura" in opcoes and "producao_anual" in opcoes
    _esperar(pg, "() => [...document.querySelectorAll('#imgs img')].filter(i => i.complete && i.naturalWidth > 0).length >= 5")
    # segunda execução, comparação e reprodução
    pg.click("nav >> text=3. Triagem")
    pg.select_option("#tModo", "corrigida")
    anterior = pg.text_content("#tStatus")
    pg.click("#btExec")
    expect(pg.locator("#tStatus")).not_to_have_text(anterior, timeout=30000)
    expect(pg.locator("#tStatus")).to_contain_text("concluído", timeout=180000)
    pg.click("nav >> text=6. Execuções")
    expect(pg.locator("#tbExec tbody tr")).to_have_count(2, timeout=30000)
    pg.select_option("#cmpA", index=0)
    pg.select_option("#cmpB", index=1)
    pg.click("#btCmp")
    pg.wait_for_selector("#cmpOut table")
    assert "Núcleo A em ambos" in pg.text_content("#cmpOut")
    pg.locator("#tbExec button[data-acao=reproduzir]").first.click()
    expect(pg.locator("#cmpOut")).to_contain_text("mesmo corpus (hash)", timeout=120000)
    assert "NÃO" not in pg.text_content("#cmpOut .grid")
    # relatórios: links funcionam
    pg.click("nav >> text=7. Relatórios")
    href = pg.locator("#relOut a", has_text="resultados.xlsx").get_attribute("href")
    resp = pg.request.get(base + "/" + href)
    assert resp.status == 200 and resp.headers["content-type"].startswith("application/vnd.openxmlformats")
    assert pg.evaluate("() => window.__xss") is None
    assert pg.erros == []


def test_triagem_rapida(base, pagina, sinteticos, tmp_path):
    pg = pagina
    pg.goto(base + "/triagem_rapida.php")
    assert pg.get_attribute("#targetRaw", "readonly") is not None
    pg.set_input_files("#fileInput", sinteticos)
    pg.click("#runBtn")
    expect(pg.locator("#status")).to_have_text("Concluído.", timeout=180000)
    assert pg.locator("#topTable tbody tr").count() > 0
    assert pg.locator("#nucleoChart").count() == 1
    # título malicioso + arquivo inválido
    x = tmp_path / "lens-export.csv"
    x.write_text('Title,Publication Year,Abstract,Keywords,Citing Works Count,DOI,Source Title\n'
                 '"<img src=x onerror=""window.__xss=1"">Flood forecasting LSTM",2020,rainfall river deep learning flood '
                 'prediction,,3,10.1000/x,W\n', encoding="utf-8")
    pg.set_input_files("#fileInput", [str(x)])
    pg.click("#runBtn")
    expect(pg.locator("#status")).not_to_have_text("Concluído.", timeout=30000)
    expect(pg.locator("#status")).to_have_text("Concluído.", timeout=120000)
    assert pg.evaluate("() => window.__xss") is None and "<img src=x" in pg.text_content("#topTable")
    ruim = tmp_path / "ruim" / "lens-export.csv"
    ruim.parent.mkdir()
    ruim.write_bytes(b"\x00\x01binario")
    pg.set_input_files("#fileInput", [str(ruim)])
    pg.click("#runBtn")
    expect(pg.locator("#status")).to_contain_text("bytes nulos", timeout=60000)
    assert [e for e in pg.erros if "422" not in e] == []      # o 422 esperado aparece como erro de rede no console


def test_exportar_e_importar_execucao_zip(base, pagina, sinteticos, tmp_path):
    """Exporta uma execução como .zip pela interface (download real), importa-a em outro projeto,
    confere a marcação "importada" e a verificação, e a recusa de ID repetido — com o CSP ativo."""
    import zipfile
    pg = pagina
    pg.goto(base + "/")
    pg.fill("#pNome", "Zip origem")
    pg.click("#btCriar")
    expect(pg.locator("#projAtual")).to_have_text("Zip origem")
    pg.click("nav >> text=2. Importação")
    pg.set_input_files("#fArquivos", sinteticos)
    pg.click("#btImportar")
    expect(pg.locator("#tbArquivos tbody tr")).to_have_count(8, timeout=60000)
    pg.click("nav >> text=3. Triagem")
    pg.click("#s-triagem details summary")
    pg.fill("#nSens", "0")
    pg.click("#btExec")
    expect(pg.locator("#tStatus")).to_contain_text("concluído", timeout=180000)
    id_ = pg.text_content("#tStatus").split(":")[-1].strip()
    pg.click("nav >> text=6. Execuções")
    expect(pg.locator("#tbExec tbody tr")).to_have_count(1, timeout=30000)
    # aviso de dados licenciados só aparece ao marcar a opção (padrão: desmarcada)
    assert not pg.is_checked("#xEntradas") and not pg.is_visible("#xAviso")
    pg.check("#xEntradas")
    expect(pg.locator("#xAviso")).to_be_visible()
    pg.uncheck("#xEntradas")
    with pg.expect_download(timeout=120000) as dl:
        pg.click("#tbExec button[data-acao=exportar]")
    d = dl.value
    assert d.suggested_filename.endswith(f"_{id_}.zip")
    zpath = tmp_path / d.suggested_filename
    d.save_as(zpath)
    with zipfile.ZipFile(zpath) as z:
        nomes = z.namelist()
    assert "LEIA-ME.txt" in nomes and any(n.endswith("/manifesto.json") for n in nomes)
    assert not any(n.startswith("entradas/") for n in nomes)
    expect(pg.locator("#xOut")).to_contain_text("SHA-256 do manifesto.json")
    # importar em outro projeto
    pg.click("nav >> text=1. Projetos")
    pg.fill("#pNome", "Zip destino")
    pg.click("#btCriar")
    expect(pg.locator("#projAtual")).to_have_text("Zip destino")
    pg.click("nav >> text=6. Execuções")
    pg.set_input_files("#xZip", str(zpath))
    pg.click("#btImportarExec")
    expect(pg.locator("#xOut")).to_contain_text("verificação: ok", timeout=60000)
    expect(pg.locator("#tbExec tbody tr")).to_have_count(1)
    expect(pg.locator("#tbExec tbody tr .tag", has_text="importada")).to_have_count(1)
    assert pg.locator("#tbExec button[data-acao=reproduzir]").count() == 0
    # abrir a execução importada mostra a origem
    pg.locator("#tbExec button[data-acao=abrirExecucao]").click()
    pg.click("nav >> text=3. Triagem")
    expect(pg.locator("#triagemOut")).to_contain_text("Importada de")
    # mesmo ID de novo: recusado, nada sobrescrito
    pg.click("nav >> text=6. Execuções")
    pg.set_input_files("#xZip", str(zpath))
    pg.click("#btImportarExec")
    expect(pg.locator("#msg .erro")).to_contain_text("nada foi importado nem sobrescrito", timeout=60000)
    expect(pg.locator("#tbExec tbody tr")).to_have_count(1)
    assert [e for e in pg.erros if "422" not in e] == []      # o 422 esperado aparece como erro de rede no console
