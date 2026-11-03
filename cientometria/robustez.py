"""Testes de robustez: NÃO ajustam o método; medem o quanto o resultado depende de decisões."""
from __future__ import annotations
import numpy as np
import pandas as pd
from .config import Config
from .pipeline import executar, Resultado


def _escore_bruto(corpus, w):
    return corpus[["C_norm", "R_norm", "T_score", "A_score"]].values.astype(float) @ np.asarray(w, float)


def sensibilidade_pesos(res: Resultado, n: int = 10000, seed: int = 42, referencia: str = "Núcleo A") -> dict:
    """Quantos dos artigos de referência (Núcleo A original) permanecem
    (i) entre os |A| primeiros do ranking e (ii) acima do corte fixo (renormalizando min–max)
    quando os pesos variam. Usa escore não arredondado."""
    c = res.corpus.reset_index(drop=True)
    pos = set(np.where(c["fascia"].values == referencia)[0])
    k = len(pos)
    base = np.asarray(res.cfg.pesos, float)
    corte = res.cfg.cortes[0]

    def medir(w):
        s = _escore_bruto(c, w)
        s100 = (s - s.min()) / (s.max() - s.min()) * 100
        top = set(np.argsort(-s)[:k])
        acima = set(np.where(s100 >= corte)[0])
        return len(top & pos), len(acima & pos), len(acima)

    rng = np.random.default_rng(seed)

    def resumo(gen):
        r = np.array([medir(gen()) for _ in range(n)])
        return {"ranking_media": float(r[:, 0].mean()), "ranking_min": int(r[:, 0].min()),
                "ranking_todos": float(np.mean(r[:, 0] == k)), "ranking_ge_k_menos_2": float(np.mean(r[:, 0] >= k - 2)),
                "corte_media": float(r[:, 1].mean()), "corte_todos": float(np.mean(r[:, 1] == k)),
                "tamanho_nucleo_min": int(r[:, 2].min()), "tamanho_nucleo_max": int(r[:, 2].max())}

    saida = {"k_referencia": k, "n": n, "seed": seed}
    saida["uniforme_15"] = resumo(lambda: base * (1 + rng.uniform(-.15, .15, 4)))
    saida["dirichlet_5"] = resumo(lambda: rng.dirichlet([5] * 4))
    saida["pesos_iguais"] = dict(zip(["ranking", "corte", "tamanho_nucleo"], medir(np.array([.25] * 4))))
    saida["um_por_vez_15"] = [medir(np.where(np.arange(4) == i, base * (1 + sg * .15), base))
                              for i in range(4) for sg in (-1, 1)]
    return saida


def tabela_referencia(res_original: Resultado, res_alt: Resultado) -> pd.DataFrame:
    """Posição dos artigos do Núcleo A original num corpus alternativo (variante/corrigida)."""
    ref = res_original.corpus[res_original.corpus["fascia"] == "Núcleo A"]
    alt = res_alt.corpus.copy()
    alt["_s"] = _escore_bruto(alt, res_alt.cfg.pesos)
    lo, hi = alt["_s"].min(), alt["_s"].max()
    alt["_s100"] = (alt["_s"] - lo) / (hi - lo) * 100
    linhas = []
    for _, r in ref.iterrows():
        m = alt[alt["doi"].str.lower() == str(r["doi"]).lower()] if r["doi"] else alt[alt["title"] == r["title"]]
        linhas.append({
            "doi": r["doi"], "titulo": str(r["title"])[:70],
            "escore_original": float(r["score_final_100"]),
            "escore_alt": round(float(m["_s100"].iloc[0]), 1) if len(m) else None,
            "posicao_alt": int((alt["_s100"] > m["_s100"].iloc[0]).sum()) + 1 if len(m) else None})
    return pd.DataFrame(linhas).sort_values("posicao_alt", na_position="last").reset_index(drop=True)


def comparar_configuracoes(bases: dict, configs: dict | None = None) -> dict:
    """Roda várias configurações sobre as mesmas bases. Devolve {nome: Resultado}."""
    configs = configs or {"original": Config.original(), "variante_exclusao": Config.variante_exclusao(),
                          "corrigida": Config.corrigida()}
    return {nome: executar(bases, c) for nome, c in configs.items()}


def resumo_comparacao(resultados: dict) -> pd.DataFrame:
    linhas = []
    for nome, r in resultados.items():
        e = r.estratos()
        linhas.append({"configuracao": nome, "unicos": r.contagens["unicos"], "corpus": len(r.corpus),
                       "max_citacoes": int(r.corpus["citations"].max()) if len(r.corpus) else 0, **e})
    return pd.DataFrame(linhas)
