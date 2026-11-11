<?php require __DIR__ . '/seguranca.php'; $csrf = seg_pagina(); ?>
<!doctype html>
<html lang="pt-BR">
<head>
<meta charset="UTF-8" />
<meta name="viewport" content="width=device-width, initial-scale=1.0" />
<meta name="csrf-token" content="<?= htmlspecialchars($csrf, ENT_QUOTES) ?>" />
<title>Plataforma de Cientometria</title>
<style>
  :root { --bg:#0f172a; --card:#111827; --borda:#243041; --muted:#94a3b8; --text:#e5e7eb;
          --ok:#22c55e; --warn:#f59e0b; --bad:#ef4444; --accent:#38bdf8; }
  * { box-sizing: border-box; }
  body { margin:0; font-family: Inter, system-ui, -apple-system, Segoe UI, Roboto, sans-serif;
         background: linear-gradient(180deg,#020617,#0f172a); color:var(--text); }
  .app { display:grid; grid-template-columns: 240px 1fr; min-height:100vh; }
  nav { background:#0b1220; border-right:1px solid var(--borda); padding:16px 10px; position:sticky; top:0; height:100vh; overflow:auto; }
  nav h1 { font-size:16px; margin:4px 8px 4px; }
  nav .proj { font-size:12px; color:var(--muted); margin:0 8px 14px; min-height:16px; }
  nav button { display:block; width:100%; text-align:left; background:none; border:0; color:var(--text);
               padding:9px 10px; border-radius:8px; cursor:pointer; font-size:14px; }
  nav button.ativo { background:#1e293b; color:var(--accent); }
  nav button:disabled { color:#475569; cursor:not-allowed; }
  nav a { display:block; color:var(--muted); font-size:12px; margin:18px 10px 0; }
  main { padding:20px 24px 80px; max-width:1300px; }
  .card { background:rgba(17,24,39,.9); border:1px solid #1f2937; border-radius:14px; padding:16px; margin-bottom:16px; }
  h2 { margin:0 0 12px; font-size:20px; } h3 { margin:14px 0 8px; font-size:15px; }
  p, .small { color:var(--muted); font-size:13px; }
  .grid { display:grid; grid-template-columns:repeat(auto-fill,minmax(150px,1fr)); gap:10px; }
  .kpi { padding:10px; border-radius:10px; background:#0b1220; border:1px solid var(--borda); }
  .kpi .l { color:var(--muted); font-size:12px; } .kpi .v { font-size:24px; font-weight:700; }
  .btn { background:#0ea5e9; color:#06202d; border:0; border-radius:9px; font-weight:700; padding:8px 13px; cursor:pointer; }
  .btn.sec { background:#1e293b; color:var(--text); border:1px solid var(--borda); }
  .btn:disabled { opacity:.5; cursor:not-allowed; }
  input, select, textarea { background:#0b1220; color:var(--text); border:1px solid var(--borda); border-radius:8px; padding:7px; font:inherit; }
  label { font-size:13px; color:#cbd5e1; }
  .row { display:flex; gap:10px; flex-wrap:wrap; align-items:center; margin:8px 0; }
  table { width:100%; border-collapse:collapse; font-size:12.5px; }
  th, td { border-bottom:1px solid #1f2937; padding:6px; text-align:left; vertical-align:top; }
  th { color:#cbd5e1; position:sticky; top:0; background:#111827; }
  .tabela { max-height:420px; overflow:auto; border:1px solid #1f2937; border-radius:10px; }
  .aviso { border-left:4px solid var(--warn); background:#1f1a0b; padding:10px 12px; border-radius:8px; font-size:13px; margin:10px 0; }
  .erro { border-left:4px solid var(--bad); background:#200b0b; padding:10px 12px; border-radius:8px; font-size:13px; }
  .okb { color:var(--ok); } .badb { color:var(--bad); }
  .tag { display:inline-block; padding:2px 7px; border-radius:99px; background:#1e293b; font-size:11px; margin-right:4px; }
  .imgs { display:grid; grid-template-columns:repeat(auto-fill,minmax(420px,1fr)); gap:12px; }
  .imgs img { width:100%; background:white; border-radius:8px; }
  .secao { display:none; } .secao.ativa { display:block; }
  pre { white-space:pre-wrap; font-size:12px; background:#0b1220; padding:10px; border-radius:8px; }
  @media (max-width: 800px) { .app { grid-template-columns:1fr; } nav { position:static; height:auto; } }
</style>
</head>
<body>
<div class="app">
  <nav>
    <h1>Cientometria</h1>
    <div class="proj" id="projAtual">nenhum projeto aberto</div>
    <button data-s="projetos" class="ativo">1. Projetos</button>
    <button data-s="importacao" data-p>2. Importação e diagnóstico</button>
    <button data-s="triagem" data-p>3. Triagem (método)</button>
    <button data-s="robustez" data-p>4. Robustez e modos</button>
    <button data-s="bibliometria" data-p>5. Análises bibliométricas</button>
    <button data-s="execucoes" data-p>6. Execuções e comparação</button>
    <button data-s="relatorios" data-p>7. Relatórios</button>
    <a href="triagem_rapida.php">Triagem rápida (sem projeto) →</a>
  </nav>
  <main>
    <div class="aviso"><b>Aviso metodológico.</b> A triagem é automática (casamento de termos + escore ponderado), sem revisão
      manual registro a registro. Escores 0–100 são relativos ao corpus (min–max). Nenhum modo deve ser escolhido para atingir uma
      quantidade predeterminada de artigos. Todos os cálculos são feitos pelo pacote Python <code>cientometria</code>.</div>
    <div id="msg"></div>

    <!-- 1. PROJETOS -->
    <section class="secao ativa" id="s-projetos">
      <div class="card"><h2>Projetos</h2>
        <div class="row">
          <input id="pNome" placeholder="Nome do projeto" style="min-width:260px">
          <input id="pDesc" placeholder="Descrição" style="flex:1; min-width:260px">
          <input id="pFontes" placeholder="Fontes bibliográficas (ex.: Scopus, Lens)" style="min-width:260px">
          <button class="btn" id="btCriar">Criar projeto</button>
        </div>
        <div class="tabela" id="tbProjetos"></div>
      </div>
      <div class="card" id="cardProjeto" style="display:none"><h2 id="tProjeto"></h2><div id="infoProjeto"></div>
        <h3>Histórico</h3><div class="tabela" id="tbHistorico"></div></div>
    </section>

    <!-- 2. IMPORTAÇÃO -->
    <section class="secao" id="s-importacao">
      <div class="card"><h2>Importação</h2>
        <p>Formatos: CSV, TSV, TXT, XLSX, RIS, BibTeX e WoS (texto). Bases identificadas automaticamente pelas colunas: Scopus, Web of
          Science, Lens, IEEE Xplore, SciELO, OpenAlex; outras usam o mapeamento genérico. Cada arquivo é guardado com seu SHA-256 e
          nunca é sobrescrito. Para reproduzir o artigo, use os 8 nomes originais (ex.: <code>lens-export.csv</code>).</p>
        <div class="row">
          <input type="file" id="fArquivos" multiple accept=".csv,.tsv,.txt,.xlsx,.xls,.ris,.bib,.bibtex,.nbib">
          <label>Tipo de base: <select id="fBase"><option value="">detectar</option><option>lens</option><option>scopus</option>
            <option>ieee</option><option>scielo</option><option>wos</option><option>openalex</option><option>generico</option></select></label>
          <button class="btn" id="btImportar">Importar</button>
        </div>
        <div class="tabela" id="tbArquivos"></div>
      </div>
      <div class="card"><h2>Diagnóstico das exportações</h2>
        <div class="row"><label>Leitura conforme o modo: <select id="dModo"><option value="original">original</option>
          <option value="variante_exclusao">variante_exclusao</option><option value="corrigida">corrigida</option></select></label>
          <button class="btn sec" id="btDiag">Diagnosticar</button></div>
        <div id="diagOut"></div>
      </div>
    </section>

    <!-- 3. TRIAGEM -->
    <section class="secao" id="s-triagem">
      <div class="card"><h2>Executar a triagem</h2>
        <div class="row">
          <label>Modo: <select id="tModo">
            <option value="original">original — reproduz o procedimento de jan/2026</option>
            <option value="variante_exclusao">variante_exclusao — só a exclusão dam/dike/levee muda</option>
            <option value="corrigida">corrigida — correções técnicas (muda os números)</option></select></label>
          <input id="tRotulo" placeholder="Rótulo da execução (opcional)" style="min-width:240px">
        </div>
        <details><summary class="small">Parâmetros (alterar torna a execução “personalizada” e isso fica no manifesto)</summary>
          <div class="row">Pesos: <label>C* <input id="wC" type="number" step="0.01" value="0.35" style="width:70px"></label>
            <label>R* <input id="wR" type="number" step="0.01" value="0.20" style="width:70px"></label>
            <label>T* <input id="wT" type="number" step="0.01" value="0.30" style="width:70px"></label>
            <label>A* <input id="wA" type="number" step="0.01" value="0.15" style="width:70px"></label></div>
          <div class="row">Cortes: <label>Núcleo A ≥ <input id="cA" type="number" value="70" style="width:70px"></label>
            <label>Núcleo B ≥ <input id="cB" type="number" value="50" style="width:70px"></label>
            <label>Periférico ≥ <input id="cP" type="number" value="30" style="width:70px"></label></div>
          <div class="row"><label>Sorteios de sensibilidade <input id="nSens" type="number" value="2000" style="width:90px"></label></div>
          <div class="row"><label><input type="checkbox" id="tPers"> aplicar estes pesos/cortes (senão, os da receita do modo)</label></div>
        </details>
        <div class="row"><textarea id="tObs" rows="2" style="width:100%" placeholder="Justificativa / observações (registradas no manifesto)"></textarea></div>
        <div class="row"><button class="btn" id="btExec">Executar</button><span class="small" id="tStatus"></span></div>
      </div>
      <div id="triagemOut"></div>
    </section>

    <!-- 4. ROBUSTEZ -->
    <section class="secao" id="s-robustez">
      <div class="card"><h2>Comparação entre modos</h2>
        <p>Executa os três modos sobre os mesmos arquivos para mostrar a diferença entre eles (não para escolher um).</p>
        <button class="btn sec" id="btModos">Comparar modos</button><div id="modosOut"></div></div>
      <div class="card"><h2>Diagnósticos e sensibilidade da última execução aberta</h2><div id="robOut"><p>Abra uma execução.</p></div></div>
    </section>

    <!-- 5. BIBLIOMETRIA -->
    <section class="secao" id="s-bibliometria">
      <div class="card"><h2>Análises bibliométricas</h2><p>Calculadas sobre o corpus da execução aberta. Tabelas truncadas em 50 linhas
        (arquivos completos em Relatórios).</p>
        <div class="row"><select id="bSel"></select></div><div id="bibOut"></div></div>
      <div class="card"><h2>Gráficos</h2><div class="imgs" id="imgs"></div></div>
    </section>

    <!-- 6. EXECUÇÕES -->
    <section class="secao" id="s-execucoes">
      <div class="card"><h2>Execuções do projeto</h2><div class="tabela" id="tbExec"></div>
        <div class="row"><label>A <select id="cmpA"></select></label><label>B <select id="cmpB"></select></label>
          <button class="btn sec" id="btCmp">Comparar</button></div><div id="cmpOut"></div></div>
      <div class="card"><h2>Exportar / importar execução (.zip)</h2>
        <p>O botão <b>exportar .zip</b> de cada execução gera um único arquivo com a pasta inteira da execução
          (<code>manifesto.json</code> com o SHA-256 de cada saída, corpus, consolidado, diagnósticos, bibliometria,
          gráficos e relatórios) e um <code>LEIA-ME.txt</code> com as instruções de verificação. Entregue o .zip
          completo: arquivos soltos de <code>relatorios/</code> sem o manifesto não são verificáveis.</p>
        <div class="row"><label><input type="checkbox" id="xEntradas"> incluir as exportações de entrada (dados licenciados)</label></div>
        <div class="aviso" id="xAviso" style="display:none"><b>Atenção:</b> as exportações das bases bibliográficas costumam ter
          licença restrita. Só inclua-as se o destinatário puder recebê-las; não publique este .zip.</div>
        <h3>Importar execução</h3>
        <p class="small">A execução importada fica somente leitura e marcada como <span class="tag">importada</span>.
          Cada arquivo é conferido com o SHA-256 do manifesto; pacote adulterado, com caminhos perigosos ou com ID já
          existente no projeto é recusado (nada é sobrescrito).</p>
        <div class="row"><input type="file" id="xZip" accept=".zip,application/zip">
          <button class="btn" id="btImportarExec">Importar execução (.zip)</button></div>
        <div id="xOut"></div></div>
    </section>

    <!-- 7. RELATÓRIOS -->
    <section class="secao" id="s-relatorios">
      <div class="card"><h2>Relatórios da execução aberta</h2><div id="relOut"><p>Abra uma execução.</p></div></div>
    </section>
  </main>
</div>
<script nonce="<?= htmlspecialchars(seg_nonce(), ENT_QUOTES) ?>">
const CSRF = document.querySelector('meta[name="csrf-token"]').content;
const E = {projeto: null, execucao: null, dados: null};
const $ = id => document.getElementById(id);
const esc = v => String(v ?? '').replace(/[&<>"']/g, c => ({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[c]));
const fmt = v => typeof v === 'number' ? v.toLocaleString('pt-BR', {maximumFractionDigits: 3}) : esc(v);

function msg(t, tipo='aviso') { $('msg').innerHTML = t ? `<div class="${tipo}">${t}</div>` : ''; }
async function api(acao, dados = {}, form = null) {
  const h = {'X-CSRF-Token': CSRF};
  const r = await fetch('api.php?acao=' + encodeURIComponent(acao), form ? {method:'POST', headers:h, body:form, credentials:'same-origin'}
    : {method:'POST', headers:{...h, 'Content-Type':'application/json'}, body: JSON.stringify(dados), credentials:'same-origin'});
  const t = await r.text(); let j;
  try { j = JSON.parse(t); } catch (_) { throw new Error('Resposta não-JSON: ' + t.slice(0, 300)); }
  if (j.erro) throw new Error(j.erro);
  return j;
}
function tabela(linhas, colunas) {
  if (!linhas || !linhas.length) return '<p class="small">sem dados</p>';
  colunas = colunas || Object.keys(linhas[0]);
  return `<div class="tabela"><table><thead><tr>${colunas.map(c => `<th>${esc(c)}</th>`).join('')}</tr></thead><tbody>${
    linhas.map(l => `<tr>${colunas.map(c => `<td>${typeof l[c] === 'object' && l[c] !== null ? esc(JSON.stringify(l[c])) : fmt(l[c])}</td>`).join('')}</tr>`).join('')}</tbody></table></div>`;
}
function kpis(obj) { return `<div class="grid">${Object.entries(obj).map(([k, v]) => `<div class="kpi"><div class="l">${esc(k)}</div><div class="v">${fmt(v)}</div></div>`).join('')}</div>`; }
function seguro(fn) { return async (...a) => { try { msg(''); await fn(...a); } catch (e) { msg(esc(e.message), 'erro'); } }; }

document.querySelectorAll('nav button').forEach(b => b.onclick = () => {
  if (b.disabled) return;
  document.querySelectorAll('nav button').forEach(x => x.classList.toggle('ativo', x === b));
  document.querySelectorAll('.secao').forEach(s => s.classList.toggle('ativa', s.id === 's-' + b.dataset.s));
});
function habilitar() { document.querySelectorAll('nav button[data-p]').forEach(b => b.disabled = !E.projeto); }

// ---- projetos ----
const carregarProjetos = seguro(async () => {
  const j = await api('listar_projetos');
  $('tbProjetos').innerHTML = j.projetos.length ? `<table><thead><tr><th>projeto</th><th>descrição</th><th>arquivos</th><th>execuções</th><th></th></tr></thead><tbody>${
    j.projetos.map(p => `<tr><td>${esc(p.nome)}<br><span class="small">${esc(p.slug)}</span></td><td>${esc(p.descricao)}</td><td>${p.n_arquivos}</td><td>${p.n_execucoes}</td>
    <td><button class="btn sec" data-acao="abrirProjeto" data-arg="${esc(p.slug)}">abrir</button></td></tr>`).join('')}</tbody></table>` : '<p class="small">Nenhum projeto.</p>';
});
$('btCriar').onclick = seguro(async () => {
  if (!$('pNome').value.trim()) throw new Error('Informe o nome.');
  const j = await api('criar_projeto', {nome: $('pNome').value, descricao: $('pDesc').value,
    fontes_bibliograficas: $('pFontes').value.split(',').map(s => s.trim()).filter(Boolean)});
  await carregarProjetos(); await abrirProjeto(j.projeto.slug);
});
window.abrirProjeto = seguro(async slug => {
  const j = await api('projeto', {projeto: slug});
  E.projeto = slug; E.info = j; habilitar();
  $('projAtual').textContent = j.projeto.nome;
  $('cardProjeto').style.display = '';
  $('tProjeto').textContent = j.projeto.nome;
  $('infoProjeto').innerHTML = `<p>${esc(j.projeto.descricao)}</p><p class="small">Fontes: ${esc((j.projeto.fontes_bibliograficas || []).join(', ') || '—')} · criado em ${esc(j.projeto.criado_em)}</p>`
    + kpis({arquivos: j.arquivos.filter(a => a.ativo !== false).length, execuções: j.execucoes.length});
  $('tbHistorico').innerHTML = tabela(j.historico.slice().reverse());
  renderArquivos(j.arquivos); renderExecucoes(j.execucoes);
});

// ---- importação ----
function renderArquivos(arqs) {
  $('tbArquivos').innerHTML = arqs.length ? `<table><thead><tr><th>arquivo</th><th>SHA-256</th><th>bytes</th><th>base forçada</th><th>importado em</th><th>situação</th><th></th></tr></thead><tbody>${
    arqs.map(a => `<tr><td>${esc(a.nome)}</td><td><code>${esc(a.sha256.slice(0, 16))}…</code></td><td>${fmt(a.bytes)}</td><td>${esc(a.base || '—')}</td><td>${esc(a.importado_em)}</td>
      <td>${a.ativo === false ? 'desativado' : 'ativo'}</td><td>${a.ativo === false ? '' : `<button class="btn sec" data-acao="desativar" data-arg="${esc(a.id)}">desativar</button>`}</td></tr>`).join('')}</tbody></table>`
    : '<p class="small">Nenhum arquivo importado.</p>';
}
$('btImportar').onclick = seguro(async () => {
  const fs = $('fArquivos').files; if (!fs.length) throw new Error('Selecione arquivos.');
  const fd = new FormData(); for (const f of fs) fd.append('files[]', f);
  fd.append('projeto', E.projeto); fd.append('base', $('fBase').value);
  $('btImportar').disabled = true;
  try { const j = await api('importar', {}, fd); renderArquivos(j.arquivos); msg(`${j.importados.length} arquivo(s) importado(s).`); }
  finally { $('btImportar').disabled = false; }
});
window.desativar = seguro(async id => { const j = await api('remover_arquivo', {projeto: E.projeto, id}); renderArquivos(j.arquivos); });
$('btDiag').onclick = seguro(async () => {
  $('diagOut').innerHTML = '<p class="small">lendo…</p>';
  const j = await api('diagnosticar', {projeto: E.projeto, params: {modo: $('dModo').value}});
  let h = '<h3>Fontes</h3>' + tabela(j.fontes.map(f => ({arquivo: f.arquivo, base: f.rotulo, tipo: f.tipo, deteccao: f.deteccao,
    registros: f.registros, formato: f.formato, leitura: f.leitura, avisos: f.avisos.join('; ')})));
  h += '<h3>Campos usados pela triagem e % ausente</h3>' + tabela(j.campos);
  h += '<h3>Limitações conhecidas das exportações</h3>' + Object.entries(j.limitacoes).map(([b, l]) => `<p><b>${esc(b)}</b>: ${l.map(esc).join(' ') || '—'}</p>`).join('');
  $('diagOut').innerHTML = h;
});

// ---- triagem ----
$('btExec').onclick = seguro(async () => {
  const params = {modo: $('tModo').value, n_sensibilidade: Number($('nSens').value || 0)};
  if ($('tPers').checked) {
    params.weights = {c: +$('wC').value, r: +$('wR').value, t: +$('wT').value, a: +$('wA').value};
    params.thresholds = {nucleo_a: +$('cA').value, nucleo_b: +$('cB').value, periferico: +$('cP').value};
  }
  $('btExec').disabled = true; $('tStatus').textContent = 'executando (pode levar minutos)…';
  try {
    const j = await api('executar', {projeto: E.projeto, params, rotulo: $('tRotulo').value, observacoes: $('tObs').value});
    $('tStatus').textContent = 'concluído: ' + j.manifesto.id;
    mostrarExecucao(j); await abrirProjeto(E.projeto);
  } finally { $('btExec').disabled = false; }
});
function mostrarExecucao(j) {
  E.execucao = j.pasta; E.dados = j;
  const m = j.manifesto, c = m.contagens;
  let h = `<div class="card"><h2>Execução ${esc(m.id)} <span class="tag">${esc(m.modo)}</span><span class="tag">${esc(m.versao_metodo)}</span>${
    m.configuracao_personalizada ? '<span class="tag" style="color:var(--warn)">personalizada</span>' : ''}${
    j.importacao ? '<span class="tag">importada</span>' : ''}</h2>`;
  if (j.importacao) h += `<p class="small">Importada de <code>${esc(j.importacao.arquivo_zip)}</code> em ${esc(j.importacao.importada_em)}
    (SHA-256 do .zip <code>${esc(j.importacao.sha256_zip)}</code>); somente leitura.</p>`;
  h += kpis({registros: c.registros, 'sem DOI': c.sem_doi, 'duplicatas DOI': c.duplicatas_doi, 'após DOI': c.apos_doi,
    únicos: c.unicos, 'núcleo obrigatório': c.nucleo_obrigatorio, candidatos: c.candidatos_antes_da_exclusao,
    'excluídos (candidatos)': c.excluidos_entre_candidatos, corpus: c.corpus, ...m.estratos});
  if (!m.configuracao_personalizada && m.modo === 'original')
    h += `<p class="small">Para conferir com as referências históricas do artigo (16.845 → 11.547 → 2.068 → 13/494/1.508/53) é preciso usar as
      8 exportações originais; ver <code>python -m cientometria referencia</code> e docs/AUDITORIA.md. Divergência é achado a investigar, não meta.</p>`;
  if (Object.keys(m.alteracoes_em_relacao_a_receita || {}).length)
    h += '<h3>Alterações em relação à receita</h3>' + tabela(Object.entries(m.alteracoes_em_relacao_a_receita).map(([k, v]) => ({parametro: k, receita: v.receita, usado: v.usado})));
  h += '<h3>Fontes (ordem de processamento)</h3>' + tabela(m.fontes.map(f => ({arquivo: f.arquivo, base: f.rotulo, registros: f.registros, sha256: f.sha256.slice(0, 16) + '…', avisos: f.avisos.join('; ')})));
  h += '<h3>Corpus ordenado pelo escore</h3>' + tabela(j.corpus || []) + '</div>';
  $('triagemOut').innerHTML = h;
  // robustez
  const d = j.diagnosticos || {};
  let r = '<h3>Perdas no fluxo</h3>' + kpis(d.perdas_no_fluxo || {}) + '<h3>Exclusão por trecho de texto (dam ⊂ damage)</h3>' + kpis(d.exclusao_por_trecho || {});
  if (d.sensibilidade_pesos) {
    const s = d.sensibilidade_pesos;
    r += `<h3>Sensibilidade aos pesos (k = ${s.k_referencia}, ${s.n} sorteios, seed ${s.seed})</h3>` + tabela(['uniforme_15', 'dirichlet_5'].map(k => ({cenario: k, ...s[k]})))
      + `<p class="small">Pesos iguais: ${esc(JSON.stringify(s.pesos_iguais))}</p>`;
  }
  if (j.duplicatas_para_revisao) r += `<h3>Pares duvidosos para revisão humana (${j.duplicatas_para_revisao.total})</h3>` + tabela(j.duplicatas_para_revisao.amostra);
  $('robOut').innerHTML = r;
  // bibliometria
  const b = j.bibliometria || {};
  $('bSel').innerHTML = Object.keys(b).map(k => `<option>${esc(k)}</option>`).join('');
  $('bSel').onchange = () => $('bibOut').innerHTML = tabela(b[$('bSel').value]);
  $('bibOut').innerHTML = b.cobertura ? tabela(b.cobertura) : '<p class="small">sem análises</p>';
  if (b.cobertura) $('bSel').value = 'cobertura';
  const url = p => `arquivo.php?projeto=${encodeURIComponent(E.projeto)}&execucao=${encodeURIComponent(j.pasta)}&caminho=${encodeURIComponent(p)}`;
  $('imgs').innerHTML = (j.graficos || []).map(g => `<a href="${url('graficos/' + g)}" target="_blank"><img loading="lazy" src="${url('graficos/' + g)}" alt="${esc(g)}"></a>`).join('') || '<p class="small">sem gráficos</p>';
  $('relOut').innerHTML = (j.relatorios || []).length ? '<ul>' + j.relatorios.map(f => `<li><a href="${url(f)}">${esc(f)}</a></li>`).join('') + '</ul>'
    + '<h3>Manifesto de reprodução</h3><pre>' + esc(JSON.stringify(m, null, 1)) + '</pre>' : '<p class="small">sem relatórios</p>';
}

// ---- robustez: modos ----
$('btModos').onclick = seguro(async () => {
  $('modosOut').innerHTML = '<p class="small">executando os três modos…</p>';
  const j = await api('comparar_modos', {projeto: E.projeto});
  $('modosOut').innerHTML = tabela(Object.entries(j.modos).map(([m, v]) => ({modo: m, versao: v.versao_metodo, registros: v.contagens.registros,
    unicos: v.contagens.unicos, corpus: v.contagens.corpus, ...v.estratos})));
});

// ---- execuções ----
function renderExecucoes(ex) {
  $('tbExec').innerHTML = ex.length ? `<table><thead><tr><th>id</th><th>data (UTC)</th><th>rótulo</th><th>modo</th><th>versão</th><th>únicos</th><th>corpus</th><th>A/B/P/D</th><th></th></tr></thead><tbody>${
    ex.slice().reverse().map(e => `<tr><td><code>${esc(e.id)}</code>${e.importada ? ' <span class="tag" title="importada de .zip (somente leitura)">importada</span>' : ''}</td><td>${esc(e.data_hora_utc)}</td><td>${esc(e.rotulo)}</td><td>${esc(e.modo)}${e.personalizada ? ' *' : ''}</td><td>${esc(e.versao_metodo)}</td>
      <td>${fmt(e.contagens.unicos)}</td><td>${fmt(e.contagens.corpus)}</td><td>${Object.values(e.estratos).join(' / ')}</td>
      <td><button class="btn sec" data-acao="abrirExecucao" data-arg="${esc(e.id)}">abrir</button> ${e.importada ? '' : `<button class="btn sec" data-acao="reproduzir" data-arg="${esc(e.id)}">reproduzir</button>`}
        <button class="btn sec" data-acao="exportar" data-arg="${esc(e.id)}">exportar .zip</button></td></tr>`).join('')}</tbody></table><p class="small">* configuração personalizada</p>`
    : '<p class="small">Nenhuma execução.</p>';
  const ops = ex.map(e => `<option value="${esc(e.id)}">${esc(e.id)} · ${esc(e.modo)} · ${esc(e.data_hora_utc)}</option>`).join('');
  $('cmpA').innerHTML = ops; $('cmpB').innerHTML = ops;
}
window.abrirExecucao = seguro(async id => { mostrarExecucao(await api('execucao', {projeto: E.projeto, id})); msg('Execução ' + esc(id) + ' aberta (ver seções 3 a 7).'); });
window.reproduzir = seguro(async id => {
  const c = await api('reproduzir', {projeto: E.projeto, id});
  $('cmpOut').innerHTML = `<h3>Reprodução de ${esc(id)}</h3>` + kpis({'mesma entrada e parâmetros': c.mesma_entrada_e_parametros ? 'sim' : 'não', 'mesmo corpus (hash)': c.mesmo_corpus ? 'sim' : 'NÃO'})
    + '<pre>' + esc(JSON.stringify(c, null, 1)) + '</pre>';
  await abrirProjeto(E.projeto);
});
$('btCmp').onclick = seguro(async () => {
  const c = await api('comparar', {projeto: E.projeto, a: $('cmpA').value, b: $('cmpB').value});
  $('cmpOut').innerHTML = kpis({'mesma entrada e parâmetros': c.mesma_entrada_e_parametros ? 'sim' : 'não', 'mesmo corpus': c.mesmo_corpus ? 'sim' : 'não',
    'Núcleo A em ambos': c.nucleo_a.em_ambos, 'só em A': c.nucleo_a.so_em_a.length, 'só em B': c.nucleo_a.so_em_b.length})
    + '<h3>Contagens</h3>' + tabela(Object.entries(c.contagens).map(([k, v]) => ({item: k, a: v.a, b: v.b})))
    + '<h3>Estratos</h3>' + tabela(Object.entries(c.estratos).map(([k, v]) => ({item: k, a: v.a, b: v.b})))
    + '<h3>Parâmetros diferentes</h3>' + tabela(Object.entries(c.parametros).map(([k, v]) => ({parametro: k, a: v.a, b: v.b})))
    + '<h3>Arquivos diferentes</h3>' + tabela(Object.entries(c.arquivos).map(([k, v]) => ({arquivo: k, a: v.a, b: v.b})));
});

// ---- exportar / importar execução (.zip) ----
$('xEntradas').onchange = () => { $('xAviso').style.display = $('xEntradas').checked ? '' : 'none'; };
window.exportar = seguro(async id => {
  const r = await fetch('api.php?acao=exportar_execucao', {method: 'POST', credentials: 'same-origin',
    headers: {'X-CSRF-Token': CSRF, 'Content-Type': 'application/json'},
    body: JSON.stringify({projeto: E.projeto, id, incluir_entradas: $('xEntradas').checked})});
  if (!r.ok || !(r.headers.get('Content-Type') || '').startsWith('application/zip')) {
    const t = await r.text(); let j = null;
    try { j = JSON.parse(t); } catch (_) { /* resposta não-JSON */ }
    throw new Error(j && j.erro ? j.erro : 'Falha na exportação: ' + t.slice(0, 300));
  }
  const nome = ((r.headers.get('Content-Disposition') || '').match(/filename="([A-Za-z0-9_.-]+)"/) || [])[1] || 'execucao.zip';
  const blob = await r.blob();
  const a = document.createElement('a');
  a.href = URL.createObjectURL(blob); a.download = nome;
  document.body.appendChild(a); a.click(); a.remove();
  setTimeout(() => URL.revokeObjectURL(a.href), 60000);
  const n = Number(r.headers.get('X-Cientometria-Entradas') || 0);
  $('xOut').innerHTML = `<p>Exportado <code>${esc(nome)}</code> (${fmt(blob.size)} bytes).<br>
    <span class="small">SHA-256 do .zip: <code>${esc(r.headers.get('X-Cientometria-Sha256'))}</code><br>
    SHA-256 do manifesto.json: <code>${esc(r.headers.get('X-Cientometria-Sha256-Manifesto'))}</code> — registre este valor para provar a autenticidade.<br>
    Exportações de entrada incluídas: ${n ? fmt(n) + ' (dados licenciados — não publique)' : 'não'}</span></p>`;
});
$('btImportarExec').onclick = seguro(async () => {
  const f = $('xZip').files[0]; if (!f) throw new Error('Selecione um arquivo .zip.');
  const fd = new FormData(); fd.append('files[]', f); fd.append('projeto', E.projeto);
  $('btImportarExec').disabled = true;
  try {
    const j = await api('importar_execucao', {}, fd);
    const v = j.verificacao;
    $('xOut').innerHTML = `<p>Execução <code>${esc(j.id)}</code> importada <span class="tag">importada</span>
      — verificação: <b class="${v.ok ? 'okb' : 'badb'}">${v.ok ? 'ok' : 'PROBLEMAS'}</b></p>`
      + (v.problemas.length ? '<ul>' + v.problemas.map(x => `<li>${esc(x)}</li>`).join('') + '</ul>' : '')
      + (v.avisos.length ? `<p class="small">${v.avisos.map(esc).join('<br>')}</p>` : '');
    await abrirProjeto(E.projeto);
  } finally { $('btImportarExec').disabled = false; $('xZip').value = ''; }
});

// ações dos botões gerados dinamicamente (sem handlers inline: CSP com nonce)
const ACOES_BOTAO = {abrirProjeto: x => abrirProjeto(x), desativar: x => desativar(x),
                     abrirExecucao: x => abrirExecucao(x), reproduzir: x => reproduzir(x),
                     exportar: x => exportar(x)};
document.addEventListener('click', ev => {
  const b = ev.target.closest('button[data-acao]');
  if (b && ACOES_BOTAO[b.dataset.acao]) ACOES_BOTAO[b.dataset.acao](b.dataset.arg);
});
habilitar(); carregarProjetos();
</script>
</body>
</html>
