# Exportação e importação de execuções (pacote ZIP)

Um ZIP leva uma execução científica completa de um projeto para outro, ou de uma máquina para outra, e
permite conferir que nada mudou no caminho. O pacote **restaura resultados**: não recalcula nada. A
**reexecução** é outra operação, separada, que cria uma execução nova e só é possível quando as
exportações bibliográficas de origem estão disponíveis.

## 1. Arquitetura

Não há um segundo sistema de persistência nem um segundo mecanismo de manifesto. A funcionalidade
estende os existentes:

| Peça | Papel | Arquivo |
|---|---|---|
| Formato do pacote | montar o ZIP; validar sem extrair; extrair com conferência de SHA-256. Só lê e escreve o arquivo `.zip` e não conhece projetos | `cientometria/pacote.py` (novo) |
| Manifesto do pacote | derivado do manifesto da execução por `manifesto.pacote()`. O manifesto da execução viaja intacto dentro do ZIP | `cientometria/manifesto.py` |
| Operações | `inventario_execucao`, `exportar_execucao`, `receber_pacote`, `inspecionar_pacote`, `descartar_pacote`, `restaurar_pacote`, `reexecutar`. Reutilizam `_trava`, `_json`, `_sha_saidas`, `_evento`, a cópia imutável de entradas (`_copiar_entrada`, a mesma da importação) e a renomeação atômica das execuções | `cientometria/projetos.py` |
| Verificação | `verificar_execucao` passa a reconhecer as execuções importadas: a ausência das entradas vira aviso ("reexecução impossível"), não falha dos resultados | `cientometria/projetos.py` |
| API / CLI | ações JSON e comandos `exportar`, `verificar-pacote`, `importar-pacote`, `reexecutar` | `cientometria/api.py` |
| Web | upload do ZIP (`seg_receber_pacote`) e download (`exportar_execucao` devolve `application/zip`) | `seguranca.php`, `api.php` |
| Interface | botões por execução e um painel "Importar ZIP" | `index.php`, seção 6 |

Disco, dentro da pasta do projeto, que já existia:

```
execucoes/<data>_<id>/            a execução restaurada, com o mesmo nome de pasta e o mesmo ID
execucoes/.importadas/<id>.json   procedência da restauração (SHA-256 do pacote, projeto de origem, entradas)
execucoes/.importando_<id>_<x>/   restauração em curso (invisível na lista; removida por recuperar())
pacotes/<token>.zip               pacote recebido e validado, aguardando confirmação (somente leitura)
historico.jsonl                   eventos: pacote_recebido, execucao_restaurada, pacote_ja_restaurado,
                                  pacote_descartado, execucao_exportada, execucao (com origem_execucao)
```

O registro de procedência fica fora da pasta da execução. Assim os arquivos restaurados ficam idênticos
aos originais, byte a byte, e `saidas_sha256` continua valendo.

## 2. Estrutura do ZIP (formato `cientometria-pacote-execucao`, versão 1)

```
manifesto.json                         manifesto do pacote (abaixo)
LEIA-ME.txt                            conteúdo, omissões com SHA-256, como verificar, aviso de licença
execucao/<AAAAMMDDTHHMMSSZ_id>/        a pasta da execução, inteira e byte a byte:
    manifesto.json                     manifesto da execução (parâmetros, versões, contagens, hash do corpus, saidas_sha256)
    contagens.json  corpus.csv  consolidado.csv
    diagnosticos/   campos.csv, limitacoes.json, diagnosticos.json, duplicatas_para_revisao.csv
    bibliometria/   *.csv (produção, autores, fontes, redes: nós/arestas/clusters, indicadores…)
    graficos/       *.png
    relatorios/     relatorio.pdf, relatorio_metodologico.md, resultados.xlsx, parametros.json, csv/*.csv
entradas/<sha12>__<nome>               exportações bibliográficas originais (opcional)
```

Campos de `manifesto.json`:

| Campo | Conteúdo |
|---|---|
| `formato`, `versao_formato` | identificação e versão do formato (compatibilidade) |
| `exportado_em`, `versao_aplicacao_exportacao`, `dependencias_exportacao` | quando e com qual software o pacote foi gerado |
| `execucao` | ID, pasta, rótulo, data/hora, versão da aplicação que executou, modo, versão do método, configuração personalizada, hash do corpus, impressão digital da entrada, `origem_execucao` (se for reexecução) |
| `projeto_origem` | slug, nome, descrição, fontes bibliográficas |
| `parametros` | configuração completa (`Config.completa()`) |
| `contagens_por_etapa`, `estratos` | registros → sem DOI → … → corpus; Núcleo A/B/periférico/descartado |
| `dependencias` | versões de Python, pandas, numpy, openpyxl, rapidfuzz, networkx, matplotlib na execução |
| `fontes` | cada exportação de origem: nome, SHA-256, bytes, formato, tipo de base, base forçada, registros, leitura, detecção, `incluido`, `caminho_no_pacote` ou `motivo_omissao` |
| `omitidos` | arquivos não incluídos, com SHA-256 e justificativa |
| `reprodutibilidade` | entradas incluídas/total, `reexecucao_possivel_so_com_o_pacote` e declaração em texto |
| `verificacao_na_exportacao` | resultado da conferência das saídas no momento da exportação |
| `arquivos` | SHA-256 e bytes de **cada** arquivo do ZIP (exceto o próprio manifesto) |

Sem as exportações de origem, a declaração é explícita: os resultados podem ser restaurados e conferidos,
mas a análise **não** pode ser reexecutada só com o pacote. O pacote nunca afirma reprodutibilidade
integral quando falta qualquer entrada.

## 3. Fluxos

### Exportar
1. `inventario_execucao` mostra a prévia: arquivos, tamanho, entradas incluídas ou omitidas e motivo.
2. `exportar_execucao` confere as saídas contra `saidas_sha256` e recalcula o hash do corpus. Se algo
   difere, **recusa** exportar, porque um pacote de resultados alterados não pode sair como íntegro.
3. Monta o ZIP (temporário + `fsync` + renomeação), registra `execucao_exportada` com o SHA-256 do
   pacote e devolve o arquivo. Na web ele é gerado num diretório temporário fora do webroot, enviado e apagado.

As entradas são localizadas no projeto pelo SHA-256 registrado no manifesto da execução. Entrada ausente
ou alterada no projeto não é incluída, e o motivo vai para `omitidos`.

### Importar = receber → inventário → restaurar (ou descartar)
1. **Receber** (`receber_pacote`): o upload vai para um diretório temporário fora do webroot. O Python
   valida o ZIP **sem extrair** (seção 5), copia-o para `pacotes/<token>.zip` e devolve o inventário:
   arquivos com estado `ok`, `ausente`, `alterado` ou `inesperado`, problemas, avisos, contagens,
   entradas incluídas ou omitidas, conflito de ID no projeto e se a reexecução será possível depois.
2. **Restaurar** (`restaurar_pacote`), só por confirmação explícita:
   - revalida o pacote (ele pode ter mudado desde o inventário) e recusa se houver problema;
   - extrai `execucao/` para `execucoes/.importando_…`, conferindo o SHA-256 de cada arquivo enquanto grava;
   - confere os arquivos extraídos contra o **manifesto da execução** (`saidas_sha256` e hash do corpus
     recalculado). Isso pega também um pacote adulterado de forma coerente, com arquivo e manifesto do
     pacote alterados juntos;
   - opcionalmente importa as exportações incluídas pelo mesmo caminho da importação comum (validação de
     conteúdo, cópia imutável, registro sob trava);
   - sob a trava do projeto: se o ID já existe com conteúdo idêntico, responde `ja_existia`; com conteúdo
     diferente, **recusa** (o ID original nunca é reaproveitado nem sobrescrito); senão, renomeação
     atômica para `execucoes/<pasta original>`;
   - grava `.importadas/<id>.json` e o evento `execucao_restaurada` (`recalculo: false`).
3. **Descartar** apaga o pacote recebido.

### Reexecutar (`reexecutar`)
Cria uma execução **nova** (ID novo) com os arquivos e parâmetros registrados numa execução, com
`origem_execucao` no manifesto e no evento. Exige:
- todas as exportações de origem no projeto, com o mesmo SHA-256 (vindas do pacote ou importadas à parte);
- versão do método conhecida por esta aplicação, reconstruída sem mudança a partir dos parâmetros.

Se faltar algo, recusa e diz o quê. A execução de origem nunca é alterada. O resultado traz a comparação
(`manifesto.comparar`) entre origem e nova. A ação antiga `reproduzir`, uma conferência rápida sem
bibliometria, continua disponível na API e na CLI.

## 4. Interface (seção 6, Execuções e comparação)

- Por execução: **abrir**, **inventário**, **exportar ZIP**, **verificar**, **reexecutar**. Etiquetas
  "importada de …" e "reexecução de …".
- Caixa "incluir no ZIP as exportações bibliográficas originais", marcada por padrão e com o aviso de licença.
- **Importar ZIP**: escolher o arquivo e importar. O inventário aparece antes de qualquer mudança, com
  problemas em vermelho, avisos e a declaração de reprodutibilidade. Botões **Restaurar execução**
  (desabilitado se houver problema ou conflito) e **Descartar**.
- **Comparar** continua com os seletores A/B. Funciona entre execução importada, local e reexecução.

## 5. Compatibilidade e segurança

**Versões.** `versao_formato` inteiro. Versões maiores que a suportada são recusadas com o pedido de
atualizar a aplicação. Ausente, zero ou de outro tipo também é recusado. Campos desconhecidos são
tolerados, para que extensões compatíveis não quebrem leitores antigos. A versão do método não impede a
restauração, só a reexecução.

**Validação sem extrair** (`pacote.inspecionar`):
- ZIP comum (stored/deflated). Recusa criptografia, entradas duplicadas (inclusive só na caixa) e ZIP
  corrompido ou truncado (inclusive erro de descompressão);
- nomes: relativos, sem `..`, `.`, componentes vazios, barra invertida ou NUL, só `[A-Za-z0-9._-]`, e
  dentro da estrutura (`manifesto.json`, `LEIA-ME.txt`, `execucao/<pasta>/…` com extensões de resultado,
  `entradas/<sha12>__…` com extensões bibliográficas). Executáveis, scripts e HTML não cabem na estrutura;
- só arquivos regulares: links simbólicos, dispositivos e FIFOs são recusados pelos bits de tipo;
- limites: tamanho do ZIP (`CIENTOMETRIA_MAX_MB_PACOTE`, 512 MiB), total descompactado
  (`CIENTOMETRIA_MAX_MB_PACOTE_DESCOMPACTADO`, 4096 MiB), 5.000 entradas e razão de compressão de 200
  acima de 1 MiB. A leitura é feita em blocos e nunca passa do tamanho declarado;
- integridade: cada arquivo listado existe e tem o SHA-256 declarado; arquivo não listado é "inesperado".

**Extração.** Só depois da validação e da confirmação. Nomes revalidados, destino confinado, `open(…, "xb")`
(não sobrescreve nem segue link) e SHA-256 conferido durante a gravação. Nada do pacote é executado ou
importado como código. As planilhas restauradas não são abertas.

**Web.** Upload só pelo campo `pacote`, extensão `.zip`, com CSRF, origem e Host verificados
(`seg_exigir_post_protegido`). O caminho do arquivo nunca vem do cliente: `caminho` e `destino` são
removidos do JSON, e o Python confina recebimento e exportação a `CIENTOMETRIA_DIR_IMPORTACAO` e
`CIENTOMETRIA_DIR_EXPORTACAO`. Token do pacote validado por regex. Nome do arquivo baixado validado por
regex no PHP.

**Concorrência e interrupção.** Restauração em pasta temporária invisível. Publicação por renomeação
atômica sob `_trava`. Importações simultâneas do mesmo pacote resultam em uma `restaurada` e as demais
`ja_existia`. Uma queda deixa só temporários, que `recuperar()` remove sem tocar resultados.

**Licença.** Exportar sem as entradas guarda apenas os SHA-256. `*.zip` está no `.gitignore` e
`scripts/verificar_repositorio.py` falha se um `.zip` for versionado.

**Limite do que o SHA-256 prova.** O pacote não é assinado. O SHA-256 detecta alteração acidental ou
parcial, e a conferência com o manifesto da execução detecta alteração de resultados. Quem reescreve de
forma consistente o resultado, o manifesto da execução e o do pacote produz um pacote coerente, como
qualquer conjunto de arquivos sem assinatura. A **autenticidade** depende de obter o pacote de fonte
confiável e conferir o SHA-256 informado por quem o gerou (cabeçalho `X-Pacote-SHA256` e evento
`execucao_exportada`). Ver `docs/SEGURANCA.md` §7.

## 6. Critérios de aceitação e testes

| # | Critério | Teste (`tests/test_pacote.py`) |
|---|---|---|
| 1 | Ida e volta: todos os artefatos exportados; restauração byte a byte com mesmo ID, mesma pasta e mesmo manifesto; verificação ok; procedência registrada; reexportação com os mesmos arquivos | `test_01_ida_e_volta_integra`, `test_01b_…` |
| 2 | Arquivo ausente: detectado; restauração recusada; nada listado | `test_02_arquivo_ausente` |
| 3 | Arquivo alterado após a exportação: estado `alterado`; restauração recusada | `test_03_…` |
| 4 | Hash incorreto ou mal formado no manifesto; adulteração coerente pega pelo manifesto da execução | `test_04_…`, `test_04b_…` |
| 5 | ZIP inválido, vazio, truncado, sem manifesto, manifesto ilegível ou incompleto, CRC corrompido, duplicatas, criptografia | `test_05_…` |
| 6 | Zip bomb (razão), total descompactado, número de entradas, tamanho do pacote, tamanho declarado falso | `test_06_…`, `test_06b_…` |
| 7 | Path traversal (10 variantes), links simbólicos e arquivos especiais, extração nunca escapa do destino | `test_07_…` (10), `test_07b_…`, `test_07c_…` |
| 8 | Arquivos inesperados: não listados, executáveis, fora da estrutura, de outra execução | `test_08_…` |
| 9 | Dados originais omitidos: SHA-256 guardados, motivo, declaração explícita, restauração ok, reexecução recusada | `test_09_…`, `test_09b_…` |
| 10 | Restaurar sem recalcular (pipeline, leitura, bibliometria e relatórios proibidos durante a restauração) | `test_10_…` |
| 11 | Reexecutar com novo ID, `origem_execucao`, mesmo corpus, origem intacta; versão de método desconhecida recusa só a reexecução | `test_11_…`, `test_11b_…` |
| 12 | Compatibilidade da versão do pacote (mais nova, ausente, inválida, outro formato; campos extras tolerados) | `test_12_…` |
| 13 | 8 importações simultâneas: 1 restaurada e 7 `ja_existia`, sem duplicar entradas nem deixar temporários; mesmo ID com conteúdo diferente é recusado | `test_13_…`, `test_13b_…` |
| 14 | Interrupção durante a restauração: nada pela metade e nova tentativa possível; queda do processo limpa por `recuperar()` | `test_14_…`, `test_14b_…` |
| — | Exportação recusa resultados alterados; confinamento web; tokens inválidos; descarte; API; CLI; endpoints PHP (CSRF, extensão, caminho via JSON, download com SHA-256) | demais testes do arquivo |
| — | Navegador real (Chromium, CSP ativo): reexecutar, verificar, inventário, exportar (download), importar noutro projeto, inventário, restaurar | `tests/test_interface.py::test_fluxo_completo_do_dashboard` |

Os testes usam dados **sintéticos**: verificam o mecanismo do pacote, não a reprodução do artigo. O modo
`original-2026.01` não foi alterado: arquivos congelados conferidos por `scripts/verificar_repositorio.py`,
e `test_equivalencia_original.py` passa sem alterações.

## Uso

```bash
python -m cientometria exportar <projeto> <id> --saida pasta/           # completo
python -m cientometria exportar <projeto> <id> --sem-entradas           # sem as exportações das bases
python -m cientometria verificar-pacote execucao_<id>_<projeto>.zip     # valida sem importar (código 2 se houver problema)
python -m cientometria importar-pacote <projeto> pacote.zip [--sem-entradas]
python -m cientometria reexecutar <projeto> <id>
```
