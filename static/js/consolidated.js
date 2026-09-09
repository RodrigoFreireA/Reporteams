/* REPORT BUILDER - montagem visual de relatorios imprimiveis */
let reportBuilderSelectedReports = new Set();
let reportBuilderLoadedReports = new Map();
let reportBuilderPages = [{ id: 'page-1', name: 'Pagina 1', blocks: [] }];
let reportBuilderActivePageId = 'page-1';
let reportBuilderBlockSeq = 1;
let reportBuilderDraggedBlock = null;
let reportBuilderCurrentLayoutId = null;
let reportBuilderCurrentVersionId = null;
let reportBuilderCurrentTitle = 'Relatorio visual';
let reportBuilderApplyingLayout = false;
let reportBuilderSaving = false;

const REPORT_BUILDER_SIZES = {
  medium: 'Meio bloco',
  large: 'Grande',
  full: 'Largura cheia',
};

function openConsolidatedScreen() {
  if (!authState.authenticated) return;
  authScreen.classList.add('hidden');
  sidebar.classList.add('hidden');
  uploadScreen.classList.add('hidden');
  teamScreen.classList.add('hidden');
  adminScreen.classList.add('hidden');
  customChartScreen.classList.add('hidden');
  comparativeScreen.classList.add('hidden');
  dashboardEl.classList.remove('visible');
  consolidatedScreen.classList.remove('hidden');
  btnUploadNew.classList.add('visible');
  sprintBadgeEl.classList.remove('visible');
  menuToggle.classList.add('hidden');
  syncTopbarState();
  closeSidebar();
  renderConsolidatedPicker();
  renderReportBuilderPages();
  Promise.all([
    loadReports(),
    typeof loadCustomCharts === 'function' ? loadCustomCharts() : Promise.resolve(),
  ]).then(() => {
    const chartList = getReportBuilderEl('reportBuilderChartList');
    if (chartList) chartList.dataset.ready = '';
    renderConsolidatedPicker();
  }).catch(() => {});
}

function reportDisplayName(report) {
  return report.sprint_name || report.title || report.source_filename || `Dashboard ${report.id}`;
}

function getReportBuilderEl(id) {
  return document.getElementById(id);
}

function reportBuilderTitleValue() {
  const input = getReportBuilderEl('reportBuilderTitleInput');
  const value = String(input?.value || '').trim() || 'Relatorio visual';
  return value.slice(0, 160);
}

function setReportBuilderTitle(value) {
  reportBuilderCurrentTitle = String(value || '').trim() || 'Relatorio visual';
  const input = getReportBuilderEl('reportBuilderTitleInput');
  if (input) input.value = reportBuilderCurrentTitle;
}

function setReportBuilderStatus(message, mode = 'neutral') {
  const status = getReportBuilderEl('reportBuilderSaveStatus');
  if (!status) return;
  status.textContent = message || '';
  status.dataset.mode = mode;
}

function markReportBuilderDirty() {
  if (reportBuilderApplyingLayout) return;
  setReportBuilderStatus(reportBuilderCurrentLayoutId ? 'Alteracoes nao salvas' : 'Nao salvo', 'dirty');
}

function syncReportBuilderTitle() {
  reportBuilderCurrentTitle = reportBuilderTitleValue();
  markReportBuilderDirty();
}

function showConsolidatedError(message) {
  consolidatedError.textContent = 'Aviso: ' + message;
  consolidatedError.classList.add('visible');
}

function clearConsolidatedError() {
  consolidatedError.textContent = '';
  consolidatedError.classList.remove('visible');
}

function selectedReportIds() {
  return Array.from(reportBuilderSelectedReports).filter(Boolean);
}

function selectedReportMetas() {
  const ids = new Set(selectedReportIds().map(Number));
  return reportList.filter(report => ids.has(Number(report.id)));
}

function syncReportBuilderMode() {
  const singleSelect = getReportBuilderEl('reportBuilderSingleReportInput');
  const mode = getReportBuilderEl('reportBuilderModeInput')?.value || 'compare';
  const selected = selectedReportMetas();
  if (!singleSelect) return;

  singleSelect.disabled = mode !== 'single' || selected.length === 0;
  singleSelect.innerHTML = selected.length
    ? selected.map(report => `<option value="${Number(report.id)}">${esc(reportDisplayName(report))}</option>`).join('')
    : '<option value="">Selecione dashboards</option>';
}

function renderConsolidatedPicker() {
  const list = getReportBuilderEl('consolidatedReportList');
  const meta = getReportBuilderEl('reportBuilderSelectionMeta');
  if (!list) return;

  list.innerHTML = '';
  clearConsolidatedError();

  const validIds = new Set(reportList.map(report => Number(report.id)));
  reportBuilderSelectedReports = new Set(
    selectedReportIds().map(Number).filter(id => validIds.has(id))
  );

  if (!reportList.length) {
    list.innerHTML = '<div class="reports-empty">Nenhum dashboard salvo ainda.</div>';
    if (meta) meta.textContent = 'Nenhum dashboard disponivel.';
    syncReportBuilderMode();
    renderReportBuilderChartList();
    return;
  }

  reportList.forEach(report => {
    const id = Number(report.id);
    const item = document.createElement('label');
    item.className = 'consolidated-report-option';
    item.innerHTML = `
      <input type="checkbox" value="${id}" ${reportBuilderSelectedReports.has(id) ? 'checked' : ''}>
      <span>
        <strong>${esc(reportDisplayName(report))}</strong>
        <small>${esc(report.project_name || 'Projeto nao informado')} &middot; ${esc(fmtDateTime(report.updated_at))}</small>
      </span>
    `;
    item.querySelector('input').addEventListener('change', event => {
      if (event.target.checked) reportBuilderSelectedReports.add(id);
      else reportBuilderSelectedReports.delete(id);
      const selectedCount = reportBuilderSelectedReports.size;
      if (meta) meta.textContent = selectedCount
        ? `${selectedCount} dashboard(s) selecionado(s).`
        : 'Nenhum dashboard selecionado.';
      syncReportBuilderMode();
    });
    list.appendChild(item);
  });

  if (meta) {
    const count = reportBuilderSelectedReports.size;
    meta.textContent = count ? `${count} dashboard(s) selecionado(s).` : 'Nenhum dashboard selecionado.';
  }
  syncReportBuilderMode();
  renderReportBuilderChartList();
}

function renderReportBuilderChartList() {
  const chartList = getReportBuilderEl('reportBuilderChartList');
  if (!chartList || chartList.dataset.ready === '1') return;

  const groups = {};
  getCatalog().forEach(chart => {
    if (!groups[chart.group]) groups[chart.group] = [];
    groups[chart.group].push(chart);
  });

  const renderChartOption = chart => `
    <label class="report-builder-chart-option">
          <input class="report-builder-chart-check" type="checkbox" value="${esc(chart.id)}">
          <span class="report-builder-chart-main">
            <strong>${esc(chart.name)}</strong>
            <small>${esc(chart.subtitle || '')}</small>
          </span>
          <span class="report-builder-chart-config">
            <select class="report-builder-chart-type" data-chart-id="${esc(chart.id)}">
              ${(chart.types || ['bar_v']).map(type => `
                <option value="${esc(type)}">${esc(CHART_TYPES[type]?.label || type)}</option>
              `).join('')}
            </select>
            <select class="report-builder-chart-size" data-chart-id="${esc(chart.id)}">
              ${Object.entries(REPORT_BUILDER_SIZES).map(([value, label]) => `
                <option value="${esc(value)}"${value === 'large' ? ' selected' : ''}>${esc(label)}</option>
              `).join('')}
            </select>
          </span>
    </label>
  `;

  const renderChartOptions = charts => {
    const html = [];
    let activeSubgroup = null;
    let activeNestedSubgroup = null;
    let subgroupItems = [];
    let nestedItems = [];

    const flushNestedSubgroup = () => {
      if (!activeNestedSubgroup) return;
      subgroupItems.push(`
        <div class="report-builder-chart-nested-subgroup">
          <div class="report-builder-chart-nested-subgroup-title">${esc(activeNestedSubgroup)}</div>
          ${nestedItems.join('')}
        </div>
      `);
      activeNestedSubgroup = null;
      nestedItems = [];
    };

    const flushSubgroup = () => {
      if (!activeSubgroup) return;
      flushNestedSubgroup();
      html.push(`
        <div class="report-builder-chart-subgroup">
          <div class="report-builder-chart-subgroup-title">${esc(activeSubgroup)}</div>
          ${subgroupItems.join('')}
        </div>
      `);
      activeSubgroup = null;
      subgroupItems = [];
    };

    charts.forEach(chart => {
      const subgroup = chart.subgroup || '';
      const subgroup2 = chart.subgroup2 || '';
      const optionHtml = renderChartOption(chart);
      if (!subgroup) {
        flushSubgroup();
        html.push(optionHtml);
        return;
      }
      if (subgroup !== activeSubgroup) {
        flushSubgroup();
        activeSubgroup = subgroup;
      }
      if (subgroup2) {
        if (subgroup2 !== activeNestedSubgroup) {
          flushNestedSubgroup();
          activeNestedSubgroup = subgroup2;
        }
        nestedItems.push(optionHtml);
      } else {
        flushNestedSubgroup();
        subgroupItems.push(optionHtml);
      }
    });
    flushSubgroup();
    return html.join('');
  };

  chartList.innerHTML = Object.entries(groups).map(([group, charts]) => `
    <div class="report-builder-chart-group">
      <div class="report-builder-chart-group-title">${esc(group)}</div>
      ${renderChartOptions(charts)}
    </div>
  `).join('');
  chartList.dataset.ready = '1';
}

async function loadReportBuilderReports(ids) {
  const missing = ids.filter(id => !reportBuilderLoadedReports.has(Number(id)));
  if (!missing.length) return;

  await Promise.all(missing.map(async id => {
    const body = await apiRequest(`/api/reports/${id}`);
    reportBuilderLoadedReports.set(Number(id), { report: body.report, data: body.data });
  }));
}

async function loadReportBuilderReportsLenient(ids) {
  const missingIds = [];
  const uniqueIds = Array.from(new Set(ids.map(Number).filter(Boolean)));
  await Promise.all(uniqueIds.map(async id => {
    if (reportBuilderLoadedReports.has(id)) return;
    try {
      const body = await apiRequest(`/api/reports/${id}`);
      reportBuilderLoadedReports.set(id, { report: body.report, data: body.data });
    } catch (_) {
      missingIds.push(id);
    }
  }));
  return missingIds;
}

function collectReportBuilderPageIds(pages = reportBuilderPages) {
  const ids = new Set();
  (pages || []).forEach(page => {
    (page.blocks || []).forEach(block => {
      (block.reportIds || []).forEach(id => {
        const numeric = Number(id);
        if (numeric) ids.add(numeric);
      });
    });
  });
  return Array.from(ids);
}

function normalizeReportBuilderPages(pages) {
  if (!Array.isArray(pages) || !pages.length) return [{ id: 'page-1', name: 'Pagina 1', blocks: [] }];
  return pages.map((page, pageIndex) => ({
    id: String(page?.id || `page-${pageIndex + 1}`),
    name: String(page?.name || `Pagina ${pageIndex + 1}`),
    blocks: Array.isArray(page?.blocks) ? page.blocks.map((block, blockIndex) => ({
      id: String(block?.id || `rb-loaded-${Date.now()}-${pageIndex}-${blockIndex}`),
      chartId: String(block?.chartId || ''),
      type: String(block?.type || findCatalogItem(block?.chartId)?.types?.[0] || 'bar_v'),
      size: REPORT_BUILDER_SIZES[block?.size] ? block.size : 'large',
      reportIds: Array.isArray(block?.reportIds) ? block.reportIds.map(Number).filter(Boolean) : [],
    })).filter(block => block.chartId && block.reportIds.length) : [],
  }));
}

function reportBuilderRefsForPayload(reportIds) {
  return reportIds.map(id => {
    const loaded = reportBuilderLoadedReports.get(Number(id));
    const meta = loaded?.report || reportList.find(report => Number(report.id) === Number(id));
    return {
      id: Number(id),
      title: meta?.title || '',
      sprint_name: meta?.sprint_name || '',
      project_name: meta?.project_name || '',
      updated_at: meta?.updated_at || '',
    };
  });
}

function captureReportBuilderPayload() {
  const pages = normalizeReportBuilderPages(reportBuilderPages);
  const reportIds = collectReportBuilderPageIds(pages);
  return {
    schema: 'report_builder_v1',
    title: reportBuilderTitleValue(),
    reportRefs: reportBuilderRefsForPayload(reportIds),
    pages,
  };
}

async function applyReportBuilderPayload(payload, options = {}) {
  reportBuilderApplyingLayout = true;
  try {
    reportBuilderPages = normalizeReportBuilderPages(payload?.pages);
    reportBuilderActivePageId = reportBuilderPages[0]?.id || 'page-1';
    reportBuilderBlockSeq = collectReportBuilderPageIds(reportBuilderPages).length + reportBuilderPages.reduce((sum, page) => sum + page.blocks.length, 0) + 1;
    reportBuilderCurrentLayoutId = options.layoutId ?? reportBuilderCurrentLayoutId;
    reportBuilderCurrentVersionId = options.versionId ?? reportBuilderCurrentVersionId;
    setReportBuilderTitle(options.title || payload?.title || reportBuilderCurrentTitle);

    const ids = collectReportBuilderPageIds(reportBuilderPages);
    reportBuilderSelectedReports = new Set(ids);
    const missing = await loadReportBuilderReportsLenient(ids);
    renderConsolidatedPicker();
    renderReportBuilderPages();
    if (missing.length) {
      showConsolidatedError(`Alguns dashboards salvos nao estao mais disponiveis: ${missing.join(', ')}.`);
    }
  } finally {
    reportBuilderApplyingLayout = false;
  }
}

function activeReportBuilderPage() {
  let page = reportBuilderPages.find(item => item.id === reportBuilderActivePageId);
  if (!page) {
    page = reportBuilderPages[0];
    reportBuilderActivePageId = page.id;
  }
  return page;
}

function getSelectedBuilderCharts() {
  return Array.from(document.querySelectorAll('.report-builder-chart-check:checked')).map(input => {
    const chartId = input.value;
    const typeSelect = Array.from(document.querySelectorAll('.report-builder-chart-type'))
      .find(select => select.dataset.chartId === chartId);
    const sizeSelect = Array.from(document.querySelectorAll('.report-builder-chart-size'))
      .find(select => select.dataset.chartId === chartId);
    return {
      chartId,
      type: typeSelect?.value || findCatalogItem(chartId)?.types?.[0] || 'bar_v',
      size: sizeSelect?.value || 'large',
    };
  });
}

function resolveBuilderBlockReportIds() {
  const selected = selectedReportIds().map(Number);
  const mode = getReportBuilderEl('reportBuilderModeInput')?.value || 'compare';
  if (mode === 'single') {
    const singleId = Number(getReportBuilderEl('reportBuilderSingleReportInput')?.value || selected[0]);
    return singleId ? [singleId] : [];
  }
  return selected;
}

async function addSelectedChartsToReportBuilder() {
  clearConsolidatedError();
  const reportIds = resolveBuilderBlockReportIds();
  if (!reportIds.length) {
    showConsolidatedError('Selecione pelo menos 1 dashboard.');
    return;
  }

  const selectedCharts = getSelectedBuilderCharts();
  if (!selectedCharts.length) {
    showConsolidatedError('Marque pelo menos 1 grafico.');
    return;
  }

  const button = getReportBuilderEl('btnBuildConsolidated');
  if (button) {
    button.disabled = true;
    button.textContent = 'Adicionando...';
  }

  try {
    await loadReportBuilderReports(reportIds);
    const page = activeReportBuilderPage();
    selectedCharts.forEach(chart => {
      page.blocks.push({
        id: `rb-${Date.now()}-${reportBuilderBlockSeq++}`,
        chartId: chart.chartId,
        type: chart.type,
        size: chart.size,
        reportIds: [...reportIds],
      });
    });
    markReportBuilderDirty();
    renderReportBuilderPages();
  } catch (err) {
    showConsolidatedError(err.message);
  } finally {
    if (button) {
      button.disabled = false;
      button.textContent = 'Adicionar selecionados';
    }
  }
}

function addReportBuilderPage() {
  const next = reportBuilderPages.length + 1;
  const page = { id: `page-${Date.now()}`, name: `Pagina ${next}`, blocks: [] };
  reportBuilderPages.push(page);
  reportBuilderActivePageId = page.id;
  markReportBuilderDirty();
  renderReportBuilderPages();
}

function setReportBuilderActivePage(pageId) {
  reportBuilderActivePageId = pageId;
  renderReportBuilderPages();
}

function clearReportBuilder() {
  if (reportBuilderPages.some(page => page.blocks.length) && !confirm('Limpar todos os blocos do relatorio?')) return;
  reportBuilderPages = [{ id: 'page-1', name: 'Pagina 1', blocks: [] }];
  reportBuilderActivePageId = 'page-1';
  markReportBuilderDirty();
  renderReportBuilderPages();
}

function setReportBuilderSavedState(layout, version) {
  if (layout?.id) reportBuilderCurrentLayoutId = Number(layout.id);
  if (version?.id) reportBuilderCurrentVersionId = Number(version.id);
  if (layout?.title) setReportBuilderTitle(layout.title);
  const versionLabel = version?.version_number ? `v${version.version_number}` : 'salvo';
  const timeLabel = version?.created_at ? fmtDateTime(version.created_at) : 'agora';
  setReportBuilderStatus(`Salvo ${versionLabel} em ${timeLabel}`, 'saved');
}

async function saveReportBuilder(saveAs = false) {
  if (reportBuilderSaving) return;
  clearConsolidatedError();

  let title = reportBuilderTitleValue();
  if (saveAs) {
    const suggested = reportBuilderCurrentLayoutId ? `${title} - copia` : title;
    const chosen = prompt('Nome do novo relatorio', suggested);
    if (chosen === null) return;
    title = String(chosen || '').trim() || 'Relatorio visual';
    setReportBuilderTitle(title);
  }

  reportBuilderSaving = true;
  setReportBuilderStatus('Salvando...', 'saving');
  try {
    const payload = captureReportBuilderPayload();
    payload.title = title;
    const creating = saveAs || !reportBuilderCurrentLayoutId;
    const endpoint = creating ? '/api/report-layouts' : `/api/report-layouts/${reportBuilderCurrentLayoutId}`;
    const method = creating ? 'POST' : 'PATCH';
    const body = await apiRequest(endpoint, {
      method,
      csrf: true,
      json: { title, payload, note: creating ? 'Criacao' : 'Atualizacao' },
    });
    setReportBuilderSavedState(body.layout, body.version);
  } catch (err) {
    setReportBuilderStatus('Falha ao salvar', 'error');
    showConsolidatedError(err.message);
  } finally {
    reportBuilderSaving = false;
  }
}

function showReportBuilderModal(title, sub, html) {
  const modal = getReportBuilderEl('reportBuilderModal');
  const titleEl = getReportBuilderEl('reportBuilderModalTitle');
  const subEl = getReportBuilderEl('reportBuilderModalSub');
  const bodyEl = getReportBuilderEl('reportBuilderModalBody');
  if (!modal || !titleEl || !subEl || !bodyEl) return;
  titleEl.textContent = title || '';
  subEl.textContent = sub || '';
  bodyEl.innerHTML = html || '';
  modal.classList.remove('hidden');
}

function closeReportBuilderModal() {
  getReportBuilderEl('reportBuilderModal')?.classList.add('hidden');
}

function handleReportBuilderModalBackdrop(event) {
  if (event.target?.id === 'reportBuilderModal') closeReportBuilderModal();
}

function renderSavedReportLayouts(layouts) {
  if (!layouts.length) {
    return '<div class="report-builder-empty">Nenhuma montagem salva ainda.</div>';
  }
  return layouts.map(layout => {
    const latest = layout.latest_version;
    const active = Number(layout.id) === Number(reportBuilderCurrentLayoutId);
    return `
      <article class="report-builder-saved-item ${active ? 'active' : ''}">
        <div>
          <div class="report-builder-saved-title">${esc(layout.title || 'Relatorio sem nome')}</div>
          <div class="report-builder-saved-meta">
            ${esc(latest?.version_number ? `v${latest.version_number}` : 'sem versao')} &middot;
            ${esc(fmtDateTime(layout.updated_at))} &middot;
            ${Number(layout.version_count || 0)} versao(oes)
          </div>
        </div>
        <div class="report-builder-saved-actions">
          <button class="btn-small" type="button" onclick="loadSavedReportBuilderLayout(${Number(layout.id)})">Abrir</button>
          <button class="btn-small" type="button" onclick="deleteSavedReportBuilderLayout(${Number(layout.id)})">Arquivar</button>
        </div>
      </article>
    `;
  }).join('');
}

async function openReportBuilderLibrary() {
  showReportBuilderModal('Relatorios salvos', 'Montagens visuais salvas para editar ou imprimir depois.', '<div class="report-builder-empty">Carregando...</div>');
  try {
    const body = await apiRequest('/api/report-layouts');
    showReportBuilderModal(
      'Relatorios salvos',
      `${(body.layouts || []).length} montagem(ns) disponivel(is).`,
      renderSavedReportLayouts(body.layouts || [])
    );
  } catch (err) {
    showReportBuilderModal('Relatorios salvos', '', `<div class="report-builder-empty error">${esc(err.message)}</div>`);
  }
}

async function loadSavedReportBuilderLayout(layoutId) {
  clearConsolidatedError();
  setReportBuilderStatus('Abrindo relatorio...', 'saving');
  try {
    const body = await apiRequest(`/api/report-layouts/${layoutId}`);
    await applyReportBuilderPayload(body.payload, {
      layoutId: body.layout?.id,
      versionId: body.version?.id,
      title: body.layout?.title,
    });
    setReportBuilderSavedState(body.layout, body.version);
    closeReportBuilderModal();
  } catch (err) {
    setReportBuilderStatus('Falha ao abrir', 'error');
    showConsolidatedError(err.message);
  }
}

async function deleteSavedReportBuilderLayout(layoutId) {
  if (!confirm('Arquivar este relatorio salvo? O historico deixa de aparecer na lista principal.')) return;
  try {
    await apiRequest(`/api/report-layouts/${layoutId}`, { method: 'DELETE', csrf: true });
    if (Number(layoutId) === Number(reportBuilderCurrentLayoutId)) {
      reportBuilderCurrentLayoutId = null;
      reportBuilderCurrentVersionId = null;
      markReportBuilderDirty();
    }
    await openReportBuilderLibrary();
  } catch (err) {
    showReportBuilderModal('Relatorios salvos', '', `<div class="report-builder-empty error">${esc(err.message)}</div>`);
  }
}

function renderReportBuilderVersions(versions) {
  if (!versions.length) return '<div class="report-builder-empty">Sem versoes salvas.</div>';
  return versions.map(version => `
    <article class="report-builder-saved-item ${Number(version.id) === Number(reportBuilderCurrentVersionId) ? 'active' : ''}">
      <div>
        <div class="report-builder-saved-title">Versao ${Number(version.version_number || 0)}</div>
        <div class="report-builder-saved-meta">${esc(fmtDateTime(version.created_at))}${version.note ? ` &middot; ${esc(version.note)}` : ''}</div>
      </div>
      <div class="report-builder-saved-actions">
        <button class="btn-small" type="button" onclick="loadReportBuilderVersion(${Number(version.layout_id)}, ${Number(version.id)})">Abrir</button>
        <button class="btn-small" type="button" onclick="restoreReportBuilderVersion(${Number(version.layout_id)}, ${Number(version.id)})">Restaurar</button>
        <button class="btn-small" type="button" onclick="deleteReportBuilderVersion(${Number(version.layout_id)}, ${Number(version.id)})">Excluir</button>
      </div>
    </article>
  `).join('');
}

async function openReportBuilderHistory() {
  if (!reportBuilderCurrentLayoutId) {
    showReportBuilderModal('Historico', 'Abra ou salve uma montagem antes de consultar as versoes.', '<div class="report-builder-empty">Nenhum relatorio salvo esta aberto.</div>');
    return;
  }
  showReportBuilderModal('Historico', 'Versoes salvas deste relatorio.', '<div class="report-builder-empty">Carregando...</div>');
  try {
    const body = await apiRequest(`/api/report-layouts/${reportBuilderCurrentLayoutId}/versions`);
    showReportBuilderModal(
      'Historico',
      body.layout?.title || 'Versoes salvas deste relatorio.',
      renderReportBuilderVersions(body.versions || [])
    );
  } catch (err) {
    showReportBuilderModal('Historico', '', `<div class="report-builder-empty error">${esc(err.message)}</div>`);
  }
}

async function loadReportBuilderVersion(layoutId, versionId) {
  clearConsolidatedError();
  setReportBuilderStatus('Abrindo versao...', 'saving');
  try {
    const body = await apiRequest(`/api/report-layouts/${layoutId}/versions/${versionId}`);
    await applyReportBuilderPayload(body.payload, {
      layoutId: body.layout?.id,
      versionId: body.version?.id,
      title: body.layout?.title,
    });
    const versionNumber = body.version?.version_number || '';
    setReportBuilderStatus(`Versao ${versionNumber} aberta. Salvar cria nova versao.`, 'dirty');
    closeReportBuilderModal();
  } catch (err) {
    setReportBuilderStatus('Falha ao abrir versao', 'error');
    showConsolidatedError(err.message);
  }
}

async function restoreReportBuilderVersion(layoutId, versionId) {
  if (!confirm('Restaurar esta versao como a versao mais recente?')) return;
  clearConsolidatedError();
  setReportBuilderStatus('Restaurando versao...', 'saving');
  try {
    const body = await apiRequest(`/api/report-layouts/${layoutId}/versions/${versionId}/restore`, {
      method: 'POST',
      csrf: true,
      json: { note: 'Restauracao pelo historico' },
    });
    await applyReportBuilderPayload(body.payload, {
      layoutId: body.layout?.id,
      versionId: body.version?.id,
      title: body.layout?.title,
    });
    setReportBuilderSavedState(body.layout, body.version);
    closeReportBuilderModal();
  } catch (err) {
    setReportBuilderStatus('Falha ao restaurar', 'error');
    showConsolidatedError(err.message);
  }
}

async function deleteReportBuilderVersion(layoutId, versionId) {
  if (!confirm('Excluir esta versao do historico? A montagem aberta na tela nao sera alterada.')) return;
  clearConsolidatedError();
  try {
    const body = await apiRequest(`/api/report-layouts/${layoutId}/versions/${versionId}`, {
      method: 'DELETE',
      csrf: true,
    });
    if (Number(versionId) === Number(reportBuilderCurrentVersionId)) {
      reportBuilderCurrentVersionId = body.latest_version?.id || null;
      setReportBuilderStatus('Versao aberta foi excluida do historico. Salvar cria uma nova versao.', 'dirty');
    }
    await openReportBuilderHistory();
  } catch (err) {
    showConsolidatedError(err.message);
    showReportBuilderModal('Historico', '', `<div class="report-builder-empty error">${esc(err.message)}</div>`);
  }
}

function removeReportBuilderBlock(pageId, blockId) {
  const page = reportBuilderPages.find(item => item.id === pageId);
  if (!page) return;
  page.blocks = page.blocks.filter(block => block.id !== blockId);
  markReportBuilderDirty();
  renderReportBuilderPages();
}

function updateReportBuilderBlockSize(pageId, blockId, size) {
  const page = reportBuilderPages.find(item => item.id === pageId);
  const block = page?.blocks.find(item => item.id === blockId);
  if (!block) return;
  block.size = size;
  markReportBuilderDirty();
  renderReportBuilderPages();
}

function reportBuilderBlockLabel(block) {
  const catalog = findCatalogItem(block.chartId);
  return catalog?.name || block.chartId;
}

function reportBuilderBlockMeta(block) {
  if (block.reportIds.length > 1) return `${block.reportIds.length} dashboards lado a lado`;
  const loaded = reportBuilderLoadedReports.get(Number(block.reportIds[0]));
  return loaded ? reportDisplayName(loaded.report) : 'Dashboard';
}

function reportBuilderCardClasses(block) {
  return [
    'report-builder-card',
    `report-builder-card-${block.size}`,
    block.chartId === 'roadmap' && block.type === 'timeline' ? 'report-builder-card-roadmap-timeline' : '',
  ].filter(Boolean).join(' ');
}

function renderReportBuilderPages() {
  const tabs = getReportBuilderEl('reportBuilderPageTabs');
  const pagesEl = getReportBuilderEl('reportBuilderPages');
  if (!tabs || !pagesEl) return;

  tabs.innerHTML = reportBuilderPages.map(page => `
    <button class="btn-small ${page.id === reportBuilderActivePageId ? 'active' : ''}" type="button" onclick="setReportBuilderActivePage('${esc(page.id)}')">
      ${esc(page.name)}
    </button>
  `).join('');

  pagesEl.innerHTML = reportBuilderPages.map(page => `
    <section class="report-builder-page ${page.id === reportBuilderActivePageId ? 'active' : ''}"
      ondragover="allowReportBuilderDrop(event)"
      ondrop="dropReportBuilderBlock(event, '${esc(page.id)}')">
      <div class="report-builder-page-head">
        <div>
          <div class="report-builder-page-title">${esc(page.name)}</div>
          <div class="report-builder-page-sub">${page.blocks.length ? `${page.blocks.length} bloco(s)` : 'Arraste ou adicione graficos nesta pagina.'}</div>
        </div>
      </div>
      <div class="report-builder-grid">
        ${page.blocks.map(block => `
          <article class="${esc(reportBuilderCardClasses(block))}"
            draggable="true"
            ondragstart="startReportBuilderDrag(event, '${esc(page.id)}', '${esc(block.id)}')"
            ondragover="allowReportBuilderDrop(event)"
            ondrop="dropReportBuilderBlock(event, '${esc(page.id)}', '${esc(block.id)}')">
            <div class="report-builder-card-head">
              <div>
                <div class="report-builder-card-title">${esc(reportBuilderBlockLabel(block))}</div>
                <div class="report-builder-card-sub">${esc(reportBuilderBlockMeta(block))} · ${esc(CHART_TYPES[block.type]?.label || block.type)}</div>
              </div>
              <div class="report-builder-card-actions">
                <select onchange="updateReportBuilderBlockSize('${esc(page.id)}', '${esc(block.id)}', this.value)">
                  ${Object.entries(REPORT_BUILDER_SIZES).map(([value, label]) => `
                    <option value="${esc(value)}"${block.size === value ? ' selected' : ''}>${esc(label)}</option>
                  `).join('')}
                </select>
                <button class="btn-small" type="button" onclick="removeReportBuilderBlock('${esc(page.id)}', '${esc(block.id)}')">Remover</button>
              </div>
            </div>
            <div class="report-builder-card-body" id="reportBuilderBody-${esc(block.id)}"></div>
          </article>
        `).join('')}
      </div>
    </section>
  `).join('');

  setTimeout(renderAllReportBuilderBlocks, 60);
}

function startReportBuilderDrag(event, pageId, blockId) {
  reportBuilderDraggedBlock = { pageId, blockId };
  event.dataTransfer.effectAllowed = 'move';
  event.dataTransfer.setData('text/plain', blockId);
}

function allowReportBuilderDrop(event) {
  event.preventDefault();
}

function dropReportBuilderBlock(event, targetPageId, beforeBlockId = null) {
  event.preventDefault();
  event.stopPropagation();
  if (!reportBuilderDraggedBlock) return;
  if (beforeBlockId && beforeBlockId === reportBuilderDraggedBlock.blockId) {
    reportBuilderDraggedBlock = null;
    return;
  }

  const sourcePage = reportBuilderPages.find(page => page.id === reportBuilderDraggedBlock.pageId);
  const targetPage = reportBuilderPages.find(page => page.id === targetPageId);
  if (!sourcePage || !targetPage) return;

  const sourceIndex = sourcePage.blocks.findIndex(block => block.id === reportBuilderDraggedBlock.blockId);
  if (sourceIndex < 0) return;
  const [block] = sourcePage.blocks.splice(sourceIndex, 1);

  let targetIndex = beforeBlockId
    ? targetPage.blocks.findIndex(item => item.id === beforeBlockId)
    : targetPage.blocks.length;
  if (targetIndex < 0) targetIndex = targetPage.blocks.length;
  if (targetPage === sourcePage && sourceIndex < targetIndex) targetIndex -= 1;
  targetPage.blocks.splice(targetIndex, 0, block);
  reportBuilderActivePageId = targetPageId;
  reportBuilderDraggedBlock = null;
  markReportBuilderDirty();
  renderReportBuilderPages();
}

function buildReportBuilderTimingChart(chartId, type, data) {
  const rows = chartId === 'rotulos' ? data.rotulos_rows : data.resp_rows;
  if (!rows?.length) return { traces: null };

  const labels = rows.map(row => cleanChartLabel(row[0]));
  const lead = rows.map(row => row[3] ?? 0);
  const cycle = rows.map(row => row[4] ?? 0);
  const horiz = type === 'bar_h';
  const mk = (name, values, color) => ({
    type: 'bar',
    name,
    x: horiz ? values : labels,
    y: horiz ? labels : values,
    orientation: horiz ? 'h' : 'v',
    marker: { color },
    customdata: labelHoverData(labels),
    hovertemplate: '<b>%{customdata}</b><br>' + name + ': %{'+(horiz ? 'x' : 'y')+'} dia(s)<extra></extra>',
  });

  return {
    traces: [mk('Lead Time', lead, pc(3)), mk('Cycle Time', cycle, pc(0))],
    layout: plotLayout({
      barmode: 'group',
      margin: { t: 20, r: 15, b: horiz ? 45 : 95, l: horiz ? 185 : 55 },
      xaxis: horiz ? { tickangle: 0, title: { text: 'Dias' } } : { ...labelAxis(labels, 32), tickangle: -30, title: { text: '' } },
      yaxis: horiz ? { ...labelAxis(labels, 34), title: { text: '' } } : { title: { text: 'Dias' } },
    }),
  };
}

function buildReportBuilderBurndownSP(bsp, type, data) {
  if (!bsp?.rows) return { traces: null };
  const valid = bsp.rows.filter(row => row[0] !== null);
  const dates = valid.map(row => row[0]);
  const meta = valid.map(row => row[1]);
  const realized = valid.map(row => row[2]);
  const scopeTotal = valid.map(row => row[3]);
  const metaOriginal = valid.map(row => row[4]);
  const hasScope = (bsp.scope_events || []).length || valid.some(row => Number(row[5] || 0) > 0);
  const totalSp = bsp.total_sp || 0;
  const huNames = data?.hu_full_names || {};
  const huLines = Object.entries(bsp.hu_sp || {})
    .sort((a, b) => b[1] - a[1])
    .slice(0, 10)
    .map(([hu, sp]) => `${(huNames[hu] || hu).substring(0, 45)}: ${sp} SP`)
    .join('<br>');

  const mk = (name, y, color, dash) => type === 'bar_v'
    ? { type: 'bar', name, x: dates, y, marker: { color } }
    : {
        type: 'scatter',
        mode: 'lines',
        name,
        x: dates,
        y,
        line: { color, dash: dash || 'solid', width: 2.5 },
        fill: type === 'area' ? 'tozeroy' : 'none',
        fillcolor: type === 'area' ? color + '22' : undefined,
      };

  const traces = hasScope
    ? [
        mk('Meta original', metaOriginal, pc(8), 'dash'),
        mk('Meta revisada', meta, pc(3), 'dash'),
        mk('Escopo acumulado', scopeTotal, pc(9), 'dot'),
        mk('A Realizar (SP)', realized, pc(0)),
      ]
    : [mk('Meta Linear', meta, pc(8), 'dash'), mk('A Realizar (SP)', realized, pc(0))];
  const eventVisuals = buildScopeEventMarkers(bsp.scope_events || [], 'SP', 'sp');
  const topMargin = eventVisuals.topMargin || 30;
  return {
    traces,
    layout: plotLayout({
      barmode: 'group',
      xaxis: { type: 'date', tickformat: '%d/%m' },
      yaxis: { title: { text: `SP (total: ${totalSp})` } },
      margin: { t: topMargin, r: 20, b: 50, l: 65 },
      shapes: eventVisuals.shapes,
      annotations: [
        ...eventVisuals.annotations,
        ...(huLines ? [{
        xref: 'paper',
        yref: 'paper',
        x: 1,
        y: 1,
        xanchor: 'right',
        yanchor: 'top',
        text: `<b>SP por HU</b><br>${huLines}`,
        showarrow: false,
        align: 'right',
        font: { size: 10, color: 'var(--muted)' },
        bgcolor: 'rgba(0,0,0,0)',
        bordercolor: 'rgba(0,0,0,0)',
      }] : []),
      ],
    }),
  };
}

function reportBuilderTaskReferenceDate(data) {
  const today = new Date();
  const todayDate = new Date(today.getFullYear(), today.getMonth(), today.getDate());
  const sprintEnd = parseIsoDate(data?.meta?.sprint_end);
  return sprintEnd && todayDate > sprintEnd ? sprintEnd : todayDate;
}

function buildReportBuilderAgingRows(data, view = 'areas') {
  if (!data?.task_rows?.length) return [];

  const selectedView = AGING_VIEW_OPTIONS.includes(view) ? view : 'areas';
  const refDate = reportBuilderTaskReferenceDate(data);
  const groups = new Map();
  const dayMs = 24 * 60 * 60 * 1000;

  (data.task_rows || []).forEach(task => {
    if (parseIsoDate(task?.date_done)) return;
    const createdDate = parseIsoDate(task?.date_created || task?.date_criacao);
    const startDate = parseIsoDate(task?.date_start);
    const baseDate = createdDate || startDate;
    if (!baseDate || baseDate > refDate) return;

    const ageDays = Math.floor((refDate.getTime() - baseDate.getTime()) / dayMs);
    if (ageDays < 0) return;

    collectAgingTokens(task, selectedView).forEach(({ key, label }) => {
      if (!key) return;
      const current = groups.get(key) || { label, totalAge: 0, count: 0 };
      current.totalAge += ageDays;
      current.count += 1;
      if (!current.label) current.label = label;
      groups.set(key, current);
    });
  });

  return Array.from(groups.values())
    .filter(item => item.count > 0)
    .map(item => [`${item.label} (${item.count})`, Number((item.totalAge / item.count).toFixed(2))])
    .sort((a, b) => b[1] - a[1] || a[0].localeCompare(b[0], 'pt-BR'));
}

function buildReportBuilderAgingTaskRows(data) {
  if (!data?.task_rows?.length) return [];

  const refDate = reportBuilderTaskReferenceDate(data);
  const dayMs = 24 * 60 * 60 * 1000;

  return (data.task_rows || [])
    .filter(task => !parseIsoDate(task?.date_done))
    .map((task, index) => {
      const createdDate = parseIsoDate(task?.date_created || task?.date_criacao);
      const startDate = parseIsoDate(task?.date_start);
      const baseDate = createdDate || startDate;
      if (!baseDate || baseDate > refDate) return null;

      const ageDays = Math.floor((refDate.getTime() - baseDate.getTime()) / dayMs);
      if (ageDays < 0) return null;

      const title = String(task?.title || '').trim() || `Tarefa ${index + 1}`;
      return [title, ageDays];
    })
    .filter(Boolean)
    .sort((a, b) => b[1] - a[1] || a[0].localeCompare(b[0], 'pt-BR'))
    .slice(0, 20);
}

function buildReportBuilderSingleMetricRows(sourceKey, metric, data) {
  let rows = [];
  switch (sourceKey) {
    case 'hu_tasks':
      rows = (data.hu_list || []).map(row => {
        const done = Number(row[1] || 0);
        const pending = Number(row[2] || 0);
        const value = metric === 'done' ? done : metric === 'pending' ? pending : done + pending;
        return [data.hu_full_names?.[row[0]] || row[0], value];
      });
      break;
    case 'areas':
      rows = (data.area_rows || []).map(row => [row[0], metric === 'done' ? Number(row[1] || 0) : metric === 'pending' ? Number(row[2] || 0) : Number(row[1] || 0) + Number(row[2] || 0)]);
      break;
    case 'categoria':
      rows = (data.cat_rows || []).map(row => [row[0], metric === 'done' ? Number(row[1] || 0) : metric === 'pending' ? Number(row[2] || 0) : Number(row[1] || 0) + Number(row[2] || 0)]);
      break;
    case 'colaborador':
      rows = (data.collab_rows || []).map(row => [row[0], metric === 'done' ? Number(row[1] || 0) : metric === 'pending' ? Number(row[2] || 0) : Number(row[1] || 0) + Number(row[2] || 0)]);
      break;
    case 'hu_inout':
      rows = (data.in_out || []).map(row => [row[0], Number(row[1] || 0)]);
      break;
    case 'rotulos':
      rows = (data.rotulos_rows || []).map(row => {
        const value = metric === 'done' ? Number(row[1] || 0)
          : metric === 'pending' ? Number(row[2] || 0)
            : metric === 'lead_time' ? Number(row[3] || 0)
              : Number(row[4] || 0);
        return [row[0], value];
      });
      break;
    case 'responsaveis':
      rows = (data.resp_rows || []).map(row => {
        const value = metric === 'done' ? Number(row[1] || 0)
          : metric === 'pending' ? Number(row[2] || 0)
            : metric === 'lead_time' ? Number(row[3] || 0)
              : Number(row[4] || 0);
        return [row[0], value];
      });
      break;
    case 'aging_tasks':
      rows = buildReportBuilderAgingTaskRows(data);
      break;
    case 'histograma':
      rows = (data.hist_31 || []).map((value, index) => [`${index + 1} dia${index + 1 === 1 ? '' : '(s)'}`, Number(value || 0)]);
      break;
    default:
      rows = [];
  }

  rows = rows
    .filter(row => row && row[0] !== null && row[0] !== undefined && Number.isFinite(Number(row[1])))
    .map(row => [String(row[0]), Number(row[1])]);

  if (sourceKey !== 'histograma') rows = rows.filter(row => row[1] > 0);
  return rows;
}

function applyReportBuilderCustomSort(rows, chart) {
  const sorter = chart.sort_mode || 'metric_desc';
  const sorted = [...rows];
  sorted.sort((a, b) => {
    if (sorter === 'metric_asc') return a[1] - b[1] || a[0].localeCompare(b[0], 'pt-BR');
    if (sorter === 'label_asc') return a[0].localeCompare(b[0], 'pt-BR');
    if (sorter === 'label_desc') return b[0].localeCompare(a[0], 'pt-BR');
    return b[1] - a[1] || a[0].localeCompare(b[0], 'pt-BR');
  });

  const limit = Number(chart.limit || 0);
  const limited = limit > 0 ? sorted.slice(0, limit) : sorted;
  if (chart.source_key === 'histograma' && chart.sort_mode?.startsWith('label')) {
    limited.sort((a, b) => parseInt(a[0], 10) - parseInt(b[0], 10));
  }
  return limited;
}

function buildReportBuilderCustomChart(chart, type, data) {
  if (chart.source_key === 'wip_profile') return chartWIP(data.wip, type);
  const rows = applyReportBuilderCustomSort(
    buildReportBuilderSingleMetricRows(chart.source_key, chart.metric_key, data),
    chart
  );
  return chartSingleMetric(rows, type || chart.chart_type || 'bar_v', metricLabelForCustomChart(chart));
}

function buildReportBuilderChart(chartId, type, data) {
  const customChart = getCustomChartByChartId(chartId);
  if (customChart) return buildReportBuilderCustomChart(customChart, type, data);

  switch (chartId) {
    case 'delivery_person':
      return chartPersonDelivery(type, { data, selectedPeople: 'Todos' });
    case 'burndown':
      return chartBurndown(data.burndown?.rows, type, 'Meta', 'Planejado', 'A Realizar', {
        scopeEvents: data.burndown?.scope_events,
        scopeUnit: 'tarefas',
        scopeValueKey: 'count',
      });
    case 'burndown_hu':
      return chartBurndown(data.burndown_hu?.rows, type, 'Meta', 'Planejado', 'A Realizar', {
        scopeEvents: data.burndown_hu?.scope_events,
        scopeUnit: 'tarefas',
        scopeValueKey: 'weight',
      });
    case 'burndown_sp':
      return buildReportBuilderBurndownSP(data.burndown_sp, type, data);
    case 'burnup':
      return chartBurnup(data.burndown?.rows, type, {
        yTitle: 'Tarefas',
        scopeEvents: data.burndown?.scope_events,
        scopeUnit: 'tarefas',
        scopeValueKey: 'count',
      });
    case 'burnup_hu':
      return chartBurnup(data.burndown_hu?.rows, type, {
        yTitle: 'Tarefas',
        scopeEvents: data.burndown_hu?.scope_events,
        scopeUnit: 'tarefas',
        scopeValueKey: 'weight',
      });
    case 'burnup_sp':
      return chartBurnup(data.burndown_sp?.rows, type, {
        yTitle: `SP (total: ${data.burndown_sp?.total_sp || 0})`,
        remainingIndex: 2,
        scopeIndex: 3,
        planIndex: -1,
        metaOriginalIndex: 4,
        addedIndex: 5,
        fallbackTotal: data.burndown_sp?.total_sp || 0,
        scopeEvents: data.burndown_sp?.scope_events,
        scopeUnit: 'SP',
        scopeValueKey: 'sp',
      });
    case 'burndown_nao_prev':
      return chartBurndown(data.burndown_nao_prev?.rows, type, 'Meta', 'Planejado', 'A Realizar', {
        scopeEvents: data.burndown_nao_prev?.scope_events,
        scopeUnit: 'tarefas',
        scopeValueKey: 'count',
      });
    case 'burnup_nao_prev':
      return chartBurnup(data.burndown_nao_prev?.rows, type, {
        yTitle: 'Tarefas n\u00e3o previstas',
        scopeEvents: data.burndown_nao_prev?.scope_events,
        scopeUnit: 'tarefas',
        scopeValueKey: 'count',
      });
    case 'burndown_nao_prev_hu':
      return chartBurndown(data.burndown_nao_prev_hu?.rows, type, 'Meta', 'Planejado', 'A Realizar', {
        scopeEvents: data.burndown_nao_prev_hu?.scope_events,
        scopeUnit: 'tarefas',
        scopeValueKey: 'count',
      });
    case 'burnup_nao_prev_hu':
      return chartBurnup(data.burndown_nao_prev_hu?.rows, type, {
        yTitle: 'Tarefas n\u00e3o previstas em HU',
        scopeEvents: data.burndown_nao_prev_hu?.scope_events,
        scopeUnit: 'tarefas',
        scopeValueKey: 'count',
      });
    case 'cfd':
      return chartCFD(data.cfd, type);
    case 'wip':
      return chartWIP(data.wip, type);
    case 'hu_tasks':
      return chartGrouped((data.hu_list || []).map(row => [data.hu_full_names?.[row[0]] || row[0], row[1], row[2]]), type, 'Concluidas', 'Pendentes');
    case 'areas':
      return chartGrouped(data.area_rows, type, 'Concluidas', 'Pendentes');
    case 'categoria':
      return chartGrouped(data.cat_rows, type, 'Concluidas', 'Pendentes');
    case 'colaborador':
      return chartGrouped(data.collab_rows, type, 'Concluidas', 'Pendentes');
    case 'hu_inout':
      return chartInOut(data.in_out, type);
    case 'dispersao':
      return chartDispersao(data, type);
    case 'rotulos':
    case 'responsaveis':
      return buildReportBuilderTimingChart(chartId, type, data);
    case 'aging':
      return chartSingleMetric(buildReportBuilderAgingRows(data, 'areas'), type, 'Aging medio (dias)');
    case 'aging_tasks':
      return chartSingleMetric(buildReportBuilderAgingTaskRows(data), 'bar_h', 'Aging (dias)');
    case 'histograma':
      return chartHistograma(data.hist_31, data.indicativos, type);
    default:
      return { traces: null };
  }
}

function compactBuilderLayout(layout, options = {}) {
  const isDeliveryPersonShare = options.chartId === 'delivery_person' && ['pie', 'donut'].includes(options.type);
  const topMargin = layout?.annotations?.length
    ? Math.max(Number(layout?.margin?.t || 0), isDeliveryPersonShare ? 76 : 64)
    : 18;
  const bottomMargin = isDeliveryPersonShare
    ? Math.max(Number(layout?.margin?.b || 0), 64)
    : Number(layout?.margin?.b || 50);
  const legend = isDeliveryPersonShare
    ? { ...(layout?.legend || {}), orientation: 'h', x: 0, y: -0.12, yanchor: 'top' }
    : { orientation: 'h', x: 0, y: 1.14, ...(layout?.legend || {}) };
  return {
    ...layout,
    autosize: true,
    margin: { ...(layout?.margin || {}), t: topMargin, r: 12, b: bottomMargin },
    legend,
  };
}

function renderBuilderKpis(target, data) {
  const kpis = data.kpis || {};
  const total = Number(kpis.total || 0);
  const pct = total ? Math.round(Number(kpis.done || 0) / total * 100) : 0;
  const num = (...values) => {
    for (const value of values) {
      if (value === null || value === undefined || value === '') continue;
      const parsed = Number(value);
      if (Number.isFinite(parsed)) return parsed;
    }
    return null;
  };
  const fmt = (value, digits = 0) => {
    const parsed = num(value);
    if (parsed === null) return '-';
    if (digits > 0) return parsed.toFixed(digits);
    return Number.isInteger(parsed) ? String(parsed) : parsed.toFixed(1).replace(/\.0$/, '');
  };
  const sprintDays = getSprintDayMetrics(data.meta || {});
  const items = [
    ['Total', kpis.total, 'tarefas'],
    ['Concluidas', kpis.done, `${pct}% do total`],
    ['Pendentes', kpis.pending, 'tarefas'],
    ['Fora de HU', kpis.sem_hu, 'tarefas'],
    ['Qtd HUs', fmt(kpis.hu_count, 0), 'HUs'],
    ['Responsaveis', fmt(kpis.stakeholders, 0), 'pessoas'],
    ['Cycle SP', fmt(kpis.ct_sp, 1), 'dias'],
    ['Lead SP', fmt(kpis.lt_sp, 1), 'dias'],
    ['Cycle tarefa', fmt(kpis.ct_task, 1), 'dias'],
    ['Lead tarefa', fmt(kpis.lt_task, 1), 'dias'],
    ['Dias corridos', fmt(kpis.sprint_days_calendar ?? sprintDays.calendar, 0), 'dias'],
    ['Dias uteis', fmt(kpis.sprint_days_business ?? sprintDays.business, 0), 'dias'],
  ];
  target.innerHTML = `<div class="report-builder-kpi-grid">${
    items.map(([label, value, unit]) => `
      <div class="report-builder-kpi">
        <span>${esc(label)}</span>
        <strong>${esc(value ?? '-')}</strong>
        <small>${esc(unit || '')}</small>
      </div>
    `).join('')
  }</div>`;
}

function renderBuilderMetricCards(target, data, chartId) {
  const num = value => {
    if (value === null || value === undefined || value === '') return null;
    const parsed = Number(value);
    return Number.isFinite(parsed) ? parsed : null;
  };
  const fmt = (value, digits = 1) => {
    const parsed = num(value);
    if (parsed === null) return '-';
    if (digits > 0) return parsed.toFixed(digits);
    return Number.isInteger(parsed) ? String(parsed) : parsed.toFixed(1).replace(/\.0$/, '');
  };
  const pct = value => num(value) === null ? '-' : `${fmt(value, 1)}%`;
  const flow = data.flow_metrics || {};
  const scope = data.scope_quality_metrics || {};
  const time = data.time_metrics || {};
  const status = { saudavel:'Saudavel', atencao:'Atencao', alerta:'Alerta' }[time.schedule_status] || '-';
  const itemsByChart = {
    flow_metrics: [
      ['WIP medio', fmt(flow.wip_avg, 1), 'tarefas/dia'],
      ['Throughput semanal', fmt(flow.throughput_weekly_avg, 1), 'tarefas/semana'],
      ['Efic. tarefa', pct(flow.flow_eff_task), 'cycle / lead'],
      ['Desvio Cycle Time', fmt(flow.cycle_time_stddev, 1), 'dias'],
    ],
    scope_quality: [
      ['Say/Do', pct(scope.say_do_ratio), 'SP'],
      ['Bugs/Ajustes', fmt(scope.bug_task_count, 0), 'tarefas'],
      ['Impedimentos', fmt(scope.impediment_task_count, 0), 'tarefas'],
      ['Scope creep', fmt(scope.scope_creep_tasks, 0), 'tarefas'],
    ],
    time_health: [
      ['Dias uteis restantes', fmt(time.days_remaining, 0), pct(time.days_remaining_pct)],
      ['Trabalho restante', fmt(time.work_remaining, 1), pct(time.work_remaining_pct)],
      ['Saude do prazo', status, time.schedule_delta_pct != null ? `${fmt(time.schedule_delta_pct, 1)} p.p.` : ''],
      ['1a resposta', fmt(time.first_response_avg, 1), 'dias'],
    ],
  };
  const items = itemsByChart[chartId] || [];
  if (!items.length) {
    target.innerHTML = '<div class="empty-state"><p>Sem dados suficientes.</p></div>';
    return;
  }
  target.innerHTML = `<div class="report-builder-kpi-grid">${
    items.map(([label, value, unit]) => `
      <div class="report-builder-kpi">
        <span>${esc(label)}</span>
        <strong>${esc(value ?? '-')}</strong>
        <small>${esc(unit || '')}</small>
      </div>
    `).join('')
  }</div>`;
}

function parseReportBuilderRoadmapItem(item) {
  const text = Array.isArray(item) ? String(item[0] || '') : String(item?.marco || '');
  const lines = text.split(/\n+/).map(line => line.trim()).filter(Boolean);
  const first = lines[0] || '';
  const dateMatch = first.match(/^(\d{2})\/(\d{2})\/(\d{4})(.*)$/);
  const date = dateMatch ? `${dateMatch[1]}/${dateMatch[2]}/${dateMatch[3]}` : first;
  const contentLines = [];
  const trailing = dateMatch?.[4]?.trim();
  if (trailing) contentLines.push(...trailing.split(/\t+|;|\s{2,}/).map(line => line.trim()).filter(Boolean));
  contentLines.push(...lines.slice(dateMatch ? 1 : 0));
  let goal = '';
  let marco = '';
  const unlabeled = [];
  let hasGoalLabel = false;
  let hasMarcoLabel = false;
  contentLines.forEach(line => {
    if (/^goal\s*:/i.test(line)) {
      hasGoalLabel = true;
      goal = line.replace(/^goal\s*:/i, '').trim();
    } else if (/^marco\s*:/i.test(line)) {
      hasMarcoLabel = true;
      marco = [marco, line.replace(/^marco\s*:/i, '').trim()].filter(Boolean).join(' ');
    } else {
      unlabeled.push(line);
    }
  });
  if (!hasGoalLabel && unlabeled.length && (hasMarcoLabel || unlabeled.length >= 2)) {
    goal = unlabeled.shift();
  }
  marco = [marco, ...unlabeled].filter(Boolean).join(' ');
  return { date, goal, marco, raw: text };
}

function reportBuilderRoadmapDateValue(dateText) {
  const match = String(dateText || '').match(/^(\d{2})\/(\d{2})\/(\d{4})/);
  if (!match) return null;
  const parsed = new Date(Number(match[3]), Number(match[2]) - 1, Number(match[1]));
  const time = parsed.getTime();
  return Number.isNaN(time) ? null : time;
}

function orderReportBuilderRoadmapItems(items) {
  return items
    .map((item, index) => ({ ...item, _order: index, _time: reportBuilderRoadmapDateValue(item.date) }))
    .sort((a, b) => {
      if (a._time !== null && b._time !== null && a._time !== b._time) return a._time - b._time;
      if (a._time !== null && b._time === null) return -1;
      if (a._time === null && b._time !== null) return 1;
      return a._order - b._order;
    });
}

function reportBuilderRoadmapMonthYear(dateText) {
  const match = String(dateText || '').match(/^(\d{2})\/(\d{2})\/(\d{4})/);
  if (!match) return { month: dateText || '--', year: '' };
  const monthNames = ['JAN','FEV','MAR','ABR','MAI','JUN','JUL','AGO','SET','OUT','NOV','DEZ'];
  return { month: monthNames[Number(match[2]) - 1] || match[2], year: match[3] };
}

function reportBuilderRoadmapShortDate(dateText) {
  const match = String(dateText || '').match(/^(\d{2})\/(\d{2})\/(\d{4})/);
  if (!match) return dateText || '--';
  return `${match[1]}/${match[2]}/${match[3].slice(-2)}`;
}

function renderBuilderRoadmapCards(items) {
  return `
    <div class="report-builder-roadmap-grid">
      ${items.map((item, index) => {
        const label = reportBuilderRoadmapMonthYear(item.date);
        return `<section class="report-builder-roadmap-item" style="--roadmap-color:${pc(index)}">
          <div class="report-builder-roadmap-date"><strong>${esc(label.month)}</strong><span>${esc(label.year)}</span></div>
          <div class="report-builder-roadmap-block"><b>Goal</b><p>${esc(item.goal || '-')}</p></div>
          <div class="report-builder-roadmap-block"><b>Marco</b><p>${esc(item.marco || '-')}</p></div>
        </section>`;
      }).join('')}
    </div>
  `;
}

function renderBuilderRoadmapTimeline(items) {
  const phaseSize = 11;
  const phases = [];
  for (let index = 0; index < items.length; index += phaseSize) phases.push(items.slice(index, index + phaseSize));
  return `<div class="report-builder-roadmap-timeline-stack">
    ${phases.map((phaseItems, phaseIndex) => `
      <section class="report-builder-roadmap-timeline-phase">
        <div class="report-builder-roadmap-timeline-phase-head"><span>Faixa ${phaseIndex + 1}</span><strong>${esc(phaseItems[0]?.date || '--')} - ${esc(phaseItems[phaseItems.length - 1]?.date || '--')}</strong></div>
        <div class="report-builder-roadmap-timeline" style="--roadmap-items:${Math.max(phaseItems.length, 1)}">
          <div class="report-builder-roadmap-axis" aria-hidden="true"></div>
          ${phaseItems.map((item, index) => {
            const label = reportBuilderRoadmapMonthYear(item.date);
            return `<article class="report-builder-roadmap-event is-top" style="--roadmap-color:${pc(phaseIndex * phaseSize + index)}">
              <span class="report-builder-roadmap-dot" aria-hidden="true"></span>
              <div class="report-builder-roadmap-timeline-card">
                <div class="report-builder-roadmap-timeline-date">
                  <strong>${esc(item.date || '--')}</strong>
                  <span>${esc(label.month)} ${esc(label.year)}</span>
                </div>
                <b>${esc(item.goal || '-')}</b>
                <p>${esc(item.marco || '-')}</p>
              </div>
            </article>`;
          }).join('')}
        </div>
      </section>
    `).join('')}
  </div>`;
}

function reportBuilderRoadmapPrintPosition(item, index, items) {
  const validTimes = items.map(entry => entry._time).filter(time => time !== null);
  if (validTimes.length > 1) {
    const min = Math.min(...validTimes);
    const max = Math.max(...validTimes);
    if (max > min && item._time !== null) {
      const pct = ((item._time - min) / (max - min)) * 100;
      return Math.max(8, Math.min(92, pct));
    }
  }
  if (items.length <= 1) return 50;
  return 8 + ((index / (items.length - 1)) * 84);
}

function renderBuilderRoadmapPrintPoster(items, data, period) {
  const projectName = data?.meta?.projeto || data?.meta?.project || data?.meta?.sprint_name || 'Projeto';
  const title = `Roadmap de Projeto - ${projectName}`;
  return `
    <div class="report-builder-roadmap-print-poster ${items.length > 16 ? 'is-dense' : ''}">
      <h1>${esc(title)}</h1>
      <div class="report-builder-roadmap-print-period">${esc(period)}</div>
      <div class="report-builder-roadmap-print-track">
        ${items.map((item, index) => {
          const color = pc(index);
          const label = reportBuilderRoadmapMonthYear(item.date);
          return `
            <section class="report-builder-roadmap-print-event" style="--roadmap-color:${color}">
              <div class="report-builder-roadmap-print-event-date">${esc(item.date || '--')} <span>${esc(label.month)} ${esc(label.year)}</span></div>
              <div class="report-builder-roadmap-print-event-block"><b>Goal</b><p>${esc(item.goal || '-')}</p></div>
              <div class="report-builder-roadmap-print-event-block"><b>Marco</b><p>${esc(item.marco || '-')}</p></div>
            </section>
          `;
        }).join('')}
      </div>
    </div>
  `;
}

function renderBuilderRoadmap(target, data, type = 'cards') {
  const items = orderReportBuilderRoadmapItems(
    (data?.roadmap_items || []).map(parseReportBuilderRoadmapItem).filter(item => item.raw)
  );
  target.classList.add('report-builder-roadmap-plot');
  if (!items.length) {
    target.innerHTML = '<div class="empty-state"><p>Sem roadmap associado a este dashboard.</p></div>';
    return;
  }
  const period = `${items[0].date || '--'} - ${items[items.length - 1].date || '--'}`;
  const isTimeline = type === 'timeline';
  target.innerHTML = `
    <div class="report-builder-roadmap ${isTimeline ? 'report-builder-roadmap--timeline' : ''}">
      <div class="report-builder-roadmap-head">
        <strong>${esc(data?.meta?.projeto || data?.meta?.sprint_name || 'Roadmap')}</strong>
        <span>${esc(period)}</span>
      </div>
      ${isTimeline ? `${renderBuilderRoadmapTimeline(items)}${renderBuilderRoadmapPrintPoster(items, data, period)}` : renderBuilderRoadmapCards(items)}
    </div>
  `;
}

function renderAllReportBuilderBlocks() {
  reportBuilderPages.forEach(page => {
    page.blocks.forEach(block => renderReportBuilderBlock(block));
  });
}

function renderReportBuilderBlock(block) {
  const host = getReportBuilderEl(`reportBuilderBody-${block.id}`);
  if (!host) return;
  const reports = block.reportIds.map(id => {
    const loaded = reportBuilderLoadedReports.get(Number(id));
    return loaded || { missing: true, id: Number(id) };
  });

  if (!reports.length) {
    host.innerHTML = '<div class="empty-state"><p>Carregue dashboards para renderizar este bloco.</p></div>';
    return;
  }

  const stackedDeliveryPerson = block.chartId === 'delivery_person' && reports.length > 1;
  host.classList.toggle('multi', reports.length > 1);
  host.classList.toggle('report-builder-card-body--stacked-delivery', stackedDeliveryPerson);
  host.innerHTML = reports.map(item => `
    <div class="report-builder-plot-panel">
      <div class="report-builder-plot-title" title="${esc(item.missing ? `Dashboard ${item.id}` : reportDisplayName(item.report))}">${esc(item.missing ? `Dashboard ${item.id}` : reportDisplayName(item.report))}</div>
      <div class="report-builder-plot" id="reportBuilderPlot-${esc(block.id)}-${Number(item.missing ? item.id : item.report.id)}"></div>
    </div>
  `).join('');

  reports.forEach(item => {
    const plotEl = getReportBuilderEl(`reportBuilderPlot-${block.id}-${Number(item.missing ? item.id : item.report.id)}`);
    if (!plotEl) return;
    if (item.missing) {
      plotEl.innerHTML = '<div class="empty-state"><p>Dashboard salvo nao encontrado.</p></div>';
      return;
    }
    if (block.chartId === 'kpis') {
      renderBuilderKpis(plotEl, item.data);
      return;
    }
    if (['flow_metrics', 'scope_quality', 'time_health'].includes(block.chartId)) {
      renderBuilderMetricCards(plotEl, item.data, block.chartId);
      return;
    }
    if (block.chartId === 'roadmap') {
      renderBuilderRoadmap(plotEl, item.data, block.type);
      return;
    }

    const result = buildReportBuilderChart(block.chartId, block.type, item.data);
    if (!result?.traces) {
      plotEl.innerHTML = '<div class="empty-state"><p>Sem dados suficientes.</p></div>';
      return;
    }
    Plotly.react(plotEl.id, result.traces, compactBuilderLayout(result.layout || {}, {
      chartId: block.chartId,
      type: block.type,
    }), { responsive: true, displayModeBar: false });
    plotEl.dataset.plotlyRendered = 'true';
  });
}

function resizeReportBuilderPlots() {
  document.querySelectorAll('.report-builder-plot[data-plotly-rendered="true"]').forEach(el => {
    Plotly.Plots.resize(el);
  });
}

function reportBuilderHasTimelineBlock() {
  return reportBuilderPages.some(page =>
    page.blocks.some(block => block.chartId === 'roadmap' && block.type === 'timeline')
  );
}

function reportBuilderPrintOrientation() {
  return 'landscape';
}

function applyReportBuilderPrintPageStyle() {
  const orientation = reportBuilderPrintOrientation();
  const margin = reportBuilderHasTimelineBlock() ? '5mm' : '10mm';
  let styleEl = document.getElementById('reportBuilderPrintPageStyle');
  if (!styleEl) {
    styleEl = document.createElement('style');
    styleEl.id = 'reportBuilderPrintPageStyle';
    document.head.appendChild(styleEl);
  }
  styleEl.textContent = `@page{size:A4 ${orientation};margin:${margin}}`;
  document.body.classList.toggle('report-builder-print-landscape', orientation === 'landscape');
  document.body.classList.toggle('report-builder-print-portrait', orientation === 'portrait');
}

function prepareReportBuilderPrint() {
  document.body.classList.add('report-builder-printing');
  applyReportBuilderPrintPageStyle();
  resizeReportBuilderPlots();
  requestAnimationFrame(() => resizeReportBuilderPlots());
}

function finishReportBuilderPrint() {
  document.body.classList.remove('report-builder-printing');
  document.body.classList.remove('report-builder-print-landscape', 'report-builder-print-portrait');
  setTimeout(resizeReportBuilderPlots, 80);
}

function printReportBuilder() {
  prepareReportBuilderPrint();
  setTimeout(() => {
    resizeReportBuilderPlots();
    window.print();
  }, 600);
}

window.addEventListener('beforeprint', prepareReportBuilderPrint);
window.addEventListener('afterprint', finishReportBuilderPrint);
