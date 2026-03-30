# dashboard-cientometria

Dashboard interativo (PHP + Python) para apoiar revisões sistemáticas com foco em cientometria de enchentes e IA/ML.

## Funcionalidades

- Upload de múltiplas planilhas (`.csv`, `.xlsx`) de fontes como Scopus, Lens e similares.
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

## Estrutura

- `index.php`: interface web interativa.
- `run_pipeline.php`: endpoint de upload e execução do pipeline.
- `scripts/pipeline.py`: pipeline de normalização, deduplicação, filtragem e scoring.

## Como executar

Pré-requisitos:

- PHP 8+
- Python 3.10+
- Pacotes Python: `pandas`, `openpyxl`

Instalação de dependências Python:

```bash
pip install pandas openpyxl
```

Iniciar aplicação:

```bash
php -S localhost:8000
```

Acesse:

- http://localhost:8000

## Observações

- O mapeamento de colunas usa aliases comuns entre bases. Você pode ajustar os aliases em `FIELD_MAP` no arquivo `scripts/pipeline.py`.
- O pipeline foi desenhado para priorizar robustez em dados heterogêneos e pode ser refinado com regras extras de matching fuzzy para títulos, se necessário.
