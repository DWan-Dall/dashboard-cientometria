#!/usr/bin/env python3
"""Ponte entre o dashboard (PHP) e o pacote `cientometria`.

Uso: pipeline.py <payload.json>      (mesmo contrato do script anterior)
O payload pode trazer params.modo = "original" | "variante_exclusao" | "corrigida".
O script anterior foi preservado em scripts/pipeline_legado.py.
"""
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
sys.path.insert(0, str(Path(__file__).resolve().parent))

import pandas as pd
from cientometria import Config, executar
from cientometria import robustez, diagnostico
from pipeline_legado import load_file  # leitura de .csv/.tsv/.txt/.xlsx/.bib

TIPOS = ("lens", "scopus", "ieee", "scielo")


def tipo_pelo_nome(nome: str) -> str:
    n = nome.lower()
    return next((t for t in TIPOS if t in n), "lens")


def montar_config(params: dict) -> Config:
    modo = params.get("modo", "original")
    cfg = {"original": Config.original, "variante_exclusao": Config.variante_exclusao,
           "corrigida": Config.corrigida}.get(modo, Config.original)()
    w = params.get("weights") or {}
    if w:
        cfg = cfg.com(pesos=(float(w.get("c", .35)), float(w.get("r", .20)), float(w.get("t", .30)), float(w.get("a", .15))))
    th = params.get("thresholds") or {}
    if th:
        cfg = cfg.com(cortes=(float(th.get("nucleo_a", 70)), float(th.get("nucleo_b", 50)), float(th.get("periferico", 30))))
    t = params.get("terms") or {}
    nucleo = {k: list(v) for k, v in cfg.nucleo.items()}
    mapa = {"method": "ai_ml_methods", "input_a": "hydrological_data", "input_b": "geospatial_data"}
    for k, destino in mapa.items():
        if isinstance(t.get(k), list) and t[k]:
            nucleo[destino] = [str(x).lower() for x in t[k] if str(x).strip()]
    fp = [str(x).lower() for k in ("topic1", "topic2") for x in (t.get(k) or []) if str(x).strip()]
    if fp:
        nucleo["flood_prediction"] = fp
    cfg = cfg.com(nucleo=nucleo)
    if isinstance(t.get("exclude"), list) and t["exclude"]:
        cfg = cfg.com(exclusao=tuple(str(x).lower() for x in t["exclude"] if str(x).strip()))
    # arquivos enviados no dashboard têm colunas variadas: aceitar aliases de coluna
    return cfg.com(mapeamento_tolerante=True)


def main():
    if len(sys.argv) < 2:
        raise SystemExit("Uso: pipeline.py <payload.json>")
    payload = json.loads(Path(sys.argv[1]).read_text(encoding="utf-8"))
    files = [Path(p) for p in payload.get("files", [])]
    params = payload.get("params", {}) or {}
    if not files:
        raise SystemExit("Nenhum arquivo recebido")
    cfg = montar_config(params)
    bases = {f.name: (load_file(f), tipo_pelo_nome(f.name)) for f in files}
    res = executar(bases, cfg)
    c, corpus = res.contagens, res.corpus

    removidos = {"doi_removed": [], "title_removed": [],
                 "counts": {"doi_removed": c["duplicatas_doi"] + (0 if cfg.manter_sem_doi else c["sem_doi"]),
                            "title_removed": c["removidos_titulo"]}}
    nucleos = {k: 0 for k in ["Núcleo A", "Núcleo B", "Periférico", "Descarte"]}
    nucleos.update(res.estratos() if len(corpus) else {})
    sumario = {
        "raw_records": c["registros"], "after_doi": c["apos_doi"], "after_title": c["unicos"],
        "thematic_selected": int(len(corpus)), "core_counts": nucleos,
        "t_star_distribution": {"1.0": 0, "0.7": 0, "0.4": 0},
        "a_star_bins": {">=0.9": 0, "0.7-0.9": 0, "0.5-0.7": 0},
        "score_stats": {"mean": 0, "median": 0, "std": 0},
        "sem_doi": c["sem_doi"], "candidatos_antes_da_exclusao": c["candidatos_antes_da_exclusao"],
        "excluidos_entre_candidatos": c["excluidos_entre_candidatos"],
    }
    top = []
    extras = {}
    if len(corpus):
        sumario["t_star_distribution"] = {k: int((corpus.T_score == float(k)).sum()) for k in ("1.0", "0.7", "0.4")}
        sumario["a_star_bins"] = {">=0.9": int((corpus.A_score >= .9).sum()),
                                  "0.7-0.9": int(((corpus.A_score >= .7) & (corpus.A_score < .9)).sum()),
                                  "0.5-0.7": int(((corpus.A_score >= .5) & (corpus.A_score < .7)).sum())}
        sumario["score_stats"] = {"mean": float(corpus.score_final_100.mean()),
                                  "median": float(corpus.score_final_100.median()),
                                  "std": float(corpus.score_final_100.std(ddof=0))}
        for _, r in corpus.sort_values("score_final_100", ascending=False).iterrows():
            top.append({"title": str(r["title"]), "year": int(r["year"]) if pd.notna(r["year"]) else 0,
                        "citations": float(r["citations"]), "doi": r["doi"], "nucleo": r["fascia"],
                        "score100": float(r["score_final_100"]), "c_norm": float(r["C_norm"]),
                        "r_norm": float(r["R_norm"]), "t_score": float(r["T_score"]), "a_score": float(r["A_score"])})
        if len(res.corpus[res.corpus.fascia == "Núcleo A"]):
            extras["sensibilidade_pesos"] = robustez.sensibilidade_pesos(res, n=int(params.get("n_sensibilidade", 2000)))
    extras["exclusao_por_trecho"] = diagnostico.exclusao_por_trecho(res)
    extras["perdas_no_fluxo"] = diagnostico.perdas_no_fluxo(res)

    pesos = dict(zip("crta", cfg.pesos))
    print(json.dumps({
        "summary": sumario, "top_articles": top, "dedup_removed": removidos,
        "plot_urls": {"generated_with": "python"}, "modo": cfg.modo, "config": cfg.descricao(),
        "used_params": {"weights": pesos, "year_min": 1992, "year_max": 2026,
                        "thresholds": dict(zip(("nucleo_a", "nucleo_b", "periferico"), cfg.cortes)),
                        "terms": {"topic1": cfg.nucleo["flood_prediction"], "topic2": [], "method": cfg.nucleo["ai_ml_methods"],
                                  "exclude": list(cfg.exclusao), "input_a": cfg.nucleo["hydrological_data"],
                                  "input_b": cfg.nucleo["geospatial_data"]}},
        "extras": extras}, ensure_ascii=False, default=float))


if __name__ == "__main__":
    main()
