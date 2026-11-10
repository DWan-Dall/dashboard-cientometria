"""Consolidação: chaves de deduplicação, proveniência entre bases e revisão de duplicatas duvidosas.

A deduplicação que DEFINE o corpus está em `pipeline.consolidar` (DOI exato -> título
exato, como no original). Este módulo fornece:
- `chave_doi`: DOI bruto (original) ou normalizado (cfg.normalizar_doi);
- `chave_titulo_estrita`: título sem caixa/pontuação (diagnóstico);
- `correspondencias_duvidosas`: pares quase idênticos que NÃO foram fundidos, para
  revisão humana. A revisão é registrada (`aplicar_revisao`) e nunca automática.
- `sobreposicao`: em quantas/quais bases cada obra aparece.
"""
from __future__ import annotations
import re
import unicodedata
import pandas as pd

_PREFIXOS_DOI = re.compile(r"^(https?://(dx\.)?doi\.org/|doi:\s*|doi\s+)", re.I)


def normalizar_doi(d) -> str:
    if d is None or (isinstance(d, float) and pd.isna(d)):
        return ""
    s = str(d).strip()
    s = _PREFIXOS_DOI.sub("", s).strip().rstrip(".").lower()
    return s


def chave_doi(serie: pd.Series, cfg) -> pd.Series:
    if getattr(cfg, "normalizar_doi", False):
        return serie.map(normalizar_doi)
    return serie


def chave_titulo_estrita(t) -> str:
    s = unicodedata.normalize("NFKD", str(t))
    s = "".join(c for c in s if not unicodedata.combining(c)).lower()
    s = re.sub(r"[^a-z0-9 ]", " ", s)
    return re.sub(r"\s+", " ", s).strip()


def id_obra(df: pd.DataFrame) -> pd.Series:
    """Identificador de obra para análises entre bases: DOI normalizado, senão título estrito."""
    doi = df["doi"].map(normalizar_doi) if "doi" in df else pd.Series("", index=df.index)
    tit = df["title"].map(chave_titulo_estrita) if "title" in df else pd.Series("", index=df.index)
    return pd.Series([("doi:" + d) if d else ("tit:" + t) for d, t in zip(doi, tit)], index=df.index)


def anotar_proveniencia(consolidado: pd.DataFrame, bruto: pd.DataFrame) -> pd.DataFrame:
    """Acrescenta `bases_encontradas` e `n_bases` (todas as bases em que a obra aparece).
    Não altera nenhuma linha nem contagem."""
    b = bruto.assign(_id=id_obra(bruto))
    mapa = b.groupby("_id")["source_db"].agg(lambda s: "; ".join(sorted(set(map(str, s)))))
    c = consolidado.copy()
    ids = id_obra(c)
    c["bases_encontradas"] = ids.map(mapa).fillna(c["source_db"].astype(str))
    c["n_bases"] = c["bases_encontradas"].str.count(";") + 1
    return c


def sobreposicao(bruto: pd.DataFrame) -> dict:
    """Matriz base×base (obras em comum) e distribuição de obras por número de bases."""
    b = bruto.assign(_id=id_obra(bruto))[["_id", "source_db"]].drop_duplicates()
    b = b[~b["_id"].isin(["tit:", "tit:unknown"])]
    pres = pd.crosstab(b["_id"], b["source_db"]).clip(upper=1)
    matriz = pres.T.dot(pres).rename_axis("base").reset_index()
    dist = pres.sum(axis=1).value_counts().sort_index().rename_axis("n_bases").reset_index(name="n_obras")
    return {"matriz": matriz, "por_numero_de_bases": dist}


def correspondencias_duvidosas(df: pd.DataFrame, limiar: float = 92.0, max_pares: int = 5000) -> pd.DataFrame:
    """Pares de registros com títulos muito parecidos que a deduplicação manteve separados.

    Usa blocagem por (primeira palavra significativa) para escalar. Também aponta pares
    com o mesmo DOI normalizado mas DOI bruto diferente (ex.: caixa). Resultado é para
    REVISÃO; nada é fundido automaticamente."""
    from rapidfuzz import fuzz
    d = df.reset_index(drop=True).copy()
    d["_t"] = d["title"].map(chave_titulo_estrita)
    d["_doi"] = d["doi"].map(normalizar_doi)
    pares = []
    # (a) mesmo DOI normalizado, DOI bruto diferente
    g = d[d["_doi"] != ""].groupby("_doi")
    for _doi, grupo in g:
        if len(grupo) > 1:
            idx = list(grupo.index)
            for j in idx[1:]:
                pares.append((idx[0], j, 100.0, "DOI igual após normalização"))
    # (b) títulos quase idênticos
    pare = {"a", "an", "the", "of", "on", "in", "for", "and", "to", "using", "based", "with"}

    def bloco(t):
        for w in t.split():
            if w not in pare and len(w) > 2:
                return w
        return t[:5]

    d["_b"] = d["_t"].map(bloco)
    for _, grupo in d[d["_t"].str.len() > 15].groupby("_b"):
        if len(grupo) < 2 or len(grupo) > 3000:
            continue
        idx, tit = list(grupo.index), list(grupo["_t"])
        for a in range(len(idx)):
            for b in range(a + 1, len(idx)):
                if tit[a] == tit[b] and d.at[idx[a], "title"] == d.at[idx[b], "title"]:
                    continue
                s = fuzz.ratio(tit[a], tit[b])
                if s >= limiar:
                    pares.append((idx[a], idx[b], float(s), "título semelhante"))
            if len(pares) >= max_pares:
                break
    linhas = []
    for i, j, s, motivo in pares[:max_pares]:
        ri, rj = d.loc[i], d.loc[j]
        linhas.append({"id_a": i, "id_b": j, "similaridade": round(s, 1), "motivo": motivo,
                       "titulo_a": ri["title"], "titulo_b": rj["title"], "doi_a": ri["doi"], "doi_b": rj["doi"],
                       "ano_a": ri.get("year"), "ano_b": rj.get("year"),
                       "base_a": ri.get("source_db"), "base_b": rj.get("source_db"),
                       "decisao": ""})
    return pd.DataFrame(linhas, columns=["id_a", "id_b", "similaridade", "motivo", "titulo_a", "titulo_b",
                                         "doi_a", "doi_b", "ano_a", "ano_b", "base_a", "base_b", "decisao"])


def criterios(cfg) -> dict:
    """Descrição dos critérios de consolidação efetivamente aplicados (para o manifesto)."""
    return {
        "etapa_1": "DOI " + ("normalizado (caixa baixa, sem https://doi.org/ e doi:)"
                             if cfg.normalizar_doi else "como texto bruto (sensível a caixa)"),
        "registros_sem_doi": "mantidos" if cfg.manter_sem_doi else "DESCARTADOS na etapa de DOI (original)",
        "etapa_2": "título em caixa baixa e sem espaços nas pontas (igualdade exata)",
        "titulos_ausentes": ("nunca colapsados entre si" if cfg.manter_sem_doi
                             else "colapsados num único registro (original)"),
        "registro_mantido": "o primeiro na ordem de processamento das bases (keep='first')",
        "revisao_humana": "pares duvidosos listados em `correspondencias_duvidosas`; não fundidos automaticamente",
    }
