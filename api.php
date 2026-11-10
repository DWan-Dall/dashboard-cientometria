<?php
// Ponte HTTP -> `python3 -m cientometria.api <acao> <payload.json>`.
// Nenhum cálculo científico é feito aqui: este arquivo só recebe uploads e repassa JSON.
header('Content-Type: application/json; charset=utf-8');
ini_set('display_errors', '0');

const ACOES = ['listar_projetos', 'criar_projeto', 'projeto', 'atualizar_projeto', 'importar', 'remover_arquivo',
               'diagnosticar', 'executar', 'execucoes', 'execucao', 'comparar', 'reproduzir', 'comparar_modos'];

function falhar($codigo, $msg) {
  http_response_code($codigo);
  echo json_encode(['erro' => $msg], JSON_UNESCAPED_UNICODE);
  exit;
}

function raizProjetos() {
  $r = getenv('CIENTOMETRIA_PROJETOS');
  return $r ? $r : __DIR__ . '/projetos';
}

function chamarPython($acao, $dados) {
  $tmp = sys_get_temp_dir() . '/' . uniqid('cient_', true) . '.json';
  $dados['raiz'] = raizProjetos();
  file_put_contents($tmp, json_encode($dados, JSON_UNESCAPED_UNICODE));
  $cmd = 'cd ' . escapeshellarg(__DIR__) . ' && CIENTOMETRIA_PROJETOS=' . escapeshellarg(raizProjetos())
       . ' python3 -m cientometria.api ' . escapeshellarg($acao) . ' ' . escapeshellarg($tmp) . ' 2>&1';
  $saida = [];
  $rc = 0;
  exec($cmd, $saida, $rc);
  @unlink($tmp);
  $txt = trim(implode("\n", $saida));
  // a última linha é o JSON (avisos de bibliotecas podem vir antes)
  $linhas = explode("\n", $txt);
  $json = json_decode(end($linhas), true);
  if ($json === null) {
    falhar(500, 'Resposta inválida do motor Python: ' . substr($txt, 0, 800));
  }
  if ($rc !== 0) {
    http_response_code(422);
  }
  return $json;
}

if ($_SERVER['REQUEST_METHOD'] !== 'POST') {
  falhar(405, 'Use POST.');
}
$acao = $_GET['acao'] ?? '';
if (!in_array($acao, ACOES, true)) {
  falhar(400, 'Ação inválida.');
}

if ($acao === 'importar') {
  if (!isset($_FILES['files'])) falhar(400, 'Nenhum arquivo enviado.');
  $projeto = $_POST['projeto'] ?? '';
  $base = $_POST['base'] ?? '';
  $dir = sys_get_temp_dir() . '/' . uniqid('up_', true);
  mkdir($dir, 0700, true);
  $arquivos = [];
  for ($i = 0; $i < count($_FILES['files']['name']); $i++) {
    if ($_FILES['files']['error'][$i] !== UPLOAD_ERR_OK) continue;
    $nome = preg_replace('/[^a-zA-Z0-9._-]/', '_', basename($_FILES['files']['name'][$i]));
    $destino = $dir . '/' . $i . '_' . $nome;
    if (move_uploaded_file($_FILES['files']['tmp_name'][$i], $destino)) {
      $arquivos[] = ['caminho' => $destino, 'nome' => $nome, 'base' => $base !== '' ? $base : null];
    }
  }
  if (!$arquivos) falhar(400, 'Falha no upload (verifique upload_max_filesize/post_max_size).');
  $r = chamarPython('importar', ['projeto' => $projeto, 'arquivos' => $arquivos]);
  foreach ($arquivos as $a) @unlink($a['caminho']);
  @rmdir($dir);
  echo json_encode($r, JSON_UNESCAPED_UNICODE);
  exit;
}

$dados = json_decode(file_get_contents('php://input'), true);
if (!is_array($dados)) $dados = [];
unset($dados['raiz']);
echo json_encode(chamarPython($acao, $dados), JSON_UNESCAPED_UNICODE);
