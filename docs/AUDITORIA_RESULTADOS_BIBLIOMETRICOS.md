# Auditoria dos resultados — execução `052b2a400fc1`

Data da auditoria: 11/11/2026 · Código de referência: branch `feat/unificacao-cientometria` (`2e32d75`) ·
Execução auditada: aplicação **0.2.0**, modo **original**, método **original-2026.01**, 11/11/2026 12:04 UTC.

Escopo: auditar os resultados **sem alterar o método nem os arquivos de resultado**. Nenhum arquivo recebido
foi modificado; nenhuma exportação licenciada foi versionada. Defeitos confirmados foram registrados como
testes (`tests/test_auditoria_resultados.py`), não corrigidos.

## 1. Resumo executivo

| Bloco | Conclusão | Base |
|---|---|---|
| **Proveniência** | ✅ Os arquivos pertencem à execução `052b2a400fc1` | hash do corpus recalculado = `0bea8b65…` registrado; PDF e relatório citam a execução; 30 abas do XLSX idênticas aos 30 CSVs |
| **Triagem** (corpus, escores, estratos, Núcleo A) | ✅ **Consistente** | C\*, R\*, escore e estrato recalculados conferem nos 2.068 registros; contagens fecham; Núcleo A = subconjunto do corpus |
| **Indicadores bibliométricos** | ⚠️ **Parcialmente consistentes** | os cálculos conferem com os dados que receberam, mas autores, coautoria, instituições e países cobrem só **463–464 de 2.068 documentos (22%)**, as "áreas" são rótulos automáticos da Lens/MAG, a co-citação mistura identificadores e há falsos positivos em tecnologias |
| **Corpus como lista de leitura** | ⚠️ Requer revisão | contém ≈181 preprints/discussões, 30 pareceres/comentários e 91 pares de prováveis duplicatas (17 nos Núcleos A+B) — herdados do procedimento original |

Conclusão geral: os resultados da **triagem são consistentes e reproduzíveis**; os **indicadores
bibliométricos são parcialmente consistentes** — corretos aritmeticamente, mas vários não representam o corpus
inteiro e não devem ser publicados como tal sem as ressalvas e correções da §10.

Observação de versão: a execução usou a aplicação 0.2.0, anterior à correção do achado 11 de `docs/AUDITORIA.md`
(11.546 únicos em vez de 11.547, por fundir dois tipos de título ausente). O efeito é 1 registro antes da
triagem temática; o corpus de 2.068 e os estratos não mudaram.

## 2. Inventário dos arquivos analisados

Recebidos num pacote `.7z` (SHA-256 `9e300aa2…9278496`), extraído em diretório isolado; SHA-256 de cada arquivo
em `docs/evidencias/auditoria_052b2a400fc1/sha256_arquivos_recebidos.txt`.

| Grupo | Arquivos | Linhas |
|---|---|---|
| Triagem | `corpus.csv` (2.068), `contagens.csv`, `estratos.csv`, `nucleo_a.csv` (13), `parametros.json`, `relatorio_metodologico.md`, `relatorio.pdf` (20 p., 17 gráficos), `resultados.xlsx` (30 abas) | — |
| Indicadores | `bib_producao_anual` (35), `bib_periodicos` (629), `bib_paises` (67), `bib_instituicoes` (804), `bib_estratos` (4), `bib_areas` (1.668), `bib_autores_resumo`, `bib_autores_frequencia` (1.899) | |
| Redes | `bib_coautoria_*` (1.888 nós, 4.754 arestas), `bib_coocorrencia_*` (4.795 termos, 7.864 arestas, 8 clusters), `bib_cocitacao_*` (33.198 refs, 17.097 arestas), `bib_acoplamento_arestas` (72.231) | |
| Tecnologias e cobertura | `bib_tecnologias_*`, `bib_sobreposicao_*`, `bib_cobertura`, `bib_scores_por_ano` | |
| Duplicado | `bib_tecnologias_percentual_por_ano(1).csv` | cópia byte a byte (download repetido do navegador) |

**Não recebidos** (limitam a auditoria): `manifesto.json` (SHA-256 de cada saída), `consolidado.csv`,
`diagnosticos/`, `bibliometria/`, `graficos/` da pasta da execução e as **8 exportações de entrada**. Sem as
exportações não é possível refazer autores, afiliações, áreas, palavras-chave e referências a partir da fonte
— apenas verificar a coerência interna (§9).

## 3. Metodologia de verificação

1. **Proveniência**: recalcular `hash_tabela` do corpus exportado (reordenado por arquivo/linha de origem,
   escore bruto recomposto pelos pesos de `parametros.json`) e comparar com o hash do relatório.
2. **Recomputação independente** de cada indicador a partir do `corpus.csv` ou do CSV de origem (somas,
   fórmulas, grafos com networkx, centralidade/densidade de Callon, denominadores).
3. **Testes de invariantes** automatizados (Parte A de `tests/test_auditoria_resultados.py`).
4. **Investigação de causa** de cada anomalia, com exemplos do próprio corpus.
5. **Gráficos**: regeneração de todos os 17 a partir dos CSVs com as funções da plataforma, comparação com as
   imagens extraídas do PDF e **inspeção visual**; um controle negativo mostrou que a diferença de pixels sozinha
   é fraca como prova (alterar 2024 de 405 para 200 mudou o erro médio só de 0,0127 para 0,0155), por isso a
   conclusão sobre gráficos se apoia na inspeção dos valores.
6. **PDF × CSV/MD**: texto extraído das 20 páginas; todos os 233 números do relatório metodológico estão no PDF.

## 4. Resultados por análise

| # | Análise | Verificação | Resultado |
|---|---|---|---|
| 1 | Corpus como origem | hash, 2.068 linhas, `contagens.corpus` | ✅ origem efetiva de todas as análises **exceto** a sobreposição entre bases (usa os 16.845 registros brutos) |
| 2a | Produção anual | n e citações por ano recalculados | ✅ confere; 9 documentos sem ano ficam fora (2.059 + 9 = 2.068) |
| 2b | Periódicos | contagem e Bradford recalculados | ✅ confere; 493 documentos sem periódico (418 Lens, 74 Scopus, 1 Lens PT) ficam fora (1.575 + 493 = 2.068); zonas com 518/533/524 documentos |
| 2c | Países / instituições | origem e cobertura | ⚠️ só afiliações de registros Scopus (≈464 documentos); 677 pares documento–país, 1.178 documento–instituição |
| 2d | Autores | cobertura | ⚠️ 463 documentos com autor ≈ 464 de origem Scopus; **nenhum** dos 1.604 de origem Lens |
| 2e | Estratos | bib × corpus × estratos.csv | ✅ 13/494/1.508/53 |
| 3 | Ausentes / duplicados | nulos, DOI, títulos | ⚠️ 9 sem ano; 27 DOIs duplicados só na caixa; 37 títulos iguais após pontuação; 181 preprints/discussões; 30 pareceres/comentários |
| 4a | Coautoria | grau, força, componentes, Louvain | ✅ grau/força/333 componentes/densidade conferem; ⚠️ nó espúrio `null` (grau 5) |
| 4b | Coocorrência | freq ≥ 3, peso ≥ 2, peso ≤ min(freq) | ✅ confere; 614 termos, 1 componente |
| 4c | Co-citação | top 300, peso ≤ min(freq) | ✅ aritmética; ⚠️ 29.490 IDs Lens + 3.708 textos livres; "referência" `undefined` em 30 documentos |
| 4d | Acoplamento | auto-laços, identificadores | ⚠️ 2 auto-laços e 12 títulos colidindo (identificador = 80 primeiros caracteres) |
| 5 | Clusters e mapa temático | centralidade/densidade recalculadas | ✅ valores exatos; ⚠️ modularidade 0,158 e quadrantes degenerados (§5) |
| 6 | Tecnologias | multiplicidade e denominadores | ✅ múltiplas por documento (4.772 pares para 2.068 documentos) é legítimo; percentual = menções/menções do ano; ⚠️ falsos positivos (`attention`, `ensemble`) e 0% em anos sem menção |
| 7 | Sobreposição entre bases | matriz, diagonal, n_bases | ✅ simétrica, traço = Σ n_bases·n_obras = 16.823; ⚠️ definição diferente da deduplicação da triagem (§5) |
| 8 | Escores por ano | médias recalculadas | ✅ confere (26 anos com documento; os 9 sem ano ficam fora) |
| 9 | Gráficos | regeneração + inspeção | ✅ 17 gráficos correspondem aos CSVs; ⚠️ layout das redes não reproduzível entre versões de bibliotecas (co-citação: mesmos nós, posições diferentes) |
| 10 | PDF × exportações | texto, números, hash | ✅ mesmos números do relatório metodológico; mesma execução e hash |

### 4.1 Rastreabilidade (função → CSV)

Fluxo comum: `projetos.Projeto.executar` → `pipeline.executar` (triagem) → `Projeto._estendido` liga cada
registro do corpus à linha da exportação de onde veio (`arquivo_origem`, `linha_origem`) e lê os campos
bibliográficos com `entrada.normalizar_estendido` (aliases tolerantes) → `bibliometria.analisar` →
`relatorios.exportar` grava `relatorios/csv/*.csv` e `resultados.xlsx` (relatório: CSVs com prefixo `'` em textos
que começam com `= + - @`; XLSX sem fórmulas).

| CSV | Função | Campos usados | Transformações | Parâmetros | Denominador / unidade |
|---|---|---|---|---|---|
| `corpus`, `nucleo_a`, `estratos`, `contagens` | `pipeline.executar`, `nucleo.calcular_escore`, `Resultado.estratos` | title, abstract, keywords, year, citations, doi | filtros por trecho, min–max, cortes | pesos, cortes, listas de termos (`parametros.json`) | 2.068 documentos; contagens = registros em cada etapa |
| `bib_producao_anual` | `producao_anual` | year, citations | anos completados com 0; crescimento vs ano anterior | — | documentos **com ano** (2.059) |
| `bib_periodicos` | `periodicos` | source | espaços normalizados, `title()`; Bradford por terços acumulados | — | documentos **com periódico** (1.575) |
| `bib_paises` | `paises` | countries (se houver) ou affiliations | último segmento da afiliação; aliases de país; 1 vez por documento | — | pares documento–país; documentos com afiliação (≈464) |
| `bib_instituicoes` | `instituicoes` | affiliations | segmento com "Univ/Institut…" | — | pares documento–instituição |
| `bib_areas` | `areas` | subject_area ← `Fields of Study` (Lens) | divisão por `;` | — | pares documento–área (20.715) |
| `bib_estratos` | `estratos` | fascia | contagem | cortes | 2.068 |
| `bib_autores_*` | `autores` | authors | separador `;` se existir, senão `,`; únicos por documento | — | autores distintos; documentos com autor (463) |
| `bib_coautoria_*` | `coautoria` | authors | pares por documento; Louvain; intermediação no top 60 | semente 123, `top_nos=60` | arestas = pares de coautores; peso = nº de documentos |
| `bib_coocorrencia_*` | `coocorrencia` | author_keywords → keywords → index_keywords (1º disponível) | caixa baixa; termos com freq ≥ 3; arestas peso ≥ 2; Louvain; Callon simplificado | `min_freq=3`, `min_peso=2`, semente 123 | peso = documentos com o par |
| `bib_cocitacao_*` | `cocitacao` | references | DOI extraído se houver, senão texto (120 car.) ou ID Lens; top 300 refs citadas ≥ 2 | `min_citacoes=2`, `max_refs=300` | peso = documentos que citam o par |
| `bib_acoplamento_arestas` | `acoplamento` | references, title | índice invertido referência → documentos; documento = título[:80] | `min_compartilhadas=1`, `max_docs_por_ref=200` | peso = referências em comum |
| `bib_tecnologias_*` | `tecnologias`, `detectar_tecnologias` | technologies, ou regex sobre title+abstract+keywords | dicionário `TECNOLOGIAS`; categoria por `categoria_tecnologia` | dicionário | frequência = documentos; por ano = menções; % = menções da categoria / menções do ano |
| `bib_scores_por_ano` | `scores_por_ano` | year, C/R/T/A, score_final_100 | média por ano | — | documentos com ano por ano |
| `bib_sobreposicao_*` | `consolidacao.sobreposicao` | **bruto** (16.845 registros): source_db, doi, title | `id_obra` = DOI normalizado ou título simplificado; presença por base | — | obras distintas (12.486); **não** é o corpus |
| `bib_cobertura` | `analisar` | — | "sim/não" por análise | — | não informa cobertura (AR-06) |

**Reprodutibilidade:** com as mesmas exportações, a mesma versão e as mesmas bibliotecas, todas as tabelas são
determinísticas (sementes fixas: Louvain 123, sensibilidade 42). Com versões diferentes de numpy/networkx, os
**layouts** das redes mudam (AR-15); os valores, não. A partir só dos arquivos entregues é possível reproduzir
corpus, escores, estratos, produção anual, periódicos, escores por ano, mapa temático e percentuais de tecnologia;
autores, afiliações, áreas, palavras-chave e referências exigem as exportações.

## 5. Inconsistências encontradas (com classificação)

### 5.1 Pontos levantados pela pesquisadora

| Ponto | Origem determinada | Classificação |
|---|---|---|
| Produção anual soma 2.059 ≠ 2.068 | 9 documentos sem ano (todos de origem Lens EN). A série anual só conta documentos com ano, mas não informa os excluídos | **Característica legítima dos dados** + problema de interpretação (falta a linha "sem ano") |
| Sobreposição soma 12.486 ≠ 12.470 | 12.486 = **obras distintas nos 16.845 registros brutos**, identificadas por DOI normalizado ou título simplificado. 12.470 = registros **após a etapa DOI da triagem** (DOI bruto sensível à caixa; registros sem DOI descartados). Grandezas e regras diferentes | **Problema de interpretação** (as grandezas não são comparáveis) + **decisão metodológica** pouco documentada (regra de identidade ≠ deduplicação da triagem) |
| Registros sem autor ou destino nas redes | (a) existe um "autor" chamado literalmente `null` (marcador vazio da exportação) que o pandas/planilha leem como vazio; ele liga 5 coautores. (b) não há nós vazios nas redes de co-citação/acoplamento; há a "referência" `undefined` (30 documentos) | **Erro de implementação** (marcadores não filtrados — AR-02) + problema de interpretação (leitor de CSV trata `null` como ausente) |
| Muitos ausentes em `intermediacao_nucleo` | calculada só para os 60 autores de maior grau (o "núcleo"); 1.828 vazios = 1.888 − 60 | **Decisão metodológica** (documentada só no código) / problema de interpretação |
| Áreas semanticamente distantes | `area` = *Fields of Study* da Lens (classificação automática herdada do Microsoft Academic Graph), ≈12,9 rótulos por documento; "Flood myth" (1.016), "Archaeology" (777), "Geology" (527) são rótulos automáticos, não áreas de periódico; só documentos de origem Lens têm o campo | **Limitação da base bibliográfica** |
| Tecnologias > documentos | uma tecnologia conta 1 vez por documento, mas um documento pode ter várias (4.772 pares) | **Característica legítima**; porém ver AR-04 (falsos positivos) e AR-05 (0% em anos sem menção) |

### 5.2 Achados adicionais

| ID | Achado | Evidência | Classificação |
|---|---|---|---|
| AR-01 | Autores da Lens não são lidos (coluna `Author/s` fora dos aliases) | 463 documentos com autor ≈ 464 de origem Scopus; 0 de 1.604 de origem Lens | **Erro de implementação** |
| AR-07 | Metadados bibliométricos vêm **só do registro mantido** na deduplicação (o primeiro, geralmente Lens), sem aproveitar a cópia da mesma obra em outra base | afiliações, países e instituições existem só para documentos cujo registro mantido é Scopus; a Lens não exporta afiliações | **Erro de implementação** (desenho) + limitação da base |
| AR-08 | Corpus contém preprints, discussões, pareceres e duplicatas | 46 Research Square, 38 arXiv, 12 Preprints.org, 12 ESS, 14 EarthArXiv, 59 HESS/NHESS *Discussions*; 30 "Peer Review #…", "Comment on…", "Reply on…"; 91 pares duvidosos (27 DOI só na caixa, 64 títulos ≥ 90% semelhantes), 17 em A+B; ex.: `10.21203/rs.3.rs-3218898/v1` (preprint) e `10.2166/wst.2024.174` (artigo) do mesmo trabalho, ambos no Núcleo B | **Decisão metodológica** do procedimento original (deduplicação exata, sem filtro de tipo) + limitação da base (Lens indexa preprints e pareceres) |
| AR-09 | Co-citação/acoplamento misturam identificadores | 29.490 IDs Lens (`123-498-859-171-509`) + 3.708 referências em texto (Scopus); a mesma obra citada pelas duas bases vira duas referências; rótulos do gráfico são IDs ilegíveis | **Limitação da base** + erro de implementação (sem harmonização) |
| AR-03 | Acoplamento usa os 80 primeiros caracteres do título como identificador | 12 títulos do corpus colidem; 2 auto-laços | **Erro de implementação** |
| AR-04 | Dicionário de tecnologias com termos genéricos | `\battention\b` casa "attracted attention": 135 documentos "Attention", 8 títulos com *attention mechanism/based*; `ensemble` casa previsão hidrológica por conjunto | **Erro de implementação** (Attention); decisão semântica (Ensemble) |
| AR-05 | Percentual anual 0% em anos sem menção | 2001 e 2003: 0% em todas as categorias (0/0) | **Erro de implementação** (baixo) |
| AR-06 | `cobertura` diz "sim" sem informar quantos documentos têm o campo | autores "sim" com 463/2.068 | **Erro de implementação** (transparência) |
| AR-10 | Mapa temático degenerado | centralidade = soma bruta de pesos externos e densidade = média de pesos internos, sem normalização de equivalência; ambas crescem com o tamanho do cluster: 4 maiores = "motor", 4 menores = "emergente", nenhum "nicho"/"básico"; modularidade da partição 0,158 | **Decisão metodológica** (definição simplificada de Callon) / problema de interpretação |
| AR-11 | Documentos sem ano recebem R\* = 0 | os 9 sem ano estão todos no Descarte | **Decisão metodológica** do original (preservada; ver variante §10) |
| AR-12 | Scopus "Com Filtro" ⊂ "Sem Filtro" | as 2.441 obras distintas da "Com Filtro" estão todas na "Sem Filtro": os 16.845 registros brutos contam a mesma busca duas vezes | **Decisão metodológica** do protocolo de busca (afeta o "total bruto" relatado) |
| AR-13 | Sinônimos e variantes não unificados | "machine learning" / "machine-learning"; "flood"/"floods"/"flooding"; "convolutional neural network(s)" | Limitação / melhoria |
| AR-14 | Comunidades de coautoria ≈ componentes | 333 comunidades = 333 componentes; o Louvain no maior componente (107 nós) acha 6 comunidades (Q = 0,654), mas a partição global (Q = 0,9827) é a de maior modularidade — limite de resolução | **Característica legítima** do método (interpretação: comunidades não acrescentam informação aqui) |
| AR-15 | Layout de redes não reproduzível entre ambientes | co-citação regenerada: mesmos nós, posições diferentes (semente fixa, versões de bibliotecas diferentes) | Limitação (cosmética) |
| AR-16 | Anos recentes: janela de citação e ano incompleto | 2025: 578 documentos e 329 citações; 2026: 2 documentos, crescimento −99,7% | **Problema de interpretação** |
| AR-17 | Formato de nomes de autor | `I., Ebtehaj, Isa` (iniciais, sobrenome, nome) | **Inconclusivo** sem a exportação Scopus (formato da coluna `Authors`) |
| AR-18 | Instituição truncada | `University of French West Indies (UAG` (separação por vírgula dentro de parênteses) | Erro de implementação (baixo) |

## 6. Evidências e exemplos reproduzíveis

Com a pasta da execução (os 35 arquivos) em `$PASTA`:

```bash
CIENTOMETRIA_RESULTADOS_EXECUCAO=$PASTA python -m pytest tests/test_auditoria_resultados.py -v -rxX
```

Resultado nesta auditoria: **9 invariantes aprovados, 6 defeitos confirmados (xfail)** —
`docs/evidencias/auditoria_052b2a400fc1/testes_auditoria.txt`.

Exemplos (todos verificáveis no `corpus.csv`):
- Duplicata por caixa de DOI: `10.1029/2022WR032395` (Scopus) e `10.1029/2022wr032395` (Lens), ambos Núcleo B.
- Preprint + artigo: "Research on nowcasting prediction technology for flooding scenarios…" — `10.21203/rs.3.rs-3218898/v1` e `10.2166/wst.2024.174`.
- Itens que não são artigos: "Peer Review #1 of "Multi-step rainfall forecasting using deep learning approach (v0.1)"" (`10.7287/peerj-cs.514v0.1/reviews/1`) e mais 3 variantes no corpus.
- Autor espúrio: linha `null` em `bib_coautoria_nos.csv` (grau 5).
- Referência espúria: `undefined` em `bib_cocitacao_referencias_mais_citadas.csv` (30 documentos).
- Tecnologia genérica: `B.detectar_tecnologias` marca "Attention" em "Floods have attracted attention" (teste AR-04).

## 7. Classificação de gravidade

| Gravidade | Critério | Itens |
|---|---|---|
| **Crítica** | invalida a leitura do indicador como representativo do corpus | AR-01 + AR-07 (autores, coautoria, instituições, países: 22% do corpus) |
| **Alta** | altera conclusões substantivas se não for ressalvado | AR-08 (preprints/pareceres/duplicatas no corpus, 47 em A+B); AR-09 (co-citação/acoplamento com identificadores mistos) |
| **Média** | distorce um indicador ou sua interpretação | AR-04, AR-06, AR-10, AR-11, AR-12, áreas (MAG), AR-03, AR-13 |
| **Baixa** | cosmético, documental ou de borda | AR-02, AR-05, AR-14, AR-15, AR-16, AR-18, intermediação parcial, linha "sem ano" ausente |
| Inconclusivo | depende das exportações | AR-17 |

Nenhum achado afeta os números da triagem (corpus, escores, estratos), que foram verificados integralmente.

## 8. Testes automatizados

Implementados em `tests/test_auditoria_resultados.py`:
- **Parte A — invariantes** (rodam com `CIENTOMETRIA_RESULTADOS_EXECUCAO`): proveniência por hash; aritmética
  das contagens; fórmulas C\*/R\*/escore/estrato; produção anual (+ sem ano = corpus); escores por ano;
  periódicos e Bradford; grau/força da coautoria e limite da intermediação; peso ≤ frequência nas redes;
  mapa temático recalculado; denominadores de tecnologias; simetria e traço da sobreposição; XLSX = CSV.
- **Parte B — defeitos (xfail estrito, sempre executados)**: AR-01, AR-02, AR-03, AR-04, AR-05, AR-06.
  Quando um defeito for corrigido o teste vira XPASS e o CI falha, obrigando a promovê-lo a teste normal.

Recomendados (exigem as exportações): autores/afiliações reconciliados entre cópias da mesma obra (AR-07);
harmonização de referências por DOI (AR-09); tipo de documento por registro (AR-08).

## 9. Limitações e riscos residuais

1. Sem as **8 exportações**, os indicadores bibliométricos foram verificados quanto à coerência interna, não
   recontados desde a fonte (autores, afiliações, áreas, palavras-chave e referências não estão no corpus).
2. Sem o `manifesto.json`, a proveniência dos CSVs bibliométricos se apoia no hash do corpus, no lote único de
   download (12:08:31–12:09:21) e na igualdade XLSX = CSV — não no SHA-256 de cada saída.
3. A comparação de gráficos por pixel é pouco sensível (controle negativo); a validação dos gráficos é visual.
4. A classificação de preprints/pareceres usa prefixos de DOI e padrões de título; é uma contagem aproximada.
5. Esta auditoria foi feita pelo mesmo agente que implementou a plataforma; recomenda-se conferência humana dos
   achados de gravidade crítica e alta.

## 10. Recomendações

O método `original-2026.01` **não foi alterado** e não deve ser. As correções abaixo são de análises
descritivas ou propostas de **variante independente**.

### Críticas / altas (antes de publicar indicadores bibliométricos)
1. **AR-01/AR-07 — cobertura de autores, afiliações e países**: incluir `Author/s` (Lens) nos aliases e
   **reunir metadados de todas as cópias da mesma obra** (ex.: afiliações da cópia Scopus de um registro mantido
   da Lens), sem mudar qual registro a triagem mantém. Até lá, reportar "n = 463 documentos com autor (22%)" junto
   de cada indicador.
2. **AR-08 — lista de leitura**: para a leitura, revisar os 91 pares duvidosos (`correspondencias_duvidosas`) e
   marcar preprints/pareceres. Como mudança de método, propor uma **variante independente** (ex.:
   `variante_tipo_documento`: exclui pareceres/comentários e une preprint + versão publicada), comparada ao
   original — nunca substituindo-o.
3. **AR-09 — co-citação/acoplamento**: harmonizar referências por DOI (Lens IDs ↔ DOI) ou restringir a análise a
   uma base por vez; exibir títulos, não IDs.

### Médias
4. AR-04: trocar `\battention\b` por padrões de mecanismo (`attention mechanism`, `attention-based`,
   `self-attention`) e separar `ensemble` hidrológico de `ensemble learning`.
5. AR-06: `cobertura` com `documentos_com_campo` e percentual.
6. AR-10: Callon com índice de equivalência (ou densidade/centralidade normalizadas) e aviso quando a modularidade
   for baixa.
7. AR-11: variante com R\* neutro para ano ausente (ex.: mediana), comparada ao original.
8. AR-12: relatar o total bruto com e sem a exportação "Scopus com filtro" redundante.
9. Áreas: rotular como "Fields of Study (Lens/MAG, automático)" e informar a cobertura.
10. AR-13: tesauro simples de sinônimos para palavras-chave (opcional, documentado).

### Baixas / melhorias futuras
11. AR-02 (filtrar `null`, `undefined`, `n/a`), AR-03 (identificador único no acoplamento), AR-05 (NaN para 0/0),
    AR-18 (separação de afiliações respeitando parênteses), linha "sem ano" na produção anual, documentação de
    `intermediacao_nucleo`, aviso sobre ano incompleto e janela de citação.
12. **Exportação da execução em `.zip`** com `manifesto.json` e verificação de hashes na reimportação (ver
    proposta da pesquisadora) — tornaria auditorias como esta verificáveis arquivo a arquivo.
    *Implementada depois desta auditoria* (`cientometria/pacote.py`; ações `exportar_execucao` e
    `importar_execucao`; `docs/SEGURANCA.md`, V11). Os resultados auditados aqui não foram reprocessados.

## Conclusão

- **Triagem: consistente.** Corpus, escores, estratos e Núcleo A conferem integralmente e pertencem à execução
  `052b2a400fc1` (hash verificado). Ressalva metodológica herdada do original: o corpus contém preprints,
  pareceres e duplicatas (AR-08), o que pede revisão humana da lista de leitura.
- **Indicadores bibliométricos: parcialmente consistentes.** Produção anual, periódicos, estratos, escores por
  ano, coocorrência, mapa temático (como calculado), tecnologias (como definidas) e sobreposição estão
  aritmeticamente corretos. Autores, coautoria, instituições e países **não podem ser considerados confiáveis
  como retrato do corpus** (22% de cobertura); co-citação e acoplamento precisam de harmonização; áreas e mapa
  temático exigem ressalvas de interpretação.
