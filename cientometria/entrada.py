"""Leitura e normalização das exportações.

Duas camadas, com responsabilidades separadas:

1. `normalizar` — esquema da TRIAGEM (title, year, abstract, keywords, citations, doi,
   source). No modo original reproduz o procedimento de jan/2026 (mapeamento fixo,
   colunas ausentes viram 'Unknown'/vazio). Não mude o comportamento do mapeamento
   original: o teste de equivalência (tests/test_equivalencia_original.py) protege isso.
2. `normalizar_estendido` — esquema BIBLIOMÉTRICO (autores, afiliações, países,
   palavras-chave de autor/indexadas, referências, tipo, idioma, área). Não é usado
   pela triagem; alimenta `bibliometria.py`.

Toda linha normalizada carrega proveniência: `arquivo_origem` e `linha_origem`
(linha de dados no arquivo, começando em 1). Essas colunas não entram em nenhum cálculo.
"""
from __future__ import annotations
import os
import pandas as pd

# arquivo esperado -> (rótulo, tipo de base). Mesmos nomes do procedimento original.
# A ORDEM importa: a deduplicação mantém o primeiro registro (keep='first').
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

# EXTENSÃO (não faz parte do procedimento do artigo): mapeamentos fixos para outras
# bases. RIS/BibTeX/WoS-texto são convertidos por `ingestao.py` para estes nomes.
MAPEAMENTO_EXTENSAO = {
    "wos": dict(title="TI", year="PY", abstract="AB", keywords="DE", citations="TC",
                doi="DI", source="SO"),
    "openalex": dict(title="title", year="publication_year", abstract="abstract",
                     keywords="keywords", citations="cited_by_count", doi="doi",
                     source="primary_location.source.display_name"),
    "ris": dict(title="Title", year="Year", abstract="Abstract", keywords="Author Keywords",
                citations="Cited by", doi="DOI", source="Source title"),
    "bibtex": dict(title="Title", year="Year", abstract="Abstract", keywords="Author Keywords",
                   citations="Cited by", doi="DOI", source="Source title"),
    "generico": dict(title="Title", year="Year", abstract="Abstract", keywords="Keywords",
                     citations="Cited by", doi="DOI", source="Source title"),
}

MAPEAMENTO_FIXO = {**MAPEAMENTO_ORIGINAL, **MAPEAMENTO_EXTENSAO}
TIPOS_ORIGINAIS = tuple(MAPEAMENTO_ORIGINAL)

# Aliases aceitos no modo tolerante (comparação sem caixa). Keywords: todas as colunas achadas são unidas.
ALIASES = {
    "title": ["Title", "Document Title", "Article Title", "Título", "Titulo", "TI", "display_name"],
    "year": ["Publication Year", "Year", "Ano", "PY", "publication_year"],
    "abstract": ["Abstract", "Resumo", "AB"],
    "keywords": ["Keywords", "Author Keywords", "Index Keywords", "IEEE Terms",
                 "Palavras-chave", "Palavras chave", "DE", "ID"],
    "citations": ["Citing Works Count", "Cited by", "Citations", "Article Citation Count",
                  "Times Cited", "Citações", "TC", "cited_by_count",
                  "Times Cited, All Databases"],
    "doi": ["DOI", "DI", "doi"],
    "source": ["Source Title", "Source title", "Publication Title", "Source", "Journal", "SO",
               "primary_location.source.display_name"],
}

# Esquema bibliométrico estendido (somente leitura tolerante).
ALIASES_EXT = {
    "authors": ["Authors", "Author full names", "Author Names", "Autores", "AU", "AF",
                "authorships.author.display_name"],
    "affiliations": ["Affiliations", "Authors with affiliations", "Author Affiliations",
                     "Institutions", "C1", "authorships.institutions.display_name"],
    "countries": ["Countries", "Country", "Country/Territory", "Países",
                  "authorships.countries"],
    "author_keywords": ["Author Keywords", "Keywords", "Palavras-chave", "DE"],
    "index_keywords": ["Index Keywords", "IEEE Terms", "INSPEC Controlled Terms",
                       "Keywords Plus", "MeSH Terms", "ID", "concepts.display_name"],
    "references": ["References", "Cited References", "Referências", "CR",
                   "referenced_works"],
    "doc_type": ["Document Type", "Publication Type", "Content Type", "DT", "type"],
    "language": ["Language of Original Document", "Language", "Idioma", "LA", "language"],
    "subject_area": ["Fields of Study", "Subject Area", "Research Areas", "WoS Categories",
                     "SC", "WC", "Áreas", "primary_topic.field.display_name"],
    "publisher": ["Publisher", "PU", "publisher"],
}


def _col(df, nome):
    """Coluna por nome, sem distinguir caixa; None se não existir."""
    mapa = {str(c).lower().strip(): c for c in df.columns}
    return mapa.get(str(nome).lower().strip()) if nome else None


def _colunas_tolerantes(df, campo, aliases=ALIASES):
    achadas = []
    for a in aliases[campo]:
        c = _col(df, a)
        if c is not None and c not in achadas:
            achadas.append(c)
    return achadas


def _proveniencia(df, n):
    arq = df.attrs.get("arquivo_origem", "")
    return pd.Series([arq] * n), pd.Series(range(1, n + 1))


def normalizar(df: pd.DataFrame, rotulo: str, tipo: str, cfg) -> pd.DataFrame:
    """Converte uma exportação para o esquema comum da triagem.
    Diferença deliberada em relação ao original: `source_db` é preenchida (no original
    ficava vazia por atribuir um escalar a um DataFrame vazio). Não afeta nenhuma contagem."""
    if len(df) == 0:
        return pd.DataFrame()
    n = len(df)
    out = pd.DataFrame(index=range(n))
    out["source_db"] = rotulo
    out["db_type"] = tipo
    m = MAPEAMENTO_FIXO.get(tipo, MAPEAMENTO_EXTENSAO["generico"])
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
    out["arquivo_origem"], out["linha_origem"] = _proveniencia(df, n)
    return out


def campos_usados(df: pd.DataFrame, tipo: str, cfg) -> dict:
    """Qual coluna do arquivo alimenta cada campo da triagem (None = campo vazio)."""
    m = MAPEAMENTO_FIXO.get(tipo, MAPEAMENTO_EXTENSAO["generico"])
    saida = {}
    for campo in ALIASES:
        if cfg.mapeamento_tolerante:
            cols = _colunas_tolerantes(df, campo)
            saida[campo] = (cols if campo == "keywords" else cols[:1]) or None
        else:
            c = m.get(campo)
            saida[campo] = [c] if c and c in df.columns else None
    return saida


def normalizar_estendido(df: pd.DataFrame, rotulo: str, tipo: str) -> pd.DataFrame:
    """Esquema bibliométrico (tolerante). Inclui os campos da triagem lidos com aliases."""
    if len(df) == 0:
        return pd.DataFrame()
    n = len(df)
    out = pd.DataFrame(index=range(n))
    out["source_db"] = rotulo
    out["db_type"] = tipo
    for campo in {**ALIASES, **ALIASES_EXT}:
        cols = _colunas_tolerantes(df, campo, {**ALIASES, **ALIASES_EXT})
        if not cols:
            out[campo] = pd.NA
            continue
        if campo in ("keywords", "index_keywords"):
            s = df[cols].fillna("").astype(str).agg("; ".join, axis=1).str.strip("; ")
            out[campo] = s.replace("", pd.NA).reset_index(drop=True)
        else:
            out[campo] = df[cols[0]].reset_index(drop=True)
    out["year"] = pd.to_numeric(out["year"], errors="coerce")
    out["citations"] = pd.to_numeric(out["citations"], errors="coerce")
    out["arquivo_origem"], out["linha_origem"] = _proveniencia(df, n)
    return out


def ler_csv(caminho: str) -> pd.DataFrame:
    """Leitura do procedimento original: pd.read_csv com padrões; erro -> DataFrame vazio."""
    try:
        df = pd.read_csv(caminho)
    except Exception as e:  # mesmo comportamento do original: avisa e segue com vazio
        print(f"✗ {os.path.basename(caminho)}: erro - {e}")
        return pd.DataFrame()
    df.attrs["arquivo_origem"] = os.path.basename(caminho)
    return df


def ler_pasta(pasta: str) -> dict:
    """Lê os 8 arquivos esperados. Devolve {rótulo: (DataFrame bruto, tipo)}."""
    bases = {}
    for arq, (rotulo, tipo) in BASES_ESPERADAS.items():
        p = os.path.join(pasta, arq)
        bases[rotulo] = (ler_csv(p) if os.path.exists(p) else pd.DataFrame(), tipo)
    return bases
