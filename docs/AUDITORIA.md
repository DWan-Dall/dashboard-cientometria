# Auditoria (Fase 1) — inventário, duplicidades e achados

Data: 10/11/2026 · Branch: `feat/unificacao-cientometria` (a partir de `metodo-validado`, `cde0312`).

Regra aplicada: os números do artigo são **referências históricas a verificar**, não metas. Nenhum
parâmetro foi alterado para aproximar resultados desses números.

## 1. Inventário das fontes

### Fonte A — `DWan-Dall/cientometria` (1 commit, `a54a989`)
| Arquivo | Conteúdo | Destino |
|---|---|---|
| `strings_busca_por_base.md` | Strings EN/PT para Scopus, WoS, OpenAlex, Lens, SciELO, Google Scholar; período 2000–2025; artigos e revisões; bloco costeiro e reforço Brasil/SC | Referenciado em METHODOLOGY.md §1 (protocolo de busca) |
| `checklist_exportacao_por_base.md` | Formatos e campos a exportar por base | Base da ingestão multiformato e de `diagnostico.LIMITACOES` |
| `log_buscas_template.csv` | Cabeçalho do log (Base, String, DataHora, Filtros, Resultados, Arquivo) | `docs/log_buscas_template.csv` |
| `bloc.txt` | Duas strings de rascunho (EN e PT com Brasil/SC) | Citado em METHODOLOGY.md |
| `main.R`, `Relatorio_Cientometria.Rmd` | Roteiro **bibliometrix** (convert2df, mergeDbSources, biblioAnalysis, co-palavra, co-citação, acoplamento, thematicMap) — não faz triagem | Reimplementado em `cientometria/bibliometria.py`; versão R em `R/relatorio_bibliometrix.Rmd` |

### Fonte B — `DWan-Dall/dashboard-cientometria`
| Componente | Situação encontrada | Destino |
|---|---|---|
| `cientometria/` (branch `metodo-validado`) | Pacote com modos original/variante/corrigida, robustez, validação externa, diagnósticos | **Núcleo único** do método; ampliado |
| `referencia/fase2..5.py` | Scripts originais de jan/2026 | Mantidos sem alteração (golden master) |
| `tests/` | 12 testes, incl. equivalência sintética pacote × scripts originais | Mantidos sem alteração + 45 novos |
| `notebooks/replicacao_cientometria.ipynb` | Reexecução dos scripts originais (Colab), conferência ✓/✗, robustez, validação Dias et al. 2025 | Mantido; **sem saídas gravadas** (ver achado 9) |
| `scripts/pipeline.py` | Ponte PHP → pacote | **Corrigido** (achado 1) |
| `scripts/pipeline_legado.py` | Pipeline Python antigo com regras próprias | Mantido como legado; só `load_file` era usado |
| `scripts/pipeline.R` | **Segunda implementação da triagem**, regras diferentes | Desativado (achado 4) |
| `index.php`, `run_pipeline.php` | Página única de upload+triagem | Preservada como `triagem_rapida.php`; nova interface modular |
| `Dockerfile`, `docker-compose.yml` | PHP + Python + R | Atualizados (R opcional, volume de dados) |
| Branches `codex/*` (11) | Já incorporadas em `main` via PRs #1–#11 | Nenhuma ação |

### Fonte C — `DWan-Dall/analise-aprofundada-v3` (1 commit, `71160e1`)
| Arquivo | Conteúdo | Destino |
|---|---|---|
| `cientometria_master.R` (v2.3, 1.005 linhas) | Diagnóstico de colunas, bases, "áreas", periódicos, países, coautoria (3 camadas), palavras-chave e coocorrência, clusters, séries temporais, scores por ano, tecnologias, sobreposição entre bases (matriz, Sankey) | `cientometria/bibliometria.py`, `graficos.py`, `consolidacao.sobreposicao` |
| `dados/DB_Cientometria_COMPLETA.csv` / `_Expandida_ver01.xlsx` | **Corpus publicado** (2.068 linhas, 29/21 colunas) enriquecido depois da triagem (autores, afiliações, `source_database` reconstruída, tecnologias) | Usado **localmente** como referência real de auditoria; **não copiado** para este repositório |
| `resultados_cientometria/` | Saídas do R (CSV/PNG) | Usadas para conferir a migração (§3) |
| `Códigos para Referência/` | Versões anteriores (`main*.R`, `R-de-rodrigo.R`) e resultados antigos; cópia idêntica dos dados (mesmo MD5) | Somente histórico |

### Fonte D — sessão Perplexity
Não acessível nesta sessão (host bloqueado na rede do ambiente). **Pendente**: extrair as decisões
registradas (ver TODO.md). Mesmo quando extraídas, respostas geradas por IA são registradas como
decisões/propostas, não como evidência científica.

## 2. Duplicidades e exclusividades

| Funcionalidade | A | B | C | Decisão |
|---|---|---|---|---|
| Triagem C*/R*/T*/A* | — | Python (pacote) **e** R (`pipeline.R`, regras diferentes) **e** Python legado | consome o resultado | Só o pacote Python |
| Leitura de exportações | bibliometrix | CSV/TSV/XLSX/BIB (BIB quebrado) | CSV consolidado | `ingestao.py` |
| Deduplicação | `mergeDbSources` | DOI→título (pacote); outra no R | `artigo_id` DOI→título | Pacote (triagem) + `consolidacao.id_obra` (análises) |
| Séries temporais, periódicos, países, coautoria, palavras-chave, tecnologias, sobreposição | parcial (bibliometrix) | gráficos simples no R legado | completo (R) | `bibliometria.py` |
| Co-citação, acoplamento, mapa temático | bibliometrix | — | — | `bibliometria.py` + Rmd opcional |
| Robustez, validação externa, diagnósticos | — | pacote | — | pacote |
| Projetos, manifesto, comparação de execuções | — | — | — | novo |

## 3. Achados

### Achado 1 — o modo "original" do dashboard não era o original *(corrigido)*
`scripts/pipeline.py` terminava `montar_config` com `cfg.com(mapeamento_tolerante=True)` para **todos**
os modos, e lia os arquivos na ordem do upload, com leitor diferente (`sep=None`, `utf-8-sig`,
`on_bad_lines="skip"`). Como a deduplicação mantém o primeiro registro, a ordem altera quais citações,
anos e resumos sobrevivem. Evidência (dados sintéticos de `tests/sinteticos.py`):

| Execução | únicos | corpus | A/B/P/D |
|---|---|---|---|
| `Config.original()` (pacote) | 419 | 127 | 3/19/56/49 |
| dashboard "original", upload em ordem alfabética (antes) | 447 | 134 | 1/13/63/57 |
| dashboard "original", ordem invertida (antes) | 446 | 112 | 2/18/45/47 |
| dashboard "original" (depois, qualquer ordem) | 419 | 127 | 3/19/56/49 |

Correção: `ingestao.carregar_fontes` usa a leitura original (`pd.read_csv` padrão) e a ordem canônica das 8
exportações; o mapeamento tolerante só é usado na `corrigida` ou quando pedido explicitamente (execução
"personalizada"). Testes: `tests/test_adaptador_dashboard.py`.

### Achado 2 — o corpus publicado reproduz as fórmulas de escore, com uma corrupção de dados
Verificação interna (`python -m cientometria verificar-corpus`), sem precisar das exportações:
- C* e R* recalculados por min–max: **2.068/2.068** iguais.
- Escore 0–100 recalculado a partir dos componentes publicados: **2.068/2.068** iguais **depois** de
  corrigir A*; com o A* do CSV, só 2/2.068.
- Estrato coerente com o escore e os cortes 70/50/30: **2.068/2.068**; estratos = 13/494/1.508/53.
- **A\* corrompido no CSV**: 641 linhas com `875` e `625` no lugar de `0,875` e `0,625` — típico de abrir/salvar
  em planilha com separador decimal brasileiro (há um `.~lock.DB_Cientometria_COMPLETA.csv#` do LibreOffice no
  repositório C). O XLSX tem os valores corretos. **Quem usar o CSV de C para análises de A\* terá médias
  erradas** (ex.: `10_scores/01-scores-medios-por-ano.csv` do R foi calculado com o CSV corrompido).
- T* e A* recalculados sem palavras-chave (a coluna não está no arquivo publicado): divergem em 38 e 26
  linhas, **sempre** com o publicado maior — consistente com a contribuição das palavras-chave.

Conclusão: as fases 4–5 (escore e estratos) do artigo estão confirmadas nos dados reais publicados. As fases
2–3 (16.845 → 11.547 → 2.068) **não puderam ser verificadas** aqui: exigem as 8 exportações originais.

### Achado 3 — duplicatas no corpus de 2.068
- **27 pares** de DOIs que diferem só na caixa (ex.: `10.1029/2019WR027038` × `10.1029/2019wr027038`), 54 linhas,
  distribuídas em Núcleo B (14), Periférico (34) e Descarte (6). A Lens grava DOIs em minúsculas e a Scopus
  preserva a caixa; o procedimento original compara texto bruto.
- 37 títulos repetidos após remover pontuação (candidatos a revisão humana).
Ação: `normalizar_doi` entra na `corrigida` como **corrigida-2** (versão anterior preservada como
`Config.corrigida_v1()`); pares duvidosos ficam em `diagnosticos/duplicatas_para_revisao.csv`, nunca fundidos
automaticamente. O modo `original` não muda.

### Achado 4 — segunda implementação da triagem em R *(desativada)*
`scripts/pipeline.R` usava outros termos, exigia "tema 1 E tema 2", outro T* e outro A*, e normalizava R* por
intervalo fixo 1992–2026. Era oferecido na interface como "motor". Agora `run_pipeline.php` recusa `engine=r`.

### Achado 5 — "alvos" editáveis na interface *(removidos)*
A página antiga tinha "Reconciliação metodológica (alvos)" com 16.845/12.612/11.547/2.068/13/494/1.508/53
editáveis e mostrava os deltas — desenho que incentiva ajustar parâmetros até coincidir. Viraram referências
somente leitura (teste `test_interface_nao_tem_alvos_editaveis`). O valor "após DOI = 12.612" (= 16.845 − 4.233)
é o declarado no relatório e, segundo o notebook, não corresponde à execução (o total de 5.298 sim).

### Achado 6 — parser BibTeX quebrado no dashboard anterior
`pipeline_legado.parse_bibtex` usava `r'(\\w+)\\s*=...'` (barra dupla em string raw): nenhum campo casava e
cada entrada `.bib` virava registro vazio. Substituído por `ingestao.ler_bibtex` (testado).

### Achado 7 — campos de ano sem efeito
A interface enviava `year_min`/`year_max`, ignorados pelo método (R* usa o intervalo observado). Os campos
foram desabilitados e rotulados como informativos.

### Achado 8 — divergências na migração do R (Fonte C)
- **"Áreas de conhecimento" eram os estratos**: o bloco "2) Áreas" contava a coluna `fascia`. Agora `areas()` usa
  a área temática da base e `estratos()` é separado.
- **Autores separados por vírgula**: parte nomes "Sobrenome, N.". No corpus publicado os nomes vêm "Nome Sobrenome,
  Nome Sobrenome", então a vírgula é o separador correto *ali*; o novo código usa `;` quando existe. Resultado
  conferido: arestas de coautoria **19.628** e **1.582** com peso ≥ 2 (iguais ao R); autores únicos 6.758 × 6.759
  (diferença: ponto final removido de um nome).
- **Anos sem publicação**: `replace_na(value)` sem valor deixava `NA`; agora 0. Contagens por ano iguais ao R.
- **Clusters temáticos**: componentes conexos → Louvain com semente fixa (componentes continuam exportados).
- **Proveniência**: `source_database` do corpus publicado foi reconstruída depois da triagem (no original
  `source_db` fica vazia). Nenhuma obra do corpus veio da SciELO; IEEE aparece em 160 obras, todas também
  presentes em Lens/Scopus — coerente com títulos IEEE perdidos na leitura original.

### Achado 9 — o notebook afirma reprodução, mas não guarda evidência
A síntese do notebook diz que "o procedimento original reproduz exatamente" 16.845 → … → 13/494/1.508/53, mas o
arquivo não tem saídas gravadas. A afirmação pode ser verdadeira, mas não é verificável pelo repositório.
`tests/test_dados_reais.py` transforma essa conferência em teste executável com as exportações originais.

### Achado 10 — protocolo de busca × dados coletados
As strings da Fonte A preveem 2000–2025, artigos e revisões e um bloco costeiro; o corpus tem anos 1992–2026 e
inclui "scopus-sem-filtro" e "scopus-com-filtro" da mesma busca (sobreposição de 1.040 obras). As strings
efetivamente usadas e as datas de exportação não estão registradas (o `log_buscas_template.csv` está vazio).

## 4. O que foi e o que não foi verificado

| Verificação | Situação |
|---|---|
| Pacote × scripts originais, dados sintéticos | ✓ (teste preservado) |
| Dashboard original × pacote original | ✓ (corrigido e testado) |
| Fórmulas C*, R*, escore, estratos no corpus real publicado | ✓ 2.068/2.068 |
| 16.845 → 11.547 → 2.068 com as exportações originais | **não executado** — arquivos indisponíveis aqui; teste pronto (`CIENTOMETRIA_EXPORTACOES_ORIGINAIS`) |
| Divisão 4.233/1.065 | declarado inconsistente pelo notebook; não reverificado |
| Decisões da sessão Perplexity | **pendente** (inacessível) |
| Bibliometria × saídas originais do R (12 grupos de resultados) | ✓ idênticos com a réplica `compat_r`; diferenças do padrão explicadas (§7) |
| Segurança da interface/API (§5) | ✓ 10 achados corrigidos, 38 testes |
| Persistência (§6) | ✓ 3 achados corrigidos, 12 testes |
| Docker | ✓ build, inicialização, testes dentro do contêiner, fim a fim |

## 5. Revisão de segurança (rodada 2, 10/11/2026)

Todos reproduzidos antes da correção; testes em `tests/test_seguranca.py`.

| # | Achado | Evidência | Correção |
|---|---|---|---|
| S1 | `php -S` servia **tudo** do diretório: `projetos/` (exportações licenciadas importadas), `.git`, código | `GET /projetos/<p>/arquivos/<arquivo>.csv` → 200 com o arquivo | `router.php` serve só os 5 pontos de entrada (+ JS empacotado); `.htaccess` para Apache; Docker usa o roteador e `/dados` fora de `/app` |
| S2 | Traversal no identificador do projeto | `{"projeto": "../projetos/sec"}` abria o projeto | regex `^[a-z0-9][a-z0-9-]{0,80}$` + confinamento na raiz; IDs de execução/arquivo validados |
| S3 | API sem CSRF nem verificação de origem | POST `text/plain` com `Origin: evil.example` criava projeto | token CSRF por sessão (cookie HttpOnly, SameSite=Strict), Origin/Referer, só POST |
| S4 | Sem controle de acesso | qualquer host da rede usava a API | sem credenciais, só loopback; HTTP Basic com `CIENTOMETRIA_USUARIO`/`CIENTOMETRIA_SENHA_HASH` (bcrypt/argon via `password_hash`) |
| S5 | **XSS armazenado**: títulos/DOIs de exportações inseridos como HTML na triagem rápida | título `<img src=x onerror=…>` executou JavaScript no commit `b1414c0` (Playwright) | escape em todas as interpolações; CSP `script-src 'nonce-…'` sem handlers inline; `index.php` com delegação de eventos |
| S6 | Uploads e payload da triagem rápida gravados em `tmp_uploads/` dentro do webroot | caminho em `run_pipeline.php` | diretório temporário fora do webroot (0700), removido ao fim |
| S7 | Upload sem validação de conteúdo | binário com extensão `.csv` aceito | extensão, tamanho (`CIENTOMETRIA_MAX_MB_ARQUIVO`), quantidade, bytes nulos, ZIP/OLE válidos, limite de descompactação (zip bomb), sem links simbólicos; importação confinada ao diretório de upload; arquivos importados somente leitura |
| S8 | Chart.js de CDN sem versão nem SRI | `<script src="https://cdn.jsdelivr.net/npm/chart.js">` | empacotado em `vendor/` (4.4.1, MIT) com SRI sha384 |
| S9 | Custo ilimitado: `n_sensibilidade` arbitrário | 10⁹ sorteios aceitos | limite 20.000 |
| S10 | Mensagens de erro com caminhos absolutos | erro do Python devolvido ao navegador | caminhos substituídos por `<…>` |

Verificações automáticas: `bandit` (0 achados em 3.033 linhas), `pip-audit` (2 vulnerabilidades em
dependências de desenvolvimento — pytest 8.4.2 e requests 2.32.5 — atualizadas; árvore completa sem
vulnerabilidades conhecidas), `ruff`.

## 6. Persistência (rodada 2)

| # | Achado | Evidência | Correção |
|---|---|---|---|
| P1 | Importações simultâneas **corrompiam** `arquivos.json` (temporário de nome fixo compartilhado) | 16 processos, commit `b1414c0`: `JSONDecodeError` e falha da importação | trava `fcntl` por projeto; temporário único + `fsync` + `rename`; 80/80 importações registradas |
| P2 | Execução que falhava deixava pasta parcial (sem manifesto) | código | montagem em `.em_andamento_<id>`, renomeação atômica; falhas em `.falhas/<id>/erro.txt` + evento |
| P3 | Nada impedia executar sobre arquivo de entrada alterado | código | SHA-256 reconferido antes de cada execução; cópia somente leitura; manifesto com SHA-256 de cada saída; `verificar_execucao`, `recuperar`, `reconstruir_registro` |

Limite: o processo roda como root em ambientes sem Docker; `chmod 0444` não impede root de alterar
arquivos — a detecção por SHA-256 continua valendo.

## 7. Comparação com os resultados originais do R (rodada 2)

`tests/test_comparacao_r.py` (com `CIENTOMETRIA_CORPUS_PUBLICADO` = CSV lido pelo R e
`CIENTOMETRIA_RESULTADOS_R`). A réplica `cientometria/compat_r.py` reproduz **exatamente**: bases (5),
"áreas" (= estratos), periódicos (724), países (727 nomes, 2.363 afiliações), autores (6.759),
coautoria (19.628 arestas; 1.582 com peso ≥ 2), palavras-chave (31) e coocorrência (203 arestas),
clusters (1 componente), séries de artigos/citações/média por ano (35 anos), scores médios por ano
(140 valores), tecnologias por ano (175 valores) e sobreposição entre bases (matriz e nº de bases).
Para isso foi preciso reproduzir a transliteração ICU `Latin-ASCII` (aspas curvas, travessões,
largura total, "ı" turco; cirílico preservado) e o `str_to_title` do ICU ("Seq2Seq" → "Seq2seq").

Diferenças das funções padrão (`bibliometria.py`), todas intencionais e testadas:

| Análise | R | Padrão | Motivo |
|---|---|---|---|
| Países | conta afiliações (China 364; 727 nomes) | conta documentos por país, nomes unificados (China 145; 333 nomes) | evitar que um artigo com várias afiliações do mesmo país pese mais; "USA" = "United States" |
| Áreas | contagem de `fascia` | área temática da base | rótulo do R estava errado |
| Anos sem publicação | NA | 0 | série contínua |
| Scores por ano | A\* médio até **438** (CSV corrompido) | A\* ≤ 1 (com A\* corrigido) | Achado 2 |
| Tecnologias | menções repetidas no mesmo registro contam | únicas por registro | diferença < 1% (totais iguais neste corpus) |
| Autores únicos | 6.759 | 6.758 | ponto final removido de um nome |

**Não comparáveis:** co-citação e acoplamento (o corpus publicado não tem referências citadas e o R não os
calculou); áreas temáticas (sem coluna de área). Exigem exportações com `References`/`CR`.
