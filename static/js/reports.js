/* ════════════════════════════════════════════════════════════
   REPORTS — Biblioteca de relatórios (render + API)
════════════════════════════════════════════════════════════ */
function upsertReport(report) {
  const idx = reportList.findIndex(item => item.id === report.id);
  if (idx >= 0) reportList[idx] = report;
  else reportList.unshift(report);
  reportList.sort((a, b) => String(b.updated_at || '').localeCompare(String(a.updated_at || '')));
}

function renderReports() {
  reportsListEl.innerHTML = '';
  reportsEmptyEl.classList.toggle('hidden', reportList.length > 0);
  librarySubtitleEl.textContent = reportList.length
    ? `${reportList.length} dashboard(s) salvo(s)`
    : 'Nenhum dashboard salvo ainda.';
  reportList.forEach(report => {
    const card = document.createElement('div');
    card.className = 'report-card';

    const title = document.createElement('div');
    title.className = 'report-title';
    title.textContent = report.title || report.source_filename || 'Dashboard';

    const meta = document.createElement('div');
    meta.className = 'report-meta';
    meta.innerHTML =
      `Projeto: ${esc(report.project_name || '—')}<br>` +
      `Sprint: ${esc(report.sprint_name || '—')}<br>` +
      `Atualizado: ${esc(fmtDateTime(report.updated_at))}`;

    const actions = document.createElement('div');
    actions.className = 'report-actions';

    const openBtn = document.createElement('button');
    openBtn.className = 'btn-small';
    openBtn.textContent = 'Abrir';
    openBtn.addEventListener('click', () => openReport(report.id));

    const deleteBtn = document.createElement('button');
    deleteBtn.className = 'btn-small';
    deleteBtn.textContent = 'Excluir';
    deleteBtn.addEventListener('click', () => deleteReport(report.id));

    const teamSelect = document.createElement('select');
    teamSelect.className = 'report-team-select';
    teamSelect.title = 'Associar dashboard a uma equipe';
    teamSelect.innerHTML = '<option value="">Sem equipe</option>' + (typeof teams !== 'undefined' ? teams.filter(team => team.active).map(team =>
      `<option value="${esc(team.id)}">${esc(team.name)}</option>`
    ).join('') : '');
    teamSelect.value = report.team_id ? String(report.team_id) : '';
    teamSelect.addEventListener('change', () => assignReportTeam(report.id, teamSelect.value));

    actions.append(openBtn, deleteBtn);
    card.append(title, meta, teamSelect, actions);
    reportsListEl.appendChild(card);
  });
}


/* ── API calls ──────────────────────────────────────────── */
async function loadReports() {
  if (!authState.authenticated) return;
  reportsErrorEl.classList.remove('visible');
  try {
    const body = await apiRequest('/api/reports');
    reportList = body.reports || [];
    renderReports();
    if (typeof buildSidebar === 'function') buildSidebar();
  } catch (err) {
    reportsErrorEl.textContent = 'Aviso: ' + err.message;
    reportsErrorEl.classList.add('visible');
  }
}

async function openReport(reportId) {
  document.getElementById('loadingOverlay').classList.add('visible');
  try {
    const body = await apiRequest(`/api/reports/${reportId}`);
    currentReportId = reportId;
    loadDashboard(body.data);
  } catch (err) {
    showUploadError(err.message);
  } finally {
    document.getElementById('loadingOverlay').classList.remove('visible');
  }
}

async function deleteReport(reportId) {
  if (!confirm('Excluir este dashboard salvo?')) return;
  try {
    await apiRequest(`/api/reports/${reportId}`, { method: 'DELETE', csrf: true });
    reportList = reportList.filter(item => item.id !== reportId);
    if (currentReportId === reportId) currentReportId = null;
    renderReports();
    resetToUpload();
  } catch (err) {
    reportsErrorEl.textContent = 'Aviso: ' + err.message;
    reportsErrorEl.classList.add('visible');
  }
}
