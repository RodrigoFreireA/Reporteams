/* DASHBOARD - Carregamento, sidebar e seleção de gráficos */
/* LOAD DASHBOARD */
function loadDashboard(data) {
  dashData = data;
  clearDashboardSummary({ preserveReport: true });
  document.getElementById('loadingOverlay').classList.remove('visible');
  authScreen.classList.add('hidden');
  sidebar.classList.remove('hidden');
  uploadScreen.classList.add('hidden');
  teamScreen.classList.add('hidden');
  adminScreen.classList.add('hidden');
  customChartScreen.classList.add('hidden');
  comparativeScreen.classList.add('hidden');
  consolidatedScreen.classList.add('hidden');
  dashboardEl.classList.add('visible');
  btnUploadNew.classList.add('visible');
  menuToggle.classList.remove('hidden');
  syncTopbarState();
  const sprint = data.meta?.sprint_name || '';
  if (sprint) {
    sprintBadgeEl.textContent = sprint;
    sprintBadgeEl.classList.add('visible');
  } else {
    sprintBadgeEl.classList.remove('visible');
    sprintBadgeEl.textContent = '';
  }
  btnGenerateSummary.disabled = !currentReportId;
  buildSidebar();
  selectChart('kpis');
}

/* â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•
   SIDEBAR
â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â• */
const SIDEBAR_GROUP_STATE_KEY = 'rcw-sidebar-groups';
const SIDEBAR_GROUP_ORDER = ['Resumo', 'Andamento', 'Distribui\u00e7\u00e3o', 'Tempo'];
const SIDEBAR_DEFAULT_OPEN_GROUPS = new Set(['Resumo']);

function readSidebarGroupState() {
  try {
    return JSON.parse(localStorage.getItem(SIDEBAR_GROUP_STATE_KEY) || '{}') || {};
  } catch {
    return {};
  }
}

function writeSidebarGroupState(state) {
  localStorage.setItem(SIDEBAR_GROUP_STATE_KEY, JSON.stringify(state || {}));
}

function getActiveSidebarGroup() {
  return findCatalogItem(activeChartId)?.group || null;
}

function setSidebarGroupOpen(groupName, open, { persist = true } = {}) {
  const groupEl = Array.from(document.querySelectorAll('.sidebar-group'))
    .find(el => el.dataset.group === groupName);
  if (!groupEl) return;
  groupEl.classList.toggle('collapsed', !open);
  const btn = groupEl.querySelector('.sidebar-group-toggle');
  if (btn) btn.setAttribute('aria-expanded', open ? 'true' : 'false');
  if (persist) {
    const state = readSidebarGroupState();
    state[groupName] = !!open;
    writeSidebarGroupState(state);
  }
}

function ensureActiveSidebarGroupOpen() {
  const activeGroup = getActiveSidebarGroup();
  if (activeGroup) setSidebarGroupOpen(activeGroup, true);
}

function restoreSidebarGroupStates() {
  const state = readSidebarGroupState();
  document.querySelectorAll('.sidebar-group').forEach(groupEl => {
    const groupName = groupEl.dataset.group || '';
    const open = Object.prototype.hasOwnProperty.call(state, groupName)
      ? !!state[groupName]
      : SIDEBAR_DEFAULT_OPEN_GROUPS.has(groupName);
    setSidebarGroupOpen(groupName, open, { persist: false });
  });
}

function applySidebarSearch(rawValue = '') {
  const query = normalizeText(rawValue);
  let visibleCount = 0;

  document.querySelectorAll('.sidebar-group').forEach(groupEl => {
    const groupName = groupEl.dataset.group || '';
    let groupHasMatch = false;
    groupEl.querySelectorAll('.nav-item').forEach(itemEl => {
      const haystack = normalizeText(`${itemEl.dataset.label || ''} ${groupName}`);
      const matches = !query || haystack.includes(query);
      itemEl.classList.toggle('filtered-out', !matches);
      if (matches) {
        if (query) itemEl.closest('.sidebar-subgroup')?.classList.remove('collapsed');
        if (query) itemEl.closest('.sidebar-subgroup-nested')?.classList.remove('collapsed');
        groupHasMatch = true;
        visibleCount += 1;
      }
    });
    groupEl.classList.toggle('filtered-out', !groupHasMatch);
    if (query && groupHasMatch) setSidebarGroupOpen(groupName, true, { persist: false });
  });

  if (!query) {
    restoreSidebarGroupStates();
    ensureActiveSidebarGroupOpen();
  }

  const emptyEl = document.getElementById('sidebarSearchEmpty');
  if (emptyEl) emptyEl.classList.toggle('hidden', visibleCount > 0);
}

function buildChartSidebar() {
  const sidebar = document.getElementById('sidebar');
  const chartsContainer = document.createElement('div');
  chartsContainer.className = 'sidebar-chart-nav';
  chartsContainer.id = 'sidebarChartNav';
  sidebar.appendChild(chartsContainer);

  const searchWrap = document.createElement('div');
  searchWrap.className = 'sidebar-search';
  const searchInputEl = document.createElement('input');
  searchInputEl.className = 'sidebar-search-input';
  searchInputEl.id = 'sidebarSearchInput';
  searchInputEl.type = 'search';
  searchInputEl.placeholder = 'Buscar gr\u00e1fico...';
  searchInputEl.setAttribute('aria-label', 'Buscar gr\u00e1fico');
  searchWrap.appendChild(searchInputEl);
  chartsContainer.appendChild(searchWrap);

  const groupedItems = {};
  getCatalog().forEach(item => {
    if (!hasData(item.id)) return;
    const groupName = item.group || 'Outros';
    if (!groupedItems[groupName]) groupedItems[groupName] = [];
    groupedItems[groupName].push(item);
  });

  const orderedGroups = Object.entries(groupedItems).sort(([a], [b]) => {
    const ai = SIDEBAR_GROUP_ORDER.indexOf(a);
    const bi = SIDEBAR_GROUP_ORDER.indexOf(b);
    if (ai !== -1 || bi !== -1) return (ai === -1 ? 999 : ai) - (bi === -1 ? 999 : bi);
    return a.localeCompare(b, 'pt-BR');
  });

  orderedGroups.forEach(([groupName, items]) => {
    const section = document.createElement('section');
    section.className = 'sidebar-group';
    section.dataset.group = groupName;

    const btn = document.createElement('button');
    btn.className = 'sidebar-group-toggle';
    btn.type = 'button';
    btn.innerHTML = `
      <span class="sidebar-group-chevron" aria-hidden="true"></span>
      <span class="sidebar-group-name">${esc(groupName)}</span>
      <span class="sidebar-group-count">${items.length}</span>
    `;
    btn.addEventListener('click', () => {
      const activeGroup = getActiveSidebarGroup();
      const willOpen = section.classList.contains('collapsed');
      if (!willOpen && activeGroup === groupName) return;
      setSidebarGroupOpen(groupName, willOpen);
    });
    section.appendChild(btn);

    const list = document.createElement('div');
    list.className = 'sidebar-group-items';
    let lastSubgroup = null;
    let lastSubgroup2 = null;
    let currentSubgroupItems = null;
    let currentNestedItems = null;
    const startSubgroup = subgroup => {
      const subgroupEl = document.createElement('div');
      subgroupEl.className = 'sidebar-subgroup';
      const subgroupBtn = document.createElement('button');
      subgroupBtn.type = 'button';
      subgroupBtn.className = 'sidebar-subgroup-toggle';
      subgroupBtn.setAttribute('aria-expanded', 'true');
      subgroupBtn.innerHTML = `
        <span class="sidebar-subgroup-chevron" aria-hidden="true"></span>
        <span class="sidebar-subgroup-name">${esc(subgroup)}</span>
      `;
      currentSubgroupItems = document.createElement('div');
      currentSubgroupItems.className = 'sidebar-subgroup-items';
      subgroupBtn.addEventListener('click', () => {
        const isCollapsed = subgroupEl.classList.toggle('collapsed');
        subgroupBtn.setAttribute('aria-expanded', String(!isCollapsed));
      });
      subgroupEl.append(subgroupBtn, currentSubgroupItems);
      list.appendChild(subgroupEl);
      lastSubgroup = subgroup;
      lastSubgroup2 = null;
      currentNestedItems = null;
    };
    const startNestedSubgroup = subgroup => {
      const nestedEl = document.createElement('div');
      nestedEl.className = 'sidebar-subgroup-nested';
      const nestedBtn = document.createElement('button');
      nestedBtn.type = 'button';
      nestedBtn.className = 'sidebar-subgroup-nested-toggle';
      nestedBtn.setAttribute('aria-expanded', 'true');
      nestedBtn.innerHTML = `
        <span class="sidebar-subgroup-chevron" aria-hidden="true"></span>
        <span class="sidebar-subgroup-name">${esc(subgroup)}</span>
      `;
      currentNestedItems = document.createElement('div');
      currentNestedItems.className = 'sidebar-subgroup-nested-items';
      nestedBtn.addEventListener('click', () => {
        const isCollapsed = nestedEl.classList.toggle('collapsed');
        nestedBtn.setAttribute('aria-expanded', String(!isCollapsed));
      });
      nestedEl.append(nestedBtn, currentNestedItems);
      currentSubgroupItems.appendChild(nestedEl);
      lastSubgroup2 = subgroup;
    };
    items.forEach(item => {
      const subgroup = item.subgroup || '';
      const subgroup2 = item.subgroup2 || '';
      let targetList = list;
      if (subgroup) {
        if (subgroup !== lastSubgroup) startSubgroup(subgroup);
        if (subgroup2) {
          if (subgroup2 !== lastSubgroup2) startNestedSubgroup(subgroup2);
          targetList = currentNestedItems;
        } else {
          lastSubgroup2 = null;
          currentNestedItems = null;
          targetList = currentSubgroupItems;
        }
      } else {
        currentSubgroupItems = null;
        currentNestedItems = null;
        lastSubgroup = null;
        lastSubgroup2 = null;
      }
      const el = document.createElement('button');
      el.type = 'button';
      el.className = 'nav-item' + (item.id === activeChartId ? ' active' : '');
      el.dataset.chart = item.id;
      el.dataset.label = item.name;
      el.innerHTML = `<span class="nav-icon">${item.icon}</span><span class="nav-label">${esc(item.name)}</span>`;
      el.addEventListener('click', () => selectChart(item.id));
      targetList.appendChild(el);
    });
    section.appendChild(list);
    chartsContainer.appendChild(section);
  });

  const empty = document.createElement('div');
  empty.className = 'sidebar-search-empty hidden';
  empty.id = 'sidebarSearchEmpty';
  empty.textContent = 'Nenhum gr\u00e1fico encontrado';
  chartsContainer.appendChild(empty);

  restoreSidebarGroupStates();
  ensureActiveSidebarGroupOpen();

  const searchInput = document.getElementById('sidebarSearchInput');
  if (searchInput) searchInput.addEventListener('input', () => applySidebarSearch(searchInput.value));
}

function hasData(id) {
  if (!dashData) return false;
  const customChart = getCustomChartByChartId(id);
  if (customChart) {
    if (customChart.source_key === 'wip_profile') {
      return !!(dashData.task_rows?.length && dashData.wip?.dates?.length);
    }
    const rows = getCustomChartRows(customChart);
    return customChart.source_key === 'histograma'
      ? rows.some(row => row[1] > 0)
      : rows.length > 0;
  }
  const d = dashData;
  if (['flow_metrics', 'scope_quality', 'time_health'].includes(id) && typeof ensureAdvancedMetrics === 'function') {
    ensureAdvancedMetrics();
  }
  switch (id) {
    case 'kpis':        return !!d.kpis;
    case 'delivery_person':
      return !!(
        (typeof buildPersonDeliveryRows === 'function' && buildPersonDeliveryRows().length)
        || (typeof buildPersonDeliveryDistribution === 'function' && buildPersonDeliveryDistribution().length)
      );
    case 'flow_metrics': return !!d.flow_metrics;
    case 'scope_quality': return !!d.scope_quality_metrics;
    case 'time_health': return !!d.time_metrics;
    case 'roadmap':     return !!(d.roadmap_items?.length);
    case 'burndown':    return !!(d.burndown?.rows?.some(r => r[0]));
    case 'burndown_hu': return !!(d.burndown_hu?.rows?.some(r => r[0]));
    case 'burndown_sp': return !!(d.burndown_sp?.total_sp > 0 && d.burndown_sp?.rows?.some(r => r[0]));
    case 'burnup':      return !!(d.burndown?.rows?.some(r => r[0]));
    case 'burnup_hu':   return !!(d.burndown_hu?.rows?.some(r => r[0]));
    case 'burnup_sp':   return !!(d.burndown_sp?.total_sp > 0 && d.burndown_sp?.rows?.some(r => r[0]));
    case 'burndown_nao_prev':
    case 'burnup_nao_prev':
      return !!(d.burndown_nao_prev?.rows?.some(r => r[0]));
    case 'burndown_nao_prev_hu':
    case 'burnup_nao_prev_hu':
      return !!(d.burndown_nao_prev_hu?.rows?.some(r => r[0]));
    case 'cfd':         return !!(d.cfd?.dates?.length);
    case 'wip':         return !!(d.wip?.dates?.length);
    case 'hu_tasks':    return !!(d.hu_list?.length);
    case 'areas':       return !!(d.area_rows?.length);
    case 'categoria':   return !!(d.cat_rows?.length);
    case 'colaborador': return !!(d.collab_rows?.length);
    case 'hu_inout':    return !!(d.in_out?.length);
    case 'dispersao': {
      const ctsHasMatrix = (d.cts?.matrix || []).some(row => Array.isArray(row) && row.some(value => Number(value) > 0));
      const ctsHasOutside = (d.cts?.fora_hu || []).some(value => Number(value) > 0);
      const ctsReady = !!(d.cts?.dates?.length && (ctsHasMatrix || ctsHasOutside));
      const dispReady = Array.isArray(d.dispersao?.days)
        ? d.dispersao.days.length > 0
        : Number(d.dispersao?.days) > 0;
      return ctsReady || dispReady;
    }
    case 'rotulos':     return !!(d.rotulos_rows?.length);
    case 'responsaveis':return !!(d.resp_rows?.length);
    case 'aging':       return hasAgingData('aging');
    case 'aging_tasks': return hasAgingTaskData('aging_tasks');
    case 'histograma':  return !!(d.hist_31?.some(v => v > 0));
    default:            return false;
  }
}

function scrollDashboardViewToTop() {
  const targets = [
    document.getElementById('mainArea'),
    document.getElementById('chartBody'),
    document.scrollingElement,
  ];
  targets.forEach(target => {
    if (!target) return;
    if (typeof target.scrollTo === 'function') {
      target.scrollTo({ top: 0, left: 0, behavior: 'auto' });
    } else {
      target.scrollTop = 0;
      target.scrollLeft = 0;
    }
  });
}

function buildSidebar() {
  const sidebar = document.getElementById('sidebar');
  if (!sidebar) return;
  sidebar.innerHTML = '';

  const header = document.createElement('div');
  header.className = 'sidebar-teams-header';
  header.innerHTML = `
    <div>
      <div class="sidebar-section-label">Equipes</div>
      <div class="sidebar-teams-subtitle">Dashboards por time</div>
    </div>`;
  sidebar.appendChild(header);

  const availableTeams = typeof teams !== 'undefined' ? teams : [];
  const assignedReportIds = new Set();
  availableTeams.forEach(team => {
    const teamReports = reportList.filter(report => Number(report.team_id) === Number(team.id));
    teamReports.forEach(report => assignedReportIds.add(Number(report.id)));
    appendSidebarTeam(sidebar, team, teamReports);
  });

  const unassignedReports = reportList.filter(report => !assignedReportIds.has(Number(report.id)) && !report.team_id);
  if (unassignedReports.length || !availableTeams.length) {
    appendSidebarTeam(sidebar, { id: '', name: 'Sem equipe', active: true }, unassignedReports, { unassigned: true });
  }

  if (!dashData) {
    const empty = document.createElement('div');
    empty.className = 'sidebar-dashboard-empty';
    empty.innerHTML = '<strong>Nenhum dashboard aberto</strong><span>Use o + para importar um board do Planner.</span>';
    sidebar.appendChild(empty);
    return;
  }

  const divider = document.createElement('div');
  divider.className = 'sidebar-nav-divider';
  sidebar.appendChild(divider);
  const chartLabel = document.createElement('div');
  chartLabel.className = 'sidebar-section-label sidebar-chart-label';
  chartLabel.textContent = 'Graficos do dashboard';
  sidebar.appendChild(chartLabel);
  buildChartSidebar();
}

function appendSidebarTeam(sidebar, team, reports, { unassigned = false } = {}) {
  const section = document.createElement('section');
  section.className = `sidebar-team-group${unassigned ? ' is-unassigned' : ''}`;
  const head = document.createElement('div');
  head.className = 'sidebar-team-head';
  head.innerHTML = `
    <button type="button" class="sidebar-team-toggle">
      <span class="sidebar-team-chevron"></span>
      <span class="sidebar-team-name">${esc(team.name)}</span>
      <span class="sidebar-team-count">${reports.length}</span>
    </button>
    <button type="button" class="sidebar-team-add" title="Adicionar dashboard para ${esc(team.name)}">+</button>`;
  const list = document.createElement('div');
  list.className = 'sidebar-team-reports';
  reports.forEach(report => {
    const item = document.createElement('button');
    item.type = 'button';
    item.className = `sidebar-dashboard-item${Number(report.id) === Number(currentReportId) ? ' active' : ''}`;
    item.innerHTML = `<span class="sidebar-dashboard-dot"></span><span>${esc(report.title || report.sprint_name || 'Dashboard')}</span>`;
    item.addEventListener('click', () => openReport(report.id));
    list.appendChild(item);
  });
  if (!reports.length) {
    const empty = document.createElement('div');
    empty.className = 'sidebar-team-empty';
    empty.textContent = 'Nenhum dashboard';
    list.appendChild(empty);
  }
  head.querySelector('.sidebar-team-toggle').addEventListener('click', () => section.classList.toggle('collapsed'));
  head.querySelector('.sidebar-team-add').addEventListener('click', () => resetToUpload(team.id || ''));
  section.append(head, list);
  sidebar.appendChild(section);
}

/* â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•
   SELECT CHART
â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â• */
function selectChart(id) {
  activeChartId = id;
  clearDashboardSummary({ preserveReport: true });
  document.querySelectorAll('.nav-item').forEach(el =>
    el.classList.toggle('active', el.dataset.chart === id));
  ensureActiveSidebarGroupOpen();
  // fecha sidebar em mobile ao selecionar item
  if (window.innerWidth <= 640) closeSidebar();

  const cat = findCatalogItem(id);
  if (!cat) return;
  const title = id === 'wip' && !dashData?.task_rows?.length ? 'WIP por Bucket' : cat.name;
  const subtitle = id === 'wip' && !dashData?.task_rows?.length
    ? 'Work In Progress ao longo do tempo por coluna do board'
    : (cat.subtitle || '');
  const titleEl = document.getElementById('chartTitle');
  const subtitleEl = document.getElementById('chartSubtitle');
  titleEl.textContent = title;
  subtitleEl.textContent = subtitle;
  // Aplicar fonte CTS quando seção for dispersão (fallback para dispersão legada)
  titleEl.classList.toggle('cts-font', id === 'dispersao');
  subtitleEl.classList.toggle('cts-font', id === 'dispersao');
  renderChartFilters(id);

  const sel = document.getElementById('typeSelector');
  sel.innerHTML = '';
  if (cat.types.length > 1) {
    cat.types.forEach(type => {
      const btn = document.createElement('button');
      btn.className = 'type-chip' + (getActiveType(id) === type ? ' active' : '');
      btn.dataset.type = type;
      const ct = CHART_TYPES[type];
      btn.innerHTML = `<span>${ct.icon}</span><span>${ct.label}</span>`;
      btn.addEventListener('click', () => {
        activeType[id] = type;
        sel.querySelectorAll('.type-chip').forEach(b =>
          b.classList.toggle('active', b.dataset.type === type));
        renderActive();
      });
      sel.appendChild(btn);
    });
  }
  renderActive();
  scrollDashboardViewToTop();
}

function getActiveType(id) {
  const catalogItem = findCatalogItem(id);
  if (activeType[id] && catalogItem?.types?.includes(activeType[id])) return activeType[id];
  return catalogItem?.types?.[0] || 'bar_v';
}
function renderChartFilters(id) {
  chartFiltersEl.innerHTML = '';
  const customChart = getCustomChartByChartId(id);
  const builtinWipProfile = id === 'wip' && !!dashData?.task_rows?.length;
  const usesWipProfile = builtinWipProfile || (!!customChart && customChart.source_key === 'wip_profile');
  const usesAging = id === 'aging';
  const usesAgingTasks = id === 'aging_tasks';
  const usesDeliveryPerson = id === 'delivery_person';
  if (!usesWipProfile && !usesAging && !usesAgingTasks && !usesDeliveryPerson) return;

  const state = getFilterState(id);

  if (usesDeliveryPerson) {
    const options = typeof getAvailableDeliveryPeople === 'function' ? getAvailableDeliveryPeople() : [];
    if (!options.length) return;
    if (!Array.isArray(state.delivery_people)) {
      state.delivery_people = state.delivery_person && options.includes(state.delivery_person)
        ? [state.delivery_person]
        : options.slice();
    }
    state.delivery_people = state.delivery_people.filter(person => options.includes(person));

    const wrap = document.createElement('div');
    wrap.className = 'chart-filter chart-filter--stacked chart-filter--people';
    const label = document.createElement('label');
    label.textContent = 'Pessoas';
    const body = document.createElement('div');
    body.className = 'chart-filter-body';
    const list = document.createElement('div');
    list.className = 'chart-checkbox-grid';
    options.forEach(option => {
      const item = document.createElement('label');
      item.className = 'chart-checkbox-item';
      const checkbox = document.createElement('input');
      checkbox.type = 'checkbox';
      checkbox.value = option;
      checkbox.checked = state.delivery_people.includes(option);
      checkbox.addEventListener('change', () => {
        state.delivery_people = Array.from(list.querySelectorAll('input[type="checkbox"]:checked'))
          .map(input => input.value);
        state.delivery_person = state.delivery_people.length === 1 ? state.delivery_people[0] : '';
        syncDeliveryPeopleFilter();
        clearDashboardSummary({ preserveReport: true });
        renderActive();
      });
      item.append(checkbox, document.createElement('span'));
      item.querySelector('span').textContent = option;
      list.appendChild(item);
    });
    const actions = document.createElement('div');
    actions.className = 'chart-filter-actions';
    const allBtn = document.createElement('button');
    allBtn.type = 'button';
    allBtn.className = 'btn-small';
    allBtn.textContent = 'Todos';
    allBtn.addEventListener('click', () => {
      state.delivery_people = options.slice();
      state.delivery_person = '';
      syncDeliveryPeopleFilter();
      clearDashboardSummary({ preserveReport: true });
      renderActive();
    });
    const clearBtn = document.createElement('button');
    clearBtn.type = 'button';
    clearBtn.className = 'btn-small';
    clearBtn.textContent = 'Desmarcar todos';
    clearBtn.disabled = !state.delivery_people.length;
    clearBtn.addEventListener('click', () => {
      state.delivery_people = [];
      state.delivery_person = '';
      syncDeliveryPeopleFilter();
      clearDashboardSummary({ preserveReport: true });
      renderActive();
    });
    const syncDeliveryPeopleFilter = () => {
      const selectedPeople = new Set(state.delivery_people);
      list.querySelectorAll('input[type="checkbox"]').forEach(input => {
        input.checked = selectedPeople.has(input.value);
      });
      allBtn.disabled = state.delivery_people.length === options.length;
      clearBtn.disabled = !state.delivery_people.length;
    };
    syncDeliveryPeopleFilter();
    actions.append(allBtn, clearBtn);
    body.append(list, actions);
    wrap.append(label, body);
    chartFiltersEl.appendChild(wrap);

    const weekOptions = typeof getAvailableDeliveryWeeks === 'function' ? getAvailableDeliveryWeeks() : [];
    if (weekOptions.length) {
      const selectedWeeks = typeof getSelectedDeliveryWeeks === 'function'
        ? getSelectedDeliveryWeeks(id)
        : (Array.isArray(state.delivery_weeks) ? state.delivery_weeks : weekOptions.map(option => option.id));
      state.delivery_weeks = selectedWeeks.filter(weekId => weekOptions.some(option => option.id === weekId));

      const weekWrap = document.createElement('div');
      weekWrap.className = 'chart-filter chart-filter--stacked chart-filter--weeks';
      const weekLabel = document.createElement('label');
      weekLabel.textContent = 'Semanas';
      const weekBody = document.createElement('div');
      weekBody.className = 'chart-filter-body';
      const weekList = document.createElement('div');
      weekList.className = 'chart-checkbox-grid';

      weekOptions.forEach(option => {
        const item = document.createElement('label');
        item.className = 'chart-checkbox-item';
        const checkbox = document.createElement('input');
        checkbox.type = 'checkbox';
        checkbox.value = option.id;
        checkbox.checked = state.delivery_weeks.includes(option.id);
        checkbox.addEventListener('change', () => {
          state.delivery_weeks = Array.from(weekList.querySelectorAll('input[type="checkbox"]:checked'))
            .map(input => input.value);
          syncDeliveryWeekFilter();
          clearDashboardSummary({ preserveReport: true });
          renderActive();
        });
        item.append(checkbox, document.createElement('span'));
        item.querySelector('span').textContent = option.label;
        weekList.appendChild(item);
      });

      const weekActions = document.createElement('div');
      weekActions.className = 'chart-filter-actions';
      const allWeeksBtn = document.createElement('button');
      allWeeksBtn.type = 'button';
      allWeeksBtn.className = 'btn-small';
      allWeeksBtn.textContent = 'Todas';
      allWeeksBtn.addEventListener('click', () => {
        state.delivery_weeks = weekOptions.map(option => option.id);
        syncDeliveryWeekFilter();
        clearDashboardSummary({ preserveReport: true });
        renderActive();
      });
      const clearWeeksBtn = document.createElement('button');
      clearWeeksBtn.type = 'button';
      clearWeeksBtn.className = 'btn-small';
      clearWeeksBtn.textContent = 'Desmarcar todas';
      clearWeeksBtn.disabled = !state.delivery_weeks.length;
      clearWeeksBtn.addEventListener('click', () => {
        state.delivery_weeks = [];
        syncDeliveryWeekFilter();
        clearDashboardSummary({ preserveReport: true });
        renderActive();
      });
      const syncDeliveryWeekFilter = () => {
        const selectedWeekIds = new Set(state.delivery_weeks);
        weekList.querySelectorAll('input[type="checkbox"]').forEach(input => {
          input.checked = selectedWeekIds.has(input.value);
        });
        allWeeksBtn.disabled = state.delivery_weeks.length === weekOptions.length;
        clearWeeksBtn.disabled = !state.delivery_weeks.length;
      };
      syncDeliveryWeekFilter();
      weekActions.append(allWeeksBtn, clearWeeksBtn);
      weekBody.append(weekList, weekActions);
      weekWrap.append(weekLabel, weekBody);
      chartFiltersEl.appendChild(weekWrap);
    }
  }

  if (usesWipProfile) {
    const options = getAvailableProfilesForDashboard();
    if (!options.includes(state.profile)) state.profile = 'Todos';

    const wrap = document.createElement('div');
    wrap.className = 'chart-filter';
    const label = document.createElement('label');
    label.setAttribute('for', 'chartFilterProfile');
    label.textContent = 'Perfil';
    const select = document.createElement('select');
    select.id = 'chartFilterProfile';
    select.innerHTML = options
      .map(option => `<option value="${esc(option)}"${option === state.profile ? ' selected' : ''}>${esc(option)}</option>`)
      .join('');
    select.addEventListener('change', () => {
      state.profile = select.value;
      clearDashboardSummary({ preserveReport: true });
      renderActive();
    });
    wrap.append(label, select);
    chartFiltersEl.appendChild(wrap);
  }

  if (usesAging) {
    const viewOptions = Array.isArray(AGING_VIEW_OPTIONS) && AGING_VIEW_OPTIONS.length
      ? AGING_VIEW_OPTIONS
      : ['areas', 'categoria', 'colaborador'];
    const viewLabels = (typeof AGING_VIEW_LABELS === 'object' && AGING_VIEW_LABELS) || {
      areas: 'Área',
      categoria: 'Categoria',
      colaborador: 'Colaborador',
    };
    if (!viewOptions.includes(state.aging_view)) state.aging_view = 'areas';

    const wrap = document.createElement('div');
    wrap.className = 'chart-filter';
    const label = document.createElement('label');
    label.setAttribute('for', 'chartFilterAgingView');
    label.textContent = 'Visão';
    const select = document.createElement('select');
    select.id = 'chartFilterAgingView';
    select.innerHTML = viewOptions
      .map(option => `<option value="${esc(option)}"${option === state.aging_view ? ' selected' : ''}>${esc(viewLabels[option] || option)}</option>`)
      .join('');
    select.addEventListener('change', () => {
      state.aging_view = select.value;
      clearDashboardSummary({ preserveReport: true });
      renderActive();
    });
    wrap.append(label, select);
    chartFiltersEl.appendChild(wrap);
  }

  if (usesAgingTasks) return;
}

function buildAgingTaskFilterPanel(id = 'aging_tasks') {
  const state = getFilterState(id);
  const availableLabels = getAvailableAgingTaskLabels(id);
  const labelPalette = getAgingTaskLabelPalette(id);
  const normalizedSelected = new Set(getAgingTaskSelectedLabels(id).map(value => normalizeText(value)));
  state.aging_task_labels = availableLabels.filter(label => normalizedSelected.has(normalizeText(label)));

  const wrap = document.createElement('div');
  wrap.className = 'chart-filter chart-filter--stacked chart-side-filter';

  const label = document.createElement('label');
  label.setAttribute('for', 'chartFilterAgingTaskLabels');
  label.textContent = 'Rótulos';

  const body = document.createElement('div');
  body.className = 'chart-filter-body';

  const select = document.createElement('select');
  select.id = 'chartFilterAgingTaskLabels';
  select.multiple = true;
  select.size = Math.min(Math.max(availableLabels.length || 3, 3), 18);
  select.innerHTML = availableLabels
    .map(option => `<option value="${esc(option)}"${state.aging_task_labels.includes(option) ? ' selected' : ''}>${esc(option)}</option>`)
    .join('');
  Array.from(select.options).forEach(option => {
    const teamLabel = typeof resolveAgingTaskTeamLabel === 'function'
      ? resolveAgingTaskTeamLabel(option.value)
      : null;
    const color = teamLabel ? labelPalette.get(teamLabel) : null;
    if (!color) return;
    option.style.color = color;
    option.style.fontWeight = '700';
  });
  select.addEventListener('change', () => {
    state.aging_task_labels = Array.from(select.selectedOptions).map(option => option.value);
    state.aging_task_page = 1;
    clearDashboardSummary({ preserveReport: true });
    renderActive();
  });

  const actions = document.createElement('div');
  actions.className = 'chart-filter-actions';

  const clearBtn = document.createElement('button');
  clearBtn.type = 'button';
  clearBtn.className = 'btn-small';
  clearBtn.textContent = 'Limpar';
  clearBtn.disabled = !state.aging_task_labels.length;
  clearBtn.addEventListener('click', () => {
    state.aging_task_labels = [];
    state.aging_task_page = 1;
    clearDashboardSummary({ preserveReport: true });
    renderActive();
  });

  const hint = document.createElement('div');
  hint.className = 'chart-filter-hint';
  hint.textContent = 'Selecione um ou mais rótulos. Sem seleção, o gráfico mostra todas as tarefas abertas.';

  actions.appendChild(clearBtn);
  body.append(select, actions, hint);
  wrap.append(label, body);
  return wrap;
}

function renderAgingTaskSidebar(id = 'aging_tasks') {
  const host = document.getElementById('chartSidePanel');
  if (!host) return;
  host.innerHTML = '';
  host.appendChild(buildAgingTaskFilterPanel(id));
}

/* â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•
   RENDER
â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â• */
