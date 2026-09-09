/* ════════════════════════════════════════════════════════════
   AUTH — Sessão, estado de autenticação e tela de login
════════════════════════════════════════════════════════════ */
function applySessionState(payload) {
  authState = {
    authenticated: !!payload.authenticated,
    bootstrapRequired: !!payload.bootstrap_required,
    csrfToken: payload.csrf_token || null,
    user: payload.user || null,
  };
}

function isAdminUser() {
  return authState.user?.role === 'admin';
}

function syncTopbarState() {
  topbarUserWrap.classList.toggle('hidden', !authState.user);
  topbarUserName.textContent = authState.user?.display_name || authState.user?.email || '';
  const adminPanelsHidden = adminScreen.classList.contains('hidden')
    && teamScreen.classList.contains('hidden')
    && customChartScreen.classList.contains('hidden')
    && comparativeScreen.classList.contains('hidden')
    && consolidatedScreen.classList.contains('hidden');
  btnAdminUsers.classList.toggle('visible', isAdminUser() && adminPanelsHidden);
  btnTeams.classList.toggle('visible', authState.authenticated && adminPanelsHidden);
  btnUploadNew.classList.toggle('visible', authState.authenticated && adminPanelsHidden);
  btnPlannerRules?.classList.toggle('visible', authState.authenticated && adminPanelsHidden);
  btnComparative.classList.toggle('visible', authState.authenticated && adminPanelsHidden);
  btnConsolidated.classList.toggle('visible', authState.authenticated && adminPanelsHidden);
}

function syncAuthModeUI() {
  const bootstrapMode = authState.bootstrapRequired;

  authTitle.textContent = bootstrapMode ? 'Criar primeiro admin' : 'Entrar';
  authSub.textContent = bootstrapMode
    ? 'Defina o administrador inicial. Esse usuario sera o dono dos primeiros dashboards.'
    : 'Acesse sua area para salvar e abrir dashboards por usuario.';

  authSubmitBtn.textContent = bootstrapMode ? 'Criar admin' : 'Entrar';
  displayNameFieldWrap.classList.toggle('hidden', !bootstrapMode);
  displayNameInput.required = bootstrapMode;
  passwordInput.setAttribute('autocomplete', bootstrapMode ? 'new-password' : 'current-password');
}

function syncSummaryContext() {
  const catalogItem = findCatalogItem(activeChartId);
  const isGeneral = activeChartId === 'kpis';
  summaryTitle.textContent = isGeneral ? 'Resumo geral da sprint' : `Resumo da secao`;
  summaryMeta.textContent = isGeneral
    ? 'Gere um resumo executivo do panorama completo da sprint.'
    : `Gere um resumo desta secao comparando ${catalogItem?.name || 'o grafico atual'} com os KPIs gerais da sprint.`;
  btnGenerateSummary.textContent = isGeneral ? 'Resumo geral' : 'Resumo da secao';
}

function clearDashboardSummary({ preserveReport = false } = {}) {
  currentSummaryText = '';
  if (!preserveReport) currentSummaryReportId = null;
  summaryCard.classList.remove('visible');
  summaryStatus.classList.add('hidden');
  summaryError.classList.remove('visible');
  summaryContent.textContent = '';
  syncSummaryContext();
  btnCopySummary.classList.add('hidden');
  btnHideSummary.classList.add('hidden');
  btnGenerateSummary.disabled = !currentReportId;
}

function hideDashboardSummary() {
  summaryCard.classList.remove('visible');
}

async function copyDashboardSummary() {
  if (!currentSummaryText) return;
  try {
    await navigator.clipboard.writeText(currentSummaryText);
    summaryMeta.textContent = 'Resumo copiado para a area de transferencia.';
  } catch (_) {
    summaryMeta.textContent = 'Nao foi possivel copiar automaticamente. Selecione o texto manualmente.';
  }
}

async function generateDashboardSummary() {
  if (!currentReportId) return;
  const catalogItem = findCatalogItem(activeChartId);
  const requestFilters = { ...(getFilterState(activeChartId) || {}) };
  summaryCard.classList.add('visible');
  summaryStatus.classList.remove('hidden');
  summaryStatus.textContent = 'Gerando resumo...';
  summaryError.classList.remove('visible');
  summaryContent.textContent = '';
  summaryMeta.textContent = activeChartId === 'kpis'
    ? 'Processando o payload estruturado do dashboard completo.'
    : `Processando a secao ${catalogItem?.name || activeChartId} e comparando com os KPIs gerais.`;
  btnGenerateSummary.disabled = true;

  try {
    const body = await apiRequest(`/api/reports/${currentReportId}/summary`, {
      method: 'POST',
      json: {
        chart_id: activeChartId,
        filters: requestFilters,
      },
      csrf: true,
    });
    currentSummaryText = body.summary || '';
    currentSummaryReportId = currentReportId;
    summaryContent.textContent = currentSummaryText || 'Nenhum resumo gerado.';
    const providerLabel = body.provider === 'ollama'
      ? `Ollama (${body.model || 'modelo local'})`
      : body.provider === 'heuristic_fallback'
        ? `Fallback local (${body.model || 'Ollama indisponivel'})`
        : 'Resumo local';
    const generatedAt = body.generated_at ? fmtDateTime(body.generated_at) : 'agora';
    const scopeLabel = body.scope?.label || catalogItem?.name || 'Dashboard';
    const filterLabel = body.scope?.filters?.profile && body.scope.filters.profile !== 'Todos'
      ? ` Filtro ativo: perfil ${body.scope.filters.profile}.`
      : '';
    const agingViewMap = { areas: 'área', categoria: 'categoria', colaborador: 'colaborador' };
    const agingFilterLabel = body.scope?.filters?.aging_view
      ? ` Filtro ativo: visão ${agingViewMap[body.scope.filters.aging_view] || body.scope.filters.aging_view}.`
      : '';
    const agingTaskLabels = Array.isArray(body.scope?.filters?.aging_task_labels)
      ? body.scope.filters.aging_task_labels.filter(Boolean)
      : [];
    const agingTaskFilterLabel = agingTaskLabels.length
      ? ` Filtro ativo: ${agingTaskLabels.length} rótulo(s) selecionado(s) (${agingTaskLabels.slice(0, 3).join(', ')}${agingTaskLabels.length > 3 ? ', ...' : ''}).`
      : '';
    const deliveryPeople = Array.isArray(body.scope?.filters?.delivery_people)
      ? body.scope.filters.delivery_people.filter(Boolean)
      : [];
    const deliveryPersonFilterLabel = deliveryPeople.length
      ? ` Filtro ativo: ${deliveryPeople.length} pessoa(s) selecionada(s) (${deliveryPeople.slice(0, 3).join(', ')}${deliveryPeople.length > 3 ? ', ...' : ''}).`
      : body.scope?.filters?.delivery_person
        ? ` Filtro ativo: pessoa ${body.scope.filters.delivery_person}.`
        : '';
    summaryTitle.textContent = body.scope?.kind === 'section' ? `Resumo da secao` : 'Resumo geral da sprint';
    summaryMeta.textContent = `Escopo: ${scopeLabel}. Fonte: ${providerLabel}. Gerado em ${generatedAt}.${filterLabel}${agingFilterLabel}${agingTaskFilterLabel}${deliveryPersonFilterLabel}`;
    if (body.warning) {
      summaryError.textContent = 'Aviso: ' + body.warning;
      summaryError.classList.add('visible');
    }
    btnCopySummary.classList.toggle('hidden', !currentSummaryText);
    btnHideSummary.classList.remove('hidden');
  } catch (err) {
    summaryError.textContent = 'Aviso: ' + err.message;
    summaryError.classList.add('visible');
    summaryMeta.textContent = activeChartId === 'kpis'
      ? 'Falha ao gerar o resumo geral da sprint.'
      : 'Falha ao gerar o resumo da secao atual.';
  } finally {
    summaryStatus.classList.add('hidden');
    btnGenerateSummary.disabled = !currentReportId;
  }
}

function showAuthScreen(bootstrapRequired = false, { navigateTo = true } = {}) {
  if (bootstrapRequired) document.body.classList.remove('public-mode');
  authState.authenticated = false;
  authState.user = null;
  authState.csrfToken = null;
  authState.bootstrapRequired = bootstrapRequired;
  reportList = [];
  adminUsers = [];
  customCharts = [];
  adminCustomCharts = [];
  profileRules = [];
  adminProfileRules = [];
  currentReportId = null;
  adminEditingUserId = null;
  customChartEditingId = null;
  profileRuleEditingId = null;
  activeFilters = {};
  authError.classList.remove('visible');
  authForm.reset();
  authMode = bootstrapRequired ? 'bootstrap' : 'login';
  syncAuthModeUI();
  if (!bootstrapRequired && typeof showPublicAuth === 'function') {
    showPublicAuth({ navigateTo });
  }
  authScreen.classList.remove('hidden');
  sidebar.classList.add('hidden');
  uploadScreen.classList.add('hidden');
  adminScreen.classList.add('hidden');
  teamScreen.classList.add('hidden');
  customChartScreen.classList.add('hidden');
  comparativeScreen.classList.add('hidden');
  consolidatedScreen.classList.add('hidden');
  dashboardEl.classList.remove('visible');
  btnUploadNew.classList.remove('visible');
  btnPlannerRules?.classList.remove('visible');
  btnComparative.classList.remove('visible');
  btnConsolidated.classList.remove('visible');
  btnAdminUsers.classList.remove('visible');
  btnTeams.classList.remove('visible');
  sprintBadgeEl.classList.remove('visible');
  menuToggle.classList.add('hidden');
  renderReports();
  renderAdminUsers();
  renderCustomCharts();
  renderProfileRules();
  clearDashboardSummary();
  syncTopbarState();
  if (typeof buildSidebar === 'function') buildSidebar();
  closeSidebar();
}

function showHomeScreen({ navigateTo = true, route = '/dashboard' } = {}) {
  if (navigateTo) window.setAppRoute?.(route);
  window.hidePublicViews?.();
  document.body.classList.remove('public-mode');
  authScreen.classList.add('hidden');
  sidebar.classList.remove('hidden');
  uploadScreen.classList.remove('hidden');
  adminScreen.classList.add('hidden');
  teamScreen.classList.add('hidden');
  customChartScreen.classList.add('hidden');
  comparativeScreen.classList.add('hidden');
  consolidatedScreen.classList.add('hidden');
  dashboardEl.classList.remove('visible');
  btnUploadNew.classList.add('visible');
  btnPlannerRules?.classList.add('visible');
  sprintBadgeEl.classList.remove('visible');
  menuToggle.classList.remove('hidden');
  clearDashboardSummary();
  syncTopbarState();
  closeSidebar();
}


/* ── Refresh de sessão ──────────────────────────────────── */
async function refreshSession() {
  const body = await apiRequest('/api/me');
  applySessionState(body);
  if (!authState.authenticated) {
    if (typeof resolveInitialRoute === 'function') {
      await resolveInitialRoute(false, authState.bootstrapRequired);
    } else {
      showAuthScreen(authState.bootstrapRequired);
    }
    return;
  }
  if (typeof resolveInitialRoute === 'function') {
    await resolveInitialRoute(true, false);
  } else {
    if (typeof showPostLoginScreen === 'function') {
      await showPostLoginScreen();
    } else {
      showHomeScreen();
    }
  }
  await loadProfileRules();
  await loadCustomCharts();
  await loadReports();
  if (typeof loadSavedRoadmaps === 'function') await loadSavedRoadmaps();
  if (typeof loadTeams === 'function') await loadTeams();
}

function openLibraryScreen({ navigateTo = true } = {}) {
  showHomeScreen({ navigateTo, route: '/biblioteca' });
}

/* ── Event listeners: login ─────────────────────────────── */

authForm.addEventListener('submit', async e => {
  e.preventDefault();
  authError.classList.remove('visible');
  const payload = {
    email: emailInput.value.trim(),
    password: passwordInput.value,
  };
  if (authMode === 'bootstrap') {
    payload.display_name = displayNameInput.value.trim();
  }
  try {
    const endpoint = authMode === 'bootstrap'
      ? '/api/bootstrap'
      : '/api/login';
    const body = await apiRequest(
      endpoint,
      { method: 'POST', json: payload }
    );
    applySessionState(body);
    showHomeScreen();
    await loadProfileRules();
    await loadCustomCharts();
    await loadReports();
    if (typeof loadSavedRoadmaps === 'function') await loadSavedRoadmaps();
    if (typeof loadTeams === 'function') await loadTeams();
  } catch (err) {
    authError.textContent = 'Aviso: ' + err.message;
    authError.classList.add('visible');
  }
});

/* ── Logout ─────────────────────────────────────────────── */
async function logout() {
  try {
    await apiRequest('/api/logout', { method: 'POST', json: {}, csrf: true });
    showAuthScreen(false, { navigateTo: false });
    if (typeof showLandingScreen === 'function') {
      await showLandingScreen({ navigateTo: true, replaceRoute: true });
    }
  } catch (_) {
    showAuthScreen(false);
  }
}
