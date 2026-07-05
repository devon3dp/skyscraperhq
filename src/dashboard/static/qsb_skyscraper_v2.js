/*
 * QSB Skyscraper V2 — Living 3D Cockpit Overlay
 * Phase: QSB_OPENCLAW_PAPER_TRADE_WORKERS_3D_SKYSCRAPER_V2
 *
 * Read-only overlay that sits on top of qsb_tower_2d.js (SVG) and
 * qsb_scene.js (Babylon 3D scene). Reads /api/qsb_v2/penthouse_combined
 * and decorates the existing tower with:
 *
 *   * Floor identity badges for distinct floors (kernel / command /
 *     binance / oanda / sandbox / audit / risk)
 *   * Worker count chips per floor (from canonical workers registry)
 *   * Animated OpenClaw avatar that moves between supervised floors
 *   * Trade slot meter (current / max=20) in the top-right
 *   * PnL tape underneath the meter
 *
 * Never enables execution. Never sends mutating requests except the
 * V2 dashboard buttons in the panel module (which still hit
 * read-only / paper-only endpoints).
 */
(function () {
  'use strict';

  if (window.QSB_SKYSCRAPER_V2_INSTALLED) return;
  window.QSB_SKYSCRAPER_V2_INSTALLED = true;

  const TICK_MS_FAST = 800;
  const TICK_MS_SLOW = 6000;
  let lastPanel = null;
  let openclawIdx = 0;

  // Floors we want to make visually distinct in V2.
  const DISTINCT_FLOORS = {
    53: { id: 'F53', name: 'Tower Command',         tag: 'cmd',     glow: '#6ab8ff' },
    45: { id: 'F45', name: 'Recruitment',           tag: 'workers', glow: '#4dffb0' },
    42: { id: 'F42', name: 'Binance Trading',       tag: 'binance', glow: '#ffb86c' },
    41: { id: 'F41', name: 'OANDA Practice',        tag: 'oanda',   glow: '#5ce0ff' },
    43: { id: 'F43', name: 'Stock Exchange',        tag: 'stocks',  glow: '#eaf2ff' },
    38: { id: 'F38', name: 'Sandbox Ops',           tag: 'sandbox', glow: '#4dffb0' },
    37: { id: 'F37', name: 'Simulation Labs',       tag: 'sim',     glow: '#7fc8ff' },
    31: { id: 'F31', name: 'Audit / Ledger',        tag: 'audit',   glow: '#ffc940' },
    30: { id: 'F30', name: 'Permissions / Risk',    tag: 'risk',    glow: '#b08aff' },
    23: { id: 'F23', name: 'AirLLM Chamber',        tag: 'airllm',  glow: '#7fc8ff' },
  };
  // The Penthouse band sits above floor 53 in the SVG.
  const PENTHOUSE_TAG = 'penthouse';

  function $(sel) { return document.querySelector(sel); }

  function getTower() {
    return window.QSB_TOWER_2D || null;
  }

  // ── HUD container (top-right) ─────────────────────────────────────────
  function ensureHud() {
    let hud = $('#qsbV2Hud');
    if (hud) return hud;
    hud = document.createElement('div');
    hud.id = 'qsbV2Hud';
    hud.className = 'qsb-v2-hud';
    hud.innerHTML = (
      '<div class="qsb-v2-hud-row qsb-v2-hud-title">' +
        '<span class="dot dot-paper"></span>' +
        '<span>Paper / Testnet · execution_allowed=<b>false</b></span>' +
      '</div>' +
      '<div class="qsb-v2-hud-row" id="qsbV2HudSlots">slots —/—</div>' +
      '<div class="qsb-v2-hud-meter"><div id="qsbV2HudFill" class="fill"></div></div>' +
      '<div class="qsb-v2-hud-row" id="qsbV2HudPnL">PnL: —</div>' +
      '<div class="qsb-v2-hud-row" id="qsbV2HudOpenClaw">OpenClaw: —</div>' +
      '<div class="qsb-v2-hud-row" id="qsbV2HudWorkers">Workers: —</div>'
    );
    const stage = $('#stage') || document.body;
    stage.appendChild(hud);
    return hud;
  }

  function updateHud(panel) {
    const hud = ensureHud();
    if (!panel || !panel.ok) return;
    const pt = panel.paper_trading || {};
    const oc = panel.openclaw || {};
    const w  = panel.workers || {};
    const max = pt.max_open_trades || 20;
    const cur = pt.current_open_trade_count || 0;
    const pct = Math.min(100, (cur / Math.max(1, max)) * 100);
    $('#qsbV2HudSlots').textContent =
      'open trades: ' + cur + ' / ' + max + ' · remaining: ' + (pt.remaining_trade_slots || 0);
    $('#qsbV2HudFill').style.width = pct + '%';
    const pnl = (pt.total_current_pnl || 0).toFixed(2);
    const rpnl = (pt.total_realized_pnl || 0).toFixed(2);
    $('#qsbV2HudPnL').textContent =
      'PnL · open=' + pnl + ' · realized=' + rpnl + ' · lessons=' + (pt.lesson_count || 0);
    $('#qsbV2HudOpenClaw').textContent =
      'OpenClaw: ' + (oc.status || '—') +
      ' · tickets=' + (oc.diagnostic_ticket_count || 0) +
      ' · exec=' + (oc.openclaw_real_tool_execution_enabled ? 'TRUE' : 'false');
    $('#qsbV2HudWorkers').textContent =
      'Workers: ' + (w.total_canonical_workers || 0) +
      ' (active=' + (w.total_active_workers || 0) +
      ' · new=' + (w.total_newly_employed_workers || 0) + ')';
  }

  // ── Floor identity badges (right edge of SVG) ─────────────────────────
  function ensureFloorBadgeLayer() {
    const tower = getTower();
    if (!tower || !tower.svg) return null;
    let g = tower.svg.querySelector('#v2BadgeLayer');
    if (g) return g;
    g = document.createElementNS('http://www.w3.org/2000/svg', 'g');
    g.setAttribute('id', 'v2BadgeLayer');
    tower.svg.appendChild(g);
    return g;
  }

  function paintFloorBadges() {
    const tower = getTower();
    if (!tower || !tower.svg) return;
    const layer = ensureFloorBadgeLayer();
    if (!layer) return;

    // Wipe and redraw each tick — DOM count stays small.
    layer.innerHTML = '';

    Object.keys(DISTINCT_FLOORS).forEach(function (k) {
      const n = Number(k);
      const r = tower.floorRects && tower.floorRects[n];
      if (!r) return;
      const x = Number(r.getAttribute('x'));
      const y = Number(r.getAttribute('y'));
      const w = Number(r.getAttribute('width'));
      const h = Number(r.getAttribute('height'));
      const meta = DISTINCT_FLOORS[k];

      // Glow rect overlay
      const glow = document.createElementNS('http://www.w3.org/2000/svg', 'rect');
      glow.setAttribute('x', x);
      glow.setAttribute('y', y);
      glow.setAttribute('width', w);
      glow.setAttribute('height', h);
      glow.setAttribute('fill', 'none');
      glow.setAttribute('stroke', meta.glow);
      glow.setAttribute('stroke-width', '1.4');
      glow.setAttribute('stroke-opacity', '0.85');
      glow.setAttribute('rx', '3');
      glow.setAttribute('class', 'qsb-v2-floor-glow qsb-v2-glow-' + meta.tag);
      layer.appendChild(glow);

      // Badge in right margin
      const badge = document.createElementNS('http://www.w3.org/2000/svg', 'g');
      const bx = x + w + 12;
      const by = y + h / 2;
      const text = document.createElementNS('http://www.w3.org/2000/svg', 'text');
      text.setAttribute('x', bx);
      text.setAttribute('y', by);
      text.setAttribute('text-anchor', 'start');
      text.setAttribute('alignment-baseline', 'middle');
      text.setAttribute('class', 'qsb-v2-badge qsb-v2-badge-' + meta.tag);
      text.setAttribute('fill', meta.glow);
      text.textContent = meta.id + ' · ' + meta.name;
      badge.appendChild(text);
      layer.appendChild(badge);
    });

    // Penthouse identity badge (above floor 53)
    const pent = tower.floorRects && tower.floorRects[54];
    if (pent) {
      const px = Number(pent.getAttribute('x'));
      const py = Number(pent.getAttribute('y'));
      const pw = Number(pent.getAttribute('width'));
      const ph = Number(pent.getAttribute('height'));
      const glow = document.createElementNS('http://www.w3.org/2000/svg', 'rect');
      glow.setAttribute('x', px);
      glow.setAttribute('y', py);
      glow.setAttribute('width', pw);
      glow.setAttribute('height', ph);
      glow.setAttribute('fill', 'none');
      glow.setAttribute('stroke', '#ffd24c');
      glow.setAttribute('stroke-width', '1.6');
      glow.setAttribute('stroke-opacity', '0.9');
      glow.setAttribute('rx', '4');
      glow.setAttribute('class', 'qsb-v2-floor-glow qsb-v2-glow-' + PENTHOUSE_TAG);
      layer.appendChild(glow);
      const badge = document.createElementNS('http://www.w3.org/2000/svg', 'text');
      badge.setAttribute('x', px + pw + 12);
      badge.setAttribute('y', py + ph / 2);
      badge.setAttribute('text-anchor', 'start');
      badge.setAttribute('alignment-baseline', 'middle');
      badge.setAttribute('class', 'qsb-v2-badge qsb-v2-badge-' + PENTHOUSE_TAG);
      badge.setAttribute('fill', '#ffd24c');
      badge.textContent = 'PEN · EQSB Kernel';
      layer.appendChild(badge);
    }
  }

  // ── OpenClaw avatar — animates across supervised floors ───────────────
  function ensureOpenClawAvatar() {
    const tower = getTower();
    if (!tower || !tower.svg) return null;
    let g = tower.svg.querySelector('#v2OpenclawAvatar');
    if (g) return g;
    g = document.createElementNS('http://www.w3.org/2000/svg', 'g');
    g.setAttribute('id', 'v2OpenclawAvatar');
    tower.svg.appendChild(g);
    g.innerHTML = (
      '<circle r="9" fill="#b08aff" fill-opacity="0.85" stroke="#fff" stroke-width="1.2">' +
        '<animate attributeName="r" values="9;12;9" dur="1.4s" repeatCount="indefinite"/>' +
      '</circle>' +
      '<circle r="18" fill="none" stroke="#b08aff" stroke-opacity="0.5" stroke-width="1">' +
        '<animate attributeName="r" values="14;26;14" dur="2.4s" repeatCount="indefinite"/>' +
        '<animate attributeName="stroke-opacity" values="0.6;0.05;0.6" dur="2.4s" repeatCount="indefinite"/>' +
      '</circle>' +
      '<text y="4" text-anchor="middle" fill="#fff" font-size="10" ' +
            'font-family="JetBrains Mono, monospace">OC</text>'
    );
    return g;
  }

  function moveOpenClaw(panel) {
    const tower = getTower();
    if (!tower || !tower.svg) return;
    const supervisedFloors = (panel && panel.openclaw && panel.openclaw.supervised_floors) || [
      'floor_30', 'floor_31', 'floor_37', 'floor_38',
      'floor_41', 'floor_42', 'floor_43', 'floor_45', 'floor_53',
    ];
    // Map supervised floor strings -> numeric floor index.
    const idx = (openclawIdx++ % supervisedFloors.length);
    const floorStr = supervisedFloors[idx] || 'floor_53';
    const m = /floor[_-]?0*(\d+)/.exec(floorStr);
    const n = m ? Number(m[1]) : 53;
    const r = tower.floorRects && tower.floorRects[n];
    if (!r) return;
    const x = Number(r.getAttribute('x'));
    const y = Number(r.getAttribute('y'));
    const w = Number(r.getAttribute('width'));
    const h = Number(r.getAttribute('height'));
    const tx = x + w * 0.5;
    const ty = y + h / 2;

    const g = ensureOpenClawAvatar();
    if (!g) return;
    g.setAttribute('transform', 'translate(' + tx + ',' + ty + ')');
    g.setAttribute('class', 'qsb-v2-openclaw-avatar');
  }

  // ── Worker count chips per floor ──────────────────────────────────────
  function paintWorkerChips(panel) {
    const tower = getTower();
    if (!tower || !tower.svg) return;
    let layer = tower.svg.querySelector('#v2WorkerChips');
    if (!layer) {
      layer = document.createElementNS('http://www.w3.org/2000/svg', 'g');
      layer.setAttribute('id', 'v2WorkerChips');
      tower.svg.appendChild(layer);
    }
    layer.innerHTML = '';

    const byFloor = (panel && panel.workers && panel.workers.by_home_floor_counts) || {};
    Object.keys(byFloor).forEach(function (floorKey) {
      const m = /floor[_-]?0*(\d+)/.exec(floorKey);
      if (!m) return;
      const n = Number(m[1]);
      const r = tower.floorRects && tower.floorRects[n];
      if (!r) return;
      const count = byFloor[floorKey];
      const x = Number(r.getAttribute('x'));
      const y = Number(r.getAttribute('y'));
      const h = Number(r.getAttribute('height'));
      const chip = document.createElementNS('http://www.w3.org/2000/svg', 'g');
      chip.setAttribute('class', 'qsb-v2-worker-chip');
      chip.setAttribute('transform', 'translate(' + (x - 18) + ',' + (y + h / 2) + ')');
      chip.innerHTML = (
        '<rect x="-14" y="-7" width="28" height="14" rx="3" fill="rgba(20,30,45,0.75)" ' +
              'stroke="#4dffb0" stroke-opacity="0.6"/>' +
        '<text x="0" y="3" text-anchor="middle" fill="#cfe9d6" ' +
              'font-size="9" font-family="JetBrains Mono, monospace">' + count + 'w</text>'
      );
      layer.appendChild(chip);
    });
  }

  // ── Polling loop ──────────────────────────────────────────────────────
  async function fetchPanel() {
    try {
      const r = await fetch('/api/qsb_v2/penthouse_combined?t=' + Date.now(),
                             { cache: 'no-store' });
      return await r.json();
    } catch (_) {
      return null;
    }
  }

  // Every public call is wrapped — V2 overlay must never break the
  // main cockpit, even if a registry endpoint or SVG layer is missing.
  function safe(name, fn) {
    return function () {
      try { return fn.apply(null, arguments); }
      catch (e) {
        if (window && window.console && console.warn) {
          console.warn('[qsb_skyscraper_v2] ' + name + ' failed:', e && e.message);
        }
        return null;
      }
    };
  }

  const safeUpdateHud         = safe('updateHud',         updateHud);
  const safePaintFloorBadges  = safe('paintFloorBadges',  paintFloorBadges);
  const safePaintWorkerChips  = safe('paintWorkerChips',  paintWorkerChips);
  const safeMoveOpenClaw      = safe('moveOpenClaw',      moveOpenClaw);

  async function tick() {
    let panel = null;
    try {
      panel = await fetchPanel();
    } catch (_) {}
    if (!panel) return;
    lastPanel = panel;
    safeUpdateHud(panel);
    safePaintFloorBadges();
    safePaintWorkerChips(panel);
    safeMoveOpenClaw(panel);
  }

  function start() {
    // Initial tick fires fast, then slow heartbeat — both wrapped.
    setTimeout(function () { try { tick(); } catch (_) {} }, 1200);
    setInterval(function () { try { tick(); } catch (_) {} }, TICK_MS_SLOW);
    // Move OpenClaw avatar more often than full refresh.
    setInterval(function () { safeMoveOpenClaw(lastPanel); }, TICK_MS_FAST);
  }

  function safeStart() { try { start(); } catch (e) {
    if (window && window.console) console.warn('[qsb_skyscraper_v2] start failed:', e && e.message);
  } }

  if (document.readyState === 'loading') {
    document.addEventListener('DOMContentLoaded', safeStart);
  } else {
    safeStart();
  }

  // Expose a tiny API for the V2 right-rail panel.
  window.QSB_V2 = {
    refresh: tick,
    lastPanel: function () { return lastPanel; },
  };
})();
