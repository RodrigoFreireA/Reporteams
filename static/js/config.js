/* ════════════════════════════════════════════════════════════
   CONFIG — Paletas, tipos de gráfico e catálogo
════════════════════════════════════════════════════════════ */
/* ════════════════════════════════════════════════════════════
   PALETTES — definição completa de cada paleta
════════════════════════════════════════════════════════════ */
const PALETTES = {
  teal: {
    id: 'teal', name: 'Teal',
    c1: '#004140', c2: '#ED7D31',
    colorway: ['#004140','#ED7D31','#2e9e6b','#4e7bb8','#9b59b6','#e74c3c','#1abc9c','#f39c12','#64748b','#0f766e','#b45309','#be123c','#4338ca','#16a34a','#0891b2','#9333ea'],
  },
  indigo: {
    id: 'indigo', name: 'Índigo',
    c1: '#312e81', c2: '#f59e0b',
    colorway: ['#4338ca','#f59e0b','#0ea5e9','#10b981','#8b5cf6','#ef4444','#06b6d4','#f97316','#64748b','#0369a1','#15803d','#be123c','#7e22ce','#ca8a04','#0f766e','#db2777'],
  },
  emerald: {
    id: 'emerald', name: 'Esmeralda',
    c1: '#064e3b', c2: '#fbbf24',
    colorway: ['#059669','#fbbf24','#3b82f6','#a855f7','#f43f5e','#14b8a6','#f97316','#6366f1','#64748b','#047857','#b45309','#be123c','#2563eb','#7c3aed','#0891b2','#65a30d'],
  },
  violet: {
    id: 'violet', name: 'Violeta',
    c1: '#4c1d95', c2: '#f59e0b',
    colorway: ['#7c3aed','#f59e0b','#ec4899','#34d399','#60a5fa','#f87171','#a3e635','#fb923c','#64748b','#4338ca','#be123c','#047857','#0369a1','#ca8a04','#0891b2','#16a34a'],
  },
  ruby: {
    id: 'ruby', name: 'Rubi',
    c1: '#7f1d1d', c2: '#fbbf24',
    colorway: ['#dc2626','#fbbf24','#3b82f6','#34d399','#a855f7','#06b6d4','#f97316','#6366f1','#64748b','#be123c','#047857','#0369a1','#7c3aed','#ca8a04','#0f766e','#db2777'],
  },
  slate: {
    id: 'slate', name: 'Ardósia',
    c1: '#1e3a5f', c2: '#38bdf8',
    colorway: ['#2563eb','#38bdf8','#10b981','#f59e0b','#a78bfa','#f43f5e','#fb923c','#34d399','#64748b','#0f766e','#b45309','#be123c','#7c3aed','#0369a1','#65a30d','#db2777'],
  },
  ocean: {
    id: 'ocean', name: 'Oceano',
    c1: '#075985', c2: '#14b8a6',
    colorway: ['#0284c7','#14b8a6','#f59e0b','#8b5cf6','#10b981','#ef4444','#6366f1','#f97316','#64748b','#0e7490','#7c3aed','#65a30d','#be123c','#ca8a04','#0891b2','#db2777'],
  },
  citrus: {
    id: 'citrus', name: 'Cítrico',
    c1: '#3f6212', c2: '#f97316',
    colorway: ['#65a30d','#f97316','#0ea5e9','#a855f7','#14b8a6','#ef4444','#84cc16','#f59e0b','#64748b','#15803d','#2563eb','#be123c','#7c3aed','#0891b2','#ca8a04','#db2777'],
  },
  graphite: {
    id: 'graphite', name: 'Grafite',
    c1: '#334155', c2: '#22c55e',
    colorway: ['#475569','#22c55e','#3b82f6','#f59e0b','#a855f7','#ef4444','#06b6d4','#f97316','#94a3b8','#0f766e','#4338ca','#be123c','#65a30d','#0369a1','#ca8a04','#db2777'],
  },
};

let activePaletteName = localStorage.getItem('rcw-palette') || 'teal';

function pc(n) {
  const colorway = PALETTES[activePaletteName]?.colorway || PALETTES.teal.colorway;
  return colorway[n % colorway.length] || '#004140';
}
function accentColor() { return PALETTES[activePaletteName]?.c1 || '#004140'; }
function accent2Color() { return PALETTES[activePaletteName]?.c2 || '#ED7D31'; }

/* ════════════════════════════════════════════════════════════
   CATALOG — Define todos os gráficos disponíveis
════════════════════════════════════════════════════════════ */
const CHART_TYPES = {
  bar_v:   { label: 'Barras',    icon: '▌' },
  bar_h:   { label: 'Barras H.', icon: '▬' },
  line:    { label: 'Linha',     icon: '∿' },
  area:    { label: 'Área',      icon: '◭' },
  pie:     { label: 'Pizza',     icon: '◔' },
  donut:   { label: 'Donut',     icon: '◎' },
  scatter: { label: 'Dispersão', icon: '⊹' },
  cards:   { label: 'Cartões',   icon: '☰' },
  timeline:{ label: 'Linha do tempo', icon: '-' },
};

const BUILTIN_CATALOG = [
  { id:'kpis',         name:'KPIs da Sprint',                    icon:'📊', group:'Resumo',       types:['cards'],                    subtitle:'Indicadores chave de desempenho da sprint' },
  { id:'flow_metrics', name:'M\u00e9tricas de Fluxo',            icon:'\u21c4', group:'Resumo',       types:['cards'],                    subtitle:'WIP m\u00e9dio, throughput semanal, efici\u00eancia e previsibilidade do fluxo' },
  { id:'scope_quality',name:'Escopo e Qualidade',                icon:'\u25c7', group:'Resumo',       types:['cards'],                    subtitle:'Say/Do, bugs, ajustes, impedimentos e crescimento de escopo' },
  { id:'time_health',  name:'Prazo e Calend\u00e1rio',            icon:'\u25f7', group:'Resumo',       types:['cards'],                    subtitle:'Dias restantes versus trabalho restante e tempo de primeira resposta' },
  { id:'roadmap',      name:'Roadmap',                            icon:'\u25c8', group:'Resumo',       types:['cards','timeline'],         subtitle:'Marcos do projeto importados do Planner ou colados no upload' },
  { id:'burndown',     name:'Burndown Geral',                    icon:'📉', group:'Andamento', subgroup:'Burn', types:['line','area','bar_v'],       subtitle:'Progresso de tarefas ao longo do mês' },
  { id:'burndown_hu',  name:'Burndown por HU',                   icon:'📉', group:'Andamento', subgroup:'Burn', types:['line','area','bar_v'],       subtitle:'Progresso de histórias de usuário ao longo do mês' },
  { id:'burndown_sp',  name:'Burndown por Story Points',         icon:'🎯', group:'Andamento', subgroup:'Burn', types:['line','area','bar_v'],       subtitle:'Progresso em Story Points ao longo do mês' },
  { id:'burnup',       name:'Burnup Geral',                      icon:'📈', group:'Andamento', subgroup:'Burn', types:['line','area','bar_v'],       subtitle:'Entrega acumulada versus escopo total de tarefas' },
  { id:'burnup_hu',    name:'Burnup por HU',                     icon:'📈', group:'Andamento', subgroup:'Burn', types:['line','area','bar_v'],       subtitle:'Entrega acumulada versus escopo total de histórias de usuário' },
  { id:'burnup_sp',    name:'Burnup por Story Points',           icon:'🎯', group:'Andamento', subgroup:'Burn', types:['line','area','bar_v'],       subtitle:'Story Points entregues acumulados versus escopo total' },
  { id:'cfd',          name:'CFD – Fluxo Cumulativo',            icon:'📈', group:'Andamento',     types:['area','line','bar_v'],       subtitle:'Distribuição de tarefas por status ao longo do tempo' },
  { id:'wip',          name:'WIP por Perfil',                    icon:'🧭', group:'Andamento',     types:['line','area','bar_v'],       subtitle:'Backlog, produção e concluído ao longo do tempo com filtro por perfil' },
  { id:'hu_tasks',     name:'Tarefas por HU',                    icon:'📋', group:'Distribuição',  types:['bar_v','bar_h','pie','donut'],subtitle:'Quantidade de tarefas concluídas e pendentes por HU' },
  { id:'areas',        name:'Áreas de Trabalho',                 icon:'👥', group:'Distribuição',  types:['bar_h','bar_v','pie','donut'],subtitle:'Tarefas por área de atuação da equipe' },
  { id:'categoria',    name:'Por Categoria',                     icon:'🏷️', group:'Distribuição',  types:['bar_h','bar_v','pie','donut'],subtitle:'Tarefas agrupadas por categoria / rótulo' },
  { id:'colaborador',  name:'Por Colaborador',                   icon:'👤', group:'Distribuição',  types:['bar_h','bar_v'],             subtitle:'Tarefas atribuídas por membro da equipe' },
  { id:'hu_inout',     name:'Em HU vs Fora de HU',               icon:'🔵', group:'Distribuição',  types:['donut','pie','bar_v'],       subtitle:'Proporção de tarefas vinculadas a Histórias de Usuário' },
  { id:'dispersao',    name:'CYCLE TIME SCATTERPLOT (data + volume da entrega)',            icon:'⊹',  group:'Tempo',         types:['scatter'],                  subtitle:'CYCLE TIME SCATTERPLOT (data + volume da entrega)' },
  { id:'rotulos',      name:'Lead & Cycle Time por Rótulo',      icon:'⏱',  group:'Tempo',         types:['bar_h','bar_v'],             subtitle:'Tempos médios de entrega por rótulo / categoria' },
  { id:'responsaveis', name:'Lead & Cycle Time por Responsável', icon:'⏱',  group:'Tempo',         types:['bar_h','bar_v'],             subtitle:'Tempos médios de entrega por membro da equipe' },
  { id:'aging',        name:'Aging',                             icon:'⌛',  group:'Tempo',         types:['bar_h','bar_v'],             subtitle:'Idade média das tarefas abertas por área, categoria ou colaborador' },
  { id:'aging_tasks',  name:'Aging por Tarefa',                  icon:'🧾', group:'Tempo',         types:['bar_h'],                     subtitle:'Idade das tarefas abertas, com filtro por múltiplos rótulos' },
  { id:'histograma',   name:'Histograma de Cycle Time',          icon:'📊', group:'Tempo',         types:['bar_v','line'],              subtitle:'Distribuição de frequência do cycle time das tarefas' },
];

const deliveryPersonInsertIndex = BUILTIN_CATALOG.findIndex(item => item.id === 'flow_metrics');
BUILTIN_CATALOG.splice(
  deliveryPersonInsertIndex < 0 ? 1 : deliveryPersonInsertIndex,
  0,
  { id:'delivery_person', name:'Entrega por Pessoa', icon:'▥', group:'Resumo', types:['bar_v','donut','pie'], subtitle:'Tarefas conclu\u00eddas e Story Points entregues por dia ou por pessoa' },
);

const burnUnplannedInsertIndex = BUILTIN_CATALOG.findIndex(item => item.id === 'cfd');
BUILTIN_CATALOG.splice(
  burnUnplannedInsertIndex < 0 ? BUILTIN_CATALOG.length : burnUnplannedInsertIndex,
  0,
  { id:'burndown_nao_prev', name:'Burndown N\u00e3o previstos por Tarefas', icon:'!', group:'Andamento', subgroup:'Burn', subgroup2:'N\u00e3o previstos', types:['line','area','bar_v'], subtitle:'Tarefas n\u00e3o previstas: entrada, conclus\u00e3o e saldo ao longo da sprint' },
  { id:'burnup_nao_prev',   name:'Burnup N\u00e3o previstos por Tarefas',   icon:'!', group:'Andamento', subgroup:'Burn', subgroup2:'N\u00e3o previstos', types:['line','area','bar_v'], subtitle:'Entrega acumulada de tarefas n\u00e3o previstas versus escopo acumulado' },
  { id:'burndown_nao_prev_hu', name:'Burndown N\u00e3o previstos por HU', icon:'!', group:'Andamento', subgroup:'Burn', subgroup2:'N\u00e3o previstos', types:['line','area','bar_v'], subtitle:'Tarefas n\u00e3o previstas vinculadas a HU: entrada, conclus\u00e3o e saldo' },
  { id:'burnup_nao_prev_hu',   name:'Burnup N\u00e3o previstos por HU',   icon:'!', group:'Andamento', subgroup:'Burn', subgroup2:'N\u00e3o previstos', types:['line','area','bar_v'], subtitle:'Entrega acumulada de tarefas n\u00e3o previstas vinculadas a HU' },
);

const CUSTOM_CHART_SOURCES = {
  hu_tasks: {
    label:'Tarefas por HU',
    icon:'📋',
    metrics:{
      done:'Concluidas',
      pending:'Pendentes',
      total:'Total de tarefas',
    },
    types:['bar_v','bar_h','pie','donut'],
  },
  areas: {
    label:'Areas de Trabalho',
    icon:'👥',
    metrics:{
      done:'Concluidas',
      pending:'Pendentes',
      total:'Total de tarefas',
    },
    types:['bar_v','bar_h','pie','donut'],
  },
  categoria: {
    label:'Categorias / Rotulos',
    icon:'🏷️',
    metrics:{
      done:'Concluidas',
      pending:'Pendentes',
      total:'Total de tarefas',
    },
    types:['bar_v','bar_h','pie','donut'],
  },
  colaborador: {
    label:'Colaboradores',
    icon:'👤',
    metrics:{
      done:'Concluidas',
      pending:'Pendentes',
      total:'Total de tarefas',
    },
    types:['bar_v','bar_h','pie','donut'],
  },
  hu_inout: {
    label:'Em HU vs Fora de HU',
    icon:'🔵',
    metrics:{ count:'Quantidade' },
    types:['bar_v','pie','donut'],
  },
  rotulos: {
    label:'Timing por Rotulo',
    icon:'⏱',
    metrics:{
      done:'Concluidas',
      pending:'Pendentes',
      lead_time:'Lead Time medio',
      cycle_time:'Cycle Time medio',
    },
    types:['bar_v','bar_h'],
  },
  responsaveis: {
    label:'Timing por Responsavel',
    icon:'⏱',
    metrics:{
      done:'Concluidas',
      pending:'Pendentes',
      lead_time:'Lead Time medio',
      cycle_time:'Cycle Time medio',
    },
    types:['bar_v','bar_h'],
  },
  aging_tasks: {
    label:'Aging por Tarefa',
    icon:'🧾',
    metrics:{ count:'Aging por tarefa' },
    types:['bar_h'],
  },
  histograma: {
    label:'Histograma de Cycle Time',
    icon:'📊',
    metrics:{ count:'Frequencia' },
    types:['bar_v','line'],
  },
  wip_profile: {
    label:'WIP por perfil',
    icon:'🧭',
    metrics:{ state_mix:'Backlog x Produção x Concluído' },
    types:['bar_v','line','area'],
  },
};
