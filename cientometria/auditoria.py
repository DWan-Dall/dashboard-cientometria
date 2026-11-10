"""Auditoria científica: confronto com os números HISTÓRICOS do artigo e com o corpus publicado.

Os números abaixo são REFERÊNCIAS HISTÓRICAS A VERIFICAR, não metas. Nenhuma função deste
pacote ajusta parâmetros para atingi-los. Uma divergência é um achado a investigar e
documentar (docs/AUDITORIA.md), nunca um motivo para alterar o método.
"""
from __future__ import annotations
from pathlib import Path

import numpy as np
import pandas as pd

from .config import Config
from .nucleo import classificar

# Origem: notebooks/replicacao_cientometria.ipynb, seção 2 (relatorio_cientometria.md, jan/2026).
REFERENCIAS_HISTORICAS = {
    "registros": 16845,
    "unicos": 11547,
    "removidos_total": 5298,
    "corpus": 2068,
    "Núcleo A": 13, "Núcleo B": 494, "Periférico": 1508, "Descarte": 53,
}
# Valores declarados no relatório que NÃO correspondem à execução (registrados no notebook).
DECLARADOS_INCONSISTENTES = {"removidos por DOI (declarado)": 4233, "removidos por título (declarado)": 1065}
# Contagens por base declaradas no texto final (escritas à mão no código original).
DECLARADO_POR_BASE = {"Lens (EN+PT)": 11108, "Scopus (3 variações)": 5120, "IEEE Xplore": 612, "SciELO (EN+PT)": 5}


def comparar_com_referencia(res, referencia: dict | None = None) -> pd.DataFrame:
    """Tabela item | referência histórica | obtido | confere. Não interpreta, só compara."""
    ref = referencia or REFERENCIAS_HISTORICAS
    obtido = dict(res.contagens) | res.estratos()
    linhas = [{"item": k, "referencia_historica": v, "obtido": obtido.get(k),
               "confere": obtido.get(k) == v, "diferenca": (obtido.get(k) - v) if obtido.get(k) is not None else None}
              for k, v in ref.items()]
    return pd.DataFrame(linhas)


def verificar_corpus_publicado(caminho, cfg: Config | None = None) -> dict:
    """Verificação interna do corpus publicado (DB_Cientometria_COMPLETA.csv / .xlsx).

    Não exige as exportações originais. Confere, nas 2.068 linhas:
    (1) C* e R* recalculados (min–max) == publicados;
    (2) escore 0–100 recalculado dos componentes publicados == publicado;
    (3) estrato coerente com o escore e os cortes;
    (4) valores fora do domínio (ex.: A* > 1 por corrupção de separador decimal);
    (5) DOIs duplicados que diferem só na caixa e títulos quase idênticos;
    (6) T*/A* recalculáveis sem palavras-chave (a coluna não está no arquivo publicado)."""
    from .nucleo import aderencia_tematica, aderencia_dados
    from .consolidacao import chave_titulo_estrita
    cfg = cfg or Config.original()
    p = Path(caminho)
    d = pd.read_excel(p) if p.suffix.lower() in (".xlsx", ".xls") else pd.read_csv(p)
    out = {"arquivo": p.name, "linhas": len(d), "estratos": d["fascia"].value_counts().to_dict()}
    w = np.asarray(cfg.pesos, float)

    cmin, cmax = d["citations"].min(), d["citations"].max()
    c = (d["citations"] - cmin) / (cmax - cmin)
    y = d["year"]
    ymin, ymax = y.min(), y.max()
    r = y.apply(lambda v: (v - ymin) / (ymax - ymin) if pd.notna(v) else 0)
    out["C_norm_confere"] = int(np.isclose(c, d["C_norm"], atol=1e-9).sum())
    out["R_norm_confere"] = int(np.isclose(r, d["R_norm"], atol=1e-9).sum())

    fora = {k: int((d[k] > 1).sum()) for k in ("C_norm", "R_norm", "T_score", "A_score")}
    out["valores_fora_do_dominio"] = fora
    a_corr = d["A_score"].where(d["A_score"] <= 1, d["A_score"] / 1000)
    out["A_score_valores_anomalos"] = sorted(map(float, d.loc[d["A_score"] > 1, "A_score"].unique()))

    def s100(a):
        s = w[0] * d["C_norm"] + w[1] * d["R_norm"] + w[2] * d["T_score"] + w[3] * a
        return ((s - s.min()) / (s.max() - s.min()) * 100).round(2)
    out["escore_confere_com_A_publicado"] = int((s100(d["A_score"]) - d["score_final_100"]).abs().le(0.011).sum())
    out["escore_confere_com_A_corrigido"] = int((s100(a_corr) - d["score_final_100"]).abs().le(0.011).sum())
    out["estrato_confere"] = int((classificar(d["score_final_100"], cfg) == d["fascia"]).sum())

    low = d["doi"].astype(str).str.strip().str.lower()
    out["doi_duplicado_so_na_caixa"] = int(low.duplicated().sum() - d["doi"].duplicated().sum())
    out["linhas_envolvidas_doi_caixa"] = int(low.duplicated(keep=False).sum())
    tn = d["title"].map(chave_titulo_estrita)
    out["titulos_duplicados_apos_pontuacao"] = int(tn.duplicated().sum())

    kw = pd.Series([""] * len(d))
    ab = d["abstract"].fillna("")
    t_rec = [aderencia_tematica(t, a, k, cfg) for t, a, k in zip(d["title"], ab, kw)]
    a_rec = [aderencia_dados(t, a, k, cfg) for t, a, k in zip(d["title"], ab, kw)]
    out["T_sem_palavras_chave"] = {"iguais": int(np.isclose(t_rec, d["T_score"]).sum()),
                                   "publicado_maior": int((d["T_score"].values > np.array(t_rec) + 1e-9).sum()),
                                   "publicado_menor": int((d["T_score"].values < np.array(t_rec) - 1e-9).sum())}
    out["A_sem_palavras_chave"] = {"iguais": int(np.isclose(a_rec, a_corr).sum()),
                                   "publicado_maior": int((a_corr.values > np.array(a_rec) + 1e-9).sum()),
                                   "publicado_menor": int((a_corr.values < np.array(a_rec) - 1e-9).sum())}
    if "source_database" in d:
        bases = d["source_database"].fillna("").str.split(";").explode().str.strip()
        out["registros_por_base_no_corpus"] = bases[bases != ""].value_counts().to_dict()
    if "source_db" in d:
        out["source_db_vazia"] = bool(d["source_db"].isna().all())
    return out
