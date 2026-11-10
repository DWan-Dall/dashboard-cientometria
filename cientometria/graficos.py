"""Gráficos em alta resolução (PNG 300 dpi por padrão). Só desenham resultados prontos."""
from __future__ import annotations
from pathlib import Path

import numpy as np
import pandas as pd

DPI = 300
AZUL, VERMELHO, CINZA = "#2C6FB7", "#B03A2E", "#7A7A7A"
CORES_ESTRATO = {"Núcleo A": "#1B5E20", "Núcleo B": "#2C6FB7", "Periférico": "#C58B00", "Descarte": "#9E9E9E"}


def _plt():
    import matplotlib
    matplotlib.use("Agg")
    import matplotlib.pyplot as plt
    plt.rcParams.update({"font.size": 10, "axes.spines.top": False, "axes.spines.right": False,
                         "axes.grid": True, "grid.alpha": .25, "figure.dpi": 100})
    return plt


def _salvar(fig, caminho, dpi=DPI):
    caminho = Path(caminho)
    caminho.parent.mkdir(parents=True, exist_ok=True)
    fig.tight_layout()
    fig.savefig(caminho, dpi=dpi, facecolor="white")
    _plt().close(fig)
    return str(caminho)


def barras_horizontais(df, rotulo, valor, titulo, caminho, top=20, cor=AZUL):
    plt = _plt()
    d = df.head(top).iloc[::-1]
    fig, ax = plt.subplots(figsize=(9, max(3, .32 * len(d) + 1)))
    ax.barh(d[rotulo].astype(str).str.slice(0, 60), d[valor], color=cor)
    for i, v in enumerate(d[valor]):
        ax.text(v, i, f" {v:g}", va="center", fontsize=8)
    ax.set_title(titulo)
    ax.set_xlabel(valor.replace("_", " "))
    ax.grid(axis="y", visible=False)
    return _salvar(fig, caminho)


def serie_anual(df, caminho, titulo="Produção científica por ano"):
    plt = _plt()
    fig, ax1 = plt.subplots(figsize=(10, 4.5))
    ax1.bar(df["ano"], df["n_documentos"], color=AZUL, label="documentos")
    ax1.set_ylabel("documentos")
    ax2 = ax1.twinx()
    ax2.plot(df["ano"], df["citacoes_total"], color=VERMELHO, marker="o", ms=3, label="citações")
    ax2.set_ylabel("citações (total)")
    ax2.grid(False)
    ax1.set_title(titulo)
    return _salvar(fig, caminho)


def estratos(contagens: dict, caminho, titulo="Estratos do corpus"):
    plt = _plt()
    k = list(contagens)
    fig, ax = plt.subplots(figsize=(6, 3.5))
    ax.bar(k, [contagens[x] for x in k], color=[CORES_ESTRATO.get(x, CINZA) for x in k])
    for i, x in enumerate(k):
        ax.text(i, contagens[x], str(contagens[x]), ha="center", va="bottom")
    ax.set_title(titulo)
    return _salvar(fig, caminho)


def histograma_escore(corpus, cortes, caminho):
    plt = _plt()
    fig, ax = plt.subplots(figsize=(8, 4))
    ax.hist(corpus["score_final_100"], bins=40, color=AZUL)
    for c in cortes:
        ax.axvline(c, color=VERMELHO, ls="--", lw=1)
    ax.set_xlabel("escore final (0–100, min–max no corpus)")
    ax.set_ylabel("artigos")
    ax.set_title("Distribuição do escore e cortes")
    return _salvar(fig, caminho)


def fluxo(contagens: dict, caminho):
    plt = _plt()
    etapas = [("Registros", contagens["registros"]), ("Após DOI", contagens["apos_doi"]),
              ("Únicos", contagens["unicos"]), ("Candidatos", contagens["candidatos_antes_da_exclusao"]),
              ("Corpus", contagens["corpus"])]
    fig, ax = plt.subplots(figsize=(8, 3.5))
    ax.bar([e[0] for e in etapas], [e[1] for e in etapas], color=AZUL)
    for i, (_, v) in enumerate(etapas):
        ax.text(i, v, f"{v:,}".replace(",", "."), ha="center", va="bottom")
    ax.set_title("Fluxo da triagem")
    return _salvar(fig, caminho)


def rede(arestas, a, b, caminho, titulo, top_nos=60, comunidades: dict | None = None):
    import networkx as nx
    plt = _plt()
    g = nx.Graph()
    for x, y, w in arestas[[a, b, "peso"]].itertuples(index=False):
        g.add_edge(x, y, weight=float(w))
    if g.number_of_nodes() == 0:
        return None
    forca = dict(g.degree(weight="weight"))
    nos = sorted(forca, key=forca.get, reverse=True)[:top_nos]
    s = g.subgraph(nos)
    pos = nx.spring_layout(s, seed=123, k=1.2 / np.sqrt(max(len(s), 1)))
    fig, ax = plt.subplots(figsize=(11, 9))
    ax.axis("off")
    pesos = np.array([d["weight"] for _, _, d in s.edges(data=True)] or [1])
    nx.draw_networkx_edges(s, pos, ax=ax, alpha=.25, width=.4 + 2.5 * pesos / pesos.max(), edge_color=CINZA)
    cores = [comunidades.get(n, 0) if comunidades else 0 for n in s.nodes]
    tam = np.array([forca[n] for n in s.nodes])
    nx.draw_networkx_nodes(s, pos, ax=ax, node_size=40 + 600 * tam / tam.max(), node_color=cores,
                           cmap="tab20", alpha=.85)
    rot = {n: n[:30] for n in nos[:25]}
    nx.draw_networkx_labels(s, pos, labels=rot, ax=ax, font_size=7)
    ax.set_title(titulo)
    return _salvar(fig, caminho)


def mapa_tematico(mapa, caminho):
    plt = _plt()
    if mapa is None or mapa.empty:
        return None
    fig, ax = plt.subplots(figsize=(8, 7))
    ax.scatter(mapa["centralidade"], mapa["densidade"], s=40 + mapa["frequencia"] * 3, alpha=.5, color=AZUL)
    for _, r in mapa.iterrows():
        ax.annotate(r["rotulo"][:40], (r["centralidade"], r["densidade"]), fontsize=7, ha="center")
    ax.axvline(mapa["centralidade"].median(), color=CINZA, ls="--")
    ax.axhline(mapa["densidade"].median(), color=CINZA, ls="--")
    ax.set_xlabel("centralidade (relevância)")
    ax.set_ylabel("densidade (desenvolvimento)")
    ax.set_title("Mapa temático (Callon)")
    return _salvar(fig, caminho)


def tecnologias_ano(pct, caminho):
    plt = _plt()
    if pct is None or pct.empty:
        return None
    fig, ax = plt.subplots(figsize=(10, 4.5))
    for c in pct.columns[1:]:
        ax.plot(pct["ano"], pct[c], marker="o", ms=3, label=c)
    ax.set_ylabel("% das menções no ano")
    ax.legend(fontsize=8)
    ax.set_title("Evolução das tecnologias")
    return _salvar(fig, caminho)


def heatmap_sobreposicao(matriz, caminho):
    plt = _plt()
    if matriz is None or matriz.empty:
        return None
    m = matriz.set_index("base")
    fig, ax = plt.subplots(figsize=(1.2 * len(m) + 3, 1.0 * len(m) + 2))
    im = ax.imshow(m.values, cmap="Blues")
    ax.set_xticks(range(len(m.columns)), [c[:25] for c in m.columns], rotation=45, ha="right")
    ax.set_yticks(range(len(m.index)), [c[:25] for c in m.index])
    for i in range(len(m)):
        for j in range(len(m.columns)):
            ax.text(j, i, int(m.values[i, j]), ha="center", va="center", fontsize=8)
    ax.grid(False)
    fig.colorbar(im, ax=ax)
    ax.set_title("Obras em comum entre bases")
    return _salvar(fig, caminho)


def gerar_todos(res, biblio: dict, pasta) -> list:
    """Gera os gráficos disponíveis. Devolve a lista de arquivos criados."""
    pasta = Path(pasta)
    feitos = [fluxo(res.contagens, pasta / "01-fluxo.png")]
    if len(res.corpus):
        feitos.append(estratos(res.estratos(), pasta / "02-estratos.png"))
        feitos.append(histograma_escore(res.corpus, res.cfg.cortes, pasta / "03-escore.png"))
    b = biblio
    if "producao_anual" in b:
        feitos.append(serie_anual(b["producao_anual"], pasta / "04-producao-anual.png"))
    for nome, rot, arq, tit in [("periodicos", "periodico", "05-periodicos.png", "Periódicos"),
                                ("paises", "pais", "06-paises.png", "Países"),
                                ("autores_frequencia", "autor", "07-autores.png", "Autores"),
                                ("instituicoes", "instituicao", "08-instituicoes.png", "Instituições"),
                                ("areas", "area", "09-areas.png", "Áreas"),
                                ("coocorrencia_frequencia", "termo", "10-palavras-chave.png", "Palavras-chave"),
                                ("tecnologias_frequencia", "tecnologia", "11-tecnologias.png", "Tecnologias")]:
        if nome in b and len(b[nome]):
            feitos.append(barras_horizontais(b[nome], rot, "n_documentos", tit, pasta / arq))
    if "coautoria_arestas" in b and len(b["coautoria_arestas"]):
        com = dict(zip(b["coautoria_nos"]["autor"], b["coautoria_nos"]["comunidade"])) if "coautoria_nos" in b else None
        feitos.append(rede(b["coautoria_arestas"], "autor_1", "autor_2", pasta / "12-rede-coautoria.png",
                           "Rede de coautoria (núcleo)", comunidades=com))
    if "coocorrencia_arestas" in b and len(b["coocorrencia_arestas"]):
        com = dict(zip(b["coocorrencia_clusters"]["termo"], b["coocorrencia_clusters"]["cluster"])) \
            if "coocorrencia_clusters" in b else None
        feitos.append(rede(b["coocorrencia_arestas"], "termo_1", "termo_2", pasta / "13-rede-palavras.png",
                           "Coocorrência de palavras-chave", comunidades=com))
        feitos.append(mapa_tematico(b.get("coocorrencia_mapa_tematico"), pasta / "14-mapa-tematico.png"))
    if "cocitacao_arestas" in b and len(b["cocitacao_arestas"]):
        feitos.append(rede(b["cocitacao_arestas"], "ref_1", "ref_2", pasta / "15-cocitacao.png", "Co-citação"))
    feitos.append(tecnologias_ano(b.get("tecnologias_percentual_por_ano"), pasta / "16-tecnologias-ano.png"))
    feitos.append(heatmap_sobreposicao(b.get("sobreposicao_bases_matriz"), pasta / "17-sobreposicao.png"))
    return [f for f in feitos if f]
