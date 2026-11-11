# Mapa de migração (origem → destino)

Nenhum repositório de origem foi alterado, arquivado ou apagado. Nada foi removido deste repositório:
arquivos substituídos foram movidos com `git mv` ou marcados como legado.

## Fonte A — `DWan-Dall/cientometria`

| Origem | Destino | Observação |
|---|---|---|
| `strings_busca_por_base.md` | `docs/strings_busca_por_base.md` | cópia literal |
| `checklist_exportacao_por_base.md` | `docs/checklist_exportacao_por_base.md` | cópia literal; orienta `ingestao.py` e `diagnostico.LIMITACOES` |
| `log_buscas_template.csv` | `docs/log_buscas_template.csv` | cópia literal |
| `bloc.txt` | METHODOLOGY.md §1 (referência) | rascunho de strings |
| `main.R` — `convert2df`, `mergeDbSources` | `ingestao.py`, `consolidacao.py` | leitura e deduplicação em Python |
| `main.R` — `biblioAnalysis` | `bibliometria.producao_anual/autores/periodicos/paises` | |
| `main.R` — co-palavra | `bibliometria.coocorrencia` | |
| `main.R` — co-citação | `bibliometria.cocitacao` | requer referências citadas |
| `main.R` — acoplamento (`network="authors"`) | `bibliometria.acoplamento` (por referências compartilhadas entre documentos) | o original acoplava *autores*; aqui documentos (definição usual) |
| `main.R` — `thematicMap` | `bibliometria.coocorrencia(...)['mapa_tematico']` | centralidade/densidade de Callon |
| `Relatorio_Cientometria.Rmd` | `R/relatorio_bibliometrix.Rmd` | só sobre documentos selecionados pelo pacote |

## Fonte B — `DWan-Dall/dashboard-cientometria`

| Origem | Destino | Observação |
|---|---|---|
| `cientometria/*` (metodo-validado) | `cientometria/*` | API anterior preservada (`Config`, `executar`, `ler_pasta`, …) |
| `cientometria/config.py` | idem + `normalizar_doi`, `metodo_versao`, `corrigida_v1`, `do_modo`, `de_dict` | receitas `original`/`variante` inalteradas |
| `cientometria/entrada.py` | idem + mapeamentos de extensão, `normalizar_estendido`, proveniência | mapeamento original inalterado |
| `cientometria/pipeline.py` | idem; chave `doi_chave`; anotação de proveniência | contagens do original inalteradas (golden master) |
| `scripts/pipeline.py` | reescrito como ponte fina (ingestao + parametros + saida) | **corrige** o modo original do dashboard |
| `scripts/pipeline.py: montar_config` | `cientometria/parametros.py` | sem `mapeamento_tolerante=True` forçado |
| `scripts/pipeline_legado.py: load_file/parse_bibtex` | `cientometria/ingestao.py` | parser BibTeX refeito |
| `scripts/pipeline_legado.py` (regras) | — (legado, não usado) | mantido para histórico |
| `scripts/pipeline.R` | — (legado, desativado) | segunda triagem com regras próprias |
| `index.php` | `triagem_rapida.php` (`git mv`) | sem motor R; "alvos" somente leitura |
| — | `index.php` (novo), `api.php`, `arquivo.php` | interface modular |
| `run_pipeline.php` | idem | recusa R; envia nomes originais |
| `referencia/`, `tests/test_equivalencia_original.py`, `tests/test_modos_e_robustez.py`, `tests/sinteticos.py`, `notebooks/`, `exemplos/` | inalterados | |

## Fonte C — `DWan-Dall/analise-aprofundada-v3` (`cientometria_master.R` v2.3)

| Bloco R | Destino | Diferença deliberada |
|---|---|---|
| Diagnóstico de colunas | `diagnostico.relatorio_campos`, `bibliometria.analisar()['cobertura']` | por arquivo de exportação, não só do consolidado |
| 1) Bases de dados / versões | `consolidacao.sobreposicao`, `bases_encontradas` | proveniência calculada na consolidação, não reconstruída depois |
| 2) "Áreas" | `bibliometria.areas` (área da base) e `bibliometria.estratos` | o R contava `fascia` como "área" |
| 3) Periódicos | `bibliometria.periodicos` | + citações e zonas de Bradford |
| 4) Países | `bibliometria.paises` | normalização de nomes (USA, Peoples R China…) |
| 5) Coautoria (3 camadas) | `bibliometria.coautoria`, `graficos.rede` | separador `;` quando existe; Louvain com semente |
| 6) Palavras-chave e coocorrência | `bibliometria.coocorrencia` | caixa normalizada |
| Estrutura temática (componentes) | `coocorrencia(...)['clusters']` (Louvain) e `['componentes']` | |
| 7) Séries temporais | `bibliometria.producao_anual`, `graficos.serie_anual` | anos vazios = 0 (R deixava NA) |
| 8) Scores por ano | `bibliometria.scores_por_ano` | usar A* correto (CSV publicado tem A* corrompido) |
| 9) Tecnologias | `bibliometria.tecnologias`, `categoria_tecnologia` | detecção por dicionário quando não há coluna `technologies` |
| Sobreposição entre bases (matriz, Sankey) | `consolidacao.sobreposicao`, `graficos.heatmap_sobreposicao` | Sankey não portado (TODO) |
| `dados/DB_Cientometria_*` | **não copiado** | uso local em `test_dados_reais.py` via variável de ambiente |

### Verificação da migração do R (rodada 2)

`cientometria/compat_r.py` replica as regras de contagem do R e `tests/test_comparacao_r.py` confere,
número a número, contra `resultados_cientometria/`:

| Bloco R | Arquivo R comparado | Réplica | Padrão da plataforma |
|---|---|---|---|
| Bases | `02_bases/01` | idêntica | idêntica (`consolidacao.sobreposicao`) |
| "Áreas" | `03_areas/01` | idêntica (= estratos) | `estratos()`; `areas()` usa a área temática |
| Periódicos | `04_periodicos/01` | idêntica (724) | mesmos totais; agrupa variações de caixa |
| Países | `05_paises/01` | idêntica (727; por afiliação) | por documento e nomes unificados (333) |
| Autores, coautoria | `06_coautoria/02`, `03`, `06`, `08` | idêntica | arestas idênticas; 6.758 × 6.759 autores |
| Palavras-chave, coocorrência | `07_palavras_chave/01`, `03` | idêntica | caixa normalizada |
| Clusters | `08_estrutura_tematica/01` | idêntica (componentes) | Louvain (componentes também exportados) |
| Séries temporais | `09_series_temporais/01–03` | idêntica (NA em anos vazios) | 0 em anos vazios |
| Scores por ano | `10_scores/01` | idêntica (com A\* corrompido) | C\*, R\*, T\* iguais; A\* corrigido |
| Tecnologias | `11_tecnologias/01` | idêntica | únicas por registro (mesmos totais aqui) |
| Sobreposição | `12_sobreposicao_bases/01`, `06` | idêntica | idêntica |

Co-citação, acoplamento e área temática não puderam ser comparados (sem dados no corpus publicado; o R
não os calculou).

## Rodada 2 — componentes novos

| Componente | Função |
|---|---|
| `seguranca.php`, `router.php`, `.htaccess` | acesso, CSRF, CSP, roteamento seguro, limites de upload |
| `vendor/chart-4.4.1.umd.js` | Chart.js empacotado (antes: CDN sem versão) |
| `cientometria/compat_r.py` | réplica das regras do R para auditoria |
| `scripts/verificar_repositorio.py`, `docs/congelados.sha256` | arquivos congelados e ausência de dados licenciados (CI) |
| `.github/workflows/ci.yml` | CI |
| `requirements-dev.txt`, `pyproject.toml` | dependências de desenvolvimento, ruff, pytest |

## Fonte D — sessão Perplexity

Não acessível; extração pendente (TODO.md).
