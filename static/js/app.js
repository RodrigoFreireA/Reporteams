/* ════════════════════════════════════════════════════════════
   APP — Estado vazio, resize responsivo e inicialização
════════════════════════════════════════════════════════════ */
/* ════════════════════════════════════════════════════════════
   EMPTY STATE
════════════════════════════════════════════════════════════ */
function renderEmpty(body) {
  body.innerHTML = `<div class="empty-state">
    <svg width="56" height="56" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.2">
      <rect x="3" y="3" width="18" height="18" rx="2"/>
      <line x1="9" y1="9" x2="15" y2="15"/><line x1="15" y1="9" x2="9" y2="15"/>
    </svg>
    <p>Sem dados suficientes para exibir este gráfico.</p>
  </div>`;
}

/* ════════════════════════════════════════════════════════════
   RESIZE DEBOUNCE
════════════════════════════════════════════════════════════ */
let _resizeTimer;
window.addEventListener('resize', () => {
  clearTimeout(_resizeTimer);
  _resizeTimer = setTimeout(() => {
    const el = document.getElementById('mainPlot');
    if (el) Plotly.Plots.resize(el);
    if (typeof resizeReportBuilderPlots === 'function') resizeReportBuilderPlots();
    if (typeof resizeComparativePlots === 'function') resizeComparativePlots();
  }, 120);
});

/* ════════════════════════════════════════════════════════════
   INIT — aplica preferências salvas
════════════════════════════════════════════════════════════ */
(async function init() {
  const savedTheme   = localStorage.getItem('rcw-theme')   || 'dark';
  const savedPalette = localStorage.getItem('rcw-palette') || 'teal';
  document.documentElement.dataset.theme   = savedTheme;
  document.documentElement.dataset.palette = savedPalette;
  activePaletteName = savedPalette;
  buildPaletteGrid();
  resetCustomChartForm();
  resetProfileRuleForm();
  updateThemeUI();
  try {
    await refreshSession();
  } catch (err) {
    showAuthScreen(false);
    authError.textContent = 'Aviso: ' + err.message;
    authError.classList.add('visible');
  }
})();
