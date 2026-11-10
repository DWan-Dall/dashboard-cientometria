"""Serialização de um `Resultado` para o contrato JSON do dashboard.

A interface só exibe o que está aqui: nenhum cálculo científico é feito em PHP/JS.
"""
from __future__ import annotations
import pandas as pd
from . import robustez, diagnostico
from .consolidacao import criterios
from .parametros import parametros_usados

ESTRATOS = ["Núcleo A", "Núcleo B", "Periférico", "Descarte"]


def _num(v, padrao=0):
    try:
        return padrao if pd.isna(v) else v
    except (TypeError, ValueError):
        return v


def resumo(res, fontes=None, bases=None, n_sensibilidade: int = 2000, limite_top: int | None = None) -> dict:
    cfg, c, corpus = res.cfg, res.contagens, res.corpus
    nucleos = {k: 0 for k in ESTRATOS} | (res.estratos() if len(corpus) else {})
    sumario = {
        "raw_records": c["registros"], "after_doi": c["apos_doi"], "after_title": c["unicos"],
        "thematic_selected": int(len(corpus)), "core_counts": nucleos,
        "t_star_distribution": {"1.0": 0, "0.7": 0, "0.4": 0},
        "a_star_bins": {">=0.9": 0, "0.7-0.9": 0, "0.5-0.7": 0},
        "score_stats": {"mean": 0, "median": 0, "std": 0},
        "sem_doi": c["sem_doi"], "duplicatas_doi": c["duplicatas_doi"],
        "nucleo_obrigatorio": c["nucleo_obrigatorio"],
        "candidatos_antes_da_exclusao": c["candidatos_antes_da_exclusao"],
        "excluidos_entre_candidatos": c["excluidos_entre_candidatos"],
    }
    top, extras = [], {}
    if len(corpus):
        sumario["t_star_distribution"] = {k: int((corpus.T_score == float(k)).sum()) for k in ("1.0", "0.7", "0.4")}
        sumario["a_star_bins"] = {">=0.9": int((corpus.A_score >= .9).sum()),
                                  "0.7-0.9": int(((corpus.A_score >= .7) & (corpus.A_score < .9)).sum()),
                                  "0.5-0.7": int(((corpus.A_score >= .5) & (corpus.A_score < .7)).sum())}
        sumario["score_stats"] = {"mean": float(corpus.score_final_100.mean()),
                                  "median": float(corpus.score_final_100.median()),
                                  "std": float(corpus.score_final_100.std(ddof=0))}
        ordenado = corpus.sort_values("score_final_100", ascending=False)
        if limite_top:
            ordenado = ordenado.head(limite_top)
        for pos, (_, r) in enumerate(ordenado.iterrows(), start=1):
            top.append({"rank": pos, "title": str(r["title"]), "year": int(r["year"]) if pd.notna(r["year"]) else 0,
                        "citations": float(r["citations"]), "doi": str(r["doi"]), "nucleo": r["fascia"],
                        "score100": float(r["score_final_100"]), "c_norm": float(r["C_norm"]),
                        "r_norm": float(r["R_norm"]), "t_score": float(r["T_score"]), "a_score": float(r["A_score"]),
                        "source_db": str(r.get("source_db", "")), "bases": str(r.get("bases_encontradas", ""))})
        if nucleos["Núcleo A"] and n_sensibilidade:
            extras["sensibilidade_pesos"] = robustez.sensibilidade_pesos(res, n=int(n_sensibilidade))
    extras["exclusao_por_trecho"] = diagnostico.exclusao_por_trecho(res)
    extras["perdas_no_fluxo"] = diagnostico.perdas_no_fluxo(res)
    extras["criterios_consolidacao"] = criterios(cfg)
    if bases is not None:
        extras["campos"] = diagnostico.relatorio_campos(bases, cfg).to_dict(orient="records")
        extras["limitacoes"] = diagnostico.limitacoes(bases)
    removidos = {"doi_removed": [], "title_removed": [],
                 "counts": {"doi_removed": c["removidos_etapa_doi"], "title_removed": c["removidos_titulo"]}}
    return {
        "summary": sumario, "contagens": c, "top_articles": top, "dedup_removed": removidos,
        "plot_urls": {"generated_with": "python"}, "modo": cfg.modo, "config": cfg.descricao(),
        "alteracoes_da_receita": cfg.alteracoes_em_relacao_a_receita(),
        "used_params": parametros_usados(cfg),
        "fontes": [f.como_dict() for f in (fontes or [])],
        "extras": extras,
    }
