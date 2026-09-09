/* CHARTS - Renderização de todos os gráficos e cards KPI */
function renderActive() {
  const id   = activeChartId;
  const type = getActiveType(id);
  const body = document.getElementById('chartBody');
  body.innerHTML = id === 'aging_tasks'
    ? `
      <div class="chart-workspace chart-workspace--with-sidebar">
        <aside class="chart-side-panel" id="chartSidePanel"></aside>
        <div class="chart-plot-shell" id="chartPlotShell">
          <div class="chart-plot-wrap"><div id="mainPlot" style="width:100%;height:100%;min-height:420px"></div></div>
          <div class="chart-footer" id="chartFooter"></div>
        </div>
      </div>
    `
    : `
      <div class="chart-plot-shell" id="chartPlotShell">
        <div class="chart-plot-wrap"><div id="mainPlot" style="width:100%;height:100%;min-height:420px"></div></div>
        <div class="chart-footer" id="chartFooter"></div>
      </div>
    `;
  if (id === 'kpis')         { renderSprintKPIs(body); renderDomChartFooter(id, body); return; }
  if (id === 'flow_metrics') { renderFlowMetrics(body); renderDomChartFooter(id, body); return; }
  if (id === 'scope_quality') { renderScopeQualityMetrics(body); renderDomChartFooter(id, body); return; }
  if (id === 'time_health')  { renderTimeHealthMetrics(body); renderDomChartFooter(id, body); return; }
  if (id === 'roadmap')      { renderRoadmapReport(body); return; }
  if (id === 'rotulos')      { renderTimingTable('rotulos',      body, type); return; }
  if (id === 'responsaveis') { renderTimingTable('responsaveis', body, type); return; }
  const { traces, layout } = buildChart(id, type);
  if (!traces) { renderEmpty(body); return; }
  Plotly.react('mainPlot', traces, layout, { responsive:true, displayModeBar:false });
  if (id === 'aging_tasks' && typeof renderAgingTaskSidebar === 'function') renderAgingTaskSidebar(id);
  renderChartFooter(id);
}
function isDark() { return document.documentElement.dataset.theme === 'dark'; }

function plotLayout(extra = {}) {
  const dark = isDark();
  const cw   = PALETTES[activePaletteName]?.colorway || PALETTES.teal.colorway;
  const {
    xaxis: extraXaxis = {},
    yaxis: extraYaxis = {},
    legend: extraLegend = {},
    margin: extraMargin = {},
    ...rest
  } = extra;
  return {
    paper_bgcolor: 'transparent',
    plot_bgcolor:  'transparent',
    font: { family:"'Segoe UI',system-ui,Arial", color: dark ? '#c8d0e0' : '#3a4a60', size:12 },
    margin: { t:30, r:20, b:50, l:60, ...extraMargin },
    legend: { bgcolor:'transparent', font:{ size:11 }, ...extraLegend },
    colorway: cw,
    xaxis: {
      gridcolor:    dark ? '#2a3350' : '#e0e8f0',
      zerolinecolor:dark ? '#33405a' : '#ccd5e0',
      tickfont:{ size:11 }, ...extraXaxis,
    },
    yaxis: {
      gridcolor:    dark ? '#2a3350' : '#e0e8f0',
      zerolinecolor:dark ? '#33405a' : '#ccd5e0',
      tickfont:{ size:11 }, ...extraYaxis,
    },
    ...rest,
  };
}

function cleanChartLabel(value) {
  return String(value ?? '').replace(/\s+/g, ' ').trim();
}

function splitProtectedLabelSuffix(value) {
  const text = cleanChartLabel(value);
  const protectedToken = String.raw`(?:\[[^\]]+\]|\(\s*\d+(?:\s*\/\s*\d+)?\s*\))`;
  const match = text.match(new RegExp(`(\\s*(?:${protectedToken}\\s*)+(?:[,;]\\s*[^,;]+)?)$`));
  if (!match) return { base: text, suffix: '' };
  return {
    base: text.slice(0, match.index).trim(),
    suffix: match[1].trim(),
  };
}

function takeLabelPrefix(value, maxLength) {
  const text = cleanChartLabel(value);
  if (text.length <= maxLength) return text;
  const wordCut = text.slice(0, maxLength + 1).replace(/\s+\S*$/, '').trim();
  const cut = wordCut.length >= Math.min(10, maxLength) ? wordCut : text.slice(0, maxLength).trim();
  return cut.replace(/[,\-:;./\\]+$/, '').trim();
}

function shortenChartLabel(value, maxLength = 30) {
  const text = cleanChartLabel(value);
  if (text.length <= maxLength) return text;

  const marker = '(...)';
  const { base, suffix } = splitProtectedLabelSuffix(text);
  const suffixText = suffix ? ` ${suffix}` : '';
  const source = base || text;
  const prefixLimit = Math.max(10, maxLength - marker.length - suffixText.length - 1);
  const prefix = takeLabelPrefix(source, prefixLimit);
  return `${prefix} ${marker}${suffixText}`.replace(/\s+/g, ' ').trim();
}

function labelAxis(labels, maxLength = 30) {
  return {
    tickmode: 'array',
    tickvals: labels,
    ticktext: labels.map(label => shortenChartLabel(label, maxLength)),
    tickfont: { size: 10 },
    automargin: true,
  };
}

function labelHoverData(labels) {
  return labels.map(label => esc(cleanChartLabel(label)));
}

/* â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•
   CHART BUILDERS
â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â• */
function buildChart(id, type) {
  const d = dashData;
  const customChart = getCustomChartByChartId(id);
  if (customChart) return buildCustomChart(customChart, type);
  switch(id) {
    case 'delivery_person': return chartPersonDelivery(type);
    case 'burndown':    return chartBurndown(d.burndown?.rows, type, 'Meta','Planejado','A Realizar', {
      scopeEvents: d.burndown?.scope_events,
      scopeUnit: 'tarefas',
      scopeValueKey: 'count',
    });
    case 'burndown_hu': return chartBurndown(d.burndown_hu?.rows, type, 'Meta','Planejado','A Realizar', {
      scopeEvents: d.burndown_hu?.scope_events,
      scopeUnit: 'tarefas',
      scopeValueKey: 'weight',
    });
    case 'burndown_sp': return chartBurndownSP(d.burndown_sp, type);
    case 'burnup':      return chartBurnup(d.burndown?.rows, type, {
      yTitle: 'Tarefas',
      scopeEvents: d.burndown?.scope_events,
      scopeUnit: 'tarefas',
      scopeValueKey: 'count',
    });
    case 'burnup_hu':   return chartBurnup(d.burndown_hu?.rows, type, {
      yTitle: 'Tarefas',
      scopeEvents: d.burndown_hu?.scope_events,
      scopeUnit: 'tarefas',
      scopeValueKey: 'weight',
    });
    case 'burnup_sp':   return chartBurnup(d.burndown_sp?.rows, type, {
      yTitle: `SP (total: ${d.burndown_sp?.total_sp || 0})`,
      remainingIndex: 2,
      scopeIndex: 3,
      planIndex: -1,
      metaOriginalIndex: 4,
      addedIndex: 5,
      fallbackTotal: d.burndown_sp?.total_sp || 0,
      scopeEvents: d.burndown_sp?.scope_events,
      scopeUnit: 'SP',
      scopeValueKey: 'sp',
    });
    case 'burndown_nao_prev': return chartBurndown(d.burndown_nao_prev?.rows, type, 'Meta','Planejado','A Realizar', {
      scopeEvents: d.burndown_nao_prev?.scope_events,
      scopeUnit: 'tarefas',
      scopeValueKey: 'count',
    });
    case 'burnup_nao_prev': return chartBurnup(d.burndown_nao_prev?.rows, type, {
      yTitle: 'Tarefas n\u00e3o previstas',
      scopeEvents: d.burndown_nao_prev?.scope_events,
      scopeUnit: 'tarefas',
      scopeValueKey: 'count',
    });
    case 'burndown_nao_prev_hu': return chartBurndown(d.burndown_nao_prev_hu?.rows, type, 'Meta','Planejado','A Realizar', {
      scopeEvents: d.burndown_nao_prev_hu?.scope_events,
      scopeUnit: 'tarefas',
      scopeValueKey: 'count',
    });
    case 'burnup_nao_prev_hu': return chartBurnup(d.burndown_nao_prev_hu?.rows, type, {
      yTitle: 'Tarefas n\u00e3o previstas em HU',
      scopeEvents: d.burndown_nao_prev_hu?.scope_events,
      scopeUnit: 'tarefas',
      scopeValueKey: 'count',
    });
    case 'cfd':         return chartCFD(d.cfd, type);
    case 'wip':         return d.task_rows?.length
      ? chartWipProfile({ chart_id:'wip', source_key:'wip_profile' }, type)
      : chartWIP(d.wip, type);
    case 'hu_tasks':    return chartGrouped(d.hu_list?.map(r => {
      // hu_list is [id, total, done]. Normalize it to [label, done, pending].
      const total = Math.max(Number(r?.[1]) || 0, 0);
      const done = Math.min(Math.max(Number(r?.[2]) || 0, 0), total);
      return [d.hu_full_names?.[r[0]] || r[0], done, total - done];
    }), type, 'Conclu\u00eddas','Pendentes');
    case 'areas':       return chartGrouped(d.area_rows,   type, 'Concluídas','Pendentes');
    case 'categoria':   return chartGrouped(d.cat_rows,    type, 'Concluídas','Pendentes');
    case 'colaborador': return chartGrouped(d.collab_rows, type, 'Concluídas','Pendentes');
    case 'hu_inout':    return chartInOut(d.in_out, type);
    case 'dispersao':   return chartDispersao(d, type);
    case 'aging':       return chartAging('aging', type);
    case 'aging_tasks': return chartAgingTasks('aging_tasks', type);
    case 'histograma':  return chartHistograma(d.hist_31, d.indicativos, type);
    default: return { traces: null };
  }
}


function parseRoadmapReportItem(item) {
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

function roadmapMonthYear(dateText) {
  const match = String(dateText || '').match(/^(\d{2})\/(\d{2})\/(\d{4})/);
  if (!match) return { month: dateText || '--', year: '' };
  const monthNames = ['JAN','FEV','MAR','ABR','MAI','JUN','JUL','AGO','SET','OUT','NOV','DEZ'];
  return { month: monthNames[Number(match[2]) - 1] || match[2], year: match[3] };
}

function roadmapDateValue(dateText) {
  const match = String(dateText || '').match(/^(\d{2})\/(\d{2})\/(\d{4})/);
  if (!match) return null;
  const parsed = new Date(Number(match[3]), Number(match[2]) - 1, Number(match[1]));
  const time = parsed.getTime();
  return Number.isNaN(time) ? null : time;
}

function orderRoadmapItems(items) {
  return items
    .map((item, index) => ({ ...item, _order: index, _time: roadmapDateValue(item.date) }))
    .sort((a, b) => {
      if (a._time !== null && b._time !== null && a._time !== b._time) return a._time - b._time;
      if (a._time !== null && b._time === null) return -1;
      if (a._time === null && b._time !== null) return 1;
      return a._order - b._order;
    });
}

function roadmapMoreTrigger(text, label) {
  const value = String(text || '').trim();
  if (!value) return '';
  return `<span class="roadmap-more">
    <button class="roadmap-more-trigger" type="button" aria-label="Ver ${esc(label)} completo">i</button>
    <span class="roadmap-more-tooltip" role="tooltip"><b>${esc(label)}</b><span>${esc(value)}</span></span>
  </span>`;
}

function roadmapTimelineText(value, { className, limit, label }) {
  const text = String(value || '').trim();
  const display = text || '-';
  const hasMore = text.length > limit;
  return `<div class="${className}${hasMore ? ' has-more' : ''}">
    <span class="roadmap-clamp">${esc(display)}</span>
    ${hasMore ? roadmapMoreTrigger(text, label) : ''}
  </div>`;
}

function renderRoadmapTimeline(items, options = {}) {
  const showHead = options.showHead !== false;
  const allowFullscreen = options.allowFullscreen === true;
  const panelClass = ['roadmap-timeline-panel', options.className || ''].filter(Boolean).join(' ');
  const phaseSize = 11;
  const rowSize = phaseSize;
  const phases = [];
  for (let index = 0; index < items.length; index += phaseSize) phases.push(items.slice(index, index + phaseSize));
  const renderPhase = (phaseItems, phaseIndex) => {
    const rows = [];
    for (let index = 0; index < phaseItems.length; index += rowSize) rows.push(phaseItems.slice(index, index + rowSize));
    const renderRow = (rowItems, rowIndex) => {
      const rowOffset = rowIndex * rowSize;
      const trackWidth = Math.max(960, rowItems.length * 210);
      const yearBands = [];
      rowItems.forEach((item, index) => {
        const year = String(item.date || '').match(/\d{4}/)?.[0] || '--';
        const previous = yearBands[yearBands.length - 1];
        if (previous?.year === year) previous.span += 1;
        else yearBands.push({ year, start: index + 1, span: 1 });
      });
      return `
        <div class="roadmap-timeline-scroll roadmap-timeline-scroll--row">
          <div class="roadmap-timeline-years" style="--roadmap-items:${rowItems.length}">
            ${yearBands.map(band => `<span style="grid-column:${band.start} / span ${band.span}">${esc(band.year)}</span>`).join('')}
          </div>
          <div class="roadmap-timeline-track" style="--roadmap-items:${rowItems.length};--roadmap-track-width:${trackWidth}px">
            <div class="roadmap-timeline-axis" aria-hidden="true"></div>
            ${rowItems.map((item, index) => {
              const label = roadmapMonthYear(item.date);
              const absoluteIndex = rowOffset + index;
              const laneClass = 'is-top';
              const colorIndex = Number.isFinite(item._timelineIndex) ? item._timelineIndex : phaseIndex * phaseSize + absoluteIndex;
              return `<article class="roadmap-timeline-event ${laneClass}" style="--roadmap-color:${pc(colorIndex)};grid-column:${index + 1}">
                <div class="roadmap-timeline-dot" aria-hidden="true"></div>
                <div class="roadmap-timeline-card">
                  <div class="roadmap-timeline-date">
                    <strong>${esc(item.date || '--')}</strong>
                    <span>${esc(label.month)} ${esc(label.year)}</span>
                  </div>
                  ${roadmapTimelineText(item.goal, { className: 'roadmap-timeline-goal', limit: Number.MAX_SAFE_INTEGER, label: 'Goal' })}
                  ${roadmapTimelineText(item.marco, { className: 'roadmap-timeline-text', limit: Number.MAX_SAFE_INTEGER, label: 'Marco' })}
                </div>
              </article>`;
            }).join('')}
          </div>
        </div>`;
    };
    return `
      <section class="roadmap-timeline-phase">
        <div class="roadmap-timeline-phase-head"><span>Faixa ${phaseIndex + 1}</span><strong>${esc(phaseItems[0]?.date || '--')} - ${esc(phaseItems[phaseItems.length - 1]?.date || '--')}</strong></div>
        ${rows.map(renderRow).join('')}
      </section>`;
  };
  return `
    <section class="${panelClass}">
      ${showHead ? `<div class="roadmap-section-head">
        <div>
          <span>Visao unica</span>
          <strong>Linha do tempo</strong>
        </div>
        <div class="roadmap-section-actions">
          <small>${items.length} marco${items.length === 1 ? '' : 's'}</small>
          ${allowFullscreen ? `<button class="roadmap-fullscreen-btn" type="button" onclick="openRoadmapTimelineFullscreen()">Tela cheia</button>` : ''}
        </div>
      </div>` : ''}
      ${phases.map(renderPhase).join('')}
    </section>
  `;
}

function enableRoadmapTimelineDrag(root = document) {
  root.querySelectorAll('.roadmap-timeline-scroll').forEach(scrollEl => {
    if (scrollEl.dataset.dragScrollReady === '1') return;
    scrollEl.dataset.dragScrollReady = '1';

    let isDown = false;
    let didDrag = false;
    let startX = 0;
    let startScrollLeft = 0;

    scrollEl.addEventListener('pointerdown', event => {
      if (event.pointerType === 'mouse' && event.button !== 0) return;
      if (event.target.closest('button,a,input,textarea,select')) return;
      isDown = true;
      didDrag = false;
      startX = event.clientX;
      startScrollLeft = scrollEl.scrollLeft;
      scrollEl.classList.add('is-dragging');
      scrollEl.setPointerCapture?.(event.pointerId);
    });

    scrollEl.addEventListener('pointermove', event => {
      if (!isDown) return;
      const delta = event.clientX - startX;
      if (Math.abs(delta) > 3) didDrag = true;
      scrollEl.scrollLeft = startScrollLeft - delta;
      if (didDrag) event.preventDefault();
    });

    const stopDrag = event => {
      if (!isDown) return;
      isDown = false;
      scrollEl.classList.remove('is-dragging');
      scrollEl.releasePointerCapture?.(event.pointerId);
    };

    scrollEl.addEventListener('pointerup', stopDrag);
    scrollEl.addEventListener('pointercancel', stopDrag);
    scrollEl.addEventListener('lostpointercapture', stopDrag);
    scrollEl.addEventListener('click', event => {
      if (!didDrag) return;
      event.preventDefault();
      event.stopPropagation();
      didDrag = false;
    }, true);
  });
}

function currentRoadmapItems() {
  return orderRoadmapItems(
    (dashData?.roadmap_items || []).map(parseRoadmapReportItem).filter(item => item.raw)
  );
}

function roadmapPrintShortDate(dateText) {
  const match = String(dateText || '').match(/^(\d{2})\/(\d{2})\/(\d{4})/);
  if (!match) return dateText || '--';
  return `${match[1]}/${match[2]}/${match[3].slice(-2)}`;
}

function roadmapPrintEventPosition(index, count) {
  const left = 74;
  const right = 1048;
  if (count <= 1) return (left + right) / 2;
  return left + ((right - left) * (index / (count - 1)));
}

function roadmapStandalonePrintPage(items, pageIndex, totalPages, period) {
  const projectName = dashData?.meta?.projeto || dashData?.meta?.sprint_name || 'Roadmap';
  const lanes = [
    { textTop: 126, stemTop: 270, stemHeight: 112, textWidth: 172 },
    { textTop: 432, stemTop: 382, stemHeight: 52, textWidth: 172 },
    { textTop: 212, stemTop: 304, stemHeight: 78, textWidth: 172 },
    { textTop: 518, stemTop: 382, stemHeight: 132, textWidth: 172 },
    { textTop: 294, stemTop: 330, stemHeight: 52, textWidth: 172 },
    { textTop: 614, stemTop: 382, stemHeight: 222, textWidth: 172 },
  ];
  return `
    <section class="roadmap-fullscreen-print-page">
      <div class="roadmap-standalone-sheet">
        <div class="roadmap-standalone-title">Roadmap de Projeto - ${esc(projectName)}</div>
        <div class="roadmap-standalone-period">${esc(period)}${totalPages > 1 ? ` · Parte ${pageIndex + 1}/${totalPages}` : ''}</div>
        <div class="roadmap-standalone-frame" aria-hidden="true"></div>
        <div class="roadmap-standalone-axis" aria-hidden="true"></div>
        <div class="roadmap-standalone-start" aria-hidden="true"></div>
        <div class="roadmap-standalone-end" aria-hidden="true"></div>
        ${items.map((item, index) => {
          const originalIndex = Number.isFinite(item._timelineIndex) ? item._timelineIndex : index;
          const lane = lanes[index % lanes.length];
          const x = roadmapPrintEventPosition(index, items.length).toFixed(2);
          const label = roadmapMonthYear(item.date);
          const color = pc(originalIndex);
          return `
            <div class="roadmap-standalone-stem" style="--roadmap-x:${x}px;--roadmap-color:${color};--stem-top:${lane.stemTop}px;--stem-height:${lane.stemHeight}px"></div>
            <div class="roadmap-standalone-marker" style="--roadmap-x:${x}px;--roadmap-color:${color}"></div>
            <div class="roadmap-standalone-tick" style="--roadmap-x:${x}px">${esc(roadmapPrintShortDate(item.date))}</div>
            <article class="roadmap-standalone-event" style="--roadmap-x:${x}px;--event-top:${lane.textTop}px;--event-width:${lane.textWidth}px">
              <strong>${esc(item.date || '--')} <span>${esc(label.month)} ${esc(label.year)}</span></strong>
              ${item.goal ? `<p>${esc(item.goal)}</p>` : ''}
              ${item.marco ? `<p>${esc(item.marco)}</p>` : ''}
            </article>
          `;
        }).join('')}
      </div>
    </section>
  `;
}

function roadmapTimelinePrintPages(items) {
  const pageSize = 12;
  const totalPages = Math.ceil(items.length / pageSize) || 1;
  const period = items.length ? `${items[0].date || '--'} - ${items[items.length - 1].date || '--'}` : '--';
  const pages = [];
  for (let pageIndex = 0; pageIndex < totalPages; pageIndex += 1) {
    const start = pageIndex * pageSize;
    const chunk = items.slice(start, start + pageSize).map((item, offset) => ({ ...item, _timelineIndex: start + offset }));
    pages.push(roadmapStandalonePrintPage(chunk, pageIndex, totalPages, period));
  }
  return pages.join('');
}

function openRoadmapTimelineFullscreen() {
  const items = currentRoadmapItems();
  if (!items.length) return;
  const period = `${items[0].date || '--'} - ${items[items.length - 1].date || '--'}`;
  const projectName = dashData?.meta?.projeto || dashData?.meta?.sprint_name || 'Roadmap';
  let modal = document.getElementById('roadmapFullscreenModal');
  if (!modal) {
    modal = document.createElement('div');
    modal.id = 'roadmapFullscreenModal';
    document.body.appendChild(modal);
  }
  modal.className = 'roadmap-fullscreen-modal';
  modal.innerHTML = `
    <div class="roadmap-fullscreen-shell" role="dialog" aria-modal="true" aria-label="Linha do tempo do roadmap em tela cheia">
      <header class="roadmap-fullscreen-toolbar">
        <div>
          <span>Roadmap de Projeto</span>
          <strong>${esc(projectName)}</strong>
          <small>${esc(period)}</small>
        </div>
        <div class="roadmap-fullscreen-actions">
          <button class="btn-small" type="button" onclick="printRoadmapTimelineFullscreen()">Imprimir</button>
          <button class="btn-small" type="button" onclick="closeRoadmapTimelineFullscreen()">Fechar</button>
        </div>
      </header>
      <main class="roadmap-fullscreen-content">
        <div class="roadmap-fullscreen-screen">
          ${renderRoadmapTimeline(items, { showHead:false, className:'roadmap-timeline-panel--fullscreen' })}
        </div>
        <div class="roadmap-fullscreen-print-pages">
          ${roadmapTimelinePrintPages(items)}
        </div>
      </main>
    </div>
  `;
  modal.classList.add('visible');
  document.body.classList.add('roadmap-fullscreen-open');
  enableRoadmapTimelineDrag(modal);
}

function closeRoadmapTimelineFullscreen() {
  const modal = document.getElementById('roadmapFullscreenModal');
  if (modal) modal.classList.remove('visible');
  document.body.classList.remove('roadmap-fullscreen-open', 'roadmap-fullscreen-printing');
}

function applyRoadmapFullscreenPrintPageStyle() {
  let styleEl = document.getElementById('roadmapFullscreenPrintPageStyle');
  if (!styleEl) {
    styleEl = document.createElement('style');
    styleEl.id = 'roadmapFullscreenPrintPageStyle';
    document.head.appendChild(styleEl);
  }
  styleEl.textContent = '@page{size:A4 landscape;margin:0}';
}

function printRoadmapTimelineFullscreen() {
  applyRoadmapFullscreenPrintPageStyle();
  document.body.classList.add('roadmap-fullscreen-printing');
  setTimeout(() => window.print(), 80);
}

window.addEventListener('afterprint', () => {
  document.body.classList.remove('roadmap-fullscreen-printing');
});

window.addEventListener('keydown', event => {
  if (event.key === 'Escape' && document.body.classList.contains('roadmap-fullscreen-open')) {
    closeRoadmapTimelineFullscreen();
  }
});

function renderRoadmapReport(body) {
  const items = currentRoadmapItems();
  if (!items.length) { renderEmpty(body); return; }
  const period = `${items[0].date || '--'} - ${items[items.length - 1].date || '--'}`;
  body.innerHTML = `
    <div class="roadmap-report">
      <div class="roadmap-report-head">
        <div>
          <div class="roadmap-report-eyebrow">Roadmap de Projeto</div>
          <div class="roadmap-report-title">${esc(dashData?.meta?.projeto || dashData?.meta?.sprint_name || 'Roadmap')}</div>
        </div>
        <div class="roadmap-report-period">${esc(period)}</div>
      </div>
      <div class="roadmap-report-legend"><span></span>Goal <span></span>Marco</div>
      <section class="roadmap-export-section roadmap-export-section--timeline">
        ${renderRoadmapTimeline(items, { allowFullscreen:true })}
        <div class="roadmap-export-actions" data-roadmap-export="timeline"></div>
      </section>
      <section class="roadmap-export-section roadmap-export-section--cards">
        <div class="roadmap-section-head roadmap-section-head--cards">
          <div>
            <span>Detalhamento</span>
            <strong>Cards por marco</strong>
          </div>
        </div>
        <div class="roadmap-report-grid">
          ${items.map((item, index) => {
            const label = roadmapMonthYear(item.date);
            return `<section class="roadmap-report-item" style="--roadmap-color:${pc(index)}">
              <div class="roadmap-report-date"><strong>${esc(label.month)}</strong><span>${esc(label.year)}</span></div>
              <div class="roadmap-report-block"><b>Goal</b><p>${esc(item.goal || '-')}</p></div>
              <div class="roadmap-report-block roadmap-report-block--milestone"><b>Marco</b><p>${esc(item.marco || '-')}</p></div>
            </section>`;
          }).join('')}
        </div>
        <div class="roadmap-export-actions" data-roadmap-export="cards"></div>
      </section>
    </div>
  `;
  enableRoadmapTimelineDrag(body);
  const timelineSection = body.querySelector('.roadmap-export-section--timeline');
  const cardsSection = body.querySelector('.roadmap-export-section--cards');
  const addExportButton = (slot, section, label) => {
    if (!slot || !section) return;
    slot.appendChild(createChartPngButton(() => section, label, { forceDom:true }));
  };
  addExportButton(timelineSection?.querySelector('[data-roadmap-export="timeline"]'), timelineSection, `${chartPngExportName('roadmap')} - Linha do tempo`);
  addExportButton(cardsSection?.querySelector('[data-roadmap-export="cards"]'), cardsSection, `${chartPngExportName('roadmap')} - Cards`);
}

function metricLabelForCustomChart(chart) {
  return CUSTOM_CHART_SOURCES[chart.source_key]?.metrics?.[chart.metric_key] || 'Valor';
}

function getCustomChartRows(chart) {
  if (!dashData || !chart) return [];

  const metric = chart.metric_key;
  let rows = [];
  switch (chart.source_key) {
    case 'hu_tasks':
      rows = (dashData.hu_list || []).map(r => {
        const label = dashData.hu_full_names?.[r[0]] || r[0];
        const done = Number(r[1] || 0);
        const pending = Number(r[2] || 0);
        const value = metric === 'done' ? done : metric === 'pending' ? pending : done + pending;
        return [label, value];
      });
      break;
    case 'areas':
      rows = (dashData.area_rows || []).map(r => [r[0], metric === 'done' ? Number(r[1] || 0) : metric === 'pending' ? Number(r[2] || 0) : Number(r[1] || 0) + Number(r[2] || 0)]);
      break;
    case 'categoria':
      rows = (dashData.cat_rows || []).map(r => [r[0], metric === 'done' ? Number(r[1] || 0) : metric === 'pending' ? Number(r[2] || 0) : Number(r[1] || 0) + Number(r[2] || 0)]);
      break;
    case 'colaborador':
      rows = (dashData.collab_rows || []).map(r => [r[0], metric === 'done' ? Number(r[1] || 0) : metric === 'pending' ? Number(r[2] || 0) : Number(r[1] || 0) + Number(r[2] || 0)]);
      break;
    case 'hu_inout':
      rows = (dashData.in_out || []).map(r => [r[0], Number(r[1] || 0)]);
      break;
    case 'rotulos':
      rows = (dashData.rotulos_rows || []).map(r => {
        const value = metric === 'done' ? Number(r[1] || 0)
          : metric === 'pending' ? Number(r[2] || 0)
          : metric === 'lead_time' ? Number(r[3] || 0)
          : Number(r[4] || 0);
        return [r[0], value];
      });
      break;
    case 'responsaveis':
      rows = (dashData.resp_rows || []).map(r => {
        const value = metric === 'done' ? Number(r[1] || 0)
          : metric === 'pending' ? Number(r[2] || 0)
          : metric === 'lead_time' ? Number(r[3] || 0)
          : Number(r[4] || 0);
        return [r[0], value];
      });
      break;
    case 'aging_tasks':
      rows = buildAgingTaskRows(chart.chart_id || 'aging_tasks').map(row => [row.title, Number(row.ageDays || 0)]);
      break;
    case 'histograma':
      rows = (dashData.hist_31 || []).map((value, index) => [`${index + 1} dia${index + 1 === 1 ? '' : '(s)'}`, Number(value || 0)]);
      break;
    case 'wip_profile':
      rows = [];
      break;
    default:
      rows = [];
  }

  rows = rows
    .filter(row => row && row[0] !== null && row[0] !== undefined && Number.isFinite(Number(row[1])))
    .map(row => [String(row[0]), Number(row[1])]);

  if (chart.source_key !== 'histograma') {
    rows = rows.filter(row => row[1] > 0);
  }

  const sorter = chart.sort_mode || 'metric_desc';
  rows.sort((a, b) => {
    if (sorter === 'metric_asc') return a[1] - b[1] || a[0].localeCompare(b[0]);
    if (sorter === 'label_asc') return a[0].localeCompare(b[0], 'pt-BR');
    if (sorter === 'label_desc') return b[0].localeCompare(a[0], 'pt-BR');
    return b[1] - a[1] || a[0].localeCompare(b[0], 'pt-BR');
  });

  const limit = Number(chart.limit || 0);
  if (limit > 0) rows = rows.slice(0, limit);

  if (chart.source_key === 'histograma' && chart.sort_mode?.startsWith('label')) {
    rows.sort((a, b) => parseInt(a[0], 10) - parseInt(b[0], 10));
  }

  return rows;
}

function buildWipProfileData(chart) {
  if (!dashData?.task_rows?.length || !dashData?.wip?.dates?.length) return null;

  const filterState = getFilterState(chart.chart_id);
  const selectedProfile = filterState.profile || 'Todos';
  const dates = dashData.wip.dates || [];
  const cutoff = dashData.meta?.export_date || dates[dates.length - 1] || null;
  const tasks = (dashData.task_rows || []).filter(task => {
    const profileName = taskProfileName(task);
    return selectedProfile === 'Todos' || profileName === selectedProfile;
  });
  if (!tasks.length) return null;

  const series = {
    Backlog: [],
    'Em Produção': [],
    'Concluído': [],
  };
  let lastState = { Backlog: 0, 'Em Produção': 0, 'Concluído': 0 };

  dates.forEach(dateStr => {
    if (cutoff && dateStr > cutoff) {
      series.Backlog.push(lastState.Backlog);
      series['Em Produção'].push(lastState['Em Produção']);
      series['Concluído'].push(lastState['Concluído']);
      return;
    }

    const counts = { Backlog: 0, 'Em Produção': 0, 'Concluído': 0 };
    tasks.forEach(task => {
      const doneDate = task.wip_done_date || task.date_done || task.date_due || null;
      const startDate = task.date_start || null;
      if (doneDate && doneDate <= dateStr) {
        counts['Concluído'] += 1;
        return;
      }
      if (startDate && startDate <= dateStr && (!doneDate || dateStr < doneDate)) {
        counts['Em Produção'] += 1;
        return;
      }
      if (task.is_backlog && (!startDate || startDate > dateStr) && (!doneDate || dateStr < doneDate)) {
        counts.Backlog += 1;
      }
    });

    series.Backlog.push(counts.Backlog);
    series['Em Produção'].push(counts['Em Produção']);
    series['Concluído'].push(counts['Concluído']);
    lastState = counts;
  });

  return { dates, series, selectedProfile };
}

const AGING_VIEW_OPTIONS = ['areas', 'categoria', 'colaborador'];
const AGING_VIEW_LABELS = {
  areas: 'Área',
  categoria: 'Categoria',
  colaborador: 'Colaborador',
};
const AGING_TASKS_PAGE_SIZE = 20;
const AGING_TASK_TEAM_LABELS = ['.ARQUITETURA', '.DEV', '.GP', '.Q/A TESTES', '.UX'];
const AGING_TASK_TEAM_ALIAS = {
  arquitetura: '.ARQUITETURA',
  dev: '.DEV',
  gp: '.GP',
  ux: '.UX',
  'q/a testes': '.Q/A TESTES',
  'qa testes': '.Q/A TESTES',
  'q a testes': '.Q/A TESTES',
  'q-a testes': '.Q/A TESTES',
};

function collectTaskLabels(task) {
  const unique = new Map();
  String(task?.labels || '')
    .split(';')
    .map(token => token.trim())
    .filter(Boolean)
    .forEach(label => {
      const key = normalizeText(label);
      if (!key || unique.has(key)) return;
      unique.set(key, label);
    });
  return Array.from(unique.entries()).map(([key, label]) => ({ key, label }));
}

function resolveAgingTaskTeamLabel(label) {
  const normalized = normalizeText(String(label || '').replace(/^\./, '').trim());
  if (!normalized) return null;
  return AGING_TASK_TEAM_ALIAS[normalized] || null;
}

function pickAgingTaskTeamLabel(taskLabels, selectedTeams = []) {
  const orderedTaskTeams = [];
  const seenTeams = new Set();

  taskLabels.forEach(item => {
    const teamLabel = resolveAgingTaskTeamLabel(item.label);
    if (!teamLabel || seenTeams.has(teamLabel)) return;
    seenTeams.add(teamLabel);
    orderedTaskTeams.push(teamLabel);
  });

  if (!orderedTaskTeams.length) return null;

  const selectedSet = new Set(selectedTeams.filter(Boolean));
  if (!selectedSet.size) return orderedTaskTeams[0];

  const insideSelection = orderedTaskTeams.filter(team => selectedSet.has(team));
  const outsideSelection = orderedTaskTeams.filter(team => !selectedSet.has(team));

  // Se a tarefa é compartilhada entre equipe selecionada e outra,
  // destaca a "outra" para evidenciar o compartilhamento.
  if (insideSelection.length && outsideSelection.length) return outsideSelection[0];
  if (insideSelection.length) return insideSelection[0];
  return orderedTaskTeams[0];
}

function parseIsoDate(value) {
  const raw = String(value ?? '').trim();
  const match = raw.match(/^(\d{4})-(\d{2})-(\d{2})$/);
  if (!match) return null;
  const parsed = new Date(Number(match[1]), Number(match[2]) - 1, Number(match[3]));
  return Number.isNaN(parsed.getTime()) ? null : parsed;
}

function getAgingReferenceDate() {
  const now = new Date();
  const today = new Date(now.getFullYear(), now.getMonth(), now.getDate());
  const sprintEnd = parseIsoDate(dashData?.meta?.sprint_end);
  if (sprintEnd && today > sprintEnd) return sprintEnd;
  return today;
}

function daysBetweenDates(start, end) {
  if (!start || !end) return null;
  const a = new Date(start.getFullYear(), start.getMonth(), start.getDate());
  const b = new Date(end.getFullYear(), end.getMonth(), end.getDate());
  return Math.round((b - a) / 86400000);
}

function addLocalDays(value, days) {
  const next = new Date(value.getFullYear(), value.getMonth(), value.getDate());
  next.setDate(next.getDate() + days);
  return next;
}

function dateKeyLocal(value) {
  const y = value.getFullYear();
  const m = String(value.getMonth() + 1).padStart(2, '0');
  const d = String(value.getDate()).padStart(2, '0');
  return `${y}-${m}-${d}`;
}

function formatDateOnlyPt(value) {
  const parsed = typeof value === 'string' ? parseIsoDate(value) : value;
  return parsed ? parsed.toLocaleDateString('pt-BR') : '-';
}

function formatDateDayMonthPt(value) {
  const parsed = typeof value === 'string' ? parseIsoDate(value) : value;
  if (!parsed) return '-';
  const day = String(parsed.getDate()).padStart(2, '0');
  const month = String(parsed.getMonth() + 1).padStart(2, '0');
  return `${day}/${month}`;
}

function buildDailyDateKeysBetween(startKey, endKey) {
  const start = parseIsoDate(startKey);
  const end = parseIsoDate(endKey);
  if (!start || !end) return [];
  const dates = [];
  const [from, to] = start <= end ? [start, end] : [end, start];
  for (let day = from; day <= to; day = addLocalDays(day, 1)) {
    dates.push(dateKeyLocal(day));
  }
  return dates;
}

function isBusinessDateLocal(value) {
  const weekday = value.getDay();
  if (weekday === 0 || weekday === 6) return false;
  const holidays = typeof brNationalHolidayKeys === 'function'
    ? brNationalHolidayKeys(value.getFullYear())
    : new Set();
  return !holidays.has(dateKeyLocal(value));
}

function previousBusinessDateLocal(value) {
  let current = new Date(value.getFullYear(), value.getMonth(), value.getDate());
  while (!isBusinessDateLocal(current)) current = addLocalDays(current, -1);
  return current;
}

function businessDaysBetweenLocal(start, endExclusive) {
  if (!start || !endExclusive) return 0;
  let count = 0;
  for (let day = new Date(start.getFullYear(), start.getMonth(), start.getDate()); day < endExclusive; day = addLocalDays(day, 1)) {
    if (isBusinessDateLocal(day)) count += 1;
  }
  return count;
}

function buildScheduleWindow(exportDate) {
  const deadlineSource = parseIsoDate(dashData?.meta?.sprint_end) || exportDate || new Date();
  const officialDeadline = new Date(deadlineSource.getFullYear(), deadlineSource.getMonth() + 1, 0);
  const operationalDeadline = previousBusinessDateLocal(officialDeadline);
  const officialEndExclusive = addLocalDays(officialDeadline, 1);
  const operationalEndExclusive = addLocalDays(operationalDeadline, 1);
  const minCalendarDays = 20;
  let start = parseIsoDate(dashData?.meta?.sprint_start) || addLocalDays(officialEndExclusive, -minCalendarDays);
  if (start > officialDeadline || (daysBetweenDates(start, officialEndExclusive) || 0) < minCalendarDays) {
    start = addLocalDays(officialEndExclusive, -minCalendarDays);
  }
  return { start, officialDeadline, operationalDeadline, officialEndExclusive, operationalEndExclusive, minCalendarDays };
}

function extractTaskHu(task) {
  for (const value of [task?.title, task?.hu, task?.labels]) {
    const match = String(value || '').match(/\bHU\s*0*\d+\b/i);
    if (match) return match[0].replace(/\s+/g, '').toUpperCase();
  }
  return '';
}

function taskDoneDate(task) {
  return parseIsoDate(task?.date_done || task?.wip_done_date || null);
}

function isDeliveryDoneTask(task) {
  if (taskDoneDate(task)) return true;
  if (task?.done || task?.done_kpi) return true;
  const text = normalizeText([
    task?.status,
    task?.progress,
    task?.bucket,
    task?.labels,
  ].filter(Boolean).join(';'));
  return text.includes('concluid');
}

function deriveMetricDays() {
  let start = parseIsoDate(dashData?.meta?.sprint_start);
  let end = parseIsoDate(dashData?.meta?.sprint_end);
  if (!start || !end) {
    const dates = dashData?.wip?.dates || dashData?.cfd?.dates || [];
    start = parseIsoDate(dates[0]);
    end = parseIsoDate(dates[dates.length - 1]);
    if (end) end = addLocalDays(end, 1);
  }
  if (!start || !end) {
    const today = new Date();
    start = new Date(today.getFullYear(), today.getMonth(), today.getDate());
    end = addLocalDays(start, 1);
  }
  if (end < start) [start, end] = [end, start];
  const count = Math.max(1, daysBetweenDates(start, end) || 1);
  return { start, end, count, days: Array.from({ length: count }, (_, i) => addLocalDays(start, i)) };
}

function taskStoryPointWeights(tasks, huSp) {
  const counts = {};
  tasks.forEach(task => {
    const hu = extractTaskHu(task);
    if (hu) counts[hu] = (counts[hu] || 0) + 1;
  });
  return tasks.map(task => {
    const hu = extractTaskHu(task);
    const sp = Number(huSp?.[hu] || 0);
    return hu && sp > 0 && counts[hu] ? sp / counts[hu] : 0;
  });
}

function deliveryPersonName(task) {
  return String(task?.assignee || '').trim() || 'Sem atribui\u00e7\u00e3o';
}

function getAvailableDeliveryPeople(data = dashData) {
  const names = new Set();
  (data?.task_rows || []).forEach(task => {
    if (!isDeliveryDoneTask(task)) return;
    names.add(deliveryPersonName(task));
  });
  return Array.from(names).sort((a, b) => a.localeCompare(b, 'pt-BR'));
}

function getSelectedDeliveryPeople(chartId = 'delivery_person') {
  const state = getFilterState(chartId);
  const people = getAvailableDeliveryPeople();
  if (!people.length) return [];
  if (!Array.isArray(state.delivery_people)) {
    state.delivery_people = state.delivery_person && people.includes(state.delivery_person)
      ? [state.delivery_person]
      : people.slice();
  }
  state.delivery_people = state.delivery_people.filter(person => people.includes(person));
  state.delivery_person = state.delivery_people.length === 1 ? state.delivery_people[0] : '';
  return state.delivery_people;
}

function elapsedSprintBusinessDays(data = dashData) {
  const meta = data?.meta || {};
  let start = parseIsoDate(meta.sprint_start);
  let end = parseIsoDate(meta.export_date) || new Date();
  const sprintEnd = parseIsoDate(meta.sprint_end);
  if (!start) start = deriveMetricDays().start;
  if (sprintEnd && end > sprintEnd) end = sprintEnd;
  if (!start || !end || end < start) return 0;
  return businessDaysBetweenLocal(start, addLocalDays(end, 1));
}

function getDeliveryDateBounds(data = dashData) {
  const doneDates = (data?.task_rows || [])
    .map(taskDoneDate)
    .filter(Boolean)
    .sort((a, b) => a - b);
  let start = parseIsoDate(data?.meta?.sprint_start) || doneDates[0] || deriveMetricDays().start;
  let end = parseIsoDate(data?.meta?.sprint_end)
    || doneDates[doneDates.length - 1]
    || parseIsoDate(data?.meta?.export_date)
    || addLocalDays(deriveMetricDays().end, -1);
  if (start && end && end < start) [start, end] = [end, start];
  return { start, end };
}

function getAvailableDeliveryWeeks(data = dashData) {
  const { start, end } = getDeliveryDateBounds(data);
  if (!start || !end) return [];
  const weeks = [];
  let current = new Date(start.getFullYear(), start.getMonth(), start.getDate());
  let index = 1;
  while (current <= end) {
    const weekStart = current;
    const weekEnd = addLocalDays(weekStart, 6) < end ? addLocalDays(weekStart, 6) : end;
    const startKey = dateKeyLocal(weekStart);
    const endKey = dateKeyLocal(weekEnd);
    const rangeLabel = `${formatDateOnlyPt(startKey)} a ${formatDateOnlyPt(endKey)}`;
    weeks.push({
      id: `${startKey}_${endKey}`,
      index,
      startKey,
      endKey,
      label: `Semana ${index}, de ${rangeLabel}`,
      rangeLabel,
    });
    current = addLocalDays(weekEnd, 1);
    index += 1;
  }
  return weeks;
}

function getSelectedDeliveryWeeks(chartId = 'delivery_person', data = dashData) {
  const weeks = getAvailableDeliveryWeeks(data);
  const weekIds = weeks.map(week => week.id);
  if (data !== dashData) return weekIds;
  const state = getFilterState(chartId);
  if (!weekIds.length) {
    state.delivery_weeks = [];
    return [];
  }
  if (!Array.isArray(state.delivery_weeks)) state.delivery_weeks = weekIds.slice();
  state.delivery_weeks = state.delivery_weeks.filter(weekId => weekIds.includes(weekId));
  return state.delivery_weeks;
}

function buildDeliveryWeekThroughput({ data = dashData, chartId = 'delivery_person', rows = null, selectedPeople = null } = {}) {
  const weeks = getAvailableDeliveryWeeks(data);
  if (!weeks.length) return [];
  const selectedWeekIds = new Set(getSelectedDeliveryWeeks(chartId, data));
  if (!selectedWeekIds.size) return [];
  const sourceRows = rows || buildPersonDeliveryRows({ data, chartId, selectedPeople });
  return weeks
    .filter(week => selectedWeekIds.has(week.id))
    .map(week => {
      const weekRows = sourceRows.filter(row => row[0] >= week.startKey && row[0] <= week.endKey);
      const tasks = weekRows.reduce((sum, row) => sum + Number(row[1] || 0), 0);
      const sp = weekRows.reduce((sum, row) => sum + Number(row[2] || 0), 0);
      return {
        ...week,
        tasks,
        sp: Number(sp.toFixed(2)),
      };
    });
}

function formatDeliveryWeekThroughput(weeklyThroughput) {
  if (!weeklyThroughput.length) return 'nenhuma semana selecionada';
  return weeklyThroughput
    .map(week => `Semana ${week.index} (${week.rangeLabel}): ${formatMetric(week.sp, 2)} SP / ${formatMetric(week.tasks, 0)} tarefa(s)`)
    .join(' · ');
}

function appendDeliveryFooterMetric(parent, label, value, unit = '') {
  const item = document.createElement('div');
  item.className = 'delivery-footer-metric';
  const labelEl = document.createElement('div');
  labelEl.className = 'delivery-footer-metric-label';
  labelEl.textContent = label;
  const valueEl = document.createElement('div');
  valueEl.className = 'delivery-footer-metric-value';
  valueEl.textContent = unit ? `${value} ${unit}` : String(value);
  item.append(labelEl, valueEl);
  parent.appendChild(item);
}

function appendDeliveryFooterWeek(parent, week) {
  const item = document.createElement('div');
  item.className = 'delivery-footer-week';

  const head = document.createElement('div');
  head.className = 'delivery-footer-week-head';
  const title = document.createElement('span');
  title.textContent = `Semana ${week.index}`;
  const range = document.createElement('span');
  range.textContent = week.rangeLabel;
  head.append(title, range);

  const metrics = document.createElement('div');
  metrics.className = 'delivery-footer-week-metrics';
  appendDeliveryFooterMetric(metrics, 'SP', formatMetric(week.sp, 2));
  appendDeliveryFooterMetric(metrics, 'Tarefas', formatMetric(week.tasks, 0));

  item.append(head, metrics);
  parent.appendChild(item);
}

function resolveDeliverySelection({ data = dashData, chartId = 'delivery_person', selectedPeople = null } = {}) {
  const people = getAvailableDeliveryPeople(data);
  if (selectedPeople === 'Todos') return people;
  if (Array.isArray(selectedPeople)) return selectedPeople.filter(person => people.includes(person));
  if (typeof selectedPeople === 'string' && selectedPeople) return people.includes(selectedPeople) ? [selectedPeople] : [];
  return data === dashData ? getSelectedDeliveryPeople(chartId) : people;
}

function buildPersonDeliveryRows({ data = dashData, chartId = 'delivery_person', selectedPeople = null } = {}) {
  const tasks = data?.task_rows || [];
  if (!tasks.length) return [];
  const huSp = data?.burndown_sp?.hu_sp || {};
  const weights = taskStoryPointWeights(tasks, huSp);
  const people = resolveDeliverySelection({ data, chartId, selectedPeople });
  const selectedSet = new Set(people);
  if (!selectedSet.size) return [];
  const grouped = new Map();

  tasks.forEach((task, index) => {
    const doneDate = taskDoneDate(task);
    if (!doneDate) return;
    const taskPerson = deliveryPersonName(task);
    if (!selectedSet.has(taskPerson)) return;
    const dateKey = dateKeyLocal(doneDate);
    const current = grouped.get(dateKey) || { date: dateKey, tasks: 0, sp: 0 };
    current.tasks += 1;
    current.sp += Number(weights[index] || 0);
    grouped.set(dateKey, current);
  });

  return Array.from(grouped.values())
    .sort((a, b) => a.date.localeCompare(b.date))
    .map(row => [row.date, row.tasks, Number(row.sp.toFixed(2))]);
}

function buildPersonDeliveryDistribution({ data = dashData, chartId = 'delivery_person', selectedPeople = null } = {}) {
  const tasks = data?.task_rows || [];
  if (!tasks.length) return [];
  const huSp = data?.burndown_sp?.hu_sp || {};
  const weights = taskStoryPointWeights(tasks, huSp);
  const people = resolveDeliverySelection({ data, chartId, selectedPeople });
  const selectedSet = new Set(people);
  if (!selectedSet.size) return [];
  const grouped = new Map();

  tasks.forEach((task, index) => {
    if (!isDeliveryDoneTask(task)) return;
    const taskPerson = deliveryPersonName(task);
    if (!selectedSet.has(taskPerson)) return;
    const current = grouped.get(taskPerson) || { person: taskPerson, tasks: 0, sp: 0 };
    current.tasks += 1;
    current.sp += Number(weights[index] || 0);
    grouped.set(taskPerson, current);
  });

  return Array.from(grouped.values())
    .map(row => ({ ...row, sp: Number(row.sp.toFixed(2)) }))
    .sort((a, b) => b.sp - a.sp || b.tasks - a.tasks || a.person.localeCompare(b.person, 'pt-BR'));
}

function getPersonDeliveryStats(options = {}) {
  const data = options.data || dashData;
  const selectedPeople = resolveDeliverySelection({
    data,
    chartId: options.chartId || 'delivery_person',
    selectedPeople: options.selectedPeople ?? null,
  });
  const rows = buildPersonDeliveryRows({
    data,
    chartId: options.chartId || 'delivery_person',
    selectedPeople,
  });
  const personRows = buildPersonDeliveryDistribution({
    data,
    chartId: options.chartId || 'delivery_person',
    selectedPeople,
  });
  const datedTasks = rows.reduce((sum, row) => sum + Number(row[1] || 0), 0);
  const datedSp = rows.reduce((sum, row) => sum + Number(row[2] || 0), 0);
  const distributedTasks = personRows.reduce((sum, row) => sum + Number(row.tasks || 0), 0);
  const distributedSp = personRows.reduce((sum, row) => sum + Number(row.sp || 0), 0);
  const totalTasks = datedTasks || distributedTasks;
  const totalSp = datedSp || distributedSp;
  const businessDays = elapsedSprintBusinessDays(data);
  const weeks = getAvailableDeliveryWeeks(data);
  const selectedWeeks = getSelectedDeliveryWeeks(options.chartId || 'delivery_person', data);
  const weeklyThroughput = buildDeliveryWeekThroughput({
    data,
    chartId: options.chartId || 'delivery_person',
    rows,
    selectedPeople,
  });
  return {
    rows,
    personRows,
    selectedPeople,
    weeks,
    selectedWeeks,
    weeklyThroughput,
    totalTasks,
    totalSp: Number(totalSp.toFixed(2)),
    businessDays,
    avgSpPerBusinessDay: businessDays > 0 ? Number((totalSp / businessDays).toFixed(2)) : 0,
  };
}

const QUALITY_BUG_ADJUSTMENT_TERMS = ['bug', 'ajuste'];
const QUALITY_IMPEDIMENT_TERMS = ['impedimento', 'impedido', 'impeditivo', 'bloqueio', 'bloqueado', 'blocked', 'blocker'];

function taskQualityText(task) {
  return normalizeText(`${task?.labels || ''};${task?.bucket || ''}`);
}

function taskHasQualityTerm(task, terms) {
  const text = taskQualityText(task);
  return terms.some(term => text.includes(term));
}

function qualityRowsByHu(tasks, taggedTasks, huTasks) {
  const byHu = {};
  let withoutHu = 0;
  taggedTasks.forEach(task => {
    const hu = extractTaskHu(task);
    if (!hu) {
      withoutHu += 1;
      return;
    }
    byHu[hu] = (byHu[hu] || 0) + 1;
  });

  const rows = Object.entries(byHu).map(([hu, count]) => [hu, count, (huTasks[hu] || []).length]);
  if (withoutHu) rows.push(['Fora de HU', withoutHu, '-']);
  return rows.sort((a, b) => {
    const aOutside = a[0] === 'Fora de HU';
    const bOutside = b[0] === 'Fora de HU';
    if (aOutside !== bOutside) return aOutside ? 1 : -1;
    return Number(b[1] || 0) - Number(a[1] || 0) || String(a[0]).localeCompare(String(b[0]));
  }).slice(0, 8);
}

function buildQualityTagMetrics(tasks, huTasks) {
  const huCount = Object.keys(huTasks).length;
  const bugRowsRaw = tasks.filter(task => taskHasQualityTerm(task, QUALITY_BUG_ADJUSTMENT_TERMS));
  const bugWithHu = bugRowsRaw.filter(task => extractTaskHu(task));
  const impedimentRowsRaw = tasks.filter(task => taskHasQualityTerm(task, QUALITY_IMPEDIMENT_TERMS));
  const impedimentWithHu = impedimentRowsRaw.filter(task => extractTaskHu(task));
  return {
    bug_task_count: bugRowsRaw.length,
    bug_task_with_hu_count: bugWithHu.length,
    bug_hu_count: new Set(bugWithHu.map(task => extractTaskHu(task))).size,
    bug_density_avg: huCount ? bugWithHu.length / huCount : null,
    bug_rows: qualityRowsByHu(tasks, bugRowsRaw, huTasks),
    impediment_task_count: impedimentRowsRaw.length,
    impediment_task_with_hu_count: impedimentWithHu.length,
    impediment_hu_count: new Set(impedimentWithHu.map(task => extractTaskHu(task))).size,
    impediment_rows: qualityRowsByHu(tasks, impedimentRowsRaw, huTasks),
  };
}

function avgMetric(values) {
  const vals = values.map(Number).filter(Number.isFinite);
  return vals.length ? vals.reduce((a, b) => a + b, 0) / vals.length : null;
}

function pctMetric(num, den) {
  const n = Number(num);
  const d = Number(den);
  return Number.isFinite(n) && Number.isFinite(d) && d > 0 ? n / d * 100 : null;
}


function taskFlowTimingItem(task, index, weights) {
  const done = taskDoneDate(task);
  if (!done) return null;
  const started = parseIsoDate(task.date_start);
  const created = parseIsoDate(task.date_created || task.date_criacao);
  const cycle = daysBetweenDates(started, done);
  const lead = daysBetweenDates(created, done);
  return {
    task,
    index,
    done,
    hu: extractTaskHu(task),
    sp: Number(weights?.[index] || 0),
    cycle: cycle != null && cycle >= 0 ? cycle : null,
    lead: lead != null && lead >= 0 ? lead : null,
  };
}

function flowEfficiencyForTimingItems(items, basis = 'task') {
  const valid = (items || []).filter(item => item.cycle != null && item.lead != null);
  if (!valid.length) return null;
  if (basis === 'hu') {
    const grouped = new Map();
    valid.forEach(item => {
      if (!item.hu) return;
      if (!grouped.has(item.hu)) grouped.set(item.hu, []);
      grouped.get(item.hu).push(item);
    });
    const huCycle = [];
    const huLead = [];
    grouped.forEach(rows => {
      huCycle.push(avgMetric(rows.map(row => row.cycle)));
      huLead.push(avgMetric(rows.map(row => row.lead)));
    });
    return pctMetric(avgMetric(huCycle), avgMetric(huLead));
  }
  if (basis === 'sp') {
    const weighted = valid.filter(item => item.sp > 0);
    const totalSp = weighted.reduce((sum, item) => sum + item.sp, 0);
    if (!totalSp) return null;
    const cycle = weighted.reduce((sum, item) => sum + item.cycle * item.sp, 0) / totalSp;
    const lead = weighted.reduce((sum, item) => sum + item.lead * item.sp, 0) / totalSp;
    return pctMetric(cycle, lead);
  }
  return pctMetric(avgMetric(valid.map(item => item.cycle)), avgMetric(valid.map(item => item.lead)));
}

function buildWeeklyFlowMetrics(tasks, windowData, huSp) {
  const weights = taskStoryPointWeights(tasks, huSp);
  const timedItems = tasks
    .map((task, index) => taskFlowTimingItem(task, index, weights))
    .filter(Boolean);
  const rows = [];
  const weeklyTaskEff = [];
  const weeklyHuEff = [];
  const weeklySpEff = [];

  for (let start = windowData.start, i = 1; start < windowData.end; start = addLocalDays(start, 7), i += 1) {
    const end = addLocalDays(start, 7) < windowData.end ? addLocalDays(start, 7) : windowData.end;
    const weekItems = timedItems.filter(item => item.done && item.done >= start && item.done < end);
    const label = `S${i} (${String(start.getDate()).padStart(2, '0')}/${String(start.getMonth() + 1).padStart(2, '0')}-${String(addLocalDays(end, -1).getDate()).padStart(2, '0')}/${String(addLocalDays(end, -1).getMonth() + 1).padStart(2, '0')})`;
    const tasksDone = weekItems.length;
    const spDone = weekItems.reduce((sum, item) => sum + Number(item.sp || 0), 0);
    rows.push([label, tasksDone, Number(spDone.toFixed(2))]);
    weeklyTaskEff.push(flowEfficiencyForTimingItems(weekItems, 'task'));
    weeklyHuEff.push(flowEfficiencyForTimingItems(weekItems, 'hu'));
    weeklySpEff.push(flowEfficiencyForTimingItems(weekItems, 'sp'));
  }

  return {
    throughput_rows: rows,
    throughput_weekly_avg: avgMetric(rows.map(row => row[1])),
    throughput_total: rows.reduce((sum, row) => sum + Number(row[1] || 0), 0),
    throughput_sp_weekly_avg: avgMetric(rows.map(row => row[2])),
    throughput_sp_total: rows.reduce((sum, row) => sum + Number(row[2] || 0), 0),
    throughput_weeks: rows.length,
    flow_eff_task_weekly: avgMetric(weeklyTaskEff),
    flow_eff_hu_weekly: avgMetric(weeklyHuEff),
    flow_eff_sp_weekly: avgMetric(weeklySpEff),
  };
}
function stddevMetric(values) {
  const vals = values.map(Number).filter(Number.isFinite);
  if (!vals.length) return null;
  const mean = avgMetric(vals);
  return Math.sqrt(vals.reduce((acc, value) => acc + Math.pow(value - mean, 2), 0) / vals.length);
}

function ensureAdvancedMetrics() {
  if (!dashData) return;
  const tasks = dashData.task_rows || [];
  const k = dashData.kpis || {};
  const huSp = dashData.burndown_sp?.hu_sp || {};
  const hasSp = Object.keys(huSp).length > 0;
  const windowData = deriveMetricDays();
  const huTasks = {};
  tasks.forEach(task => {
    const hu = extractTaskHu(task);
    if (!hu) return;
    if (!huTasks[hu]) huTasks[hu] = [];
    huTasks[hu].push(task);
  });
  const qualityTagMetrics = tasks.length ? buildQualityTagMetrics(tasks, huTasks) : null;
  const weeklyFlowMetrics = tasks.length ? buildWeeklyFlowMetrics(tasks, windowData, huSp) : {};

  if (!dashData.flow_metrics && tasks.length) {
    const dailyWip = windowData.days.map(day => tasks.filter(task => {
      const started = parseIsoDate(task.date_start);
      const done = taskDoneDate(task);
      return started && started <= day && (!done || done > day);
    }).length);

    const throughputRows = weeklyFlowMetrics.throughput_rows || [];

    const ctVals = tasks.map(task => {
      const done = taskDoneDate(task);
      const started = parseIsoDate(task.date_start);
      const delta = daysBetweenDates(started, done);
      return delta != null && delta >= 0 ? delta : null;
    }).filter(v => v != null);

    dashData.flow_metrics = {
      wip_avg: avgMetric(dailyWip),
      wip_days: dailyWip.length,
      throughput_weekly_avg: weeklyFlowMetrics.throughput_weekly_avg,
      throughput_total: weeklyFlowMetrics.throughput_total,
      throughput_sp_weekly_avg: weeklyFlowMetrics.throughput_sp_weekly_avg,
      throughput_sp_total: weeklyFlowMetrics.throughput_sp_total,
      throughput_weeks: weeklyFlowMetrics.throughput_weeks,
      throughput_rows: throughputRows,
      flow_eff_task: pctMetric(k.ct_task, k.lt_task),
      flow_eff_hu: pctMetric(k.ct_hu, k.lt_hu),
      flow_eff_sp: pctMetric(k.ct_sp, k.lt_sp),
      flow_eff_task_weekly: weeklyFlowMetrics.flow_eff_task_weekly,
      flow_eff_hu_weekly: weeklyFlowMetrics.flow_eff_hu_weekly,
      flow_eff_sp_weekly: weeklyFlowMetrics.flow_eff_sp_weekly,
      cycle_time_stddev: stddevMetric(ctVals),
      cycle_time_stddev_count: ctVals.length,
    };
  }

  if (dashData.flow_metrics && tasks.length) {
    const weeklyFields = {
      throughput_sp_weekly_avg: weeklyFlowMetrics.throughput_sp_weekly_avg,
      throughput_sp_total: weeklyFlowMetrics.throughput_sp_total,
      flow_eff_task_weekly: weeklyFlowMetrics.flow_eff_task_weekly,
      flow_eff_hu_weekly: weeklyFlowMetrics.flow_eff_hu_weekly,
      flow_eff_sp_weekly: weeklyFlowMetrics.flow_eff_sp_weekly,
    };
    Object.entries(weeklyFields).forEach(([key, value]) => {
      if (dashData.flow_metrics[key] === null || dashData.flow_metrics[key] === undefined) dashData.flow_metrics[key] = value;
    });
    if (!Array.isArray(dashData.flow_metrics.throughput_rows) || dashData.flow_metrics.throughput_rows.every(row => !Array.isArray(row) || row.length < 3)) {
      dashData.flow_metrics.throughput_rows = weeklyFlowMetrics.throughput_rows || [];
    }
  }
  if (!dashData.scope_quality_metrics && tasks.length) {
    const weights = taskStoryPointWeights(tasks, huSp);
    const committedSp = Number(dashData.burndown_sp?.total_sp || k.storypoints || 0);
    const deliveredSp = hasSp
      ? Object.entries(huSp).reduce((sum, [hu, sp]) => {
          const rows = huTasks[hu] || [];
          return rows.length && rows.every(task => taskDoneDate(task)) ? sum + Number(sp || 0) : sum;
        }, 0)
      : 0;
    const creepRows = tasks.filter(task => {
      const text = normalizeText(`${task.labels || ''};${task.bucket || ''}`);
      return text.includes('imprevisto') || text.includes('nao mapeado') || text.includes('nao previsto');
    });
    const creepSp = creepRows.reduce((sum, task) => sum + (weights[tasks.indexOf(task)] || 0), 0);
    const huSpValues = Object.values(huSp).map(Number).filter(v => Number.isFinite(v) && v > 0);
    dashData.scope_quality_metrics = {
      committed_sp: committedSp,
      delivered_sp: deliveredSp,
      say_do_ratio: pctMetric(deliveredSp, committedSp),
      avg_hu_size_sp: avgMetric(huSpValues),
      ...qualityTagMetrics,
      scope_creep_tasks: creepRows.length,
      scope_creep_sp: creepSp,
      scope_creep_task_pct: pctMetric(creepRows.length, tasks.length),
      scope_creep_sp_pct: pctMetric(creepSp, committedSp),
    };
  } else if (qualityTagMetrics) {
    dashData.scope_quality_metrics = {
      ...dashData.scope_quality_metrics,
      ...qualityTagMetrics,
    };
  }

  if ((!dashData.time_metrics || dashData.time_metrics.schedule_basis !== 'business_days') && tasks.length) {
    const scope = dashData.scope_quality_metrics || {};
    const weights = taskStoryPointWeights(tasks, huSp);
    const exportDate = parseIsoDate(dashData.meta?.export_date) || new Date();
    const schedule = buildScheduleWindow(exportDate);
    const totalDays = businessDaysBetweenLocal(schedule.start, schedule.operationalEndExclusive);
    const calendarTotal = Math.max(1, daysBetweenDates(schedule.start, schedule.officialEndExclusive) || schedule.minCalendarDays);
    let remainingDays = 0;
    let calendarRemaining = 0;
    if (exportDate < schedule.start) {
      remainingDays = totalDays;
      calendarRemaining = calendarTotal;
    } else if (exportDate > schedule.operationalDeadline) {
      remainingDays = 0;
      calendarRemaining = exportDate > schedule.officialDeadline ? 0 : Math.max(0, (daysBetweenDates(exportDate, schedule.officialDeadline) || 0) + 1);
    } else {
      remainingDays = businessDaysBetweenLocal(exportDate, schedule.operationalEndExclusive);
      calendarRemaining = Math.max(0, (daysBetweenDates(exportDate, schedule.officialDeadline) || 0) + 1);
    }
    const elapsed = Math.max(totalDays - remainingDays, 0);
    const calendarElapsed = Math.max(calendarTotal - calendarRemaining, 0);
    const totalWork = hasSp ? Number(scope.committed_sp || dashData.burndown_sp?.total_sp || k.storypoints || 0) : Number(k.total || tasks.length || 0);
    const doneWork = hasSp
      ? tasks.reduce((sum, task, idx) => taskDoneDate(task) ? sum + (weights[idx] || 0) : sum, 0)
      : Number(k.done || tasks.filter(taskDoneDate).length || 0);
    const remainingWork = Math.max(totalWork - doneWork, 0);
    const daysPct = pctMetric(remainingDays, totalDays) || 0;
    const workPct = pctMetric(remainingWork, totalWork) || 0;
    const delta = workPct - daysPct;
    const firstResponse = tasks.map(task => {
      const created = parseIsoDate(task.date_created || task.date_criacao);
      const started = parseIsoDate(task.date_start);
      const days = daysBetweenDates(created, started);
      return days != null && days >= 0 ? days : null;
    }).filter(v => v != null);
    dashData.time_metrics = {
      days_elapsed: elapsed,
      days_remaining: remainingDays,
      days_total: totalDays,
      days_remaining_pct: daysPct,
      calendar_days_elapsed: calendarElapsed,
      calendar_days_remaining: calendarRemaining,
      calendar_days_total: calendarTotal,
      calendar_days_remaining_pct: pctMetric(calendarRemaining, calendarTotal) || 0,
      deadline_date: dateKeyLocal(schedule.officialDeadline),
      operational_deadline_date: dateKeyLocal(schedule.operationalDeadline),
      deadline_shifted: dateKeyLocal(schedule.officialDeadline) !== dateKeyLocal(schedule.operationalDeadline),
      sprint_effective_start: dateKeyLocal(schedule.start),
      min_calendar_days: schedule.minCalendarDays,
      schedule_basis: 'business_days',
      work_remaining: remainingWork,
      work_total: totalWork,
      work_unit: hasSp ? 'SP' : 'tarefas',
      work_remaining_pct: workPct,
      schedule_delta_pct: delta,
      schedule_status: delta > 20 ? 'alerta' : delta > 10 ? 'atencao' : 'saudavel',
      first_response_avg: avgMetric(firstResponse),
      first_response_count: firstResponse.length,
    };
  }
}

function getAgingView(chartId = 'aging') {
  const state = getFilterState(chartId);
  const selected = String(state.aging_view || 'areas');
  if (!AGING_VIEW_OPTIONS.includes(selected)) state.aging_view = 'areas';
  return state.aging_view || 'areas';
}

function getAgingTaskSelectedLabels(chartId = 'aging_tasks') {
  const state = getFilterState(chartId);
  if (!Array.isArray(state.aging_task_labels)) state.aging_task_labels = [];
  state.aging_task_labels = state.aging_task_labels
    .map(value => String(value || '').trim())
    .filter(Boolean);
  return state.aging_task_labels;
}

function getAvailableAgingTaskLabels(chartId = 'aging_tasks') {
  const selected = getAgingTaskSelectedLabels(chartId);
  const unique = new Map();
  (dashData?.task_rows || []).forEach(task => {
    if (parseIsoDate(task?.date_done)) return;
    collectTaskLabels(task).forEach(({ key, label }) => {
      if (!unique.has(key)) unique.set(key, label);
    });
  });
  selected.forEach(label => {
    const key = normalizeText(label);
    if (key && !unique.has(key)) unique.set(key, label);
  });
  return Array.from(unique.values()).sort((a, b) => a.localeCompare(b, 'pt-BR'));
}

function getAgingTaskLabelPalette(chartId = 'aging_tasks') {
  const cw = PALETTES[activePaletteName]?.colorway || PALETTES.teal.colorway;
  const palette = new Map();
  AGING_TASK_TEAM_LABELS.forEach((label, index) => {
    palette.set(label, cw[index % cw.length] || pc(index));
  });
  return palette;
}

function getAgingTaskPage(chartId = 'aging_tasks', totalItems = 0) {
  const state = getFilterState(chartId);
  const totalPages = Math.max(1, Math.ceil(Math.max(0, totalItems) / AGING_TASKS_PAGE_SIZE));
  const pageValue = Number(state.aging_task_page || 1);
  const page = Number.isFinite(pageValue) ? Math.min(Math.max(1, Math.floor(pageValue)), totalPages) : 1;
  state.aging_task_page = page;
  return { page, totalPages };
}

function collectAgingTokens(task, view) {
  if (view === 'colaborador') {
    const name = String(task?.assignee || '').trim() || 'Sem atribuição';
    return [{ key: normalizeText(name), label: name }];
  }

  const labels = String(task?.labels || '')
    .split(';')
    .map(token => token.trim())
    .filter(Boolean);
  if (!labels.length) return [];

  const unique = new Map();
  labels.forEach(label => {
    const norm = normalizeText(label);
    if (!norm) return;

    if (view === 'areas') {
      if (!norm.includes('.') || norm.startsWith('hu') || norm === 'fluxo.continuo') return;
      const display = label.startsWith('.') ? label.toUpperCase() : `.${label.toUpperCase()}`;
      unique.set(normalizeText(display), display);
      return;
    }

    unique.set(norm, label);
  });

  return Array.from(unique.entries()).map(([key, label]) => ({ key, label }));
}

function buildAgingRows(view = 'areas', chartId = 'aging') {
  if (!dashData?.task_rows?.length) return [];

  const selectedView = AGING_VIEW_OPTIONS.includes(view) ? view : getAgingView(chartId);
  const refDate = getAgingReferenceDate();
  const groups = new Map();
  const dayMs = 24 * 60 * 60 * 1000;

  (dashData.task_rows || []).forEach(task => {
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

function buildAgingTaskRows(chartId = 'aging_tasks') {
  if (!dashData?.task_rows?.length) return [];

  const refDate = getAgingReferenceDate();
  const dayMs = 24 * 60 * 60 * 1000;
  const selectedLabels = new Set(
    getAgingTaskSelectedLabels(chartId).map(label => normalizeText(label)).filter(Boolean)
  );
  const selectedTeams = getAgingTaskSelectedLabels(chartId)
    .map(label => resolveAgingTaskTeamLabel(label))
    .filter(Boolean);
  const labelPalette = getAgingTaskLabelPalette(chartId);
  const unlabeledColor = isDark() ? '#7a8fa6' : '#94a3b8';

  return (dashData.task_rows || [])
    .filter(task => !parseIsoDate(task?.date_done))
    .map((task, index) => {
      const createdDate = parseIsoDate(task?.date_created || task?.date_criacao);
      const startDate = parseIsoDate(task?.date_start);
      const baseDate = createdDate || startDate;
      if (!baseDate || baseDate > refDate) return null;

      const taskLabels = collectTaskLabels(task);
      if (selectedLabels.size && !taskLabels.some(label => selectedLabels.has(label.key))) return null;

      const ageDays = Math.floor((refDate.getTime() - baseDate.getTime()) / dayMs);
      if (ageDays < 0) return null;

      const teamLabel = pickAgingTaskTeamLabel(taskLabels, selectedTeams) || 'Sem equipe';

      return {
        title: String(task?.title || '').trim() || `Tarefa ${index + 1}`,
        ageDays,
        labelsText: taskLabels.length ? taskLabels.map(label => label.label).join('; ') : 'Sem rótulos',
        assignee: String(task?.assignee || '').trim() || 'Sem atribuição',
        baseDateText: baseDate.toLocaleDateString('pt-BR'),
        teamLabel,
        teamColor: labelPalette.get(teamLabel) || unlabeledColor,
      };
    })
    .filter(Boolean)
    .sort((a, b) => b.ageDays - a.ageDays || a.title.localeCompare(b.title, 'pt-BR'));
}

function getPagedAgingTaskRows(chartId = 'aging_tasks') {
  const rows = buildAgingTaskRows(chartId);
  const { page, totalPages } = getAgingTaskPage(chartId, rows.length);
  const startIndex = (page - 1) * AGING_TASKS_PAGE_SIZE;
  const pagedRows = rows.slice(startIndex, startIndex + AGING_TASKS_PAGE_SIZE);
  return {
    rows: pagedRows,
    totalRows: rows.length,
    page,
    totalPages,
    startIndex,
    endIndex: pagedRows.length ? startIndex + pagedRows.length : startIndex,
  };
}

function getAgingTaskLegendItems(chartId = 'aging_tasks') {
  const rows = buildAgingTaskRows(chartId);
  const unique = new Map();

  rows.forEach(row => {
    const key = row.teamLabel;
    if (!key || unique.has(key)) return;
    unique.set(key, { label: row.teamLabel, color: row.teamColor });
  });

  const ordered = AGING_TASK_TEAM_LABELS
    .filter(label => unique.has(label))
    .map(label => unique.get(label));

  if (unique.has('Sem equipe')) ordered.push(unique.get('Sem equipe'));
  return ordered;
}

function toggleChartFullscreen() {
  const shell = document.getElementById('chartPlotShell');
  if (!shell) return;

  if (document.fullscreenElement === shell) {
    if (document.exitFullscreen) {
      document.exitFullscreen().then(() => {
        if (window.Plotly) Plotly.Plots.resize('mainPlot');
        renderChartFooter(activeChartId);
      }).catch(() => {});
    }
    return;
  }

  const request = shell.requestFullscreen?.bind(shell);
  if (!request) return;
  request().then(() => {
    if (window.Plotly) Plotly.Plots.resize('mainPlot');
    renderChartFooter(activeChartId);
  }).catch(() => {});
}

function chartPngExportName(chartId) {
  const chart = findCatalogItem(chartId);
  const sprint = dashData?.meta?.sprint_name || dashData?.meta?.projeto || '';
  return [chart?.name || chartId || 'grafico', sprint].filter(Boolean).join(' - ');
}

function renderDomChartFooter(chartId, body) {
  if (!body || body.querySelector('.empty-state')) return;
  const footer = document.createElement('div');
  footer.className = 'chart-footer chart-footer--standalone visible';
  footer.dataset.exportIgnore = 'true';
  const actions = document.createElement('div');
  actions.className = 'chart-footer-actions';
  actions.appendChild(createChartPngButton(() => body, chartPngExportName(chartId), { forceDom: true }));
  actions.appendChild(createChartCsvButton(() => body, chartPngExportName(chartId)));
  footer.appendChild(actions);
  body.appendChild(footer);
}

function renderChartFooter(chartId) {
  const footer = document.getElementById('chartFooter');
  if (!footer) return;
  footer.innerHTML = '';
  footer.classList.remove('visible');
  const actions = document.createElement('div');
  actions.className = 'chart-footer-actions';
  const exportBtn = createChartPngButton(
    () => document.getElementById('mainPlot'),
    chartPngExportName(chartId),
  );
  const csvBtn = createChartCsvButton(
    () => document.getElementById('mainPlot'),
    chartPngExportName(chartId),
  );
  const fullscreenBtn = document.createElement('button');
  fullscreenBtn.type = 'button';
  fullscreenBtn.className = 'btn-small';
  fullscreenBtn.textContent = document.fullscreenElement === document.getElementById('chartPlotShell')
    ? 'Sair da tela cheia'
    : 'Tela cheia';
  fullscreenBtn.addEventListener('click', toggleChartFullscreen);
  if (chartId === 'delivery_person') {
    const stats = getPersonDeliveryStats({ chartId });
    const meta = document.createElement('div');
    meta.className = 'chart-footer-meta';

    const summary = document.createElement('div');
    summary.className = 'delivery-footer-summary';
    appendDeliveryFooterMetric(summary, 'SP/dia útil transcorrido', formatMetric(stats.avgSpPerBusinessDay, 2));
    appendDeliveryFooterMetric(summary, 'SP entregue', formatMetric(stats.totalSp, 2), 'SP');
    appendDeliveryFooterMetric(summary, 'Dias úteis', formatMetric(stats.businessDays, 0));
    appendDeliveryFooterMetric(summary, 'Tarefas entregues', formatMetric(stats.totalTasks, 0));
    meta.appendChild(summary);

    if (stats.weeks.length) {
      const weekly = document.createElement('div');
      weekly.className = 'delivery-footer-weekly';
      const title = document.createElement('div');
      title.className = 'delivery-footer-section-title';
      title.textContent = 'Throughput semanal';
      const weekGrid = document.createElement('div');
      weekGrid.className = 'delivery-footer-week-grid';
      if (stats.weeklyThroughput.length) {
        stats.weeklyThroughput.forEach(week => appendDeliveryFooterWeek(weekGrid, week));
      } else {
        const empty = document.createElement('div');
        empty.className = 'chart-footer-info';
        empty.textContent = 'Nenhuma semana selecionada';
        weekGrid.appendChild(empty);
      }
      weekly.append(title, weekGrid);
      meta.appendChild(weekly);
    }
    actions.append(exportBtn, csvBtn, fullscreenBtn);
    footer.append(meta, actions);
  } else if (chartId === 'aging_tasks') {
    const pageData = getPagedAgingTaskRows(chartId);
    if (!pageData.totalRows) return;
    const state = getFilterState(chartId);
    const meta = document.createElement('div');
    meta.className = 'chart-footer-meta';
    const info = document.createElement('div');
    info.className = 'chart-footer-info';
    info.textContent = `Mostrando ${pageData.startIndex + 1}-${pageData.endIndex} de ${pageData.totalRows} tarefas · Página ${pageData.page} de ${pageData.totalPages}`;
    meta.appendChild(info);

    const legendItems = getAgingTaskLegendItems(chartId);
    if (legendItems.length) {
      const legend = document.createElement('div');
      legend.className = 'chart-footer-legend';
      legendItems.forEach(item => {
        const chip = document.createElement('div');
        chip.className = 'chart-legend-chip';
        chip.innerHTML = `<span class="chart-legend-swatch" style="background:${esc(item.color)}"></span><span>${esc(item.label)}</span>`;
        legend.appendChild(chip);
      });
      meta.appendChild(legend);
    }

    const prevBtn = document.createElement('button');
    prevBtn.type = 'button';
    prevBtn.className = 'btn-small';
    prevBtn.textContent = 'Anterior';
    prevBtn.disabled = pageData.page <= 1;
    prevBtn.addEventListener('click', () => {
      state.aging_task_page = Math.max(1, pageData.page - 1);
      clearDashboardSummary({ preserveReport: true });
      renderActive();
    });
    const nextBtn = document.createElement('button');
    nextBtn.type = 'button';
    nextBtn.className = 'btn-small';
    nextBtn.textContent = 'Próxima';
    nextBtn.disabled = pageData.page >= pageData.totalPages;
    nextBtn.addEventListener('click', () => {
      state.aging_task_page = Math.min(pageData.totalPages, pageData.page + 1);
      clearDashboardSummary({ preserveReport: true });
      renderActive();
    });
    actions.append(prevBtn, nextBtn, exportBtn, csvBtn, fullscreenBtn);
    footer.append(meta, actions);
  } else {
    actions.append(exportBtn, csvBtn, fullscreenBtn);
    footer.appendChild(actions);
  }
  footer.classList.add('visible');
}
document.addEventListener('fullscreenchange', () => {
  if (window.Plotly && document.getElementById('mainPlot')) Plotly.Plots.resize('mainPlot');
  renderChartFooter(activeChartId);
});
function hasAgingData(chartId = 'aging') {
  return buildAgingRows(getAgingView(chartId), chartId).length > 0;
}

function hasAgingTaskData(chartId = 'aging_tasks') {
  return buildAgingTaskRows(chartId).length > 0;
}

function chartAging(chartId, type) {
  const rows = buildAgingRows(getAgingView(chartId), chartId);
  return chartSingleMetric(rows, type, 'Aging médio (dias)');
}

function chartAgingTasks(chartId, type) {
  const pageData = getPagedAgingTaskRows(chartId);
  const rows = pageData.rows;
  if (!rows.length) return { traces: null };
  const labels = rows.map(row => cleanChartLabel(row.title));
  const values = rows.map(row => row.ageDays);
  const customdata = rows.map(row => [row.title, row.labelsText, row.assignee, row.baseDateText, row.teamLabel]);
  const colors = rows.map(row => row.teamColor);
  return {
    traces: [{
      type: 'bar',
      orientation: 'h',
      x: values,
      y: labels,
      customdata,
      marker: {
        color: colors,
        line: {
          color: isDark() ? '#12161f' : '#ffffff',
          width: 1.2,
        },
      },
      hovertemplate:
        '<b>%{customdata[0]}</b><br>' +
        'Equipe: %{customdata[4]}<br>' +
        'Aging: %{x} dia(s)<br>' +
        'Responsável: %{customdata[2]}<br>' +
        'Data base: %{customdata[3]}<br>' +
        'Rótulos: %{customdata[1]}<extra></extra>',
    }],
    layout: plotLayout({
      showlegend: false,
      height: Math.min(580, Math.max(420, rows.length * 22 + 120)),
      margin: { t: 30, r: 20, b: 40, l: 220 },
      xaxis: { title: { text: 'Aging (dias)' } },
      yaxis: { title: { text: '' }, ...labelAxis(labels, 36), autorange: 'reversed' },
    }),
  };
}

function chartPersonDelivery(type = 'bar_v', options = {}) {
  const stats = getPersonDeliveryStats({
    data: options.data || dashData,
    chartId: options.chartId || 'delivery_person',
    selectedPeople: options.selectedPeople ?? null,
  });
  const rows = stats.rows;
  const peopleLabel = stats.selectedPeople.length === 1
    ? stats.selectedPeople[0]
    : `${stats.selectedPeople.length} pessoas`;

  if (type === 'pie' || type === 'donut') {
    const personRows = stats.personRows || [];
    const taskRows = personRows.filter(row => Number(row.tasks || 0) > 0);
    const spRows = personRows.filter(row => Number(row.sp || 0) > 0);
    if (!taskRows.length && !spRows.length) return { traces: null };

    const hole = type === 'donut' ? 0.5 : 0;
    const colors = PALETTES[activePaletteName]?.colorway || PALETTES.teal.colorway;
    const hasBoth = taskRows.length > 0 && spRows.length > 0;
    const taskDomain = hasBoth ? [0, 0.47] : [0.15, 0.85];
    const spDomain = hasBoth ? [0.53, 1] : [0.15, 0.85];
    const traces = [];
    const annotations = [{
      xref: 'paper',
      yref: 'paper',
      x: 0,
      y: 1.18,
      xanchor: 'left',
      yanchor: 'bottom',
      text: `Sele\u00e7\u00e3o: ${esc(peopleLabel)} · Total: ${formatMetric(stats.totalTasks, 0)} tarefas / ${formatMetric(stats.totalSp, 2)} SP`,
      showarrow: false,
      font: { size: 11, color: 'var(--muted)' },
      align: 'left',
    }];

    if (taskRows.length) {
      const labels = taskRows.map(row => cleanChartLabel(row.person));
      traces.push({
        type: 'pie',
        name: 'Tarefas',
        labels: labels.map(label => shortenChartLabel(label, 28)),
        values: taskRows.map(row => row.tasks),
        customdata: labelHoverData(labels),
        domain: { x: taskDomain },
        hole,
        marker: { colors },
        textinfo: 'percent',
        textposition: 'inside',
        insidetextorientation: 'radial',
        automargin: true,
        hovertemplate: '<b>%{customdata}</b><br>Tarefas: %{value}<br>%{percent}<extra></extra>',
      });
      annotations.push({
        xref: 'paper',
        yref: 'paper',
        x: hasBoth ? 0.235 : 0.5,
        y: 1.08,
        xanchor: 'center',
        yanchor: 'bottom',
        text: 'Tarefas',
        showarrow: false,
        font: { size: 12, color: 'var(--text-head)' },
      });
    }

    if (spRows.length) {
      const labels = spRows.map(row => cleanChartLabel(row.person));
      traces.push({
        type: 'pie',
        name: 'Story Points',
        labels: labels.map(label => shortenChartLabel(label, 28)),
        values: spRows.map(row => row.sp),
        customdata: labelHoverData(labels),
        domain: { x: spDomain },
        hole,
        marker: { colors },
        textinfo: 'percent',
        textposition: 'inside',
        insidetextorientation: 'radial',
        automargin: true,
        hovertemplate: '<b>%{customdata}</b><br>Story Points: %{value:.2f}<br>%{percent}<extra></extra>',
      });
      annotations.push({
        xref: 'paper',
        yref: 'paper',
        x: hasBoth ? 0.765 : 0.5,
        y: 1.08,
        xanchor: 'center',
        yanchor: 'bottom',
        text: 'Story Points',
        showarrow: false,
        font: { size: 12, color: 'var(--text-head)' },
      });
    }

    return {
      traces,
      layout: plotLayout({
        showlegend: true,
        margin: { t: 62, r: 16, b: 24, l: 16 },
        uniformtext: { minsize: 10, mode: 'hide' },
        annotations,
      }),
    };
  }

  if (!rows.length && stats.personRows?.length) {
    const personRows = stats.personRows;
    const labels = personRows.map(row => cleanChartLabel(row.person));
    return {
      traces: [
        {
          type: 'bar',
          name: 'Tarefas entregues',
          x: labels,
          y: personRows.map(row => row.tasks),
          offsetgroup: 'tasks',
          marker: { color: pc(0) },
          customdata: labelHoverData(labels),
          hovertemplate: '<b>%{customdata}</b><br>Tarefas: %{y}<extra></extra>',
        },
        {
          type: 'bar',
          name: 'Story Points entregues',
          x: labels,
          y: personRows.map(row => row.sp),
          offsetgroup: 'sp',
          marker: { color: pc(10) },
          customdata: labelHoverData(labels),
          hovertemplate: '<b>%{customdata}</b><br>Story Points: %{y:.2f}<extra></extra>',
        },
      ],
      layout: plotLayout({
        barmode: 'group',
        xaxis: { ...labelAxis(labels, 28), tickangle: -25 },
        yaxis: { title: { text: 'Quantidade / SP' }, rangemode: 'tozero' },
        legend: { orientation: 'h', x: 0, y: 1.12 },
        margin: { t: 52, r: 24, b: 85, l: 70 },
        annotations: [{
          xref: 'paper',
          yref: 'paper',
          x: 0,
          y: 1.18,
          xanchor: 'left',
          yanchor: 'bottom',
          text: `Sele\u00e7\u00e3o: ${esc(peopleLabel)} · Agrupado por pessoa por falta de data de conclus\u00e3o no JSON`,
          showarrow: false,
          font: { size: 11, color: 'var(--muted)' },
          align: 'left',
        }],
      }),
    };
  }

  const dates = rows.map(row => row[0]);
  const tasks = rows.map(row => row[1]);
  const storyPoints = rows.map(row => row[2]);
  const labels = dates.map(date => formatDateOnlyPt(date));
  const dataDateSet = new Set(dates);
  const axisDates = buildDailyDateKeysBetween(dates[0], dates[dates.length - 1]);
  const axisLabels = axisDates.map(date => (
    dataDateSet.has(date) ? formatDateOnlyPt(date) : formatDateDayMonthPt(date)
  ));

  return {
    traces: [
      {
        type: 'bar',
        name: 'Tarefas entregues',
        x: dates,
        y: tasks,
        offsetgroup: 'tasks',
        marker: { color: pc(0) },
        customdata: labels,
        hovertemplate: '<b>%{customdata}</b><br>Tarefas: %{y}<extra></extra>',
      },
      {
        type: 'bar',
        name: 'Story Points entregues',
        x: dates,
        y: storyPoints,
        offsetgroup: 'sp',
        marker: { color: pc(10) },
        customdata: labels,
        hovertemplate: '<b>%{customdata}</b><br>Story Points: %{y:.2f}<extra></extra>',
      },
    ],
    layout: plotLayout({
      barmode: 'group',
      xaxis: {
        type: 'date',
        tickmode: 'array',
        tickvals: axisDates,
        ticktext: axisLabels,
        tickangle: -35,
        tickfont: { size: 10 },
        automargin: true,
      },
      yaxis: { title: { text: 'Quantidade / SP' }, rangemode: 'tozero' },
      legend: { orientation: 'h', x: 0, y: 1.12 },
      margin: { t: 52, r: 24, b: 88, l: 70 },
      annotations: [{
        xref: 'paper',
        yref: 'paper',
        x: 0,
        y: 1.18,
        xanchor: 'left',
        yanchor: 'bottom',
        text: `Sele\u00e7\u00e3o: ${esc(peopleLabel)} · M\u00e9dia: ${formatMetric(stats.avgSpPerBusinessDay, 2)} SP/dia \u00fatil (${stats.businessDays} dias \u00fateis)`,
        showarrow: false,
        font: { size: 11, color: 'var(--muted)' },
        align: 'left',
      }],
    }),
  };
}

function chartSingleMetric(rows, type, seriesLabel) {
  if (!rows?.length) return { traces: null };

  const labels = rows.map(r => cleanChartLabel(r[0]));
  const values = rows.map(r => r[1]);
  if (type === 'pie' || type === 'donut') {
    const pieRows = rows.filter(r => r[1] > 0);
    if (!pieRows.length) return { traces: null };
    const pieLabels = pieRows.map(r => cleanChartLabel(r[0]));
    const pieShortLabels = pieLabels.map(label => shortenChartLabel(label, 34));
    return {
      traces: [{
        type:'pie',
        labels: pieShortLabels,
        values: pieRows.map(r => r[1]),
        customdata: labelHoverData(pieLabels),
        hole: type === 'donut' ? 0.5 : 0,
        marker:{ colors: PALETTES[activePaletteName]?.colorway || PALETTES.teal.colorway },
        textinfo:'percent',
        textposition:'inside',
        insidetextorientation:'radial',
        automargin:true,
        hovertemplate: '<b>%{customdata}</b><br>' + seriesLabel + ': %{value}<br>%{percent}<extra></extra>',
      }],
      layout: plotLayout({
        margin:{ t:30,r:20,b:20,l:20 },
        showlegend:true,
        uniformtext:{ minsize:10, mode:'hide' },
      }),
    };
  }
  if (type === 'line') {
    return {
      traces: [{
        type:'scatter',
        mode:'lines+markers',
        x: labels,
        y: values,
        name: seriesLabel,
        customdata: labelHoverData(labels),
        line:{ color: pc(0), width: 2.5 },
        marker:{ color: pc(0), size: 6 },
        hovertemplate: '<b>%{customdata}</b><br>' + seriesLabel + ': %{y}<extra></extra>',
      }],
      layout: plotLayout({
        showlegend:false,
        margin:{ t:30,r:20,b:90,l:55 },
        xaxis:{ ...labelAxis(labels, 34), tickangle:-25 },
        yaxis:{ title:{ text: seriesLabel } },
      }),
    };
  }

  const horiz = type === 'bar_h';
  return {
    traces: [{
      type:'bar',
      name: seriesLabel,
      x: horiz ? values : labels,
      y: horiz ? labels : values,
      orientation: horiz ? 'h' : 'v',
      marker:{ color: pc(0) },
      customdata: labelHoverData(labels),
      hovertemplate: '<b>%{customdata}</b><br>' + seriesLabel + ': %{'+(horiz ? 'x' : 'y')+'}<extra></extra>',
    }],
    layout: plotLayout({
      showlegend:false,
      margin:{ t:30,r:20,b:horiz?40:90,l:horiz?190:55 },
      yaxis: horiz
        ? { ...labelAxis(labels, 34), title:{ text: '' } }
        : { title:{ text: seriesLabel } },
      xaxis: horiz
        ? { title:{ text: seriesLabel }, tickangle: 0 }
        : { ...labelAxis(labels, 32), title:{ text: '' }, tickangle: -30 },
    }),
  };
}

function buildCustomChart(chart, type) {
  const resolvedType = type || chart.chart_type || 'bar_v';
  if (chart.source_key === 'wip_profile') {
    return chartWipProfile(chart, resolvedType);
  }
  const rows = getCustomChartRows(chart);
  if (!rows.length) return { traces: null };
  return chartSingleMetric(rows, resolvedType, metricLabelForCustomChart(chart));
}

function chartWipProfile(chart, type) {
  const data = buildWipProfileData(chart);
  if (!data) return { traces: null };
  const cw = PALETTES[activePaletteName]?.colorway || PALETTES.teal.colorway;
  const seriesEntries = [
    ['Concluído', data.series['Concluído'], cw[2] || pc(2)],
    ['Em Produção', data.series['Em Produção'], cw[0] || pc(0)],
    ['Backlog', data.series.Backlog, '#7a8fa6'],
  ];

  const traces = seriesEntries.map(([name, values, color]) => {
    if (type === 'bar_v') {
      return { type:'bar', name, x:data.dates, y:values, marker:{ color } };
    }
    return {
      type:'scatter',
      mode:'lines',
      name,
      x:data.dates,
      y:values,
      line:{ color, width:2.5 },
      fill: type === 'area' ? 'tonexty' : 'none',
      fillcolor: type === 'area' ? color + '33' : undefined,
      stackgroup: type === 'area' ? 'wip-profile' : undefined,
    };
  });

  return {
    traces,
    layout: plotLayout({
      barmode:'stack',
      xaxis:{ type:'date', tickformat:'%d/%m' },
      yaxis:{ title:{ text:'Tarefas' } },
      margin:{ t:30, r:20, b:50, l:55 },
    }),
  };
}

/* â”€â”€ Burndown â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€ */
function buildScopeEventMarkers(events = [], unit = 'SP', valueKey = 'sp') {
  const dayNumber = dateStr => {
    const parsed = Date.parse(`${dateStr}T00:00:00`);
    return Number.isFinite(parsed) ? Math.floor(parsed / 86400000) : 0;
  };
  const formatScopeUnit = value => {
    if (unit === 'SP') return 'SP';
    if (String(unit).toLowerCase().startsWith('tarefa')) {
      return Math.abs(Number(value) || 0) === 1 ? 'tarefa' : 'tarefas';
    }
    return unit;
  };
  const compactScopeLabel = labels => {
    const cleanLabels = Array.from(new Set(labels.filter(Boolean).map(label => String(label).trim()).filter(Boolean)));
    if (!cleanLabels.length) return '';
    if (cleanLabels.length > 1) return `${cleanLabels.length} itens`;
    const label = cleanLabels[0];
    const normalized = label.normalize('NFD').replace(/[\u0300-\u036f]/g, '').toLowerCase();
    if (normalized.includes('nao previsto')) return '';
    return label.length > 18 ? `${label.slice(0, 17)}...` : label;
  };

  const groups = new Map();
  (events || []).forEach(event => {
    const date = String(event?.date || '').trim();
    if (!date) return;
    const value = Number(event?.[valueKey] ?? event?.sp ?? event?.weight ?? 0);
    if (!Number.isFinite(value) || value <= 0) return;
    const current = groups.get(date) || { date, value: 0, labels: [] };
    current.value += value;
    if (event.hu) current.labels.push(String(event.hu));
    else if (event.label) current.labels.push(String(event.label));
    groups.set(date, current);
  });

  const items = Array.from(groups.values()).sort((a, b) => a.date.localeCompare(b.date));
  const minGapDays = 4;
  const maxLanes = 4;
  const laneLastDay = [];
  items.forEach((item, index) => {
    const day = dayNumber(item.date);
    let lane = laneLastDay.findIndex(lastDay => day - lastDay >= minGapDays);
    if (lane === -1) lane = Math.min(laneLastDay.length, maxLanes - 1);
    laneLastDay[lane] = day;
    item.lane = lane;
    item.offsetDirection = index % 2 === 0 ? 1 : -1;
  });
  const laneCount = Math.max(1, ...items.map(item => (item.lane || 0) + 1));
  const shapes = items.map(item => ({
    type: 'line',
    xref: 'x',
    yref: 'paper',
    x0: item.date,
    x1: item.date,
    y0: 0,
    y1: 1,
    line: { color: '#d97706', width: 1.5, dash: 'dot' },
  }));
  const annotations = items.map(item => {
    const scopeLabel = compactScopeLabel(item.labels);
    const lane = item.lane || 0;
    const horizontalOffset = item.offsetDirection * (16 + (lane % 2) * 8);
    return {
      xref: 'x',
      yref: 'paper',
      x: item.date,
      y: 1,
      xanchor: 'center',
      yanchor: 'bottom',
      text: `+${formatMetric(item.value, unit === 'SP' ? 1 : 0)} ${formatScopeUnit(item.value)}${scopeLabel ? `<br>${scopeLabel}` : ''}`,
      showarrow: true,
      arrowhead: 2,
      ax: horizontalOffset,
      ay: -28 - lane * 24,
      align: 'center',
      font: { size: 9, color: '#d97706' },
      bgcolor: 'rgba(255,255,255,.86)',
      bordercolor: 'rgba(217,119,6,.35)',
      borderpad: 3,
    };
  });
  return { shapes, annotations, topMargin: annotations.length ? 76 + (laneCount - 1) * 24 : 30 };
}

function chartBurndown(rows, type, l1, l2, l3, options = {}) {
  if (!rows) return { traces: null };
  const valid = rows.filter(r => r[0] !== null);
  const dates = valid.map(r => r[0]);
  const meta  = valid.map(r => r[1]);
  const plan  = valid.map(r => r[2]);
  const rlz   = valid.map(r => r[3]);
  const scopeTotal = valid.map(r => r[4]);
  const metaOriginal = valid.map(r => r[5]);
  const hasScope = (options.scopeEvents || []).length || valid.some(r => Number(r[6] || 0) > 0);

  const mk = (name, y, color, dash) => type === 'bar_v'
    ? { type:'bar', name, x:dates, y, marker:{ color } }
    : {
        type:'scatter', mode:'lines', name, x:dates, y,
        line:{ color, dash:dash||'solid', width:2.5 },
        fill: type==='area' ? 'tozeroy' : 'none',
        fillcolor: type==='area' ? color+'22' : undefined,
      };

  const traces = hasScope
    ? [
        mk('Meta original', metaOriginal, pc(8), 'dash'),
        mk('Meta revisada', meta, pc(3), 'dash'),
        mk('Escopo acumulado', scopeTotal, pc(9), 'dot'),
        mk(l2, plan, pc(10)),
        mk(l3, rlz, pc(0)),
      ]
    : [mk(l1, meta, pc(8), 'dash'), mk(l2, plan, pc(10)), mk(l3, rlz, pc(0))];
  const eventVisuals = buildScopeEventMarkers(options.scopeEvents || [], options.scopeUnit || 'tarefas', options.scopeValueKey || 'weight');
  const topMargin = eventVisuals.topMargin || 30;
  return {
    traces,
    layout: plotLayout({
      barmode:'group',
      xaxis:{ type:'date', tickformat:'%d/%m' },
      yaxis:{ title:{ text:'Tarefas' } },
      margin:{ t:topMargin,r:20,b:50,l:55 },
      shapes: eventVisuals.shapes,
      annotations: eventVisuals.annotations,
    }),
  };
}

/* â”€â”€ Burndown SP â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€ */
function chartBurndownSP(bsp, type) {
  if (!bsp?.rows) return { traces: null };
  const valid  = bsp.rows.filter(r => r[0] !== null);
  const dates  = valid.map(r => r[0]);
  const meta   = valid.map(r => r[1]);
  const rlz    = valid.map(r => r[2]);
  const scopeTotal = valid.map(r => r[3]);
  const metaOriginal = valid.map(r => r[4]);
  const hasScope = (bsp.scope_events || []).length || valid.some(r => Number(r[5] || 0) > 0);
  const totalSP = bsp.total_sp || 0;

  // Tabela SP por HU como anotação em tooltip
  const huSP = bsp.hu_sp || {};
  const huLines = Object.entries(huSP)
    .sort((a, b) => b[1] - a[1])
    .slice(0, 10)
    .map(([hu, sp]) => `${(dashData.hu_full_names?.[hu] || hu).substring(0, 45)}: ${sp} SP`)
    .join('<br>');

  const mk = (name, y, color, dash) => type === 'bar_v'
    ? { type:'bar', name, x:dates, y, marker:{ color } }
    : {
        type:'scatter', mode:'lines', name, x:dates, y,
        line:{ color, dash:dash||'solid', width:2.5 },
        fill: type==='area' ? 'tozeroy' : 'none',
        fillcolor: type==='area' ? color+'22' : undefined,
      };

  const traces = hasScope
    ? [
        mk('Meta original', metaOriginal, pc(8), 'dash'),
        mk('Meta revisada', meta, pc(3), 'dash'),
        mk('Escopo acumulado', scopeTotal, pc(9), 'dot'),
        mk('A Realizar (SP)', rlz, pc(0)),
      ]
    : [mk('Meta Linear', meta, pc(8), 'dash'), mk('A Realizar (SP)', rlz, pc(0))];
  const eventVisuals = buildScopeEventMarkers(bsp.scope_events || [], 'SP', 'sp');
  const topMargin = eventVisuals.topMargin || 30;
  return {
    traces,
    layout: plotLayout({
      barmode:'group',
      xaxis:{ type:'date', tickformat:'%d/%m' },
      yaxis:{ title:{ text:`SP (total: ${totalSP})` } },
      margin:{ t:topMargin, r:20, b:50, l:65 },
      shapes: eventVisuals.shapes,
      annotations: [
        ...eventVisuals.annotations,
        ...(huLines ? [{
        xref:'paper', yref:'paper', x:1, y:1, xanchor:'right', yanchor:'top',
        text: `<b>SP por HU</b><br>${huLines}`,
        showarrow: false, align:'right',
        font:{ size:10, color:'var(--muted)' },
        bgcolor: 'rgba(0,0,0,0)', bordercolor:'rgba(0,0,0,0)',
      }] : []),
      ],
    }),
  };
}

function chartBurnup(rows, type, options = {}) {
  if (!rows) return { traces: null };
  const valid = rows.filter(r => r[0] !== null);
  if (!valid.length) return { traces: null };

  const metaIndex = Number.isInteger(options.metaIndex) ? options.metaIndex : 1;
  const planIndex = Number.isInteger(options.planIndex) ? options.planIndex : 2;
  const remainingIndex = Number.isInteger(options.remainingIndex) ? options.remainingIndex : 3;
  const scopeIndex = Number.isInteger(options.scopeIndex) ? options.scopeIndex : 4;
  const metaOriginalIndex = Number.isInteger(options.metaOriginalIndex) ? options.metaOriginalIndex : 5;
  const addedIndex = Number.isInteger(options.addedIndex) ? options.addedIndex : 6;
  const fallbackValues = valid.flatMap(row => [row[1], row[2], row[3], row[4]].map(Number).filter(Number.isFinite));
  const optionFallbackTotal = Number(options.fallbackTotal);
  const fallbackTotal = Number.isFinite(optionFallbackTotal) && optionFallbackTotal > 0
    ? optionFallbackTotal
    : Math.max(0, ...fallbackValues);
  const clampMetric = value => {
    const numeric = Number(value);
    return Math.max(Number((Number.isFinite(numeric) ? numeric : 0).toFixed(2)), 0);
  };
  const metricAt = (row, index) => {
    if (!Number.isInteger(index) || index < 0) return null;
    const value = Number(row[index]);
    return Number.isFinite(value) ? value : null;
  };
  const dates = valid.map(r => r[0]);
  const scopeTotal = valid.map(r => {
    const scoped = Number(r[scopeIndex]);
    return Number.isFinite(scoped) ? scoped : fallbackTotal;
  });
  const delivered = valid.map((r, index) => {
    const remaining = metricAt(r, remainingIndex);
    return clampMetric(scopeTotal[index] - (remaining ?? 0));
  });

  let cumulativeAdded = 0;
  const originalScope = valid.map((r, index) => {
    const addedToday = metricAt(r, addedIndex) ?? 0;
    cumulativeAdded += addedToday;
    return clampMetric(scopeTotal[index] - cumulativeAdded);
  });
  const hasScope = (options.scopeEvents || []).length || valid.some(r => Number(r[addedIndex] || 0) > 0);
  const toDeliveredTarget = (scopeSeries, remainingTargetIndex) => valid.map((r, index) => {
    const remainingTarget = metricAt(r, remainingTargetIndex);
    return clampMetric(scopeSeries[index] - (remainingTarget ?? 0));
  });
  const metaDelivered = toDeliveredTarget(scopeTotal, metaIndex);
  const hasPlan = Number.isInteger(planIndex) && planIndex >= 0 && valid.some(r => metricAt(r, planIndex) !== null);
  const planDelivered = hasPlan ? toDeliveredTarget(scopeTotal, planIndex) : null;
  const hasMetaOriginal = hasScope
    && Number.isInteger(metaOriginalIndex)
    && metaOriginalIndex >= 0
    && valid.some(r => metricAt(r, metaOriginalIndex) !== null);
  const metaOriginalDelivered = hasMetaOriginal ? toDeliveredTarget(originalScope, metaOriginalIndex) : null;

  const mk = (name, y, color, dash) => type === 'bar_v'
    ? { type:'bar', name, x:dates, y, marker:{ color } }
    : {
        type:'scatter', mode:'lines', name, x:dates, y,
        line:{ color, dash:dash||'solid', width:2.5 },
        fill: type==='area' ? 'tozeroy' : 'none',
        fillcolor: type==='area' ? color+'22' : undefined,
      };

  const traces = hasScope
    ? [
        ...(metaOriginalDelivered ? [mk('Meta original', metaOriginalDelivered, pc(8), 'dash')] : []),
        mk('Meta revisada', metaDelivered, pc(3), 'dash'),
        ...(planDelivered ? [mk('Planejado', planDelivered, pc(10))] : []),
        mk('Escopo acumulado', scopeTotal, pc(9), 'dot'),
        mk('Entregue', delivered, pc(0)),
      ]
    : [
        mk('Meta Linear', metaDelivered, pc(8), 'dash'),
        ...(planDelivered ? [mk('Planejado', planDelivered, pc(10))] : []),
        mk('Escopo', scopeTotal, pc(9), 'dot'),
        mk('Entregue', delivered, pc(0)),
      ];
  const eventVisuals = buildScopeEventMarkers(
    options.scopeEvents || [],
    options.scopeUnit || 'tarefas',
    options.scopeValueKey || 'count'
  );
  const topMargin = eventVisuals.topMargin || 30;

  return {
    traces,
    layout: plotLayout({
      barmode:'group',
      xaxis:{ type:'date', tickformat:'%d/%m' },
      yaxis:{ title:{ text: options.yTitle || 'Tarefas' } },
      margin:{ t:topMargin, r:20, b:50, l:55 },
      shapes: eventVisuals.shapes,
      annotations: eventVisuals.annotations,
    }),
  };
}

/* â”€â”€ CFD â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€ */
function chartCFD(cfd, type) {
  if (!cfd?.dates?.length) return { traces: null };
  const mk = (name, y, color) => type === 'bar_v'
    ? { type:'bar', name, x:cfd.dates, y, marker:{ color } }
    : {
        type:'scatter', mode:'lines', name, x:cfd.dates, y,
        line:{ color, width:2.5 },
        fill: type==='area' ? 'tonexty' : 'none',
        fillcolor: type==='area' ? color+'44' : undefined,
        stackgroup: type==='area' ? 'cfd' : undefined,
      };
  return {
    traces: [mk('Concluído', cfd.done, pc(2)), mk('Em progresso', cfd.doing, pc(1)), mk('A fazer', cfd.todo, '#7a8fa6')],
    layout: plotLayout({ barmode:'stack', xaxis:{ type:'date', tickformat:'%d/%m' }, yaxis:{ title:{ text:'Tarefas' } } }),
  };
}

/* â”€â”€ WIP â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€ */
function chartWIP(wip, type) {
  if (!wip?.dates?.length) return { traces: null };
  const cw = PALETTES[activePaletteName]?.colorway || PALETTES.teal.colorway;
  const traces = (wip.buckets || []).map((bkt, i) => {
    const y = wip.matrix[bkt] || [], c = cw[i % cw.length];
    return type === 'bar_v'
      ? { type:'bar', name:bkt, x:wip.dates, y, marker:{ color:c } }
      : {
          type:'scatter', mode:'lines', name:bkt, x:wip.dates, y,
          line:{ color:c, width:2 },
          fill: type==='area' ? 'tonexty' : 'none',
          fillcolor: type==='area' ? c+'33' : undefined,
          stackgroup: type==='area' ? 'wip' : undefined,
        };
  });
  return {
    traces,
    layout: plotLayout({ barmode:'stack', xaxis:{ type:'date', tickformat:'%d/%m' }, yaxis:{ title:{ text:'Tarefas' } } }),
  };
}

/* â”€â”€ Grouped bars / pie / donut â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€ */
function chartGrouped(rows, type, l1, l2) {
  if (!rows?.length) return { traces: null };
  const labels   = rows.map(r => cleanChartLabel(r[0]));
  const doneVals = rows.map(r => Number(r[1]) || 0);
  const pendVals = rows.map(r => Number(r[2]) || 0);
  const totals = labels.map((_, index) => doneVals[index] + pendVals[index]);
  const cw = PALETTES[activePaletteName]?.colorway || PALETTES.teal.colorway;

  if (type === 'pie' || type === 'donut') {
    const total = rows.map(r => (r[1]||0)+(r[2]||0));
    const shortLabels = labels.map(label => shortenChartLabel(label, 34));
    return {
      traces: [{ type:'pie', labels:shortLabels, values:total, hole:type==='donut'?0.5:0,
        customdata:labelHoverData(labels), marker:{ colors:cw },
        textinfo:'percent', textposition:'inside', insidetextorientation:'radial',
        automargin:true,
        hovertemplate:'<b>%{customdata}</b><br>Total: %{value}<br>%{percent}<extra></extra>' }],
      layout: plotLayout({
        margin:{ t:30,r:20,b:20,l:20 },
        showlegend:true,
        uniformtext:{ minsize:10, mode:'hide' },
      }),
    };
  }
  const horiz = type === 'bar_h';
  const hoverData = labels.map((label, index) => [
    label, doneVals[index], pendVals[index], totals[index],
    totals[index] > 0 ? (doneVals[index] / totals[index] * 100).toFixed(1) : '0.0',
  ]);
  const mk = (name, vals, color) => ({
    type:'bar', name,
    x: horiz ? vals : labels,
    y: horiz ? labels : vals,
    orientation: horiz ? 'h' : 'v',
    marker:{ color },
    customdata: hoverData,
    hovertemplate: '<b>%{customdata[0]}</b><br>' + name + ': %{'+(horiz ? 'x' : 'y')+'}<br>' +
      l1 + ': %{customdata[1]}<br>' + l2 + ': %{customdata[2]}<br>' +
      'Total: %{customdata[3]}<br>' + l1 + ': %{customdata[4]}% do total<extra></extra>',
  });
  return {
    traces: [mk(l1, doneVals, pc(0)), mk(l2, pendVals, pc(1))],
    layout: plotLayout({ barmode:'group',
      margin:{ t:30,r:20, b:horiz?40:90, l:horiz?190:55 },
      xaxis: horiz
        ? { tickangle:0 }
        : { ...labelAxis(labels, 32), tickangle:-30 },
      yaxis: horiz ? { ...labelAxis(labels, 34) } : undefined }),
  };
}

/* â”€â”€ In/Out â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€ */
function chartInOut(inOut, type) {
  if (!inOut?.length) return { traces: null };
  const labels = inOut.map(r => r[0]);
  const vals   = inOut.map(r => r[1]);
  if (type === 'bar_v') {
    return {
      traces: [{ type:'bar', x:labels, y:vals, marker:{ color:[pc(0),pc(1)] } }],
      layout: plotLayout({ showlegend:false }),
    };
  }
  return {
    traces: [{ type:'pie', labels, values:vals, hole:type==='donut'?0.5:0,
      marker:{ colors:[pc(0),pc(1)] }, textinfo:'label+percent' }],
    layout: plotLayout({ margin:{ t:30,r:20,b:20,l:20 } }),
  };
}

/* Dispersão */
function chartDispersao(data, type) {
  const cw = PALETTES[activePaletteName]?.colorway || PALETTES.teal.colorway;
  const cts = data?.cts || {};
  const disp = data?.dispersao || {};

  let dates = [];
  let labels = [];
  let matrix = [];
  let outside = [];

  if (cts?.dates?.length && Array.isArray(cts.matrix)) {
    dates = cts.dates.slice();
    labels = (cts.hu_labels || []).map(v => String(v || '').trim()).filter(Boolean);
    matrix = labels.map((_, i) => Array.isArray(cts.matrix[i]) ? cts.matrix[i] : []);
    outside = Array.isArray(cts.fora_hu) ? cts.fora_hu : [];
  } else {
    const dayCount = Number(disp?.days);
    if (Array.isArray(disp?.days)) {
      dates = disp.days.slice();
    } else if (Number.isFinite(dayCount) && dayCount > 0 && disp?.bd_start) {
      const start = new Date(`${disp.bd_start}T00:00:00`);
      if (!Number.isNaN(start.getTime())) {
        for (let i = 0; i < dayCount; i++) {
          const dt = new Date(start);
          dt.setDate(start.getDate() + i);
          dates.push(dt.toISOString().slice(0, 10));
        }
      }
    }

    const huList = Array.isArray(disp?.hu_list) ? disp.hu_list : [];
    const huMatrix = disp?.hu_matrix || {};
    labels = huList.map(hu => data?.hu_full_names?.[hu] || hu);
    matrix = huList.map((hu, i) => {
      if (Array.isArray(huMatrix)) return Array.isArray(huMatrix[i]) ? huMatrix[i] : [];
      if (Array.isArray(huMatrix?.[hu])) return huMatrix[hu];
      return [];
    });
    outside = Array.isArray(disp?.nao_hu_daily) ? disp.nao_hu_daily : [];
  }

  if (!dates.length) return { traces: null };

  const parseDayOfMonth = (value, fallbackIndex) => {
    if (typeof value === 'number' && Number.isFinite(value)) return value;
    const raw = String(value ?? '').trim();
    if (!raw) return fallbackIndex + 1;
    const iso = raw.match(/^(\d{4})-(\d{2})-(\d{2})$/);
    if (iso) return Number(iso[3]);
    const slash = raw.match(/^(\d{1,2})[\/-](\d{1,2})(?:[\/-](\d{2,4}))?$/);
    if (slash) return Number(slash[1]);
    const dt = new Date(raw);
    if (!Number.isNaN(dt.getTime())) return dt.getDate();
    const num = Number(raw);
    return Number.isFinite(num) ? num : fallbackIndex + 1;
  };

  const parseDateMaybe = (value) => {
    const raw = String(value ?? '').trim();
    if (!raw) return null;
    const iso = raw.match(/^(\d{4})-(\d{2})-(\d{2})$/);
    if (iso) {
      const dt = new Date(`${iso[1]}-${iso[2]}-${iso[3]}T00:00:00`);
      return Number.isNaN(dt.getTime()) ? null : dt;
    }
    const fullSlash = raw.match(/^(\d{1,2})\/(\d{1,2})\/(\d{2,4})$/);
    if (fullSlash) {
      const yyyy = fullSlash[3].length === 2 ? `20${fullSlash[3]}` : fullSlash[3];
      const mm = String(fullSlash[2]).padStart(2, '0');
      const dd = String(fullSlash[1]).padStart(2, '0');
      const dt = new Date(`${yyyy}-${mm}-${dd}T00:00:00`);
      return Number.isNaN(dt.getTime()) ? null : dt;
    }
    return null;
  };

  const parsedDates = dates.map(parseDateMaybe);
  const useDateAxis = parsedDates.every(Boolean);
  const toIsoLocal = (dt) => {
    const yyyy = dt.getFullYear();
    const mm = String(dt.getMonth() + 1).padStart(2, '0');
    const dd = String(dt.getDate()).padStart(2, '0');
    return `${yyyy}-${mm}-${dd}`;
  };
  const toDayMonth = (dt) => {
    const dd = String(dt.getDate()).padStart(2, '0');
    const mm = String(dt.getMonth() + 1).padStart(2, '0');
    return `${dd}/${mm}`;
  };

  const xValues = useDateAxis
    ? parsedDates.map(dt => toIsoLocal(dt))
    : dates.map((value, index) => parseDayOfMonth(value, index));
  const traces = [];
  const allBubbleSizes = [];

  const addTrace = (name, rowValues, yIndex, color, symbol = 'circle') => {
    const xPts = [];
    const yPts = [];
    const bubbleSize = [];
    const tooltip = [];

    xValues.forEach((xValue, dayIndex) => {
      const count = Number(rowValues?.[dayIndex] || 0);
      if (!(count > 0)) return;
      xPts.push(xValue);
      yPts.push(yIndex);
      bubbleSize.push(count);
      const dayLabel = useDateAxis ? toDayMonth(parsedDates[dayIndex]) : xValue;
      tooltip.push(`${name}<br>Dia ${dayLabel}: ${count} entrega(s)`);
      allBubbleSizes.push(count);
    });

    if (!xPts.length) return;
    traces.push({
      type: 'scatter',
      mode: 'markers',
      name,
      x: xPts,
      y: yPts,
      text: tooltip,
      hovertemplate: '%{text}<extra></extra>',
      marker: {
        color,
        symbol,
        size: bubbleSize,
        sizemode: 'area',
        sizemin: 7,
        opacity: 0.8,
        line: { width: 0.7, color: 'rgba(255,255,255,0.38)' },
      },
    });
  };

  labels.forEach((label, idx) => addTrace(label, matrix[idx] || [], (idx + 1) * 2, cw[idx % cw.length]));
  const outsideHasData = outside.some(value => Number(value) > 0);
  if (outsideHasData) addTrace('Fora de HU', outside, (labels.length + 1) * 2, '#8E9BA9', 'x');

  if (!traces.length) return { traces: null };

  const maxBubble = Math.max(...allBubbleSizes, 1);
  const sizeref = (2 * maxBubble) / (36 ** 2);
  traces.forEach(trace => { trace.marker.sizeref = sizeref; });

  const msPerDay = 24 * 60 * 60 * 1000;
  const xMin = useDateAxis
    ? new Date(parsedDates[0].getTime() - (3 * msPerDay))
    : Math.min(...xValues);
  const xMax = useDateAxis
    ? new Date(parsedDates[parsedDates.length - 1].getTime() + (3 * msPerDay))
    : Math.max(...xValues);
  const yMax = labels.length + (outsideHasData ? 1 : 0);

  return {
    traces,
    layout: plotLayout({
      xaxis: {
        title: { text: 'Data (dia do mês)' },
        ...(useDateAxis
          ? {
              type: 'date',
              tickmode: 'linear',
              dtick: msPerDay,
              tickformat: '%d',
              range: [toIsoLocal(xMin), toIsoLocal(xMax)],
            }
          : {
              tickmode: 'linear',
              dtick: 1,
              range: [xMin - 3, xMax + 3],
            }),
      },
      yaxis: {
        showticklabels: false,
        ticks: '',
        title: { text: '' },
        range: [0, (yMax + 1) * 2],
      },
      legend: {
        orientation: 'h',
        x: 0,
        xanchor: 'left',
        y: 1.1,
        yanchor: 'bottom',
        bgcolor: 'transparent',
        itemsizing: 'constant',
      },
      margin: { t: 90, r: 20, b: 70, l: 20 },
    }),
  };
}

/* â”€â”€ Histograma â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€ */
function chartHistograma(hist31, indicativos, type) {
  if (!hist31?.some(v => v > 0)) return { traces: null };
  const days  = hist31.map((_, i) => `${i+1} dia${i+1===1?'':'(s)'}`);
  const trace = type === 'line'
    ? { type:'scatter', mode:'lines+markers', x:days, y:hist31, name:'Freq.',
        line:{ color:pc(0), width:2.5 }, marker:{ color:pc(0), size:6 } }
    : { type:'bar', x:days, y:hist31, marker:{ color:pc(0) }, name:'Tarefas' };
  return {
    traces: [trace],
    layout: plotLayout({ xaxis:{ title:{ text:'Cycle Time (dias)' } }, yaxis:{ title:{ text:'Qtd Tarefas' } }, showlegend:false }),
  };
}

/* â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•
   KPI CARDS
â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â• */
function metricNumber(...values) {
  for (const value of values) {
    if (value === null || value === undefined || value === '') continue;
    const parsed = Number(value);
    if (Number.isFinite(parsed)) return parsed;
  }
  return null;
}

function formatMetric(value, digits = 1) {
  const parsed = metricNumber(value);
  if (parsed === null) return '-';
  if (digits > 0) return parsed.toFixed(digits);
  return Number.isInteger(parsed) ? String(parsed) : parsed.toFixed(1).replace(/\.0$/, '');
}

function formatMetricPct(value) {
  const parsed = metricNumber(value);
  return parsed === null ? '-' : `${formatMetric(parsed, 1)}%`;
}

function renderMetricSections(body, sections, supportHtml = '') {
  body.innerHTML = `<div class="kpi-groups metric-groups">${
    sections.map(section => `<section class="kpi-section">
      <div class="kpi-section-head">${esc(section.title)}</div>
      <div class="kpi-grid">${
        section.items.map(i => {
          const infoLines = Array.isArray(i.info) ? i.info.filter(Boolean) : [];
          const info = infoLines.length ? `<span class="kpi-info">
            <button class="kpi-info-trigger" type="button" aria-label="Detalhes de ${esc(i.label)}">i</button>
            <span class="kpi-tooltip" role="tooltip">${infoLines.map(line => `<span>${esc(line)}</span>`).join('')}</span>
          </span>` : '';
          return `<div class="kpi-card${infoLines.length ? ' has-tooltip' : ''}">
          <div class="kpi-card-head">
            <div class="kpi-label">${esc(i.label)}</div>
            ${info}
          </div>
          <div class="kpi-value">${esc(i.value ?? '-')}</div>
          <div class="kpi-unit">${esc(i.unit || '')}</div>
          ${i.sub ? `<div class="kpi-sub">${esc(i.sub)}</div>` : ''}
        </div>`;
        }).join('')
      }</div>
    </section>`).join('')
  }</div>${supportHtml}`;
}

function metricTable(headers, rows) {
  if (!rows?.length) return '';
  return `<div class="metric-table-wrap"><table class="metric-table">
    <thead><tr>${headers.map(h => `<th>${esc(h)}</th>`).join('')}</tr></thead>
    <tbody>${rows.map(row => `<tr>${row.map(cell => `<td>${esc(cell)}</td>`).join('')}</tr>`).join('')}</tbody>
  </table></div>`;
}


function chartCardInfo(label, subtitle) {
  const key = label + "|" + subtitle;
  const info = {
    "Throughput semanal|Tarefas": ["Média semanal de tarefas concluídas.", "O gráfico mostra as entregas agrupadas por semana."],
    "Throughput semanal|Story Points": ["Média semanal de Story Points concluídos.", "O cálculo usa o peso proporcional de SP das tarefas."],
    "Eficiencia de fluxo|Total": ["Compara Cycle Time e Lead Time por tarefa, HU e Story Point.", "Valores maiores indicam menor tempo de espera antes do trabalho ativo."],
    "Eficiencia de fluxo|Semanal": ["Mostra a média semanal da eficiência por tarefa, HU e Story Point.", "Semanas sem amostra válida não entram na média."],
    "Concluídas x Pendentes|Tarefas": ["Distribui as tarefas entre concluídas e pendentes.", "A soma das fatias representa o total de tarefas."],
    "Concluídos x Pendentes|Story Points": ["Distribui os Story Points entre concluídos e pendentes.", "Usa o saldo oficial do burndown de SP quando disponível."],
    "Lead x Cycle|Por SP": ["Compara Lead Time e Cycle Time ponderados por Story Point.", "A ponderação usa o peso proporcional de SP das tarefas."],
    "Lead x Cycle|Por HU": ["Compara o Lead Time e o Cycle Time médios das HUs.", "Cada fatia representa sua proporção relativa de dias."],
    "Lead x Cycle|Por tarefa": ["Compara Lead Time e Cycle Time médios das tarefas concluídas.", "Lead inclui espera; Cycle considera apenas o tempo ativo."],
  }[key] || [];
  if (!info.length) return "";
  return "<span class=\"kpi-info\"><button class=\"kpi-info-trigger\" type=\"button\" aria-label=\"Detalhes de " + esc(label) + "\">i</button><span class=\"kpi-tooltip\" role=\"tooltip\">" + info.map(line => "<span>" + esc(line) + "</span>").join("") + "</span></span>";
}
function buildFlowChartsHtml() {
  const charts = [
    { id: 'flowChartThroughputTasks', title: 'Throughput semanal', subtitle: 'Tarefas' },
    { id: 'flowChartThroughputSp', title: 'Throughput semanal', subtitle: 'Story Points' },
    { id: 'flowChartEfficiencyTotal', title: 'Eficiencia de fluxo', subtitle: 'Total' },
    { id: 'flowChartEfficiencyWeekly', title: 'Eficiencia de fluxo', subtitle: 'Semanal' },
  ];
  return `<div class="kpi-groups metric-groups kpi-chart-groups">
    <section class="kpi-section kpi-chart-section">
      <div class="kpi-section-head">Gr\u00e1ficos Fluxo</div>
      <div class="kpi-chart-grid">${
        charts.map(chart => `<article class="kpi-chart-card">
          <div class="kpi-chart-head">
            <div class="kpi-label">${esc(chart.title)}</div>
            ${chartCardInfo(chart.title, chart.subtitle)}
            <div class="kpi-unit">${esc(chart.subtitle)}</div>
          </div>
          <div class="kpi-chart-plot" id="${esc(chart.id)}"></div>
        </article>`).join('')
      }</div>
    </section>
  </div>`;
}

function buildFlowBarTrace(labels, values, name, color, unitLabel, valueDigits = 0) {
  const rows = labels.map((label, index) => ({
    label,
    value: metricNumber(values[index]) ?? 0,
  }));
  if (!rows.some(row => row.value > 0)) return null;
  return {
    type: 'bar',
    name,
    x: rows.map(row => row.label),
    y: rows.map(row => row.value),
    marker: { color },
    hovertemplate: `<b>%{x}</b><br>${unitLabel}: %{y:.${valueDigits}f}<extra></extra>`,
  };
}

function buildFlowBarLayout() {
  return plotLayout({
    showlegend: false,
    margin: { t: 8, r: 10, b: 52, l: 48 },
    height: 245,
    xaxis: { tickangle: -25, automargin: true },
    yaxis: { rangemode: 'tozero' },
  });
}

function renderFlowMetricCharts() {
  if (!window.Plotly) return;
  const m = dashData.flow_metrics || {};
  const rows = Array.isArray(m.throughput_rows) ? m.throughput_rows : [];
  const labels = rows.map(row => row[0]);
  const tasks = rows.map(row => row[1]);
  const storyPoints = rows.map(row => row[2]);
  const charts = [
    {
      id: 'flowChartThroughputTasks',
      traces: [buildFlowBarTrace(labels, tasks, 'Tarefas', pc(0), 'Tarefas', 0)].filter(Boolean),
      layout: buildFlowBarLayout(),
    },
    {
      id: 'flowChartThroughputSp',
      traces: [buildFlowBarTrace(labels, storyPoints, 'Story Points', pc(3), 'Story Points', 1)].filter(Boolean),
      layout: buildFlowBarLayout(),
    },
    {
      id: 'flowChartEfficiencyTotal',
      traces: [buildKpiPieTrace(
        ['Por tarefa', 'Por HU', 'Por Story Point'],
        [m.flow_eff_task, m.flow_eff_hu, m.flow_eff_sp],
        [pc(0), pc(3), pc(4)],
        'Eficiencia',
        1,
      )].filter(Boolean),
      layout: buildKpiPieLayout(),
    },
    {
      id: 'flowChartEfficiencyWeekly',
      traces: [buildKpiPieTrace(
        ['Por tarefa', 'Por HU', 'Por Story Point'],
        [m.flow_eff_task_weekly, m.flow_eff_hu_weekly, m.flow_eff_sp_weekly],
        [pc(0), pc(3), pc(4)],
        'Eficiencia',
        1,
      )].filter(Boolean),
      layout: buildKpiPieLayout(),
    },
  ];

  charts.forEach(chart => {
    const el = document.getElementById(chart.id);
    if (!el) return;
    if (!chart.traces.length) {
      el.innerHTML = '<div class="kpi-chart-empty">Sem dados para exibir</div>';
      return;
    }
    Plotly.react(el, chart.traces, chart.layout, { responsive: true, displayModeBar: false });
  });
}
function renderFlowMetrics(body) {
  ensureAdvancedMetrics();
  const m = dashData.flow_metrics || {};
  const wipInfo = [
    'M\u00e9dia de tarefas em andamento por dia.',
    `Dias analisados: ${formatMetric(m.wip_days, 0)}.`,
    'Conta tarefas iniciadas e ainda n\u00e3o conclu\u00eddas em cada dia da janela.',
  ];
  const throughputInfo = [
    'M\u00e9dia semanal de tarefas conclu\u00eddas.',
    `Entregas no per\u00edodo: ${formatMetric(m.throughput_total, 0)}.`,
    `Semanas medidas: ${formatMetric(m.throughput_weeks, 0)}.`,
  ];
  const throughputSpInfo = [
    'M\u00e9dia semanal de Story Points conclu\u00eddos.',
    `SP entregues no per\u00edodo: ${formatMetric(m.throughput_sp_total, 1)}.`,
    `Semanas medidas: ${formatMetric(m.throughput_weeks, 0)}.`,
    'Cada tarefa conclu\u00edda contribui com o peso de SP proporcional da sua HU.',
  ];
  const weeksInfo = [
    'Quantidade de semanas usadas no c\u00e1lculo de throughput.',
    'A janela segue o per\u00edodo de datas dispon\u00edvel para a sprint.',
  ];
  const flowEffTaskInfo = [
    'Efici\u00eancia de fluxo por tarefa.',
    'F\u00f3rmula: Cycle Time m\u00e9dio de tarefa / Lead Time m\u00e9dio de tarefa.',
    'Quanto maior, menor o tempo de espera antes do trabalho ativo.',
  ];
  const flowEffTaskWeeklyInfo = [
    'M\u00e9dia das efici\u00eancias semanais por tarefa.',
    'Em cada semana: Cycle Time m\u00e9dio das tarefas conclu\u00eddas / Lead Time m\u00e9dio das tarefas conclu\u00eddas.',
    'Semanas sem amostra v\u00e1lida n\u00e3o entram na m\u00e9dia.',
  ];
  const flowEffHuInfo = [
    'Efici\u00eancia de fluxo agregada por HU.',
    'F\u00f3rmula: Cycle Time m\u00e9dio por HU / Lead Time m\u00e9dio por HU.',
    'Usa as m\u00e9dias das tarefas agrupadas por HU.',
  ];
  const flowEffHuWeeklyInfo = [
    'M\u00e9dia das efici\u00eancias semanais por HU.',
    'Em cada semana, calcula as m\u00e9dias por HU das tarefas conclu\u00eddas naquela semana.',
    'Semanas sem HU com datas v\u00e1lidas n\u00e3o entram na m\u00e9dia.',
  ];
  const flowEffSpInfo = [
    'Efici\u00eancia ponderada por Story Point.',
    'F\u00f3rmula: Cycle Time por SP / Lead Time por SP.',
    'Depende de HUs com Story Points mapeados.',
  ];
  const flowEffSpWeeklyInfo = [
    'M\u00e9dia das efici\u00eancias semanais ponderadas por Story Point.',
    'Em cada semana, Cycle e Lead s\u00e3o ponderados pelo SP proporcional das tarefas conclu\u00eddas.',
    'Semanas sem SP mapeado n\u00e3o entram na m\u00e9dia.',
  ];
  const stddevInfo = [
    'Mede a dispers\u00e3o do Cycle Time das tarefas conclu\u00eddas.',
    `Amostra: ${formatMetric(m.cycle_time_stddev_count, 0)} tarefas.`,
    'Valores menores indicam fluxo mais previs\u00edvel.',
  ];
  const sections = [
    {
      title: 'Fluxo',
      items: [
        { label:'WIP m\u00e9dio', value:formatMetric(m.wip_avg, 1), unit:'tarefas/dia', sub:`${formatMetric(m.wip_days, 0)} dias analisados`, info: wipInfo },
        { label:'Throughput semanal', value:formatMetric(m.throughput_weekly_avg, 1), unit:'tarefas/semana', sub:`${formatMetric(m.throughput_total, 0)} entregas no per\u00edodo`, info: throughputInfo },
        { label:'Throughput semanal SP', value:formatMetric(m.throughput_sp_weekly_avg, 1), unit:'SP/semana', sub:`${formatMetric(m.throughput_sp_total, 1)} SP no per\u00edodo`, info: throughputSpInfo },
        { label:'Semanas medidas', value:formatMetric(m.throughput_weeks, 0), unit:'semanas', info: weeksInfo },
      ],
    },
    {
      title: 'Efici\u00eancia',
      items: [
        { label:'Por tarefa (total)', value:formatMetricPct(m.flow_eff_task), unit:'cycle / lead', info: flowEffTaskInfo },
        { label:'Por HU (total)', value:formatMetricPct(m.flow_eff_hu), unit:'cycle / lead', info: flowEffHuInfo },
        { label:'Por Story Point (total)', value:formatMetricPct(m.flow_eff_sp), unit:'cycle / lead', info: flowEffSpInfo },
        { label:'Por tarefa (semanal)', value:formatMetricPct(m.flow_eff_task_weekly), unit:'cycle / lead', info: flowEffTaskWeeklyInfo },
        { label:'Por HU (semanal)', value:formatMetricPct(m.flow_eff_hu_weekly), unit:'cycle / lead', info: flowEffHuWeeklyInfo },
        { label:'Por Story Point (semanal)', value:formatMetricPct(m.flow_eff_sp_weekly), unit:'cycle / lead', info: flowEffSpWeeklyInfo },
      ],
    },
    {
      title: 'Previsibilidade',
      items: [
        { label:'Desvio padr\u00e3o Cycle Time', value:formatMetric(m.cycle_time_stddev, 1), unit:'dias', sub:`${formatMetric(m.cycle_time_stddev_count, 0)} tarefas na amostra`, info: stddevInfo },
      ],
    },
  ];
  const rows = (m.throughput_rows || []).map(row => [row[0], row[1], formatMetric(row[2], 1)]);
  renderMetricSections(body, sections, buildFlowChartsHtml() + metricTable(['Semana', 'Conclu\u00eddas', 'Story Points'], rows));
  requestAnimationFrame(renderFlowMetricCharts);
}

function renderScopeQualityMetrics(body) {
  ensureAdvancedMetrics();
  const m = dashData.scope_quality_metrics || {};
  const sayDoInfo = [
    'Compara Story Points entregues com Story Points prometidos.',
    `SP entregues: ${formatMetric(m.delivered_sp, 1)}.`,
    `SP prometidos: ${formatMetric(m.committed_sp, 1)}.`,
    'Tarefas sem HU/SP n\u00e3o alteram este ratio.',
  ];
  const committedSpInfo = [
    'Total de Story Points planejados para a sprint.',
    'Vem da soma dos SP mapeados nas HUs ou do KPI de storypoints.',
  ];
  const deliveredSpInfo = [
    'Story Points de HUs conclu\u00eddas.',
    'Uma HU s\u00f3 entra como entregue quando todas as tarefas daquela HU est\u00e3o conclu\u00eddas.',
  ];
  const bugDensityInfo = [
    'Quantidade de tarefas bug/ajuste vinculadas a HU dividida pelo total de HUs.',
    `Bugs/ajustes vinculados a HU: ${formatMetric(m.bug_task_with_hu_count, 0)}.`,
    'Itens sem HU aparecem no total de tarefas bug/ajuste, mas n\u00e3o entram nesta densidade.',
  ];
  const bugTaskInfo = [
    'Conta tarefas com r\u00f3tulos contendo bug ou ajuste.',
    `Total encontrado: ${formatMetric(m.bug_task_count, 0)}.`,
    `Vinculadas a HU: ${formatMetric(m.bug_task_with_hu_count, 0)}.`,
  ];
  const bugHuInfo = [
    'Quantidade de HUs distintas com pelo menos uma tarefa bug/ajuste.',
    'Considera apenas tarefas bug/ajuste que possuem HU no t\u00edtulo ou nos r\u00f3tulos.',
  ];
  const impedimentInfo = [
    'Conta tarefas com tag ou bucket de impedimento/bloqueio.',
    `Total encontrado: ${formatMetric(m.impediment_task_count, 0)}.`,
    `HUs afetadas: ${formatMetric(m.impediment_hu_count, 0)}.`,
  ];
  const avgHuInfo = [
    'M\u00e9dia de Story Points por HU.',
    'Usa apenas HUs com SP extra\u00eddo do t\u00edtulo ou dos r\u00f3tulos.',
  ];
  const scopeCreepInfo = [
    'Tarefas classificadas como n\u00e3o previstas, imprevistas ou n\u00e3o mapeadas.',
    `Total: ${formatMetric(m.scope_creep_tasks, 0)} tarefas.`,
    m.scope_creep_task_pct != null ? `Participa\u00e7\u00e3o: ${formatMetricPct(m.scope_creep_task_pct)} do total.` : null,
  ];
  const scopeCreepSpInfo = [
    'Story Points estimados das tarefas de scope creep.',
    'Usa pesos de SP por HU quando esse mapeamento existe.',
    m.scope_creep_sp_pct != null ? `Participa\u00e7\u00e3o: ${formatMetricPct(m.scope_creep_sp_pct)} dos SP.` : null,
  ];
  const sections = [
    {
      title: 'Compromisso',
      items: [
        { label:'Say/Do Ratio', value:formatMetricPct(m.say_do_ratio), unit:'SP entregue / prometido', info: sayDoInfo },
        { label:'SP prometidos', value:formatMetric(m.committed_sp, 1), unit:'SP', info: committedSpInfo },
        { label:'SP entregues', value:formatMetric(m.delivered_sp, 1), unit:'SP', info: deliveredSpInfo },
      ],
    },
    {
      title: 'Qualidade',
      items: [
        { label:'Densidade bugs/HU', value:formatMetric(m.bug_density_avg, 2), unit:'tarefas por HU', info: bugDensityInfo },
        { label:'Tarefas bug/ajuste', value:formatMetric(m.bug_task_count, 0), unit:'tarefas', sub: m.bug_task_with_hu_count != null ? `${formatMetric(m.bug_task_with_hu_count, 0)} vinculadas a HU` : null, info: bugTaskInfo },
        { label:'HUs afetadas', value:formatMetric(m.bug_hu_count, 0), unit:'HUs', info: bugHuInfo },
        { label:'Impedimentos', value:formatMetric(m.impediment_task_count, 0), unit:'tarefas', sub: m.impediment_hu_count != null ? `${formatMetric(m.impediment_hu_count, 0)} HUs afetadas` : null, info: impedimentInfo },
      ],
    },
    {
      title: 'Escopo',
      items: [
        { label:'Tamanho m\u00e9dio HU', value:formatMetric(m.avg_hu_size_sp, 1), unit:'SP', info: avgHuInfo },
        { label:'Scope creep', value:formatMetric(m.scope_creep_tasks, 0), unit:'tarefas', sub: m.scope_creep_task_pct != null ? `${formatMetricPct(m.scope_creep_task_pct)} do total` : null, info: scopeCreepInfo },
        { label:'Scope creep em SP', value:formatMetric(m.scope_creep_sp, 1), unit:'SP', sub: m.scope_creep_sp_pct != null ? `${formatMetricPct(m.scope_creep_sp_pct)} dos SP` : null, info: scopeCreepSpInfo },
      ],
    },
  ];
  const rows = [
    ...(m.bug_rows || []).map(row => ['Bug/Ajuste', row[0], row[1], row[2]]),
    ...(m.impediment_rows || []).map(row => ['Impedimento', row[0], row[1], row[2]]),
  ];
  renderMetricSections(body, sections, metricTable(['Tag', 'HU', 'Tarefas', 'Tarefas HU'], rows));
}

function renderTimeHealthMetrics(body) {
  ensureAdvancedMetrics();
  const m = dashData.time_metrics || {};
  const statusLabel = {
    saudavel: 'Saud\u00e1vel',
    atencao: 'Aten\u00e7\u00e3o',
    alerta: 'Alerta',
  }[m.schedule_status] || '-';
  const deadline = formatDateOnlyPt(m.deadline_date);
  const operationalDeadline = formatDateOnlyPt(m.operational_deadline_date);
  const sprintStart = formatDateOnlyPt(m.sprint_effective_start);
  const workUnit = m.work_unit || '';
  const workUnitLabel = workUnit || 'unidades';
  const daysRemainingInfo = [
    'Conta os dias \u00fateis ainda dispon\u00edveis na janela operacional da sprint.',
    `In\u00edcio efetivo: ${sprintStart}.`,
    `\u00daltimo dia \u00fatil considerado: ${operationalDeadline}.`,
    `Decorridos: ${formatMetric(m.days_elapsed, 0)} de ${formatMetric(m.days_total, 0)} dias \u00fateis.`,
    `Restantes: ${formatMetric(m.days_remaining, 0)} dias \u00fateis (${formatMetricPct(m.days_remaining_pct)} do prazo \u00fatil).`,
  ];
  const workRemainingInfo = [
    'Mede o esfor\u00e7o ainda aberto na unidade principal do plano.',
    `Total planejado: ${formatMetric(m.work_total, 1)} ${workUnitLabel}.`,
    `Restante: ${formatMetric(m.work_remaining, 1)} ${workUnitLabel}.`,
    `Percentual restante: ${formatMetricPct(m.work_remaining_pct)} do trabalho.`,
    'Usa Story Points quando h\u00e1 SP por HU; caso contr\u00e1rio usa quantidade de tarefas.',
  ];
  const healthInfo = [
    'Compara trabalho restante com dias \u00fateis restantes.',
    `Deadline oficial: ${deadline}.`,
    `\u00daltimo dia \u00fatil considerado: ${operationalDeadline}.`,
    `Diferen\u00e7a atual: ${formatMetric(m.schedule_delta_pct, 1)} p.p.`,
    `Sprint efetiva: m\u00ednimo de ${formatMetric(m.min_calendar_days || 20, 0)} dias corridos.`,
    `Classifica\u00e7\u00e3o: saud\u00e1vel at\u00e9 10 p.p.; aten\u00e7\u00e3o acima de 10 p.p.; alerta acima de 20 p.p.`,
  ];
  const firstResponseInfo = [
    'M\u00e9dia entre a cria\u00e7\u00e3o da tarefa e sua primeira data de in\u00edcio.',
    `M\u00e9dia atual: ${formatMetric(m.first_response_avg, 1)} dias.`,
    `Amostra: ${formatMetric(m.first_response_count, 0)} tarefas com cria\u00e7\u00e3o e in\u00edcio v\u00e1lidos.`,
  ];
  const daysElapsedInfo = [
    'Dias \u00fateis j\u00e1 consumidos desde o in\u00edcio efetivo da sprint.',
    `In\u00edcio efetivo: ${sprintStart}.`,
    `Decorridos: ${formatMetric(m.days_elapsed, 0)} de ${formatMetric(m.days_total, 0)} dias \u00fateis.`,
    `Ainda restam: ${formatMetric(m.days_remaining, 0)} dias \u00fateis.`,
  ];
  const durationInfo = [
    'Total de dias \u00fateis da janela operacional da sprint.',
    `In\u00edcio efetivo: ${sprintStart}.`,
    `Deadline oficial: ${deadline}.`,
    `\u00daltimo dia \u00fatil considerado: ${operationalDeadline}.`,
    `Dias corridos efetivos: ${formatMetric(m.calendar_days_total, 0)}; dias \u00fateis: ${formatMetric(m.days_total, 0)}.`,
  ];
  const sections = [
    {
      title: 'Prazo',
      items: [
        { label:'Dias \u00fateis restantes', value:formatMetric(m.days_remaining, 0), unit:'dias', sub:`${formatMetricPct(m.days_remaining_pct)} do prazo \u00fatil`, info: daysRemainingInfo },
        { label:'Trabalho restante', value:formatMetric(m.work_remaining, 1), unit:workUnit, sub:`${formatMetricPct(m.work_remaining_pct)} do trabalho`, info: workRemainingInfo },
        { label:'Sa\u00fade do prazo', value:statusLabel, unit:m.schedule_delta_pct != null ? `${formatMetric(m.schedule_delta_pct, 1)} p.p.` : '', info: healthInfo },
      ],
    },
    {
      title: 'Resposta',
      items: [
        { label:'Lead Time 1\u00aa resposta', value:formatMetric(m.first_response_avg, 1), unit:'dias', sub:`${formatMetric(m.first_response_count, 0)} tarefas na amostra`, info: firstResponseInfo },
        { label:'Dias \u00fateis decorridos', value:formatMetric(m.days_elapsed, 0), unit:'dias', info: daysElapsedInfo },
        { label:'Dura\u00e7\u00e3o \u00fatil da sprint', value:formatMetric(m.days_total, 0), unit:'dias', info: durationInfo },
      ],
    },
  ];
  const daysPct = Math.max(0, Math.min(metricNumber(m.days_remaining_pct) ?? 0, 100));
  const workPct = Math.max(0, Math.min(metricNumber(m.work_remaining_pct) ?? 0, 100));
  const meter = `<div class="metric-health">
    <div class="metric-health-title">Dias \u00fateis restantes vs. trabalho restante</div>
    <div class="metric-health-row"><span>Dias \u00fateis</span><div class="metric-health-track"><b style="width:${daysPct}%"></b></div><strong>${formatMetricPct(daysPct)}</strong></div>
    <div class="metric-health-row"><span>Trabalho</span><div class="metric-health-track work"><b style="width:${workPct}%"></b></div><strong>${formatMetricPct(workPct)}</strong></div>
  </div>`;
  renderMetricSections(body, sections, meter);
}

function buildKpiPieTrace(labels, values, colors, unitLabel, valueDigits = 0) {
  const rows = labels
    .map((label, index) => ({
      label,
      value: metricNumber(values[index]) ?? 0,
      color: colors[index],
    }))
    .filter(row => row.value > 0);
  if (!rows.length) return null;
  return {
    type: 'pie',
    labels: rows.map(row => row.label),
    values: rows.map(row => row.value),
    marker: { colors: rows.map(row => row.color), line: { color: isDark() ? '#151b2d' : '#ffffff', width: 2 } },
    textinfo: 'label+percent',
    textposition: 'inside',
    insidetextorientation: 'radial',
    hovertemplate: `<b>%{label}</b><br>${unitLabel}: %{value:.${valueDigits}f}<br>%{percent}<extra></extra>`,
    sort: false,
  };
}

function buildKpiPieLayout() {
  return plotLayout({
    showlegend: true,
    margin: { t: 4, r: 8, b: 4, l: 8 },
    height: 245,
    legend: {
      orientation: 'h',
      x: 0.5,
      xanchor: 'center',
      y: -0.04,
      yanchor: 'top',
      bgcolor: 'transparent',
      font: { size: 11 },
    },
    uniformtext: { mode: 'hide', minsize: 10 },
  });
}

function getBurndownStoryPointCompletion(k, bsp, referenceDate) {
  const validRows = (bsp?.rows || []).filter(row => row?.[0] && metricNumber(row?.[2]) !== null);
  const referenceKey = String(referenceDate || '').slice(0, 10);
  const eligibleRows = referenceKey
    ? validRows.filter(row => String(row[0]).slice(0, 10) <= referenceKey)
    : validRows;
  const currentRow = eligibleRows[eligibleRows.length - 1];
  if (!currentRow) return null;

  const total = metricNumber(currentRow[3], bsp?.total_sp, k.storypoints);
  const remaining = metricNumber(currentRow[2]);
  if (total === null || remaining === null) return null;

  const pending = Number(Math.min(Math.max(remaining, 0), total).toFixed(2));
  return {
    done: Number(Math.max(total - pending, 0).toFixed(2)),
    pending,
    total,
  };
}

function getTaskStoryPointCompletion(k, tasks, huSp) {
  const burndownCompletion = getBurndownStoryPointCompletion(
    k,
    dashData.burndown_sp,
    dashData.meta?.export_date,
  );
  if (burndownCompletion) return burndownCompletion;

  const weights = taskStoryPointWeights(tasks, huSp);
  const committed = metricNumber(dashData.scope_quality_metrics?.committed_sp, dashData.burndown_sp?.total_sp, k.storypoints) ?? 0;
  const weightedDone = weights.reduce((sum, weight, index) => isDeliveryDoneTask(tasks[index]) ? sum + (weight || 0) : sum, 0);
  // Compatibilidade com relatórios antigos que ainda não possuem linhas de burndown SP.
  const done = Number(weightedDone.toFixed(2));
  return {
    done,
    pending: Number(Math.max(committed - done, 0).toFixed(2)),
    total: committed,
  };
}

function renderKpiPieCharts() {
  if (!window.Plotly) return;
  const k = dashData.kpis || {};
  const tasks = dashData.task_rows || [];
  const huSp = dashData.burndown_sp?.hu_sp || {};
  const spCompletion = getTaskStoryPointCompletion(k, tasks, huSp);
  const items = [
    {
      id: 'kpiPieTasks',
      labels: ['Conclu\u00eddas', 'Pendentes'],
      values: [k.done, k.pending],
      colors: [pc(2), pc(8)],
      unit: 'Tarefas',
      digits: 0,
    },
    {
      id: 'kpiPieStorypoints',
      labels: ['Conclu\u00eddos', 'Pendentes'],
      values: [spCompletion.done, spCompletion.pending],
      colors: [pc(0), pc(8)],
      unit: 'Story Points',
      digits: 1,
    },
    {
      id: 'kpiPieLeadCycleSp',
      labels: ['Lead Time', 'Cycle Time'],
      values: [k.lt_sp, k.ct_sp],
      colors: [pc(3), pc(0)],
      unit: 'Dias',
      digits: 1,
    },
    {
      id: 'kpiPieLeadCycleHu',
      labels: ['Lead Time', 'Cycle Time'],
      values: [k.lt_hu, k.ct_hu],
      colors: [pc(3), pc(0)],
      unit: 'Dias',
      digits: 1,
    },
    {
      id: 'kpiPieLeadCycleTask',
      labels: ['Lead Time', 'Cycle Time'],
      values: [k.lt_task, k.ct_task],
      colors: [pc(3), pc(0)],
      unit: 'Dias',
      digits: 1,
    },
  ];
  items.forEach(item => {
    const el = document.getElementById(item.id);
    if (!el) return;
    const trace = buildKpiPieTrace(item.labels, item.values, item.colors, item.unit, item.digits);
    if (!trace) {
      el.innerHTML = '<div class="kpi-chart-empty">Sem dados para exibir</div>';
      return;
    }
    Plotly.react(el, [trace], buildKpiPieLayout(), { responsive: true, displayModeBar: false });
  });
}

function buildKpiChartsHtml() {
  const charts = [
    { id: 'kpiPieTasks', title: 'Conclu\u00eddas x Pendentes', subtitle: 'Tarefas' },
    { id: 'kpiPieStorypoints', title: 'Conclu\u00eddos x Pendentes', subtitle: 'Story Points' },
    { id: 'kpiPieLeadCycleSp', title: 'Lead x Cycle', subtitle: 'Por SP' },
    { id: 'kpiPieLeadCycleHu', title: 'Lead x Cycle', subtitle: 'Por HU' },
    { id: 'kpiPieLeadCycleTask', title: 'Lead x Cycle', subtitle: 'Por tarefa' },
  ];
  return `<div class="kpi-groups metric-groups kpi-chart-groups">
    <section class="kpi-section kpi-chart-section">
      <div class="kpi-section-head">Gr\u00e1ficos KPI</div>
      <div class="kpi-chart-grid">${
        charts.map(chart => `<article class="kpi-chart-card">
          <div class="kpi-chart-head">
            <div class="kpi-label">${esc(chart.title)}</div>
            ${chartCardInfo(chart.title, chart.subtitle)}
            <div class="kpi-unit">${esc(chart.subtitle)}</div>
          </div>
          <div class="kpi-chart-plot" id="${esc(chart.id)}"></div>
        </article>`).join('')
      }</div>
    </section>
  </div>`;
}
function renderSprintKPIs(body) {
  const k = dashData.kpis || {};
  const m = dashData.meta || {};
  ensureAdvancedMetrics();
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

  const total = Number(k.total || 0);
  const pct = total ? Math.round(Number(k.done || 0) / total * 100) : 0;
  const storyTotal = num(dashData.burndown_sp?.total_sp, k.storypoints);
  const huSpCount = Object.keys(dashData.burndown_sp?.hu_sp || {}).length;
  const huCount = num(k.hu_count, Array.isArray(dashData.hu_list) ? dashData.hu_list.length : null, huSpCount);
  const sprintDays = getSprintDayMetrics(m);
  const timeMetrics = dashData.time_metrics || {};
  const hasDeadlineCalendar = k.sprint_calendar_basis === 'deadline_month';
  const calendarDays = hasDeadlineCalendar
    ? num(k.sprint_days_calendar, sprintDays.calendar)
    : num(timeMetrics.calendar_days_total, k.sprint_days_calendar, sprintDays.calendar);
  const businessDays = hasDeadlineCalendar
    ? num(k.sprint_days_business, sprintDays.business)
    : num(timeMetrics.days_total, k.sprint_days_business, sprintDays.business);
  const removedDays = hasDeadlineCalendar
    ? (num(k.sprint_weekend_days, sprintDays.weekends) || 0) + (num(k.sprint_holiday_days, sprintDays.holidays) || 0)
    : Math.max(0, (calendarDays || 0) - (businessDays || 0));
  const totalInfo = [
    'Total de tarefas consideradas nos KPIs da sprint.',
    'Respeita os filtros de escopo aplicados no processamento.',
  ];
  const doneInfo = [
    'Tarefas marcadas como conclu\u00eddas no Planner.',
    `Representa ${pct}% do total considerado.`,
  ];
  const pendingInfo = [
    'Tarefas ainda n\u00e3o conclu\u00eddas.',
    'F\u00f3rmula: total de tarefas - tarefas conclu\u00eddas.',
  ];
  const pctDoneInfo = [
    'Percentual de conclus\u00e3o da sprint por quantidade de tarefas.',
    `F\u00f3rmula: ${formatMetric(k.done, 0)} conclu\u00eddas / ${formatMetric(k.total, 0)} totais.`,
  ];
  const huInfo = [
    'Quantidade de HUs distintas identificadas no t\u00edtulo ou nos r\u00f3tulos.',
    'Usa t\u00edtulo primeiro e, se necess\u00e1rio, r\u00f3tulos no padr\u00e3o HU seguido de n\u00famero.',
  ];
  const stakeholdersInfo = [
    'Quantidade de respons\u00e1veis nomeados nas tarefas.',
    'Conta pessoas distintas com atribui\u00e7\u00e3o preenchida.',
  ];
  const storyPointsInfo = [
    'Total de Story Points planejados nas HUs.',
    `HUs com SP mapeado: ${formatMetric(huSpCount, 0)}.`,
    'Os SP s\u00e3o extra\u00eddos da HU no t\u00edtulo ou nos r\u00f3tulos quando dispon\u00edveis.',
  ];
  const outsideHuInfo = [
    'Tarefas sem HU identificada no t\u00edtulo nem nos r\u00f3tulos.',
    'Entram no total de tarefas, mas n\u00e3o entram nos indicadores agrupados por HU/SP.',
  ];
  const ctSpInfo = [
    'Cycle Time ponderado por Story Point.',
    'Mede tempo ativo entre in\u00edcio e conclus\u00e3o considerando o peso em SP.',
    'Depende de HUs com SP mapeados.',
  ];
  const ltSpInfo = [
    'Lead Time ponderado por Story Point.',
    'Mede tempo total entre cria\u00e7\u00e3o e conclus\u00e3o considerando o peso em SP.',
    'Depende de HUs com SP mapeados.',
  ];
  const ctHuInfo = [
    'Cycle Time m\u00e9dio por HU.',
    'Mede o tempo ativo das tarefas da HU, do in\u00edcio at\u00e9 a conclus\u00e3o.',
  ];
  const ltHuInfo = [
    'Lead Time m\u00e9dio por HU.',
    'Mede o tempo total das tarefas da HU, da cria\u00e7\u00e3o at\u00e9 a conclus\u00e3o.',
  ];
  const ctTaskInfo = [
    'Cycle Time m\u00e9dio por tarefa conclu\u00edda.',
    'F\u00f3rmula: data de conclus\u00e3o - data de in\u00edcio.',
  ];
  const ltTaskInfo = [
    'Lead Time m\u00e9dio por tarefa conclu\u00edda.',
    'F\u00f3rmula: data de conclus\u00e3o - data de cria\u00e7\u00e3o.',
  ];
  const calendarDaysInfo = [
    'Dura\u00e7\u00e3o da sprint em dias corridos.',
    hasDeadlineCalendar ? 'Usa a janela efetiva at\u00e9 o deadline oficial do m\u00eas.' : 'Usa as datas da sprint ou a janela derivada dos dados.',
  ];
  const businessDaysInfo = [
    'Dura\u00e7\u00e3o da sprint em dias \u00fateis.',
    'Remove fins de semana e feriados nacionais do Brasil.',
    removedDays ? `Dias removidos: ${formatMetric(removedDays, 0)}.` : 'Nenhum dia removido nesta janela.',
  ];

  const groups = [
    {
      title: 'Entrega',
      items: [
        { label:'Total de Tarefas', value:k.total, unit:'tarefas', info: totalInfo },
        { label:'Conclu\u00eddas', value:k.done, unit:'tarefas', sub:`${pct}% do total`, info: doneInfo },
        { label:'Pendentes', value:k.pending, unit:'tarefas', info: pendingInfo },
        { label:'% Conclu\u00eddo', value:pct, unit:'%', info: pctDoneInfo },
      ],
    },
    {
      title: 'Escopo',
      items: [
        { label:'Qtd de HUs', value:fmt(huCount), unit:'HUs', info: huInfo },
        { label:'Respons\u00e1veis nomeados', value:fmt(k.stakeholders), unit:'pessoas', info: stakeholdersInfo },
        {
          label:'Story Points',
          value: storyTotal ? fmt(storyTotal) : '-',
          unit:'SP',
          sub: dashData.burndown_sp?.total_sp ? `${huSpCount} HUs com SP` : null,
          info: storyPointsInfo,
        },
        { label:'Fora de HU', value:k.sem_hu, unit:'tarefas', info: outsideHuInfo },
      ],
    },
    {
      title: 'Tempo',
      items: [
        { label:'Cycle Time por SP', value:fmt(k.ct_sp, 1), unit:'dias', info: ctSpInfo },
        { label:'Lead Time por SP', value:fmt(k.lt_sp, 1), unit:'dias', info: ltSpInfo },
        { label:'Cycle Time (HU)', value:fmt(k.ct_hu, 1), unit:'dias', info: ctHuInfo },
        { label:'Lead Time (HU)', value:fmt(k.lt_hu, 1), unit:'dias', info: ltHuInfo },
        { label:'Cycle Time (tarefa)', value:fmt(k.ct_task, 1), unit:'dias', info: ctTaskInfo },
        { label:'Lead Time (tarefa)', value:fmt(k.lt_task, 1), unit:'dias', info: ltTaskInfo },
      ],
    },
    {
      title: 'Calend\u00e1rio',
      items: [
        { label:'Dias corridos sprint', value:fmt(calendarDays), unit:'dias', info: calendarDaysInfo },
        {
          label:'Dias \u00fateis sprint',
          value:fmt(businessDays),
          unit:'dias',
          sub: removedDays ? `${removedDays} dias removidos` : null,
          info: businessDaysInfo,
        },
      ],
    },
  ];

  const metaHtml = `<div class="kpi-export-meta" style="font-size:.78rem;color:var(--muted);margin-top:.5rem">
    Sprint: <strong style="color:var(--text)">${esc(m.sprint_name || '-')}</strong> &nbsp;&middot;&nbsp;
    Projeto: <strong style="color:var(--text)">${esc(m.projeto || '-')}</strong> &nbsp;&middot;&nbsp;
    Gerente: <strong style="color:var(--text)">${esc(m.gerente || '-')}</strong> &nbsp;&middot;&nbsp;
    Export: <strong style="color:var(--text)">${esc(m.export_date || '-')}</strong>
  </div>`;
  renderMetricSections(body, groups, buildKpiChartsHtml() + metaHtml);
  requestAnimationFrame(renderKpiPieCharts);
}

function renderKPIs(body) {
  return renderSprintKPIs(body);
  const k   = dashData.kpis || {};
  const m   = dashData.meta || {};
  const pct = k.total ? Math.round(k.done / k.total * 100) : 0;
  const items = [
    { label:'Total de Tarefas',    value:k.total,    unit:'tarefas' },
    { label:'Concluídas',          value:k.done,     unit:'tarefas', sub:`${pct}% do total` },
    { label:'Pendentes',           value:k.pending,  unit:'tarefas' },
    { label:'Fora de HU',          value:k.sem_hu,   unit:'tarefas' },
    { label:'Cycle Time (tarefa)', value:k.ct_task != null ? k.ct_task.toFixed(1) : '—', unit:'dias' },
    { label:'Lead Time (tarefa)',  value:k.lt_task  != null ? k.lt_task.toFixed(1)  : '—', unit:'dias' },
    { label:'Cycle Time (HU)',     value:k.ct_hu  != null ? k.ct_hu.toFixed(1)  : '—', unit:'dias' },
    { label:'Lead Time (HU)',      value:k.lt_hu  != null ? k.lt_hu.toFixed(1)  : '—', unit:'dias' },
    { label:'Story Points', value: (dashData.burndown_sp?.total_sp || k.storypoints || 0) || '—', unit:'SP',
      sub: dashData.burndown_sp?.total_sp ? `${Object.keys(dashData.burndown_sp.hu_sp||{}).length} HUs com SP` : null },
    { label:'% Concluído',         value:pct, unit:'%' },
  ];
  body.innerHTML = `<div class="kpi-grid">${
    items.map(i => `<div class="kpi-card">
      <div class="kpi-label">${esc(i.label)}</div>
      <div class="kpi-value">${esc(i.value ?? '—')}</div>
      <div class="kpi-unit">${esc(i.unit)}</div>
      ${i.sub ? `<div class="kpi-sub">${esc(i.sub)}</div>` : ''}
    </div>`).join('')
  }</div>
  <div style="font-size:.78rem;color:var(--muted);margin-top:.5rem">
    Sprint: <strong style="color:var(--text)">${esc(m.sprint_name || '—')}</strong> &nbsp;&middot;&nbsp;
    Projeto: <strong style="color:var(--text)">${esc(m.projeto || '—')}</strong> &nbsp;&middot;&nbsp;
    Gerente: <strong style="color:var(--text)">${esc(m.gerente || '—')}</strong> &nbsp;&middot;&nbsp;
    Export: <strong style="color:var(--text)">${esc(m.export_date || '—')}</strong>
  </div>`;
}

/* â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•
   TIMING TABLE (Rótulos / Responsáveis)
â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â• */
function renderTimingTable(id, body, type) {
  const rows = id === 'rotulos' ? dashData.rotulos_rows : dashData.resp_rows;
  if (!rows?.length) { renderEmpty(body); return; }

  if (type === 'bar_v' || type === 'bar_h') {
    const labels = rows.map(r => cleanChartLabel(r[0]));
    const lt     = rows.map(r => r[3] ?? 0);
    const ct     = rows.map(r => r[4] ?? 0);
    const horiz  = type === 'bar_h';
    const mk = (name, vals, color) => ({
      type:'bar', name,
      x: horiz ? vals : labels,
      y: horiz ? labels : vals,
      orientation: horiz ? 'h' : 'v',
      marker:{ color },
      customdata: labelHoverData(labels),
      hovertemplate: '<b>%{customdata}</b><br>' + name + ': %{'+(horiz ? 'x' : 'y')+'} dia(s)<extra></extra>',
    });
    body.innerHTML = '<div class="chart-plot-shell" id="chartPlotShell"><div class="chart-plot-wrap"><div id="mainPlot" style="width:100%;height:100%;min-height:420px"></div></div><div class="chart-footer" id="chartFooter"></div></div>';
    Plotly.react('mainPlot',
      [mk('Lead Time', lt, pc(3)), mk('Cycle Time', ct, pc(0))],
      plotLayout({ barmode:'group',
        margin:{ t:30,r:20, b:horiz?40:95, l:horiz?210:60 },
        xaxis: horiz
          ? { tickangle:0, title:{ text:'Dias' } }
          : { ...labelAxis(labels, 32), tickangle:-30, title:{ text:'' } },
        yaxis: horiz
          ? { ...labelAxis(labels, 34), title:{ text:'' } }
          : { title:{ text:'Dias' } },
      }),
      { responsive:true, displayModeBar:false }
    );
    renderChartFooter(id);
    return;
  }

  // Table view
  const maxLT = Math.max(...rows.map(r => r[3] ?? 0));
  const maxCT = Math.max(...rows.map(r => r[4] ?? 0));
  body.innerHTML = `<div class="data-table-wrap"><table class="data-table">
    <thead><tr>
      <th>${id==='rotulos'?'Rótulo':'Responsável'}</th>
      <th style="text-align:right">Concluídas</th>
      <th style="text-align:right">Pendentes</th>
      <th style="min-width:180px">Lead Time (dias)</th>
      <th style="min-width:180px">Cycle Time (dias)</th>
    </tr></thead>
    <tbody>${rows.map(r => {
      const ltPct = maxLT ? Math.round((r[3]??0)/maxLT*100) : 0;
      const ctPct = maxCT ? Math.round((r[4]??0)/maxCT*100) : 0;
      return `<tr>
        <td>${esc(r[0])}</td>
        <td class="td-num">${esc(r[1])}</td>
        <td class="td-num">${esc(r[2])}</td>
        <td class="td-bar">${esc(r[3]!=null?(r[3]).toFixed(1):'—')}
          ${r[3]!=null?`<div class="mini-bar-bg"><div class="mini-bar-fill" style="width:${ltPct}%;background:${pc(3)}"></div></div>`:''}
        </td>
        <td class="td-bar">${esc(r[4]!=null?(r[4]).toFixed(1):'—')}
          ${r[4]!=null?`<div class="mini-bar-bg"><div class="mini-bar-fill" style="width:${ctPct}%"></div></div>`:''}
        </td>
      </tr>`;
    }).join('')}</tbody>
  </table></div>`;
  renderDomChartFooter(id, body);
}
