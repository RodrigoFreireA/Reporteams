/* UTILS - Estado global, helpers e wrapper de API */
/* STATE */
let dashData      = null;
let activeChartId = 'kpis';
let activeType    = {};
let authState     = { authenticated:false, bootstrapRequired:false, csrfToken:null, user:null };
let authMode      = 'login';
let reportList    = [];
let savedRoadmaps = [];
let currentReportId = null;
let adminUsers = [];
let adminEditingUserId = null;
let customCharts = [];
let adminCustomCharts = [];
let customChartEditingId = null;
let profileRules = [];
let adminProfileRules = [];
let profileRuleEditingId = null;
let activeFilters = {};
let currentSummaryText = '';
let currentSummaryReportId = null;

function esc(value) {
  return String(value ?? '')
    .replaceAll('&', '&amp;')
    .replaceAll('<', '&lt;')
    .replaceAll('>', '&gt;')
    .replaceAll('"', '&quot;')
    .replaceAll("'", '&#39;');
}

function parseDateOnlyUtc(value) {
  const raw = String(value ?? '').trim();
  const match = raw.match(/^(\d{4})-(\d{2})-(\d{2})$/);
  if (!match) return null;
  const parsed = new Date(Date.UTC(Number(match[1]), Number(match[2]) - 1, Number(match[3])));
  return Number.isNaN(parsed.getTime()) ? null : parsed;
}

function easterUtcDate(year) {
  const a = year % 19;
  const b = Math.floor(year / 100);
  const c = year % 100;
  const d = Math.floor(b / 4);
  const e = b % 4;
  const f = Math.floor((b + 8) / 25);
  const g = Math.floor((b - f + 1) / 3);
  const h = (19 * a + b - d - g + 15) % 30;
  const i = Math.floor(c / 4);
  const k = c % 4;
  const l = (32 + 2 * e + 2 * i - h - k) % 7;
  const m = Math.floor((a + 11 * h + 22 * l) / 451);
  const month = Math.floor((h + l - 7 * m + 114) / 31);
  const day = ((h + l - 7 * m + 114) % 31) + 1;
  return new Date(Date.UTC(year, month - 1, day));
}

function dateKeyUtc(value) {
  const y = value.getUTCFullYear();
  const m = String(value.getUTCMonth() + 1).padStart(2, '0');
  const d = String(value.getUTCDate()).padStart(2, '0');
  return `${y}-${m}-${d}`;
}

function addDaysUtc(value, days) {
  const next = new Date(value.getTime());
  next.setUTCDate(next.getUTCDate() + days);
  return next;
}

function brNationalHolidayKeys(year) {
  const easter = easterUtcDate(year);
  return new Set([
    `${year}-01-01`,
    dateKeyUtc(addDaysUtc(easter, -2)),
    `${year}-04-21`,
    `${year}-05-01`,
    `${year}-09-07`,
    `${year}-10-12`,
    `${year}-11-02`,
    `${year}-11-15`,
    `${year}-11-20`,
    `${year}-12-25`,
  ]);
}

function getSprintDayMetrics(meta = {}) {
  let start = parseDateOnlyUtc(meta.sprint_start);
  let end = parseDateOnlyUtc(meta.sprint_end);
  if (!start || !end) {
    return { calendar: null, business: null, weekends: 0, holidays: 0 };
  }
  if (end < start) [start, end] = [end, start];

  const calendar = Math.max(0, Math.round((end - start) / 86400000));
  const holidays = new Set();
  for (let year = start.getUTCFullYear(); year <= end.getUTCFullYear(); year += 1) {
    brNationalHolidayKeys(year).forEach(key => holidays.add(key));
  }

  let business = 0;
  let weekends = 0;
  let holidayCount = 0;
  for (let day = new Date(start.getTime()); day < end; day = addDaysUtc(day, 1)) {
    const weekday = day.getUTCDay();
    if (weekday === 0 || weekday === 6) {
      weekends += 1;
    } else if (holidays.has(dateKeyUtc(day))) {
      holidayCount += 1;
    } else {
      business += 1;
    }
  }
  return { calendar, business, weekends, holidays: holidayCount };
}

const BUILTIN_PROFILE_DISPLAY = {
  Gestao: 'Gestão',
  Requisitos: 'Requisito',
  Testes: 'Teste',
  UX: 'UX',
  Devs: 'DEV',
  Arquitetura: 'Arquitetura',
  DB: 'DB',
  Publicacao: 'Publicação',
  Revisao: 'Revisão',
  Construcao: 'Construção',
  Prototipo: 'Protótipo',
  Pesquisa: 'Pesquisa',
  Outros: 'Outros',
};

function normalizeText(value) {
  return String(value ?? '')
    .normalize('NFD')
    .replace(/[\u0300-\u036f]/g, '')
    .toLowerCase()
    .trim();
}

function splitRuleTerms(value) {
  return String(value ?? '')
    .replace(/\n/g, ';')
    .split(/[;,]/)
    .map(item => item.trim())
    .filter(Boolean);
}

function normalizeProfileName(value) {
  const raw = String(value ?? '').trim();
  return normalizeText(BUILTIN_PROFILE_DISPLAY[raw] || raw);
}

function getCustomChartByChartId(chartId) {
  return customCharts.find(chart => chart.chart_id === chartId) || null;
}

function toCustomCatalogItem(chart) {
  const availableTypes = Array.isArray(chart.available_types) && chart.available_types.length
    ? chart.available_types
    : [chart.chart_type || 'bar_v'];
  return {
    id: chart.chart_id,
    name: chart.name,
    icon: chart.icon || CUSTOM_CHART_SOURCES[chart.source_key]?.icon || '✨',
    group: chart.group || 'Distribuição',
    types: availableTypes,
    subtitle: chart.subtitle || `Customizado a partir de ${CUSTOM_CHART_SOURCES[chart.source_key]?.label || 'dataset interno'}`,
  };
}

function getCatalog() {
  return [
    ...BUILTIN_CATALOG,
    ...customCharts.filter(chart => chart.enabled).map(toCustomCatalogItem),
  ];
}

function findCatalogItem(id) {
  return getCatalog().find(item => item.id === id) || null;
}

function fmtDateTime(value) {
  if (!value) return '—';
  const d = new Date(value);
  return Number.isNaN(d.getTime()) ? value : d.toLocaleString('pt-BR');
}

function pngExportFilename(value) {
  const normalized = String(value || 'grafico')
    .normalize('NFD')
    .replace(/[\u0300-\u036f]/g, '')
    .replace(/[^a-zA-Z0-9]+/g, '-')
    .replace(/^-+|-+$/g, '')
    .toLowerCase();
  return normalized || 'grafico';
}

function downloadDataUrl(dataUrl, filename) {
  const link = document.createElement('a');
  link.href = dataUrl;
  link.download = `${pngExportFilename(filename)}.png`;
  document.body.appendChild(link);
  link.click();
  link.remove();
}

function csvExportFilename(value) {
  return pngExportFilename(value);
}

function csvCell(value) {
  if (value === null || value === undefined) return '';
  const text = Array.isArray(value)
    ? value.map(item => Array.isArray(item) ? item.join(' | ') : item).join(' | ')
    : String(value);
  return /[";\r\n]/.test(text) ? `"${text.replace(/"/g, '""')}"` : text;
}

function rowsToCsv(rows) {
  if (!Array.isArray(rows) || !rows.length) return '';
  const headers = Array.from(rows.reduce((set, row) => {
    Object.keys(row || {}).forEach(key => set.add(key));
    return set;
  }, new Set()));
  const lines = [headers.map(csvCell).join(';')];
  rows.forEach(row => {
    lines.push(headers.map(header => csvCell(row?.[header])).join(';'));
  });
  return lines.join('\r\n');
}

function downloadTextFile(text, filename, extension, type) {
  const blob = new Blob([text], { type });
  const url = URL.createObjectURL(blob);
  const link = document.createElement('a');
  link.href = url;
  link.download = `${csvExportFilename(filename)}.${extension}`;
  document.body.appendChild(link);
  link.click();
  link.remove();
  window.setTimeout(() => URL.revokeObjectURL(url), 0);
}

function csvDataLabel(value) {
  if (Array.isArray(value)) return value.map(csvDataLabel).join(' | ');
  if (value === null || value === undefined) return '';
  return String(value);
}

function plotlyTraceRows(plot) {
  const traces = Array.from(plot?.data || []);
  const rows = [];
  traces.forEach((trace, traceIndex) => {
    const serie = trace.name || `Serie ${traceIndex + 1}`;
    if (Array.isArray(trace.labels) && Array.isArray(trace.values)) {
      const length = Math.max(trace.labels.length, trace.values.length);
      for (let index = 0; index < length; index += 1) {
        rows.push({
          Serie: serie,
          Rotulo: csvDataLabel(trace.labels[index]),
          Valor: trace.values[index] ?? '',
          Tipo: trace.type || '',
          Detalhe: csvDataLabel(Array.isArray(trace.customdata) ? trace.customdata[index] : ''),
        });
      }
      return;
    }

    const xValues = Array.isArray(trace.x) ? trace.x : [];
    const yValues = Array.isArray(trace.y) ? trace.y : [];
    const length = Math.max(xValues.length, yValues.length);
    for (let index = 0; index < length; index += 1) {
      const horizontal = trace.orientation === 'h';
      rows.push({
        Serie: serie,
        Rotulo: csvDataLabel(horizontal ? yValues[index] : xValues[index]),
        X: xValues[index] ?? '',
        Y: yValues[index] ?? '',
        Valor: horizontal ? (xValues[index] ?? '') : (yValues[index] ?? ''),
        Tipo: trace.type || '',
        Detalhe: csvDataLabel(Array.isArray(trace.customdata) ? trace.customdata[index] : ''),
      });
    }
  });
  return rows;
}

function tableRowsFromElement(target) {
  const rows = [];
  const tables = Array.from(target?.querySelectorAll?.('table') || [])
    .filter(table => !table.closest('[data-export-ignore="true"]'));
  tables.forEach((table, tableIndex) => {
    const headers = Array.from(table.querySelectorAll('thead th')).map(cell => cell.textContent.trim());
    Array.from(table.querySelectorAll('tbody tr')).forEach(tr => {
      const cells = Array.from(tr.children).map(cell => cell.textContent.replace(/\s+/g, ' ').trim());
      const row = tables.length > 1 ? { Tabela: `Tabela ${tableIndex + 1}` } : {};
      cells.forEach((cell, index) => {
        row[headers[index] || `Coluna ${index + 1}`] = cell;
      });
      rows.push(row);
    });
  });
  return rows;
}

function metricCardRowsFromElement(target) {
  const rows = [];
  Array.from(target?.querySelectorAll?.('.kpi-card') || [])
    .filter(card => !card.closest('[data-export-ignore="true"]'))
    .forEach(card => {
      rows.push({
        Secao: card.closest('.kpi-section')?.querySelector('.kpi-section-head')?.textContent.trim() || '',
        Indicador: card.querySelector('.kpi-label')?.textContent.trim() || '',
        Valor: card.querySelector('.kpi-value')?.textContent.trim() || '',
        Unidade: card.querySelector('.kpi-unit')?.textContent.trim() || '',
        Complemento: card.querySelector('.kpi-sub')?.textContent.trim() || '',
      });
    });
  return rows;
}

function roadmapRowsFromElement(target) {
  const items = Array.from(target?.querySelectorAll?.('.roadmap-report-item') || []);
  return items.map(item => ({
    Data: item.querySelector('.roadmap-report-date')?.textContent.replace(/\s+/g, ' ').trim() || '',
    Goal: item.querySelector('.roadmap-report-block:not(.roadmap-report-block--milestone) p')?.textContent.trim() || '',
    Marco: item.querySelector('.roadmap-report-block--milestone p')?.textContent.trim() || '',
  }));
}

function plotlyRowsFromElement(target) {
  const plots = Array.from(target?.querySelectorAll?.('.js-plotly-plot') || []);
  const multiple = plots.length > 1;
  return plots.flatMap((plot, index) => plotlyTraceRows(plot).map(row => ({
    Secao: plot.closest('.kpi-section')?.querySelector('.kpi-section-head')?.textContent.trim() || 'Grafico',
    Grafico: plot.closest('.kpi-chart-card')?.querySelector('.kpi-label')?.textContent.trim()
      || plot.closest('.kpi-chart-card')?.querySelector('.kpi-unit')?.textContent.trim()
      || (multiple ? `Grafico ${index + 1}` : 'Grafico'),
    ...row,
  })));
}

function panelRowsFromElement(target) {
  return [
    ...metricCardRowsFromElement(target),
    ...tableRowsFromElement(target),
    ...roadmapRowsFromElement(target),
    ...plotlyRowsFromElement(target),
  ];
}
function extractChartCsvRows(target) {
  if (!target) return [];
  if (target.querySelector?.('.kpi-section')) {
    return panelRowsFromElement(target);
  }
  const plot = target.classList?.contains('js-plotly-plot')
    ? target
    : target.querySelector?.('.js-plotly-plot');
  if (plot) {
    const rows = plotlyTraceRows(plot);
    if (rows.length) return rows;
  }
  return [
    ...tableRowsFromElement(target),
    ...metricCardRowsFromElement(target),
    ...roadmapRowsFromElement(target),
  ];
}
function exportChartAsCsv(target, filename, options = {}) {
  if (!target) throw new Error('Grafico nao encontrado para exportacao CSV.');
  const rows = typeof options.rowsGetter === 'function'
    ? options.rowsGetter(target)
    : extractChartCsvRows(target);
  const csv = rowsToCsv(rows);
  if (!csv) throw new Error('Nenhum dado tabular encontrado para exportacao CSV.');
  downloadTextFile(`\ufeff${csv}`, filename, 'csv', 'text/csv;charset=utf-8');
}

function createChartCsvButton(targetOrGetter, filename, options = {}) {
  const button = document.createElement('button');
  button.type = 'button';
  button.className = options.className || 'btn-small chart-export-btn';
  button.dataset.exportIgnore = 'true';
  button.title = 'Exportar dados deste grafico como CSV';
  button.innerHTML = '<span class="chart-export-icon" aria-hidden="true">CSV</span><span>Exportar CSV</span>';
  button.addEventListener('click', () => {
    const originalHtml = button.innerHTML;
    button.disabled = true;
    button.textContent = 'Exportando...';
    try {
      const target = typeof targetOrGetter === 'function' ? targetOrGetter() : targetOrGetter;
      exportChartAsCsv(target, filename, options);
      button.textContent = 'CSV exportado';
    } catch (error) {
      console.error('Falha ao exportar grafico como CSV', error);
      button.textContent = 'Falha ao exportar';
    } finally {
      window.setTimeout(() => {
        button.disabled = false;
        button.innerHTML = originalHtml;
      }, 1400);
    }
  });
  return button;
}
function copyExportStyles(source, clone) {
  if (!(source instanceof Element) || !(clone instanceof Element)) return;
  const computed = getComputedStyle(source);
  const declarations = [];
  for (let index = 0; index < computed.length; index += 1) {
    const property = computed[index];
    declarations.push(`${property}:${computed.getPropertyValue(property)};`);
  }
  clone.setAttribute('style', declarations.join(''));

  const sourceChildren = Array.from(source.children);
  const cloneChildren = Array.from(clone.children);
  sourceChildren.forEach((child, index) => copyExportStyles(child, cloneChildren[index]));
}

function currentChartExportAppearance() {
  const rootStyles = getComputedStyle(document.documentElement);
  const readColor = (property, fallback) => rootStyles.getPropertyValue(property).trim() || fallback;
  const light = document.documentElement.dataset.theme === 'light';
  return {
    background: readColor('--bg', light ? '#ffffff' : '#12161f'),
    font: readColor('--font-color', light ? '#3a4a60' : '#c8d0e0'),
    grid: readColor('--gridcol', light ? '#e0e8f0' : '#2a3350'),
    zero: readColor('--zerocol', light ? '#ccd5e0' : '#33405a'),
  };
}


async function replaceExportPlotlyNodesWithImages(source, clone) {
  if (!window.Plotly?.toImage) return;
  const sourcePlots = Array.from(source?.querySelectorAll?.('.js-plotly-plot') || []);
  const clonePlots = Array.from(clone?.querySelectorAll?.('.js-plotly-plot') || []);
  for (let index = 0; index < sourcePlots.length; index += 1) {
    const sourcePlot = sourcePlots[index];
    const clonePlot = clonePlots[index];
    if (!sourcePlot || !clonePlot) continue;
    const rect = sourcePlot.getBoundingClientRect();
    const width = Math.max(1, Math.round(rect.width || sourcePlot.scrollWidth || 1));
    const height = Math.max(1, Math.round(rect.height || sourcePlot.scrollHeight || 1));
    try {
      const dataUrl = await Plotly.toImage(sourcePlot, { format: 'png', width, height, scale: 2 });
      const img = document.createElement('img');
      img.src = dataUrl;
      img.alt = '';
      img.setAttribute('aria-hidden', 'true');
      img.style.display = 'block';
      img.style.width = `${width}px`;
      img.style.height = `${height}px`;
      img.style.maxWidth = '100%';
      img.style.objectFit = 'contain';
      clonePlot.replaceWith(img);
    } catch (error) {
      console.warn('Falha ao converter Plotly interno para PNG durante exportacao DOM', error);
      const fallback = document.createElement('div');
      fallback.textContent = 'Grafico indisponivel no export';
      fallback.style.display = 'flex';
      fallback.style.alignItems = 'center';
      fallback.style.justifyContent = 'center';
      fallback.style.width = `${width}px`;
      fallback.style.height = `${height}px`;
      fallback.style.maxWidth = '100%';
      fallback.style.color = currentChartExportAppearance().font;
      fallback.style.fontSize = '12px';
      clonePlot.replaceWith(fallback);
    }
  }
}
function exportRelativeRect(element, rootRect) {
  const rect = element.getBoundingClientRect();
  return {
    x: rect.left - rootRect.left,
    y: rect.top - rootRect.top,
    width: rect.width,
    height: rect.height,
  };
}

function exportColor(value, fallback) {
  if (!value || value === 'rgba(0, 0, 0, 0)' || value === 'transparent') return fallback;
  return value;
}

function drawExportRoundRect(context, x, y, width, height, radius, fill, stroke) {
  const r = Math.min(radius, width / 2, height / 2);
  context.beginPath();
  context.moveTo(x + r, y);
  context.lineTo(x + width - r, y);
  context.quadraticCurveTo(x + width, y, x + width, y + r);
  context.lineTo(x + width, y + height - r);
  context.quadraticCurveTo(x + width, y + height, x + width - r, y + height);
  context.lineTo(x + r, y + height);
  context.quadraticCurveTo(x, y + height, x, y + height - r);
  context.lineTo(x, y + r);
  context.quadraticCurveTo(x, y, x + r, y);
  context.closePath();
  if (fill) {
    context.fillStyle = fill;
    context.fill();
  }
  if (stroke) {
    context.strokeStyle = stroke;
    context.lineWidth = 1;
    context.stroke();
  }
}

function exportLineHeight(styles) {
  const parsed = Number.parseFloat(styles.lineHeight);
  if (Number.isFinite(parsed)) return parsed;
  const fontSize = Number.parseFloat(styles.fontSize) || 12;
  return fontSize * 1.22;
}

function drawExportTextElement(context, element, rootRect) {
  if (!element || element.closest('[data-export-ignore="true"]') || element.closest('.js-plotly-plot')) return;
  if (element.closest('.kpi-chart-plot')) return;
  const text = (element.textContent || '').replace(/\s+/g, ' ').trim();
  if (!text) return;
  const rect = exportRelativeRect(element, rootRect);
  if (rect.width <= 0 || rect.height <= 0) return;
  const styles = getComputedStyle(element);
  const color = exportColor(styles.color, currentChartExportAppearance().font);
  const lineHeight = exportLineHeight(styles);
  const align = styles.textAlign === 'right' ? 'right' : styles.textAlign === 'center' ? 'center' : 'left';
  const padding = 1;
  const maxWidth = Math.max(1, rect.width - padding * 2);
  const words = text.split(' ');
  const lines = [];
  let line = '';

  context.save();
  context.font = styles.font || `${styles.fontWeight || '400'} ${styles.fontSize || '12px'} ${styles.fontFamily || 'Arial'}`;
  context.fillStyle = color;
  context.textBaseline = 'top';
  context.textAlign = align;

  words.forEach(word => {
    const next = line ? `${line} ${word}` : word;
    if (context.measureText(next).width <= maxWidth || !line) {
      line = next;
    } else {
      lines.push(line);
      line = word;
    }
  });
  if (line) lines.push(line);

  const maxLines = Math.max(1, Math.floor((rect.height + 2) / lineHeight));
  const visibleLines = lines.slice(0, maxLines);
  if (lines.length > maxLines && visibleLines.length) {
    let last = visibleLines[visibleLines.length - 1];
    while (last.length > 1 && context.measureText(`${last}...`).width > maxWidth) last = last.slice(0, -1);
    visibleLines[visibleLines.length - 1] = `${last}...`;
  }

  const x = align === 'right' ? rect.x + rect.width - padding : align === 'center' ? rect.x + rect.width / 2 : rect.x + padding;
  visibleLines.forEach((value, index) => {
    context.fillText(value, x, rect.y + index * lineHeight, maxWidth);
  });
  context.restore();
}

function loadExportImage(dataUrl) {
  return new Promise((resolve, reject) => {
    const image = new Image();
    image.onload = () => resolve(image);
    image.onerror = reject;
    image.src = dataUrl;
  });
}

async function drawExportPlotImages(context, target, rootRect) {
  if (!window.Plotly?.toImage) return;
  const plots = Array.from(target.querySelectorAll('.kpi-chart-plot.js-plotly-plot, .kpi-chart-plot .js-plotly-plot, .metric-chart-plot.js-plotly-plot, .metric-chart-plot .js-plotly-plot'));
  for (const plot of plots) {
    const rect = exportRelativeRect(plot, rootRect);
    if (rect.width <= 0 || rect.height <= 0) continue;
    try {
      const dataUrl = await Plotly.toImage(plot, {
        format: 'png',
        width: Math.max(1, Math.round(rect.width)),
        height: Math.max(1, Math.round(rect.height)),
        scale: 2,
      });
      const image = await loadExportImage(dataUrl);
      context.drawImage(image, rect.x, rect.y, rect.width, rect.height);
    } catch (error) {
      console.warn('Falha ao desenhar Plotly no export Canvas', error);
      context.save();
      context.fillStyle = currentChartExportAppearance().font;
      context.font = '600 12px Segoe UI, Arial, sans-serif';
      context.textAlign = 'center';
      context.textBaseline = 'middle';
      context.fillText('Grafico indisponivel no export', rect.x + rect.width / 2, rect.y + rect.height / 2, rect.width - 16);
      context.restore();
    }
  }
}

async function exportMetricPanelAsCanvasPng(target, filename) {
  const rect = target.getBoundingClientRect();
  const width = Math.max(1, Math.ceil(Math.max(rect.width, target.scrollWidth)));
  const height = Math.max(1, Math.ceil(Math.max(rect.height, target.scrollHeight)));
  const maxScale = Math.min(2, 8192 / Math.max(width, height));
  const scale = Math.max(1, maxScale);
  const canvas = document.createElement('canvas');
  canvas.width = Math.round(width * scale);
  canvas.height = Math.round(height * scale);
  const context = canvas.getContext('2d');
  const appearance = currentChartExportAppearance();
  const targetStyles = getComputedStyle(target);
  const background = exportColor(targetStyles.backgroundColor, appearance.background);
  context.scale(scale, scale);
  context.fillStyle = background;
  context.fillRect(0, 0, width, height);

  const rootRect = target.getBoundingClientRect();
  const drawBox = (element, radius = 12) => {
    const box = exportRelativeRect(element, rootRect);
    const styles = getComputedStyle(element);
    drawExportRoundRect(
      context,
      box.x,
      box.y,
      box.width,
      box.height,
      radius,
      exportColor(styles.backgroundColor, null),
      exportColor(styles.borderTopColor, null),
    );
  };

  Array.from(target.querySelectorAll('.kpi-section')).forEach(section => {
    const box = exportRelativeRect(section, rootRect);
    const styles = getComputedStyle(section);
    if (styles.borderTopWidth !== '0px') {
      context.strokeStyle = exportColor(styles.borderTopColor, appearance.grid);
      context.lineWidth = 1;
      context.beginPath();
      context.moveTo(box.x, box.y + 0.5);
      context.lineTo(box.x + box.width, box.y + 0.5);
      context.stroke();
    }
  });
  Array.from(target.querySelectorAll('.kpi-card,.kpi-chart-card,.metric-table-wrap,.metric-health')).forEach(element => drawBox(element, 12));
  Array.from(target.querySelectorAll('.metric-health-track')).forEach(track => drawBox(track, 999));
  Array.from(target.querySelectorAll('.metric-health-track b')).forEach(bar => drawBox(bar, 999));
  Array.from(target.querySelectorAll('.metric-table th')).forEach(cell => {
    const box = exportRelativeRect(cell, rootRect);
    const styles = getComputedStyle(cell);
    context.fillStyle = exportColor(styles.backgroundColor, background);
    context.fillRect(box.x, box.y, box.width, box.height);
  });

  await drawExportPlotImages(context, target, rootRect);

  const textSelectors = [
    '.kpi-section-head', '.kpi-label', '.kpi-value', '.kpi-unit', '.kpi-sub',
    '.metric-table th', '.metric-table td', '.metric-health-title',
    '.metric-health-row span', '.metric-health-row strong', '.kpi-chart-empty', '.kpi-export-meta',
  ].join(',');
  Array.from(target.querySelectorAll(textSelectors)).forEach(element => drawExportTextElement(context, element, rootRect));
  downloadDataUrl(canvas.toDataURL('image/png'), filename);
}
async function exportRoadmapAsCanvasPng(target, filename) {
  const timelineScroll = target.querySelector('.roadmap-timeline-scroll');
  const timelineTrack = target.querySelector('.roadmap-timeline-track');
  const exportLayout = [timelineScroll, timelineTrack].filter(Boolean).map(element => ({
    element,
    cssText: element.style.cssText,
  }));
  if (timelineScroll && timelineTrack) {
    const availableWidth = Math.max(720, Math.floor(target.getBoundingClientRect().width));
    const columns = Math.max(2, Math.min(5, Math.floor((availableWidth - 24) / 210)));
    timelineScroll.style.overflow = 'visible';
    timelineScroll.style.padding = '0';
    timelineTrack.style.minWidth = '0';
    timelineTrack.style.width = '100%';
    timelineTrack.style.height = 'auto';
    timelineTrack.style.gridTemplateColumns = `repeat(${columns}, minmax(0, 1fr))`;
    timelineTrack.style.gridAutoRows = '190px';
    timelineTrack.style.gap = '.5rem 0';
  }
  try {
  const rect = target.getBoundingClientRect();
  const width = Math.max(1, Math.ceil(Math.max(rect.width, target.scrollWidth)));
  const height = Math.max(1, Math.ceil(Math.max(rect.height, target.scrollHeight)));
  const scale = Math.max(1, Math.min(2, 8192 / Math.max(width, height)));
  const canvas = document.createElement('canvas');
  canvas.width = Math.round(width * scale);
  canvas.height = Math.round(height * scale);
  const context = canvas.getContext('2d');
  const appearance = currentChartExportAppearance();
  const rootRect = target.getBoundingClientRect();
  context.scale(scale, scale);
  context.fillStyle = exportColor(getComputedStyle(target).backgroundColor, appearance.background);
  context.fillRect(0, 0, width, height);

  const drawBox = (element, radius = 8) => {
    const box = exportRelativeRect(element, rootRect);
    const styles = getComputedStyle(element);
    const computedRadius = Number.parseFloat(styles.borderTopLeftRadius) || radius;
    let fill = exportColor(styles.backgroundColor, null);
    if (element.classList.contains('roadmap-report-head')) {
      const gradient = context.createLinearGradient(box.x, box.y, box.x + box.width, box.y + box.height);
      const accentLight = getComputedStyle(document.documentElement).getPropertyValue('--accent-l').trim() || accentColor();
      gradient.addColorStop(0, accentColor());
      gradient.addColorStop(1, accentLight);
      fill = gradient;
    }
    if (element.classList.contains('roadmap-timeline-axis')) {
      const gradient = context.createLinearGradient(box.x, box.y, box.x + box.width, box.y);
      gradient.addColorStop(0, accentColor());
      gradient.addColorStop(1, accent2Color());
      fill = gradient;
    }
    const fullBorder = element.matches('.roadmap-report,.roadmap-report-head,.roadmap-timeline-panel,.roadmap-timeline-card,.roadmap-report-item');
    const hasShadow = element.classList.contains('roadmap-timeline-card');
    context.save();
    if (hasShadow) {
      context.shadowColor = 'rgba(0,0,0,.18)';
      context.shadowBlur = 14;
      context.shadowOffsetY = 6;
    }
    drawExportRoundRect(context, box.x, box.y, box.width, box.height, computedRadius, fill,
      fullBorder ? exportColor(styles.borderColor, null) : null);
    context.restore();
    if (!fullBorder && styles.borderBottomWidth !== '0px') {
      context.strokeStyle = exportColor(styles.borderBottomColor, appearance.grid);
      context.lineWidth = Math.max(1, Number.parseFloat(styles.borderBottomWidth) || 1);
      context.beginPath();
      context.moveTo(box.x, box.y + box.height - context.lineWidth / 2);
      context.lineTo(box.x + box.width, box.y + box.height - context.lineWidth / 2);
      context.stroke();
    }
    if (styles.borderTopWidth !== '0px') {
      context.strokeStyle = exportColor(styles.borderTopColor, appearance.grid);
      context.lineWidth = Math.max(1, Number.parseFloat(styles.borderTopWidth) || 1);
      context.beginPath();
      context.moveTo(box.x, box.y + context.lineWidth / 2);
      context.lineTo(box.x + box.width, box.y + context.lineWidth / 2);
      context.stroke();
    }
  };

  target.querySelectorAll('.roadmap-report,.roadmap-report-head,.roadmap-timeline-panel,.roadmap-timeline-card,.roadmap-report-item,.roadmap-report-date,.roadmap-report-block').forEach(drawBox);
  target.querySelectorAll('.roadmap-timeline-event').forEach(element => {
    const box = exportRelativeRect(element, rootRect);
    const styles = getComputedStyle(element);
    const color = styles.getPropertyValue('--roadmap-color').trim() || accentColor();
    const y = box.y + box.height / 2;
    const top = element.classList.contains('is-top') ? y - 57 : y;
    const bottom = element.classList.contains('is-top') ? y : y + 57;
    context.strokeStyle = color;
    context.lineWidth = 2;
    context.beginPath();
    context.moveTo(box.x + box.width / 2, top);
    context.lineTo(box.x + box.width / 2, bottom);
    context.stroke();
  });
  const timelineEvents = Array.from(target.querySelectorAll('.roadmap-timeline-event'));
  const timelineRows = [...new Set(timelineEvents.map(element => {
    const box = exportRelativeRect(element, rootRect);
    return Math.round(box.y + box.height / 2);
  }))];
  const timelinePanel = target.querySelector('.roadmap-timeline-panel');
  if (timelinePanel) {
    const panelBox = exportRelativeRect(timelinePanel, rootRect);
    const gradient = context.createLinearGradient(panelBox.x, 0, panelBox.x + panelBox.width, 0);
    gradient.addColorStop(0, accentColor());
    gradient.addColorStop(1, accent2Color());
    context.strokeStyle = gradient;
    context.lineWidth = 3;
    timelineRows.forEach(y => {
      context.beginPath();
      context.moveTo(panelBox.x + 18, y);
      context.lineTo(panelBox.x + panelBox.width - 18, y);
      context.stroke();
    });
  }
  target.querySelectorAll('.roadmap-timeline-dot').forEach(element => {
    const box = exportRelativeRect(element, rootRect);
    const styles = getComputedStyle(element);
    context.fillStyle = exportColor(styles.backgroundColor, appearance.font);
    context.strokeStyle = exportColor(styles.borderColor, appearance.background);
    context.lineWidth = Math.max(2, Number.parseFloat(styles.borderLeftWidth) || 3);
    context.beginPath();
    context.arc(box.x + box.width / 2, box.y + box.height / 2, Math.max(2, box.width / 2), 0, Math.PI * 2);
    context.fill();
    context.stroke();
  });

  const textSelectors = [
    '.roadmap-report-eyebrow', '.roadmap-report-title', '.roadmap-report-period',
    '.roadmap-report-legend', '.roadmap-section-head span', '.roadmap-section-head strong',
    '.roadmap-report-date strong', '.roadmap-report-date span', '.roadmap-report-block b',
    '.roadmap-report-block p', '.roadmap-timeline-date strong', '.roadmap-timeline-date span',
    '.roadmap-timeline-goal .roadmap-clamp', '.roadmap-timeline-text .roadmap-clamp',
  ].join(',');
  target.querySelectorAll(textSelectors).forEach(element => drawExportTextElement(context, element, rootRect));
  downloadDataUrl(canvas.toDataURL('image/png'), filename);
  } finally {
    exportLayout.forEach(({ element, cssText }) => { element.style.cssText = cssText; });
  }
}

function exportRoadmapExecutivePng(filename) {
  const items = typeof currentRoadmapItems === 'function' ? currentRoadmapItems() : [];
  if (!items.length) throw new Error('Roadmap nao encontrado para exportacao.');

  const width = 1800;
  const height = 1100;
  const scale = Math.min(2, 8192 / Math.max(width, height));
  const canvas = document.createElement('canvas');
  canvas.width = Math.round(width * scale);
  canvas.height = Math.round(height * scale);
  const context = canvas.getContext('2d');
  const appearance = currentChartExportAppearance();
  const rootStyles = getComputedStyle(document.documentElement);
  const textColor = rootStyles.getPropertyValue('--text').trim() || '#dce5f4';
  const mutedColor = rootStyles.getPropertyValue('--muted').trim() || '#91a0b8';
  const cardColor = rootStyles.getPropertyValue('--card').trim() || '#1b2436';
  const panelColor = rootStyles.getPropertyValue('--bg3').trim() || '#202b42';
  const borderColor = rootStyles.getPropertyValue('--border').trim() || '#3b4964';
  context.scale(scale, scale);
  context.fillStyle = appearance.background;
  context.fillRect(0, 0, width, height);

  const roundBox = (x, y, w, h, radius, fill, stroke) => {
    drawExportRoundRect(context, x, y, w, h, radius, fill, stroke);
  };
  const wrapText = (text, x, y, maxWidth, lineHeight, maxLines, color, font) => {
    const words = String(text || '-').split(/\s+/);
    const lines = [];
    let line = '';
    context.font = font;
    words.forEach(word => {
      const next = line ? `${line} ${word}` : word;
      if (!line || context.measureText(next).width <= maxWidth) line = next;
      else { lines.push(line); line = word; }
    });
    if (line) lines.push(line);
    const visible = lines.slice(0, maxLines);
    if (lines.length > maxLines && visible.length) {
      let last = visible[visible.length - 1];
      while (last.length > 1 && context.measureText(`${last}...`).width > maxWidth) last = last.slice(0, -1);
      visible[visible.length - 1] = `${last}...`;
    }
    context.fillStyle = color;
    visible.forEach((value, index) => context.fillText(value, x, y + index * lineHeight));
  };

  const headerGradient = context.createLinearGradient(40, 30, width - 40, 120);
  headerGradient.addColorStop(0, accentColor());
  headerGradient.addColorStop(1, rootStyles.getPropertyValue('--accent-l').trim() || accentColor());
  roundBox(40, 30, width - 80, 100, 18, headerGradient, null);
  context.fillStyle = '#fff';
  context.font = '900 28px Segoe UI, Arial, sans-serif';
  context.fillText(`ROADMAP DE PROJETO - ${dashData?.meta?.projeto || dashData?.meta?.sprint_name || 'Roadmap'}`.toUpperCase(), 68, 70);
  context.font = '700 15px Segoe UI, Arial, sans-serif';
  context.fillText(`${items[0].date || '--'} - ${items[items.length - 1].date || '--'}`, 68, 102);

  const panelX = 40;
  const panelY = 155;
  const panelW = width - 80;
  const panelH = height - panelY - 35;
  roundBox(panelX, panelY, panelW, panelH, 18, panelColor, borderColor);
  const columns = Math.ceil(items.length / 2);
  const gap = 10;
  const innerX = panelX + 22;
  const innerW = panelW - 44;
  const cellW = (innerW - gap * (columns - 1)) / columns;
  const rowH = (panelH - 48) / 2;
  const cardH = Math.min(176, rowH - 58);
  const labelFont = '900 11px Segoe UI, Arial, sans-serif';
  const bodyFont = '600 10px Segoe UI, Arial, sans-serif';

  for (let row = 0; row < 2; row += 1) {
    const rowItems = items.slice(row * columns, (row + 1) * columns);
    const rowY = panelY + 22 + row * rowH;
    context.fillStyle = mutedColor;
    context.font = '900 12px Segoe UI, Arial, sans-serif';
    context.fillText(`FAIXA ${row + 1}`, innerX, rowY + 13);
    const axisY = rowY + rowH / 2 + 4;
    const axisGradient = context.createLinearGradient(innerX, axisY, innerX + innerW, axisY);
    axisGradient.addColorStop(0, accentColor());
    axisGradient.addColorStop(1, accent2Color());
    context.strokeStyle = axisGradient;
    context.lineWidth = 3;
    context.beginPath();
    context.moveTo(innerX, axisY);
    context.lineTo(innerX + innerW, axisY);
    context.stroke();
    context.fillStyle = accent2Color();
    context.beginPath();
    context.moveTo(innerX + innerW, axisY);
    context.lineTo(innerX + innerW - 13, axisY - 8);
    context.lineTo(innerX + innerW - 13, axisY + 8);
    context.closePath();
    context.fill();

    rowItems.forEach((item, index) => {
      const x = innerX + index * (cellW + gap);
      const color = pc(row * columns + index);
      const isTop = index % 2 === 0;
      const y = isTop ? rowY + 25 : rowY + rowH - cardH - 12;
      const centerX = x + cellW / 2;
      context.strokeStyle = color;
      context.lineWidth = 2;
      context.beginPath();
      context.moveTo(centerX, isTop ? y + cardH : axisY);
      context.lineTo(centerX, isTop ? axisY : y);
      context.stroke();
      context.fillStyle = color;
      context.beginPath();
      context.arc(centerX, axisY, 7, 0, Math.PI * 2);
      context.fill();
      roundBox(x, y, cellW, cardH, 9, cardColor, color);
      context.fillStyle = color;
      context.fillRect(x, y, cellW, 4);
      context.fillStyle = textColor;
      context.font = labelFont;
      context.fillText(item.date || '--', x + 10, y + 22);
      context.fillStyle = color;
      context.font = '900 10px Segoe UI, Arial, sans-serif';
      context.textAlign = 'right';
      context.fillText(roadmapMonthYear(item.date).month, x + cellW - 10, y + 22);
      context.textAlign = 'left';
      context.fillStyle = mutedColor;
      context.font = '900 9px Segoe UI, Arial, sans-serif';
      context.fillText('GOAL', x + 10, y + 43);
      wrapText(item.goal, x + 10, y + 57, cellW - 20, 12, 2, textColor, bodyFont);
      context.fillStyle = accent2Color();
      context.font = '900 9px Segoe UI, Arial, sans-serif';
      context.fillText('MARCO', x + 10, y + 88);
      wrapText(item.marco, x + 10, y + 102, cellW - 20, 12, 5, textColor, bodyFont);
    });
  }
  downloadDataUrl(canvas.toDataURL('image/png'), filename);
}

async function exportDomElementAsPng(target, filename) {
  if (target.matches?.('.roadmap-export-section--timeline')) {
    exportRoadmapExecutivePng(filename);
    return;
  }
  if (target.matches?.('.roadmap-export-section--cards')) {
    await exportRoadmapAsCanvasPng(target, filename);
    return;
  }
  if (target.querySelector?.('.kpi-section')) {
    await exportMetricPanelAsCanvasPng(target, filename);
    return;
  }
  const rect = target.getBoundingClientRect();
  const width = Math.max(1, Math.ceil(Math.max(rect.width, target.scrollWidth)));
  const height = Math.max(1, Math.ceil(Math.max(rect.height, target.scrollHeight)));
  const maxScale = Math.min(2, 8192 / Math.max(width, height));
  const scale = Math.max(1, maxScale);
  const clone = target.cloneNode(true);
  copyExportStyles(target, clone);
  await replaceExportPlotlyNodesWithImages(target, clone);
  clone.querySelectorAll('[data-export-ignore="true"],button,select,input').forEach(element => element.remove());
  clone.style.width = `${width}px`;
  clone.style.height = `${height}px`;
  clone.style.margin = '0';
  clone.style.overflow = 'hidden';

  const serialized = new XMLSerializer().serializeToString(clone);
  const svg = `<svg xmlns="http://www.w3.org/2000/svg" width="${width}" height="${height}" viewBox="0 0 ${width} ${height}">
    <foreignObject width="100%" height="100%">
      <div xmlns="http://www.w3.org/1999/xhtml" style="width:${width}px;height:${height}px;overflow:hidden">${serialized}</div>
    </foreignObject>
  </svg>`;
  const url = URL.createObjectURL(new Blob([svg], { type: 'image/svg+xml;charset=utf-8' }));

  try {
    const image = new Image();
    image.decoding = 'async';
    image.src = url;
    await image.decode();
    const canvas = document.createElement('canvas');
    canvas.width = Math.round(width * scale);
    canvas.height = Math.round(height * scale);
    const context = canvas.getContext('2d');
    context.scale(scale, scale);
    const background = getComputedStyle(target).backgroundColor;
    context.fillStyle = background && background !== 'rgba(0, 0, 0, 0)'
      ? background
      : currentChartExportAppearance().background;
    context.fillRect(0, 0, width, height);
    context.drawImage(image, 0, 0, width, height);
    const dataUrl = canvas.toDataURL('image/png');
    downloadDataUrl(dataUrl, filename);
  } finally {
    URL.revokeObjectURL(url);
  }
}

async function exportChartAsPng(target, filename, options = {}) {
  if (!target) throw new Error('Grafico nao encontrado para exportacao.');
  const plot = target.classList?.contains('js-plotly-plot')
    ? target
    : target.querySelector?.('.js-plotly-plot');
  if (!options.forceDom && plot && window.Plotly?.toImage) {
    const width = Math.max(900, Math.round(plot.getBoundingClientRect().width || 0));
    const height = Math.max(520, Math.round(plot.getBoundingClientRect().height || 0));
    const appearance = currentChartExportAppearance();
    const sourceLayout = plot.layout || {};
    const exportHost = document.createElement('div');
    exportHost.setAttribute('aria-hidden', 'true');
    Object.assign(exportHost.style, {
      position: 'fixed',
      left: '-10000px',
      top: '0',
      width: `${width}px`,
      height: `${height}px`,
      background: appearance.background,
      pointerEvents: 'none',
    });
    document.body.appendChild(exportHost);

    const themedAxis = axis => ({
      ...(axis || {}),
      gridcolor: appearance.grid,
      zerolinecolor: appearance.zero,
      tickfont: { ...(axis?.tickfont || {}), color: appearance.font },
      title: axis?.title
        ? { ...axis.title, font: { ...(axis.title.font || {}), color: appearance.font } }
        : axis?.title,
    });
    const exportLayout = {
      ...sourceLayout,
      width,
      height,
      autosize: false,
      paper_bgcolor: appearance.background,
      plot_bgcolor: appearance.background,
      font: { ...(sourceLayout.font || {}), color: appearance.font },
      legend: {
        ...(sourceLayout.legend || {}),
        font: { ...(sourceLayout.legend?.font || {}), color: appearance.font },
      },
      xaxis: themedAxis(sourceLayout.xaxis),
      yaxis: themedAxis(sourceLayout.yaxis),
    };

    try {
      await Plotly.newPlot(exportHost, plot.data || [], exportLayout, {
        staticPlot: true,
        displayModeBar: false,
        responsive: false,
      });
      const dataUrl = await Plotly.toImage(exportHost, { format: 'png', width, height, scale: 2 });
      downloadDataUrl(dataUrl, filename);
    } finally {
      Plotly.purge(exportHost);
      exportHost.remove();
    }
    return;
  }
  await exportDomElementAsPng(target, filename);
}

function createChartPngButton(targetOrGetter, filename, options = {}) {
  const button = document.createElement('button');
  button.type = 'button';
  button.className = options.className || 'btn-small chart-export-btn';
  button.dataset.exportIgnore = 'true';
  button.title = 'Exportar este grafico como PNG';
  button.innerHTML = '<span class="chart-export-icon" aria-hidden="true">&#8595;</span><span>Exportar PNG</span>';
  button.addEventListener('click', async () => {
    const originalHtml = button.innerHTML;
    button.disabled = true;
    button.textContent = 'Exportando...';
    try {
      const target = typeof targetOrGetter === 'function' ? targetOrGetter() : targetOrGetter;
      await exportChartAsPng(target, filename, options);
      button.textContent = 'PNG exportado';
    } catch (error) {
      console.error('Falha ao exportar grafico como PNG', error);
      button.textContent = 'Falha ao exportar';
    } finally {
      window.setTimeout(() => {
        button.disabled = false;
        button.innerHTML = originalHtml;
      }, 1400);
    }
  });
  return button;
}

async function apiRequest(url, options = {}) {
  const opts = { method: 'GET', credentials: 'same-origin', ...options };
  opts.headers = { ...(options.headers || {}) };
  if (options.json !== undefined) {
    opts.headers['Content-Type'] = 'application/json';
    opts.body = JSON.stringify(options.json);
  }
  if (options.csrf && authState.csrfToken) {
    opts.headers['X-CSRF-Token'] = authState.csrfToken;
  }
  const res = await fetch(url, opts);
  let body = {};
  try { body = await res.json(); } catch (_) {}
  if (!res.ok) {
    if (res.status === 401) {
      showAuthScreen(body.bootstrap_required === true);
    }
    throw new Error(body.erro || `HTTP ${res.status}`);
  }
  return body;
}
