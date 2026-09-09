/* ════════════════════════════════════════════════════════════
   UPLOAD — Drag & drop, seleção de arquivo e envio
════════════════════════════════════════════════════════════ */
dropZone.addEventListener('dragover',  e => { e.preventDefault(); dropZone.classList.add('drag'); });
dropZone.addEventListener('dragleave', ()  => dropZone.classList.remove('drag'));
dropZone.addEventListener('drop',      e  => {
  e.preventDefault(); dropZone.classList.remove('drag');
  if (e.dataTransfer.files.length) handleFile(e.dataTransfer.files[0]);
});
fileInput.addEventListener('change', () => { if (fileInput.files.length) handleFile(fileInput.files[0]); });

function handleFile(file) {
  if (!authState.authenticated) {
    showAuthScreen(authState.bootstrapRequired);
    return;
  }
  if (!file.name.endsWith('.xlsx')) {
    showUploadError('Envie um arquivo .xlsx exportado do Microsoft Planner.');
    return;
  }
  const selectedRoadmapId = savedRoadmapSelect?.value || '';
  const roadmapRaw = roadmapPasteInput?.value || '';
  const roadmapRows = selectedRoadmapId ? [] : parseRoadmapPasteRows(roadmapRaw);
  if (!selectedRoadmapId && roadmapRaw.trim() && !roadmapRows.length) {
    showUploadError('Roadmap manual preenchido, mas nenhuma linha valida foi encontrada. Cole as colunas Data, Goal e Marco.');
    return;
  }
  const roadmapItems = buildRoadmapItemsFromRows(roadmapRows);
  updateRoadmapPasteStatus(roadmapRows);
  uploadError.classList.remove('visible');
  uploadProgress.classList.add('visible');
  progBar.style.width = '0%';
  progText.textContent = 'Enviando arquivo...';
  document.getElementById('loadingOverlay').classList.add('visible');

  const fd = new FormData();
  fd.append('arquivo', file);
  const plannerFormat = document.querySelector('input[name="plannerFormat"]:checked')?.value || 'legacy';
  fd.append('planner_format', plannerFormat);
  if (uploadTeamSelect?.value) fd.append('team_id', uploadTeamSelect.value);
  const ignoredLabels = new Set();
  if (ignoreFluxoContinuoInput?.checked) {
    ignoredLabels.add('.FLUXO.CONTINUO');
    ignoredLabels.add('FLUXO.CONTINUO');
    ignoredLabels.add('.FLUXO CONTINUO');
    ignoredLabels.add('FLUXO CONTINUO');
  }
  if (ignoredLabels.size) {
    fd.append('rotulos_ignorar', Array.from(ignoredLabels).join(';'));
  }
  if (selectedRoadmapId) {
    fd.append('roadmap_id', selectedRoadmapId);
  } else if (roadmapItems.length) {
    fd.append('roadmap_json', JSON.stringify(roadmapItems));
    if (roadmapSaveTitleInput?.value?.trim()) fd.append('roadmap_title', roadmapSaveTitleInput.value.trim());
    const inferredDate = roadmapSaveDateInput?.value || roadmapDateToIso(roadmapRows[0]?.date);
    if (inferredDate) fd.append('roadmap_project_date', inferredDate);
  }
  const xhr = new XMLHttpRequest();
  xhr.open('POST', '/upload');
  if (authState.csrfToken) xhr.setRequestHeader('X-CSRF-Token', authState.csrfToken);

  xhr.upload.onprogress = e => {
    if (e.lengthComputable)
      progBar.style.width = Math.round(e.loaded / e.total * 60) + '%';
  };

  xhr.onreadystatechange = () => {
    if (xhr.readyState !== 4) return;
    progBar.style.width = '100%';
    try {
      const body = JSON.parse(xhr.responseText);
      if (xhr.status === 401) {
        showAuthScreen(body.bootstrap_required === true);
        showUploadError(body.erro || 'Sua sessao expirou.');
        return;
      }
      if (!body.ok) { showUploadError(body.erro || 'Falha ao processar o arquivo.'); return; }
      currentReportId = body.report?.id || null;
      if (body.report) upsertReport(body.report);
      if (body.roadmap) {
        upsertSavedRoadmap(body.roadmap);
        renderSavedRoadmapOptions(String(body.roadmap.id));
        if (!selectedRoadmapId && roadmapItems.length) {
          if (roadmapPasteInput) roadmapPasteInput.value = '';
          if (roadmapSaveTitleInput) roadmapSaveTitleInput.value = '';
          if (roadmapSaveDateInput) roadmapSaveDateInput.value = '';
          localStorage.removeItem(ROADMAP_PASTE_STORAGE_KEY);
          toggleRoadmapManualForm(false);
          updateRoadmapPasteStatus();
        }
      }
      renderReports();
      progText.textContent = 'Pronto! Carregando dashboard...';
      setTimeout(() => loadDashboard(body.data), 200);
    } catch (_) { showUploadError('Erro inesperado. Tente novamente.'); }
  };
  xhr.onerror = () => showUploadError('Erro de conexao. O servidor esta rodando?');
  xhr.send(fd);
}

function showUploadError(msg) {
  uploadProgress.classList.remove('visible');
  document.getElementById('loadingOverlay').classList.remove('visible');
  uploadError.textContent = 'Aviso: ' + msg;
  uploadError.classList.add('visible');
}

function resetToUpload(teamId = '') {
  dashData = null;
  currentReportId = null;
  showHomeScreen();
  if (uploadTeamSelect) uploadTeamSelect.value = teamId ? String(teamId) : '';
  uploadProgress.classList.remove('visible');
  uploadError.classList.remove('visible');
  reportsErrorEl.classList.remove('visible');
  fileInput.value = '';
  progBar.style.width = '0%';
  progText.textContent = 'Enviando arquivo...';
}

const ROADMAP_PASTE_STORAGE_KEY = 'rcw-roadmap-paste';
const ROADMAP_POSITION_SEQ = [10, -10, 40, 25, 10, -40, -25, -10, 40, 25, 10, -40, -10, 40, 25, 10, -40, -25, -10, 40];

function roadmapDateToIso(dateText) {
  const match = String(dateText || '').match(/^(\d{2})\/(\d{2})\/(\d{4})$/);
  return match ? `${match[3]}-${match[2]}-${match[1]}` : '';
}

function formatSavedRoadmapDate(value, fallback = 'Sem data') {
  if (!value) return fallback;
  const match = String(value).match(/^(\d{4})-(\d{2})-(\d{2})$/);
  return match ? `${match[3]}/${match[2]}/${match[1]}` : String(value);
}

function findSavedRoadmap(id) {
  const numericId = Number(id || 0);
  return savedRoadmaps.find(item => Number(item.id) === numericId) || null;
}

function upsertSavedRoadmap(roadmap) {
  if (!roadmap?.id) return;
  const index = savedRoadmaps.findIndex(item => Number(item.id) === Number(roadmap.id));
  if (index >= 0) savedRoadmaps[index] = roadmap;
  else savedRoadmaps.unshift(roadmap);
  savedRoadmaps.sort((a, b) => {
    const dateCmp = String(b.project_date || '').localeCompare(String(a.project_date || ''));
    return dateCmp || String(b.updated_at || '').localeCompare(String(a.updated_at || ''));
  });
}

function savedRoadmapItemToRow(item) {
  const text = Array.isArray(item) ? String(item[0] || '') : String(item?.marco || '');
  const lines = text.split(/\n+/).map(line => line.trim()).filter(Boolean);
  const first = lines[0] || '';
  const dateMatch = first.match(/^(\d{2}\/\d{2}\/\d{4})(.*)$/);
  const date = dateMatch?.[1] || first;
  const contentLines = [];
  const trailing = dateMatch?.[2]?.trim();
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
  return { date, goal, marco };
}

function renderRoadmapRowsPreview(rows) {
  if (!roadmapPastePreview) return;
  if (!rows?.length) {
    roadmapPastePreview.innerHTML = '';
    return;
  }
  roadmapPastePreview.innerHTML = rows.slice(0, 6).map(row => `
    <div class="roadmap-preview-row">
      <div class="roadmap-preview-date">${esc(row.date || '-')}</div>
      <div><strong>Goal</strong><span>${esc(row.goal || '-')}</span></div>
      <div><strong>Marco</strong><span>${esc(row.marco || '-')}</span></div>
    </div>
  `).join('') + (rows.length > 6 ? `<div class="roadmap-preview-more">+${rows.length - 6} marco(s)</div>` : '');
}

function updateSavedRoadmapMeta() {
  if (!savedRoadmapMeta) return;
  const selected = findSavedRoadmap(savedRoadmapSelect?.value);
  if (!selected) {
    savedRoadmapMeta.textContent = savedRoadmaps.length
      ? 'Nenhum roadmap salvo selecionado.'
      : 'Nenhum roadmap salvo ainda. Cole um roadmap para salvar no primeiro upload.';
    return;
  }
  const date = selected.project_date_label || formatSavedRoadmapDate(selected.project_date);
  savedRoadmapMeta.textContent = `${date} - ${selected.item_count || 0} marco${selected.item_count === 1 ? '' : 's'} - ${selected.title || 'Roadmap'}`;
}

function renderSavedRoadmapOptions(selectedId = savedRoadmapSelect?.value || '') {
  if (!savedRoadmapSelect) return;
  const currentId = String(selectedId || '');
  savedRoadmapSelect.innerHTML = '<option value="">Usar roadmap do Planner</option>' + savedRoadmaps.map(item => {
    const date = item.project_date_label || formatSavedRoadmapDate(item.project_date);
    const count = Number(item.item_count || 0);
    const label = `${date} - ${item.title || 'Roadmap'} (${count} marco${count === 1 ? '' : 's'})`;
    return `<option value="${esc(item.id)}"${String(item.id) === currentId ? ' selected' : ''}>${esc(label)}</option>`;
  }).join('');
  updateSavedRoadmapMeta();
  updateRoadmapPasteStatus();
}
function toggleRoadmapManualForm(force = null) {
  if (!roadmapAddPanel) return;
  const shouldOpen = force === null ? roadmapAddPanel.classList.contains('hidden') : !!force;
  roadmapAddPanel.classList.toggle('hidden', !shouldOpen);
  if (shouldOpen) {
    if (savedRoadmapSelect) savedRoadmapSelect.value = '';
    updateSavedRoadmapMeta();
    updateRoadmapPasteStatus();
    roadmapPasteInput?.focus();
  }
}

async function loadSavedRoadmaps() {
  if (!authState.authenticated) return;
  try {
    const body = await apiRequest('/api/roadmaps');
    savedRoadmaps = body.roadmaps || [];
    renderSavedRoadmapOptions();
  } catch (err) {
    if (savedRoadmapMeta) savedRoadmapMeta.textContent = 'Aviso: ' + err.message;
  }
}

function roadmapWeirdScore(text) {
  return Array.from(String(text || '')).reduce((count, ch) => {
    const code = ch.charCodeAt(0);
    return count + ([0xc2, 0xc3, 0xe2, 0xfffd].includes(code) ? 1 : 0);
  }, 0);
}

function repairRoadmapMojibake(text) {
  const value = String(text || '');
  if (!roadmapWeirdScore(value)) return value;
  try {
    const bytes = Uint8Array.from(Array.from(value).map(ch => ch.charCodeAt(0) & 255));
    const decoded = new TextDecoder('utf-8', { fatal:false }).decode(bytes);
    return roadmapWeirdScore(decoded) < roadmapWeirdScore(value) ? decoded : value;
  } catch (_) {
    return value;
  }
}

function splitRoadmapCells(line) {
  if (line.includes('\t')) return line.split('\t');
  if (line.includes(';')) return line.split(';');
  return line.split(/\s{2,}/);
}

function parseRoadmapPasteRows(raw) {
  const text = repairRoadmapMojibake(raw)
    .replace(/\uFEFF/g, '')
    .replace(/\r\n/g, '\n')
    .replace(/\r/g, '\n')
    .trim();
  if (!text) return [];

  const rows = [];
  text.split('\n').map(line => line.trim()).filter(Boolean).forEach(line => {
    if (/^data\s+goal\s+marco$/i.test(line.replace(/\t+/g, ' '))) return;

    if (/^\d{2}\/\d{2}\/\d{4}\b/.test(line)) {
      const cells = splitRoadmapCells(line).map(cell => cell.trim());
      const date = cells[0] || '';
      const goal = cells[1] || '';
      const milestone = cells.slice(2).join(' ').trim();
      rows.push({ date, goal, marco: milestone });
      return;
    }

    if (rows.length) {
      const last = rows[rows.length - 1];
      last.marco = [last.marco, line.replace(/\t+/g, ' ')].filter(Boolean).join(' ');
    }
  });

  return rows.filter(row => row.date && (row.goal || row.marco));
}

function buildRoadmapItemsFromRows(rows) {
  return (rows || []).map((row, index) => {
    const parts = [row.date];
    if (row.goal) parts.push(`Goal: ${row.goal}`);
    if (row.marco) parts.push(`Marco: ${row.marco}`);
    return {
      marco: parts.join('\n'),
      posicao: ROADMAP_POSITION_SEQ[index % ROADMAP_POSITION_SEQ.length],
    };
  });
}

function updateRoadmapPasteStatus(rows = null) {
  if (!roadmapPasteStatus) return;
  const selected = findSavedRoadmap(savedRoadmapSelect?.value);
  if (selected) {
    roadmapPasteStatus.textContent = `Roadmap salvo selecionado: ${selected.title || 'Roadmap'}. Ele sera associado ao dashboard enviado.`;
    roadmapPasteStatus.classList.remove('error');
    return;
  }
  const parsedRows = rows || parseRoadmapPasteRows(roadmapPasteInput?.value || '');
  const hasText = !!(roadmapPasteInput?.value || '').trim();
  if (!hasText) {
    roadmapPasteStatus.textContent = 'Opcional. Se preenchido, este roadmap sera salvo junto com o dashboard para reuso.';
    roadmapPasteStatus.classList.remove('error');
    return;
  }
  if (!parsedRows.length) {
    roadmapPasteStatus.textContent = 'Nenhuma linha valida encontrada. Esperado: Data, Goal e Marco.';
    roadmapPasteStatus.classList.add('error');
    return;
  }
  roadmapPasteStatus.textContent = `${parsedRows.length} marco${parsedRows.length === 1 ? '' : 's'} pronto${parsedRows.length === 1 ? '' : 's'} para salvar no dashboard.`;
  roadmapPasteStatus.classList.remove('error');
}

function previewRoadmapPaste() {
  if (!roadmapPastePreview) return;
  const selected = findSavedRoadmap(savedRoadmapSelect?.value);
  if (selected) {
    const rows = (selected.items || []).map(savedRoadmapItemToRow).filter(row => row.date || row.goal || row.marco);
    renderRoadmapRowsPreview(rows);
    updateRoadmapPasteStatus(rows);
    return;
  }
  const rows = parseRoadmapPasteRows(roadmapPasteInput?.value || '');
  updateRoadmapPasteStatus(rows);
  renderRoadmapRowsPreview(rows);
}

function clearRoadmapPaste() {
  if (!roadmapPasteInput) return;
  roadmapPasteInput.value = '';
  if (savedRoadmapSelect) savedRoadmapSelect.value = '';
  if (roadmapSaveTitleInput) roadmapSaveTitleInput.value = '';
  if (roadmapSaveDateInput) roadmapSaveDateInput.value = '';
  localStorage.removeItem(ROADMAP_PASTE_STORAGE_KEY);
  updateSavedRoadmapMeta();
  updateRoadmapPasteStatus([]);
  if (roadmapPastePreview) roadmapPastePreview.innerHTML = '';
}

if (savedRoadmapSelect) {
  savedRoadmapSelect.addEventListener('change', () => {
    if (savedRoadmapSelect.value) toggleRoadmapManualForm(false);
    updateSavedRoadmapMeta();
    updateRoadmapPasteStatus();
    previewRoadmapPaste();
  });
}

if (roadmapPasteInput) {
  roadmapPasteInput.value = localStorage.getItem(ROADMAP_PASTE_STORAGE_KEY) || '';
  if (roadmapPasteInput.value.trim()) toggleRoadmapManualForm(true);
  roadmapPasteInput.addEventListener('input', () => {
    if (savedRoadmapSelect?.value) {
      savedRoadmapSelect.value = '';
      updateSavedRoadmapMeta();
    }
    localStorage.setItem(ROADMAP_PASTE_STORAGE_KEY, roadmapPasteInput.value);
    updateRoadmapPasteStatus();
  });
  updateRoadmapPasteStatus();
}

