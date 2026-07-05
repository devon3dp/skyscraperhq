// QSB Tower V1.3 — qsb_tower_2d.js (V2 — full recap + render model)
// Phase: QSB_TOWER_FULL_RECAP_AND_3D_DASHBOARD_REBUILD_V1
//
// Larger, brighter SVG skyscraper that ingests:
//   state.dashboard_render_model  — floors, highlighted floors, routes, lift shafts
//   state.floor_name_map          — { "1": "Operations Department", ... "53": "Tower Command Department" }
// and falls back to /api/unified floors[] if those are missing.
//
// Features:
//   - 53 stacked floors (F1–F53), roof (F54), penthouse (F55 = QSB Kernel), ground (0)
//   - 9 lift shafts with continuously animated capsules
//   - route lines from render_model.routes connecting source→target floors
//     and pulsing in their team color
//   - named worker dots with abbreviated DOM-overlay labels
//   - packet circles flying source→target along the shafts
//   - pseudo-3D rotation effect (CSS-driven, toggleable)
//   - "Show All Floor Names" mode that labels every floor on the right
//   - "Highlight category" mode (trading / models / risk) that glows
//     all floors in a category
//   - Floor click → onPick({kind:'floor', number, label, ...})
//   - Worker click → onPick({kind:'worker', id, ...})
//   - hudTip on hover

(function () {
  'use strict';

  const NS = 'http://www.w3.org/2000/svg';

  // ── viewport / geometry ───────────────────────────────────────────────
  const VIEW_W = 820;
  const VIEW_H = 1160;
  const TOWER_TOP_Y = 36;
  const TOWER_BOT_Y = 1116;
  const CENTER_X    = VIEW_W / 2;
  const TOP_WIDTH   = 380;
  const BOT_WIDTH   = 560;

  const ROOF_H   = 30;
  const PENT_H   = 36;
  const GROUND_H = 28;
  const FLOORS_COUNT = 53;

  // ── colors (must match render_model categories) ───────────────────────
  const PACKET_COLORS = {
    worker:   '#4dffb0',
    strategy: '#5ce0ff',
    ledger:   '#ffd24c',
    openclaw: '#b08aff',
    kernel:   '#6ab8ff',
    airllm:   '#7fc8ff',
    paper:    '#ffe066',
    stocks:   '#eaf2ff',
    crypto:   '#ffb86c',
    cross:    '#c8a6ff',
    risk:     '#ff5060',
    routing:  '#8aa8ff',
  };
  const COLOR_BY_LABEL = {
    green:  PACKET_COLORS.worker,
    cyan:   PACKET_COLORS.strategy,
    gold:   PACKET_COLORS.ledger,
    purple: PACKET_COLORS.cross,
    white:  PACKET_COLORS.stocks,
    blue:   PACKET_COLORS.kernel,
    yellow: PACKET_COLORS.paper,
    orange: PACKET_COLORS.crypto,
    red:    PACKET_COLORS.risk,
  };

  // Category → glow palette (mirrors src/tower/dashboard_render_model.py)
  const CATEGORY_PALETTE = {
    kernel:               { color: '#ffd24c', glow: 1.20 },
    command:              { color: '#6ab8ff', glow: 1.10 },
    trading_fx:           { color: '#5ce0ff', glow: 1.05 },
    trading_crypto:       { color: '#ffb86c', glow: 1.05 },
    trading_equities:     { color: '#eaf2ff', glow: 1.10 },
    model_lane:           { color: '#5ce0ff', glow: 0.90 },
    advisory_model:       { color: '#7fc8ff', glow: 1.05 },
    routing:              { color: '#8aa8ff', glow: 0.85 },
    worker_coordination:  { color: '#4dffb0', glow: 0.85 },
    risk:                 { color: '#b08aff', glow: 1.00 },
    audit:                { color: '#ffc940', glow: 1.00 },
    strategy:             { color: '#5ce0ff', glow: 0.95 },
    sandbox:              { color: '#4dffb0', glow: 0.90 },
    monitoring:           { color: '#88a3c2', glow: 0.55 },
    infrastructure:       { color: '#5b78a4', glow: 0.45 },
    vacant:               { color: '#3a5070', glow: 0.20 },
    locked_external:      { color: '#b08aff', glow: 0.45 },
  };

  // Category groups for the highlight buttons
  const HIGHLIGHT_GROUPS = {
    trading: ['trading_fx', 'trading_crypto', 'trading_equities'],
    models:  ['model_lane', 'advisory_model', 'routing'],
    risk:    ['risk', 'audit', 'sandbox', 'strategy'],
  };

  // Fallback name map if state has no render_model nor floor_name_map yet
  const FALLBACK_NAMES = {
    23: 'AIR LLM Operations Department',
    24: 'Model Routing Department',
    25: 'Agent Coordination Department',
    30: 'Permissions Department',
    31: 'Audit Department',
    37: 'Simulation Labs',
    38: 'Sandbox Operations',
    41: 'OANDA Trading Floor',
    42: 'Binance Trading Floor',
    43: 'Stock Exchange Trading Floor',
    53: 'Tower Command Department',
  };

  // ── State container ───────────────────────────────────────────────────
  const T = {
    host: null,
    svg: null,
    hudTipEl: null,
    onPick: null,
    onDiag: null,

    // SVG nodes
    layerBg: null, layerRoutes: null, layerShafts: null, layerFloors: null,
    layerLabels: null, layerLabelsAll: null, layerWorkers: null,
    layerCapsules: null, layerPackets: null, layerForeground: null,

    floorRects: {},          // n -> SVGRect
    floorLabels: {},         // n -> SVGText (highlighted-only labels)
    floorLabelsAll: {},      // n -> SVGText (show-all-names mode)
    routeLines: [],          // [{el, src, dst, color, advisory}]
    shafts: [],              // [{ topX, botX, line, ...}]
    capsules: [],            // [{rect, label, shaftIdx, phase, speed}]
    workerNodes: {},         // id -> {g, dot, text, baseX, baseY, pulsePhase, cls}
    activePackets: [],

    lastPacketSig: null,
    rafHandle: null,
    paused: false,

    // Modes
    rotateOn: true,
    showAllNames: false,
    highlightGroup: null,    // null | 'trading' | 'models' | 'risk'
    categoryByFloor: {},     // n -> category from render_model

    diag: {
      renderer: 'svg_2d_pseudo_3d',
      svg_w: VIEW_W, svg_h: VIEW_H,
      floors_rendered: 0,
      shafts_rendered: 0,
      capsules_rendered: 0,
      workers_rendered: 0,
      routes_rendered: 0,
      packets_active: 0,
      last_state_ts: null,
      last_error: '',
    },
    state: null,
  };
  window.QSB_TOWER_2D = T;

  // ── helpers ────────────────────────────────────────────────────────────
  function mk(tag, attrs, parent) {
    const el = document.createElementNS(NS, tag);
    if (attrs) for (const k in attrs) el.setAttribute(k, attrs[k]);
    if (parent) parent.appendChild(el);
    return el;
  }
  function esc(s) {
    return String(s == null ? '' : s).replace(/[&<>"']/g, (c) =>
      ({ '&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;' }[c]));
  }
  function parseFloorNum(s) {
    if (s == null) return null;
    if (typeof s === 'number') return s;
    if (s === 'ground') return 0;
    if (s === 'roof' || s === 'roof_lock') return 54;
    if (s === 'penthouse' || s === 'penthouse_kernel_review') return 55;
    const m = /^(?:floor_)?(\d{1,2})$/.exec(s);
    if (m) return parseInt(m[1], 10);
    return null;
  }
  function hashStr(s) { let h = 0; if (!s) return 0; for (let i = 0; i < s.length; i++) { h = ((h << 5) - h) + s.charCodeAt(i); h |= 0; } return h; }
  function abbrev(name) {
    if (!name) return '';
    const parts = String(name).split(/\s+/).filter(Boolean);
    if (parts.length === 1) return parts[0].slice(0, 6);
    return parts.map((p) => p[0]).join('').slice(0, 4).toUpperCase();
  }

  // ── geometry ───────────────────────────────────────────────────────────
  function slabRange(n) {
    if (n === 54) return [TOWER_TOP_Y, TOWER_TOP_Y + ROOF_H];
    // F55 is the penthouse — kernel lives here, NOT F53 (Tower Command).
    if (n === 55) return [TOWER_TOP_Y + ROOF_H, TOWER_TOP_Y + ROOF_H + PENT_H];
    if (n === 0)  return [TOWER_BOT_Y - GROUND_H, TOWER_BOT_Y];
    // F1–F53 stack in the slabs below the penthouse zone (53 floors total).
    const totalH = (TOWER_BOT_Y - GROUND_H) - (TOWER_TOP_Y + ROOF_H + PENT_H);
    const slabH = totalH / 53;
    const idxFromTop = 53 - n;
    const top = TOWER_TOP_Y + ROOF_H + PENT_H + idxFromTop * slabH;
    return [top, top + slabH];
  }
  function slabCenterY(n) { const [a, b] = slabRange(n); return (a + b) / 2; }
  function widthAt(y) {
    const u = (y - TOWER_TOP_Y) / (TOWER_BOT_Y - TOWER_TOP_Y);
    return TOP_WIDTH + (BOT_WIDTH - TOP_WIDTH) * u;
  }
  function shaftXAt(shaftIdx, y) {
    const s = T.shafts[shaftIdx];
    if (!s) return CENTER_X;
    const u = (y - TOWER_TOP_Y) / (TOWER_BOT_Y - TOWER_TOP_Y);
    return s.topX + (s.botX - s.topX) * u;
  }

  // ── build skeleton ─────────────────────────────────────────────────────
  function build() {
    T.host.innerHTML = '';
    const svg = mk('svg', {
      viewBox: '0 0 ' + VIEW_W + ' ' + VIEW_H,
      preserveAspectRatio: 'xMidYMid meet',
      class: 'qsb-tower-svg',
    }, T.host);
    T.svg = svg;

    const defs = mk('defs', null, svg);
    const bg = mk('radialGradient', { id: 'qsbBg', cx: '50%', cy: '0%', r: '95%' }, defs);
    mk('stop', { offset: '0%',  'stop-color': '#1c3168' }, bg);
    mk('stop', { offset: '60%', 'stop-color': '#070d22' }, bg);
    mk('stop', { offset: '100%','stop-color': '#02050d' }, bg);

    const towerGrad = mk('linearGradient', { id: 'qsbTowerGrad', x1: '0', y1: '0', x2: '0', y2: '1' }, defs);
    mk('stop', { offset: '0%',   'stop-color': '#14274a' }, towerGrad);
    mk('stop', { offset: '100%', 'stop-color': '#06101e' }, towerGrad);

    const floorGrad = mk('linearGradient', { id: 'qsbFloorGrad', x1: '0', y1: '0', x2: '0', y2: '1' }, defs);
    mk('stop', { offset: '0%',   'stop-color': '#1d3360' }, floorGrad);
    mk('stop', { offset: '100%', 'stop-color': '#0d1a36' }, floorGrad);

    const haloGrad = mk('radialGradient', { id: 'qsbHalo', cx: '50%', cy: '50%', r: '60%' }, defs);
    mk('stop', { offset: '0%',   'stop-color': 'rgba(255,201,64,0.85)' }, haloGrad);
    mk('stop', { offset: '60%',  'stop-color': 'rgba(255,201,64,0.2)' }, haloGrad);
    mk('stop', { offset: '100%', 'stop-color': 'rgba(255,201,64,0)' }, haloGrad);

    const glow = mk('filter', { id: 'qsbGlow', x: '-50%', y: '-50%', width: '200%', height: '200%' }, defs);
    mk('feGaussianBlur', { stdDeviation: '2.8', result: 'blur' }, glow);
    const merge = mk('feMerge', null, glow);
    mk('feMergeNode', { in: 'blur' }, merge);
    mk('feMergeNode', { in: 'SourceGraphic' }, merge);

    // Layered groups (back to front)
    T.layerBg       = mk('g', { class: 'qsb-bg' }, svg);
    T.layerRoutes   = mk('g', { class: 'qsb-routes' }, svg);
    T.layerShafts   = mk('g', { class: 'qsb-shafts' }, svg);
    T.layerFloors   = mk('g', { class: 'qsb-floors' }, svg);
    T.layerLabelsAll= mk('g', { class: 'qsb-labels-all' }, svg);
    T.layerLabels   = mk('g', { class: 'qsb-labels' }, svg);
    T.layerWorkers  = mk('g', { class: 'qsb-workers' }, svg);
    T.layerCapsules = mk('g', { class: 'qsb-capsules' }, svg);
    T.layerPackets  = mk('g', { class: 'qsb-packets' }, svg);
    T.layerForeground = mk('g', { class: 'qsb-fg' }, svg);

    // BG: sky + stars + plaza
    mk('rect', { x: 0, y: 0, width: VIEW_W, height: VIEW_H, fill: 'url(#qsbBg)' }, T.layerBg);
    for (let i = 0; i < 110; i++) {
      mk('circle', {
        cx: Math.random() * VIEW_W,
        cy: Math.random() * (TOWER_TOP_Y + 70),
        r: Math.random() * 0.9 + 0.2,
        fill: '#9fc6ff', opacity: (0.45 + Math.random() * 0.55).toFixed(2),
      }, T.layerBg);
    }

    // Tower body
    const trapezoid = [
      [CENTER_X - TOP_WIDTH / 2, TOWER_TOP_Y],
      [CENTER_X + TOP_WIDTH / 2, TOWER_TOP_Y],
      [CENTER_X + BOT_WIDTH / 2, TOWER_BOT_Y],
      [CENTER_X - BOT_WIDTH / 2, TOWER_BOT_Y],
    ].map((p) => p.join(',')).join(' ');
    mk('polygon', {
      points: trapezoid,
      fill: 'url(#qsbTowerGrad)',
      stroke: 'rgba(120,200,255,0.55)',
      'stroke-width': '1.8',
      filter: 'url(#qsbGlow)',
    }, T.layerBg);

    // Ground ellipse
    mk('ellipse', {
      cx: CENTER_X, cy: TOWER_BOT_Y + 16,
      rx: BOT_WIDTH / 2 + 80, ry: 18,
      fill: 'rgba(60,120,200,0.18)',
      stroke: 'rgba(90,160,230,0.4)',
      'stroke-width': '0.8',
    }, T.layerBg);

    // Penthouse halo
    const pentY = slabCenterY(55);
    mk('circle', {
      cx: CENTER_X, cy: pentY,
      r: 110, fill: 'url(#qsbHalo)',
    }, T.layerBg);

    buildShafts();
    buildFloorSlabs();
    buildCapsules();

    // Roof spire
    mk('line', {
      x1: CENTER_X, y1: TOWER_TOP_Y - 8,
      x2: CENTER_X, y2: TOWER_TOP_Y - 46,
      stroke: '#8fc8ff', 'stroke-width': '1.6',
      filter: 'url(#qsbGlow)',
    }, T.layerForeground);
    mk('circle', { cx: CENTER_X, cy: TOWER_TOP_Y - 46, r: 3.2, fill: '#cfe6ff', filter: 'url(#qsbGlow)' }, T.layerForeground);

    // Caption
    mk('text', {
      x: 14, y: 24, fill: '#cfe0ff', 'font-size': '13',
      'font-family': 'Inter,Segoe UI,system-ui', 'font-weight': '700',
      'letter-spacing': '0.9',
    }, T.layerForeground).textContent = 'QSB SKYSCRAPER · SVG PSEUDO-3D';
    mk('text', {
      x: VIEW_W - 14, y: 24, fill: '#88a3c2', 'font-size': '11',
      'font-family': 'Inter,Segoe UI,system-ui', 'text-anchor': 'end',
    }, T.layerForeground).textContent = 'render model · floor_name_map · advisory routes';

    T.diag.svg_w = VIEW_W; T.diag.svg_h = VIEW_H;
    T.diag.shafts_rendered = T.shafts.length;
    T.diag.capsules_rendered = T.capsules.length;
    pushDiag();
  }

  function buildShafts() {
    const numShafts = 9;
    for (let i = 0; i < numShafts; i++) {
      const p = (i - (numShafts - 1) / 2) / numShafts;
      const topX = CENTER_X + p * (TOP_WIDTH - 30);
      const botX = CENTER_X + p * (BOT_WIDTH - 30);
      const path = mk('line', {
        x1: topX, y1: TOWER_TOP_Y + ROOF_H,
        x2: botX, y2: TOWER_BOT_Y - GROUND_H,
        stroke: 'rgba(80,170,240,0.36)', 'stroke-width': '1.4',
      }, T.layerShafts);
      mk('line', {
        x1: topX, y1: TOWER_TOP_Y + ROOF_H,
        x2: botX, y2: TOWER_BOT_Y - GROUND_H,
        stroke: 'rgba(110,210,255,0.22)', 'stroke-width': '5.0',
        filter: 'url(#qsbGlow)',
      }, T.layerShafts);
      T.shafts.push({ topX, botX, line: path });
    }
  }

  function buildFloorSlabs() {
    let count = 0;
    // Top→bottom render order: roof(54), penthouse(55=Kernel), F53..F1, ground(0)
    const order = [54, 55, ...Array.from({ length: 53 }, (_, i) => 53 - i), 0];
    for (const n of order) {
      const [top, bot] = slabRange(n);
      const cy = (top + bot) / 2;
      const w = widthAt(cy) - 16;
      const x = CENTER_X - w / 2;
      const h = bot - top - 1;

      let fill = 'url(#qsbFloorGrad)';
      let stroke = 'rgba(90,160,220,0.40)';
      let filter = '';
      let opacity = '1';
      let cls = 'fl';

      if (n === 54) { fill = 'rgba(176,138,255,0.45)'; stroke = 'rgba(176,138,255,0.9)';  filter = 'url(#qsbGlow)'; cls = 'fl fl-roof'; }
      else if (n === 55) { fill = 'rgba(255,201,64,0.55)'; stroke = 'rgba(255,224,128,0.95)'; filter = 'url(#qsbGlow)'; cls = 'fl fl-penthouse'; }
      else if (n === 0)  { fill = 'rgba(106,184,255,0.32)'; stroke = 'rgba(106,184,255,0.7)';  cls = 'fl fl-ground'; }

      const rect = mk('rect', {
        x: x, y: top + 0.5, width: w, height: h,
        rx: 1.6, ry: 1.6,
        fill, stroke, 'stroke-width': '1.0',
        'fill-opacity': opacity,
        class: cls,
        'data-floor': String(n),
        filter,
      }, T.layerFloors);
      T.floorRects[n] = rect;

      rect.addEventListener('mouseenter', () => showTipForFloor(n));
      rect.addEventListener('mouseleave', () => hideTip());
      rect.addEventListener('click', () => {
        if (typeof T.onPick === 'function') {
          T.onPick({
            kind: 'floor',
            number: n,
            display_name: rect.dataset.displayName || null,
            category: rect.dataset.category || null,
            status: rect.dataset.status || null,
          });
        }
      });
      count++;
    }
    T.diag.floors_rendered = count;
  }

  function buildCapsules() {
    for (let i = 0; i < T.shafts.length; i++) {
      const cap = mk('rect', {
        width: 20, height: 14,
        rx: 4.5, ry: 4.5,
        fill: 'rgba(70,140,235,0.85)',
        stroke: '#bfe0ff', 'stroke-width': '0.9',
        filter: 'url(#qsbGlow)',
      }, T.layerCapsules);
      const label = mk('text', {
        fill: '#ffffff', 'font-size': '8.4',
        'font-family': 'Inter,Segoe UI,system-ui', 'font-weight': '700',
        'text-anchor': 'middle',
      }, T.layerCapsules);
      const initials = ['MS','SW','RS','PS','KC','LC','OM','SI','CA'][i] || '··';
      label.textContent = initials;
      T.capsules.push({
        rect: cap, label, shaftIdx: i,
        phase: Math.random() * Math.PI * 2,
        speed: 0.18 + Math.random() * 0.16,
      });
    }
  }

  // ── label rendering (driven by state.floor_name_map) ───────────────────
  function refreshLabels(state) {
    // Clear existing label layers
    while (T.layerLabels.firstChild) T.layerLabels.removeChild(T.layerLabels.firstChild);
    while (T.layerLabelsAll.firstChild) T.layerLabelsAll.removeChild(T.layerLabelsAll.firstChild);
    T.floorLabels = {}; T.floorLabelsAll = {};

    const nameMap = pickNameMap(state);
    const render = (state && state.dashboard_render_model) || {};
    const highlightedSet = new Set(((render && render.highlighted_floors) || []).map((id) => parseFloorNum(id)));

    // Numbers on the left every 5 + always for highlighted floors
    for (let n = 1; n <= 53; n++) {
      const hl = highlightedSet.has(n) || !!FALLBACK_NAMES[n];
      const show5 = (n % 5 === 0) || (n === 1);
      if (!hl && !show5) continue;
      const cy = slabCenterY(n);
      const x = CENTER_X - widthAt(cy) / 2 - 10;
      const t = mk('text', {
        x: x, y: cy + 3.2,
        fill: hl ? '#ffffff' : '#7e9cc4',
        'font-size': hl ? '11' : '10',
        'font-family': 'Inter,Segoe UI,system-ui',
        'font-weight': hl ? '700' : '500',
        'text-anchor': 'end',
      }, T.layerLabels);
      t.textContent = n;
    }

    // Highlighted floor names on the right
    for (let n = 1; n <= 53; n++) {
      if (!highlightedSet.has(n) && !FALLBACK_NAMES[n]) continue;
      const name = nameMap[n] || FALLBACK_NAMES[n] || ('Floor ' + n);
      const cy = slabCenterY(n);
      const x = CENTER_X + widthAt(cy) / 2 + 10;
      const t = mk('text', {
        x: x, y: cy + 3.2,
        fill: pickHighlightColor(n, state),
        'font-size': '11.5',
        'font-family': 'Inter,Segoe UI,system-ui',
        'font-weight': '700', 'letter-spacing': '0.45',
      }, T.layerLabels);
      t.textContent = name;
      T.floorLabels[n] = t;
    }

    // Roof + Ground side labels
    const roofY = slabCenterY(54);
    const tRoof = mk('text', {
      x: CENTER_X + widthAt(roofY) / 2 + 10, y: roofY + 3.2,
      fill: '#c8a6ff', 'font-size': '11.5', 'font-weight': '700',
      'font-family': 'Inter,Segoe UI,system-ui',
    }, T.layerLabels);
    tRoof.textContent = 'Roof — External Providers (LOCKED)';

    const groundY = slabCenterY(0);
    const tGround = mk('text', {
      x: CENTER_X + widthAt(groundY) / 2 + 10, y: groundY + 3.2,
      fill: '#9fc4ff', 'font-size': '11.5', 'font-weight': '700',
      'font-family': 'Inter,Segoe UI,system-ui',
    }, T.layerLabels);
    tGround.textContent = 'Ground / Reception Lobby';

    // "Show All Names" mode: label EVERY floor on the right with a small font
    if (T.showAllNames) {
      for (let n = 1; n <= 53; n++) {
        const name = nameMap[n] || FALLBACK_NAMES[n] || ('Floor ' + n);
        const cy = slabCenterY(n);
        const x = CENTER_X + widthAt(cy) / 2 + 132;
        const t = mk('text', {
          x: x, y: cy + 3,
          fill: '#9fbedd', 'font-size': '9.2',
          'font-family': 'Inter,Segoe UI,system-ui', 'font-weight': '500',
        }, T.layerLabelsAll);
        t.textContent = (n < 10 ? ' ' : '') + n + ' · ' + name;
        T.floorLabelsAll[n] = t;
      }
    }
  }

  function pickNameMap(state) {
    const out = {};
    if (state && state.floor_name_map && typeof state.floor_name_map === 'object') {
      for (const k of Object.keys(state.floor_name_map)) {
        const n = parseInt(k, 10);
        if (Number.isFinite(n)) out[n] = state.floor_name_map[k];
      }
    }
    if (state && state.dashboard_render_model && Array.isArray(state.dashboard_render_model.floors)) {
      state.dashboard_render_model.floors.forEach((f) => {
        if (typeof f.number === 'number' && f.name && !out[f.number]) out[f.number] = f.name;
      });
    }
    if (state && Array.isArray(state.floors)) {
      state.floors.forEach((f) => {
        if (typeof f.number === 'number' && f.department && !out[f.number]) out[f.number] = f.department;
      });
    }
    return out;
  }

  function pickHighlightColor(n, state) {
    const render = (state && state.dashboard_render_model) || {};
    const floors = (render && render.floors) || [];
    const match = floors.find((f) => f.number === n);
    if (match && match.label_color) return match.label_color;
    if (FALLBACK_NAMES[n]) {
      const fallback = {
        23: '#bfe0ff', 24: '#bcd0ff', 25: '#a8ffd0',
        30: '#d6c0ff', 31: '#ffe080',
        37: '#bde6ff', 38: '#a8ffd0',
        41: '#bde6ff', 42: '#ffd39a', 43: '#f2f6ff',
        53: '#ffe080',
      };
      return fallback[n] || '#dbeaff';
    }
    return '#dbeaff';
  }

  // ── routes ────────────────────────────────────────────────────────────
  function refreshRoutes(state) {
    while (T.layerRoutes.firstChild) T.layerRoutes.removeChild(T.layerRoutes.firstChild);
    T.routeLines = [];
    const render = (state && state.dashboard_render_model) || {};
    const routes = render.routes || [];
    routes.forEach((r) => spawnRouteLine(r));
    T.diag.routes_rendered = T.routeLines.length;
  }

  function spawnRouteLine(r) {
    const src = parseFloorNum(r.source_floor);
    let   dst = parseFloorNum(r.target_floor);
    if (src == null) return;
    if (dst == null) {
      if (r.target_floor === 'penthouse' || r.target_floor === 'penthouse_kernel_review') dst = 55;
      else return;
    }
    const ySrc = slabCenterY(src);
    const yDst = slabCenterY(dst);
    const xMid = CENTER_X + (r.advisory_only ? 40 : 0);
    const xSide = CENTER_X + widthAt((ySrc + yDst) / 2) / 2 + 70;
    // Bezier curve along the right side: src center → side bulge → dst center
    const d = `M ${CENTER_X} ${ySrc} Q ${xSide} ${(ySrc + yDst) / 2} ${CENTER_X} ${yDst}`;
    const color = COLOR_BY_LABEL[(r.color || 'cyan').toLowerCase()] || PACKET_COLORS.strategy;
    const el = mk('path', {
      d: d,
      fill: 'none',
      stroke: color,
      'stroke-width': r.advisory_only ? '1.0' : '1.6',
      'stroke-dasharray': r.advisory_only ? '4 5' : '0',
      opacity: '0.42',
      filter: 'url(#qsbGlow)',
    }, T.layerRoutes);
    T.routeLines.push({ el, src, dst, color, advisory: !!r.advisory_only, route_type: r.route_type });
  }

  // ── state ingestion ────────────────────────────────────────────────────
  function applyState(state) {
    if (!state) return;
    T.state = state;
    T.diag.last_state_ts = state.ts || null;

    // Build category map for highlight groups
    const render = (state && state.dashboard_render_model) || {};
    const floors = render.floors || [];
    T.categoryByFloor = {};
    floors.forEach((f) => {
      if (typeof f.number === 'number') T.categoryByFloor[f.number] = f.category || 'infrastructure';
    });

    // Stamp display_name / category onto every floor rect's dataset so hovers
    // and clicks always carry the canonical name from the system.
    const sf = state.floors || [];
    sf.forEach((f) => {
      const rect = T.floorRects[f.number];
      if (!rect) return;
      rect.dataset.displayName = f.display_name || f.canonical_name || f.department || ('Floor ' + f.number);
      rect.dataset.category    = f.category || 'infrastructure';
      rect.dataset.status      = f.status   || 'active';
    });

    // Floor color overrides from render model
    floors.forEach((f) => {
      const n = f.number;
      const rect = T.floorRects[n];
      if (!rect) return;
      if (n === 55 || n === 54 || n === 0) return;     // penthouse/roof/ground keep stylized defaults
      const palette = CATEGORY_PALETTE[f.category] || CATEGORY_PALETTE.infrastructure;
      const baseFill = palette.color;
      const isHigh = !!f.highlight || HIGHLIGHT_GROUPS_HAS(T.highlightGroup, f.category);
      const opacity = isHigh ? 0.7 : (palette.glow >= 0.85 ? 0.55 : palette.glow >= 0.45 ? 0.32 : 0.18);
      rect.setAttribute('fill', baseFill);
      rect.setAttribute('fill-opacity', String(opacity));
      rect.setAttribute('stroke', isHigh ? '#ffffff' : 'rgba(120,170,220,0.45)');
      if (isHigh) rect.setAttribute('filter', 'url(#qsbGlow)');
      else rect.removeAttribute('filter');
    });

    // Penthouse (F55) glow / roof lock pulse driven by kernel + locks
    const active = state.kernel && state.kernel.activation_status === 'active_local_only';
    if (T.floorRects[55]) {
      T.floorRects[55].setAttribute('fill', active ? 'rgba(255,201,64,0.6)' : 'rgba(120,90,30,0.4)');
    }
    const lockTrue = state.lock_count_true || 0;
    if (T.floorRects[54]) {
      T.floorRects[54].setAttribute('fill', lockTrue > 0 ? 'rgba(255,80,96,0.55)' : 'rgba(176,138,255,0.45)');
      T.floorRects[54].setAttribute('stroke', lockTrue > 0 ? 'rgba(255,140,150,0.95)' : 'rgba(176,138,255,0.9)');
    }

    refreshLabels(state);
    refreshRoutes(state);
    refreshWorkers(state);
    spawnPacketsFromState(state, state.ts);
    pushDiag();
  }

  function HIGHLIGHT_GROUPS_HAS(group, category) {
    if (!group) return false;
    const cats = HIGHLIGHT_GROUPS[group] || [];
    return cats.indexOf(category) !== -1;
  }

  // ── workers ────────────────────────────────────────────────────────────
  // V1 redesign: default to "counts_only" — render only per-floor count
  // badges on the exterior. Individual dots/labels only render when the
  // operator explicitly switches mode via the header toggle.
  function refreshWorkers(state) {
    const workers = state.workers || [];
    const mode = (window.QSB && window.QSB.workerViewMode) || 'counts_only';

    // Group by floor regardless — needed for badges.
    const byFloor = {};
    workers.forEach((w) => {
      const f = parseFloorNum(w.home_floor) || 38;
      (byFloor[f] = byFloor[f] || []).push(w);
    });

    // Decide which workers render as individual dots.
    let renderSet = new Set();
    const selectedFloor = (window.QSB && window.QSB.selectedFloor) || null;
    if (mode === 'operational_only') {
      workers.forEach((w) => {
        if (!w.is_simulation) renderSet.add(w.id);
      });
    } else if (mode === 'all_workers_visible') {
      workers.forEach((w) => renderSet.add(w.id));
    } else if (mode === 'selected_floor_and_groups') {
      // V1 rebuild default: per-floor badges + individual workers ONLY on
      // the selected floor (when a floor is selected). No swarm anywhere.
      workers.forEach((w) => {
        const wf = parseFloorNum(w.home_floor);
        if (selectedFloor && wf === selectedFloor) renderSet.add(w.id);
      });
    } else if (mode === 'worker_problems') {
      // Highlight only workers tagged in OpenClaw findings/tickets or
      // sitting on warning.
      const problems = (window.QSB && window.QSB.problemWorkerIds) || new Set();
      workers.forEach((w) => { if (problems.has(w.id)) renderSet.add(w.id); });
    } // counts_only — renderSet stays empty.

    // Remove any individual dots that should no longer render.
    for (const id of Object.keys(T.workerNodes)) {
      if (!renderSet.has(id)) {
        const node = T.workerNodes[id];
        if (node && node.g && node.g.parentNode) node.g.parentNode.removeChild(node.g);
        delete T.workerNodes[id];
      }
    }

    // Render individual dots only for the selected mode.
    for (const fStr of Object.keys(byFloor)) {
      const f = parseInt(fStr, 10);
      const arr = byFloor[f].filter((w) => renderSet.has(w.id));
      if (!arr.length) continue;
      const cy = slabCenterY(f);
      const w = widthAt(cy) - 50;
      arr.forEach((wkr, i) => {
        const offsetX = arr.length === 1 ? 0 : ((i / (arr.length - 1)) - 0.5) * w * 0.85;
        const cx = CENTER_X + offsetX;
        upsertWorker(wkr, cx, cy);
      });
    }

    // Per-floor count badges (always painted; replace each tick).
    let badgeLayer = T.svg && T.svg.querySelector('#v1WorkforceBadges');
    if (T.svg && !badgeLayer) {
      badgeLayer = document.createElementNS(NS, 'g');
      badgeLayer.setAttribute('id', 'v1WorkforceBadges');
      T.svg.appendChild(badgeLayer);
    }
    if (badgeLayer) {
      badgeLayer.innerHTML = '';
      Object.keys(byFloor).forEach((fStr) => {
        const f = parseInt(fStr, 10);
        const arr = byFloor[f];
        const rect = T.floorRects && T.floorRects[f];
        if (!rect) return;
        const x = Number(rect.getAttribute('x'));
        const y = Number(rect.getAttribute('y'));
        const h = Number(rect.getAttribute('height'));
        const opsCount = arr.filter((w) => !w.is_simulation).length;
        const simCount = arr.filter((w) =>  w.is_simulation).length;
        const g = document.createElementNS(NS, 'g');
        g.setAttribute('class', 'qsb-wf-badge');
        g.setAttribute('transform', 'translate(' + (x - 24) + ',' + (y + h / 2) + ')');
        const label = opsCount + (simCount ? ' · ' + simCount + 'S' : '');
        g.innerHTML = (
          '<rect x="-20" y="-7" width="40" height="14" rx="3" ' +
                'fill="rgba(20,30,45,0.78)" stroke="rgba(120,160,210,.5)" />' +
          '<text x="0" y="3" text-anchor="middle" fill="#cfdcef" ' +
                'font-size="9" font-family="JetBrains Mono, monospace">' +
                label + '</text>'
        );
        badgeLayer.appendChild(g);
      });
    }
    T.diag.workers_rendered = Object.keys(T.workerNodes).length;
  }

  function workerCls(w) {
    // V1 worker truth: SIM seeds get their own class so CSS can dim them.
    if (w && (w.is_simulation === true ||
              /^sim[_-]/i.test(w.id || '') ||
              /sim_worker_floor/i.test(w.id || '') ||
              /sim_worker_floor/i.test(w.name || ''))) {
      return 'sim';
    }
    const n = (w.name || w.id || '').toLowerCase();
    if (n.includes('openclaw')) return 'openclaw';
    if (n.includes('airllm'))   return 'airllm';
    if (n.includes('ledger'))   return 'ledger';
    if (n.includes('correlation') || n.includes('risk-on') || n.includes('risk_on')) return 'cross';
    if (n.includes('equity') || n.includes('stock'))         return 'stocks';
    if (n.includes('strategy')) return 'strategy';
    if (n.includes('kernel'))   return 'kernel';
    if (n.includes('paper'))    return 'paper';
    return 'worker';
  }

  function upsertWorker(w, cx, cy) {
    let node = T.workerNodes[w.id];
    const cls = workerCls(w);
    const color = PACKET_COLORS[cls] || PACKET_COLORS.worker;
    if (!node) {
      const g = mk('g', { class: 'qsb-worker wkr-' + cls, 'data-wid': w.id }, T.layerWorkers);
      const dot = mk('circle', {
        cx: cx, cy: cy, r: 3.6,
        fill: color, stroke: '#0a1428', 'stroke-width': '0.7',
        filter: 'url(#qsbGlow)',
      }, g);
      const text = mk('text', {
        x: cx + 6, y: cy + 2.5,
        fill: '#dbeaff', 'font-size': '8.4',
        'font-family': 'Inter,Segoe UI,system-ui',
        'pointer-events': 'none',
      }, g);
      text.textContent = abbrev(w.name || w.id);
      g.addEventListener('mouseenter', () => showTipForWorker(w));
      g.addEventListener('mouseleave', () => hideTip());
      g.addEventListener('click', () => {
        if (typeof T.onPick === 'function') T.onPick({ kind: 'worker', id: w.id, name: w.name, floor: parseFloorNum(w.home_floor), role: w.role });
      });
      node = T.workerNodes[w.id] = { g, dot, text, baseX: cx, baseY: cy, pulsePhase: Math.random() * Math.PI * 2, cls };
    } else {
      node.dot.setAttribute('cx', cx); node.dot.setAttribute('cy', cy);
      node.text.setAttribute('x', cx + 6); node.text.setAttribute('y', cy + 2.5);
      node.baseX = cx; node.baseY = cy;
    }
  }

  // ── packets ────────────────────────────────────────────────────────────
  function spawnPacketsFromState(state) {
    const pkts = state.packets || [];
    const sig = pkts.map((p) => (p.ts || '') + ':' + p.source_floor + ':' + p.target_floor).join('|');
    if (sig === T.lastPacketSig) return;
    T.lastPacketSig = sig;
    pkts.forEach((p, i) => setTimeout(() => spawnPacket(p), i * 220));
  }

  function spawnPacket(p) {
    const src = parseFloorNum(p.source_floor); let dst = parseFloorNum(p.target_floor);
    if (src == null) return;
    if (dst == null) {
      if (p.target_floor === 'penthouse' || p.target_floor === 'penthouse_kernel_review') dst = 55;
      else return;
    }
    const cySrc = slabCenterY(src);
    const cyDst = slabCenterY(dst);
    const color = COLOR_BY_LABEL[(p.color || 'green').toLowerCase()] || PACKET_COLORS[p.type] || '#9fc6ff';

    const circle = mk('circle', {
      cx: CENTER_X, cy: cySrc, r: 4.2,
      fill: color, stroke: '#ffffff', 'stroke-width': '0.6',
      filter: 'url(#qsbGlow)', opacity: '0.95',
    }, T.layerPackets);
    // V3: arc amplitude is deterministic — same packet draws the same
    // curve every time. NO random jitter masquerading as live activity.
    const seed = (p.ts || '') + '|' + (p.source_floor || '') + '|' + (p.target_floor || '');
    let h = 0;
    for (let i = 0; i < seed.length; i++) { h = ((h << 5) - h) + seed.charCodeAt(i); h |= 0; }
    const arcAmp = 30 + (Math.abs(h) % 23);
    T.activePackets.push({
      el: circle, xSrc: CENTER_X, xDst: CENTER_X, cySrc, cyDst,
      born: performance.now(),
      dur: 1700 + Math.abs(dst - src) * 38,
      arcAmp: arcAmp,
    });
  }

  // ── animation loop ─────────────────────────────────────────────────────
  function frame() {
    T.rafHandle = requestAnimationFrame(frame);
    if (T.paused) return;
    const now = performance.now() / 1000;

    // ── V3 LIVE_DATA_ONLY ─────────────────────────────────────────────
    // Capsules park unless a real lift_movements record is set on them.
    for (const cap of T.capsules) {
      const s = T.shafts[cap.shaftIdx];
      if (!s) continue;
      const yTop = TOWER_TOP_Y + ROOF_H + 8;
      const yBot = TOWER_BOT_Y - GROUND_H - 8;
      const range = yBot - yTop;
      let y;
      if (cap.live_dest_y != null && cap.live_start_y != null && cap.live_started_ms) {
        const dur = Math.max(400, cap.live_dur_ms || 1800);
        const t = Math.min(1, Math.max(0, (performance.now() - cap.live_started_ms) / dur));
        const ease = 0.5 - Math.cos(Math.PI * t) / 2;
        y = cap.live_start_y + (cap.live_dest_y - cap.live_start_y) * ease;
        if (t >= 1) {
          cap.live_start_y = cap.live_dest_y;
          cap.live_dest_y = null;
          cap.live_started_ms = 0;
          cap.parked_y = y;
        }
      } else {
        if (cap.parked_y == null) cap.parked_y = yTop + range * 0.5;
        y = cap.parked_y;
      }
      const x = shaftXAt(cap.shaftIdx, y) - 10;
      cap.rect.setAttribute('y', y - 7);
      cap.rect.setAttribute('x', x);
      cap.label.setAttribute('x', x + 10);
      cap.label.setAttribute('y', y + 3);
    }

    // Worker pulse — gated. Idle workers stay at default radius. Pulse
    // only fires when the V3 telemetry layer tags a worker as in_transit
    // OR the worker fired a recent event (within the last ~30 s).
    for (const id of Object.keys(T.workerNodes)) {
      const w = T.workerNodes[id];
      if (!w) continue;
      if (w.in_transit || w.recent_event) {
        const r = 3.4 + Math.sin(now * 2.5 + w.pulsePhase) * 0.8;
        w.dot.setAttribute('r', r.toFixed(2));
      } else {
        w.dot.setAttribute('r', '3.4');
      }
    }

    // Route line pulse
    for (let i = 0; i < T.routeLines.length; i++) {
      const r = T.routeLines[i];
      const alpha = (r.advisory ? 0.28 : 0.35) + 0.20 * Math.abs(Math.sin(now * 0.8 + i * 0.6));
      r.el.setAttribute('opacity', alpha.toFixed(3));
    }

    // Packets
    const tNow = performance.now();
    const remaining = [];
    for (const p of T.activePackets) {
      const t = (tNow - p.born) / p.dur;
      if (t >= 1) {
        if (p.el.parentNode) p.el.parentNode.removeChild(p.el);
        continue;
      }
      const ease = 0.5 - Math.cos(Math.PI * t) / 2;
      const y = p.cySrc + (p.cyDst - p.cySrc) * ease;
      const arc = Math.sin(t * Math.PI) * p.arcAmp;
      const x = p.xSrc + arc * ((p.cyDst - p.cySrc >= 0) ? 1 : -1);
      p.el.setAttribute('cx', x);
      p.el.setAttribute('cy', y);
      p.el.setAttribute('opacity', (0.55 + 0.45 * Math.sin(t * Math.PI)).toFixed(3));
      remaining.push(p);
    }
    T.activePackets = remaining;
    T.diag.packets_active = remaining.length;
  }

  // ── tooltip ────────────────────────────────────────────────────────────
  function showTipForFloor(n) {
    if (!T.hudTipEl) return;
    let title, sub;
    const nameMap = pickNameMap(T.state || {});
    const fallback = FALLBACK_NAMES[n];
    if (n === 54) { title = 'Roof — External Providers'; sub = 'LOCKED'; }
    else if (n === 55) { title = 'Penthouse — QSB Kernel'; sub = nameMap[55] ? ('active_local_only · ' + nameMap[55]) : 'active_local_only'; }
    else if (n === 0)  { title = 'Ground — Reception Lobby'; sub = 'plaza'; }
    else {
      title = nameMap[n] || fallback || ('Floor ' + n);
      sub = 'Floor ' + n + ' — click for details';
    }
    T.hudTipEl.innerHTML = '<div class="ht-title">' + esc(title) + '</div><div class="ht-sub">' + esc(sub) + '</div>';
    T.hudTipEl.classList.add('on');
  }
  function showTipForWorker(w) {
    if (!T.hudTipEl) return;
    const origin = w.origin || w.team || 'registry';
    const simTag = w.is_simulation ? '<span class="ht-sim">SIM</span> ' : '';
    const role = w.role || (w.is_simulation ? 'simulation_worker' : '');
    T.hudTipEl.innerHTML = (
      '<div class="ht-title">' + simTag + esc(w.name || w.id) + '</div>' +
      '<div class="ht-sub">' + esc(role + ' · home ' + (w.home_floor || '—') +
                                    ' · source ' + origin) + '</div>'
    );
    T.hudTipEl.classList.add('on');
  }
  function hideTip() { if (T.hudTipEl) T.hudTipEl.classList.remove('on'); }

  function pushDiag() { if (typeof T.onDiag === 'function') { try { T.onDiag(T.diag); } catch (e) {} } }

  // ── public API ─────────────────────────────────────────────────────────
  window.QSB_TOWER_2D_INIT = function (opts) {
    T.host = opts.hostEl;
    T.hudTipEl = opts.hudTipEl || null;
    T.onPick = opts.onPick || null;
    T.onDiag = opts.onDiag || null;
    try {
      build();
      // ensure rotate-on class initially
      if (T.rotateOn && T.host) T.host.classList.add('qsb-rotate-on');
      if (T.rafHandle) cancelAnimationFrame(T.rafHandle);
      T.rafHandle = requestAnimationFrame(frame);
    } catch (e) {
      T.diag.last_error = (e && e.message ? e.message : String(e)).slice(0, 200);
      pushDiag();
      throw e;
    }
    window.addEventListener('qsb:state', (e) => applyState(e.detail));
    if (window.QSB && window.QSB.state) applyState(window.QSB.state);
    return T;
  };
  window.QSB_TOWER_2D_PAUSE = function (paused) { T.paused = !!paused; };
  window.QSB_TOWER_2D_INFO = function () { return Object.assign({}, T.diag); };
  window.QSB_TOWER_2D_SET_ROTATE = function (on) {
    T.rotateOn = !!on;
    if (T.host) T.host.classList.toggle('qsb-rotate-on', T.rotateOn);
  };
  window.QSB_TOWER_2D_SET_SHOW_ALL_NAMES = function (on) {
    T.showAllNames = !!on;
    if (T.state) refreshLabels(T.state);
  };
  window.QSB_TOWER_2D_SET_HIGHLIGHT_GROUP = function (group) {
    if (group && !HIGHLIGHT_GROUPS[group]) group = null;
    T.highlightGroup = group;
    if (T.state) applyState(T.state);
  };
  window.QSB_TOWER_2D_FOCUS_FLOOR = function (n) {
    const rect = T.floorRects[n];
    if (!rect) return;
    // Brief outline pulse
    rect.classList.add('fl-focus-pulse');
    setTimeout(() => rect.classList.remove('fl-focus-pulse'), 1400);
  };
})();
