<?php
// Ponte HTTP -> `python3 -m cientometria.api <acao> <payload.json>`.
// Nenhum cálculo científico é feito aqui: este arquivo só recebe uploads e repassa JSON.
// Segurança: ver seguranca.php (autenticação/loopback, origem, CSRF, limites de upload).
require __DIR__ . '/seguranca.php';
header('Content-Type: application/json; charset=utf-8');
ini_set('display_errors', '0');

const ACOES = ['listar_projetos', 'criar_projeto', 'projeto', 'atualizar_projeto', 'importar', 'remover_arquivo',
               'diagnosticar', 'executar', 'execucoes', 'execucao', 'comparar', 'reproduzir', 'comparar_modos',
               'verificar_execucao'];

function raizProjetos() {
  $r = getenv('CIENTOMETRIA_PROJETOS');
  return $r ? $r : __DIR__ . '/projetos';
}

function chamarPython($acao, $dados, $dirUpload = null) {
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
    $cmd = 'cd ' . escapeshellarg(__DIR__) . ' && ' . $env . ' python3 -m cientometria.api '
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

$corpo = file_get_contents('php://input', false, null, 0, 1024 * 1024);
$dados = json_decode($corpo, true);
if (!is_array($dados)) $dados = [];
unset($dados['raiz'], $dados['arquivos_caminho']);
echo json_encode(chamarPython($acao, $dados), JSON_UNESCAPED_UNICODE);
