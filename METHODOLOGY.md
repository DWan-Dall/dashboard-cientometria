# Metodologia

Fonte única da regra: o pacote Python `cientometria`. Este documento descreve o que o código faz; quando
houver divergência, o código e os testes prevalecem e o documento deve ser corrigido.

## 1. Protocolo de busca (registro)

Strings por base: `docs/strings_busca_por_base.md`. Campos a exportar: `docs/checklist_exportacao_por_base.md`.
Registre cada busca em `docs/log_buscas_template.csv` (base, string exata, data/hora, filtros, nº de retornos,
arquivo). O artigo usou 8 exportações: Lens (EN, PT), Scopus (sem filtro, com filtro, PT), IEEE Xplore,
SciELO (EN, PT). As strings e datas efetivamente usadas nessas exportações **não estão registradas**
(docs/AUDITORIA.md, achado 10).

## 2. Triagem (procedimento do artigo, jan/2026)

1. **Leitura** de cada exportação (`pd.read_csv` padrão) e **mapeamento fixo** de colunas por base
   (`entrada.MAPEAMENTO_ORIGINAL`). Coluna ausente → título `Unknown`, demais campos vazios, citações 0.
2. **Consolidação** na ordem: Lens EN, Lens PT, Scopus sem filtro, Scopus com filtro, Scopus PT, IEEE,
   SciELO EN, SciELO PT.
3. **Deduplicação**: (a) mantêm-se só registros **com** DOI, sem repetição de DOI (texto bruto); (b) sem
   repetição do título em caixa baixa e sem espaços nas pontas. Sempre o **primeiro** registro é mantido.
4. **Filtros temáticos** (casamento por trecho de texto, sem distinção de caixa — `termos.py`):
   - FP: previsão de enchentes (18 termos) em título+resumo+palavras-chave;
   - IA: métodos de IA/ML (20) em título+resumo+palavras-chave;
   - H: dados hidrológicos (20) em resumo+palavras-chave; G: geoespaciais (20) em resumo+palavras-chave;
   - X: exclusão (15 termos) em título+resumo.
   - Núcleo obrigatório = FP ∧ IA ∧ ¬X; **núcleo expandido (corpus)** = FP ∧ IA ∧ (H ∨ G) ∧ ¬X.
5. **Escore** sobre o corpus:
   - C* = (C − Cmin)/(Cmax − Cmin) (citações; 0 se Cmax = Cmin);
   - R* = (Y − Ymin)/(Ymax − Ymin) (ano; 0 se ausente);
   - T* = 1,0 se FP e IA no título; 0,7 se FP e IA em título+resumo+palavras-chave; senão 0,4;
   - A* = (I + M + O + C)/4, com I ∈ {0, 1} (dados de entrada), M, O, C ∈ {0,5; 1} (método específico,
     saída, contexto);
   - S = 0,35·C* + 0,20·R* + 0,30·T* + 0,15·A*; S₁₀₀ = min–max(S)·100, arredondado a 2 casas.
6. **Estratos**: Núcleo A ≥ 70; Núcleo B ≥ 50; Periférico ≥ 30; Descarte < 30.

**Limites do método** (devem constar em qualquer uso): triagem automática sem revisão humana registro a
registro (não há concordância entre avaliadores); escores relativos ao corpus; rótulo dependente de cortes
fixos; termos curtos (`dem`, `gis`, `rnn`, `cnn`, `dam`) casam dentro de outras palavras.

## 3. Modos e versões do método

| Modo | Versão | Diferença em relação ao anterior | Justificativa |
|---|---|---|---|
| `original` | `original-2026.01` | — | Reproduzir e auditar o artigo. **Congelado.** |
| `variante_exclusao` | `variante-1` | `dam`, `dike`, `levee` como palavra inteira (com plural) | Medir o efeito de `dam` ⊂ *damage* (ex.: Mosavi et al., 2018, excluído no original) |
| `corrigida` | `corrigida-1` | + mapeamento tolerante de colunas (IEEE, SciELO, Scopus `Author/Index Keywords`); + mantém registros sem DOI; títulos ausentes não colapsam | Falhas de implementação documentadas (colunas não lidas; "deduplicação" que descartava registros sem DOI) |
| `corrigida` | **`corrigida-2`** (vigente) | + DOI normalizado (caixa baixa, sem `https://doi.org/`/`doi:`) antes de deduplicar | 27 pares de DOIs que diferem só na caixa no corpus publicado (AUDITORIA, achado 3) |

`Config.corrigida_v1()` reproduz a `corrigida-1` para comparação. Toda nova alteração que mude números deve
criar nova versão em `cientometria/versao.py` com data e justificativa, e um teste.

**Regra:** nenhum modo é escolhido para atingir uma quantidade predeterminada de artigos. Os modos existem
para mostrar a diferença entre eles (aba "Robustez e modos"; `comparar_modos`).

Parâmetros alterados pelo usuário (pesos, cortes, termos, opções) tornam a execução **personalizada**; o
manifesto lista cada alteração em relação à receita do modo.

## 4. Robustez e validação

- **Sensibilidade aos pesos** (`robustez.sensibilidade_pesos`): 10.000 sorteios (±15% uniforme e
  Dirichlet(5)), semente fixa; mede quantos artigos do Núcleo A permanecem no topo do ranking e acima do corte.
- **Tabela de referência** entre modos (`robustez.tabela_referencia`).
- **Exclusão por trecho** (`diagnostico.exclusao_por_trecho`): candidatos excluídos só porque
  `dam/dike/levee` aparece dentro de outra palavra.
- **Validação externa** (`validacao.validar_referencias`): para cada referência de uma revisão independente
  (exemplo: 22 de Dias et al., 2025 em `exemplos/`), indica recuperação, sobrevivência à deduplicação,
  filtro, exclusão e estrato.
- **Duplicatas duvidosas** (`consolidacao.correspondencias_duvidosas`): lista para revisão humana; a decisão
  é registrada na coluna `decisao` e nunca aplicada automaticamente.

## 5. Análises bibliométricas (descritivas)

Não alteram a triagem. Calculadas sobre o corpus de uma execução (`bibliometria.analisar`): produção anual
(documentos, citações, crescimento), autores, instituições (segmento com "Univ…/Institut…" da afiliação),
países (coluna de países; senão último segmento da afiliação; contagem inteira por documento), periódicos
(com zonas de Bradford por terços acumulados), áreas temáticas da base, coautoria (rede, Louvain, centralidade),
coocorrência de palavras-chave (frequência mínima 3, aresta mínima 2), clusters (Louvain, semente 123) e mapa
temático de Callon (centralidade = soma dos pesos externos; densidade = média dos pesos internos;
quadrantes pela mediana), co-citação e acoplamento (exigem referências citadas na exportação), tecnologias
(coluna `technologies` ou dicionário sobre o texto; categorias do R original) e sobreposição entre bases.
A tabela `cobertura` diz o que não pôde ser calculado e por quê.

## 6. Reprodutibilidade

Cada execução grava um manifesto (`manifesto.json`) com ID, data/hora UTC, versões da aplicação, do método
e das dependências, SHA-256 de cada arquivo, ordem de processamento, todos os parâmetros (inclusive listas de
termos), pesos, cortes, regras de exclusão, critérios de consolidação, contagens de cada etapa, estratos, a
lista do Núcleo A e o hash do corpus. `reproduzir` reexecuta com os mesmos arquivos e parâmetros e compara
os hashes.

## 7. Material metodológico externo (sessão Perplexity)

Pendente de extração (inacessível nesta sessão). Quando extraído, registrar aqui cada decisão com: quem
propôs (usuário ou IA), se foi confirmada, e a fonte científica citada (ou "sem fonte"). Sugestões de IA não
são evidência científica.
