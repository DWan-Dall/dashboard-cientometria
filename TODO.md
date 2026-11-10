# Pendências

## Prioridade alta (integridade científica)

- [ ] **Repetir a reprodução com as 8 exportações originais após a correção do achado 11** (esperado: 11.547
      únicos; a primeira execução real, de 10/11/2026, deu 11.546 e todo o resto conferiu).
- [ ] (feito parcialmente) **Executar a reprodução com as 8 exportações originais** (`CIENTOMETRIA_EXPORTACOES_ORIGINAIS=… pytest
      tests/test_dados_reais.py -v` e `python -m cientometria referencia <pasta>`). Registrar o resultado em
      `docs/AUDITORIA.md` §4, com o SHA-256 de cada arquivo (sem publicar os arquivos).
- [ ] Reverificar a divisão declarada 4.233 (DOI) / 1.065 (título) com as exportações originais.
- [ ] Extrair as decisões metodológicas da sessão Perplexity (Fonte D) e registrá-las em METHODOLOGY.md §7,
      separando decisão do usuário × sugestão da IA e indicando fontes científicas (ou "sem fonte").
- [ ] Registrar as strings de busca e datas efetivamente usadas nas 8 exportações (`docs/log_buscas_template.csv`).
- [ ] Revisar manualmente os pares de `duplicatas_para_revisao.csv` do corpus real e os 27 DOIs com caixa
      diferente; decidir e registrar.
- [ ] Conferir manualmente os artigos do Núcleo A (a triagem é automática).
- [ ] Corrigir o `A_score` corrompido no CSV do repositório `analise-aprofundada-v3` (no próprio repositório,
      pela autora) e regenerar `10_scores/` a partir do XLSX correto.

## Verificações da rodada 2 (10/11/2026)

- [x] Auditoria de segurança da interface/API: 10 achados corrigidos (docs/AUDITORIA.md §5), 38 testes.
- [x] Persistência: concorrência, falhas, integridade, recuperação (§6), 12 testes.
- [x] Docker: build, inicialização com compose, testes dentro do contêiner e fim a fim.
- [x] Bibliometria × saídas originais do R: 12 grupos idênticos via `compat_r` (§7), 20 testes.
- [x] ruff, bandit, pip-audit; CI no GitHub Actions (`.github/workflows/ci.yml`).
- [x] Primeira execução do CI no GitHub: verde (8 jobs, commit `8fc05f9`).
- [x] Rodada 3 de segurança: 6 achados novos (DNS rebinding, proxy reverso, triagem rápida sem validação,
      metadados sem validação, injeção de fórmulas, negação de serviço) corrigidos e testados.
- [x] Validação em caixa-preta antes/depois em 3 versões e no Docker (`docs/SEGURANCA.md` §3).
- [x] Regressão: retrato do processamento (4 modos × 2 cenários), contrato da API, interface no Chromium.
- [ ] Executar `tests/test_comparacao_r.py` e `tests/test_dados_reais.py` em máquina com os dados (não
      rodam no CI porque os dados não são versionados).
- [ ] Revisão de segurança por outra pessoa (este relatório foi produzido por quem também escreveu as correções).
- [ ] Limite de tentativas de senha e de taxa de requisições; fila de execução (riscos residuais em docs/SEGURANCA.md §5).
- [ ] Testar `.htaccess` num Apache real, ou removê-lo se não houver uso previsto com Apache.
- [ ] Definir política de acesso para uso em servidor compartilhado: HTTPS (proxy reverso), credenciais
      fortes, limite de taxa; hoje o modelo é uso local ou atrás de 127.0.0.1.

## Funcionalidades

- [ ] Gravar decisões da revisão de duplicatas pela interface (hoje: CSV com coluna `decisao`).
- [ ] Sankey base × versão da busca (existia no R com networkD3).
- [ ] Co-citação/acoplamento exigem referências: documentar quais exportações as trazem (Scopus CSV "References",
      WoS `CR`) e testar com exportações reais.
- [ ] Importar exportações OpenAlex via API (abstract em índice invertido).
- [ ] Validação externa (`validacao.py`) pela interface, com upload da lista de referências.
- [ ] Fila de execução assíncrona para corpora muito grandes (hoje a requisição HTTP espera o término).
- [x] Autenticação (HTTP Basic) e bloqueio de acesso remoto sem credenciais.

## Infraestrutura

- [x] `docker build` verificado (rodada 2). Se o Docker Hub limitar requisições, use
      `--build-arg IMAGEM_BASE=mirror.gcr.io/library/php:8.3-cli-bookworm`.
- [x] CI (GitHub Actions): testes Python 3.11/3.12, ruff, bandit, pip-audit, `php -l`, arquivos
      congelados, ausência de dados licenciados, build e inicialização do Docker.
- [ ] Hashes nas dependências (`pip-compile --generate-hashes`) para instalação verificável.
- [ ] Mover JavaScript inline das páginas para arquivos estáticos (o CSP já usa nonce; isso simplificaria a política).
- [ ] Remover o aviso de `FutureWarning` do script original só no ambiente de teste (não alterar `referencia/`).
