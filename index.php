<?php
?>
<!doctype html>
<html lang="pt-BR">
<head>
  <meta charset="UTF-8" />
  <meta name="viewport" content="width=device-width, initial-scale=1.0" />
  <title>Dashboard Cientometria de Enchentes + IA</title>
  <style>
    :root {
      --bg: #0f172a;
      --card: #111827;
      --muted: #94a3b8;
      --text: #e5e7eb;
      --ok: #22c55e;
      --warn: #f59e0b;
      --bad: #ef4444;
      --accent: #38bdf8;
    }
    body {
      margin: 0;
      font-family: Inter, system-ui, -apple-system, Segoe UI, Roboto, sans-serif;
      background: linear-gradient(180deg, #020617, #0f172a);
      color: var(--text);
    }
    .container {
      max-width: 1200px;
      margin: 24px auto;
      padding: 0 16px 64px;
    }
    .card {
      background: rgba(17,24,39,0.9);
      border: 1px solid #1f2937;
      border-radius: 16px;
      padding: 16px;
      margin-bottom: 16px;
      box-shadow: 0 10px 30px rgba(0,0,0,0.2);
    }
    h1, h2 { margin: 8px 0 14px; }
    p { color: var(--muted); }
    .grid {
      display: grid;
      grid-template-columns: repeat(4, minmax(0, 1fr));
      gap: 12px;
    }
    .kpi { padding: 12px; border-radius: 12px; background: #0b1220; border: 1px solid #243041; }
    .kpi .label { color: var(--muted); font-size: 13px; }
    .kpi .value { font-size: 30px; font-weight: 700; margin-top: 4px; }
    .dropzone {
      border: 2px dashed #334155;
      border-radius: 14px;
      padding: 20px;
      text-align: center;
      color: var(--muted);
      transition: border-color .2s;
    }
    .dropzone.drag { border-color: var(--accent); }
    .btn {
      background: #0ea5e9;
      color: #06202d;
      border: none;
      border-radius: 10px;
      font-weight: 700;
      padding: 10px 14px;
      cursor: pointer;
    }
    .btn:disabled { opacity: .5; cursor: not-allowed; }
    .row { display:flex; gap:12px; align-items:center; flex-wrap: wrap; }
    table {
      width: 100%;
      border-collapse: collapse;
      font-size: 13px;
    }
    th, td {
      border-bottom: 1px solid #263244;
      padding: 8px;
      text-align: left;
      vertical-align: top;
    }
    th { color: #cbd5e1; }
    .tag { padding:3px 8px; border-radius:999px; font-size:12px; font-weight:700; }
    .nA { background: rgba(34,197,94,.15); color: #86efac; }
    .nB { background: rgba(56,189,248,.15); color: #7dd3fc; }
    .nP { background: rgba(245,158,11,.15); color: #fcd34d; }
    .nD { background: rgba(239,68,68,.15); color: #fca5a5; }
    .small { font-size: 12px; color: var(--muted); }
    canvas { max-height: 320px; }
    @media (max-width: 900px) { .grid { grid-template-columns: repeat(2, minmax(0, 1fr)); } }
  </style>
</head>
<body>
  <div class="container">
    <div class="card">
      <h1>Dashboard interativo de cientometria</h1>
      <p>Importe planilhas de Scopus, Lens e outras bases (<strong>.csv/.xlsx/.bib</strong>). O sistema normaliza campos, deduplica por DOI + título e aplica filtro temático + escore de relevância automaticamente.</p>
      <div id="dropzone" class="dropzone">
        <input id="fileInput" type="file" multiple accept=".csv,.xlsx,.bib,.tsv,.txt" />
        <div>Arraste arquivos aqui ou selecione no campo acima.</div>
      </div>
      <div class="row" style="margin-top:12px;">
        <label class="small">Motor:
          <select id="engineSelect">
            <option value="python">Python</option>
            <option value="r">R</option>
          </select>
        </label>
        <button id="runBtn" class="btn" disabled>Processar planilhas</button>
        <span id="status" class="small">Nenhum arquivo selecionado.</span>
      </div>
      <details style="margin-top:10px;">
        <summary style="cursor:pointer; color:#cbd5e1;">Parâmetros de cálculo (editáveis)</summary>
        <div class="row" style="margin-top:10px;">
          <label class="small">Peso C* <input id="wC" type="number" step="0.01" value="0.35" style="width:80px"></label>
          <label class="small">Peso R* <input id="wR" type="number" step="0.01" value="0.20" style="width:80px"></label>
          <label class="small">Peso T* <input id="wT" type="number" step="0.01" value="0.30" style="width:80px"></label>
          <label class="small">Peso A* <input id="wA" type="number" step="0.01" value="0.15" style="width:80px"></label>
          <label class="small">Ano min <input id="yearMin" type="number" value="1992" style="width:90px"></label>
          <label class="small">Ano max <input id="yearMax" type="number" value="2026" style="width:90px"></label>
          <label class="small">Núcleo A >= <input id="thA" type="number" value="70" style="width:80px"></label>
          <label class="small">Núcleo B >= <input id="thB" type="number" value="50" style="width:80px"></label>
          <label class="small">Periférico >= <input id="thP" type="number" value="30" style="width:80px"></label>
        </div>
      </details>
    </div>

    <div class="card">
      <h2>Resumo do pipeline</h2>
      <div class="grid" id="kpis"></div><pre id="paramsView" class="small" style="white-space:pre-wrap; margin-top:10px;"></pre>
    </div>

    <div class="card">
      <h2>Distribuição por núcleo</h2>
      <canvas id="nucleoChart"></canvas>
    </div>

    <div class="card">
      <h2>Gráficos gerados pelo pipeline</h2>
      <div class="row">
        <img id="plotNucleo" alt="Distribuição por núcleo (R)" style="max-width:48%; border-radius:10px; display:none;"/>
        <img id="plotScore" alt="Histograma de score (R)" style="max-width:48%; border-radius:10px; display:none;"/>
      </div>
    </div>

    <div class="card">
      <h2>Top artigos por Score100</h2>
      <div style="overflow:auto;">
        <table id="topTable">
          <thead>
            <tr>
              <th>Título</th>
              <th>Ano</th>
              <th>Citações</th>
              <th>DOI</th>
              <th>Núcleo</th>
              <th>Score100</th>
            </tr>
          </thead>
          <tbody></tbody>
        </table>
      </div>
    </div>
  </div>

  <script src="https://cdn.jsdelivr.net/npm/chart.js"></script>
  <script>
    const fileInput = document.getElementById('fileInput');
    const runBtn = document.getElementById('runBtn');
    const statusEl = document.getElementById('status');
    const dropzone = document.getElementById('dropzone');
    const kpisEl = document.getElementById('kpis');
    const tbody = document.querySelector('#topTable tbody');
    const engineSelect = document.getElementById('engineSelect');
    const plotNucleo = document.getElementById('plotNucleo');
    const plotScore = document.getElementById('plotScore');
    const paramsView = document.getElementById('paramsView');
    let chart;

    function setStatus(msg) { statusEl.textContent = msg; }

    fileInput.addEventListener('change', () => {
      runBtn.disabled = fileInput.files.length === 0;
      setStatus(fileInput.files.length ? `${fileInput.files.length} arquivo(s) selecionado(s).` : 'Nenhum arquivo selecionado.');
    });

    ;['dragenter','dragover'].forEach(evt => dropzone.addEventListener(evt, e => {
      e.preventDefault(); e.stopPropagation(); dropzone.classList.add('drag');
    }));
    ;['dragleave','drop'].forEach(evt => dropzone.addEventListener(evt, e => {
      e.preventDefault(); e.stopPropagation(); dropzone.classList.remove('drag');
    }));
    dropzone.addEventListener('drop', e => {
      const dt = e.dataTransfer;
      fileInput.files = dt.files;
      runBtn.disabled = fileInput.files.length === 0;
      setStatus(fileInput.files.length ? `${fileInput.files.length} arquivo(s) selecionado(s).` : 'Nenhum arquivo selecionado.');
    });

    runBtn.addEventListener('click', async () => {
      if (!fileInput.files.length) return;
      runBtn.disabled = true;
      setStatus('Processando...');
      const fd = new FormData();
      for (const file of fileInput.files) fd.append('files[]', file);
      fd.append('engine', engineSelect.value);
      const params = {
        weights: {
          c: Number(document.getElementById('wC').value || 0.35),
          r: Number(document.getElementById('wR').value || 0.2),
          t: Number(document.getElementById('wT').value || 0.3),
          a: Number(document.getElementById('wA').value || 0.15)
        },
        year_min: Number(document.getElementById('yearMin').value || 1992),
        year_max: Number(document.getElementById('yearMax').value || 2026),
        thresholds: {
          nucleo_a: Number(document.getElementById('thA').value || 70),
          nucleo_b: Number(document.getElementById('thB').value || 50),
          periferico: Number(document.getElementById('thP').value || 30)
        }
      };
      fd.append('params', JSON.stringify(params));
      try {
        const res = await fetch('run_pipeline.php', { method: 'POST', body: fd });
        const raw = await res.text();
        let data;
        try {
          data = JSON.parse(raw);
        } catch (_) {
          throw new Error(`Resposta inválida do servidor (não-JSON): ${raw.slice(0, 180)}`);
        }
        if (!res.ok || data.error) throw new Error(data.error || 'Falha ao processar arquivos.');
        render(data);
        setStatus('Concluído.');
      } catch (err) {
        setStatus(`Erro: ${err.message}`);
      } finally {
        runBtn.disabled = false;
      }
    });

    function kpi(label, value) {
      return `<div class="kpi"><div class="label">${label}</div><div class="value">${value}</div></div>`;
    }

    function render(data) {
      const s = data.summary;
      const cc = Object.assign({'Núcleo A':0,'Núcleo B':0,'Periférico':0,'Descarte':0}, s.core_counts || {});
      kpisEl.innerHTML = [
        kpi('Registros brutos', s.raw_records),
        kpi('Após dedup DOI', s.after_doi),
        kpi('Após dedup título', s.after_title),
        kpi('Selecionados no filtro temático', s.thematic_selected),
        kpi('Núcleo A', cc['Núcleo A']),
        kpi('Núcleo B', cc['Núcleo B']),
        kpi('Periférico', cc['Periférico']),
        kpi('Descarte', cc['Descarte'])
      ].join('');

      const labels = Object.keys(cc);
      const values = labels.map(k => cc[k]);
      paramsView.textContent = [
        data.used_params ? ('Parâmetros usados: ' + JSON.stringify(data.used_params, null, 2)) : '',
        s.t_star_distribution ? ('Distribuição T*: ' + JSON.stringify(s.t_star_distribution)) : '',
        s.a_star_bins ? ('Faixas A*: ' + JSON.stringify(s.a_star_bins)) : '',
        s.score_stats ? ('Score100 stats: ' + JSON.stringify(s.score_stats)) : ''
      ].filter(Boolean).join('\n');
      if (chart) chart.destroy();
      chart = new Chart(document.getElementById('nucleoChart'), {
        type: 'bar',
        data: {
          labels,
          datasets: [{
            label: 'Artigos',
            data: values,
            backgroundColor: ['#22c55e','#38bdf8','#f59e0b','#ef4444']
          }]
        },
        options: { responsive: true, plugins: { legend: { display: false } } }
      });

      plotNucleo.style.display = "none"; plotScore.style.display = "none";
      if (data.plot_urls) {
        if (data.plot_urls.core_distribution) { plotNucleo.src = data.plot_urls.core_distribution + '?t=' + Date.now(); plotNucleo.style.display = 'block'; }
        if (data.plot_urls.score_histogram) { plotScore.src = data.plot_urls.score_histogram + '?t=' + Date.now(); plotScore.style.display = 'block'; }
      }

      tbody.innerHTML = '';
      const rows = Array.isArray(data.top_articles) ? data.top_articles : [];
      for (const r of rows) {
        const tr = document.createElement('tr');
        const cls = r.nucleo === 'Núcleo A' ? 'nA' : r.nucleo === 'Núcleo B' ? 'nB' : r.nucleo === 'Periférico' ? 'nP' : 'nD';
        tr.innerHTML = `
          <td>${r.title || ''}</td>
          <td>${r.year ?? ''}</td>
          <td>${r.citations ?? ''}</td>
          <td>${r.doi || ''}</td>
          <td><span class="tag ${cls}">${r.nucleo}</span></td>
          <td>${Number(r.score100).toFixed(2)}</td>
        `;
        tbody.appendChild(tr);
      }
    }
  </script>
</body>
</html>
