<?php
header('Content-Type: application/json; charset=utf-8');

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

$uploadDir = __DIR__ . '/tmp_uploads';
if (!is_dir($uploadDir)) {
  mkdir($uploadDir, 0777, true);
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
file_put_contents($payloadPath, json_encode(['files' => $paths], JSON_UNESCAPED_UNICODE));

$cmd = 'python3 ' . escapeshellarg(__DIR__ . '/scripts/pipeline.py') . ' ' . escapeshellarg($payloadPath) . ' 2>&1';
$output = [];
$returnVar = 0;
exec($cmd, $output, $returnVar);

foreach ($paths as $p) {
  @unlink($p);
}
@unlink($payloadPath);

if ($returnVar !== 0) {
  http_response_code(500);
  echo json_encode(['error' => "Falha no pipeline: " . implode("\n", $output)]);
  exit;
}

$json = implode("\n", $output);
$decoded = json_decode($json, true);
if (!$decoded) {
  http_response_code(500);
  echo json_encode(['error' => 'Resposta inválida do pipeline.']);
  exit;
}

echo json_encode($decoded, JSON_UNESCAPED_UNICODE);
