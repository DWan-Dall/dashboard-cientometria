"""Ingestão de arquivos: leitura de formatos, identificação da base, proveniência e ordem.

Regras que preservam a reprodução do artigo:
- No modo `original`, arquivos .csv são lidos EXATAMENTE como no procedimento original
  (`pd.read_csv` com parâmetros padrão; erro -> base vazia). Outras leituras (separador
  detectado, codificação alternativa, linhas defeituosas ignoradas) só nos demais modos,
  e cada desvio fica registrado em `Fonte.avisos`.
- Quando os nomes dos arquivos coincidem com os 8 nomes do procedimento original,
  a ordem e os rótulos canônicos são usados (a deduplicação mantém o 1º registro,
  então a ordem muda o resultado). Caso contrário, a ordem é a recebida e fica
  registrada no manifesto.
"""
from __future__ import annotations
import csv
import hashlib
import io
import os
import re
from dataclasses import dataclass, field, asdict
from pathlib import Path

import pandas as pd

from .entrada import BASES_ESPERADAS, ler_csv

FORMATOS = (".csv", ".tsv", ".txt", ".xlsx", ".xls", ".ris", ".bib", ".bibtex", ".nbib")


@dataclass
class Fonte:
    arquivo: str                 # nome do arquivo (sem diretório)
    caminho: str
    sha256: str
    bytes: int
    formato: str
    tipo: str                    # lens, scopus, ieee, scielo, wos, openalex, ris, bibtex, generico
    rotulo: str
    registros: int = 0
    colunas: list = field(default_factory=list)
    leitura: str = ""            # estratégia de leitura usada
    deteccao: str = ""           # como o tipo foi identificado
    canonico: bool = False       # nome coincide com o procedimento original
    avisos: list = field(default_factory=list)

    def como_dict(self) -> dict:
        d = asdict(self)
        d["colunas"] = list(map(str, self.colunas))
        return d


def sha256_arquivo(caminho) -> str:
    h = hashlib.sha256()
    with open(caminho, "rb") as f:
        for bloco in iter(lambda: f.read(1 << 20), b""):
            h.update(bloco)
    return h.hexdigest()


# ---------------------------------------------------------------------------
# Leitores por formato
# ---------------------------------------------------------------------------
def _ler_texto(caminho) -> tuple[str, str]:
    bruto = Path(caminho).read_bytes()
    for enc in ("utf-8-sig", "utf-8", "cp1252", "latin-1"):
        try:
            return bruto.decode(enc), enc
        except UnicodeDecodeError:
            continue
    return bruto.decode("latin-1", errors="replace"), "latin-1(replace)"


def ler_tabela_robusta(caminho, avisos: list) -> pd.DataFrame:
    """CSV/TSV/TXT com separador detectado e codificação alternativa."""
    texto, enc = _ler_texto(caminho)
    if enc != "utf-8-sig" and enc != "utf-8":
        avisos.append(f"codificação {enc}")
    amostra = texto[:20000]
    try:
        sep = csv.Sniffer().sniff(amostra, delimiters=",;\t|").delimiter
    except csv.Error:
        sep = "\t" if amostra.count("\t") > amostra.count(",") else ","
    linhas_ruins = []

    def _ruim(linha):
        linhas_ruins.append(linha)
        return None

    df = pd.read_csv(io.StringIO(texto), sep=sep, engine="python", on_bad_lines=_ruim, dtype=str,
                     keep_default_na=True)
    if linhas_ruins:
        avisos.append(f"{len(linhas_ruins)} linha(s) malformada(s) ignorada(s)")
    if sep != ",":
        avisos.append(f"separador {sep!r}")
    # números voltam a numérico onde possível (anos, citações)
    for c in df.columns:
        conv = pd.to_numeric(df[c], errors="coerce")
        if df[c].notna().sum() and conv.notna().sum() == df[c].notna().sum():
            df[c] = conv
    return df


# --- WoS texto (Plain Text / "FN Clarivate") ---------------------------------
def ler_wos_texto(caminho) -> pd.DataFrame:
    texto, _ = _ler_texto(caminho)
    registros, atual, tag = [], {}, None
    for linha in texto.splitlines():
        if linha.startswith("ER"):
            if atual:
                registros.append(atual)
            atual, tag = {}, None
            continue
        if linha[:2] in ("FN", "VR", "EF"):
            continue
        if len(linha) >= 2 and linha[:2].strip() and linha[2:3] in (" ", ""):
            tag = linha[:2]
            valor = linha[3:].strip()
            atual[tag] = (atual[tag] + "\n" + valor) if tag in atual else valor
        elif tag and linha.startswith("   "):
            atual[tag] = atual[tag] + "\n" + linha.strip()
    if atual:
        registros.append(atual)
    df = pd.DataFrame(registros)
    multi = {"AU": "; ", "AF": "; ", "C1": "; ", "CR": "; ", "DE": " ", "ID": " "}
    for t, s in multi.items():
        if t in df:
            df[t] = df[t].fillna("").str.replace("\n", s, regex=False).replace("", pd.NA)
    for t in ("TI", "AB", "SO"):
        if t in df:
            df[t] = df[t].str.replace("\n", " ", regex=False)
    return df


def _e_wos_texto(caminho) -> bool:
    with open(caminho, "rb") as f:
        cab = f.read(200).decode("utf-8", errors="ignore").lstrip("﻿")
    return cab.startswith("FN ") or "\nPT " in cab[:200] or cab.startswith("PT ")


# --- RIS ---------------------------------------------------------------------
_RIS = {"TI": "Title", "T1": "Title", "PY": "Year", "Y1": "Year", "DA": "Year", "AB": "Abstract",
        "N2": "Abstract", "KW": "Author Keywords", "DO": "DOI", "JO": "Source title",
        "T2": "Source title", "JF": "Source title", "AU": "Authors", "A1": "Authors",
        "AD": "Affiliations", "LA": "Language", "TY": "Document Type", "PB": "Publisher",
        "UR": "URL"}
_RIS_MULTI = {"Author Keywords", "Authors", "Affiliations"}


def ler_ris(caminho) -> pd.DataFrame:
    texto, _ = _ler_texto(caminho)
    registros, atual = [], {}
    rx = re.compile(r"^([A-Z][A-Z0-9])  - ?(.*)$")
    for linha in texto.splitlines():
        m = rx.match(linha)
        if not m:
            continue
        tag, valor = m.group(1), m.group(2).strip()
        if tag == "ER":
            registros.append(atual)
            atual = {}
            continue
        campo = _RIS.get(tag)
        if not campo or not valor:
            continue
        if campo in _RIS_MULTI:
            atual.setdefault(campo, []).append(valor)
        elif campo not in atual:
            atual[campo] = valor
    if atual:
        registros.append(atual)
    linhas = [{k: ("; ".join(v) if isinstance(v, list) else v) for k, v in r.items()} for r in registros]
    df = pd.DataFrame(linhas)
    if "Year" in df:
        df["Year"] = pd.to_numeric(df["Year"].astype(str).str.extract(r"(\d{4})")[0], errors="coerce")
    return df


# --- BibTeX ------------------------------------------------------------------
_BIB = {"title": "Title", "year": "Year", "abstract": "Abstract", "keywords": "Author Keywords",
        "author_keywords": "Author Keywords", "doi": "DOI", "journal": "Source title",
        "booktitle": "Source title", "author": "Authors", "affiliation": "Affiliations",
        "affiliations": "Affiliations", "language": "Language", "publisher": "Publisher",
        "note": "Note", "references": "References", "type": "Document Type",
        "web-of-science-categories": "WoS Categories", "research-areas": "Research Areas"}


def _valor_bib(texto: str, i: int) -> tuple[str, int]:
    """Lê um valor BibTeX a partir de texto[i] ({...}, "..." ou número). Devolve (valor, fim)."""
    while i < len(texto) and texto[i] in " \t\r\n":
        i += 1
    if i >= len(texto):
        return "", i
    if texto[i] == "{":
        prof, j = 0, i
        while j < len(texto):
            if texto[j] == "{":
                prof += 1
            elif texto[j] == "}":
                prof -= 1
                if prof == 0:
                    return texto[i + 1:j], j + 1
            j += 1
        return texto[i + 1:], len(texto)
    if texto[i] == '"':
        j = i + 1
        while j < len(texto) and not (texto[j] == '"' and texto[j - 1] != "\\"):
            j += 1
        return texto[i + 1:j], j + 1
    m = re.match(r"[^,}\s]+", texto[i:])
    return (m.group(0), i + m.end()) if m else ("", i)


def ler_bibtex(caminho) -> pd.DataFrame:
    texto, _ = _ler_texto(caminho)
    linhas = []
    for m in re.finditer(r"@(\w+)\s*\{\s*([^,]*),", texto):
        if m.group(1).lower() in ("comment", "string", "preamble"):
            continue
        i, campos = m.end(), {"Document Type": m.group(1).lower()}
        while i < len(texto):
            mm = re.compile(r"\s*([\w\-:.]+)\s*=\s*").match(texto, i)
            if not mm:
                break
            valor, i = _valor_bib(texto, mm.end())
            valor = re.sub(r"\s+", " ", valor.replace("{", "").replace("}", "")).strip()
            chave = mm.group(1).lower()
            destino = _BIB.get(chave)
            if chave in ("cited-by", "citedby", "times-cited", "cited_by"):
                destino = "Cited by"
            if destino:
                if destino == "Authors":
                    valor = "; ".join(a.strip() for a in valor.split(" and "))
                campos.setdefault(destino, valor)
            while i < len(texto) and texto[i] in " \t\r\n,":
                i += 1
            if i < len(texto) and texto[i] == "}":
                break
        linhas.append(campos)
    df = pd.DataFrame(linhas)
    for c in ("Year", "Cited by"):
        if c in df:
            df[c] = pd.to_numeric(df[c].astype(str).str.extract(r"(\d+)")[0], errors="coerce")
    return df


def ler_arquivo(caminho, estrategia: str = "robusta", avisos: list | None = None) -> tuple[pd.DataFrame, str, str]:
    """Lê um arquivo. Devolve (DataFrame, formato, estratégia usada).

    estrategia='original' só se aplica a .csv: leitura idêntica ao procedimento do artigo."""
    avisos = [] if avisos is None else avisos
    p = Path(caminho)
    suf = p.suffix.lower()
    if suf == ".csv" and estrategia == "original":
        return ler_csv(str(p)), "csv", "original: pd.read_csv padrão"
    if suf in (".xlsx", ".xls"):
        return pd.read_excel(p), "xlsx", "pd.read_excel"
    if suf == ".ris":
        return ler_ris(p), "ris", "parser RIS"
    if suf in (".bib", ".bibtex"):
        return ler_bibtex(p), "bibtex", "parser BibTeX"
    if suf in (".txt", ".nbib") and _e_wos_texto(p):
        return ler_wos_texto(p), "wos-texto", "parser WoS (texto)"
    if suf in (".csv", ".tsv", ".txt"):
        if estrategia == "original":
            avisos.append("formato fora do procedimento original: lido com leitura robusta")
        return ler_tabela_robusta(p, avisos), suf.lstrip("."), "robusta (separador/codificação detectados)"
    raise ValueError(f"Formato não suportado: {p.name} (aceitos: {', '.join(FORMATOS)})")


# ---------------------------------------------------------------------------
# Identificação da base
# ---------------------------------------------------------------------------
_ASSINATURAS = [
    ("lens", {"lens id", "citing works count"}, 1),
    ("scopus", {"eid", "source title", "cited by", "link"}, 2),
    ("scopus", {"author(s) id", "eid"}, 1),
    ("ieee", {"document title", "article citation count", "ieee terms"}, 2),
    ("ieee", {"pdf link", "document title"}, 2),
    ("wos", {"ut", "ti", "so", "py"}, 3),
    ("wos", {"ut (unique wos id)", "article title"}, 1),
    ("openalex", {"openalex_id", "publication_year"}, 1),
    ("openalex", {"id", "display_name", "publication_year", "cited_by_count"}, 3),
    ("scielo", {"título", "resumo"}, 2),
]


def detectar_tipo(df: pd.DataFrame, nome: str, formato: str = "") -> tuple[str, str]:
    """Devolve (tipo, como foi detectado). Ordem: nome canônico > formato > colunas > nome."""
    if nome in BASES_ESPERADAS:
        return BASES_ESPERADAS[nome][1], "nome canônico do procedimento original"
    if formato == "wos-texto":
        return "wos", "formato WoS texto"
    if formato in ("ris", "bibtex"):
        return formato, f"formato {formato}"
    cols = {str(c).lower().strip().lstrip("﻿") for c in df.columns}
    for tipo, assinatura, minimo in _ASSINATURAS:
        if len(assinatura & cols) >= minimo:
            return tipo, f"colunas: {sorted(assinatura & cols)}"
    n = nome.lower()
    for tipo in ("lens", "scopus", "ieee", "scielo", "wos", "openalex"):
        if tipo in n:
            return tipo, "nome do arquivo"
    return "generico", "não identificado (mapeamento genérico)"


ROTULOS = {"lens": "Lens", "scopus": "Scopus", "ieee": "IEEE Xplore", "scielo": "SciELO",
           "wos": "Web of Science", "openalex": "OpenAlex", "ris": "RIS", "bibtex": "BibTeX",
           "generico": "Genérica"}


def carregar_fontes(caminhos, cfg, nomes: list | None = None, tipos: dict | None = None):
    """Lê arquivos e devolve (bases, fontes).

    bases: {rótulo: (DataFrame bruto, tipo)} na ordem de processamento (ver docstring do módulo).
    fontes: lista de `Fonte` com hash, leitura, detecção e avisos.
    nomes: nomes originais dos arquivos (quando o caminho tem nome temporário).
    tipos: {nome: tipo} para forçar o tipo de base de um arquivo (decisão registrada)."""
    caminhos = [str(c) for c in caminhos]
    nomes = nomes or [os.path.basename(c) for c in caminhos]
    tipos = tipos or {}
    itens = list(zip(caminhos, nomes))
    todos_canonicos = all(n in BASES_ESPERADAS for _, n in itens)
    if todos_canonicos:
        ordem = list(BASES_ESPERADAS)
        itens.sort(key=lambda x: ordem.index(x[1]))
    estrategia = "original" if cfg.modo == "original" or not cfg.mapeamento_tolerante else "robusta"
    bases, fontes, usados = {}, [], {}
    for caminho, nome in itens:
        avisos = []
        df, formato, leitura = ler_arquivo(caminho, estrategia=estrategia, avisos=avisos)
        df.attrs["arquivo_origem"] = nome
        if nome in tipos:
            tipo, deteccao = tipos[nome], "definido pelo usuário"
        else:
            tipo, deteccao = detectar_tipo(df, nome, formato)
        canonico = nome in BASES_ESPERADAS
        rotulo = BASES_ESPERADAS[nome][0] if canonico else f"{ROTULOS.get(tipo, tipo)} — {nome}"
        if rotulo in usados:
            usados[rotulo] += 1
            rotulo = f"{rotulo} ({usados[rotulo]})"
        else:
            usados[rotulo] = 1
        if cfg.modo == "original" and tipo not in ("lens", "scopus", "ieee", "scielo"):
            avisos.append(f"tipo '{tipo}' não existe no procedimento original: mapeamento fixo de extensão")
        if len(df) == 0:
            avisos.append("arquivo vazio ou ilegível nesta estratégia de leitura")
        fontes.append(Fonte(arquivo=nome, caminho=caminho, sha256=sha256_arquivo(caminho),
                            bytes=os.path.getsize(caminho), formato=formato, tipo=tipo, rotulo=rotulo,
                            registros=len(df), colunas=list(df.columns), leitura=leitura,
                            deteccao=deteccao, canonico=canonico, avisos=avisos))
        bases[rotulo] = (df, tipo)
    if not todos_canonicos and len(itens) > 1:
        for f in fontes:
            f.avisos.append("ordem de processamento = ordem recebida (afeta qual duplicata é mantida)")
    return bases, fontes
