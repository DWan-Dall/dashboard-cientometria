# dashboard-cientometria

Triagem cientométrica **replicável** para revisões sobre previsão de enchentes com IA/ML: pacote Python (`cientometria`), dashboard (PHP) e notebook de replicação.

> **Aviso metodológico.** A triagem é automática (casamento de termos + escore ponderado). **Não há revisão manual registro a registro**, então não existe concordância entre revisores. Os escores 0–100 são *relativos ao corpus* (min–max): o "100" não é qualidade absoluta, e o rótulo "Núcleo A" (corte fixo em 70) depende da composição do corpus. A posição no ranking é mais estável que o rótulo. Os artigos do estrato mais alto devem ser conferidos manualmente.

## Três modos (mesmo código, decisões explícitas)

| Modo | O que faz | Para que serve |
|---|---|---|
| `original` | Reproduz exatamente o procedimento de jan/2026 (scripts em `referencia/`), inclusive suas falhas | Replicar e auditar os números do capítulo |
| `variante_exclusao` | Muda **somente** a exclusão `dam/dike/levee` (de trecho de texto para palavra inteira) | Medir quanto o resultado depende dessa decisão |
| `corrigida` | Corrige também a leitura de colunas (IEEE/SciELO/Scopus) e mantém registros sem DOI | Uso futuro; **muda os números** |

Não se escolhe o modo para "chegar" a um resultado esperado: o objetivo é mostrar a diferença entre eles.

## Falhas do procedimento original (documentadas e testáveis)
1. A coluna de base de origem (`source_db`) fica vazia (atribuição de escalar a um DataFrame vazio); o mesmo ocorre com campos cuja coluna não existe no arquivo.
2. A etapa de DOI descarta todos os registros sem DOI (não é deduplicação).
3. Os termos de exclusão são testados por trecho de texto: `dam` casa com *damage*.
4. Colunas inexistentes (IEEE: título/palavras-chave; SciELO-EN; Scopus: `Keywords`) são ignoradas em silêncio.
5. Termos curtos (`dem`, `gis`, `rnn`, `cnn`) também casam dentro de outras palavras.

`cientometria.diagnostico` torna essas falhas visíveis para os seus dados.

## Uso rápido (Python)

```python
from cientometria import Config, executar, ler_pasta, robustez, diagnostico

bases = ler_pasta("minhas_exportacoes/")        # os 8 CSVs (ver cientometria/entrada.py)
orig = executar(bases, Config.original())
print(orig.contagens, orig.estratos())

var = executar(bases, Config.variante_exclusao())
print(robustez.tabela_referencia(orig, var))      # onde ficam os artigos do Núcleo A original
print(robustez.sensibilidade_pesos(orig, n=10000, seed=42))
print(diagnostico.exclusao_por_trecho(orig))
```

Validação externa (referências de uma revisão independente): `cientometria.validacao.validar_referencias` (exemplo: `exemplos/referencias_dias2025.csv`).

## Testes

```bash
pip install -r requirements.txt
pytest -q
```

`tests/test_equivalencia_original.py` executa os scripts originais (`referencia/fase2..5`) e o pacote sobre as mesmas exportações **sintéticas** e exige resultados idênticos. Com seus dados reais, rode o notebook (`notebooks/replicacao_cientometria.ipynb`), que compara cada número com o declarado no relatório original (✓/✗).

## Dados
As exportações da Lens, Scopus, IEEE Xplore e SciELO têm licença das bases e **não são redistribuídas** aqui. Cada pessoa usa as próprias exportações.

## Dashboard (PHP)

O motor **Python** usa o pacote `cientometria` (modos original/variante/corrigida, listas de termos validadas por padrão, diagnósticos e sensibilidade aos pesos no painel de parâmetros). O motor **R** (`scripts/pipeline.R`) é **legado** e não implementa o método validado; o Python anterior está em `scripts/pipeline_legado.py`.

Funcionalidades (descrição anterior à versão validada; as regras de filtro e escore agora seguem o pacote):

- Upload de múltiplas planilhas (`.csv`, `.tsv`, `.txt`, `.xlsx`, `.bib`) de fontes como Scopus, Lens e similares.
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
php -d upload_max_filesize=128M -d post_max_size=128M -d max_file_uploads=100 -S localhost:8000
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
- Para arquivos Scopus muito grandes, mantenha `post_max_size` e `upload_max_filesize` em pelo menos `128M`.
