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
    python3 -m cientometria exportar <slug> <id> [--sem-entradas] [--saida pasta]
    python3 -m cientometria verificar-pacote pacote.zip
    python3 -m cientometria importar-pacote <slug> pacote.zip [--sem-entradas]
    python3 -m cientometria reexecutar <slug> <id>
"""
from __future__ import annotations
import argparse
import json
import os
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
    if acao == "verificar_execucao":
        return p.verificar_execucao(dados["id"])
    # pacote ZIP: exportar (destino confinado por CIENTOMETRIA_DIR_EXPORTACAO), receber (origem
    # confinada por CIENTOMETRIA_DIR_IMPORTACAO), inspecionar/restaurar/descartar por token
    if acao == "inventario_execucao":
        return p.inventario_execucao(dados["id"], bool(dados.get("incluir_entradas", True)))
    if acao == "exportar_execucao":
        return p.exportar_execucao(dados["id"], dados["destino"], bool(dados.get("incluir_entradas", True)))
    if acao == "receber_pacote":
        return p.receber_pacote(dados["caminho"])
    if acao == "inspecionar_pacote":
        return p.inspecionar_pacote(dados["token"])
    if acao == "restaurar_pacote":
        return p.restaurar_pacote(dados["token"], bool(dados.get("importar_entradas", True)))
    if acao == "descartar_pacote":
        return p.descartar_pacote(dados["token"])
    if acao == "reexecutar":
        return p.reexecutar(dados["id"])
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
    from .limites import aplicar
    aplicar()
    try:
        out = despachar(argv[0], dados)
        print(json.dumps(out, ensure_ascii=False, default=str))
    except (Exception, MemoryError) as e:  # noqa: BLE001 — erro devolvido como JSON para a interface
        msg = f"{type(e).__name__}: {e}"
        for raiz in filter(None, [dados.get("raiz"), os.environ.get("CIENTOMETRIA_PROJETOS"),
                                  os.environ.get("CIENTOMETRIA_DIR_IMPORTACAO"), str(Path.cwd())]):
            msg = msg.replace(str(raiz), "<…>")
        print(json.dumps({"erro": msg[:1000]}, ensure_ascii=False))
        sys.exit(1)


def principal_cli(argv=None):
    ap = argparse.ArgumentParser(prog="cientometria", description="Plataforma de cientometria reproduzível")
    ap.add_argument("--raiz", help="pasta dos projetos (padrão: $CIENTOMETRIA_PROJETOS ou ./projetos)")
    sub = ap.add_subparsers(dest="cmd", required=True)
    s = sub.add_parser("projeto-criar")
    s.add_argument("nome")
    s.add_argument("--descricao", default="")
    sub.add_parser("projetos")
    s = sub.add_parser("importar")
    s.add_argument("projeto")
    s.add_argument("arquivos", nargs="+")
    s.add_argument("--base", help="força o tipo de base (lens, scopus, ieee, scielo, wos, openalex, ...)")
    s = sub.add_parser("diagnosticar")
    s.add_argument("projeto")
    s.add_argument("--modo", default="original")
    s = sub.add_parser("executar")
    s.add_argument("projeto")
    s.add_argument("--modo", default="original")
    s.add_argument("--rotulo", default="")
    s.add_argument("--params", help="JSON com parâmetros (ver parametros.py)")
    s.add_argument("--n-sensibilidade", type=int, default=2000)
    s = sub.add_parser("execucoes")
    s.add_argument("projeto")
    s = sub.add_parser("comparar")
    s.add_argument("projeto")
    s.add_argument("a")
    s.add_argument("b")
    s = sub.add_parser("reproduzir")
    s.add_argument("projeto")
    s.add_argument("id")
    s = sub.add_parser("exportar", help="exporta uma execução completa como ZIP verificável")
    s.add_argument("projeto")
    s.add_argument("id")
    s.add_argument("--sem-entradas", action="store_true", help="omite as exportações originais (licença)")
    s.add_argument("--saida", default=".")
    s = sub.add_parser("verificar-pacote", help="valida um ZIP de execução sem importar")
    s.add_argument("pacote")
    s = sub.add_parser("importar-pacote", help="restaura uma execução de um ZIP (sem recalcular)")
    s.add_argument("projeto")
    s.add_argument("pacote")
    s.add_argument("--sem-entradas", action="store_true", help="não importa as exportações incluídas")
    s = sub.add_parser("reexecutar", help="nova execução com os arquivos e parâmetros de outra")
    s.add_argument("projeto")
    s.add_argument("id")
    s = sub.add_parser("verificar-corpus")
    s.add_argument("arquivo")
    s = sub.add_parser("referencia")
    s.add_argument("pasta", help="pasta com as 8 exportações originais")
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
    elif a.cmd == "exportar":
        imp(Projeto.abrir(a.projeto, a.raiz).exportar_execucao(a.id, Path(a.saida), not a.sem_entradas))
    elif a.cmd == "verificar-pacote":
        from .pacote import inspecionar
        inv = inspecionar(a.pacote)
        imp({k: v for k, v in inv.items() if k != "arquivos"} | {"arquivos_com_problema": [
            x for x in inv["arquivos"] if x["estado"] != "ok"]})
        if not inv["ok"]:
            sys.exit(2)
    elif a.cmd == "importar-pacote":
        p = Projeto.abrir(a.projeto, a.raiz)
        inv = p.receber_pacote(a.pacote)
        if not inv["ok"]:
            p.descartar_pacote(inv["token"])
            imp({"erro": "pacote com problemas", "problemas": inv["problemas"]})
            sys.exit(2)
        imp(p.restaurar_pacote(inv["token"], not a.sem_entradas))
    elif a.cmd == "reexecutar":
        r = Projeto.abrir(a.projeto, a.raiz).reexecutar(a.id)
        imp({k: r[k] for k in ("id", "origem", "avisos")} | {
            "mesmo_corpus": r["comparacao"]["mesmo_corpus"], "contagens": r["comparacao"]["contagens"]})
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
