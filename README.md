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

Para testes e verificações: `pip install -r requirements-dev.txt`.

## Dashboard

```bash
php -d upload_max_filesize=512M -d post_max_size=512M -d max_file_uploads=50 -S 127.0.0.1:8000 router.php
```

Use sempre `router.php`: sem ele, o servidor embutido do PHP serve qualquer arquivo da pasta, inclusive
`projetos/` (exportações licenciadas) e `.git`.

Abra http://localhost:8000. Seções: **Projetos → Importação e diagnóstico → Triagem → Robustez e modos →
Análises bibliométricas → Execuções e comparação → Relatórios**. A página `triagem_rapida.php` faz uma triagem
avulsa, sem projeto. Os projetos ficam em `./projetos` (ou em `$CIENTOMETRIA_PROJETOS`), fora do Git.

Com Docker (R opcional: `--build-arg COM_R=1`; a porta fica só em 127.0.0.1 do host):

```bash
docker compose up --build
```

Se o Docker Hub limitar requisições, use um espelho da imagem base:

```bash
docker build --build-arg IMAGEM_BASE=mirror.gcr.io/library/php:8.3-cli-bookworm -t dashboard-cientometria:local .
```

### Acesso e segurança

Sem configuração, só o próprio computador (loopback) acessa a interface. Para acessar de outra máquina,
defina usuário e senha (HTTP Basic; use HTTPS num proxy reverso):

```bash
export CIENTOMETRIA_USUARIO=pesquisa
```

```bash
export CIENTOMETRIA_SENHA_HASH="$(php -r 'echo password_hash("troque-esta-senha", PASSWORD_DEFAULT);')"
```

Acesse por `localhost`/`127.0.0.1`: outros nomes no cabeçalho `Host` são recusados (proteção contra DNS
rebinding). Para usar um nome de servidor, liste-o em `CIENTOMETRIA_HOSTS` (separados por vírgula) e configure
credenciais. Atrás de proxy reverso a senha é sempre exigida.

Limites por processo (contra negação de serviço): `CIENTOMETRIA_MEMORIA_MAX_MB` (padrão 6144),
`CIENTOMETRIA_TEMPO_MAX_S` (3600), `CIENTOMETRIA_MAX_MB_DESCOMPACTADO` (512 por planilha .xlsx).

Outras variáveis: `CIENTOMETRIA_MAX_MB_ARQUIVO` (padrão 200), `CIENTOMETRIA_MAX_ARQUIVOS` (50),
`CIENTOMETRIA_PROJETOS` (pasta dos projetos), `CIENTOMETRIA_DIR_UPLOAD` (temporários).
`CIENTOMETRIA_PERMITIR_SEM_SENHA=1` só deve ser usado atrás de porta publicada em 127.0.0.1 (como no
docker-compose). Relatório completo de segurança e estabilidade, com evidências: `docs/SEGURANCA.md`.
Validação em caixa-preta de uma instância em execução:

```bash
python scripts/validacao_seguranca.py --base http://127.0.0.1:8000
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

### Exportar e importar execuções (ZIP)

Cada execução pode ser baixada como um ZIP completo (resultados, diagnósticos, bibliometria, redes,
gráficos, relatórios PDF/MD/XLSX e manifesto com o SHA-256 de cada arquivo), com ou sem as exportações
originais das bases (licença!). Importar mostra o inventário antes de qualquer alteração; **restaurar**
recupera os resultados sem recalcular, preservando ID e procedência; **reexecutar** cria uma execução nova
a partir dos arquivos e parâmetros registrados, e só é possível com as exportações de origem.

```bash
python -m cientometria exportar <projeto> <id> [--sem-entradas] [--saida pasta]
python -m cientometria verificar-pacote pacote.zip
python -m cientometria importar-pacote <projeto> pacote.zip
python -m cientometria reexecutar <projeto> <id>
```

Detalhes, formato e garantias: `docs/EXPORTACAO_EXECUCOES.md`.

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

## Testes e verificações

```bash
python -m pytest -q
```

```bash
ruff check cientometria scripts tests && bandit -q -r cientometria && python scripts/verificar_repositorio.py
```

Os testes que dependem de dados não versionados são pulados sem eles. Comparação com os resultados
originais do R (`analise-aprofundada-v3`):

```bash
CIENTOMETRIA_CORPUS_PUBLICADO=…/dados/DB_Cientometria_COMPLETA.csv CIENTOMETRIA_RESULTADOS_R=…/resultados_cientometria python -m pytest tests/test_comparacao_r.py -v
```

`tests/test_equivalencia_original.py` executa os scripts originais e o pacote sobre exportações **sintéticas**
e exige resultados idênticos. Isso prova a equivalência do código, **não** a reprodução do artigo, que exige
as exportações reais.

## Dados

As exportações da Lens, Scopus, IEEE Xplore, SciELO, Web of Science e OpenAlex têm licença das bases e
**não são redistribuídas** aqui. Cada pessoa usa as próprias exportações.
