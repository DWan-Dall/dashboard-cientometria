"""Manifesto de reprodução: tudo o que é preciso para recuperar e comparar uma execução."""
from __future__ import annotations
import hashlib
import importlib.metadata as md
import json
import platform
import uuid
from datetime import datetime, timezone

import pandas as pd

from .versao import APP_VERSAO, METODO_HISTORICO
from .consolidacao import criterios

DEPENDENCIAS = ("pandas", "numpy", "openpyxl", "rapidfuzz", "networkx", "matplotlib")
COLUNAS_CORPUS = ["title", "year", "citations", "doi", "source_db", "C_norm", "R_norm", "T_score",
                  "A_score", "score_final", "score_final_100", "fascia"]


def versoes_dependencias() -> dict:
    v = {"python": platform.python_version()}
    for p in DEPENDENCIAS:
        try:
            v[p] = md.version(p)
        except md.PackageNotFoundError:
            v[p] = None
    return v


def hash_tabela(df: pd.DataFrame, colunas=COLUNAS_CORPUS) -> str:
    """SHA-256 de uma representação canônica (colunas fixas, floats com 10 casas)."""
    cols = [c for c in colunas if c in df]
    d = df[cols].copy()
    for c in d.select_dtypes("number").columns:
        d[c] = d[c].astype(float).round(10)
    csv = d.to_csv(index=False, lineterminator="\n", float_format="%.10f")
    return hashlib.sha256(csv.encode("utf-8")).hexdigest()


def _sha(obj) -> str:
    return hashlib.sha256(json.dumps(obj, sort_keys=True, ensure_ascii=False, default=str).encode()).hexdigest()


def gerar(res, fontes, rotulo: str = "", observacoes: str = "") -> dict:
    cfg = res.cfg
    fontes_d = [f.como_dict() if hasattr(f, "como_dict") else dict(f) for f in fontes]
    for f in fontes_d:
        f.pop("caminho", None)
        f["colunas"] = f.get("colunas", [])[:200]
    parametros = cfg.completa()
    entradas = [{"arquivo": f["arquivo"], "sha256": f["sha256"], "tipo": f["tipo"]} for f in fontes_d]
    corpus = res.corpus
    finais = {}
    if len(corpus):
        ordenado = corpus.sort_values("score_final_100", ascending=False)
        for k in ["Núcleo A", "Núcleo B"]:
            sub = ordenado[ordenado["fascia"] == k]
            finais[k] = [{"doi": str(r.doi), "titulo": str(r.title)[:200], "escore": float(r.score_final_100)}
                         for r in sub.itertuples()] if k == "Núcleo A" else len(sub)
    return {
        "id": uuid.uuid4().hex[:12],
        "rotulo": rotulo,
        "data_hora_utc": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "versao_aplicacao": APP_VERSAO,
        "modo": cfg.modo,
        "versao_metodo": cfg.metodo_versao,
        "historico_metodo": METODO_HISTORICO,
        "configuracao_personalizada": cfg.personalizada(),
        "alteracoes_em_relacao_a_receita": cfg.alteracoes_em_relacao_a_receita(),
        "fontes": fontes_d,
        "ordem_processamento": [f["rotulo"] for f in fontes_d],
        "parametros": parametros,
        "pesos": list(cfg.pesos),
        "cortes": {"nucleo_a": cfg.cortes[0], "nucleo_b": cfg.cortes[1], "periferico": cfg.cortes[2]},
        "regras_exclusao": {"termos": list(cfg.exclusao),
                            "palavra_inteira": list(cfg.exclusao_palavra_inteira),
                            "demais": "trecho de texto (substring), sem distinção de caixa"},
        "criterios_consolidacao": criterios(cfg),
        "contagens": res.contagens,
        "estratos": res.estratos(),
        "resultados_finais": finais,
        "hash_corpus": hash_tabela(corpus) if len(corpus) else None,
        "impressao_digital_entrada": _sha({"entradas": entradas, "parametros": parametros}),
        "dependencias": versoes_dependencias(),
        "plataforma": platform.platform(),
        "observacoes": observacoes,
    }


def comparar(a: dict, b: dict) -> dict:
    """Diferenças entre dois manifestos (entradas, parâmetros, contagens, estratos, Núcleo A)."""
    def dif(x, y):
        chaves = sorted(set(x) | set(y))
        return {k: {"a": x.get(k), "b": y.get(k)} for k in chaves if x.get(k) != y.get(k)}

    ha = {f["arquivo"]: f["sha256"] for f in a["fontes"]}
    hb = {f["arquivo"]: f["sha256"] for f in b["fontes"]}
    na = {r["doi"] or r["titulo"] for r in a.get("resultados_finais", {}).get("Núcleo A", [])}
    nb = {r["doi"] or r["titulo"] for r in b.get("resultados_finais", {}).get("Núcleo A", [])}
    return {
        "a": a["id"], "b": b["id"],
        "mesma_entrada_e_parametros": a["impressao_digital_entrada"] == b["impressao_digital_entrada"],
        "mesmo_corpus": a["hash_corpus"] == b["hash_corpus"],
        "modo": {"a": a["modo"], "b": b["modo"]},
        "versao_metodo": {"a": a["versao_metodo"], "b": b["versao_metodo"]},
        "arquivos": dif(ha, hb),
        "parametros": dif(a["parametros"], b["parametros"]),
        "contagens": dif(a["contagens"], b["contagens"]),
        "estratos": dif(a["estratos"], b["estratos"]),
        "nucleo_a": {"so_em_a": sorted(na - nb), "so_em_b": sorted(nb - na), "em_ambos": len(na & nb)},
        "dependencias": dif(a["dependencias"], b["dependencias"]),
    }
