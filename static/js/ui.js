/* ════════════════════════════════════════════════════════════
   UI — Tema, paleta de cores, sidebar mobile
════════════════════════════════════════════════════════════ */
/* ════════════════════════════════════════════════════════════
   PALETTE & THEME
════════════════════════════════════════════════════════════ */
function setPalette(name) {
  if (!PALETTES[name]) return;
  activePaletteName = name;
  document.documentElement.dataset.palette = name;
  localStorage.setItem('rcw-palette', name);
  updatePaletteUI();
  if (dashData) renderActive();
}

function setTheme(theme) {
  document.documentElement.dataset.theme = theme;
  localStorage.setItem('rcw-theme', theme);
  updateThemeUI();
  if (dashData) renderActive();
}

/* ── Sidebar mobile ─────────────────────────────────── */
function toggleSidebar() {
  const sb = document.getElementById('sidebar');
  const ov = document.getElementById('sidebarOverlay');
  const open = sb.classList.toggle('open');
  ov.classList.toggle('visible', open);
}
function closeSidebar() {
  document.getElementById('sidebar').classList.remove('open');
  document.getElementById('sidebarOverlay').classList.remove('visible');
}

function togglePalettePanel() {
  const panel = document.getElementById('palettePanel');
  const btn   = document.getElementById('paletteBtn');
  const isOpen = panel.classList.toggle('open');
  if (isOpen) {
    const rect = btn.getBoundingClientRect();
    const panelW = 340;
    let left = rect.right - panelW;
    if (left < 8) left = 8;
    panel.style.top  = (rect.bottom + 8) + 'px';
    panel.style.left = left + 'px';
    panel.style.right = 'auto';
  }
}

function updatePaletteUI() {
  document.querySelectorAll('.palette-item').forEach(el => {
    el.classList.toggle('active', el.dataset.palette === activePaletteName);
  });
}

function updateThemeUI() {
  const theme = document.documentElement.dataset.theme;
  document.getElementById('btnThemeDark').classList.toggle('active',  theme === 'dark');
  document.getElementById('btnThemeLight').classList.toggle('active', theme === 'light');
}

function buildPaletteGrid() {
  const grid = document.getElementById('paletteGrid');
  grid.innerHTML = '';
  Object.values(PALETTES).forEach(p => {
    const el = document.createElement('div');
    el.className = 'palette-item' + (p.id === activePaletteName ? ' active' : '');
    el.dataset.palette = p.id;
    const colors = (p.colorway || [p.c1, p.c2]).slice(0, 16);
    el.innerHTML = `
      <div class="palette-swatch">
        ${colors.map(color => `<span class="palette-color" style="background:${color}"></span>`).join('')}
      </div>
      <div class="palette-name">${p.name}</div>`;
    el.addEventListener('click', () => setPalette(p.id));
    grid.appendChild(el);
  });
}

// Close palette panel on outside click
document.addEventListener('click', e => {
  const wrap = document.getElementById('paletteBtnWrap');
  if (wrap && !wrap.contains(e.target)) {
    document.getElementById('palettePanel').classList.remove('open');
  }
});
