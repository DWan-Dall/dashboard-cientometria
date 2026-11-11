<?php
// Camada de segurança comum a todas as páginas e endpoints.
//
// - Cabeçalhos de segurança e CSP com nonce (sem scripts inline sem nonce).
// - Sessão com cookie HttpOnly/SameSite=Strict e token CSRF obrigatório em POST.
// - Origin/Referer, quando presentes, precisam ser do próprio host.
// - Acesso: sem credenciais configuradas, só clientes locais (loopback) são aceitos.
//   Para acesso de outra máquina/rede, configure CIENTOMETRIA_USUARIO e
//   CIENTOMETRIA_SENHA_HASH (gerado com password_hash) — autenticação HTTP Basic.
//   CIENTOMETRIA_PERMITIR_SEM_SENHA=1 desliga a exigência (use só atrás de porta
//   publicada em 127.0.0.1, como no docker-compose.yml).
// - Cabeçalho Host restrito (contra DNS rebinding): só localhost/127.0.0.1/[::1], salvo os
//   nomes listados em CIENTOMETRIA_HOSTS (separados por vírgula).
// - Requisição com X-Forwarded-For/Forwarded/X-Real-IP (passou por proxy reverso) nunca é
//   tratada como local: atrás de proxy, credenciais são obrigatórias.
//
// Não há regra científica aqui.

if (!defined('CIENTOMETRIA_SEGURANCA')) {
  define('CIENTOMETRIA_SEGURANCA', 1);

  $GLOBALS['CSP_NONCE'] = base64_encode(random_bytes(16));

  function seg_cabecalhos($html = true) {
    header('X-Content-Type-Options: nosniff');
    header('X-Frame-Options: DENY');
    header('Referrer-Policy: same-origin');
    header('Cross-Origin-Opener-Policy: same-origin');
    header('Cross-Origin-Resource-Policy: same-origin');
    if ($html) {
      header("Content-Security-Policy: default-src 'self'; script-src 'nonce-" . $GLOBALS['CSP_NONCE']
        . "'; style-src 'self' 'unsafe-inline'; img-src 'self' data:; connect-src 'self'; object-src 'none'; "
        . "base-uri 'none'; form-action 'self'; frame-ancestors 'none'");
    } else {
      header("Content-Security-Policy: default-src 'none'; frame-ancestors 'none'; sandbox");
    }
  }

  function seg_negar($codigo, $msg, $json = true) {
    http_response_code($codigo);
    if ($json) {
      header('Content-Type: application/json; charset=utf-8');
      echo json_encode(['erro' => $msg, 'error' => $msg], JSON_UNESCAPED_UNICODE);
    } else {
      header('Content-Type: text/plain; charset=utf-8');
      echo $msg;
    }
    exit;
  }

  function seg_via_proxy() {
    foreach (['HTTP_X_FORWARDED_FOR', 'HTTP_FORWARDED', 'HTTP_X_REAL_IP', 'HTTP_X_FORWARDED_HOST'] as $k) {
      if (!empty($_SERVER[$k])) return true;
    }
    return false;
  }

  // Nome de host sem porta, em minúsculas ('[::1]:8000' -> '::1').
  function seg_host_sem_porta($h) {
    $h = strtolower(trim((string)$h));
    if ($h === '') return '';
    if ($h[0] === '[') {
      $fim = strpos($h, ']');
      return $fim === false ? '' : substr($h, 1, $fim - 1);
    }
    $p = strrpos($h, ':');
    return $p === false ? $h : substr($h, 0, $p);
  }

  function seg_host_permitido() {
    $host = seg_host_sem_porta($_SERVER['HTTP_HOST'] ?? '');
    $ok = ['localhost', '127.0.0.1', '::1'];
    $extra = getenv('CIENTOMETRIA_HOSTS');
    if ($extra) {
      foreach (explode(',', $extra) as $h) {
        $h = strtolower(trim($h));
        if ($h !== '') $ok[] = $h;
      }
    }
    return $host !== '' && in_array($host, $ok, true);
  }

  function seg_ip_local() {
    if (seg_via_proxy()) return false;
    $ip = $_SERVER['REMOTE_ADDR'] ?? '';
    return $ip === '127.0.0.1' || $ip === '::1' || strpos($ip, '127.') === 0 || $ip === '::ffff:127.0.0.1';
  }

  function seg_autenticar($json = true) {
    if (!seg_host_permitido()) {
      seg_negar(421, 'Host não permitido. Acesse por localhost/127.0.0.1 ou configure CIENTOMETRIA_HOSTS.', $json);
    }
    $usuario = getenv('CIENTOMETRIA_USUARIO');
    $hash = getenv('CIENTOMETRIA_SENHA_HASH');
    if ($usuario && $hash) {
      $u = $_SERVER['PHP_AUTH_USER'] ?? null;
      $p = $_SERVER['PHP_AUTH_PW'] ?? null;
      if ($u === null && !empty($_SERVER['HTTP_AUTHORIZATION'])
          && stripos($_SERVER['HTTP_AUTHORIZATION'], 'basic ') === 0) {
        $par = explode(':', (string)base64_decode(substr($_SERVER['HTTP_AUTHORIZATION'], 6)), 2);
        if (count($par) === 2) { [$u, $p] = $par; }
      }
      if ($u === null || !hash_equals($usuario, (string)$u) || !password_verify((string)$p, $hash)) {
        header('WWW-Authenticate: Basic realm="Cientometria", charset="UTF-8"');
        seg_negar(401, 'Autenticação necessária.', $json);
      }
      return;
    }
    // Atrás de proxy reverso a senha é sempre exigida, mesmo com CIENTOMETRIA_PERMITIR_SEM_SENHA=1.
    if (!seg_ip_local() && (getenv('CIENTOMETRIA_PERMITIR_SEM_SENHA') !== '1' || seg_via_proxy())) {
      seg_negar(403, 'Acesso remoto sem credenciais bloqueado. Configure CIENTOMETRIA_USUARIO e '
        . 'CIENTOMETRIA_SENHA_HASH (ver README).', $json);
    }
  }

  function seg_sessao() {
    if (session_status() !== PHP_SESSION_ACTIVE) {
      session_name('cientometria_sessao');
      session_set_cookie_params(['lifetime' => 0, 'path' => '/', 'httponly' => true, 'samesite' => 'Strict',
                                 'secure' => (!empty($_SERVER['HTTPS']) && $_SERVER['HTTPS'] !== 'off')]);
      session_start();
    }
    if (empty($_SESSION['csrf'])) {
      $_SESSION['csrf'] = bin2hex(random_bytes(32));
    }
    return $_SESSION['csrf'];
  }

  function seg_token_csrf() {
    return seg_sessao();
  }

  function seg_origem_valida() {
    $host = $_SERVER['HTTP_HOST'] ?? '';
    foreach (['HTTP_ORIGIN', 'HTTP_REFERER'] as $k) {
      if (!empty($_SERVER[$k])) {
        $h = parse_url($_SERVER[$k], PHP_URL_HOST);
        $p = parse_url($_SERVER[$k], PHP_URL_PORT);
        $origem = $h . ($p ? ':' . $p : '');
        return $host !== '' && strcasecmp($origem, $host) === 0;
      }
    }
    return true;  // clientes sem Origin/Referer (ex.: CLI) ainda precisam do token
  }

  // Para endpoints que alteram estado (POST): autenticação + origem + CSRF.
  function seg_exigir_post_protegido() {
    seg_cabecalhos(false);
    seg_autenticar(true);
    if ($_SERVER['REQUEST_METHOD'] !== 'POST') {
      seg_negar(405, 'Use POST.');
    }
    if (!seg_origem_valida()) {
      seg_negar(403, 'Origem da requisição não permitida.');
    }
    $token = seg_sessao();
    $enviado = $_SERVER['HTTP_X_CSRF_TOKEN'] ?? '';
    session_write_close();  // não segura o lock da sessão durante execuções longas
    if (!is_string($enviado) || !hash_equals($token, $enviado)) {
      seg_negar(403, 'Token CSRF ausente ou inválido. Recarregue a página.');
    }
  }

  // Para páginas HTML.
  function seg_pagina() {
    seg_cabecalhos(true);
    seg_autenticar(false);
    $t = seg_sessao();
    session_write_close();
    return $t;
  }

  function seg_nonce() {
    return $GLOBALS['CSP_NONCE'];
  }

  // Limites de upload (bytes por arquivo e número de arquivos).
  function seg_limites() {
    $mb = (int)(getenv('CIENTOMETRIA_MAX_MB_ARQUIVO') ?: 200);
    $n = (int)(getenv('CIENTOMETRIA_MAX_ARQUIVOS') ?: 50);
    return [$mb * 1024 * 1024, $n];
  }

  function seg_diretorio_temporario($prefixo) {
    $base = getenv('CIENTOMETRIA_DIR_UPLOAD') ?: sys_get_temp_dir() . '/cientometria_upload';
    if (!is_dir($base)) { @mkdir($base, 0700, true); }
    $dir = $base . '/' . $prefixo . bin2hex(random_bytes(8));
    if (!mkdir($dir, 0700)) {
      seg_negar(500, 'Falha ao criar diretório temporário.');
    }
    return $dir;
  }

  function seg_remover_diretorio($dir) {
    if (!is_dir($dir)) return;
    foreach (scandir($dir) as $f) {
      if ($f === '.' || $f === '..') continue;
      $p = $dir . '/' . $f;
      is_dir($p) && !is_link($p) ? seg_remover_diretorio($p) : @unlink($p);
    }
    @rmdir($dir);
  }

  // Recebe $_FILES['files'] com validação de nome, extensão, tamanho e quantidade.
  function seg_receber_uploads($dir) {
    if (!isset($_FILES['files']) || !is_array($_FILES['files']['name'])) {
      seg_negar(400, 'Nenhum arquivo enviado.');
    }
    [$max, $maxN] = seg_limites();
    $ext_ok = ['csv', 'tsv', 'txt', 'xlsx', 'xls', 'ris', 'bib', 'bibtex', 'nbib'];
    $n = count($_FILES['files']['name']);
    if ($n > $maxN) seg_negar(413, "Máximo de $maxN arquivos por envio.");
    $saida = [];
    for ($i = 0; $i < $n; $i++) {
      $erro = $_FILES['files']['error'][$i];
      if ($erro !== UPLOAD_ERR_OK) {
        seg_negar(400, "Falha no upload do arquivo " . ($i + 1) . " (código $erro).");
      }
      $nome = preg_replace('/[^A-Za-z0-9._-]/', '_', basename((string)$_FILES['files']['name'][$i]));
      $nome = ltrim($nome, '.');
      if ($nome === '' || strlen($nome) > 150) seg_negar(400, 'Nome de arquivo inválido.');
      $ext = strtolower(pathinfo($nome, PATHINFO_EXTENSION));
      if (!in_array($ext, $ext_ok, true)) seg_negar(415, "Extensão não aceita: .$ext");
      $tam = (int)$_FILES['files']['size'][$i];
      if ($tam <= 0 || $tam > $max) seg_negar(413, "Arquivo vazio ou maior que o limite: $nome");
      $destino = $dir . '/' . sprintf('%03d', $i) . '_' . $nome;
      if (!is_uploaded_file($_FILES['files']['tmp_name'][$i])
          || !move_uploaded_file($_FILES['files']['tmp_name'][$i], $destino)) {
        seg_negar(400, "Falha ao receber $nome.");
      }
      @chmod($destino, 0600);
      $saida[] = ['caminho' => $destino, 'nome' => $nome];
    }
    return $saida;
  }
}
