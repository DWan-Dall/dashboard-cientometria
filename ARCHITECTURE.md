# Arquitetura

## Princípio

**Uma regra, um lugar.** Todo cálculo científico da triagem está no pacote Python `cientometria`. PHP e
JavaScript só enviam arquivos/parâmetros e exibem JSON. R pode produzir relatórios complementares a partir
de resultados do pacote, mas não implementa triagem.

```
Navegador ──► index.php / triagem_rapida.php  (exibição)
                 │ fetch
                 ▼
            api.php · run_pipeline.php · arquivo.php   (upload, repasse, download — sem regras)
                 │ exec
                 ▼
   python -m cientometria.api <ação>   ·   scripts/pipeline.py      CLI: python -m cientometria …
                 │
                 ▼
 ┌──────────────────────── pacote cientometria ─────────────────────────┐
 │ ingestao      formatos, tipo de base, SHA-256, ordem, avisos         │
 │ entrada       esquema da triagem (mapeamento original/tolerante)     │
 │               + esquema bibliométrico estendido, proveniência        │
 │ consolidacao  chaves DOI/título, proveniência entre bases, pares     │
 │               duvidosos, sobreposição, critérios                     │
 │ pipeline      consolidar → filtrar → escorar → classificar           │
 │ nucleo/termos filtros e escore C*, R*, T*, A* (funções puras)        │
 │ config/versao modos, receitas, versões do método                     │
 │ parametros    JSON da interface → Config (fonte única)               │
 │ diagnostico · robustez · validacao · auditoria                       │
 │ bibliometria · graficos · relatorios                                 │
 │ manifesto     manifesto de reprodução e comparação                   │
 │ projetos      projetos, arquivos imutáveis, execuções, histórico     │
 │ saida · api   contratos JSON                                         │
 └───────────────────────────────────────────────────────────────────────┘
                 │
                 ▼
  $CIENTOMETRIA_PROJETOS/<projeto>/{arquivos, execucoes/<id>, historico.jsonl}   (fora do Git)
```

## Decisões arquiteturais

| # | Decisão | Motivo |
|---|---|---|
| D1 | Pacote Python como única implementação da triagem | Eliminar divergência entre R, Python legado e pacote (AUDITORIA, achado 4) |
| D2 | `referencia/` (scripts originais) congelado e testado contra o pacote | O modo original precisa provar equivalência, não apenas afirmá-la |
| D3 | Leitura e ordem do modo original idênticas ao procedimento | A deduplicação mantém o 1º registro; leitor/ordem mudam o resultado (achado 1) |
| D4 | Mapeamentos de extensão (WoS, OpenAlex, RIS, BibTeX, genérico) separados do mapeamento original | Ampliar bases sem tocar o original |
| D5 | Esquema bibliométrico separado do esquema da triagem, ligados por `arquivo_origem`/`linha_origem` | Análises usam campos extras sem alterar a triagem |
| D6 | Execuções imutáveis em pastas próprias + manifesto + histórico append-only | "Nova importação não sobrescreve resultados anteriores"; recuperação e comparação |
| D7 | Projetos em sistema de arquivos (JSON/CSV), não em banco | Transparência e portabilidade; dados licenciados ficam fora do Git (`projetos/` no `.gitignore`, volume `/dados` no Docker) |
| D8 | Versão do método explícita (`versao.py`) e `corrigida_v1` preservada | Mudanças metodológicas registradas e comparáveis |
| D9 | Parâmetros fora da receita marcam a execução como "personalizada" | Impedir que ajustes passem despercebidos |
| D10 | Interface sem "alvos" editáveis; números do artigo só como referência histórica | Integridade: não incentivar ajuste para atingir quantidades |
| D11 | Duplicatas duvidosas listadas para revisão, nunca fundidas automaticamente | Decisão humana registrada |
| D12 | PHP embutido (`php -S`) mantido | Compatível com a forma de uso atual e com o Docker existente |

## Contratos

- `scripts/pipeline.py <payload.json>` → JSON `summary/top_articles/dedup_removed/plot_urls/used_params/extras`
  (contrato anterior, mais `fontes`, `contagens`, `alteracoes_da_receita`). `payload.names` traz os nomes
  originais dos arquivos.
- `python -m cientometria.api <ação> <payload.json>` → JSON; erro → `{"erro": ...}` e código 1. Ações em
  `api.despachar`.

## Testes

| Arquivo | Cobre |
|---|---|
| `test_equivalencia_original.py` | pacote × scripts originais (sintético) — **preservado** |
| `test_modos_e_robustez.py` | modos, robustez, diagnósticos, validação, contrato JSON — **preservado** |
| `test_adaptador_dashboard.py` | dashboard original = pacote original, ordem, nomes temporários, R recusado, sem alvos editáveis |
| `test_ingestao.py` | CSV/TSV/TXT/XLSX/RIS/BibTeX/WoS, codificação, linhas ruins, detecção de base, entradas incompletas |
| `test_consolidacao.py` | ausência de DOI, duplicatas, DOI normalizado, versões da corrigida, proveniência, pares duvidosos |
| `test_projetos_manifesto.py` | imutabilidade, manifesto, consistência e reprodução, personalização, relatórios, API |
| `test_bibliometria.py` | análises com resultado conhecido |
| `test_volume.py` | 60 mil registros |
| `test_dados_reais.py` | exportações originais e corpus publicado (via variáveis de ambiente) |
