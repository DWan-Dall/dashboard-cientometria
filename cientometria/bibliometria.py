"""Análises bibliométricas complementares (descritivas). NÃO alteram a triagem.

Migradas de `analise-aprofundada-v3/cientometria_master.R` (v2.3) e do roteiro
bibliometrix de `cientometria/main.R`. Diferenças deliberadas em relação ao R
(ver MIGRATION.md):
- "Áreas": o R contava a coluna `fascia` (estrato do escore) sob o rótulo "Áreas de
  conhecimento". Aqui `areas()` usa a área temática da base (Fields of Study, Subject
  Area, WoS Categories); os estratos ficam em `estratos()`.
- Autores: o R separava autores por vírgula, o que parte nomes no formato "Sobrenome, N."
  Aqui o separador é ';' quando existe na coluna, senão ','.
- Clusters temáticos: o R usava componentes conexos; aqui Louvain com semente fixa
  (componentes conexos continuam disponíveis em `coocorrencia(...)['componentes']`).

Entrada: DataFrame no esquema de `entrada.normalizar_estendido` (colunas ausentes são
toleradas; a análise correspondente é marcada como "não executada" em `cobertura`).
"""
from __future__ import annotations
import itertools
import re
from collections import Counter

import numpy as np
import pandas as pd

SEMENTE = 123

# ---------------------------------------------------------------------------
# utilidades
# ---------------------------------------------------------------------------


def _tem(df, col):
    return col in df and df[col].notna().any() and (df[col].astype(str).str.strip() != "").any()


def _sep(serie: pd.Series) -> str:
    amostra = serie.dropna().astype(str).head(500)
    return ";" if amostra.str.contains(";").any() else ","


def dividir(serie: pd.Series, sep: str | None = None, minusculo: bool = False) -> pd.Series:
    """Série de listas (itens limpos, sem repetição dentro do registro)."""
    sep = sep or _sep(serie)

    def f(v):
        if v is None or (isinstance(v, float) and np.isnan(v)) or v is pd.NA:
            return []
        itens = [re.sub(r"\s+", " ", x).strip().strip(".") for x in str(v).split(sep)]
        itens = [x.lower() if minusculo else x for x in itens if x and x.lower() not in ("nan", "none", "<na>")]
        return list(dict.fromkeys(itens))
    return serie.map(f)


def _freq(listas: pd.Series, nome: str) -> pd.DataFrame:
    c = Counter(itertools.chain.from_iterable(listas))
    return pd.DataFrame(c.most_common(), columns=[nome, "n_documentos"])


def _arestas(listas: pd.Series, a: str, b: str, max_itens: int = 60) -> pd.DataFrame:
    c = Counter()
    for itens in listas:
        itens = sorted(itens)[:max_itens]
        c.update(itertools.combinations(itens, 2))
    linhas = [(x, y, n) for (x, y), n in c.items()]
    return pd.DataFrame(linhas, columns=[a, b, "peso"]).sort_values("peso", ascending=False, ignore_index=True)


def _grafo(arestas: pd.DataFrame, a: str, b: str):
    import networkx as nx
    g = nx.Graph()
    for x, y, w in arestas[[a, b, "peso"]].itertuples(index=False):
        g.add_edge(x, y, weight=float(w))
    return g


def _comunidades(g) -> dict:
    import networkx as nx
    if g.number_of_nodes() == 0:
        return {}
    comms = nx.community.louvain_communities(g, weight="weight", seed=SEMENTE)
    comms = sorted(comms, key=lambda s: (-len(s), sorted(s)[0]))
    return {n: i + 1 for i, s in enumerate(comms) for n in s}


# ---------------------------------------------------------------------------
# análises
# ---------------------------------------------------------------------------


def producao_anual(df: pd.DataFrame) -> pd.DataFrame:
    d = df[df["year"].notna()].copy()
    if d.empty:
        return pd.DataFrame(columns=["ano", "n_documentos", "citacoes_total", "citacoes_media"])
    d["year"] = d["year"].astype(int)
    cit = pd.to_numeric(d.get("citations"), errors="coerce") if "citations" in d else pd.Series(0, index=d.index)
    d["_c"] = cit.fillna(0)
    g = d.groupby("year").agg(n_documentos=("year", "size"), citacoes_total=("_c", "sum"), citacoes_media=("_c", "mean"))
    anos = pd.RangeIndex(g.index.min(), g.index.max() + 1, name="year")
    g = g.reindex(anos, fill_value=0).reset_index().rename(columns={"year": "ano"})
    g["citacoes_media"] = g["citacoes_media"].round(3)
    g["crescimento_pct"] = g["n_documentos"].pct_change().replace([np.inf, -np.inf], np.nan).mul(100).round(1)
    return g


def autores(df: pd.DataFrame) -> dict:
    if not _tem(df, "authors"):
        return {}
    listas = dividir(df["authors"])
    freq = _freq(listas, "autor")
    por_doc = listas.map(len)
    return {"frequencia": freq,
            "resumo": pd.DataFrame([{"autores_unicos": len(freq), "documentos_com_autor": int((por_doc > 0).sum()),
                                     "media_autores_por_documento": round(float(por_doc[por_doc > 0].mean()), 2)
                                     if (por_doc > 0).any() else 0,
                                     "separador": _sep(df["authors"])}])}


_INST = re.compile(r"(univ|universidad|universidade|université|institut|instituto|college|school|academy|"
                   r"centre|center|laborat|agency|ministry|council|survey|corporation|company)", re.I)


def _instituicao(afiliacao: str) -> str:
    partes = [p.strip() for p in afiliacao.split(",") if p.strip()]
    for p in partes:
        if _INST.search(p):
            return p
    return partes[0] if partes else afiliacao


def instituicoes(df: pd.DataFrame) -> pd.DataFrame:
    if not _tem(df, "affiliations"):
        return pd.DataFrame()
    listas = dividir(df["affiliations"], sep=";").map(lambda xs: list(dict.fromkeys(_instituicao(x) for x in xs)))
    return _freq(listas, "instituicao")


_PAISES_ALIAS = {
    "usa": "United States", "u.s.a.": "United States", "united states of america": "United States",
    "us": "United States", "uk": "United Kingdom", "england": "United Kingdom", "scotland": "United Kingdom",
    "wales": "United Kingdom", "northern ireland": "United Kingdom", "peoples r china": "China",
    "people's republic of china": "China", "pr china": "China", "p.r. china": "China",
    "south korea": "South Korea", "republic of korea": "South Korea", "korea": "South Korea",
    "brasil": "Brazil", "iran (islamic republic of)": "Iran", "russian federation": "Russia",
    "viet nam": "Vietnam", "türkiye": "Turkey", "turkiye": "Turkey", "the netherlands": "Netherlands",
}


def _pais(texto: str) -> str | None:
    t = re.sub(r"[\d\-]+", " ", texto).strip().strip(".").strip()
    ultimo = t.split(",")[-1].strip()
    ultimo = re.sub(r"\s+", " ", ultimo)
    # "Iowa City IA USA" -> última palavra quando é sigla conhecida
    if ultimo.lower() not in _PAISES_ALIAS and len(ultimo.split()) > 1:
        cauda = ultimo.split()[-1]
        if cauda.lower() in _PAISES_ALIAS:
            ultimo = cauda
    if not ultimo or len(ultimo) > 40:
        return None
    return _PAISES_ALIAS.get(ultimo.lower(), ultimo.title() if ultimo.islower() else ultimo)


def paises(df: pd.DataFrame) -> pd.DataFrame:
    """Documentos por país (contagem inteira: cada país conta 1 vez por documento)."""
    if _tem(df, "countries"):
        listas = dividir(df["countries"], sep=";").map(lambda xs: list(dict.fromkeys(
            _PAISES_ALIAS.get(x.lower(), x) for x in xs)))
        origem = "countries"
    elif _tem(df, "affiliations"):
        listas = dividir(df["affiliations"], sep=";").map(
            lambda xs: list(dict.fromkeys(p for p in (_pais(x) for x in xs) if p)))
        origem = "affiliations (último segmento)"
    else:
        return pd.DataFrame()
    f = _freq(listas, "pais")
    f.attrs["origem"] = origem
    f["origem"] = origem
    return f


def periodicos(df: pd.DataFrame, top: int | None = None) -> pd.DataFrame:
    if not _tem(df, "source"):
        return pd.DataFrame()
    s = df["source"].dropna().astype(str).str.strip()
    s = s[~s.str.lower().isin(["", "unknown", "nan"])].map(lambda x: re.sub(r"\s+", " ", x).title())
    cit = pd.to_numeric(df.loc[s.index, "citations"], errors="coerce").fillna(0) if "citations" in df else 0
    t = pd.DataFrame({"periodico": s, "cit": cit}).groupby("periodico").agg(
        n_documentos=("periodico", "size"), citacoes=("cit", "sum")).sort_values(
        ["n_documentos", "citacoes"], ascending=False).reset_index()
    t["pct_acumulado"] = (t["n_documentos"].cumsum() / t["n_documentos"].sum() * 100).round(1)
    t["zona_bradford"] = pd.cut(t["pct_acumulado"], [0, 33.4, 66.7, 100.1], labels=[1, 2, 3]).astype(int)
    return t.head(top) if top else t


def areas(df: pd.DataFrame) -> pd.DataFrame:
    if not _tem(df, "subject_area"):
        return pd.DataFrame()
    return _freq(dividir(df["subject_area"], sep=";"), "area")


def estratos(df: pd.DataFrame) -> pd.DataFrame:
    if "fascia" not in df:
        return pd.DataFrame()
    return df["fascia"].value_counts().rename_axis("estrato").reset_index(name="n_documentos")


def coautoria(df: pd.DataFrame, top_nos: int = 60) -> dict:
    if not _tem(df, "authors"):
        return {}
    import networkx as nx
    listas = dividir(df["authors"])
    arestas = _arestas(listas, "autor_1", "autor_2")
    if arestas.empty:
        return {"arestas": arestas}
    g = _grafo(arestas, "autor_1", "autor_2")
    com = _comunidades(g)
    grau = dict(g.degree())
    nos = pd.DataFrame({"autor": list(grau), "grau": list(grau.values())})
    nos["forca"] = nos["autor"].map(dict(g.degree(weight="weight")))
    nos["comunidade"] = nos["autor"].map(com)
    nos = nos.sort_values(["grau", "forca"], ascending=False, ignore_index=True)
    nucleo = set(nos.head(top_nos)["autor"])
    sub = g.subgraph(nucleo)
    btw = nx.betweenness_centrality(sub, seed=SEMENTE) if sub.number_of_nodes() else {}
    nos["intermediacao_nucleo"] = nos["autor"].map(btw).round(4)
    resumo = pd.DataFrame([{"autores": g.number_of_nodes(), "arestas": g.number_of_edges(),
                            "arestas_peso_ge_2": int((arestas["peso"] >= 2).sum()),
                            "componentes": nx.number_connected_components(g),
                            "maior_componente": len(max(nx.connected_components(g), key=len)),
                            "comunidades_louvain": len(set(com.values())),
                            "densidade": round(nx.density(g), 6)}])
    return {"arestas": arestas, "nos": nos, "resumo": resumo}


def coocorrencia(df: pd.DataFrame, campo: str | None = None, min_freq: int = 3, min_peso: int = 2) -> dict:
    """Coocorrência de palavras-chave, clusters (Louvain) e mapa temático (Callon)."""
    if campo is None:
        campo = next((c for c in ("author_keywords", "keywords", "index_keywords") if _tem(df, c)), None)
    if campo is None or not _tem(df, campo):
        return {}
    import networkx as nx
    listas = dividir(df[campo], sep=";", minusculo=True)
    freq = _freq(listas, "termo")
    manter = set(freq[freq["n_documentos"] >= min_freq]["termo"])
    listas_f = listas.map(lambda xs: [x for x in xs if x in manter])
    arestas = _arestas(listas_f, "termo_1", "termo_2")
    arestas = arestas[arestas["peso"] >= min_peso].reset_index(drop=True)
    saida = {"campo": campo, "frequencia": freq, "arestas": arestas}
    if arestas.empty:
        return saida
    g = _grafo(arestas, "termo_1", "termo_2")
    com = _comunidades(g)
    fmap = dict(zip(freq["termo"], freq["n_documentos"]))
    clusters = pd.DataFrame({"termo": list(com), "cluster": list(com.values())})
    clusters["n_documentos"] = clusters["termo"].map(fmap)
    clusters = clusters.sort_values(["cluster", "n_documentos"], ascending=[True, False], ignore_index=True)
    comp = {n: i + 1 for i, c in enumerate(sorted(nx.connected_components(g), key=len, reverse=True)) for n in c}
    # mapa temático (Callon): centralidade = soma dos pesos externos; densidade = média dos pesos internos
    linhas = []
    for k, grupo in clusters.groupby("cluster"):
        membros = set(grupo["termo"])
        interno = [d["weight"] for u, v, d in g.edges(membros, data=True) if u in membros and v in membros]
        externo = [d["weight"] for u, v, d in g.edges(membros, data=True) if (u in membros) != (v in membros)]
        linhas.append({"cluster": k, "rotulo": "; ".join(grupo["termo"].head(3)), "n_termos": len(membros),
                       "frequencia": int(grupo["n_documentos"].sum()),
                       "centralidade": float(sum(externo)),
                       "densidade": float(np.mean(interno)) if interno else 0.0,
                       "termos": "; ".join(grupo["termo"].head(8))})
    mapa = pd.DataFrame(linhas)
    if len(mapa):
        mc, md = mapa["centralidade"].median(), mapa["densidade"].median()
        mapa["quadrante"] = np.select(
            [(mapa.centralidade >= mc) & (mapa.densidade >= md), (mapa.centralidade < mc) & (mapa.densidade >= md),
             (mapa.centralidade >= mc) & (mapa.densidade < md)],
            ["motor", "nicho", "básico/transversal"], "emergente ou em declínio")
    saida.update({"clusters": clusters, "mapa_tematico": mapa,
                  "componentes": pd.DataFrame({"termo": list(comp), "componente": list(comp.values())})})
    return saida


def _referencias(df: pd.DataFrame) -> pd.Series:
    def norm(r):
        r = re.sub(r"\s+", " ", r.lower()).strip()
        m = re.search(r"10\.\d{4,9}/\S+", r)
        return ("doi:" + m.group(0).rstrip(".,;")) if m else r[:120]
    return dividir(df["references"], sep=";").map(lambda xs: list(dict.fromkeys(norm(x) for x in xs if len(x) > 5)))


def cocitacao(df: pd.DataFrame, min_citacoes: int = 2, max_refs: int = 300) -> dict:
    if not _tem(df, "references"):
        return {}
    refs = _referencias(df)
    freq = _freq(refs, "referencia")
    top = set(freq[freq["n_documentos"] >= min_citacoes].head(max_refs)["referencia"])
    arestas = _arestas(refs.map(lambda xs: [x for x in xs if x in top]), "ref_1", "ref_2", max_itens=max_refs)
    return {"referencias_mais_citadas": freq, "arestas": arestas}


def acoplamento(df: pd.DataFrame, min_compartilhadas: int = 1, max_docs_por_ref: int = 200) -> dict:
    if not _tem(df, "references"):
        return {}
    refs = _referencias(df)
    ident = df["title"].astype(str).str.slice(0, 80) if "title" in df else df.index.astype(str)
    indice = {}
    for i, xs in zip(df.index, refs):
        for r in xs:
            indice.setdefault(r, []).append(i)
    c = Counter()
    for docs in indice.values():
        if 1 < len(docs) <= max_docs_por_ref:
            c.update(itertools.combinations(sorted(docs), 2))
    linhas = [(ident[a], ident[b], n) for (a, b), n in c.items() if n >= min_compartilhadas]
    arestas = pd.DataFrame(linhas, columns=["doc_1", "doc_2", "peso"]).sort_values("peso", ascending=False, ignore_index=True)
    return {"arestas": arestas}


# --- tecnologias (port de categoria_tecnologia() do R, com detecção no texto) ---
TECNOLOGIAS = {
    "LSTM": r"\blstm\b|long short[- ]term memory", "GRU": r"\bgru\b|gated recurrent",
    "CNN": r"\bcnn\b|convolutional", "RNN": r"\brnn\b|recurrent neural", "Transformer": r"transformer",
    "U-Net": r"u-?net\b", "ConvLSTM": r"convlstm", "Attention": r"attention mechanism|\battention\b",
    "Random Forest": r"random forest", "XGBoost": r"xgboost", "Gradient Boosting": r"gradient boost",
    "AdaBoost": r"adaboost", "SVM": r"\bsvm\b|support vector", "Decision Tree": r"decision tree",
    "KNN": r"\bk-?nn\b|nearest neighbo", "Naive Bayes": r"naive bayes", "Logistic Regression": r"logistic regression",
    "ANN/MLP": r"artificial neural network|\bann\b|multilayer perceptron|\bmlp\b",
    "Deep Learning": r"deep learning", "Machine Learning": r"machine learning",
    "Ensemble": r"\bensemble", "Genetic Algorithm": r"genetic algorithm", "PSO": r"particle swarm|\bpso\b",
    "Fuzzy": r"\bfuzzy", "Federated Learning": r"federated learning", "Graph Neural Network": r"graph neural|\bgnn\b",
}


def categoria_tecnologia(x: str) -> str:
    x2 = str(x).lower()
    if re.search(r"deep learning|lstm|cnn|rnn|gru|transformer|u-net|convlstm|neural network|seq2seq|attention|ann/mlp|graph neural", x2):
        return "Deep Learning"
    if re.search(r"ensemble|bagging|boosting|xgboost|gradient boosting|adaboost|stacking|random forest", x2):
        return "Ensemble"
    if re.search(r"genetic algorithm|particle swarm|pso|metaheuristic|firefly|grey wolf|optimization|ant colony", x2):
        return "Metaheurísticos"
    if re.search(r"machine learning|svm|support vector|decision tree|logistic regression|linear regression|k-nn|knn|naive bayes|lasso|ridge|forest", x2):
        return "Machine Learning Clássico"
    return "Outros"


def detectar_tecnologias(df: pd.DataFrame) -> pd.Series:
    if _tem(df, "technologies"):
        return dividir(df["technologies"], sep=";")
    texto = (df.get("title", "").astype(str) + " " + df.get("abstract", "").astype(str) + " " +
             df.get("keywords", "").astype(str)).str.lower()
    rx = {k: re.compile(v) for k, v in TECNOLOGIAS.items()}
    return texto.map(lambda t: [k for k, r in rx.items() if r.search(t)])


def tecnologias(df: pd.DataFrame) -> dict:
    listas = detectar_tecnologias(df)
    freq = _freq(listas, "tecnologia")
    if freq.empty:
        return {}
    freq["categoria"] = freq["tecnologia"].map(categoria_tecnologia)
    d = pd.DataFrame({"ano": df["year"], "tec": listas}).dropna(subset=["ano"]).explode("tec").dropna()
    if d.empty:
        return {"frequencia": freq}
    d["ano"] = d["ano"].astype(int)
    d["categoria"] = d["tec"].map(categoria_tecnologia)
    cats = ["Deep Learning", "Ensemble", "Machine Learning Clássico", "Metaheurísticos", "Outros"]
    tab = pd.crosstab(d["ano"], d["categoria"]).reindex(columns=cats, fill_value=0)
    tab = tab.reindex(range(tab.index.min(), tab.index.max() + 1), fill_value=0)
    pct = tab.div(tab.sum(axis=1).replace(0, np.nan), axis=0).fillna(0).mul(100).round(2)
    return {"frequencia": freq,
            "por_ano": tab.rename_axis("ano").reset_index(),
            "percentual_por_ano": pct.rename_axis("ano").reset_index(),
            "origem": "coluna technologies" if _tem(df, "technologies") else "detecção por dicionário no texto"}


def scores_por_ano(df: pd.DataFrame) -> pd.DataFrame:
    cols = [c for c in ("C_norm", "R_norm", "T_score", "A_score", "score_final_100") if c in df]
    if not cols or "year" not in df:
        return pd.DataFrame()
    return df.dropna(subset=["year"]).assign(ano=lambda x: x["year"].astype(int)).groupby("ano")[cols].mean().round(4).reset_index()


def analisar(df: pd.DataFrame, bruto: pd.DataFrame | None = None, min_freq_kw: int = 3) -> dict:
    """Executa todas as análises possíveis. Devolve {nome: DataFrame} + 'cobertura'."""
    from .consolidacao import sobreposicao
    out, cob = {}, []

    def reg(nome, resultado, motivo):
        if isinstance(resultado, pd.DataFrame):
            resultado = {"": resultado} if not resultado.empty else {}
        ok = bool(resultado)
        for k, v in (resultado or {}).items():
            if isinstance(v, pd.DataFrame):
                out[f"{nome}_{k}".rstrip("_")] = v
        cob.append({"analise": nome, "executada": "sim" if ok else "não", "observacao": "" if ok else motivo})

    reg("producao_anual", producao_anual(df), "sem ano")
    reg("autores", autores(df), "sem coluna de autores")
    reg("instituicoes", instituicoes(df), "sem afiliações")
    reg("paises", paises(df), "sem países/afiliações")
    reg("periodicos", periodicos(df), "sem periódico")
    reg("areas", areas(df), "sem área temática na exportação")
    reg("estratos", estratos(df), "sem estratos (não é o corpus escorado)")
    reg("coautoria", coautoria(df), "sem autores")
    reg("coocorrencia", coocorrencia(df, min_freq=min_freq_kw), "sem palavras-chave")
    reg("cocitacao", cocitacao(df), "exportação sem referências citadas")
    reg("acoplamento", acoplamento(df), "exportação sem referências citadas")
    reg("tecnologias", tecnologias(df), "nenhuma tecnologia detectada")
    reg("scores_por_ano", scores_por_ano(df), "sem escores")
    if bruto is not None and len(bruto):
        reg("sobreposicao_bases", sobreposicao(bruto), "sem bases")
    out["cobertura"] = pd.DataFrame(cob)
    return out
