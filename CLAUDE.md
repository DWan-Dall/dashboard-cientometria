# CLAUDE.md — instruções para agentes neste repositório

## Regras de integridade científica (obrigatórias)

- O pacote Python `cientometria` é a **única** implementação da triagem. Não implemente filtros, escores,
  deduplicação ou estratos em PHP, JavaScript ou R. PHP/JS só repassam e exibem.
- **Nunca** ajuste parâmetros, termos, leitura ou código para que os resultados coincidam com os números do
  artigo (16.845 → 11.547 → 2.068 → 13/494/1.508/53). São referências históricas a verificar. Divergência é
  achado: investigue e documente em `docs/AUDITORIA.md`.
- O modo `original` (`original-2026.01`) é congelado. Não altere `referencia/`, `entrada.MAPEAMENTO_ORIGINAL`,
  `termos.py`, `nucleo.py` ou o comportamento de `pipeline.consolidar` quando as opções novas estão desligadas.
  `tests/test_equivalencia_original.py` protege isso e deve continuar passando sem alterações.
- Mudança que altera números = nova versão em `cientometria/versao.py` (data, descrição, justificativa) +
  teste + METHODOLOGY.md §3. Preserve a versão anterior como receita comparável (ex.: `Config.corrigida_v1`).
- Não versione dados licenciados (exportações das bases, corpus derivado delas). Testes com dados reais usam
  variáveis de ambiente (`tests/test_dados_reais.py`).
- Testes sintéticos não comprovam a reprodução do artigo; diga isso ao relatar resultados.
- Interface: nada de "metas"/"alvos" editáveis com os números do artigo.
- `docs/congelados.sha256` lista os arquivos do modo original; o CI falha se mudarem.

## Regras de segurança

- Todo endpoint PHP inclui `seguranca.php`: POST com `seg_exigir_post_protegido()` (acesso, origem, CSRF),
  páginas com `seg_pagina()`. Scripts só com `nonce`; nada de `onclick=`/`innerHTML` com dado não escapado.
- Uploads só por `seg_receber_uploads()` em diretório temporário fora do webroot; o Python revalida
  (`ingestao.validar_conteudo`) e confina a importação (`CIENTOMETRIA_DIR_IMPORTACAO`).
- Identificadores vindos da web (projeto, execução, arquivo) sempre validados por regex em `projetos.py`.
- Alterações em metadados de projeto sempre sob `_trava()`; JSON com `_json()` (atômico).

## Comandos

```bash
python -m pytest -q                       # suíte completa (~45 s)
php -S 127.0.0.1:8000 router.php          # dashboard (sempre com router.php)
python -m cientometria --help             # CLI
for f in *.php; do php -l $f; done        # lint PHP
ruff check cientometria scripts tests     # lint Python
bandit -q -r cientometria                 # análise de segurança
python scripts/verificar_repositorio.py   # arquivos congelados + ausência de dados licenciados
```

## Mapa rápido

- Triagem: `config.py`, `termos.py`, `entrada.py`, `pipeline.py`, `nucleo.py`.
- Entrada de arquivos: `ingestao.py` (formatos, tipo de base, ordem canônica, leitura original).
- Interface ↔ pacote: `parametros.py` (JSON → Config), `saida.py`, `api.py`.
- Projetos/execuções: `projetos.py`, `manifesto.py`, `relatorios.py`, `graficos.py`.
- Análises: `bibliometria.py` (descritivas; não alteram a triagem).
- Auditoria: `auditoria.py`, `diagnostico.py`, `robustez.py`, `validacao.py`, `docs/AUDITORIA.md`.

## Convenções

Código, comentários e documentação em português. Funções puras no núcleo; efeitos (disco) em `projetos.py`.
Commits pequenos, sem reescrever histórico.
