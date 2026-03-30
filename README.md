# dashboard-cientometria

Dashboard interativo (PHP + Python/R) para apoiar revisões sistemáticas com foco em cientometria de enchentes e IA/ML.

## Funcionalidades

- Upload de múltiplas planilhas (`.csv`, `.xlsx`) de fontes como Scopus, Lens e similares.
- Seleção do motor de processamento: **Python** ou **R** diretamente na interface.
- Normalização de campos-chave: título, ano, resumo, palavras-chave, citações, DOI e periódico.
- Deduplicação em 2 estágios:
  1. por DOI;
  2. por título normalizado (case-insensitive).
- Filtro temático conjuntivo (AND), exigindo:
  - enchentes/inundações + previsão,
  - termos de IA/ML,
  - contexto de dados hidrológicos ou geoespaciais,
  - exclusão de tópicos marginais (insurance/mythology/psychology).
- Cálculo de escore composto:
  - `Score = 0.35*C* + 0.20*R* + 0.30*T* + 0.15*A*`
- Normalização final para escala `0–100` e classificação em núcleos:
  - Núcleo A (>=70)
  - Núcleo B (50–69.99)
  - Periférico (30–49.99)
  - Descarte (<30)
- Visualização com KPIs, gráfico de distribuição e tabela dos artigos com maior score.
- Quando o motor **R** é usado, o pipeline também gera gráficos PNG (ggplot2) servidos no localhost.

## Estrutura

- `index.php`: interface web interativa.
- `run_pipeline.php`: endpoint de upload e execução do pipeline (Python ou R).
- `scripts/pipeline.py`: pipeline em Python.
- `scripts/pipeline.R`: pipeline equivalente em R + geração de gráficos.
- `Dockerfile`: imagem única com PHP + Python + R.
- `docker-compose.yml`: execução local com container.

## Como executar (local)

Pré-requisitos:

- PHP 8+
- Python 3.10+
- R 4.2+
- Pacotes Python: `pandas`, `openpyxl`
- Pacotes R: `jsonlite`, `readxl`, `ggplot2`

Instalação de dependências Python:

```bash
pip install -r requirements.txt
```

Instalação de dependências R:

```r
install.packages(c("jsonlite", "readxl", "ggplot2"), repos = "https://cloud.r-project.org")
```

Iniciar aplicação:

```bash
php -S localhost:8000
```

Acesse:

- http://localhost:8000

## Como executar com Docker

Build da imagem:

```bash
docker build -t dashboard-cientometria .
```

Executar container:

```bash
docker run --rm -p 8000:8000 dashboard-cientometria
```

Ou com Docker Compose:

```bash
docker compose up --build
```

Acesse:

- http://localhost:8000

> Nota Docker: a imagem usa `venv` interno (`/opt/venv`) para instalar dependências Python, evitando o erro de PEP 668.

## Observações

- O mapeamento de colunas usa aliases comuns entre bases. Você pode ajustar os aliases em `FIELD_MAP` (Python) ou `field_map` (R).
- Os gráficos gerados em R são salvos em `tmp_uploads/plots/` para visualização no navegador.
