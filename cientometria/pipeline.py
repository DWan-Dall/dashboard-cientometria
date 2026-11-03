"""Orquestra as etapas: consolidar → filtrar → escorar → classificar."""
from __future__ import annotations
from dataclasses import dataclass, field
import pandas as pd
from .config import Config
from . import entrada, nucleo


@dataclass
class Resultado:
    cfg: Config
    bruto: pd.DataFrame          # todos os registros normalizados, antes da deduplicação
    consolidado: pd.DataFrame    # após deduplicação, com flags temáticos
    corpus: pd.DataFrame         # núcleo expandido, com escore e fascia
    contagens: dict = field(default_factory=dict)

    def estratos(self) -> dict:
        return {k: int((self.corpus["fascia"] == k).sum())
                for k in ["Núcleo A", "Núcleo B", "Periférico", "Descarte"]}


def consolidar(frames: list, cfg: Config):
    """Deduplica em duas etapas (DOI, depois título). Devolve (df, contagens).

    Modo original: a etapa de DOI mantém apenas linhas COM DOI (descarta as sem DOI).
    Com cfg.manter_sem_doi=True, registros sem DOI são mantidos e passam só pela
    deduplicação por título; títulos 'Unknown'/vazios nunca são colapsados entre si."""
    frames = [f for f in frames if len(f) > 0]
    bruto = pd.concat(frames, ignore_index=True)
    bruto["title_normalized"] = bruto["title"].astype(str).str.lower().str.strip()
    sem_doi = int((bruto["doi"] == "").sum())
    com_doi = bruto[bruto["doi"] != ""]
    dup_doi = int(com_doi.duplicated(subset=["doi"]).sum())
    if cfg.manter_sem_doi:
        a = pd.concat([com_doi.drop_duplicates(subset=["doi"], keep="first"),
                       bruto[bruto["doi"] == ""]]).sort_index()
    else:
        a = com_doi.drop_duplicates(subset=["doi"], keep="first")
    apos_doi = len(a)
    if cfg.manter_sem_doi:
        sem_titulo = a["title_normalized"].isin(["", "unknown"])
        b = pd.concat([a[sem_titulo], a[~sem_titulo].drop_duplicates(subset=["title_normalized"], keep="first")]).sort_index()
    else:
        b = a.drop_duplicates(subset=["title_normalized"], keep="first")
    c = {
        "registros": len(bruto), "sem_doi": sem_doi, "duplicatas_doi": dup_doi,
        "removidos_etapa_doi": len(bruto) - apos_doi, "apos_doi": apos_doi,
        "removidos_titulo": apos_doi - len(b), "unicos": len(b),
        "removidos_total": len(bruto) - len(b),
    }
    return bruto, b.copy(), c


def executar(bases: dict, cfg: Config | None = None) -> Resultado:
    """bases: {rótulo: (DataFrame bruto, tipo)} — ver entrada.ler_pasta()."""
    cfg = cfg or Config.original()
    frames = [entrada.normalizar(df, rot, tipo, cfg) for rot, (df, tipo) in bases.items()]
    bruto, cons, contagens = consolidar(frames, cfg)
    cons = nucleo.aplicar_filtros(cons, cfg)
    cand = nucleo.candidatos(cons)
    exp = nucleo.nucleo_expandido(cons)
    contagens.update({
        "nucleo_obrigatorio": int(len(nucleo.nucleo_obrigatorio(cons))),
        "candidatos_antes_da_exclusao": int(len(cand)),
        "excluidos_entre_candidatos": int(cand["is_excluded"].sum()),
        "corpus": int(len(exp)),
    })
    corpus = nucleo.calcular_escore(exp, cfg) if len(exp) else exp.assign(fascia=[])
    return Resultado(cfg=cfg, bruto=bruto, consolidado=cons, corpus=corpus, contagens=contagens)
