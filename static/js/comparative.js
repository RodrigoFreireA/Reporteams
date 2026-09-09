/* COMPARATIVE - comparativo mensal de dashboards Planner salvos */
let comparativeSelectedReports = new Set();
let comparativeLoadedReports = new Map();
let comparativeRenderSeq = 0;
let comparativePeopleReportId = null;
let comparativePeopleChartType = 'donut';

const COMPARATIVE_MAX_REPORTS = 3;
const COMPARATIVE_PLOT_IDS = [
  'comparativeDeliveryPlot',
  'comparativeFlowPlot',
  'comparativeQualityPlot',
  'comparativePeoplePlot',
];

const COMPARATIVE_DETAIL_METRICS = [
  { label: 'Story points', path: ['kpis', 'storypoints'], decimals: 1 },
  { label: 'Tarefas totais', path: ['kpis', 'total'] },
  { label: 'Concluidas', path: ['kpis', 'done'] },
  { label: 'Pendentes', path: ['kpis', 'pending'] },
  { label: 'Conclusao', decimals: 1, suffix: '%', compute: data => pct(safeNum(data?.kpis?.done), safeNum(data?.kpis?.total)) },
  { label: 'Nao previstas', path: ['kpis', 'nao_prev'] },
  { label: 'Backlog', path: ['kpis', 'backlog_total'] },
  { label: 'Fora de HU', path: ['kpis', 'sem_hu'] },
  { label: 'HUs', path: ['kpis', 'hu_count'] },
  { label: 'Responsaveis', path: ['kpis', 'stakeholders'] },
  { label: 'Cycle SP', path: ['kpis', 'ct_sp'], decimals: 1, suffix: ' dias' },
  { label: 'Lead SP', path: ['kpis', 'lt_sp'], decimals: 1, suffix: ' dias' },
  { label: 'Cycle tarefa', path: ['kpis', 'ct_task'], decimals: 1, suffix: ' dias' },
  { label: 'Lead tarefa', path: ['kpis', 'lt_task'], decimals: 1, suffix: ' dias' },
  { label: 'Say/Do', path: ['scope_quality_metrics', 'say_do_ratio'], decimals: 1, suffix: '%' },
  { label: 'SP entregues', path: ['scope_quality_metrics', 'delivered_sp'], decimals: 1 },
  { label: 'Bugs/ajustes', path: ['scope_quality_metrics', 'bug_task_count'] },
  { label: 'Impedimentos', path: ['scope_quality_metrics', 'impediment_task_count'] },
  { label: 'Escopo extra', path: ['scope_quality_metrics', 'scope_creep_task_pct'], decimals: 1, suffix: '%' },
  { label: 'WIP medio', path: ['flow_metrics', 'wip_avg'], decimals: 1 },
  { label: 'Throughput semanal', path: ['flow_metrics', 'throughput_weekly_avg'], decimals: 1 },
  { label: 'Eficiencia fluxo SP', path: ['flow_metrics', 'flow_eff_sp'], decimals: 1, suffix: '%' },
  { label: 'Delta prazo x trabalho', path: ['time_metrics', 'schedule_delta_pct'], decimals: 1, suffix: '%' },
];

function openComparativeScreen() {
  if (!authState.authenticated) return;
  authScreen.classList.add('hidden');
  sidebar.classList.add('hidden');
  uploadScreen.classList.add('hidden');
  teamScreen.classList.add('hidden');
  adminScreen.classList.add('hidden');
  customChartScreen.classList.add('hidden');
  consolidatedScreen.classList.add('hidden');
  dashboardEl.classList.remove('visible');
  comparativeScreen.classList.remove('hidden');
  btnUploadNew.classList.add('visible');
  sprintBadgeEl.classList.remove('visible');
  menuToggle.classList.add('hidden');
  syncTopbarState();
  closeSidebar();
  renderComparativePicker();
  renderComparativeDashboard();
  loadReports()
    .then(() => {
      renderComparativePicker();
      return renderComparativeDashboard();
    })
    .catch(() => {});
}

function comparativeReportName(report) {
  return report?.sprint_name || report?.title || report?.source_filename || `Dashboard ${report?.id || ''}`;
}

function comparativeReportMeta(report) {
  const parts = [
    report?.project_name || 'Projeto nao informado',
    report?.export_date ? `Export: ${report.export_date}` : fmtDateTime(report?.updated_at),
  ].filter(Boolean);
  return parts.join(' - ');
}

function safeNum(value) {
  const n = Number(value);
  return Number.isFinite(n) ? n : 0;
}

function nullableNum(value) {
  const n = Number(value);
  return Number.isFinite(n) ? n : null;
}

function pct(part, total) {
  return total ? (part / total) * 100 : 0;
}

function readComparativePath(data, path) {
  return path.reduce((acc, key) => acc == null ? undefined : acc[key], data);
}

function fmtComparativeValue(value, decimals = 0, suffix = '') {
  const n = nullableNum(value);
  if (n === null) return '-';
  const text = n.toLocaleString('pt-BR', {
    maximumFractionDigits: decimals,
    minimumFractionDigits: decimals > 0 && Math.abs(n) < 10 && n % 1 !== 0 ? 1 : 0,
  });
  return `${text}${suffix}`;
}

function comparativeDateSource(item) {
  return item?.data?.meta?.sprint_start
    || item?.data?.meta?.export_date
    || item?.report?.export_date
    || item?.report?.updated_at
    || item?.report?.created_at
    || '';
}

function comparativeTimestamp(item) {
  const parsed = Date.parse(comparativeDateSource(item));
  return Number.isFinite(parsed) ? parsed : Number.MAX_SAFE_INTEGER;
}

function comparativeMonthLabel(item) {
  const parsed = Date.parse(comparativeDateSource(item));
  if (!Number.isFinite(parsed)) return comparativeReportName(item?.report);
  return new Date(parsed).toLocaleDateString('pt-BR', { month: 'short', year: '2-digit' }).replace('.', '');
}

function comparativeSelectedIds() {
  return Array.from(comparativeSelectedReports).map(Number).filter(Boolean);
}

function comparativeItems() {
  return comparativeSelectedIds()
    .map(id => comparativeLoadedReports.get(id))
    .filter(Boolean)
    .sort((a, b) => comparativeTimestamp(a) - comparativeTimestamp(b));
}

function showComparativeError(message) {
  if (!comparativeError) return;
  comparativeError.textContent = 'Aviso: ' + message;
  comparativeError.classList.add('visible');
}

function clearComparativeError() {
  if (!comparativeError) return;
  comparativeError.textContent = '';
  comparativeError.classList.remove('visible');
}

function syncComparativeMeta() {
  const count = comparativeSelectedReports.size;
  if (comparativeSelectionMeta) {
    comparativeSelectionMeta.textContent = count
      ? `${count}/${COMPARATIVE_MAX_REPORTS} dashboard(s) selecionado(s).`
      : 'Nenhum dashboard selecionado.';
  }
}

function renderComparativePicker() {
  if (!comparativeReportList) return;

  const validIds = new Set(reportList.map(report => Number(report.id)));
  comparativeSelectedReports = new Set(
    comparativeSelectedIds().filter(id => validIds.has(id))
  );
  syncComparativeMeta();
  comparativeReportList.innerHTML = '';

  if (!reportList.length) {
    comparativeReportList.innerHTML = '<div class="reports-empty">Nenhum dashboard salvo ainda.</div>';
    return;
  }

  const selectedCount = comparativeSelectedReports.size;
  reportList.forEach(report => {
    const id = Number(report.id);
    const selected = comparativeSelectedReports.has(id);
    const locked = !selected && selectedCount >= COMPARATIVE_MAX_REPORTS;
    const item = document.createElement('label');
    item.className = `consolidated-report-option comparative-report-option${selected ? ' selected' : ''}${locked ? ' locked' : ''}`;
    item.innerHTML = `
      <input type="checkbox" value="${id}" ${selected ? 'checked' : ''} ${locked ? 'disabled' : ''}>
      <span>
        <strong>${esc(comparativeReportName(report))}</strong>
        <small>${esc(comparativeReportMeta(report))}</small>
      </span>
    `;
    item.querySelector('input').addEventListener('change', event => {
      const checked = event.target.checked;
      if (checked && !comparativeSelectedReports.has(id) && comparativeSelectedReports.size >= COMPARATIVE_MAX_REPORTS) {
        event.target.checked = false;
        showComparativeError(`Selecione no maximo ${COMPARATIVE_MAX_REPORTS} dashboards.`);
        return;
      }
      if (checked) comparativeSelectedReports.add(id);
      else comparativeSelectedReports.delete(id);
      clearComparativeError();
      renderComparativePicker();
      renderComparativeDashboard();
    });
    comparativeReportList.appendChild(item);
  });
}

function clearComparativeSelection() {
  comparativeSelectedReports.clear();
  clearComparativeError();
  renderComparativePicker();
  renderComparativeDashboard();
}

function removeComparativeReport(reportId) {
  comparativeSelectedReports.delete(Number(reportId));
  renderComparativePicker();
  renderComparativeDashboard();
}

function normalizeComparativeReportData(data) {
  const payload = data && typeof data === 'object' ? data : {};
  if (!payload.meta || typeof payload.meta !== 'object') payload.meta = {};
  if (!payload.kpis || typeof payload.kpis !== 'object') payload.kpis = {};

  const kpis = payload.kpis;
  const tasks = Array.isArray(payload.task_rows) ? payload.task_rows : [];
  const num = value => {
    const parsed = Number(value);
    return Number.isFinite(parsed) ? parsed : null;
  };
  const hasNumber = value => num(value) !== null;
  const shouldFill = value => value === null || value === undefined || value === '' || Number(value) === 0;
  const metricObjectReady = key => (
    payload[key]
    && typeof payload[key] === 'object'
    && !Array.isArray(payload[key])
  );

  if (!metricObjectReady('flow_metrics') || (
    !hasNumber(payload.flow_metrics.wip_avg)
    && !hasNumber(payload.flow_metrics.throughput_weekly_avg)
  )) {
    delete payload.flow_metrics;
  }
  if (!metricObjectReady('scope_quality_metrics') || (
    !hasNumber(payload.scope_quality_metrics.say_do_ratio)
    && !hasNumber(payload.scope_quality_metrics.committed_sp)
    && !hasNumber(payload.scope_quality_metrics.delivered_sp)
  )) {
    delete payload.scope_quality_metrics;
  }
  if (!metricObjectReady('time_metrics')) {
    delete payload.time_metrics;
  }

  if (tasks.length) {
    const taskText = task => normalizeText([
      task?.status,
      task?.progress,
      task?.bucket,
      task?.labels,
    ].filter(Boolean).join(';'));
    const taskDone = task => !!(
      task?.done
      || task?.done_kpi
      || task?.date_done
      || task?.wip_done_date
      || taskText(task).includes('concluid')
    );
    const taskHu = task => {
      const match = String(task?.labels || '').match(/\bHU\s*0*\d+\b/i);
      return match ? match[0].replace(/\s+/g, '').toUpperCase() : '';
    };

    if (shouldFill(kpis.total)) kpis.total = tasks.length;
    if (shouldFill(kpis.done)) kpis.done = tasks.filter(taskDone).length;
    if (!hasNumber(kpis.pending) || shouldFill(kpis.pending)) {
      kpis.pending = Math.max(Number(kpis.total || tasks.length) - Number(kpis.done || 0), 0);
    }
    if (shouldFill(kpis.sem_hu)) kpis.sem_hu = tasks.filter(task => !taskHu(task)).length;
    if (shouldFill(kpis.hu_count)) {
      kpis.hu_count = new Set(tasks.map(taskHu).filter(Boolean)).size;
    }
    if (shouldFill(kpis.stakeholders)) {
      kpis.stakeholders = new Set(
        tasks.map(task => String(task?.assignee || '').trim()).filter(Boolean)
      ).size;
    }
    if (shouldFill(kpis.nao_prev)) {
      kpis.nao_prev = tasks.filter(task => {
        const text = taskText(task);
        return text.includes('nao previsto') || text.includes('imprevisto') || text.includes('nao mapeado');
      }).length;
    }
    if (shouldFill(kpis.backlog_total)) {
      kpis.backlog_total = tasks.filter(task => taskText(task).includes('backlog')).length;
    }
  }

  const burndownSpTotal = num(payload.burndown_sp?.total_sp);
  if (shouldFill(kpis.storypoints) && burndownSpTotal && burndownSpTotal > 0) {
    kpis.storypoints = burndownSpTotal;
  }
  if (
    (!hasNumber(kpis.pct_entrega) || (Number(kpis.pct_entrega) === 0 && Number(kpis.done || 0) > 0))
    && Number(kpis.total || 0) > 0
  ) {
    kpis.pct_entrega = Number(kpis.done || 0) / Number(kpis.total || 1);
  }
  if (shouldFill(kpis.hu_count) && Array.isArray(payload.hu_list)) {
    kpis.hu_count = payload.hu_list.length;
  }
  if (shouldFill(kpis.stakeholders) && Array.isArray(payload.collab_rows)) {
    kpis.stakeholders = payload.collab_rows.length;
  }

  if (typeof ensureAdvancedMetrics === 'function' && tasks.length) {
    const previousDashData = dashData;
    try {
      dashData = payload;
      ensureAdvancedMetrics();
    } finally {
      dashData = previousDashData;
    }
  }

  return payload;
}

async function ensureComparativeReportsLoaded(ids) {
  await Promise.all(ids.map(async id => {
    if (comparativeLoadedReports.has(id)) return;
    const body = await apiRequest(`/api/reports/${id}`);
    comparativeLoadedReports.set(id, {
      id,
      report: body.report || reportList.find(report => Number(report.id) === id) || { id },
      data: normalizeComparativeReportData(body.data),
    });
  }));
}

function renderComparativeEmpty(message = 'Escolha ate 3 dashboards salvos para comparar.') {
  if (comparativeOverviewMeta) comparativeOverviewMeta.textContent = message;
  if (comparativeSelectedChips) comparativeSelectedChips.innerHTML = '';
  if (comparativeKpiGrid) comparativeKpiGrid.innerHTML = `<div class="report-builder-empty">${esc(message)}</div>`;
  if (comparativeTableWrap) comparativeTableWrap.innerHTML = '';
  const peopleControls = document.getElementById('comparativePeopleControls');
  if (peopleControls) peopleControls.innerHTML = '';
  COMPARATIVE_PLOT_IDS.forEach(id => {
    const el = document.getElementById(id);
    if (el && window.Plotly) Plotly.purge(el);
  });
}

async function renderComparativeDashboard() {
  const seq = ++comparativeRenderSeq;
  const ids = comparativeSelectedIds();

  if (!ids.length) {
    renderComparativeEmpty();
    return;
  }

  if (comparativeOverviewMeta) comparativeOverviewMeta.textContent = 'Carregando dashboards selecionados...';
  if (comparativeKpiGrid) comparativeKpiGrid.innerHTML = '<div class="report-builder-empty">Carregando dados...</div>';

  try {
    await ensureComparativeReportsLoaded(ids);
    if (seq !== comparativeRenderSeq) return;
    const items = comparativeItems();
    renderComparativeChips(items);
    renderComparativeKpis(items);
    renderComparativeCharts(items);
    renderComparativePeopleChart(items);
    renderComparativeTable(items);
    if (comparativeOverviewMeta) {
      comparativeOverviewMeta.textContent = `${items.length} dashboard(s) em comparacao, ordenados por mes.`;
    }
  } catch (err) {
    showComparativeError(err.message);
    renderComparativeEmpty('Nao foi possivel carregar um dos dashboards selecionados.');
  }
}

function renderComparativeChips(items) {
  if (!comparativeSelectedChips) return;
  comparativeSelectedChips.innerHTML = items.map(item => `
    <button class="comparative-chip" type="button" onclick="removeComparativeReport(${Number(item.id)})">
      <span>${esc(comparativeMonthLabel(item))}</span>
      <strong>${esc(comparativeReportName(item.report))}</strong>
      <em>x</em>
    </button>
  `).join('');
}

function renderComparativeKpis(items) {
  if (!comparativeKpiGrid) return;
  comparativeKpiGrid.innerHTML = items.map(item => {
    const data = item.data || {};
    const kpis = data.kpis || {};
    const scope = data.scope_quality_metrics || {};
    const donePct = pct(safeNum(kpis.done), safeNum(kpis.total));
    return `
      <article class="kpi-card comparative-month-card">
        <div class="kpi-card-head">
          <div>
            <div class="kpi-label">${esc(comparativeMonthLabel(item))}</div>
            <div class="comparative-card-title">${esc(comparativeReportName(item.report))}</div>
          </div>
          <span>${esc(data.meta?.export_date || item.report?.export_date || '')}</span>
        </div>
        <div class="comparative-card-grid">
          <span><em>SP</em><strong>${fmtComparativeValue(kpis.storypoints, 1)}</strong></span>
          <span><em>Conclusao</em><strong>${fmtComparativeValue(donePct, 1, '%')}</strong></span>
          <span><em>Concluidas</em><strong>${fmtComparativeValue(kpis.done)}</strong></span>
          <span><em>Pendentes</em><strong>${fmtComparativeValue(kpis.pending)}</strong></span>
          <span><em>Cycle SP</em><strong>${fmtComparativeValue(kpis.ct_sp, 1, 'd')}</strong></span>
          <span><em>Lead SP</em><strong>${fmtComparativeValue(kpis.lt_sp, 1, 'd')}</strong></span>
          <span><em>Say/Do</em><strong>${fmtComparativeValue(scope.say_do_ratio, 1, '%')}</strong></span>
          <span><em>Backlog</em><strong>${fmtComparativeValue(kpis.backlog_total)}</strong></span>
        </div>
      </article>
    `;
  }).join('');
}

function comparativeLabels(items) {
  return items.map(item => comparativeMonthLabel(item));
}

function chartData(items, reader) {
  return items.map(item => safeNum(reader(item.data || {}, item.report || {})));
}

function renderComparativeCharts(items) {
  if (!items.length || !window.Plotly || typeof plotLayout !== 'function') return;
  const labels = comparativeLabels(items);

  Plotly.react('comparativeDeliveryPlot', [
    { type: 'bar', name: 'Story points', x: labels, y: chartData(items, data => data.kpis?.storypoints), marker: { color: pc(0) } },
    { type: 'bar', name: 'Concluidas', x: labels, y: chartData(items, data => data.kpis?.done), marker: { color: pc(1) } },
    { type: 'bar', name: 'Pendentes', x: labels, y: chartData(items, data => data.kpis?.pending), marker: { color: pc(2) } },
    { type: 'bar', name: 'Nao previstas', x: labels, y: chartData(items, data => data.kpis?.nao_prev), marker: { color: pc(3) } },
  ], plotLayout({
    barmode: 'group',
    margin: { t: 18, r: 16, b: 46, l: 52 },
    yaxis: { title: { text: 'Volume' } },
  }), { responsive: true, displayModeBar: false });

  Plotly.react('comparativeFlowPlot', [
    { type: 'scatter', mode: 'lines+markers', name: 'Cycle SP', x: labels, y: chartData(items, data => data.kpis?.ct_sp), line: { color: pc(0), width: 3 } },
    { type: 'scatter', mode: 'lines+markers', name: 'Lead SP', x: labels, y: chartData(items, data => data.kpis?.lt_sp), line: { color: pc(1), width: 3 } },
    { type: 'scatter', mode: 'lines+markers', name: 'WIP medio', x: labels, y: chartData(items, data => data.flow_metrics?.wip_avg), line: { color: pc(2), width: 3 } },
    { type: 'scatter', mode: 'lines+markers', name: 'Throughput sem.', x: labels, y: chartData(items, data => data.flow_metrics?.throughput_weekly_avg), line: { color: pc(3), width: 3 } },
  ], plotLayout({
    margin: { t: 18, r: 16, b: 46, l: 52 },
    yaxis: { title: { text: 'Dias / media' } },
  }), { responsive: true, displayModeBar: false });

  Plotly.react('comparativeQualityPlot', [
    { type: 'bar', name: 'Say/Do %', x: labels, y: chartData(items, data => data.scope_quality_metrics?.say_do_ratio), marker: { color: pc(0) } },
    { type: 'bar', name: 'Bugs/ajustes', x: labels, y: chartData(items, data => data.scope_quality_metrics?.bug_task_count), marker: { color: pc(1) } },
    { type: 'bar', name: 'Impedimentos', x: labels, y: chartData(items, data => data.scope_quality_metrics?.impediment_task_count), marker: { color: pc(2) } },
    { type: 'bar', name: 'Escopo extra %', x: labels, y: chartData(items, data => data.scope_quality_metrics?.scope_creep_task_pct), marker: { color: pc(3) } },
  ], plotLayout({
    barmode: 'group',
    margin: { t: 18, r: 16, b: 46, l: 52 },
    yaxis: { title: { text: 'Valor' } },
  }), { responsive: true, displayModeBar: false });
}

function comparativePeopleSelectedItem(items) {
  if (!items.length) return null;
  const validIds = new Set(items.map(item => Number(item.id)));
  if (!validIds.has(Number(comparativePeopleReportId))) {
    comparativePeopleReportId = Number(items[items.length - 1].id);
  }
  return items.find(item => Number(item.id) === Number(comparativePeopleReportId)) || items[items.length - 1];
}

function renderComparativePeopleControls(items, selectedItem) {
  const controls = document.getElementById('comparativePeopleControls');
  if (!controls) return;
  const type = comparativePeopleChartType === 'pie' ? 'pie' : 'donut';
  comparativePeopleChartType = type;
  controls.innerHTML = `
    <select id="comparativePeopleReportSelect" aria-label="Dashboard para entregas por pessoa">
      ${items.map(item => `
        <option value="${Number(item.id)}" ${Number(item.id) === Number(selectedItem?.id) ? 'selected' : ''}>
          ${esc(comparativeMonthLabel(item))} - ${esc(comparativeReportName(item.report))}
        </option>
      `).join('')}
    </select>
    <button class="comparative-type-toggle ${type === 'donut' ? 'active' : ''}" type="button" data-comparative-people-type="donut">Donut</button>
    <button class="comparative-type-toggle ${type === 'pie' ? 'active' : ''}" type="button" data-comparative-people-type="pie">Pizza</button>
  `;

  const select = controls.querySelector('#comparativePeopleReportSelect');
  if (select) {
    select.addEventListener('change', () => {
      comparativePeopleReportId = Number(select.value);
      renderComparativePeopleChart(items);
    });
  }

  controls.querySelectorAll('[data-comparative-people-type]').forEach(button => {
    button.addEventListener('click', () => {
      comparativePeopleChartType = button.dataset.comparativePeopleType === 'pie' ? 'pie' : 'donut';
      renderComparativePeopleChart(items);
    });
  });
}

function renderComparativePeopleChart(items) {
  const plotEl = document.getElementById('comparativePeoplePlot');
  if (!plotEl) return;
  if (!items.length || !window.Plotly || typeof chartPersonDelivery !== 'function') {
    const controls = document.getElementById('comparativePeopleControls');
    if (controls) controls.innerHTML = '';
    if (window.Plotly) Plotly.purge(plotEl);
    return;
  }

  const selectedItem = comparativePeopleSelectedItem(items);
  renderComparativePeopleControls(items, selectedItem);
  let result = null;
  try {
    result = chartPersonDelivery(comparativePeopleChartType, {
      data: selectedItem?.data || {},
      selectedPeople: 'Todos',
    });
  } catch (err) {
    console.error('Falha ao montar entregas por pessoa no comparativo', err);
    Plotly.purge(plotEl);
    plotEl.innerHTML = '<div class="report-builder-empty error">Nao foi possivel montar entregas por pessoa para este dashboard.</div>';
    return;
  }

  if (!result?.traces) {
    Plotly.purge(plotEl);
    plotEl.innerHTML = '<div class="report-builder-empty">Sem entregas por pessoa neste dashboard.</div>';
    return;
  }

  plotEl.innerHTML = '';
  Plotly.react('comparativePeoplePlot', result.traces, {
    ...(result.layout || {}),
    autosize: true,
    margin: { ...(result.layout?.margin || {}), t: 58, r: 16, b: 28, l: 16 },
  }, { responsive: true, displayModeBar: false }).catch(err => {
    console.error('Falha ao renderizar entregas por pessoa no comparativo', err);
    Plotly.purge(plotEl);
    plotEl.innerHTML = '<div class="report-builder-empty error">Nao foi possivel renderizar entregas por pessoa para este dashboard.</div>';
  });
}

function renderComparativeTable(items) {
  if (!comparativeTableWrap) return;
  const headers = items.map(item => comparativeMonthLabel(item));
  const rows = COMPARATIVE_DETAIL_METRICS.map(metric => {
    const values = items.map(item => metric.compute
      ? metric.compute(item.data || {}, item.report || {})
      : readComparativePath(item.data || {}, metric.path || []));
    const first = nullableNum(values[0]);
    const last = nullableNum(values[values.length - 1]);
    const delta = first !== null && last !== null && values.length > 1
      ? fmtComparativeValue(last - first, metric.decimals || 0, metric.suffix || '')
      : '-';
    return `
      <tr>
        <td><strong>${esc(metric.label)}</strong></td>
        ${values.map(value => `<td>${esc(fmtComparativeValue(value, metric.decimals || 0, metric.suffix || ''))}</td>`).join('')}
        <td>${esc(delta)}</td>
      </tr>
    `;
  }).join('');

  comparativeTableWrap.innerHTML = `
    <table class="admin-users-table comparative-table">
      <thead>
        <tr>
          <th>Metrica</th>
          ${headers.map(header => `<th>${esc(header)}</th>`).join('')}
          <th>Variacao</th>
        </tr>
      </thead>
      <tbody>${rows}</tbody>
    </table>
  `;
}

function resizeComparativePlots() {
  if (!comparativeScreen || comparativeScreen.classList.contains('hidden') || !window.Plotly) return;
  COMPARATIVE_PLOT_IDS.forEach(id => {
    const el = document.getElementById(id);
    if (el) Plotly.Plots.resize(el);
  });
}
