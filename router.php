<?php
// Roteador do servidor embutido do PHP:  php -S 127.0.0.1:8000 router.php
// Só os pontos de entrada abaixo são servidos. Todo o resto (projetos/ com dados
// licenciados, .git, código-fonte, testes, tmp_uploads/) responde 404.
$caminho = parse_url($_SERVER['REQUEST_URI'] ?? '/', PHP_URL_PATH) ?: '/';
$caminho = rawurldecode($caminho);
$permitidos = ['/' => 'index.php', '/index.php' => 'index.php', '/triagem_rapida.php' => 'triagem_rapida.php',
               '/api.php' => 'api.php', '/arquivo.php' => 'arquivo.php', '/run_pipeline.php' => 'run_pipeline.php'];
// bibliotecas JavaScript empacotadas localmente (versão fixa, verificadas por SRI na página)
if ($caminho === '/vendor/chart-4.4.1.umd.js') {
  header('Content-Type: application/javascript; charset=utf-8');
  header('X-Content-Type-Options: nosniff');
  header('Cache-Control: public, max-age=31536000, immutable');
  readfile(__DIR__ . '/vendor/chart-4.4.1.umd.js');
  return true;
}
if (!isset($permitidos[$caminho])) {
  http_response_code(404);
  header('Content-Type: text/plain; charset=utf-8');
  header('X-Content-Type-Options: nosniff');
  echo 'Não encontrado';
  return true;
}
$_SERVER['SCRIPT_NAME'] = '/' . $permitidos[$caminho];
require __DIR__ . '/' . $permitidos[$caminho];
return true;
