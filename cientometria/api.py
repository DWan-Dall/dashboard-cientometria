"""API JSON e linha de comando.

O dashboard PHP chama:  python3 -m cientometria.api <acao> <arquivo_payload.json>
e recebe JSON em stdout. Erros: JSON {"erro": "..."} e código de saída 1.

Linha de comando para pesquisadores (sem dashboard):
    python3 -m cientometria projeto-criar "Meu projeto" --descricao "..."
    python3 -m cientometria importar <slug> arq1.csv arq2.ris ...
    python3 -m cientometria executar <slug> --modo original
    python3 -m cientometria execucoes <slug>
    python3 -m cientometria comparar <slug> <id_a> <id_b>
    python3 -m cientometria reproduzir <slug> <id>
    python3 -m cientometria verificar-corpus DB_Cientometria_COMPLETA.csv
"""
from __future__ import annotations
import argparse
import json
import sys
from pathlib import Path

import pandas as pd

from .config import Config
from .parametros import config_de_parametros
from .projetos import Projeto


def _tabela(df: pd.DataFrame, limite=200):
    return json.loads(df.head(limite).to_json(orient="records", force_ascii=False, default_handler=str))


def _resultado_execucao(p: Projeto, id_: str, limite_top: int = 500) -> dict:
    pasta = p.pasta_execucao(id_)
    man = json.loads((pasta / "manifesto.json").read_text(encoding="utf-8"))
    out = {"manifesto": man, "pasta": pasta.name}
    corpus = pasta / "corpus.csv"
    if corpus.exists():
        c = pd.read_csv(corpus)
        if len(c):
            c = c.sort_values("score_final_100", ascending=False)
            cols = [x for x in ["title", "year", "citations", "doi", "source_db", "bases_encontradas", "C_norm",
                                "R_norm", "T_score", "A_score", "score_final_100", "fascia"] if x in c]
            out["corpus"] = _tabela(c[cols], limite_top)
    d = pasta / "diagnosticos"
    if d.exists():
        out["diagnosticos"] = json.loads((d / "diagnosticos.json").read_text(encoding="utf-8"))
        out["limitacoes"] = json.loads((d / "limitacoes.json").read_text(encoding="utf-8"))
        out["campos"] = _tabela(pd.read_csv(d / "campos.csv"), 1000)
        dup = d / "duplicatas_para_revisao.csv"
        if dup.exists():
            dd = pd.read_csv(dup)
            out["duplicatas_para_revisao"] = {"total": len(dd), "amostra": _tabela(dd, 100)}
    b = pasta / "bibliometria"
    if b.exists():
        out["bibliometria"] = {f.stem: _tabela(pd.read_csv(f), 50) for f in sorted(b.glob("*.csv"))
                               if f.stat().st_size > 1}
    g = pasta / "graficos"
    out["graficos"] = sorted(x.name for x in g.glob("*.png")) if g.exists() else []
    r = pasta / "relatorios"
    out["relatorios"] = sorted(str(x.relative_to(pasta)) for x in r.rglob("*") if x.is_file()) if r.exists() else []
    return out


def despachar(acao: str, dados: dict) -> dict:
    raiz = dados.get("raiz")
    if acao == "listar_projetos":
        return {"projetos": Projeto.listar(raiz)}
    if acao == "criar_projeto":
        p = Projeto.criar(dados["nome"], dados.get("descricao", ""), dados.get("fontes_bibliograficas"), raiz=raiz)
        return {"projeto": p.info}
    p = Projeto.abrir(dados["projeto"], raiz)
    if acao == "projeto":
        return {"projeto": p.info, "arquivos": p.arquivos(incluir_removidos=True),
                "execucoes": p.execucoes(), "historico": p.historico()[-100:]}
    if acao == "atualizar_projeto":
        p.atualizar(**dados.get("campos", {}))
        return {"projeto": p.info}
    if acao == "importar":
        regs = [p.importar(a["caminho"], a.get("nome"), a.get("base")) for a in dados["arquivos"]]
        return {"importados": regs, "arquivos": p.arquivos()}
    if acao == "remover_arquivo":
        p.remover_arquivo(dados["id"])
        return {"arquivos": p.arquivos(incluir_removidos=True)}
    if acao == "diagnosticar":
        return p.diagnosticar(config_de_parametros(dados.get("params")), dados.get("arquivos"))
    if acao == "executar":
        cfg = config_de_parametros(dados.get("params"))
        r = p.executar(cfg, ids=dados.get("arquivos"), rotulo=dados.get("rotulo", ""),
                       observacoes=dados.get("observacoes", ""),
                       n_sensibilidade=int((dados.get("params") or {}).get("n_sensibilidade", 2000)))
        return _resultado_execucao(p, r["id"])
    if acao == "execucoes":
        return {"execucoes": p.execucoes()}
    if acao == "execucao":
        return _resultado_execucao(p, dados["id"])
    if acao == "comparar":
        return p.comparar(dados["a"], dados["b"])
    if acao == "reproduzir":
        return p.reproduzir(dados["id"])
    if acao == "comparar_modos":
        from .pipeline import executar
        bases, fontes = p.carregar(Config.original(), dados.get("arquivos"))
        linhas = {}
        for modo in ("original", "variante_exclusao", "corrigida"):
            cfg = Config.do_modo(modo)
            b, _ = p.carregar(cfg, dados.get("arquivos"))
            r = executar(b, cfg)
            linhas[modo] = {"contagens": r.contagens, "estratos": r.estratos(), "versao_metodo": cfg.metodo_versao}
        return {"modos": linhas}
    raise ValueError(f"Ação desconhecida: {acao}")


def principal_api(argv):
    if len(argv) < 2:
        raise SystemExit("Uso: python -m cientometria.api <acao> <payload.json>")
    dados = json.loads(Path(argv[1]).read_text(encoding="utf-8")) if len(argv) > 1 else {}
    try:
        out = despachar(argv[0], dados)
        print(json.dumps(out, ensure_ascii=False, default=str))
    except Exception as e:  # noqa: BLE001 — erro devolvido como JSON para a interface
        print(json.dumps({"erro": f"{type(e).__name__}: {e}"}, ensure_ascii=False))
        sys.exit(1)


def principal_cli(argv=None):
    ap = argparse.ArgumentParser(prog="cientometria", description="Plataforma de cientometria reproduzível")
    ap.add_argument("--raiz", help="pasta dos projetos (padrão: $CIENTOMETRIA_PROJETOS ou ./projetos)")
    sub = ap.add_subparsers(dest="cmd", required=True)
    s = sub.add_parser("projeto-criar"); s.add_argument("nome"); s.add_argument("--descricao", default="")
    sub.add_parser("projetos")
    s = sub.add_parser("importar"); s.add_argument("projeto"); s.add_argument("arquivos", nargs="+")
    s.add_argument("--base", help="força o tipo de base (lens, scopus, ieee, scielo, wos, openalex, ...)")
    s = sub.add_parser("diagnosticar"); s.add_argument("projeto"); s.add_argument("--modo", default="original")
    s = sub.add_parser("executar"); s.add_argument("projeto"); s.add_argument("--modo", default="original")
    s.add_argument("--rotulo", default=""); s.add_argument("--params", help="JSON com parâmetros (ver parametros.py)")
    s.add_argument("--n-sensibilidade", type=int, default=2000)
    s = sub.add_parser("execucoes"); s.add_argument("projeto")
    s = sub.add_parser("comparar"); s.add_argument("projeto"); s.add_argument("a"); s.add_argument("b")
    s = sub.add_parser("reproduzir"); s.add_argument("projeto"); s.add_argument("id")
    s = sub.add_parser("verificar-corpus"); s.add_argument("arquivo")
    s = sub.add_parser("referencia"); s.add_argument("pasta", help="pasta com as 8 exportações originais")
    a = ap.parse_args(argv)
    imp = lambda o: print(json.dumps(o, ensure_ascii=False, indent=1, default=str))  # noqa: E731
    if a.cmd == "projeto-criar":
        imp(Projeto.criar(a.nome, a.descricao, raiz=a.raiz).info)
    elif a.cmd == "projetos":
        imp(Projeto.listar(a.raiz))
    elif a.cmd == "importar":
        p = Projeto.abrir(a.projeto, a.raiz)
        imp([p.importar(x, base=a.base) for x in a.arquivos])
    elif a.cmd == "diagnosticar":
        imp(Projeto.abrir(a.projeto, a.raiz).diagnosticar(Config.do_modo(a.modo)))
    elif a.cmd == "executar":
        params = json.loads(a.params) if a.params else {}
        params.setdefault("modo", a.modo)
        r = Projeto.abrir(a.projeto, a.raiz).executar(config_de_parametros(params), rotulo=a.rotulo,
                                                      n_sensibilidade=a.n_sensibilidade)
        m = r["manifesto"]
        imp({"id": m["id"], "pasta": r["pasta"], "modo": m["modo"], "versao_metodo": m["versao_metodo"],
             "contagens": m["contagens"], "estratos": m["estratos"]})
    elif a.cmd == "execucoes":
        imp(Projeto.abrir(a.projeto, a.raiz).execucoes())
    elif a.cmd == "comparar":
        imp(Projeto.abrir(a.projeto, a.raiz).comparar(a.a, a.b))
    elif a.cmd == "reproduzir":
        imp(Projeto.abrir(a.projeto, a.raiz).reproduzir(a.id))
    elif a.cmd == "verificar-corpus":
        from .auditoria import verificar_corpus_publicado
        imp(verificar_corpus_publicado(a.arquivo))
    elif a.cmd == "referencia":
        from .auditoria import comparar_com_referencia
        from .entrada import ler_pasta
        from .pipeline import executar
        for modo in ("original", "variante_exclusao", "corrigida"):
            r = executar(ler_pasta(a.pasta), Config.do_modo(modo))
            print(f"\n== {modo} ({r.cfg.metodo_versao})")
            print(comparar_com_referencia(r).to_string(index=False))


if __name__ == "__main__":
    principal_api(sys.argv[1:])
