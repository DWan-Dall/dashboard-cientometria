"""Réplica das regras de contagem de `analise-aprofundada-v3/cientometria_master.R` (v2.3).

Existe só para AUDITORIA DA MIGRAÇÃO: permite comparar, número a número, o que o R
produziu (`resultados_cientometria/`) com uma implementação Python das mesmas regras,
e separar diferenças de porte (erros) de diferenças de definição (escolhas documentadas
em `bibliometria.py`). Não é usada pela triagem nem pelas análises padrão.

Regras do R reproduzidas aqui (e onde `bibliometria.py` difere — ver MIGRATION.md):
- texto: `stri_trans_general("Latin-ASCII")` + `str_squish`;
- `split_multi`: divide, aplica squish e descarta vazios, SEM deduplicar no registro;
- países: unidade = AFILIAÇÃO (um documento com 3 afiliações chinesas conta 3);
- autores/coautoria: separados por vírgula, únicos por `artigo_id`
  (DOI limpo em maiúsculas, senão DOI, senão título);
- palavras-chave: 1ª fonte não vazia entre author_keywords, index_keywords e
  technologies, com `str_to_title`; arestas com n ≥ 3; clusters = componentes conexos;
- séries temporais: anos sem publicação ficam NA (`replace_na()` sem valor);
- scores por ano: anos sem artigos ficam 0;
- "áreas" = contagem da coluna `fascia` (estratos);
- sobreposição: `artigo_id` como acima; bases distintas por artigo.
"""
from __future__ import annotations
import itertools
import re
import unicodedata
from collections import Counter

import numpy as np
import pandas as pd

from .bibliometria import categoria_tecnologia


def squish(x) -> str:
    return re.sub(r"\s+", " ", str(x)).strip()


# Pontuação que a transformação ICU "Latin-ASCII" (stringi) converte para ASCII.
_PONTUACAO_ICU = str.maketrans({"\u2018": "'", "\u2019": "'", "\u201a": ",", "\u201b": "'", "\u2032": "'",
                                "\u201c": '"', "\u201d": '"', "\u201e": ",,", "\u201f": '"', "\u2033": '"',
                                "\u2010": "-", "\u2011": "-", "\u2012": "-", "\u2013": "-", "\u2014": "-",
                                "\u2015": "-", "\u2212": "-", "\u00a0": " ", "\u2009": " ", "\u202f": " ",
                                "\u2026": "...", "\u00ab": "<<", "\u00bb": ">>", "\u2039": "<", "\u203a": ">"})


_LATINAS_SEM_DECOMPOSICAO = {"ı": "i", "ł": "l", "Ł": "L", "ø": "o", "Ø": "O", "đ": "d", "Đ": "D", "ß": "ss",
                             "æ": "ae", "Æ": "AE", "œ": "oe", "Œ": "OE", "þ": "th", "Þ": "TH", "ð": "d", "Ð": "D",
                             "ħ": "h", "Ħ": "H", "ŀ": "l", "Ŀ": "L", "ŋ": "n", "Ŋ": "N"}


def latin_ascii(x) -> str:
    """Aproximação de stri_trans_general(x, "Latin-ASCII"): só letras LATINAS perdem
    diacríticos (cirílico, grego etc. ficam como estão) e a pontuação tipográfica vira ASCII."""
    out = []
    for ch in str(x).translate(_PONTUACAO_ICU):
        if "\uff01" <= ch <= "\uff5e":                 # formas de largura total -> ASCII
            out.append(chr(ord(ch) - 0xFEE0))
        elif ch in _LATINAS_SEM_DECOMPOSICAO:
            out.append(_LATINAS_SEM_DECOMPOSICAO[ch])
        elif ord(ch) > 127 and "LATIN" in unicodedata.name(ch, ""):
            out.append("".join(c for c in unicodedata.normalize("NFKD", ch) if not unicodedata.combining(c)))
        else:
            out.append(ch)
    return "".join(out)


def clean_text(x):
    if x is None or (isinstance(x, float) and np.isnan(x)):
        return np.nan
    return squish(latin_ascii(x))


def _vazio(v) -> bool:
    return v is None or (isinstance(v, float) and np.isnan(v)) or str(v) == ""


def split_multi(serie: pd.Series, sep: str) -> list[tuple[int, str]]:
    """[(posição da linha, item)] — como tidyr::separate_rows + squish + filtro de vazios."""
    out = []
    for i, v in enumerate(serie):
        if _vazio(v):
            continue
        for item in str(v).split(sep):
            item = squish(item)
            if item:
                out.append((i, item))
    return out


def artigo_id(df: pd.DataFrame) -> pd.Series:
    ids = []
    for dc, d, t in zip(df.get("doi_clean", [np.nan] * len(df)), df["doi"], df["title"]):
        if not _vazio(dc):
            ids.append(squish(dc).upper())
        elif not _vazio(d):
            ids.append(squish(d).upper())
        else:
            ids.append(squish(t).upper())
    return pd.Series(ids, index=df.index)


def preparar(df: pd.DataFrame) -> pd.DataFrame:
    """Bloco "Padronização" do R."""
    d = df.copy()
    for c in ("journal_consolidado", "source_database", "source_file", "technologies",
              "author_keywords", "index_keywords"):
        if c in d:
            d[c] = d[c].map(clean_text)
    for c in ("authors", "affiliations", "countries", "title"):
        if c in d:
            d[c] = d[c].map(lambda v: np.nan if _vazio(v) else squish(v))
    d["year"] = pd.to_numeric(d["year"], errors="coerce")
    return d


def _contagem(itens, nome):
    c = Counter(itens)
    t = pd.DataFrame(sorted(c.items(), key=lambda kv: (-kv[1], kv[0])), columns=[nome, "n"])
    return t


def bases(df):
    return _contagem([b for _, b in split_multi(df["source_database"], ";")], "base")


def areas(df):
    return _contagem(df["fascia"].tolist(), "fascia")


def periodicos(df):
    j = [x for x in df["journal_consolidado"] if not _vazio(x)]
    return _contagem(j, "journal_consolidado")


def paises(df):
    afs = split_multi(df["affiliations"], ";")
    ps = []
    for _, a in afs:
        partes = squish(a).split(",")
        p = squish(partes[-1]) if partes else ""
        if p:
            ps.append(clean_text(p))
    return _contagem(ps, "country")


def _autores_long(df):
    ids = artigo_id(df)
    pares = set()
    for i, v in enumerate(df["authors"]):
        if _vazio(v):
            continue
        for a in str(v).split(","):
            a = squish(a)
            if a:
                pares.add((ids.iloc[i], a))
    return pares


def autores(df):
    return _contagem([a for _, a in _autores_long(df)], "author")


def coautoria(df):
    por_artigo = {}
    for art, a in _autores_long(df):
        por_artigo.setdefault(art, set()).add(a)
    c = Counter()
    for autores_ in por_artigo.values():
        for x, y in itertools.combinations(sorted(autores_), 2):
            c[(x, y)] += 1
    return pd.DataFrame([(x, y, n) for (x, y), n in c.items()], columns=["author_1", "author_2", "peso"])


def _str_to_title(s: str) -> str:
    # stringr::str_to_title usa quebra de palavras do ICU: letras e dígitos formam uma palavra
    return re.sub(r"[^\W_]+", lambda m: m.group(0)[0].upper() + m.group(0)[1:].lower(), s)


def palavras_chave(df):
    fonte = None
    for c in ("author_keywords", "index_keywords"):
        if c in df and df[c].map(lambda v: not _vazio(v)).any():
            fonte = c
            break
    fonte = fonte or "technologies"
    kw = [(i, _str_to_title(k)) for i, k in split_multi(df[fonte], ";")]
    freq = _contagem([k for _, k in kw], "keyword")
    por = {}
    for i, k in kw:
        por.setdefault(i, set()).add(k)
    c = Counter()
    for ks in por.values():
        for x, y in itertools.combinations(sorted(ks), 2):
            c[(x, y)] += 1
    arestas = pd.DataFrame([(x, y, n) for (x, y), n in c.items() if n >= 3], columns=["keyword_1", "keyword_2", "n"])
    return {"fonte": fonte, "frequencia": freq, "arestas": arestas}


def clusters(arestas: pd.DataFrame):
    import networkx as nx
    g = nx.Graph()
    g.add_edges_from(zip(arestas["keyword_1"], arestas["keyword_2"]))
    comps = list(nx.connected_components(g))
    return pd.DataFrame([(k, i + 1) for i, c in enumerate(comps) for k in c], columns=["keyword", "cluster"])


def series(df):
    d = df[df["year"].notna()].copy()
    d["year"] = d["year"].astype(int)
    anos = pd.RangeIndex(d["year"].min(), d["year"].max() + 1, name="year")
    n = d.groupby("year").size().reindex(anos)              # NA onde não há artigos (como no R)
    s = d.groupby("year")["citations"].sum().reindex(anos)
    m = d.groupby("year")["citations"].mean().reindex(anos)
    return pd.DataFrame({"n_artigos": n, "total_citacoes": s, "media_citacoes": m}).reset_index()


def scores(df):
    cols = {"A": "A_score", "C": "C_norm", "R": "R_norm", "T": "T_score"}
    d = df[df["year"].notna()].copy()
    d["year"] = d["year"].astype(int)
    longo = d.melt(id_vars="year", value_vars=list(cols.values()), var_name="col", value_name="valor")
    longo["score"] = longo["col"].map({v: k for k, v in cols.items()})
    media = longo.groupby(["year", "score"])["valor"].mean()
    anos = range(int(df["year"].min()), int(df["year"].max()) + 1)
    idx = pd.MultiIndex.from_product([anos, sorted(cols)], names=["year", "score"])
    return media.reindex(idx, fill_value=0).rename("media").reset_index()


def tecnologias(df):
    d = df[df["year"].notna()].reset_index(drop=True)
    linhas = [(int(d.loc[i, "year"]), categoria_tecnologia(clean_text(t).lower()))
              for i, t in split_multi(d["technologies"], ";")]
    t = pd.DataFrame(linhas, columns=["year", "categoria"]).value_counts().rename("frequencia").reset_index()
    cats = ["Deep Learning", "Ensemble", "Machine Learning Clássico", "Metaheurísticos", "Outros"]
    anos = range(int(df["year"].min()), int(df["year"].max()) + 1)
    idx = pd.MultiIndex.from_product([anos, cats], names=["year", "categoria"])
    return t.set_index(["year", "categoria"])["frequencia"].reindex(idx, fill_value=0).reset_index()


def sobreposicao(df):
    ids = artigo_id(df)
    pares = {(ids.iloc[i], b) for i, b in split_multi(df["source_database"], ";")}
    por = {}
    for art, b in pares:
        por.setdefault(art, set()).add(b)
    m = Counter()
    for bs in por.values():
        for x in bs:
            for y in bs:
                m[(x, y)] += 1
    matriz = pd.DataFrame([(x, y, n) for (x, y), n in m.items()], columns=["base_1", "base_2", "n_compartilhados"])
    resumo = pd.Series([len(v) for v in por.values()]).value_counts().sort_index()
    return {"matriz": matriz, "por_numero_de_bases": resumo.rename_axis("n_bases").rename("n_artigos").reset_index()}
