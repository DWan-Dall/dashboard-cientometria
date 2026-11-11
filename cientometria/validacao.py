"""Validação externa de cobertura: as referências de uma revisão independente foram
recuperadas, sobreviveram à deduplicação, passaram no filtro, foram excluídas, entraram no corpus?"""
from __future__ import annotations
import re
import pandas as pd
from .pipeline import Resultado


def _nt(t) -> str:
    return re.sub(r"\s+", " ", re.sub(r"[^a-z0-9 ]", " ", str(t).lower())).strip()


def _melhor(alvo, candidatos):
    try:
        from rapidfuzz import fuzz, process
        r = process.extractOne(alvo, candidatos, scorer=fuzz.ratio)
        return (r[2], r[1]) if r else (None, 0)
    except ImportError:
        import difflib
        melhor, idx = 0, None
        for i, c in enumerate(candidatos):
            s = difflib.SequenceMatcher(None, alvo, c).ratio() * 100
            if s > melhor:
                melhor, idx = s, i
        return idx, melhor


def validar_referencias(refs: dict, res: Resultado, limiar: float = 90.0) -> pd.DataFrame:
    """refs: {id: título}. Casamento por similaridade de título normalizado (>= limiar)."""
    bruto = res.bruto.copy()
    bruto["tn"] = bruto["title"].map(_nt)
    cons = res.consolidado
    cons_tn = cons["title"].map(_nt)
    corp_tn = res.corpus["title"].map(_nt) if len(res.corpus) else pd.Series(dtype=str)
    lista = bruto["tn"].tolist()
    linhas = []
    for k, titulo in refs.items():
        i, s = _melhor(_nt(titulo), lista)
        if i is None or s < limiar:
            linhas.append({"ref": k, "recuperada": "não", "sobreviveu_dedup": "", "filtro": "", "excluida": "",
                           "no_corpus": "", "fascia": ""})
            continue
        tn = lista[i]
        c = cons[cons_tn == tn]
        passou = bool(len(c) and ((c.flood_pred_score == 1) & (c.ai_ml_score == 1) &
                                  ((c.hydro_score == 1) | (c.geospatial_score == 1))).any())
        excl = bool(len(c) and c.is_excluded.any())
        no = len(corp_tn) and (corp_tn == tn).any()
        fx = res.corpus[corp_tn == tn]["fascia"].iloc[0] if no else ""
        linhas.append({"ref": k, "recuperada": "sim", "sobreviveu_dedup": "sim" if len(c) else "não",
                       "filtro": "passa" if passou else "não passa", "excluida": "SIM" if excl else "",
                       "no_corpus": "sim" if no else "não", "fascia": fx})
    return pd.DataFrame(linhas)


def ler_referencias(caminho: str) -> dict:
    """CSV com colunas id,titulo."""
    d = pd.read_csv(caminho)
    return dict(zip(d["id"], d["titulo"]))
