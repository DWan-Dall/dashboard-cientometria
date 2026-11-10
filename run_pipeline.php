<?php
// Triagem rápida (sem projeto): recebe arquivos e repassa a scripts/pipeline.py.
// A triagem tem uma única implementação: o pacote Python `cientometria`.
// O antigo motor R (scripts/pipeline.R) implementava regras próprias e foi desativado.
require __DIR__ . '/seguranca.php';
header('Content-Type: application/json; charset=utf-8');
ini_set('display_errors', '0');

function parseSizeToBytes($value) {
  $value = trim($value);
  $unit = strtolower(substr($value, -1));
  $num = (float)$value;
  switch ($unit) {
    case 'g': return (int)($num * 1024 * 1024 * 1024);
    case 'm': return (int)($num * 1024 * 1024);
    case 'k': return (int)($num * 1024);
    default: return (int)$num;
  }
}

$contentLength = (int)($_SERVER['CONTENT_LENGTH'] ?? 0);
$postMax = parseSizeToBytes(ini_get('post_max_size'));
if ($postMax > 0 && $contentLength > $postMax) {
  seg_negar(413, 'Arquivo(s) excedem o limite de upload do PHP (post_max_size/upload_max_filesize).');
}

seg_exigir_post_protegido();

$engine = $_POST['engine'] ?? 'python';
if ($engine !== 'python') {
  seg_negar(400, 'Motor R desativado para a triagem: o método só é executado pelo pacote Python cientometria (ver ARCHITECTURE.md).');
}

$params = json_decode($_POST['params'] ?? '{}', true);
if (!is_array($params)) { $params = []; }

// Uploads e payload ficam FORA do diretório servido pela web.
$dir = seg_diretorio_temporario('rapida_');
try {
  $arquivos = seg_receber_uploads($dir);
  $payloadPath = $dir . '/payload.json';
  file_put_contents($payloadPath, json_encode([
    'files' => array_column($arquivos, 'caminho'),
    'names' => array_column($arquivos, 'nome'),   // nome original: tipo de base e ordem canônica
    'params' => $params,
  ], JSON_UNESCAPED_UNICODE));

  $stderrPath = $dir . '/stderr.log';
  $cmd = 'cd ' . escapeshellarg(__DIR__) . ' && python3 ' . escapeshellarg(__DIR__ . '/scripts/pipeline.py') . ' '
       . escapeshellarg($payloadPath) . ' 2>' . escapeshellarg($stderrPath);
  $output = [];
  $returnVar = 0;
  exec($cmd, $output, $returnVar);
  $stderr = file_exists($stderrPath) ? trim(file_get_contents($stderrPath)) : '';
} finally {
  seg_remover_diretorio($dir);
}

if ($returnVar !== 0) {
  // a última linha do stderr costuma ter a mensagem útil; não devolve caminhos completos
  $linhas = array_values(array_filter(explode("\n", $stderr)));
  $ultima = $linhas ? end($linhas) : 'erro desconhecido';
  $ultima = str_replace([$dir, __DIR__], ['<tmp>', '<app>'], $ultima);
  seg_negar(500, 'Falha no pipeline: ' . substr($ultima, 0, 500));
}

$json = trim(implode("\n", $output));
$decoded = json_decode($json, true);
if (!$decoded) {
  seg_negar(500, 'Resposta inválida do pipeline.');
}
echo json_encode($decoded, JSON_UNESCAPED_UNICODE);
