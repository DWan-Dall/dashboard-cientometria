"""Diagnósticos: tornam visíveis as falhas silenciosas (colunas não lidas, descartes, exclusões)."""
from __future__ import annotations
import re
import pandas as pd
from .entrada import MAPEAMENTO_FIXO, MAPEAMENTO_EXTENSAO, _col, ALIASES, campos_usados
from .nucleo import candidatos, _regex_palavra
from .pipeline import Resultado


def colunas_nao_lidas(bases: dict) -> pd.DataFrame:
    """Para cada exportação, quais campos do mapeamento ORIGINAL não existem no arquivo."""
    linhas = []
    for rotulo, (df, tipo) in bases.items():
        if len(df) == 0:
            continue
        m = MAPEAMENTO_FIXO.get(tipo, MAPEAMENTO_EXTENSAO['generico'])
        ausentes = [f"{c}='{v}'" for c, v in m.items() if v and v not in df.columns]
        disponiveis = {campo: [a for a in ALIASES[campo] if _col(df, a)] for campo in ALIASES}
        linhas.append({"base": rotulo, "registros": len(df), "campos_nao_lidos": "; ".join(ausentes) or "—",
                       "recuperaveis_com_aliases": {k: v for k, v in disponiveis.items() if v}})
    return pd.DataFrame(linhas)


def perdas_no_fluxo(res: Resultado) -> dict:
    c = res.contagens
    return {
        "registros_sem_doi_descartados": c["sem_doi"] if not res.cfg.manter_sem_doi else 0,
        "duplicatas_reais_por_doi": c["duplicatas_doi"],
        "removidos_por_titulo": c["removidos_titulo"],
        "titulos_ausentes_antes_da_dedup": int(res.bruto["title"].isin(["Unknown", ""]).sum() + res.bruto["title"].isna().sum()),
    }


def exclusao_por_trecho(res: Resultado) -> dict:
    """Quantos candidatos foram excluídos SÓ porque 'dam/dike/levee' aparece dentro de outra palavra."""
    cfg = res.cfg
    cand = candidatos(res.consolidado)
    exc = cand[cand["is_excluded"]]
    curtos = ("dam", "dike", "levee")
    rx = re.compile("|".join(_regex_palavra(k).pattern for k in curtos), re.I)

    def so_substring(r):
        t = (str(r["title"]) + " " + str(r["abstract"])).lower()
        outros = any(k in t for k in cfg.exclusao if k not in curtos)
        return (not outros) and any(k in t for k in curtos) and not rx.search(t)

    n = int(exc.apply(so_substring, axis=1).sum()) if len(exc) else 0
    return {"candidatos": len(cand), "excluidos": len(exc), "excluidos_so_por_trecho": n,
            "fracao": (n / len(cand)) if len(cand) else 0.0}


# Limitações conhecidas de cada exportação (documentadas; não são corrigidas pelo código).
LIMITACOES = {
    "lens": ["Contagem de citações (Citing Works Count) é da Lens, não comparável à Scopus/WoS.",
             "Referências citadas não vêm no CSV padrão: co-citação/acoplamento indisponíveis."],
    "scopus": ["O CSV não tem coluna 'Keywords' (há 'Author Keywords' e 'Index Keywords'): "
               "no modo original as palavras-chave ficam vazias.",
               "O limite de exportação da interface (2.000/20.000 registros) pode truncar buscas grandes."],
    "ieee": ["O título está em 'Document Title' e as palavras-chave em 'Author Keywords'/'IEEE Terms': "
             "no modo original título vira 'Unknown' e todos os títulos ausentes colapsam na deduplicação.",
             "Citações em 'Article Citation Count' (não lida no modo original)."],
    "scielo": ["Não há contagem de citações (C* = 0 para todos).",
               "Colunas em português ('Título', 'Resumo', 'Ano') não são lidas no modo original."],
    "wos": ["Times Cited (TC) refere-se à Core Collection; 'Z9' inclui todas as bases."],
    "openalex": ["O resumo vem como índice invertido na API; exportações CSV podem não trazê-lo.",
                 "DOI vem com prefixo https://doi.org/ (só é comparável com normalizar_doi=True)."],
    "ris": ["RIS não traz contagem de citações na maioria das bases (C* = 0)."],
    "bibtex": ["Campos variam por base; citações só quando a base inclui 'note'/'cited-by'."],
    "generico": ["Base não identificada: confira o mapeamento de campos antes de interpretar."],
}


def relatorio_campos(bases: dict, cfg) -> pd.DataFrame:
    """Por arquivo e campo da triagem: coluna usada, % de valores ausentes e limitações."""
    linhas = []
    for rotulo, (df, tipo) in bases.items():
        usados = campos_usados(df, tipo, cfg) if len(df) else {c: None for c in ALIASES}
        for campo, cols in usados.items():
            if cols and len(df):
                v = df[cols].astype(str).replace({"nan": "", "None": "", "<NA>": ""}).apply(
                    lambda s: s.str.strip()).agg("".join, axis=1)
                ausente = float((v == "").mean() * 100)
            else:
                ausente = 100.0
            linhas.append({"base": rotulo, "tipo": tipo, "registros": len(df), "campo": campo,
                           "coluna_usada": "; ".join(map(str, cols)) if cols else "—",
                           "pct_ausente": round(ausente, 1)})
    return pd.DataFrame(linhas)


def limitacoes(bases: dict) -> dict:
    return {rotulo: LIMITACOES.get(tipo, []) for rotulo, (_, tipo) in bases.items()}
