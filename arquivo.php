<?php
// Serve gráficos e relatórios de uma execução. Só caminhos dentro de
// <projetos>/<projeto>/execucoes/<execucao>/(graficos|relatorios)/...
ini_set('display_errors', '0');
$raiz = getenv('CIENTOMETRIA_PROJETOS') ?: __DIR__ . '/projetos';
$projeto = $_GET['projeto'] ?? '';
$execucao = $_GET['execucao'] ?? '';
$caminho = $_GET['caminho'] ?? '';
if (!preg_match('/^[a-z0-9-]+$/', $projeto) || !preg_match('/^[A-Za-z0-9_]+$/', $execucao)
    || !preg_match('#^(graficos|relatorios)/[A-Za-z0-9_./-]+$#', $caminho) || strpos($caminho, '..') !== false) {
  http_response_code(400);
  exit('Parâmetros inválidos');
}
$base = realpath($raiz . '/' . $projeto . '/execucoes/' . $execucao);
$alvo = realpath($raiz . '/' . $projeto . '/execucoes/' . $execucao . '/' . $caminho);
if ($base === false || $alvo === false || strpos($alvo, $base . DIRECTORY_SEPARATOR) !== 0 || !is_file($alvo)) {
  http_response_code(404);
  exit('Não encontrado');
}
$tipos = ['png' => 'image/png', 'pdf' => 'application/pdf', 'csv' => 'text/csv; charset=utf-8',
          'md' => 'text/markdown; charset=utf-8', 'json' => 'application/json',
          'xlsx' => 'application/vnd.openxmlformats-officedocument.spreadsheetml.sheet'];
$ext = strtolower(pathinfo($alvo, PATHINFO_EXTENSION));
header('Content-Type: ' . ($tipos[$ext] ?? 'application/octet-stream'));
if ($ext !== 'png') {
  header('Content-Disposition: attachment; filename="' . basename($alvo) . '"');
}
header('Content-Length: ' . filesize($alvo));
readfile($alvo);
