<?php
// Ponte HTTP -> `python3 -m cientometria.api <acao> <payload.json>`.
// Nenhum cálculo científico é feito aqui: este arquivo só recebe uploads e repassa JSON.
// Segurança: ver seguranca.php (autenticação/loopback, origem, CSRF, limites de upload).
require __DIR__ . '/seguranca.php';
header('Content-Type: application/json; charset=utf-8');
ini_set('display_errors', '0');

const ACOES = ['listar_projetos', 'criar_projeto', 'projeto', 'atualizar_projeto', 'importar', 'remover_arquivo',
               'diagnosticar', 'executar', 'execucoes', 'execucao', 'comparar', 'reproduzir', 'comparar_modos',
               'verificar_execucao', 'inventario_execucao', 'exportar_execucao', 'receber_pacote',
               'inspecionar_pacote', 'restaurar_pacote', 'descartar_pacote', 'reexecutar'];

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
      // o Python só grava o pacote dentro deste diretório
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

if ($acao === 'importar') {
  $projeto = $_POST['projeto'] ?? '';
  if (!is_string($projeto) || !preg_match('/^[a-z0-9][a-z0-9-]{0,80}$/', $projeto)) {
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

function projetoValido($p) {
  return is_string($p) && preg_match('/^[a-z0-9][a-z0-9-]{0,80}$/', $p);
}

if ($acao === 'receber_pacote') {
  $projeto = $_POST['projeto'] ?? '';
  if (!projetoValido($projeto)) seg_negar(400, 'Projeto inválido.');
  $dir = seg_diretorio_temporario('pk_');
  try {
    $zip = seg_receber_pacote($dir);
    $r = chamarPython('receber_pacote', ['projeto' => $projeto, 'caminho' => $zip], $dir);
  } finally {
    seg_remover_diretorio($dir);
  }
  echo json_encode($r, JSON_UNESCAPED_UNICODE);
  exit;
}

$corpo = file_get_contents('php://input', false, null, 0, 1024 * 1024);
$dados = json_decode($corpo, true);
if (!is_array($dados)) $dados = [];
unset($dados['raiz'], $dados['arquivos_caminho'], $dados['destino'], $dados['caminho']);

if ($acao === 'exportar_execucao') {
  // devolve o ZIP como download; erros continuam em JSON
  if (!projetoValido($dados['projeto'] ?? null) || !is_string($dados['id'] ?? null)
      || !preg_match('/^[0-9a-f]{12}$/', $dados['id'])) {
    seg_negar(400, 'Projeto ou execução inválidos.');
  }
  $dir = seg_diretorio_temporario('ex_');
  try {
    $dados['destino'] = $dir;
    $r = chamarPython('exportar_execucao', $dados, null, $dir);
    if (isset($r['erro'])) { echo json_encode($r, JSON_UNESCAPED_UNICODE); exit; }
    $arq = realpath((string)($r['arquivo'] ?? ''));
    $base = realpath($dir);
    $nome = basename((string)$arq);
    if ($arq === false || $base === false || strpos($arq, $base . DIRECTORY_SEPARATOR) !== 0 || !is_file($arq)
        || !preg_match('/^execucao_[0-9a-f]{12}_[a-z0-9-]{1,81}(_sem-entradas)?\.zip$/', $nome)) {
      seg_negar(500, 'Pacote inválido.');
    }
    header('Content-Type: application/zip');
    header('Content-Disposition: attachment; filename="' . $nome . '"');
    header('Content-Length: ' . filesize($arq));
    header('X-Pacote-SHA256: ' . preg_replace('/[^0-9a-f]/', '', (string)($r['sha256'] ?? '')));
    header('Cache-Control: no-store');
    readfile($arq);
  } finally {
    seg_remover_diretorio($dir);
  }
  exit;
}

echo json_encode(chamarPython($acao, $dados), JSON_UNESCAPED_UNICODE);
