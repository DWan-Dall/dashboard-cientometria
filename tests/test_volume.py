"""Volume elevado: ~60 mil registros (3,5x o volume do artigo) em tempo razoável."""
import time

import numpy as np
import pandas as pd

from cientometria import Config, executar
from cientometria.consolidacao import correspondencias_duvidosas


def test_volume_elevado():
    rng = np.random.default_rng(1)
    n = 60_000
    temas = np.array(["flood forecasting", "flood risk", "drought", "flooding", "soil erosion"])
    met = np.array(["lstm", "random forest", "regression", "deep learning", "survey"])
    dados = np.array(["rainfall", "satellite", "economy", "river", "interviews"])
    t, m, d = rng.choice(temas, n), rng.choice(met, n), rng.choice(dados, n)
    ids = rng.integers(0, 45_000, n)                     # ~25% de duplicatas
    df = pd.DataFrame({"Title": [f"{a} with {b} study {i}" for a, b, i in zip(t, m, ids)],
                       "Publication Year": rng.integers(1995, 2026, n),
                       "Abstract": [f"{a} {b} {c} urban basin prediction" for a, b, c in zip(t, m, d)],
                       "Keywords": "", "Citing Works Count": rng.pareto(1.2, n).astype(int),
                       "DOI": np.where(rng.random(n) < .9, [f"10.1/{i}" for i in ids], ""),
                       "Source Title": "J"})
    bases = {"Lens (EN)": (df.iloc[: n // 2].reset_index(drop=True), "lens"),
             "Lens (PT)": (df.iloc[n // 2:].reset_index(drop=True), "lens")}
    t0 = time.time()
    for cfg in (Config.original(), Config.corrigida()):
        r = executar(bases, cfg)
        assert r.contagens["registros"] == n
        assert r.contagens["unicos"] <= 45_000 + r.contagens["sem_doi"]
        assert len(r.corpus) > 1000 and sum(r.estratos().values()) == len(r.corpus)
    assert time.time() - t0 < 180
    t1 = time.time()
    correspondencias_duvidosas(r.consolidado.head(20_000), max_pares=2000)
    assert time.time() - t1 < 120
