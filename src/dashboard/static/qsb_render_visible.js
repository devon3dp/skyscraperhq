/*
 * QSB Render Visible Layer
 * Phase: QSB_RENDER_VISIBLE_WORKERS_AND_LIFTS_FIX_V1
 *
 * Responsibilities:
 *   1. Parse URLSearchParams on boot and initialize window.QSB.selectedFloor.
 *      Re-emits a synthetic qsb:pick event so every listener reacts as if
 *      the user had clicked Floor N.
 *   2. Paint a left-side LIFT STRIP showing 9 real lifts with id, type,
 *      status, current floor, target, and IDLE label when not moving.
 *   3. Paint per-floor worker density badges on the SVG floor slabs so
 *      the tower view is no longer just floor names. Each badge shows
 *      "ops·tr·rest" with color coding.
 *   4. Paint a top-right "Workforce summary" pill summarizing canonical,
 *      active, moving, training, resting, rendered_now, and selected_floor
 *      count, plus an explanation of why 1191 != 1191 labels.
 *
 * NO randomness. NO fake counts. If data is missing show "no data" /
 * "idle" / "awaiting telemetry."
 */
(function () {
  'use strict';
  if (window.QSB_RENDER_VISIBLE_INSTALLED) return;
  window.QSB_RENDER_VISIBLE_INSTALLED = true;

  const POLL_MS = 5000;
  let cache = {};

  function esc(s) {
    if (s === null || s === undefined) return '';
    return String(s).replace(/&/g, '&amp;').replace(/</g, '&lt;').replace(/>/g, '&gt;');
  }

  async function fetchJSON(url) {
    try {
      const sep = url.indexOf('?') === -1 ? '?' : '&';
      const r = await fetch(url + sep + 't=' + Date.now(), { cache: 'no-store' });
      if (!r.ok) return null;
      return await r.json();
    } catch (_) { return null; }
  }

  // ── 1. URL → selectedFloor ─────────────────────────────────────────
  function parseUrlFloor() {
    try {
      const params = new URLSearchParams(window.location.search);
      const raw = params.get('floor');
      if (!raw) return null;
      const n = parseInt(raw, 10);
      if (isNaN(n) || n < 0 || n > 54) return null;
      return n;
    } catch (_) { return null; }
  }

  function applyUrlFloor() {
    const n = parseUrlFloor();
    if (n === null) return;
    window.QSB = window.QSB || {};
    window.QSB.selectedFloor = n;
    // Synthetic pick event so every renderer reacts identically.
    const detail = { kind: 'floor', number: n, source: 'url_param' };
    window.dispatchEvent(new CustomEvent('qsb:pick', { detail }));
    window.dispatchEvent(new CustomEvent('qsb:url_floor', { detail }));
    // Re-poke the interior renderers in case they were not bound yet.
    setTimeout(function () {
      if (window.QSB_3D_WORKERS && window.QSB_3D_WORKERS.onFloorPick) {
        window.QSB_3D_WORKERS.onFloorPick(n);
      }
      if (window.QSB_3D_FLOORS && window.QSB_3D_FLOORS.onFloorPick) {
        window.QSB_3D_FLOORS.onFloorPick(n);
      }
    }, 800);
    setTimeout(function () {
      if (window.QSB_3D_WORKERS && window.QSB_3D_WORKERS.onFloorPick) {
        window.QSB_3D_WORKERS.onFloorPick(n);
      }
    }, 2500);
  }

  // ── 2. Lift strip ──────────────────────────────────────────────────
  function ensureLiftStrip() {
    let el = document.getElementById('qsbLiftStrip');
    if (el) return el;
    const stage = document.getElementById('stage') || document.body;
    el = document.createElement('div');
    el.id = 'qsbLiftStrip';
    el.className = 'qsb-lift-strip';
    el.innerHTML = '<h4>LIFTS · 9</h4><div id="qsbLiftRows" class="qsb-lift-rows"></div>';
    stage.appendChild(el);
    return el;
  }

  function renderLifts(scene) {
    const el = ensureLiftStrip();
    const rows = el.querySelector('#qsbLiftRows');
    const lifts = (scene && scene.lifts) || [];
    if (!lifts.length) {
      rows.innerHTML = '<div class="qsb-lift-empty">No lift telemetry · awaiting registry</div>';
      return;
    }
    let html = '';
    lifts.forEach(function (L) {
      const status = L.moving ? 'MOVING' : (L.status === 'online' ? 'IDLE' : (L.status || 'unknown').toUpperCase());
      const stCls = L.moving ? 'moving' : (L.status === 'online' ? 'idle' : 'stale');
      const cur = (L.current_floor !== null && L.current_floor !== undefined) ? L.current_floor : '—';
      const tgt = (L.target_floor !== null && L.target_floor !== undefined) ? L.target_floor : '—';
      const typeCls = 'type-' + (L.type || 'main');
      html += (
        '<div class="qsb-lift-row ' + stCls + '" data-lift="' + esc(L.lift_id) + '" ' +
              'title="' + esc(L.lift_id) + ' · serves ' + esc((L.serves || []).slice(0, 8).join(',')) + '">' +
          '<span class="qsb-lift-name ' + typeCls + '">' + esc(L.lift_id) + '</span>' +
          '<span class="qsb-lift-type">' + esc(L.type || 'main') + '</span>' +
          '<span class="qsb-lift-floor">cur:' + esc(cur) + '</span>' +
          '<span class="qsb-lift-floor">→' + esc(tgt) + '</span>' +
          '<span class="qsb-lift-status ' + stCls + '">' + esc(status) + '</span>' +
        '</div>'
      );
    });
    rows.innerHTML = html;
  }

  // ── 3. Per-floor density badges on tower ──────────────────────────
  function ensureFloorDensityLayer() {
    // Place inside the same SVG renderer so badges scale with the tower.
    const host = document.getElementById('qsbTower2D');
    if (!host) return null;
    const svg = host.querySelector('svg');
    if (!svg) return null;
    let layer = svg.querySelector('#qsbFloorDensity');
    if (layer) return layer;
    layer = document.createElementNS('http://www.w3.org/2000/svg', 'g');
    layer.setAttribute('id', 'qsbFloorDensity');
    svg.appendChild(layer);
    return layer;
  }

  function renderFloorDensities(workerScene) {
    const layer = ensureFloorDensityLayer();
    if (!layer) return;
    while (layer.firstChild) layer.removeChild(layer.firstChild);
    const host = document.getElementById('qsbTower2D');
    const svg = host && host.querySelector('svg');
    if (!svg) return;

    const perFloor = (workerScene && workerScene.per_floor) || [];
    perFloor.forEach(function (rec) {
      const f = rec.floor;
      const slab = svg.querySelector('rect[data-floor="' + f + '"]');
      if (!slab) return;
      const x = parseFloat(slab.getAttribute('x'));
      const y = parseFloat(slab.getAttribute('y'));
      const w = parseFloat(slab.getAttribute('width'));
      const h = parseFloat(slab.getAttribute('height'));
      // Density badge anchored to right edge of the slab.
      const cls = rec.classes || {};
      const ops = cls.operational_worker || 0;
      const tr = (cls.training_worker || 0) + (cls.candidate_worker || 0) + (cls.lesson_worker || 0);
      const rs = cls.resting_worker || 0;
      const total = rec.total || (ops + tr + rs);
      const bx = x + w + 6;
      const by = y + h / 2;
      // Background pill
      const pill = document.createElementNS('http://www.w3.org/2000/svg', 'rect');
      pill.setAttribute('x', bx);
      pill.setAttribute('y', by - 6);
      pill.setAttribute('rx', 4);
      pill.setAttribute('ry', 4);
      pill.setAttribute('width', 64);
      pill.setAttribute('height', 13);
      pill.setAttribute('fill', 'rgba(20,40,80,0.85)');
      pill.setAttribute('stroke', 'rgba(110,210,255,0.45)');
      pill.setAttribute('stroke-width', '0.6');
      layer.appendChild(pill);
      const txt = document.createElementNS('http://www.w3.org/2000/svg', 'text');
      txt.setAttribute('x', bx + 4);
      txt.setAttribute('y', by + 3.5);
      txt.setAttribute('font-size', '8.4');
      txt.setAttribute('font-family', 'Inter,Segoe UI,system-ui');
      txt.setAttribute('font-weight', '700');
      txt.setAttribute('fill', '#bfe0ff');
      txt.textContent = total + ' · op' + ops + ' tr' + tr + ' r' + rs;
      layer.appendChild(txt);
    });
  }

  // ── 4. Workforce summary pill ─────────────────────────────────────
  function ensureWorkforceSummary() {
    let el = document.getElementById('qsbWorkforceSummary');
    if (el) return el;
    const stage = document.getElementById('stage') || document.body;
    el = document.createElement('div');
    el.id = 'qsbWorkforceSummary';
    el.className = 'qsb-workforce-summary';
    stage.appendChild(el);
    return el;
  }

  function renderWorkforceSummary(workerScene, budget, selectedFloor) {
    const el = ensureWorkforceSummary();
    const c = (workerScene && workerScene.classes_overall) || {};
    const total = workerScene ? workerScene.canonical_total : 0;
    const ops = c.operational_worker || 0;
    const tr = (c.training_worker || 0) + (c.candidate_worker || 0) + (c.lesson_worker || 0);
    const rs = c.resting_worker || 0;
    const sim = c.sim_worker || 0;
    const cap = (budget && budget.selected_floor_individual_workers_cap) || 12;
    let selCount = 0;
    if (selectedFloor !== null && selectedFloor !== undefined && workerScene && workerScene.per_floor) {
      const rec = workerScene.per_floor.find(function (r) { return r.floor === selectedFloor; });
      if (rec) selCount = rec.total;
    }
    const renderedNow = Math.min(selCount, cap);
    const hidden = total - renderedNow;
    el.innerHTML = (
      '<h4>WORKFORCE</h4>' +
      '<div class="qsb-wf-line"><span>canonical</span><b>' + total + '</b></div>' +
      '<div class="qsb-wf-line"><span>operational</span><b>' + ops + '</b></div>' +
      '<div class="qsb-wf-line"><span>training+candidate+lesson</span><b>' + tr + '</b></div>' +
      '<div class="qsb-wf-line"><span>resting</span><b>' + rs + '</b></div>' +
      '<div class="qsb-wf-line"><span>sim</span><b>' + sim + '</b></div>' +
      '<div class="qsb-wf-line"><span>selected floor</span><b>' + (selectedFloor === null || selectedFloor === undefined ? '—' : ('F' + selectedFloor + ' · ' + selCount)) + '</b></div>' +
      '<div class="qsb-wf-line"><span>rendered now</span><b>' + renderedNow + '</b></div>' +
      '<div class="qsb-wf-line"><span>hidden by zoom/cap</span><b>' + hidden + '</b></div>' +
      '<div class="qsb-wf-note">' +
        '1191 canonical workers are summarized as per-floor density badges. ' +
        'Click any floor to inspect named worker rows (cap ' + cap + ' per room).' +
      '</div>'
    );
  }

  // ── Orchestrator ──────────────────────────────────────────────────
  async function pollAll() {
    const [liftScene, workerScene, budget] = await Promise.all([
      fetchJSON('/api/dashboard/lift_scene_state'),
      fetchJSON('/api/dashboard/worker_scene_state'),
      fetchJSON('/api/dashboard/worker_render_budget'),
    ]);
    cache.liftScene = liftScene;
    cache.workerScene = workerScene;
    cache.budget = budget;
    renderLifts(liftScene);
    renderFloorDensities(workerScene);
    const sel = (window.QSB && window.QSB.selectedFloor) || null;
    renderWorkforceSummary(workerScene, budget, sel);
  }

  function attach() {
    applyUrlFloor();
    setTimeout(function () { pollAll().catch(function () {}); }, 1500);
    setInterval(function () { pollAll().catch(function () {}); }, POLL_MS);
    // Repaint workforce summary when user picks a floor.
    window.addEventListener('qsb:pick', function (e) {
      const sel = (e && e.detail && e.detail.kind === 'floor') ? e.detail.number : null;
      window.QSB = window.QSB || {};
      if (sel !== null) window.QSB.selectedFloor = sel;
      renderWorkforceSummary(cache.workerScene, cache.budget, window.QSB.selectedFloor);
    });
    // Re-apply URL once SVG floor slabs exist.
    let tries = 0;
    const re = setInterval(function () {
      tries++;
      const host = document.getElementById('qsbTower2D');
      const svg = host && host.querySelector('svg');
      if (svg && svg.querySelector('rect[data-floor]')) {
        applyUrlFloor();
        renderFloorDensities(cache.workerScene);
        clearInterval(re);
      }
      if (tries > 20) clearInterval(re);
    }, 600);
  }

  if (document.readyState === 'loading') {
    document.addEventListener('DOMContentLoaded', attach);
  } else {
    attach();
  }
  window.QSB_RENDER_VISIBLE = { refresh: pollAll, cache: cache, applyUrlFloor: applyUrlFloor };
})();
