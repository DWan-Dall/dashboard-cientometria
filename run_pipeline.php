<?php
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
  http_response_code(413);
  echo json_encode([
    'error' => 'Arquivo(s) excedem o limite de upload do PHP.',
    'details' => 'Aumente post_max_size/upload_max_filesize (ex.: 128M).'
  ], JSON_UNESCAPED_UNICODE);
  exit;
}

if ($_SERVER['REQUEST_METHOD'] !== 'POST') {
  http_response_code(405);
  echo json_encode(['error' => 'Método não permitido']);
  exit;
}

if (!isset($_FILES['files'])) {
  http_response_code(400);
  echo json_encode(['error' => 'Nenhum arquivo enviado.']);
  exit;
}

$engine = $_POST['engine'] ?? 'python';
$engine = in_array($engine, ['python', 'r'], true) ? $engine : 'python';

$paramsRaw = $_POST['params'] ?? '{}';
$params = json_decode($paramsRaw, true);
if (!is_array($params)) { $params = []; }

$uploadDir = __DIR__ . '/tmp_uploads';
$plotDir = $uploadDir . '/plots';
if (!is_dir($plotDir)) {
  mkdir($plotDir, 0777, true);
}

$paths = [];
$names = $_FILES['files']['name'];
$tmpNames = $_FILES['files']['tmp_name'];
$errors = $_FILES['files']['error'];

for ($i = 0; $i < count($names); $i++) {
  if ($errors[$i] !== UPLOAD_ERR_OK) {
    continue;
  }
  $safeName = preg_replace('/[^a-zA-Z0-9._-]/', '_', basename($names[$i]));
  $target = $uploadDir . '/' . uniqid('upl_', true) . '_' . $safeName;
  if (move_uploaded_file($tmpNames[$i], $target)) {
    $paths[] = $target;
  }
}

if (count($paths) === 0) {
  http_response_code(400);
  echo json_encode(['error' => 'Falha no upload dos arquivos.']);
  exit;
}

$payloadPath = $uploadDir . '/' . uniqid('payload_', true) . '.json';
$payload = [
  'files' => $paths,
  'plot_dir' => $plotDir,
  'plot_url_prefix' => 'tmp_uploads/plots',
  'params' => $params
];
file_put_contents($payloadPath, json_encode($payload, JSON_UNESCAPED_UNICODE));

$stderrPath = $uploadDir . '/' . uniqid('stderr_', true) . '.log';
if ($engine === 'r') {
  $cmd = 'Rscript ' . escapeshellarg(__DIR__ . '/scripts/pipeline.R') . ' ' . escapeshellarg($payloadPath) . ' 2>' . escapeshellarg($stderrPath);
} else {
  $cmd = 'python3 ' . escapeshellarg(__DIR__ . '/scripts/pipeline.py') . ' ' . escapeshellarg($payloadPath) . ' 2>' . escapeshellarg($stderrPath);
}

$output = [];
$returnVar = 0;
exec($cmd, $output, $returnVar);
$stderr = file_exists($stderrPath) ? trim(file_get_contents($stderrPath)) : '';
@unlink($stderrPath);

foreach ($paths as $p) {
  @unlink($p);
}
@unlink($payloadPath);

if ($returnVar !== 0) {
  http_response_code(500);
  $msg = trim(implode("\n", $output));
  if ($stderr !== '') {
    $msg = $msg !== '' ? $msg . "\n" . $stderr : $stderr;
  }
  echo json_encode(['error' => "Falha no pipeline ({$engine}): " . $msg]);
  exit;
}

$json = trim(implode("\n", $output));
if ($json === '') {
  http_response_code(500);
  echo json_encode(['error' => 'Pipeline não retornou conteúdo JSON.']);
  exit;
}

$decoded = json_decode($json, true);
if (!$decoded) {
  http_response_code(500);
  echo json_encode([
    'error' => 'Resposta inválida do pipeline.',
    'raw_output_preview' => substr($json, 0, 500),
    'stderr_preview' => substr($stderr, 0, 500)
  ], JSON_UNESCAPED_UNICODE);
  exit;
}

echo json_encode($decoded, JSON_UNESCAPED_UNICODE);
