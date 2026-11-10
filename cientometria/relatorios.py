"""Relatórios de uma execução: CSV, XLSX, PDF, relatório metodológico (Markdown) e parâmetros."""
from __future__ import annotations
import json
import textwrap
from pathlib import Path

import pandas as pd

from .versao import METODO_HISTORICO

COLUNAS_EXPORTACAO = ["source_db", "bases_encontradas", "title", "year", "citations", "doi", "source",
                      "C_norm", "R_norm", "T_score", "A_score", "score_final_100", "fascia",
                      "arquivo_origem", "linha_origem"]


def _fmt(n):
    return f"{n:,}".replace(",", ".") if isinstance(n, int) else str(n)


def relatorio_metodologico(manifesto: dict, diagnosticos: dict | None = None) -> str:
    m, c, e = manifesto, manifesto["contagens"], manifesto["estratos"]
    p = m["parametros"]
    L = [f"# Relatório metodológico — execução {m['id']}", "",
         f"- Data/hora (UTC): {m['data_hora_utc']}",
         f"- Aplicação: {m['versao_aplicacao']} · Modo: **{m['modo']}** · Versão do método: **{m['versao_metodo']}**",
         f"- Configuração personalizada: {'**sim**' if m['configuracao_personalizada'] else 'não'}",
         f"- Impressão digital (entradas + parâmetros): `{m['impressao_digital_entrada']}`",
         f"- Hash do corpus: `{m['hash_corpus']}`", "",
         "> A triagem é automática (casamento de termos + escore ponderado), sem revisão manual registro a "
         "registro. Os escores 0–100 são relativos ao corpus (min–max); o rótulo dos estratos depende dos "
         "cortes fixos e da composição do corpus. A posição no ranking é mais estável que o rótulo.", "",
         "## 1. Fontes", "", "| ordem | arquivo | base | tipo | registros | SHA-256 | leitura | avisos |",
         "|---|---|---|---|---|---|---|---|"]
    for i, f in enumerate(m["fontes"], 1):
        L.append(f"| {i} | {f['arquivo']} | {f['rotulo']} | {f['tipo']} | {_fmt(f['registros'])} | "
                 f"`{f['sha256'][:16]}…` | {f['leitura']} | {'; '.join(f['avisos']) or '—'} |")
    L += ["", "## 2. Consolidação", ""]
    for k, v in m["criterios_consolidacao"].items():
        L.append(f"- **{k.replace('_', ' ')}**: {v}")
    L += ["", "## 3. Fluxo", "", "| etapa | quantidade |", "|---|---|"]
    for k in ["registros", "sem_doi", "duplicatas_doi", "removidos_etapa_doi", "apos_doi", "removidos_titulo",
              "unicos", "nucleo_obrigatorio", "candidatos_antes_da_exclusao", "excluidos_entre_candidatos", "corpus"]:
        L.append(f"| {k.replace('_', ' ')} | {_fmt(c.get(k))} |")
    L += ["", "## 4. Filtros temáticos", "",
          "Núcleo expandido = (previsão de enchentes) E (IA/ML) E (dados hidrológicos OU geoespaciais) "
          "E NÃO (exclusão). Casamento por trecho de texto, sem distinção de caixa; previsão e IA/ML em "
          "título+resumo+palavras-chave; dados em resumo+palavras-chave; exclusão em título+resumo.", ""]
    for k, v in p["nucleo"].items():
        L.append(f"- **{k}** ({len(v)}): {', '.join(v)}")
    L.append(f"- **exclusão** ({len(p['exclusao'])}): {', '.join(p['exclusao'])}")
    L.append(f"- **exclusão por palavra inteira**: {', '.join(p['exclusao_palavra_inteira']) or 'nenhum (tudo por trecho)'}")
    w = m["pesos"]
    L += ["", "## 5. Escore", "",
          f"S = {w[0]}·C* + {w[1]}·R* + {w[2]}·T* + {w[3]}·A*, depois min–max para 0–100.",
          "- C*: citações min–max no corpus; R*: ano min–max; T* ∈ {1,0; 0,7; 0,4}; A* = (I+M+O+C)/4.",
          f"- Cortes: Núcleo A ≥ {m['cortes']['nucleo_a']}; Núcleo B ≥ {m['cortes']['nucleo_b']}; "
          f"Periférico ≥ {m['cortes']['periferico']}; abaixo: Descarte.", "",
          "| estrato | artigos |", "|---|---|"]
    L += [f"| {k} | {_fmt(v)} |" for k, v in e.items()]
    if m["alteracoes_em_relacao_a_receita"]:
        L += ["", "## 6. Alterações em relação à receita do modo", ""]
        for k, v in m["alteracoes_em_relacao_a_receita"].items():
            L.append(f"- **{k}**: receita `{str(v['receita'])[:120]}` → usado `{str(v['usado'])[:120]}`")
    if diagnosticos:
        L += ["", "## 7. Diagnósticos", ""]
        for k, v in diagnosticos.items():
            if isinstance(v, dict):
                L.append(f"- **{k}**: " + "; ".join(f"{a}={b}" for a, b in v.items()))
    L += ["", "## 8. Histórico de versões do método", ""]
    L += [f"- `{h['versao']}` ({h['data']}): {h['descricao']}" for h in METODO_HISTORICO]
    L += ["", "## 9. Ambiente", "", "```json", json.dumps(m["dependencias"], indent=1), "```"]
    return "\n".join(L) + "\n"


def _pdf(pasta: Path, manifesto: dict, md_texto: str, imagens: list) -> Path:
    import matplotlib
    matplotlib.use("Agg")
    import matplotlib.pyplot as plt
    from matplotlib.backends.backend_pdf import PdfPages
    destino = pasta / "relatorio.pdf"
    linhas = []
    for l in md_texto.splitlines():
        linhas += textwrap.wrap(l, 110) or [""]
    with PdfPages(destino) as pdf:
        for i in range(0, len(linhas), 62):
            fig = plt.figure(figsize=(8.27, 11.69))
            fig.text(.06, .97, "\n".join(linhas[i:i + 62]), va="top", family="monospace", fontsize=7)
            pdf.savefig(fig)
            plt.close(fig)
        for img in imagens:
            fig = plt.figure(figsize=(8.27, 11.69))
            ax = fig.add_axes([.05, .05, .9, .9])
            ax.imshow(plt.imread(img))
            ax.axis("off")
            ax.set_title(Path(img).stem, fontsize=9)
            pdf.savefig(fig)
            plt.close(fig)
        d = pdf.infodict()
        d["Title"] = f"Cientometria — execução {manifesto['id']}"
    return destino


def exportar(res, manifesto: dict, biblio: dict, pasta, imagens: list | None = None,
             diagnosticos: dict | None = None, formatos=("csv", "xlsx", "pdf", "md", "json")) -> list:
    pasta = Path(pasta)
    pasta.mkdir(parents=True, exist_ok=True)
    feitos = []
    corpus = res.corpus.sort_values("score_final_100", ascending=False) if len(res.corpus) else res.corpus
    exp = corpus[[c for c in COLUNAS_EXPORTACAO if c in corpus]]
    tabelas = {"corpus": exp, "nucleo_a": exp[exp["fascia"] == "Núcleo A"] if len(exp) else exp,
               "contagens": pd.DataFrame([res.contagens]),
               "estratos": pd.DataFrame([res.estratos()])}
    tabelas.update({f"bib_{k}": v for k, v in (biblio or {}).items() if isinstance(v, pd.DataFrame)})
    if "csv" in formatos:
        (pasta / "csv").mkdir(exist_ok=True)
        for k, v in tabelas.items():
            v.to_csv(pasta / "csv" / f"{k}.csv", index=False, encoding="utf-8")
        feitos.append(str(pasta / "csv"))
    if "xlsx" in formatos:
        destino = pasta / "resultados.xlsx"
        with pd.ExcelWriter(destino, engine="openpyxl") as xw:
            usados = set()
            for k, v in tabelas.items():
                nome = k[:31]
                while nome in usados:
                    nome = nome[:29] + str(len(usados))
                usados.add(nome)
                v.head(1_000_000).to_excel(xw, sheet_name=nome, index=False)
        feitos.append(str(destino))
    md_texto = relatorio_metodologico(manifesto, diagnosticos)
    if "md" in formatos:
        (pasta / "relatorio_metodologico.md").write_text(md_texto, encoding="utf-8")
        feitos.append(str(pasta / "relatorio_metodologico.md"))
    if "json" in formatos:
        (pasta / "parametros.json").write_text(json.dumps(manifesto["parametros"], ensure_ascii=False, indent=1),
                                               encoding="utf-8")
        feitos.append(str(pasta / "parametros.json"))
    if "pdf" in formatos:
        feitos.append(str(_pdf(pasta, manifesto, md_texto, imagens or [])))
    return feitos
