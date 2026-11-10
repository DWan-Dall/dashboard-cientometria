# Pendências

## Prioridade alta (integridade científica)

- [ ] **Executar a reprodução com as 8 exportações originais** (`CIENTOMETRIA_EXPORTACOES_ORIGINAIS=… pytest
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

## Funcionalidades

- [ ] Gravar decisões da revisão de duplicatas pela interface (hoje: CSV com coluna `decisao`).
- [ ] Sankey base × versão da busca (existia no R com networkD3).
- [ ] Co-citação/acoplamento exigem referências: documentar quais exportações as trazem (Scopus CSV "References",
      WoS `CR`) e testar com exportações reais.
- [ ] Importar exportações OpenAlex via API (abstract em índice invertido).
- [ ] Validação externa (`validacao.py`) pela interface, com upload da lista de referências.
- [ ] Fila de execução assíncrona para corpora muito grandes (hoje a requisição HTTP espera o término).
- [ ] Autenticação, se o dashboard for exposto fora de `localhost`.

## Infraestrutura

- [ ] Verificar `docker build` (não havia daemon Docker no ambiente desta implementação).
- [ ] CI (GitHub Actions) rodando `pytest` e `php -l`.
- [ ] Remover o aviso de `FutureWarning` do script original só no ambiente de teste (não alterar `referencia/`).
