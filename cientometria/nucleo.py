"""Casamento de termos, filtros temáticos e escore (C*, R*, T*, A*). Funções puras."""
from __future__ import annotations
import re
import pandas as pd


def contem_algum(texto, termos) -> int:
    """1 se algum termo ocorre como TRECHO do texto (sem caixa); 0 caso contrário.
    Igual a check_keyword_presence(..., 'any') do original."""
    if pd.isna(texto) or texto == "":
        return 0
    t = str(texto).lower()
    return 1 if any(k.lower() in t for k in termos) else 0


def _regex_palavra(termo: str):
    return re.compile(r"\b" + re.escape(termo) + r"s?\b", re.I)


def excluido(titulo, resumo, cfg) -> bool:
    """Termos de exclusão em título+resumo. Os listados em
    cfg.exclusao_palavra_inteira exigem palavra inteira (com plural simples)."""
    t = (str(titulo) + " " + str(resumo)).lower()
    inteira = set(cfg.exclusao_palavra_inteira)
    for k in cfg.exclusao:
        if k in inteira:
            if _regex_palavra(k).search(t):
                return True
        elif k.lower() in t:
            return True
    return False


def aplicar_filtros(df: pd.DataFrame, cfg) -> pd.DataFrame:
    """Acrescenta flag_* e devolve o DataFrame (mesmas colunas do original)."""
    d = df.copy()
    n = cfg.nucleo
    tak = d["title"].astype(str) + " " + d["abstract"].astype(str) + " " + d["keywords"].astype(str)
    ak = d["abstract"].astype(str) + " " + d["keywords"].astype(str)
    d["flood_pred_score"] = tak.map(lambda x: contem_algum(x, n["flood_prediction"]))
    d["ai_ml_score"] = tak.map(lambda x: contem_algum(x, n["ai_ml_methods"]))
    d["hydro_score"] = ak.map(lambda x: contem_algum(x, n["hydrological_data"]))
    d["geospatial_score"] = ak.map(lambda x: contem_algum(x, n["geospatial_data"]))
    d["is_excluded"] = [excluido(t, a, cfg) for t, a in zip(d["title"], d["abstract"])]
    return d


def candidatos(d: pd.DataFrame) -> pd.DataFrame:
    """Passa FP & IA & (hidro|geo), ignorando a exclusão (para diagnóstico)."""
    return d[(d.flood_pred_score == 1) & (d.ai_ml_score == 1) &
             ((d.hydro_score == 1) | (d.geospatial_score == 1))]


def nucleo_expandido(d: pd.DataFrame) -> pd.DataFrame:
    return candidatos(d)[lambda x: ~x["is_excluded"]].copy()


def nucleo_obrigatorio(d: pd.DataFrame) -> pd.DataFrame:
    return d[(d.flood_pred_score == 1) & (d.ai_ml_score == 1) & (~d.is_excluded)].copy()


def aderencia_tematica(titulo, resumo, palavras, cfg) -> float:
    """T*: 1,0 se FP e IA no título; 0,7 se FP e IA em título+resumo+palavras-chave; senão 0,4."""
    n = cfg.nucleo
    conteudo = f"{titulo} {resumo} {palavras}"
    if contem_algum(str(titulo), n["flood_prediction"]) and contem_algum(str(titulo), n["ai_ml_methods"]):
        return 1.0
    if contem_algum(conteudo, n["flood_prediction"]) and contem_algum(conteudo, n["ai_ml_methods"]):
        return 0.7
    return 0.4


def aderencia_dados(titulo, resumo, palavras, cfg) -> float:
    """A* = (I + M + O + C) / 4. I∈{0,1}; M,O,C∈{0,5;1}."""
    n = cfg.nucleo
    entrada = n["hydrological_data"] + n["geospatial_data"]
    ak = f"{resumo} {palavras}"
    I = 1.0 if contem_algum(ak, entrada) else 0.0
    M = 1.0 if contem_algum(f"{resumo} {titulo}", cfg.ml_especifico) else 0.5
    O = 1.0 if contem_algum(f"{titulo} {resumo}", cfg.saida) else 0.5
    C = 1.0 if contem_algum(ak, cfg.contexto) else 0.5
    return (I + M + O + C) / 4


def calcular_escore(corpus: pd.DataFrame, cfg) -> pd.DataFrame:
    """Acrescenta C_norm, R_norm, T_score, A_score, score_final, score_final_100 e fascia."""
    d = corpus.copy()
    w1, w2, w3, w4 = cfg.pesos
    cmin, cmax = d["citations"].min(), d["citations"].max()
    d["C_norm"] = ((d["citations"] - cmin) / (cmax - cmin)) if cmax > cmin else 0.0
    d["C_norm"] = d["C_norm"].fillna(0)
    ymin = d["year"][d["year"].notna()].min()
    ymax = d["year"].max()
    d["R_norm"] = d["year"].apply(
        lambda y: (y - ymin) / (ymax - ymin) if pd.notna(y) and y >= ymin and ymax > ymin else 0)
    d["T_score"] = [aderencia_tematica(t, a, k, cfg) for t, a, k in zip(d.title, d.abstract, d.keywords)]
    d["A_score"] = [aderencia_dados(t, a, k, cfg) for t, a, k in zip(d.title, d.abstract, d.keywords)]
    d["score_final"] = w1 * d.C_norm + w2 * d.R_norm + w3 * d.T_score + w4 * d.A_score
    lo, hi = d["score_final"].min(), d["score_final"].max()
    d["score_final_100"] = (((d["score_final"] - lo) / (hi - lo)) * 100 if hi > lo else 0.0)
    d["score_final_100"] = d["score_final_100"].round(2)
    d["fascia"] = classificar(d["score_final_100"], cfg)
    return d


def classificar(s100: pd.Series, cfg) -> pd.Series:
    a, b, p = cfg.cortes
    f = pd.Series("Descarte", index=s100.index)
    f[s100 >= p] = "Periférico"
    f[s100 >= b] = "Núcleo B"
    f[s100 >= a] = "Núcleo A"
    return f
