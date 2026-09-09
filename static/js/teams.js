/* TEAMS - equipes, membros e politica de duracao da sprint */
let teams = [];
let teamUsers = [];
let teamEditingId = null;
let selectedTeamId = null;

function teamDurationLabel(team) {
  const days = Number(team?.sprint_duration_days || 0);
  const mode = team?.sprint_mode === 'business' ? 'uteis' : 'corridos';
  return `${days} dias ${mode}`;
}

function teamCanManage(team) {
  return !!team && (isAdminUser() || ['owner', 'admin'].includes(team.current_user_role));
}

function renderUploadTeamOptions(selectedId = uploadTeamSelect?.value || '') {
  if (!uploadTeamSelect) return;
  const activeTeams = teams.filter(team => team.active);
  uploadTeamSelect.innerHTML = '<option value="">Sem equipe (relatorio legado)</option>' + activeTeams.map(team => `
    <option value="${esc(team.id)}"${String(team.id) === String(selectedId) ? ' selected' : ''}>
      ${esc(team.name)} - sprint de ${esc(teamDurationLabel(team))}
    </option>`).join('');
}

function resetTeamForm() {
  teamEditingId = null;
  teamForm?.reset();
  if (teamSprintDaysInput) teamSprintDaysInput.value = '15';
  if (teamCustomDaysInput) teamCustomDaysInput.value = '15';
  if (teamCustomDaysWrap) teamCustomDaysWrap.classList.add('hidden');
  if (teamActiveInput) teamActiveInput.checked = true;
  if (teamFormTitle) teamFormTitle.textContent = 'Nova equipe';
  if (teamFormSub) teamFormSub.textContent = 'Crie uma equipe para associar novos uploads e administrar o ciclo da sprint.';
  if (teamSubmitBtn) teamSubmitBtn.textContent = 'Criar equipe';
  teamCancelBtn?.classList.add('hidden');
  teamFormError?.classList.remove('visible');
}

function selectedTeamDuration() {
  if (teamSprintDaysInput?.value === 'custom') return Number(teamCustomDaysInput?.value || 0);
  return Number(teamSprintDaysInput?.value || 0);
}

function renderTeams() {
  if (!teamsList) return;
  teamsList.innerHTML = '';
  teamsEmpty?.classList.toggle('hidden', teams.length > 0);
  if (teamsSubtitle) {
    teamsSubtitle.textContent = teams.length
      ? `${teams.length} equipe(s) disponivel(is) para este usuario`
      : 'Crie a primeira equipe para comecar a organizar as sprints.';
  }
  teams.forEach(team => {
    const card = document.createElement('article');
    card.className = `team-card${team.active ? '' : ' is-archived'}`;
    card.innerHTML = `
      <div class="team-card-head">
        <div>
          <div class="team-card-kicker">${team.active ? 'ATIVA' : 'ARQUIVADA'}</div>
          <h3>${esc(team.name)}</h3>
        </div>
        <span class="team-duration-badge">${esc(teamDurationLabel(team))}</span>
      </div>
      <div class="team-card-project">${esc(team.project_name || 'Projeto nao informado')}</div>
      <div class="team-card-meta">
        <span>${Number(team.member_count || 0)} membro(s)</span>
        <span>${team.current_user_role ? `Seu perfil: ${esc(team.current_user_role)}` : 'Acesso administrativo'}</span>
      </div>
      <div class="team-card-actions">
        <button class="btn-small" type="button" data-team-action="members" data-team-id="${team.id}">Membros</button>
        ${teamCanManage(team) ? `<button class="btn-small" type="button" data-team-action="edit" data-team-id="${team.id}">Editar</button>` : ''}
        ${teamCanManage(team) && team.active ? `<button class="btn-small danger" type="button" data-team-action="archive" data-team-id="${team.id}">Arquivar</button>` : ''}
      </div>`;
    teamsList.appendChild(card);
  });
}

async function loadTeams() {
  if (!authState.authenticated) return;
  teamsError?.classList.remove('visible');
  try {
    const body = await apiRequest('/api/teams');
    teams = body.teams || [];
    renderTeams();
    renderReports();
    renderUploadTeamOptions();
    if (typeof buildSidebar === 'function') buildSidebar();
    if (selectedTeamId) {
      const selected = teams.find(team => Number(team.id) === Number(selectedTeamId));
      if (selected) await loadTeamMembers(selected.id);
      else teamMembersCard?.classList.add('hidden');
    }
  } catch (error) {
    if (teamsError) {
      teamsError.textContent = 'Aviso: ' + error.message;
      teamsError.classList.add('visible');
    }
  }
}

async function assignReportTeam(reportId, teamId) {
  try {
    const body = await apiRequest(`/api/reports/${reportId}/team`, {
      method: 'PATCH',
      json: { team_id: teamId || null },
      csrf: true,
    });
    upsertReport(body.report);
    renderReports();
    if (typeof buildSidebar === 'function') buildSidebar();
  } catch (error) {
    teamsError.textContent = 'Aviso: ' + error.message;
    teamsError.classList.add('visible');
    renderReports();
  }
}

async function loadTeamUsers() {
  if (teamUsers.length) return;
  const body = await apiRequest('/api/teams/users');
  teamUsers = body.users || [];
}

function openTeamsScreen({ navigateTo = true } = {}) {
  if (!authState.authenticated) {
    window.showPublicAuth?.({ navigateTo: true });
    return;
  }
  if (navigateTo) window.setAppRoute?.('/equipes');
  document.body.classList.remove('public-mode');
  window.hidePublicViews?.();
  authScreen.classList.add('hidden');
  sidebar.classList.add('hidden');
  uploadScreen.classList.add('hidden');
  adminScreen.classList.add('hidden');
  customChartScreen.classList.add('hidden');
  comparativeScreen.classList.add('hidden');
  consolidatedScreen.classList.add('hidden');
  dashboardEl.classList.remove('visible');
  teamScreen.classList.remove('hidden');
  btnUploadNew.classList.add('visible');
  sprintBadgeEl.classList.remove('visible');
  menuToggle.classList.add('hidden');
  syncTopbarState();
  closeSidebar();
  loadTeams();
}

function editTeam(teamId) {
  const team = teams.find(item => Number(item.id) === Number(teamId));
  if (!team || !teamCanManage(team)) return;
  teamEditingId = team.id;
  teamNameInput.value = team.name || '';
  teamProjectInput.value = team.project_name || '';
  teamSprintModeInput.value = team.sprint_mode || 'calendar';
  const knownDays = ['7', '10', '15', '20', '30', '60'];
  if (knownDays.includes(String(team.sprint_duration_days))) {
    teamSprintDaysInput.value = String(team.sprint_duration_days);
    teamCustomDaysWrap.classList.add('hidden');
  } else {
    teamSprintDaysInput.value = 'custom';
    teamCustomDaysInput.value = String(team.sprint_duration_days || 15);
    teamCustomDaysWrap.classList.remove('hidden');
  }
  teamActiveInput.checked = !!team.active;
  teamFormTitle.textContent = 'Editar equipe';
  teamFormSub.textContent = 'Alteracoes futuras nao reescrevem a duracao registrada nos dashboards antigos.';
  teamSubmitBtn.textContent = 'Salvar alteracoes';
  teamCancelBtn.classList.remove('hidden');
  teamFormError.classList.remove('visible');
  teamNameInput.focus();
}

async function archiveTeam(teamId) {
  const team = teams.find(item => Number(item.id) === Number(teamId));
  if (!team || !teamCanManage(team)) return;
  if (!confirm(`Arquivar a equipe ${team.name}? Relatorios antigos continuarao disponiveis.`)) return;
  try {
    await apiRequest(`/api/teams/${team.id}`, { method: 'DELETE', json: {}, csrf: true });
    if (selectedTeamId === team.id) teamMembersCard?.classList.add('hidden');
    await loadTeams();
  } catch (error) {
    teamsError.textContent = 'Aviso: ' + error.message;
    teamsError.classList.add('visible');
  }
}

async function loadTeamMembers(teamId) {
  try {
    const body = await apiRequest(`/api/teams/${teamId}`);
    const team = body.team;
    selectedTeamId = team.id;
    const canManage = teamCanManage(team);
    teamMembersCard.classList.remove('hidden');
    teamMembersTitle.textContent = `Membros — ${team.name}`;
    teamMembersSubtitle.textContent = `${team.member_count || 0} membro(s) · sprint de ${teamDurationLabel(team)}`;
    teamMemberForm.classList.toggle('hidden', !canManage);
    teamMembersError.classList.remove('visible');
    if (canManage) {
      await loadTeamUsers();
      const memberIds = new Set((team.members || []).map(member => Number(member.id)));
      teamMemberUserInput.innerHTML = '<option value="">Selecione um usuario</option>' + teamUsers
        .filter(user => !memberIds.has(Number(user.id)))
        .map(user => `<option value="${esc(user.id)}">${esc(user.display_name || user.email)} — ${esc(user.email)}</option>`)
        .join('');
    }
    teamMembersList.innerHTML = (team.members || []).map(member => `
      <div class="team-member-row">
        <div><strong>${esc(member.display_name || member.email)}</strong><span>${esc(member.email)}</span></div>
        <div class="team-member-row-actions"><span class="admin-badge">${esc(member.role)}</span>
        ${canManage && member.role !== 'owner' ? `<button class="btn-small danger" type="button" data-remove-member="${member.id}">Remover</button>` : ''}</div>
      </div>`).join('') || '<div class="team-member-empty">Nenhum membro adicional cadastrado.</div>';
  } catch (error) {
    teamMembersError.textContent = 'Aviso: ' + error.message;
    teamMembersError.classList.add('visible');
  }
}

teamSprintDaysInput?.addEventListener('change', () => {
  teamCustomDaysWrap?.classList.toggle('hidden', teamSprintDaysInput.value !== 'custom');
});

teamsList?.addEventListener('click', event => {
  const button = event.target.closest('[data-team-action]');
  if (!button) return;
  const teamId = Number(button.dataset.teamId);
  if (button.dataset.teamAction === 'edit') editTeam(teamId);
  if (button.dataset.teamAction === 'archive') archiveTeam(teamId);
  if (button.dataset.teamAction === 'members') loadTeamMembers(teamId);
});

teamMembersList?.addEventListener('click', event => {
  const button = event.target.closest('[data-remove-member]');
  if (!button || !selectedTeamId) return;
  const userId = Number(button.dataset.removeMember);
  apiRequest(`/api/teams/${selectedTeamId}/members/${userId}`, { method: 'DELETE', json: {}, csrf: true })
    .then(() => loadTeamMembers(selectedTeamId))
    .catch(error => {
      teamMembersError.textContent = 'Aviso: ' + error.message;
      teamMembersError.classList.add('visible');
    });
});

teamForm?.addEventListener('submit', async event => {
  event.preventDefault();
  teamFormError.classList.remove('visible');
  const duration = selectedTeamDuration();
  if (!duration || duration < 1 || duration > 366) {
    teamFormError.textContent = 'Informe uma duracao entre 1 e 366 dias.';
    teamFormError.classList.add('visible');
    return;
  }
  const payload = {
    name: teamNameInput.value.trim(),
    project_name: teamProjectInput.value.trim(),
    sprint_duration_days: duration,
    sprint_mode: teamSprintModeInput.value,
    active: teamActiveInput.checked,
  };
  teamSubmitBtn.disabled = true;
  try {
    const endpoint = teamEditingId ? `/api/teams/${teamEditingId}` : '/api/teams';
    await apiRequest(endpoint, {
      method: teamEditingId ? 'PATCH' : 'POST',
      json: payload,
      csrf: true,
    });
    resetTeamForm();
    await loadTeams();
  } catch (error) {
    teamFormError.textContent = 'Aviso: ' + error.message;
    teamFormError.classList.add('visible');
  } finally {
    teamSubmitBtn.disabled = false;
  }
});

teamMemberForm?.addEventListener('submit', async event => {
  event.preventDefault();
  if (!selectedTeamId || !teamMemberUserInput.value) return;
  teamMembersError.classList.remove('visible');
  try {
    await apiRequest(`/api/teams/${selectedTeamId}/members`, {
      method: 'POST',
      json: { user_id: Number(teamMemberUserInput.value), role: teamMemberRoleInput.value },
      csrf: true,
    });
    await loadTeams();
    await loadTeamMembers(selectedTeamId);
  } catch (error) {
    teamMembersError.textContent = 'Aviso: ' + error.message;
    teamMembersError.classList.add('visible');
  }
});
