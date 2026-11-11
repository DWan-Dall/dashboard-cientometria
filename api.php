<?php
// Ponte HTTP -> `python3 -m cientometria.api <acao> <payload.json>`.
// Nenhum cálculo científico é feito aqui: este arquivo só recebe uploads e repassa JSON.
// Segurança: ver seguranca.php (autenticação/loopback, origem, CSRF, limites de upload).
require __DIR__ . '/seguranca.php';
header('Content-Type: application/json; charset=utf-8');
ini_set('display_errors', '0');

const ACOES = ['listar_projetos', 'criar_projeto', 'projeto', 'atualizar_projeto', 'importar', 'remover_arquivo',
               'diagnosticar', 'executar', 'execucoes', 'execucao', 'comparar', 'reproduzir', 'comparar_modos',
               'verificar_execucao', 'exportar_execucao', 'importar_execucao'];
const PROJETO_RX = '/^[a-z0-9][a-z0-9-]{0,80}$/';

function raizProjetos() {
  $r = getenv('CIENTOMETRIA_PROJETOS');
  return $r ? $r : __DIR__ . '/projetos';
}

function chamarPython($acao, $dados, $dirUpload = null, $dirExportacao = null) {
  $dir = seg_diretorio_temporario('api_');
  try {
    $tmp = $dir . '/payload.json';
    $dados['raiz'] = raizProjetos();
    file_put_contents($tmp, json_encode($dados, JSON_UNESCAPED_UNICODE));
    $env = 'CIENTOMETRIA_PROJETOS=' . escapeshellarg(raizProjetos());
    if ($dirUpload !== null) {
      // o Python só aceita importar arquivos de dentro deste diretório
      $env .= ' CIENTOMETRIA_DIR_IMPORTACAO=' . escapeshellarg($dirUpload);
    }
    if ($dirExportacao !== null) {
      // o .zip exportado é gravado só neste diretório temporário (fora do webroot)
      $env .= ' CIENTOMETRIA_DIR_EXPORTACAO=' . escapeshellarg($dirExportacao);
    }
    $tempo = (int)(getenv('CIENTOMETRIA_TEMPO_MAX_S') ?: 3600);
    $cmd = 'cd ' . escapeshellarg(__DIR__) . ' && ' . $env . ' timeout -k 10 ' . ($tempo + 30)
         . ' python3 -m cientometria.api '
         . escapeshellarg($acao) . ' ' . escapeshellarg($tmp) . ' 2>' . escapeshellarg($dir . '/stderr.log');
    $saida = [];
    $rc = 0;
    exec($cmd, $saida, $rc);
  } finally {
    seg_remover_diretorio($dir);
  }
  $linhas = array_values(array_filter($saida, 'strlen'));
  $json = $linhas ? json_decode(end($linhas), true) : null;
  if ($json === null) {
    seg_negar(500, 'Resposta inválida do motor Python.');
  }
  if ($rc !== 0) {
    http_response_code(422);
  }
  return $json;
}

seg_exigir_post_protegido();

$acao = $_GET['acao'] ?? '';
if (!is_string($acao) || !in_array($acao, ACOES, true)) {
  seg_negar(400, 'Ação inválida.');
}

if ($acao === 'importar_execucao') {
  // Upload de um pacote .zip de execução: um único arquivo .zip, limite próprio.
  $projeto = $_POST['projeto'] ?? '';
  if (!is_string($projeto) || !preg_match(PROJETO_RX, $projeto)) {
    seg_negar(400, 'Projeto inválido.');
  }
  $dir = seg_diretorio_temporario('upz_');
  try {
    $arquivos = seg_receber_uploads($dir, ['zip'], 1, seg_limite_zip());
    $r = chamarPython('importar_execucao', ['projeto' => $projeto, 'arquivo' => $arquivos[0]], $dir);
  } finally {
    seg_remover_diretorio($dir);
  }
  echo json_encode($r, JSON_UNESCAPED_UNICODE);
  exit;
}

if ($acao === 'exportar_execucao') {
  // Gera o .zip num diretório temporário fora do webroot, devolve-o como download e o apaga.
  $corpo = file_get_contents('php://input', false, null, 0, 64 * 1024);
  $d = json_decode($corpo, true);
  $projeto = is_array($d) ? ($d['projeto'] ?? '') : '';
  $id = is_array($d) ? ($d['id'] ?? '') : '';
  $comEntradas = is_array($d) && ($d['incluir_entradas'] ?? false) === true;
  if (!is_string($projeto) || !preg_match(PROJETO_RX, $projeto)) seg_negar(400, 'Projeto inválido.');
  if (!is_string($id) || !preg_match('/^([0-9]{8}T[0-9]{6}Z_)?[0-9a-f]{12}$/', $id)) seg_negar(400, 'Execução inválida.');
  $dir = seg_diretorio_temporario('exp_');
  try {
    $r = chamarPython('exportar_execucao', ['projeto' => $projeto, 'id' => $id, 'incluir_entradas' => $comEntradas],
                      null, $dir);
    if (isset($r['erro'])) {
      echo json_encode($r, JSON_UNESCAPED_UNICODE);
      return;
    }
    $nome = $r['arquivo'] ?? '';
    if (!is_string($nome) || !preg_match('/^[0-9]{8}T[0-9]{6}Z_[0-9a-f]{12}(_com_entradas)?\.zip$/', $nome)) {
      seg_negar(500, 'Resposta inválida do motor Python.');
    }
    $alvo = realpath($dir . '/' . $nome);
    $base = realpath($dir);
    if ($alvo === false || $base === false || dirname($alvo) !== $base || !is_file($alvo) || is_link($dir . '/' . $nome)) {
      seg_negar(500, 'Pacote não gerado.');
    }
    header('Content-Type: application/zip');
    header('Content-Disposition: attachment; filename="' . $nome . '"');
    header('Cache-Control: private, no-store');
    header('Content-Length: ' . filesize($alvo));
    header('X-Cientometria-Sha256: ' . preg_replace('/[^0-9a-f]/', '', (string)($r['sha256'] ?? '')));
    header('X-Cientometria-Sha256-Manifesto: ' . preg_replace('/[^0-9a-f]/', '', (string)($r['sha256_manifesto'] ?? '')));
    header('X-Cientometria-Entradas: ' . (int)($r['entradas_incluidas'] ?? 0));
    readfile($alvo);
  } finally {
    seg_remover_diretorio($dir);
  }
  return;
}

if ($acao === 'importar') {
  $projeto = $_POST['projeto'] ?? '';
  if (!is_string($projeto) || !preg_match(PROJETO_RX, $projeto)) {
    seg_negar(400, 'Projeto inválido.');
  }
  $base = $_POST['base'] ?? '';
  $bases = ['', 'lens', 'scopus', 'ieee', 'scielo', 'wos', 'openalex', 'ris', 'bibtex', 'generico'];
  if (!in_array($base, $bases, true)) seg_negar(400, 'Tipo de base inválido.');
  $dir = seg_diretorio_temporario('up_');
  try {
    $arquivos = seg_receber_uploads($dir);
    foreach ($arquivos as &$a) { $a['base'] = $base !== '' ? $base : null; }
    unset($a);
    $r = chamarPython('importar', ['projeto' => $projeto, 'arquivos' => $arquivos], $dir);
  } finally {
    seg_remover_diretorio($dir);
  }
  echo json_encode($r, JSON_UNESCAPED_UNICODE);
  exit;
}

$corpo = file_get_contents('php://input', false, null, 0, 1024 * 1024);
$dados = json_decode($corpo, true);
if (!is_array($dados)) $dados = [];
unset($dados['raiz'], $dados['arquivos_caminho']);
echo json_encode(chamarPython($acao, $dados), JSON_UNESCAPED_UNICODE);
