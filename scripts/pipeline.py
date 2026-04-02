#!/usr/bin/env python3
import json
import re
import sys
import unicodedata
from pathlib import Path

import pandas as pd

FIELD_MAP = {
    "title": ["title", "document title", "titulo", "título"],
    "year": ["year", "publication year", "ano", "coverdate"],
    "abstract": ["abstract", "summary", "resumo", "description"],
    "keywords": ["keywords", "author keywords", "index keywords", "palavras-chave", "keyword"],
    "citations": ["cited by", "citations", "times cited", "citation count", "número de citações"],
    "doi": ["doi", "digital object identifier"],
    "journal": ["source title", "journal", "periódico", "publication name"],
}

FLOOD_TERMS = ["flood", "inundacao", "inundação", "enchente", "flooding", "inundation"]
FORECAST_TERMS = ["forecast", "forecasting", "prediction", "previsao", "previsão", "early warning"]
AI_TERMS = ["machine learning", "deep learning", "artificial intelligence", "neural network", "xgboost", "svm", "random forest", "cnn", "rnn", "lstm"]
EXCLUDE_TERMS = ["flood insurance", "flood mythology", "flood psychology"]
HYDRO_TERMS = ["rain", "rainfall", "chuva", "streamflow", "vazao", "vazão", "water level", "nivel d", "nível d", "hydrolog"]
GEO_TERMS = ["satellite", "dem", "digital elevation", "remote sensing", "geospatial", "gis"]
METHOD_STRONG = ["lstm", "rnn", "cnn", "random forest", "svm", "xgboost", "transformer", "ensemble", "gradient boosting"]
OUTPUT_STRONG = ["prediction", "forecast", "early warning", "mapping"]
OUTPUT_MED = ["model", "risk assessment", "susceptibility"]
CONTEXT_STRONG = ["urban", "coastal", "river", "city", "basin", "watershed"]

DEFAULT_TERMS = {
    "topic1": FLOOD_TERMS,
    "topic2": FORECAST_TERMS,
    "method": AI_TERMS,
    "exclude": EXCLUDE_TERMS,
    "input_a": HYDRO_TERMS,
    "input_b": GEO_TERMS,
    "method_strong": METHOD_STRONG,
    "output_strong": OUTPUT_STRONG,
    "output_med": OUTPUT_MED,
    "context_strong": CONTEXT_STRONG,
}


def normalize_text(value: str) -> str:
    if value is None:
        return ""
    value = str(value)
    value = unicodedata.normalize("NFKD", value)
    value = "".join(ch for ch in value if not unicodedata.combining(ch))
    value = value.lower().strip()
    value = re.sub(r"\s+", " ", value)
    return value


def pick_column(df: pd.DataFrame, aliases):
    norm_cols = {normalize_text(c): c for c in df.columns}
    for a in aliases:
        n = normalize_text(a)
        if n in norm_cols:
            return norm_cols[n]
    return None


def harmonize(df: pd.DataFrame, source_file: str = "") -> pd.DataFrame:
    out = pd.DataFrame()
    for target, aliases in FIELD_MAP.items():
        col = pick_column(df, aliases)
        out[target] = df[col] if col else ""

    out["title"] = out["title"].astype(str)
    out["abstract"] = out["abstract"].astype(str)
    out["keywords"] = out["keywords"].astype(str)
    out["doi"] = out["doi"].astype(str).str.strip().str.lower()
    out["journal"] = out["journal"].astype(str)
    out["year"] = pd.to_numeric(out["year"], errors="coerce").fillna(0).astype(int)
    out["citations"] = pd.to_numeric(out["citations"], errors="coerce").fillna(0)

    out["title_norm"] = out["title"].map(normalize_text)
    out["blob"] = (out["title"].fillna("") + " " + out["abstract"].fillna("") + " " + out["keywords"].fillna(""))
    out["blob_norm"] = out["blob"].map(normalize_text)
    out["source_file"] = source_file
    return out


def contains_any(text: str, terms):
    return any(t in text for t in terms)

def thematic_filter(df: pd.DataFrame, terms: dict) -> pd.Series:
    blob = df["blob_norm"]
    has_topic1 = blob.apply(lambda t: contains_any(t, terms["topic1"]))
    has_topic2 = blob.apply(lambda t: contains_any(t, terms["topic2"]))
    has_method = blob.apply(lambda t: contains_any(t, terms["method"]))
    has_inputs = blob.apply(lambda t: contains_any(t, terms["input_a"]) or contains_any(t, terms["input_b"]))
    excluded = blob.apply(lambda t: contains_any(t, terms["exclude"]))
    return has_topic1 & has_topic2 & has_method & has_inputs & (~excluded)

def minmax(series: pd.Series):
    smin, smax = series.min(), series.max()
    if smax == smin:
        return pd.Series([1.0] * len(series), index=series.index)
    return (series - smin) / (smax - smin)

def clamp_norm(series: pd.Series, vmin: float, vmax: float):
    if vmax == vmin:
        return pd.Series([1.0] * len(series), index=series.index)
    return ((series - vmin) / (vmax - vmin)).clip(lower=0, upper=1)

def score_t(row, terms):
    t = normalize_text(row["title"])
    a = normalize_text(row["abstract"])
    k = normalize_text(row["keywords"])

    def combo(txt: str) -> bool:
        return contains_any(txt, terms["topic1"]) and contains_any(txt, terms["topic2"]) and contains_any(txt, terms["method"])

    if combo(t) or combo(a):
        return 1.0
    if combo(k) or combo(a):
        return 0.7
    return 0.4

def score_a(row, terms):
    txt = row["blob_norm"]
    has_hydro = contains_any(txt, terms["input_a"])
    has_geo = contains_any(txt, terms["input_b"])
    I = 1.0 if (has_hydro and has_geo) else (0.5 if has_hydro or has_geo else 0.0)

    strong_method = contains_any(txt, terms["method_strong"])
    generic_ml = contains_any(txt, terms["method"])
    M = 1.0 if strong_method else (0.5 if generic_ml else 0.0)

    O = 1.0 if contains_any(txt, terms["output_strong"]) else (0.5 if contains_any(txt, terms["output_med"]) else 0.0)
    C = 1.0 if contains_any(txt, terms["context_strong"]) else (0.5 if contains_any(txt, terms["topic1"]) else 0.0)

    return (I + M + O + C) / 4.0


def classify(score100, thresholds):
    if score100 >= thresholds["nucleo_a"]:
        return "Núcleo A"
    if score100 >= thresholds["nucleo_b"]:
        return "Núcleo B"
    if score100 >= thresholds["periferico"]:
        return "Periférico"
    return "Descarte"

def parse_bibtex(path: Path) -> pd.DataFrame:
    text = path.read_text(encoding="utf-8", errors="ignore")
    entries = re.split(r"@\w+\s*\{", text)[1:]
    rows = []
    for e in entries:
        fields = {}
        for m in re.finditer(r'(\\w+)\\s*=\\s*["{]([^"}]+)', e, flags=re.IGNORECASE):
            fields[m.group(1).lower()] = m.group(2).strip()
        rows.append({
            "title": fields.get("title", ""),
            "year": fields.get("year", ""),
            "abstract": fields.get("abstract", ""),
            "keywords": fields.get("keywords", ""),
            "citations": fields.get("citedby", 0),
            "doi": fields.get("doi", ""),
            "journal": fields.get("journal", fields.get("booktitle", "")),
        })
    return pd.DataFrame(rows)

def load_file(path: Path) -> pd.DataFrame:
    suffix = path.suffix.lower()
    if suffix in {".csv", ".tsv", ".txt"}:
        return pd.read_csv(path, sep=None, engine="python", encoding="utf-8-sig", on_bad_lines="skip")
    if suffix in {".xlsx", ".xls"}:
        return pd.read_excel(path)
    if suffix == ".bib":
        return parse_bibtex(path)
    raise ValueError(f"Formato não suportado: {path.name}")


def main():
    if len(sys.argv) < 2:
        raise SystemExit("Uso: pipeline.py <payload.json>")

    payload_path = Path(sys.argv[1])
    payload = json.loads(payload_path.read_text(encoding="utf-8"))
    files = [Path(p) for p in payload.get("files", [])]
    params = payload.get("params", {}) or {}
    weights = params.get("weights", {}) if isinstance(params.get("weights", {}), dict) else {}
    thresholds = params.get("thresholds", {}) if isinstance(params.get("thresholds", {}), dict) else {}
    term_params = params.get("terms", {}) if isinstance(params.get("terms", {}), dict) else {}
    terms = {}
    for k, v in DEFAULT_TERMS.items():
        custom = term_params.get(k)
        terms[k] = [normalize_text(x) for x in custom if str(x).strip()] if isinstance(custom, list) and len(custom) > 0 else [normalize_text(x) for x in v]

    used_params = {
        "weights": {
            "c": float(weights.get("c", 0.35)),
            "r": float(weights.get("r", 0.20)),
            "t": float(weights.get("t", 0.30)),
            "a": float(weights.get("a", 0.15)),
        },
        "year_min": int(params.get("year_min", 1992)),
        "year_max": int(params.get("year_max", 2026)),
        "thresholds": {
            "nucleo_a": float(thresholds.get("nucleo_a", 70)),
            "nucleo_b": float(thresholds.get("nucleo_b", 50)),
            "periferico": float(thresholds.get("periferico", 30)),
        },
        "terms": {k: terms[k] for k in ["topic1","topic2","method","exclude","input_a","input_b"]},
    }

    if not files:
        raise SystemExit("Nenhum arquivo recebido")

    frames = []
    for f in files:
        df = load_file(f)
        frames.append(harmonize(df, f.name))

    all_df = pd.concat(frames, ignore_index=True)
    raw_records = len(all_df)

    no_empty_doi = all_df[all_df["doi"].str.len() > 0].copy()
    empty_doi = all_df[all_df["doi"].str.len() == 0].copy()
    doi_dup_mask = no_empty_doi.duplicated(subset=["doi"], keep="first")
    removed_doi = no_empty_doi[doi_dup_mask].copy()
    dedup_doi = pd.concat([no_empty_doi[~doi_dup_mask], empty_doi], ignore_index=True)
    after_doi = len(dedup_doi)

    title_dup_mask = dedup_doi.duplicated(subset=["title_norm"], keep="first")
    removed_title = dedup_doi[title_dup_mask].copy()
    dedup_title = dedup_doi[~title_dup_mask].copy()
    after_title = len(dedup_title)

    dedup_removed = {
        "doi_removed": [
            {"title": r["title"], "doi": r["doi"], "year": int(r["year"]), "source_file": r.get("source_file", "")}
            for _, r in removed_doi.head(1000).iterrows()
        ],
        "title_removed": [
            {"title": r["title"], "doi": r["doi"], "year": int(r["year"]), "source_file": r.get("source_file", "")}
            for _, r in removed_title.head(1000).iterrows()
        ],
        "counts": {"doi_removed": int(len(removed_doi)), "title_removed": int(len(removed_title))},
    }

    thematic_mask = thematic_filter(dedup_title, terms)
    selected = dedup_title[thematic_mask].copy()

    if len(selected) == 0:
        result = {
            "summary": {
                "raw_records": int(raw_records),
                "after_doi": int(after_doi),
                "after_title": int(after_title),
                "thematic_selected": 0,
                "core_counts": {"Núcleo A": 0, "Núcleo B": 0, "Periférico": 0, "Descarte": 0},
                "t_star_distribution": {"1.0":0,"0.7":0,"0.4":0},
                "a_star_bins": {">=0.9":0,"0.7-0.9":0,"0.5-0.7":0},
                "score_stats": {"mean":0,"median":0,"std":0},
            },
            "top_articles": [],
            "dedup_removed": dedup_removed,
            "plot_urls": {"generated_with": "python"},
            "used_params": used_params,
        }
        print(json.dumps(result, ensure_ascii=False))
        return

    cmin = params.get("c_min", float(selected["citations"].min()))
    cmax = params.get("c_max", float(selected["citations"].max()))
    selected["c_star"] = clamp_norm(selected["citations"], float(cmin), float(cmax))
    selected["r_star"] = clamp_norm(selected["year"], used_params["year_min"], used_params["year_max"])
    selected["t_star"] = selected.apply(score_t, axis=1, args=(terms,))
    selected["a_star"] = selected.apply(score_a, axis=1, args=(terms,))
    w = used_params["weights"]
    selected["score"] = w["c"] * selected["c_star"] + w["r"] * selected["r_star"] + w["t"] * selected["t_star"] + w["a"] * selected["a_star"]
    selected["score100"] = minmax(selected["score"]) * 100
    selected["nucleo"] = selected["score100"].apply(lambda v: classify(v, used_params["thresholds"]))

    core_counts = selected["nucleo"].value_counts().to_dict()
    for c in ["Núcleo A", "Núcleo B", "Periférico", "Descarte"]:
        core_counts.setdefault(c, 0)

    t_dist = {"1.0": int((selected["t_star"] == 1.0).sum()), "0.7": int((selected["t_star"] == 0.7).sum()), "0.4": int((selected["t_star"] == 0.4).sum())}
    a_bins = {
        ">=0.9": int((selected["a_star"] >= 0.9).sum()),
        "0.7-0.9": int(((selected["a_star"] >= 0.7) & (selected["a_star"] < 0.9)).sum()),
        "0.5-0.7": int(((selected["a_star"] >= 0.5) & (selected["a_star"] < 0.7)).sum()),
    }

    top = selected.sort_values("score100", ascending=False)

    result = {
        "summary": {
            "raw_records": int(raw_records),
            "after_doi": int(after_doi),
            "after_title": int(after_title),
            "thematic_selected": int(len(selected)),
            "core_counts": core_counts,
            "t_star_distribution": t_dist,
            "a_star_bins": a_bins,
            "score_stats": {
                "mean": float(selected["score100"].mean()),
                "median": float(selected["score100"].median()),
                "std": float(selected["score100"].std(ddof=0)),
            },
        },
        "used_params": used_params,
        "dedup_removed": dedup_removed,
        "plot_urls": {"generated_with": "python"},
        "top_articles": [
            {
                "title": r["title"],
                "year": int(r["year"]),
                "citations": float(r["citations"]),
                "doi": r["doi"],
                "nucleo": r["nucleo"],
                "score100": float(r["score100"]),
                "c_norm": float(r["c_star"]),
                "r_norm": float(r["r_star"]),
                "t_score": float(r["t_star"]),
                "a_score": float(r["a_star"]),
            }
            for _, r in top.iterrows()
        ],
    }
    print(json.dumps(result, ensure_ascii=False))


if __name__ == "__main__":
    main()
