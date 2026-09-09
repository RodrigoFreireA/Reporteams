/* ════════════════════════════════════════════════════════════
   ADMIN — Usuários, custom charts, profile rules
════════════════════════════════════════════════════════════ */
function resetAdminForm() {
  adminEditingUserId = null;
  adminUserForm.reset();
  adminRoleInput.value = 'user';
  adminPasswordInput.required = true;
  adminFormTitle.textContent = 'Novo usuario';
  adminFormSub.textContent = 'Crie acessos individuais para sua equipe e defina quem tambem pode administrar usuarios.';
  adminPasswordHint.textContent = 'A senha inicial deve ter ao menos 12 caracteres, com letras e numeros, sem padroes obvios.';
  adminSubmitBtn.textContent = 'Criar usuario';
  adminCancelBtn.classList.add('hidden');
  adminFormError.classList.remove('visible');
}

function timestampMs(value) {
  const parsed = Date.parse(value || '');
  return Number.isFinite(parsed) ? parsed : null;
}

function userSessionRevokedSinceLastLogin(user) {
  const revokedAt = timestampMs(user.session_revoked_at);
  if (revokedAt === null) return false;
  const lastLoginAt = timestampMs(user.last_login_at);
  return lastLoginAt === null || revokedAt >= lastLoginAt;
}

function renderAdminUsers() {
  adminUsersList.innerHTML = '';
  adminUsersEmpty.classList.toggle('hidden', adminUsers.length > 0);
  adminUsersSubtitle.textContent = adminUsers.length
    ? `${adminUsers.length} usuario(s) cadastrados`
    : 'Nenhum usuario adicional cadastrado ainda.';

  if (!adminUsers.length) return;

  const table = document.createElement('table');
  table.className = 'admin-users-table admin-users-table--users';
  table.innerHTML = `
    <thead>
      <tr>
        <th>Nome</th>
        <th>E-mail</th>
        <th>Perfil</th>
        <th>Dashboards</th>
        <th>Ultimo login</th>
        <th>Criado em</th>
        <th>Acoes</th>
      </tr>
    </thead>
    <tbody></tbody>
  `;

  const tbody = table.querySelector('tbody');

  adminUsers.forEach(user => {
    const row = document.createElement('tr');

    const nameCell = document.createElement('td');
    nameCell.innerHTML = `<div class="admin-user-name">${esc(user.display_name || 'Usuario')}</div>`;

    const emailCell = document.createElement('td');
    emailCell.innerHTML = `<div class="admin-user-email">${esc(user.email || '—')}</div>`;

    const roleCell = document.createElement('td');
    const badges = document.createElement('div');
    badges.className = 'admin-user-badges';

    const roleBadge = document.createElement('span');
    roleBadge.className = `admin-badge ${user.role === 'admin' ? 'admin' : user.role === 'disabled' ? 'disabled' : ''}`.trim();
    roleBadge.textContent = user.role === 'admin' ? 'ADMIN' : user.role === 'disabled' ? 'DESATIVADO' : 'USUARIO';
    badges.appendChild(roleBadge);

    if (user.id === authState.user?.id) {
      const selfBadge = document.createElement('span');
      selfBadge.className = 'admin-badge';
      selfBadge.textContent = 'VOCE';
      badges.appendChild(selfBadge);
    }
    roleCell.appendChild(badges);

    const reportsCell = document.createElement('td');
    reportsCell.className = 'admin-user-meta-cell';
    reportsCell.textContent = String(user.report_count ?? 0);

    const lastLoginCell = document.createElement('td');
    lastLoginCell.className = 'admin-user-meta-cell';
    lastLoginCell.textContent = user.last_login_at ? fmtDateTime(user.last_login_at) : 'Nunca';

    const createdCell = document.createElement('td');
    createdCell.className = 'admin-user-meta-cell';
    createdCell.textContent = fmtDateTime(user.created_at);

    const actionsCell = document.createElement('td');
    const actions = document.createElement('div');
    actions.className = 'admin-user-actions';

    const editBtn = document.createElement('button');
    editBtn.className = 'btn-small';
    editBtn.textContent = 'Editar';
    editBtn.addEventListener('click', () => startAdminEdit(user.id));

    const toggleBtn = document.createElement('button');
    toggleBtn.className = 'btn-small';
    toggleBtn.textContent = user.role === 'disabled' ? 'Ativar' : 'Desativar';
    toggleBtn.disabled = user.id === authState.user?.id;
    toggleBtn.addEventListener('click', () => toggleAdminUserStatus(user.id));

    const sessionBtn = document.createElement('button');
    sessionBtn.className = 'btn-small';
    const hasLogin = timestampMs(user.last_login_at) !== null;
    const sessionRevoked = userSessionRevokedSinceLastLogin(user);
    sessionBtn.textContent = !hasLogin ? 'Sem sessao' : sessionRevoked ? 'Encerrada' : 'Sessao';
    sessionBtn.title = user.id === authState.user?.id
      ? 'Use Sair para encerrar sua propria sessao'
      : !hasLogin
        ? 'Este usuario ainda nao fez login'
        : sessionRevoked
          ? 'Sessao encerrada; o botao sera reativado apos novo login'
          : 'Encerrar sessao deste usuario';
    sessionBtn.disabled = user.id === authState.user?.id || !hasLogin || sessionRevoked;
    sessionBtn.addEventListener('click', () => revokeAdminUserSession(user.id));

    const deleteBtn = document.createElement('button');
    deleteBtn.className = 'btn-small';
    deleteBtn.textContent = 'Excluir';
    deleteBtn.disabled = user.id === authState.user?.id;
    deleteBtn.addEventListener('click', () => deleteAdminUser(user.id));

    actions.append(editBtn, toggleBtn, sessionBtn, deleteBtn);
    actionsCell.appendChild(actions);

    row.append(nameCell, emailCell, roleCell, reportsCell, lastLoginCell, createdCell, actionsCell);
    tbody.appendChild(row);
  });

  adminUsersList.appendChild(table);
}

function openAdminUsers() {
  if (!isAdminUser()) return;
  authScreen.classList.add('hidden');
  sidebar.classList.add('hidden');
  uploadScreen.classList.add('hidden');
  teamScreen.classList.add('hidden');
  dashboardEl.classList.remove('visible');
  adminScreen.classList.remove('hidden');
  customChartScreen.classList.add('hidden');
  comparativeScreen.classList.add('hidden');
  consolidatedScreen.classList.add('hidden');
  btnUploadNew.classList.add('visible');
  sprintBadgeEl.classList.remove('visible');
  menuToggle.classList.add('hidden');
  syncTopbarState();
  closeSidebar();
  if (!adminEditingUserId) resetAdminForm();
  if (!adminUsers.length) loadAdminUsers();
}

async function loadAdminUsers() {
  if (!isAdminUser()) return;
  adminUsersError.classList.remove('visible');
  try {
    const body = await apiRequest('/api/admin/users');
    adminUsers = body.users || [];
    renderAdminUsers();
  } catch (err) {
    adminUsersError.textContent = 'Aviso: ' + err.message;
    adminUsersError.classList.add('visible');
  }
}

function startAdminEdit(userId) {
  const user = adminUsers.find(item => item.id === userId);
  if (!user) return;
  adminEditingUserId = user.id;
  adminDisplayNameInput.value = user.display_name || '';
  adminEmailInput.value = user.email || '';
  adminPasswordInput.value = '';
  adminRoleInput.value = user.role || 'user';
  adminPasswordInput.required = false;
  adminFormTitle.textContent = 'Editar usuario';
  adminFormSub.textContent = 'Atualize dados do acesso e, se precisar, altere o perfil ou redefina a senha.';
  adminPasswordHint.textContent = 'Deixe a senha em branco para manter a senha atual.';
  adminSubmitBtn.textContent = 'Salvar alteracoes';
  adminCancelBtn.classList.remove('hidden');
  adminFormError.classList.remove('visible');
  if (adminScreen.classList.contains('hidden')) openAdminUsers();
}

function focusNewAdminUserForm() {
  resetAdminForm();
  adminDisplayNameInput.focus();
  adminUserForm.scrollIntoView({ behavior: 'smooth', block: 'start' });
}

async function toggleAdminUserStatus(userId) {
  const user = adminUsers.find(item => item.id === userId);
  if (!user) return;
  const nextRole = user.role === 'disabled' ? 'user' : 'disabled';
  const message = nextRole === 'disabled'
    ? `Desativar o acesso de ${user.display_name || user.email}?`
    : `Reativar o acesso de ${user.display_name || user.email} como usuario comum?`;
  if (!confirm(message)) return;
  try {
    const body = await apiRequest(`/api/admin/users/${userId}`, {
      method: 'PATCH',
      json: {
        display_name: user.display_name,
        email: user.email,
        role: nextRole,
      },
      csrf: true,
    });
    if (body.current_user) authState.user = body.current_user;
    await loadAdminUsers();
    syncTopbarState();
  } catch (err) {
    adminUsersError.textContent = 'Aviso: ' + err.message;
    adminUsersError.classList.add('visible');
  }
}

async function revokeAdminUserSession(userId) {
  const user = adminUsers.find(item => item.id === userId);
  if (!user) return;
  if (!confirm(`Encerrar a sessao ativa de ${user.display_name || user.email}?`)) return;
  try {
    await apiRequest(`/api/admin/users/${userId}/sessions/revoke`, {
      method: 'POST',
      json: {},
      csrf: true,
    });
    await loadAdminUsers();
  } catch (err) {
    adminUsersError.textContent = 'Aviso: ' + err.message;
    adminUsersError.classList.add('visible');
  }
}

async function deleteAdminUser(userId) {
  const user = adminUsers.find(item => item.id === userId);
  if (!user) return;
  if (!confirm(`Excluir ${user.display_name || user.email} e todos os dashboards desse usuario?`)) return;
  try {
    await apiRequest(`/api/admin/users/${userId}`, {
      method: 'DELETE',
      csrf: true,
    });
    if (adminEditingUserId === userId) resetAdminForm();
    await loadAdminUsers();
  } catch (err) {
    adminUsersError.textContent = 'Aviso: ' + err.message;
    adminUsersError.classList.add('visible');
  }
}

function getSelectedCustomChartTypes() {
  return Array.from(customChartTypeOptions.querySelectorAll('input[type="checkbox"]:checked'))
    .map(input => input.value);
}

function syncCustomChartDefaultType(selectedDefaultType) {
  const checkedTypes = getSelectedCustomChartTypes();
  if (!checkedTypes.length) {
    customChartDefaultTypeInput.innerHTML = '';
    return '';
  }
  const safeDefault = checkedTypes.includes(selectedDefaultType) ? selectedDefaultType : checkedTypes[0];
  customChartDefaultTypeInput.innerHTML = checkedTypes
    .map(key => `<option value="${esc(key)}"${key === safeDefault ? ' selected' : ''}>${esc(CHART_TYPES[key]?.label || key)}</option>`)
    .join('');
  return safeDefault;
}

function renderCustomChartTypeOptions(source, selectedTypes, selectedDefaultType) {
  const selectedSet = new Set((Array.isArray(selectedTypes) ? selectedTypes : [selectedTypes]).filter(Boolean));
  const effectiveTypes = source.types.filter(type => selectedSet.has(type));
  const checkedTypes = effectiveTypes.length ? effectiveTypes : [source.types[0]];

  customChartTypeOptions.innerHTML = '';
  source.types.forEach(type => {
    const label = document.createElement('label');
    label.className = 'admin-check-option';

    const input = document.createElement('input');
    input.type = 'checkbox';
    input.value = type;
    input.checked = checkedTypes.includes(type);
    input.addEventListener('change', () => {
      const checkedNow = getSelectedCustomChartTypes();
      if (!checkedNow.length) {
        input.checked = true;
      }
      syncCustomChartDefaultType(customChartDefaultTypeInput.value || selectedDefaultType);
    });

    const text = document.createElement('span');
    text.textContent = CHART_TYPES[type]?.label || type;
    label.append(input, text);
    customChartTypeOptions.appendChild(label);
  });

  syncCustomChartDefaultType(selectedDefaultType);
}

function syncCustomChartSourceOptions(selectedSource, selectedMetric, selectedTypes, selectedDefaultType) {
  const sourceKey = selectedSource && CUSTOM_CHART_SOURCES[selectedSource]
    ? selectedSource
    : Object.keys(CUSTOM_CHART_SOURCES)[0];
  const source = CUSTOM_CHART_SOURCES[sourceKey];

  customChartSourceInput.innerHTML = Object.entries(CUSTOM_CHART_SOURCES)
    .map(([key, value]) => `<option value="${esc(key)}"${key === sourceKey ? ' selected' : ''}>${esc(value.label)}</option>`)
    .join('');

  const metricKeys = Object.keys(source.metrics);
  const safeMetric = metricKeys.includes(selectedMetric) ? selectedMetric : metricKeys[0];
  customChartMetricInput.innerHTML = metricKeys
    .map(key => `<option value="${esc(key)}"${key === safeMetric ? ' selected' : ''}>${esc(source.metrics[key])}</option>`)
    .join('');

  renderCustomChartTypeOptions(source, selectedTypes, selectedDefaultType);
}

function resetCustomChartForm() {
  customChartEditingId = null;
  customChartForm.reset();
  customChartGroupInput.value = 'Distribuição';
  customChartSortInput.value = 'metric_desc';
  customChartEnabledInput.value = '1';
  customChartOrderInput.value = '0';
  customChartLimitInput.value = '';
  syncCustomChartSourceOptions('categoria', null, ['bar_v'], 'bar_v');
  customChartFormTitle.textContent = 'Novo grafico customizado';
  customChartFormSub.textContent = 'Monte uma visualizacao a partir dos datasets ja calculados pelo dashboard, sem mexer nos graficos nativos.';
  customChartFormHint.textContent = 'V1 segura: apenas datasets e metricas homologadas. Sem regra livre, SQL ou codigo.';
  customChartSubmitBtn.textContent = 'Criar grafico';
  customChartCancelBtn.classList.add('hidden');
  customChartFormError.classList.remove('visible');
}

function renderCustomCharts() {
  customChartsList.innerHTML = '';
  customChartsEmpty.classList.toggle('hidden', adminCustomCharts.length > 0);
  customChartsSubtitle.textContent = adminCustomCharts.length
    ? `${adminCustomCharts.length} grafico(s) cadastrado(s)`
    : 'Nenhum grafico customizado cadastrado ainda.';

  if (!adminCustomCharts.length) return;

  const table = document.createElement('table');
  table.className = 'admin-users-table';
  table.innerHTML = `
    <thead>
      <tr>
        <th>Nome</th>
        <th>Categoria</th>
        <th>Fonte</th>
        <th>Metrica</th>
        <th>Tipos</th>
        <th>Status</th>
        <th>Acoes</th>
      </tr>
    </thead>
    <tbody></tbody>
  `;

  const tbody = table.querySelector('tbody');
  adminCustomCharts.forEach(chart => {
    const row = document.createElement('tr');

    const nameCell = document.createElement('td');
    nameCell.innerHTML = `
      <div class="admin-user-name">${esc(chart.name || 'Grafico')}</div>
      <div class="admin-user-email">${esc(chart.subtitle || 'Sem subtitulo')}</div>
    `;

    const groupCell = document.createElement('td');
    groupCell.className = 'admin-user-meta-cell';
    groupCell.textContent = chart.group || 'Distribuição';

    const sourceCell = document.createElement('td');
    sourceCell.className = 'admin-user-meta-cell';
    sourceCell.textContent = CUSTOM_CHART_SOURCES[chart.source_key]?.label || chart.source_key || '—';

    const metricCell = document.createElement('td');
    metricCell.className = 'admin-user-meta-cell';
    metricCell.textContent = CUSTOM_CHART_SOURCES[chart.source_key]?.metrics?.[chart.metric_key] || chart.metric_key || '—';

    const typeCell = document.createElement('td');
    typeCell.className = 'admin-user-meta-cell';
    const availableTypes = Array.isArray(chart.available_types) && chart.available_types.length
      ? chart.available_types
      : [chart.chart_type].filter(Boolean);
    const availableTypeLabels = availableTypes.map(key => CHART_TYPES[key]?.label || key);
    const defaultTypeLabel = CHART_TYPES[chart.chart_type]?.label || chart.chart_type || '—';
    typeCell.innerHTML = `
      <div>${esc(availableTypeLabels.join(', ') || '—')}</div>
      <div class="admin-user-email">Inicial: ${esc(defaultTypeLabel)}</div>
    `;

    const statusCell = document.createElement('td');
    const badges = document.createElement('div');
    badges.className = 'admin-user-badges';
    const statusBadge = document.createElement('span');
    statusBadge.className = `admin-badge ${chart.enabled ? 'admin' : 'disabled'}`.trim();
    statusBadge.textContent = chart.enabled ? 'ATIVO' : 'INATIVO';
    badges.appendChild(statusBadge);
    statusCell.appendChild(badges);

    const actionsCell = document.createElement('td');
    const actions = document.createElement('div');
    actions.className = 'admin-user-actions';

    const editBtn = document.createElement('button');
    editBtn.className = 'btn-small';
    editBtn.textContent = 'Editar';
    editBtn.addEventListener('click', () => startCustomChartEdit(chart.id));

    const toggleBtn = document.createElement('button');
    toggleBtn.className = 'btn-small';
    toggleBtn.textContent = chart.enabled ? 'Desativar' : 'Ativar';
    toggleBtn.addEventListener('click', () => toggleCustomChartEnabled(chart.id));

    const deleteBtn = document.createElement('button');
    deleteBtn.className = 'btn-small';
    deleteBtn.textContent = 'Excluir';
    deleteBtn.addEventListener('click', () => deleteCustomChart(chart.id));

    actions.append(editBtn, toggleBtn, deleteBtn);
    actionsCell.appendChild(actions);

    row.append(nameCell, groupCell, sourceCell, metricCell, typeCell, statusCell, actionsCell);
    tbody.appendChild(row);
  });

  customChartsList.appendChild(table);
}

function openCustomChartsAdmin() {
  if (!isAdminUser()) return;
  authScreen.classList.add('hidden');
  sidebar.classList.add('hidden');
  uploadScreen.classList.add('hidden');
  teamScreen.classList.add('hidden');
  adminScreen.classList.add('hidden');
  dashboardEl.classList.remove('visible');
  customChartScreen.classList.remove('hidden');
  comparativeScreen.classList.add('hidden');
  consolidatedScreen.classList.add('hidden');
  btnUploadNew.classList.add('visible');
  sprintBadgeEl.classList.remove('visible');
  menuToggle.classList.add('hidden');
  syncTopbarState();
  closeSidebar();
  if (!customChartEditingId) resetCustomChartForm();
  if (!profileRuleEditingId) resetProfileRuleForm();
  if (!adminCustomCharts.length) loadAdminCustomCharts();
  if (!adminProfileRules.length) loadAdminProfileRules();
}

async function loadCustomCharts() {
  if (!authState.authenticated) return;
  try {
    const body = await apiRequest('/api/charts/custom');
    customCharts = body.charts || [];
    if (dashData) {
      buildSidebar();
      const available = getCatalog().filter(item => hasData(item.id)).map(item => item.id);
      if (available.length && !available.includes(activeChartId)) {
        activeChartId = available.includes('kpis') ? 'kpis' : available[0];
      }
      if (available.length && available.includes(activeChartId)) selectChart(activeChartId);
    }
  } catch (_) {
    customCharts = [];
  }
}

async function loadAdminCustomCharts() {
  if (!isAdminUser()) return;
  customChartsError.classList.remove('visible');
  try {
    const body = await apiRequest('/api/admin/custom-charts');
    adminCustomCharts = body.charts || [];
    renderCustomCharts();
  } catch (err) {
    customChartsError.textContent = 'Aviso: ' + err.message;
    customChartsError.classList.add('visible');
  }
}

function startCustomChartEdit(chartId) {
  const chart = adminCustomCharts.find(item => item.id === chartId);
  if (!chart) return;
  customChartEditingId = chart.id;
  customChartNameInput.value = chart.name || '';
  customChartGroupInput.value = chart.group || 'Distribuição';
  customChartSubtitleInput.value = chart.subtitle || '';
  customChartSortInput.value = chart.sort_mode || 'metric_desc';
  customChartLimitInput.value = chart.limit ?? '';
  customChartOrderInput.value = chart.sort_order ?? 0;
  customChartEnabledInput.value = chart.enabled ? '1' : '0';
  syncCustomChartSourceOptions(
    chart.source_key,
    chart.metric_key,
    chart.available_types || [chart.chart_type],
    chart.chart_type
  );
  customChartFormTitle.textContent = 'Editar grafico customizado';
  customChartFormSub.textContent = 'Ajuste a regra homologada e a posicao desse grafico no menu lateral.';
  customChartFormHint.textContent = 'A alteracao e aplicada sem tocar nos graficos nativos existentes.';
  customChartSubmitBtn.textContent = 'Salvar alteracoes';
  customChartCancelBtn.classList.remove('hidden');
  customChartFormError.classList.remove('visible');
  if (customChartScreen.classList.contains('hidden')) openCustomChartsAdmin();
}

async function toggleCustomChartEnabled(chartId) {
  const chart = adminCustomCharts.find(item => item.id === chartId);
  if (!chart) return;
  const nextEnabled = !chart.enabled;
  if (!confirm(`${nextEnabled ? 'Ativar' : 'Desativar'} o grafico "${chart.name}"?`)) return;
  try {
    await apiRequest(`/api/admin/custom-charts/${chartId}`, {
      method: 'PATCH',
      json: { enabled: nextEnabled },
      csrf: true,
    });
    await loadAdminCustomCharts();
    await loadCustomCharts();
  } catch (err) {
    customChartsError.textContent = 'Aviso: ' + err.message;
    customChartsError.classList.add('visible');
  }
}

async function deleteCustomChart(chartId) {
  const chart = adminCustomCharts.find(item => item.id === chartId);
  if (!chart) return;
  if (!confirm(`Excluir o grafico "${chart.name}"?`)) return;
  try {
    await apiRequest(`/api/admin/custom-charts/${chartId}`, {
      method: 'DELETE',
      csrf: true,
    });
    if (customChartEditingId === chartId) resetCustomChartForm();
    await loadAdminCustomCharts();
    await loadCustomCharts();
  } catch (err) {
    customChartsError.textContent = 'Aviso: ' + err.message;
    customChartsError.classList.add('visible');
  }
}

function resetProfileRuleForm() {
  profileRuleEditingId = null;
  profileRuleForm.reset();
  profileRulePriorityInput.value = '100';
  profileRuleEnabledInput.value = '1';
  profileRuleFormTitle.textContent = 'Novo perfil customizado';
  profileRuleFormSub.textContent = 'Use o perfil extraido pelo sistema como base e sobreponha com regras adicionais quando precisar agrupar ou corrigir casos.';
  profileRuleHint.textContent = 'A regra entra antes do perfil base extraido. Quanto menor a prioridade, mais cedo a regra e aplicada.';
  profileRuleSubmitBtn.textContent = 'Criar perfil';
  profileRuleCancelBtn.classList.add('hidden');
  profileRulesFormError.classList.remove('visible');
}

function renderProfileRules() {
  profileRulesList.innerHTML = '';
  profileRulesEmpty.classList.toggle('hidden', adminProfileRules.length > 0);
  profileRulesSubtitle.textContent = adminProfileRules.length
    ? `${adminProfileRules.length} perfil(is) customizado(s)`
    : 'Nenhum perfil customizado cadastrado ainda.';

  if (!adminProfileRules.length) return;

  const table = document.createElement('table');
  table.className = 'admin-users-table';
  table.innerHTML = `
    <thead>
      <tr>
        <th>Perfil</th>
        <th>Criterios</th>
        <th>Prioridade</th>
        <th>Status</th>
        <th>Acoes</th>
      </tr>
    </thead>
    <tbody></tbody>
  `;

  const tbody = table.querySelector('tbody');
  adminProfileRules.forEach(rule => {
    const row = document.createElement('tr');

    const nameCell = document.createElement('td');
    nameCell.innerHTML = `<div class="admin-user-name">${esc(rule.name || 'Perfil')}</div>`;

    const criteriaCell = document.createElement('td');
    criteriaCell.className = 'admin-user-meta-cell';
    const chunks = [];
    if ((rule.base_profiles || []).length) chunks.push(`Base: ${rule.base_profiles.join(', ')}`);
    if (rule.labels_contains) chunks.push(`Rotulos: ${rule.labels_contains}`);
    if (rule.assignee_contains) chunks.push(`Responsavel: ${rule.assignee_contains}`);
    if (rule.bucket_contains) chunks.push(`Bucket: ${rule.bucket_contains}`);
    criteriaCell.innerHTML = chunks.map(item => `<div>${esc(item)}</div>`).join('') || '—';

    const priorityCell = document.createElement('td');
    priorityCell.className = 'admin-user-meta-cell';
    priorityCell.textContent = String(rule.priority ?? 100);

    const statusCell = document.createElement('td');
    const badges = document.createElement('div');
    badges.className = 'admin-user-badges';
    const statusBadge = document.createElement('span');
    statusBadge.className = `admin-badge ${rule.enabled ? 'admin' : 'disabled'}`.trim();
    statusBadge.textContent = rule.enabled ? 'ATIVO' : 'INATIVO';
    badges.appendChild(statusBadge);
    statusCell.appendChild(badges);

    const actionsCell = document.createElement('td');
    const actions = document.createElement('div');
    actions.className = 'admin-user-actions';

    const editBtn = document.createElement('button');
    editBtn.className = 'btn-small';
    editBtn.textContent = 'Editar';
    editBtn.addEventListener('click', () => startProfileRuleEdit(rule.id));

    const toggleBtn = document.createElement('button');
    toggleBtn.className = 'btn-small';
    toggleBtn.textContent = rule.enabled ? 'Desativar' : 'Ativar';
    toggleBtn.addEventListener('click', () => toggleProfileRuleEnabled(rule.id));

    const deleteBtn = document.createElement('button');
    deleteBtn.className = 'btn-small';
    deleteBtn.textContent = 'Excluir';
    deleteBtn.addEventListener('click', () => deleteProfileRule(rule.id));

    actions.append(editBtn, toggleBtn, deleteBtn);
    actionsCell.appendChild(actions);

    row.append(nameCell, criteriaCell, priorityCell, statusCell, actionsCell);
    tbody.appendChild(row);
  });

  profileRulesList.appendChild(table);
}

async function loadProfileRules() {
  if (!authState.authenticated) return;
  try {
    const body = await apiRequest('/api/profile-rules');
    profileRules = body.rules || [];
    if (dashData) {
      buildSidebar();
      renderChartFilters(activeChartId);
      renderActive();
    }
  } catch (_) {
    profileRules = [];
  }
}

async function loadAdminProfileRules() {
  if (!isAdminUser()) return;
  profileRulesError.classList.remove('visible');
  try {
    const body = await apiRequest('/api/admin/profile-rules');
    adminProfileRules = body.rules || [];
    renderProfileRules();
  } catch (err) {
    profileRulesError.textContent = 'Aviso: ' + err.message;
    profileRulesError.classList.add('visible');
  }
}

function startProfileRuleEdit(ruleId) {
  const rule = adminProfileRules.find(item => item.id === ruleId);
  if (!rule) return;
  profileRuleEditingId = rule.id;
  profileRuleNameInput.value = rule.name || '';
  profileRuleBaseProfilesInput.value = rule.base_profiles_text || '';
  profileRuleLabelsInput.value = rule.labels_contains || '';
  profileRuleAssigneeInput.value = rule.assignee_contains || '';
  profileRuleBucketInput.value = rule.bucket_contains || '';
  profileRulePriorityInput.value = String(rule.priority ?? 100);
  profileRuleEnabledInput.value = rule.enabled ? '1' : '0';
  profileRuleFormTitle.textContent = 'Editar perfil customizado';
  profileRuleFormSub.textContent = 'Ajuste o agrupamento para recalcular os graficos filtraveis baseados em perfil.';
  profileRuleHint.textContent = 'Essa regra tem precedencia sobre o perfil extraido automaticamente.';
  profileRuleSubmitBtn.textContent = 'Salvar alteracoes';
  profileRuleCancelBtn.classList.remove('hidden');
}

async function toggleProfileRuleEnabled(ruleId) {
  const rule = adminProfileRules.find(item => item.id === ruleId);
  if (!rule) return;
  const nextEnabled = !rule.enabled;
  if (!confirm(`${nextEnabled ? 'Ativar' : 'Desativar'} o perfil "${rule.name}"?`)) return;
  try {
    await apiRequest(`/api/admin/profile-rules/${ruleId}`, {
      method: 'PATCH',
      json: { enabled: nextEnabled },
      csrf: true,
    });
    await loadAdminProfileRules();
    await loadProfileRules();
  } catch (err) {
    profileRulesError.textContent = 'Aviso: ' + err.message;
    profileRulesError.classList.add('visible');
  }
}

async function deleteProfileRule(ruleId) {
  const rule = adminProfileRules.find(item => item.id === ruleId);
  if (!rule) return;
  if (!confirm(`Excluir o perfil customizado "${rule.name}"?`)) return;
  try {
    await apiRequest(`/api/admin/profile-rules/${ruleId}`, {
      method: 'DELETE',
      csrf: true,
    });
    if (profileRuleEditingId === ruleId) resetProfileRuleForm();
    await loadAdminProfileRules();
    await loadProfileRules();
  } catch (err) {
    profileRulesError.textContent = 'Aviso: ' + err.message;
    profileRulesError.classList.add('visible');
  }
}

function resolvedBaseProfile(task) {
  const raw = String(task?.profile_base_display || task?.profile_base || '').trim();
  if (!raw) return 'Outros';
  return BUILTIN_PROFILE_DISPLAY[raw] || raw;
}

function textMatchesTerms(value, terms) {
  const hay = normalizeText(value);
  if (!terms.length) return true;
  return terms.some(term => hay.includes(normalizeText(term)));
}

function profileRuleMatches(task, rule) {
  const baseProfiles = (rule.base_profiles || []).map(normalizeProfileName).filter(Boolean);
  const labelTerms = splitRuleTerms(rule.labels_contains);
  const assigneeTerms = splitRuleTerms(rule.assignee_contains);
  const bucketTerms = splitRuleTerms(rule.bucket_contains);
  let criteriaCount = 0;

  if (baseProfiles.length) {
    criteriaCount += 1;
    if (!baseProfiles.includes(normalizeProfileName(task?.profile_base || task?.profile_base_display || ''))) return false;
  }
  if (labelTerms.length) {
    criteriaCount += 1;
    if (!textMatchesTerms(task.labels, labelTerms)) return false;
  }
  if (assigneeTerms.length) {
    criteriaCount += 1;
    if (!textMatchesTerms(task.assignee, assigneeTerms)) return false;
  }
  if (bucketTerms.length) {
    criteriaCount += 1;
    if (!textMatchesTerms(task.bucket, bucketTerms)) return false;
  }

  return criteriaCount > 0;
}

function taskProfileName(task) {
  const orderedRules = [...profileRules]
    .filter(rule => rule.enabled)
    .sort((a, b) => (a.priority ?? 100) - (b.priority ?? 100) || String(a.name || '').localeCompare(String(b.name || ''), 'pt-BR'));

  for (const rule of orderedRules) {
    if (profileRuleMatches(task, rule)) return rule.name;
  }
  return resolvedBaseProfile(task);
}

function getAvailableProfilesForDashboard() {
  const names = new Set();
  (dashData?.task_rows || []).forEach(task => names.add(taskProfileName(task)));
  return ['Todos', ...Array.from(names).sort((a, b) => a.localeCompare(b, 'pt-BR'))];
}

function getFilterState(chartId) {
  if (!activeFilters[chartId]) activeFilters[chartId] = {};
  return activeFilters[chartId];
}


/* ── Event listeners: forms admin ──────────────────────── */
adminUserForm.addEventListener('submit', async e => {
  e.preventDefault();
  if (!isAdminUser()) return;

  adminFormError.classList.remove('visible');
  const payload = {
    display_name: adminDisplayNameInput.value.trim(),
    email: adminEmailInput.value.trim(),
    role: adminRoleInput.value,
  };
  const password = adminPasswordInput.value;
  if (password) payload.password = password;

  if (!adminEditingUserId && !password) {
    adminFormError.textContent = 'Aviso: Informe uma senha inicial para o novo usuario.';
    adminFormError.classList.add('visible');
    return;
  }

  try {
    const body = await apiRequest(
      adminEditingUserId ? `/api/admin/users/${adminEditingUserId}` : '/api/admin/users',
      {
        method: adminEditingUserId ? 'PATCH' : 'POST',
        json: payload,
        csrf: true,
      }
    );
    if (body.current_user) authState.user = body.current_user;
    resetAdminForm();
    await loadAdminUsers();
    syncTopbarState();
  } catch (err) {
    adminFormError.textContent = 'Aviso: ' + err.message;
    adminFormError.classList.add('visible');
  }
});

customChartSourceInput.addEventListener('change', () => {
  syncCustomChartSourceOptions(
    customChartSourceInput.value,
    customChartMetricInput.value,
    getSelectedCustomChartTypes(),
    customChartDefaultTypeInput.value
  );
});

customChartForm.addEventListener('submit', async e => {
  e.preventDefault();
  if (!isAdminUser()) return;

  customChartFormError.classList.remove('visible');
  const selectedChartTypes = getSelectedCustomChartTypes();
  if (!selectedChartTypes.length) {
    customChartFormError.textContent = 'Aviso: selecione ao menos um tipo de grafico.';
    customChartFormError.classList.add('visible');
    return;
  }
  const payload = {
    name: customChartNameInput.value.trim(),
    group: customChartGroupInput.value,
    subtitle: customChartSubtitleInput.value.trim(),
    source_key: customChartSourceInput.value,
    metric_key: customChartMetricInput.value,
    chart_type: customChartDefaultTypeInput.value,
    chart_types: selectedChartTypes,
    sort_mode: customChartSortInput.value,
    limit: customChartLimitInput.value.trim(),
    sort_order: customChartOrderInput.value.trim(),
    enabled: customChartEnabledInput.value === '1',
  };

  try {
    await apiRequest(
      customChartEditingId ? `/api/admin/custom-charts/${customChartEditingId}` : '/api/admin/custom-charts',
      {
        method: customChartEditingId ? 'PATCH' : 'POST',
        json: payload,
        csrf: true,
      }
    );
    resetCustomChartForm();
    await loadAdminCustomCharts();
    await loadCustomCharts();
  } catch (err) {
    customChartFormError.textContent = 'Aviso: ' + err.message;
    customChartFormError.classList.add('visible');
  }
});

profileRuleForm.addEventListener('submit', async e => {
  e.preventDefault();
  if (!isAdminUser()) return;

  profileRulesFormError.classList.remove('visible');
  const payload = {
    name: profileRuleNameInput.value.trim(),
    base_profiles_text: profileRuleBaseProfilesInput.value.trim(),
    labels_contains: profileRuleLabelsInput.value.trim(),
    assignee_contains: profileRuleAssigneeInput.value.trim(),
    bucket_contains: profileRuleBucketInput.value.trim(),
    priority: profileRulePriorityInput.value.trim(),
    enabled: profileRuleEnabledInput.value === '1',
  };

  try {
    await apiRequest(
      profileRuleEditingId ? `/api/admin/profile-rules/${profileRuleEditingId}` : '/api/admin/profile-rules',
      {
        method: profileRuleEditingId ? 'PATCH' : 'POST',
        json: payload,
        csrf: true,
      }
    );
    resetProfileRuleForm();
    await loadAdminProfileRules();
    await loadProfileRules();
  } catch (err) {
    profileRulesFormError.textContent = 'Aviso: ' + err.message;
    profileRulesFormError.classList.add('visible');
  }
});
