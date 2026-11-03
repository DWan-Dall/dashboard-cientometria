"""Diagnósticos: tornam visíveis as falhas silenciosas (colunas não lidas, descartes, exclusões)."""
from __future__ import annotations
import re
import pandas as pd
from .entrada import MAPEAMENTO_ORIGINAL, _col, ALIASES
from .nucleo import candidatos, excluido, _regex_palavra
from .pipeline import Resultado


def colunas_nao_lidas(bases: dict) -> pd.DataFrame:
    """Para cada exportação, quais campos do mapeamento ORIGINAL não existem no arquivo."""
    linhas = []
    for rotulo, (df, tipo) in bases.items():
        if len(df) == 0:
            continue
        m = MAPEAMENTO_ORIGINAL[tipo]
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
