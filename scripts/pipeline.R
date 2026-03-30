#!/usr/bin/env Rscript
suppressPackageStartupMessages({
  library(jsonlite)
  library(readxl)
  library(ggplot2)
})

normalize_text <- function(x) {
  x <- ifelse(is.na(x), "", as.character(x))
  x <- iconv(x, to = "ASCII//TRANSLIT")
  x <- tolower(trimws(x))
  gsub("\\s+", " ", x)
}

field_map <- list(
  title = c("title", "document title", "titulo", "título"),
  year = c("year", "publication year", "ano", "coverdate"),
  abstract = c("abstract", "summary", "resumo", "description"),
  keywords = c("keywords", "author keywords", "index keywords", "palavras-chave", "keyword"),
  citations = c("cited by", "citations", "times cited", "citation count", "número de citações"),
  doi = c("doi", "digital object identifier"),
  journal = c("source title", "journal", "periódico", "publication name")
)

pick_col <- function(df, aliases) {
  norm <- setNames(names(df), normalize_text(names(df)))
  for (a in aliases) {
    key <- normalize_text(a)
    if (key %in% names(norm)) return(norm[[key]])
  }
  NULL
}

harmonize <- function(df) {
  out <- data.frame(row.names = seq_len(nrow(df)), stringsAsFactors = FALSE)
  for (target in names(field_map)) {
    col <- pick_col(df, field_map[[target]])
    out[[target]] <- if (!is.null(col)) df[[col]] else ""
  }
  out$title <- as.character(out$title)
  out$abstract <- as.character(out$abstract)
  out$keywords <- as.character(out$keywords)
  out$doi <- tolower(trimws(as.character(out$doi)))
  out$journal <- as.character(out$journal)
  out$year <- suppressWarnings(as.integer(out$year)); out$year[is.na(out$year)] <- 0
  out$citations <- suppressWarnings(as.numeric(out$citations)); out$citations[is.na(out$citations)] <- 0
  out$title_norm <- normalize_text(out$title)
  out$blob_norm <- normalize_text(paste(out$title, out$abstract, out$keywords))
  out
}

contains_any <- function(text, terms) {
  sapply(text, function(t) any(vapply(terms, function(term) grepl(term, t, fixed = TRUE), logical(1))))
}

minmax <- function(x) {
  mn <- min(x, na.rm = TRUE); mx <- max(x, na.rm = TRUE)
  if (mx == mn) return(rep(1, length(x)))
  (x - mn) / (mx - mn)
}


parse_bib <- function(path) {
  txt <- paste(readLines(path, warn = FALSE, encoding = "UTF-8"), collapse = "\n")
  parts <- unlist(strsplit(txt, "@\\w+\\s*\\{"))
  parts <- parts[nzchar(parts)]
  rows <- lapply(parts, function(e) {
    g <- function(field) {
      m <- regexec(paste0(field, "\\s*=\\s*[\"{]([^\"}]+)"), e, ignore.case = TRUE)
      r <- regmatches(e, m)[[1]]
      if (length(r) >= 2) r[2] else ""
    }
    data.frame(
      title = g("title"),
      year = g("year"),
      abstract = g("abstract"),
      keywords = g("keywords"),
      citations = g("citedby"),
      doi = g("doi"),
      journal = ifelse(nzchar(g("journal")), g("journal"), g("booktitle")),
      stringsAsFactors = FALSE
    )
  })
  do.call(rbind, rows)
}

load_input <- function(f) {
  ext <- tolower(tools::file_ext(f))
  if (ext %in% c("csv", "tsv", "txt")) {
    df <- tryCatch(read.csv(f, stringsAsFactors = FALSE), error = function(e) NULL)
    if (is.null(df) || ncol(df) <= 1) {
      df <- read.delim(f, stringsAsFactors = FALSE)
    }
    return(df)
  }
  if (ext %in% c("xlsx", "xls")) return(read_excel(f))
  if (ext == "bib") return(parse_bib(f))
  stop(paste("Formato não suportado:", ext))
}

args <- commandArgs(trailingOnly = TRUE)
if (length(args) < 1) stop("Uso: pipeline.R <payload.json>")
payload <- fromJSON(args[1])
files <- payload$files
plot_dir <- payload$plot_dir
plot_prefix <- payload$plot_url_prefix
params <- payload$params
if (is.null(params)) params <- list()
weights <- params$weights; if (is.null(weights)) weights <- list()
thresholds <- params$thresholds; if (is.null(thresholds)) thresholds <- list()
used_params <- list(
  weights = list(
    c = as.numeric(ifelse(is.null(weights$c), 0.35, weights$c)),
    r = as.numeric(ifelse(is.null(weights$r), 0.20, weights$r)),
    t = as.numeric(ifelse(is.null(weights$t), 0.30, weights$t)),
    a = as.numeric(ifelse(is.null(weights$a), 0.15, weights$a))
  ),
  year_min = as.integer(ifelse(is.null(params$year_min), 1992, params$year_min)),
  year_max = as.integer(ifelse(is.null(params$year_max), 2026, params$year_max)),
  thresholds = list(
    nucleo_a = as.numeric(ifelse(is.null(thresholds$nucleo_a), 70, thresholds$nucleo_a)),
    nucleo_b = as.numeric(ifelse(is.null(thresholds$nucleo_b), 50, thresholds$nucleo_b)),
    periferico = as.numeric(ifelse(is.null(thresholds$periferico), 30, thresholds$periferico))
  )
)

a <- c("flood", "inundacao", "inundação", "enchente", "flooding", "inundation")
b <- c("forecast", "forecasting", "prediction", "previsao", "previsão", "early warning")
c <- c("machine learning", "deep learning", "artificial intelligence", "neural network", "xgboost", "svm", "random forest", "cnn", "rnn", "lstm")
ex <- c("flood insurance", "flood mythology", "flood psychology")
h <- c("rain", "rainfall", "chuva", "streamflow", "vazao", "vazão", "water level", "hydrolog")
g <- c("satellite", "dem", "digital elevation", "remote sensing", "geospatial", "gis")

frames <- lapply(files, function(f) {
  df <- load_input(f)
  harmonize(as.data.frame(df, stringsAsFactors = FALSE))
})
all_df <- do.call(rbind, frames)
raw_records <- nrow(all_df)

no_empty <- all_df[nchar(all_df$doi) > 0, ]
empty <- all_df[nchar(all_df$doi) == 0, ]
dedup_doi <- rbind(no_empty[!duplicated(no_empty$doi), ], empty)
after_doi <- nrow(dedup_doi)
dedup_title <- dedup_doi[!duplicated(dedup_doi$title_norm), ]
after_title <- nrow(dedup_title)

has_flood <- contains_any(dedup_title$blob_norm, a)
has_forecast <- contains_any(dedup_title$blob_norm, b)
has_ai <- contains_any(dedup_title$blob_norm, c)
has_hg <- contains_any(dedup_title$blob_norm, h) | contains_any(dedup_title$blob_norm, g)
excluded <- contains_any(dedup_title$blob_norm, ex)
selected <- dedup_title[has_flood & has_forecast & has_ai & has_hg & !excluded, ]

if (nrow(selected) == 0) {
  result <- list(summary = list(raw_records = raw_records, after_doi = after_doi, after_title = after_title, thematic_selected = 0,
                                core_counts = list("Núcleo A" = 0, "Núcleo B" = 0, "Periférico" = 0, "Descarte" = 0)),
                 top_articles = list(),
                 plot_urls = list(),
                 used_params = used_params)
  cat(toJSON(result, auto_unbox = TRUE, force = TRUE, pretty = FALSE))
  quit(save = "no")
}

cmin <- ifelse(is.null(params$c_min), min(selected$citations, na.rm = TRUE), as.numeric(params$c_min))
cmax <- ifelse(is.null(params$c_max), max(selected$citations, na.rm = TRUE), as.numeric(params$c_max))
if (cmax == cmin) { selected$c_star <- rep(1, nrow(selected)) } else { selected$c_star <- pmax(0, pmin(1, (selected$citations - cmin)/(cmax-cmin))) }
if (used_params$year_max == used_params$year_min) { selected$r_star <- rep(1, nrow(selected)) } else { selected$r_star <- pmax(0, pmin(1, (selected$year - used_params$year_min)/(used_params$year_max-used_params$year_min))) }

selected$t_star <- ifelse(contains_any(normalize_text(selected$title), a) & contains_any(normalize_text(selected$title), b) & contains_any(normalize_text(selected$title), c), 1.0, 0.7)
selected$a_star <- pmax(0.5, pmin(1.0, (ifelse(contains_any(selected$blob_norm, h) & contains_any(selected$blob_norm, g), 1, 0.5) +
  ifelse(contains_any(selected$blob_norm, c), 1, 0.5) +
  ifelse(contains_any(selected$blob_norm, b), 1, 0.5) +
  ifelse(contains_any(selected$blob_norm, c("urban","coastal","river","city","basin","watershed")), 1, 0.5)) / 4))

w <- used_params$weights
selected$score <- w$c * selected$c_star + w$r * selected$r_star + w$t * selected$t_star + w$a * selected$a_star
selected$score100 <- minmax(selected$score) * 100
th <- used_params$thresholds
selected$nucleo <- ifelse(selected$score100 >= th$nucleo_a, "Núcleo A", ifelse(selected$score100 >= th$nucleo_b, "Núcleo B", ifelse(selected$score100 >= th$periferico, "Periférico", "Descarte")))

core_counts <- list("Núcleo A" = sum(selected$nucleo == "Núcleo A"), "Núcleo B" = sum(selected$nucleo == "Núcleo B"), "Periférico" = sum(selected$nucleo == "Periférico"), "Descarte" = sum(selected$nucleo == "Descarte"))

if (!dir.exists(plot_dir)) dir.create(plot_dir, recursive = TRUE)
ts <- as.integer(Sys.time())
core_plot <- file.path(plot_dir, paste0("core_distribution_", ts, ".png"))
score_plot <- file.path(plot_dir, paste0("score_histogram_", ts, ".png"))

p1 <- ggplot(selected, aes(x = nucleo, fill = nucleo)) + geom_bar() + theme_minimal() + labs(title = "Distribuição por Núcleo", x = "Núcleo", y = "Artigos") + theme(legend.position = "none")
ggsave(core_plot, p1, width = 8, height = 4, dpi = 120)

p2 <- ggplot(selected, aes(x = score100)) + geom_histogram(bins = 30, fill = "#0ea5e9", color = "white") + theme_minimal() + labs(title = "Histograma Score100", x = "Score100", y = "Frequência")
ggsave(score_plot, p2, width = 8, height = 4, dpi = 120)

top <- selected[order(-selected$score100), c("title", "year", "citations", "doi", "nucleo", "score100")]
top <- head(top, 50)

top_articles <- lapply(seq_len(nrow(top)), function(i) {
  r <- top[i, ]
  list(title = as.character(r$title), year = as.integer(r$year), citations = as.numeric(r$citations), doi = as.character(r$doi), nucleo = as.character(r$nucleo), score100 = as.numeric(r$score100))
})

result <- list(
  summary = list(raw_records = raw_records, after_doi = after_doi, after_title = after_title, thematic_selected = nrow(selected), core_counts = core_counts),
  top_articles = top_articles,
  plot_urls = list(core_distribution = paste0(plot_prefix, "/", basename(core_plot)), score_histogram = paste0(plot_prefix, "/", basename(score_plot)), generated_with = "R"),
  used_params = used_params
)

cat(toJSON(result, auto_unbox = TRUE, force = TRUE, pretty = FALSE))
