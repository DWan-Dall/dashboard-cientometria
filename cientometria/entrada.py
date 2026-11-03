"""Leitura e normalização das exportações (Lens, Scopus, IEEE Xplore, SciELO)."""
from __future__ import annotations
import os
import pandas as pd

# arquivo esperado -> (rótulo, tipo de base). Mesmos nomes do procedimento original.
BASES_ESPERADAS = {
    "lens-export.csv": ("Lens (EN)", "lens"),
    "lens-export-port.csv": ("Lens (PT)", "lens"),
    "scopus-sem-filtro.csv": ("Scopus (Sem Filtro)", "scopus"),
    "scopus-com-filtro.csv": ("Scopus (Com Filtro)", "scopus"),
    "scopus-port.csv": ("Scopus (PT)", "scopus"),
    "ieee-export.csv": ("IEEE Xplore", "ieee"),
    "SciELO.csv": ("SciELO (EN)", "scielo"),
    "SciELO-port.csv": ("SciELO (PT)", "scielo"),
}

# Mapeamento ORIGINAL (fixo). Colunas inexistentes nos arquivos reais de IEEE, SciELO
# e Scopus (Keywords) fazem o campo cair em 'Unknown'/vazio — falha documentada.
MAPEAMENTO_ORIGINAL = {
    "lens": dict(title="Title", year="Publication Year", abstract="Abstract", keywords="Keywords",
                 citations="Citing Works Count", doi="DOI", source="Source Title"),
    "scopus": dict(title="Title", year="Year", abstract="Abstract", keywords="Keywords",
                   citations="Cited by", doi="DOI", source="Source title"),
    "ieee": dict(title="Title", year="Publication Year", abstract="Abstract", keywords="Keywords",
                 citations="Citations", doi="DOI", source="Source Title"),
    "scielo": dict(title="Title", year="Year", abstract="Abstract", keywords="Keywords",
                   citations=None, doi="DOI", source="Source"),
}

# Aliases aceitos no modo tolerante (comparação sem caixa). Keywords: todas as colunas achadas são unidas.
ALIASES = {
    "title": ["Title", "Document Title", "Article Title", "Título", "Titulo"],
    "year": ["Publication Year", "Year", "Ano", "PY"],
    "abstract": ["Abstract", "Resumo"],
    "keywords": ["Keywords", "Author Keywords", "Index Keywords", "IEEE Terms",
                 "Palavras-chave", "Palavras chave"],
    "citations": ["Citing Works Count", "Cited by", "Citations", "Article Citation Count",
                  "Times Cited", "Citações"],
    "doi": ["DOI"],
    "source": ["Source Title", "Source title", "Publication Title", "Source", "Journal"],
}


def _col(df, nome):
    """Coluna por nome, sem distinguir caixa; None se não existir."""
    mapa = {c.lower().strip(): c for c in df.columns}
    return mapa.get(str(nome).lower().strip()) if nome else None


def _colunas_tolerantes(df, campo):
    achadas = []
    for a in ALIASES[campo]:
        c = _col(df, a)
        if c is not None and c not in achadas:
            achadas.append(c)
    return achadas


def normalizar(df: pd.DataFrame, rotulo: str, tipo: str, cfg) -> pd.DataFrame:
    """Converte uma exportação para o esquema comum.
    Diferença deliberada em relação ao original: `source_db` é preenchida (no original
    ficava vazia por atribuir um escalar a um DataFrame vazio). Não afeta nenhuma contagem."""
    if len(df) == 0:
        return pd.DataFrame()
    n = len(df)
    out = pd.DataFrame(index=range(n))
    out["source_db"] = rotulo
    out["db_type"] = tipo
    m = MAPEAMENTO_ORIGINAL[tipo]
    tol = cfg.mapeamento_tolerante

    def texto(campo, padrao):
        if tol:
            cols = _colunas_tolerantes(df, campo)
            if not cols:
                return pd.Series([padrao] * n)
            if campo == "keywords":
                return df[cols].fillna("").astype(str).agg("; ".join, axis=1).str.strip("; ").reset_index(drop=True)
            return df[cols[0]].fillna(padrao).reset_index(drop=True)
        c = m.get(campo)
        return df[c].fillna(padrao).reset_index(drop=True) if c in df.columns else pd.Series([padrao] * n)

    def numero(campo):
        if tol:
            cols = _colunas_tolerantes(df, campo)
            col = cols[0] if cols else None
        else:
            col = m.get(campo) if m.get(campo) in df.columns else None
        if col is None:
            return pd.Series([float("nan")] * n)
        return pd.to_numeric(df[col], errors="coerce").reset_index(drop=True)

    out["title"] = texto("title", "Unknown")
    out["year"] = numero("year")
    out["abstract"] = texto("abstract", "")
    out["keywords"] = texto("keywords", "")
    out["citations"] = numero("citations").fillna(0).astype(int)
    out["doi"] = texto("doi", "")
    out["source"] = texto("source", "Unknown")
    return out


def ler_csv(caminho: str) -> pd.DataFrame:
    try:
        return pd.read_csv(caminho)
    except Exception as e:  # mesmo comportamento do original: avisa e segue com vazio
        print(f"✗ {os.path.basename(caminho)}: erro - {e}")
        return pd.DataFrame()


def ler_pasta(pasta: str) -> dict:
    """Lê os 8 arquivos esperados. Devolve {rótulo: (DataFrame bruto, tipo)}."""
    bases = {}
    for arq, (rotulo, tipo) in BASES_ESPERADAS.items():
        p = os.path.join(pasta, arq)
        bases[rotulo] = (ler_csv(p) if os.path.exists(p) else pd.DataFrame(), tipo)
    return bases
