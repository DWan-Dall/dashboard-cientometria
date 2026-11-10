<?php
// Serve gráficos e relatórios de uma execução. Só caminhos dentro de
// <projetos>/<projeto>/execucoes/<execucao>/(graficos|relatorios)/...
// Exige a mesma autenticação/política de acesso das páginas (seguranca.php).
require __DIR__ . '/seguranca.php';
ini_set('display_errors', '0');
seg_cabecalhos(false);
seg_autenticar(false);
if ($_SERVER['REQUEST_METHOD'] !== 'GET') seg_negar(405, 'Use GET.', false);

$raiz = getenv('CIENTOMETRIA_PROJETOS') ?: __DIR__ . '/projetos';
$projeto = $_GET['projeto'] ?? '';
$execucao = $_GET['execucao'] ?? '';
$caminho = $_GET['caminho'] ?? '';
if (!is_string($projeto) || !is_string($execucao) || !is_string($caminho)
    || !preg_match('/^[a-z0-9][a-z0-9-]{0,80}$/', $projeto)
    || !preg_match('/^[0-9]{8}T[0-9]{6}Z_[0-9a-f]{12}$/', $execucao)
    || !preg_match('#^(graficos|relatorios)/[A-Za-z0-9_-]+(/[A-Za-z0-9_-]+)*\.(png|pdf|csv|md|json|xlsx)$#', $caminho)) {
  seg_negar(400, 'Parâmetros inválidos', false);
}
$base = realpath($raiz . '/' . $projeto . '/execucoes/' . $execucao);
$alvo = realpath($raiz . '/' . $projeto . '/execucoes/' . $execucao . '/' . $caminho);
if ($base === false || $alvo === false || strpos($alvo, $base . DIRECTORY_SEPARATOR) !== 0 || !is_file($alvo)) {
  seg_negar(404, 'Não encontrado', false);
}
$tipos = ['png' => 'image/png', 'pdf' => 'application/pdf', 'csv' => 'text/csv; charset=utf-8',
          'md' => 'text/markdown; charset=utf-8', 'json' => 'application/json',
          'xlsx' => 'application/vnd.openxmlformats-officedocument.spreadsheetml.sheet'];
$ext = strtolower(pathinfo($alvo, PATHINFO_EXTENSION));
header('Content-Type: ' . $tipos[$ext]);
header('Cache-Control: private, no-store');
if ($ext !== 'png') {
  header('Content-Disposition: attachment; filename="' . basename($alvo) . '"');
}
header('Content-Length: ' . filesize($alvo));
readfile($alvo);
