# dashboard-cientometria — plataforma de cientometria reproduzível

Importe exportações de várias bases bibliográficas, aplique o método de triagem documentado no artigo
(escore composto C\*, R\*, T\*, A\*), meça a robustez do resultado, rode análises bibliométricas e gere
relatórios reproduzíveis — sem depender dos notebooks originais.

> **Aviso metodológico.** A triagem é automática (casamento de termos + escore ponderado). **Não há revisão
> manual registro a registro**, então não existe concordância entre revisores. Os escores 0–100 são *relativos
> ao corpus* (min–max): o "100" não é qualidade absoluta, e o rótulo "Núcleo A" (corte fixo em 70) depende da
> composição do corpus. A posição no ranking é mais estável que o rótulo. Os artigos do estrato mais alto
> devem ser conferidos manualmente.

| Documento | Conteúdo |
|---|---|
| [METHODOLOGY.md](METHODOLOGY.md) | o método, os modos e as versões |
| [ARCHITECTURE.md](ARCHITECTURE.md) | módulos e decisões arquiteturais |
| [MIGRATION.md](MIGRATION.md) | origem e destino de cada componente dos três repositórios |
| [docs/AUDITORIA.md](docs/AUDITORIA.md) | inventário, duplicidades e achados da auditoria |
| [TODO.md](TODO.md) | pendências |

## Três modos (mesmo código, decisões explícitas)

| Modo | Versão | O que faz | Para que serve |
|---|---|---|---|
| `original` | `original-2026.01` | Reproduz o procedimento de jan/2026 (`referencia/`), inclusive suas falhas | Replicar e auditar o artigo |
| `variante_exclusao` | `variante-1` | Muda **só** a exclusão `dam/dike/levee` (trecho → palavra inteira) | Medir quanto o resultado depende dessa decisão |
| `corrigida` | `corrigida-2` | Corrige leitura de colunas, mantém registros sem DOI e normaliza DOI | Uso futuro; **muda os números** |

Não se escolhe o modo para "chegar" a um resultado esperado: o objetivo é mostrar a diferença entre eles.
Os números do artigo (16.845 → 11.547 → 2.068 → 13/494/1.508/53) são **referências históricas a verificar**,
não metas.

## Instalação

```bash
pip install -r requirements.txt
```

## Dashboard

```bash
php -d upload_max_filesize=256M -d post_max_size=256M -d max_file_uploads=100 -S localhost:8000
```

Abra http://localhost:8000. Seções: **Projetos → Importação e diagnóstico → Triagem → Robustez e modos →
Análises bibliométricas → Execuções e comparação → Relatórios**. A página `triagem_rapida.php` faz uma triagem
avulsa, sem projeto. Os projetos ficam em `./projetos` (ou em `$CIENTOMETRIA_PROJETOS`), fora do Git.

Com Docker (R opcional: `--build-arg COM_R=1`):

```bash
docker compose up --build
```

## Linha de comando (sem dashboard)

```bash
python -m cientometria projeto-criar "Revisão enchentes"
```

```bash
python -m cientometria importar revisao-enchentes exportacoes/*.csv exportacoes/*.ris
```

```bash
python -m cientometria diagnosticar revisao-enchentes --modo original
```

```bash
python -m cientometria executar revisao-enchentes --modo original --rotulo "réplica do artigo"
```

```bash
python -m cientometria execucoes revisao-enchentes
```

```bash
python -m cientometria comparar revisao-enchentes <id_a> <id_b>
```

```bash
python -m cientometria reproduzir revisao-enchentes <id>
```

Cada execução cria `projetos/<projeto>/execucoes/<data>_<id>/` com `manifesto.json`, `corpus.csv`,
`consolidado.csv`, `diagnosticos/` (campos ausentes, limitações, duplicatas para revisão), `bibliometria/`,
`graficos/` (PNG 300 dpi) e `relatorios/` (CSV, XLSX, PDF, relatório metodológico em Markdown, parâmetros).

## Uso como biblioteca

```python
from cientometria import Config, executar, carregar_fontes
from cientometria import robustez, diagnostico

bases, fontes = carregar_fontes(["lens-export.csv", "scopus-sem-filtro.csv"], Config.original())
orig = executar(bases, Config.original())
print(orig.contagens, orig.estratos())
print(robustez.sensibilidade_pesos(orig, n=10000, seed=42))
print(diagnostico.exclusao_por_trecho(orig))
```

Formatos aceitos: CSV, TSV, TXT, XLSX, RIS, BibTeX e Web of Science (texto). Bases reconhecidas pelas colunas:
Scopus, Web of Science, Lens, IEEE Xplore, SciELO, OpenAlex; outras usam o mapeamento genérico.

## Reproduzir o artigo

1. Coloque as 8 exportações originais numa pasta, com os nomes `lens-export.csv`, `lens-export-port.csv`,
   `scopus-sem-filtro.csv`, `scopus-com-filtro.csv`, `scopus-port.csv`, `ieee-export.csv`, `SciELO.csv`,
   `SciELO-port.csv`.
2. Compare com as referências históricas nos três modos:

```bash
python -m cientometria referencia /caminho/da/pasta
```

3. Rode os testes com dados reais (equivalência pacote × scripts originais e números históricos):

```bash
CIENTOMETRIA_EXPORTACOES_ORIGINAIS=/caminho/da/pasta python -m pytest tests/test_dados_reais.py -v
```

Divergência é achado a investigar e documentar em `docs/AUDITORIA.md`, nunca motivo para mudar o método.
O corpus publicado (2.068 registros) pode ser conferido sem as exportações:

```bash
python -m cientometria verificar-corpus DB_Cientometria_Expandida_ver01.xlsx
```

## Testes

```bash
python -m pytest -q
```

`tests/test_equivalencia_original.py` executa os scripts originais e o pacote sobre exportações **sintéticas**
e exige resultados idênticos. Isso prova a equivalência do código, **não** a reprodução do artigo, que exige
as exportações reais.

## Dados

As exportações da Lens, Scopus, IEEE Xplore, SciELO, Web of Science e OpenAlex têm licença das bases e
**não são redistribuídas** aqui. Cada pessoa usa as próprias exportações.
