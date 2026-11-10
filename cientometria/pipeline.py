"""Orquestra as etapas: consolidar → filtrar → escorar → classificar."""
from __future__ import annotations
from dataclasses import dataclass, field
import pandas as pd
from .config import Config
from . import entrada, nucleo
from .consolidacao import chave_doi, anotar_proveniencia


@dataclass
class Resultado:
    cfg: Config
    bruto: pd.DataFrame          # todos os registros normalizados, antes da deduplicação
    consolidado: pd.DataFrame    # após deduplicação, com flags temáticos
    corpus: pd.DataFrame         # núcleo expandido, com escore e fascia
    contagens: dict = field(default_factory=dict)

    def estratos(self) -> dict:
        if "fascia" not in self.corpus:
            return {k: 0 for k in ["Núcleo A", "Núcleo B", "Periférico", "Descarte"]}
        return {k: int((self.corpus["fascia"] == k).sum())
                for k in ["Núcleo A", "Núcleo B", "Periférico", "Descarte"]}


def consolidar(frames: list, cfg: Config):
    """Deduplica em duas etapas (DOI, depois título). Devolve (bruto, df, contagens).

    Modo original: a etapa de DOI mantém apenas linhas COM DOI (descarta as sem DOI) e
    compara o DOI como texto bruto. Com cfg.manter_sem_doi=True, registros sem DOI são
    mantidos e passam só pela deduplicação por título; títulos 'Unknown'/vazios nunca são
    colapsados entre si. Com cfg.normalizar_doi=True, a comparação usa o DOI normalizado
    (a coluna `doi` exibida não é alterada)."""
    frames = [f for f in frames if len(f) > 0]
    if not frames:
        raise ValueError("Nenhum registro lido: todos os arquivos estão vazios ou ilegíveis.")
    bruto = pd.concat(frames, ignore_index=True)
    bruto["title_normalized"] = bruto["title"].astype(str).str.lower().str.strip()
    if "titulo_sem_coluna" in bruto:
        # no script original esses títulos são NaN: grupo próprio, separado de 'unknown' (achado 11)
        sem_coluna = bruto["titulo_sem_coluna"].fillna(False).astype(bool)
        bruto.loc[sem_coluna, "title_normalized"] = "\x00titulo-sem-coluna"
    bruto["doi_chave"] = chave_doi(bruto["doi"], cfg)
    sem = bruto["doi_chave"] == ""
    sem_doi = int(sem.sum())
    com_doi = bruto[~sem]
    dup_doi = int(com_doi.duplicated(subset=["doi_chave"]).sum())
    if cfg.manter_sem_doi:
        a = pd.concat([com_doi.drop_duplicates(subset=["doi_chave"], keep="first"),
                       bruto[sem]]).sort_index()
    else:
        a = com_doi.drop_duplicates(subset=["doi_chave"], keep="first")
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
    """bases: {rótulo: (DataFrame bruto, tipo)} — ver entrada.ler_pasta() ou ingestao.carregar_fontes()."""
    cfg = cfg or Config.original()
    frames = [entrada.normalizar(df, rot, tipo, cfg) for rot, (df, tipo) in bases.items()]
    bruto, cons, contagens = consolidar(frames, cfg)
    cons = nucleo.aplicar_filtros(cons, cfg)
    cons = anotar_proveniencia(cons, bruto)
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
