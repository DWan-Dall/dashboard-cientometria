"""Conversão de parâmetros vindos da interface (JSON) para `Config`.

Fonte única dessa conversão: o dashboard (PHP) e a API usam esta função. Qualquer
parâmetro diferente da receita do modo torna a configuração "personalizada", o que fica
registrado no manifesto (`Config.alteracoes_em_relacao_a_receita`).

Decisão de auditoria (nov/2026): o adaptador anterior forçava `mapeamento_tolerante=True`
em TODOS os modos, de modo que o "original" do dashboard não era o original. Agora a
leitura tolerante só é usada se o modo a prevê (corrigida) ou se for pedida
explicitamente em `params["mapeamento_tolerante"]` (e aí a execução é personalizada).
"""
from __future__ import annotations
from .config import Config

_MAPA_TERMOS = {"method": "ai_ml_methods", "input_a": "hydrological_data", "input_b": "geospatial_data"}


def _lista(v):
    return [str(x).strip().lower() for x in v if str(x).strip()] if isinstance(v, list) else []


def config_de_parametros(params: dict | None) -> Config:
    params = params or {}
    cfg = Config.do_modo(params.get("modo", "original"))
    w = params.get("weights") or {}
    if w:
        novos = (float(w.get("c", cfg.pesos[0])), float(w.get("r", cfg.pesos[1])),
                 float(w.get("t", cfg.pesos[2])), float(w.get("a", cfg.pesos[3])))
        if abs(sum(novos) - 1.0) > 1e-6:
            raise ValueError(f"Os pesos devem somar 1 (soma = {sum(novos):.4f}).")
        cfg = cfg.com(pesos=novos)
    th = params.get("thresholds") or {}
    if th:
        cortes = (float(th.get("nucleo_a", cfg.cortes[0])), float(th.get("nucleo_b", cfg.cortes[1])),
                  float(th.get("periferico", cfg.cortes[2])))
        if not (cortes[0] >= cortes[1] >= cortes[2]):
            raise ValueError("Cortes devem obedecer Núcleo A ≥ Núcleo B ≥ Periférico.")
        cfg = cfg.com(cortes=cortes)
    t = params.get("terms") or {}
    nucleo = {k: list(v) for k, v in cfg.nucleo.items()}
    for k, destino in _MAPA_TERMOS.items():
        if _lista(t.get(k)):
            nucleo[destino] = _lista(t[k])
    fp = _lista(t.get("topic1")) + _lista(t.get("topic2"))
    if fp:
        nucleo["flood_prediction"] = fp
    if nucleo != cfg.nucleo:
        cfg = cfg.com(nucleo=nucleo)
    if _lista(t.get("exclude")):
        cfg = cfg.com(exclusao=tuple(_lista(t["exclude"])))
    for chave in ("mapeamento_tolerante", "manter_sem_doi", "normalizar_doi"):
        if chave in params and params[chave] is not None:
            cfg = cfg.com(**{chave: bool(params[chave])})
    return cfg


def parametros_usados(cfg: Config) -> dict:
    """Formato `used_params` esperado pelo dashboard."""
    return {"weights": dict(zip("crta", cfg.pesos)),
            "thresholds": dict(zip(("nucleo_a", "nucleo_b", "periferico"), cfg.cortes)),
            "terms": {"topic1": cfg.nucleo["flood_prediction"], "topic2": [],
                      "method": cfg.nucleo["ai_ml_methods"], "exclude": list(cfg.exclusao),
                      "input_a": cfg.nucleo["hydrological_data"], "input_b": cfg.nucleo["geospatial_data"]},
            "modo": cfg.modo, "metodo_versao": cfg.metodo_versao,
            "mapeamento_tolerante": cfg.mapeamento_tolerante, "manter_sem_doi": cfg.manter_sem_doi,
            "normalizar_doi": cfg.normalizar_doi}
