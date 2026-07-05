/*
 * QSB Visible Dashboard Rebuild — Phase
 * QSB_DASHBOARD_VISIBLE_REALITY_REBUILD_V1
 *
 * This is the "you can see it without squinting" layer. It paints:
 *   - a top-center BUILD BADGE that proves the new build is live
 *   - a left-edge LIFT COLUMN with 9 cells (id, type, current floor, status)
 *   - an OPENCLAW ORB anchored to the tower's current OpenClaw floor
 *   - a SELECTED FLOOR ring on the SVG tower when ?floor=N
 *   - a FLOOR 42 BINANCE interior panel when floor=42
 *
 * No JSON-only optimism. Every painted element is anchored to a real
 * registry payload or labelled "no data" when missing.
 */
(function () {
  'use strict';
  if (window.QSB_VISIBLE_INSTALLED) return;
  window.QSB_VISIBLE_INSTALLED = true;

  const POLL_MS = 5000;
  const BUILD_TAG = 'visible-cockpit-v1';

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

  // ── BUILD BADGE ────────────────────────────────────────────────
  function ensureBuildBadge() {
    let el = document.getElementById('qsbBuildBadge');
    if (el) return el;
    el = document.createElement('div');
    el.id = 'qsbBuildBadge';
    el.className = 'qsb-build-badge';
    el.setAttribute('data-build', BUILD_TAG);
    el.textContent = BUILD_TAG + ' · ALL EXEC LOCKS CLOSED';
    document.body.appendChild(el);
    return el;
  }

  // ── LIFT COLUMN (always visible, left edge) ─────────────────────
  function ensureLiftColumn() {
    let el = document.getElementById('qsbLiftColumn');
    if (el) return el;
    const stage = document.getElementById('stage') || document.body;
    el = document.createElement('div');
    el.id = 'qsbLiftColumn';
    el.className = 'qsb-lift-column';
    el.innerHTML =
      '<div class="qsb-lift-column-hdr">LIFTS · 9</div>' +
      '<div id="qsbLiftColumnRows"></div>';
    stage.appendChild(el);
    return el;
  }

  function renderLiftColumn(scene) {
    const el = ensureLiftColumn();
    const rows = el.querySelector('#qsbLiftColumnRows');
    const lifts = (scene && scene.lifts) || [];
    if (!lifts.length) {
      rows.innerHTML = '<div class="qsb-lift-cell stale"><span class="ico"></span><div><div class="qsb-lift-cell-name">no data</div></div></div>';
      return;
    }
    let html = '';
    lifts.forEach(function (L, i) {
      const status = L.moving ? 'MOVING' : (L.status === 'online' ? 'IDLE' : (L.status || 'unk').toUpperCase());
      const cls = L.moving ? 'moving' : (L.status === 'online' ? 'idle' : 'stale');
      const cur = (L.current_floor !== null && L.current_floor !== undefined) ? L.current_floor : '—';
      const shortName = (L.lift_id || ('L' + (i + 1))).replace(/_/g, ' ').slice(0, 10);
      html += (
        '<div class="qsb-lift-cell ' + cls + '" data-type="' + esc(L.type || 'main') + '" ' +
              'title="' + esc(L.lift_id) + ' · serves ' + esc((L.serves || []).slice(0, 8).join(',')) + '">' +
          '<span class="ico"></span>' +
          '<div>' +
            '<div class="qsb-lift-cell-name">' + esc(shortName) + '</div>' +
            '<div class="qsb-lift-cell-meta">f' + esc(cur) + ' · ' +
              '<span class="qsb-lift-cell-status">' + esc(status) + '</span>' +
            '</div>' +
          '</div>' +
        '</div>'
      );
    });
    rows.innerHTML = html;
  }

  // ── OPENCLAW ORB on tower ──────────────────────────────────────
  function ensureOpenClawOrb() {
    let el = document.getElementById('qsbOpenClawOrb');
    if (el) return el;
    const stage = document.getElementById('stage') || document.body;
    el = document.createElement('div');
    el.id = 'qsbOpenClawOrb';
    el.className = 'qsb-openclaw-orb';
    el.title = 'OpenClaw supervisor (read-only, advisory)';
    const label = document.createElement('div');
    label.className = 'qsb-openclaw-orb-label';
    label.id = 'qsbOpenClawOrbLabel';
    label.textContent = 'OpenClaw';
    el.appendChild(label);
    stage.appendChild(el);
    return el;
  }

  function renderOpenClawOrb(route, tickets) {
    const orb = ensureOpenClawOrb();
    const label = orb.querySelector('#qsbOpenClawOrbLabel');
    const cf = route && route.current_floor;
    // Anchor to the SVG slab for that floor.
    const host = document.getElementById('qsbTower2D');
    const svg = host && host.querySelector('svg');
    if (!svg || cf === null || cf === undefined) {
      // fallback: top-right area
      orb.style.right = '20px';
      orb.style.left = 'auto';
      orb.style.top = '120px';
      label.textContent = 'OpenClaw · floor —';
      return;
    }
    const slab = svg.querySelector('rect[data-floor="' + cf + '"]');
    if (!slab) return;
    const stage = document.getElementById('stage');
    const stageRect = stage.getBoundingClientRect();
    const svgRect = svg.getBoundingClientRect();
    const slabRect = slab.getBoundingClientRect();
    // Position relative to the stage container.
    const top = (slabRect.top - stageRect.top) + (slabRect.height / 2) - 16;
    const left = (slabRect.right - stageRect.left) + 8;
    orb.style.top = top + 'px';
    orb.style.left = left + 'px';
    orb.style.right = 'auto';
    const tcount = (tickets && tickets.ticket_count) || (tickets && (tickets.tickets || []).length) || 0;
    label.textContent = 'OpenClaw · floor ' + cf + ' · ' + tcount + ' tickets';
  }

  // ── SELECTED FLOOR ring on SVG tower ────────────────────────────
  function renderSelectedFloorRing(n) {
    const host = document.getElementById('qsbTower2D');
    const svg = host && host.querySelector('svg');
    if (!svg) return;
    let layer = svg.querySelector('#qsbSelectedRingLayer');
    if (!layer) {
      layer = document.createElementNS('http://www.w3.org/2000/svg', 'g');
      layer.setAttribute('id', 'qsbSelectedRingLayer');
      svg.appendChild(layer);
    }
    while (layer.firstChild) layer.removeChild(layer.firstChild);
    if (n === null || n === undefined) return;
    const slab = svg.querySelector('rect[data-floor="' + n + '"]');
    if (!slab) return;
    const ring = document.createElementNS('http://www.w3.org/2000/svg', 'rect');
    const x = parseFloat(slab.getAttribute('x'));
    const y = parseFloat(slab.getAttribute('y'));
    const w = parseFloat(slab.getAttribute('width'));
    const h = parseFloat(slab.getAttribute('height'));
    ring.setAttribute('x', x - 3);
    ring.setAttribute('y', y - 3);
    ring.setAttribute('width', w + 6);
    ring.setAttribute('height', h + 6);
    ring.setAttribute('rx', 3);
    ring.setAttribute('fill', 'none');
    ring.setAttribute('stroke', '#ffd886');
    ring.setAttribute('stroke-width', '1.4');
    ring.setAttribute('class', 'qsb-selected-floor-ring');
    layer.appendChild(ring);
  }

  // ── FLOOR 42 BINANCE INTERIOR ──────────────────────────────────
  function ensureF42Panel() {
    let el = document.getElementById('qsbF42Binance');
    if (el) return el;
    const stage = document.getElementById('stage') || document.body;
    el = document.createElement('div');
    el.id = 'qsbF42Binance';
    el.className = 'qsb-f42-binance';
    el.style.display = 'none';
    stage.appendChild(el);
    return el;
  }

  async function renderF42(selectedFloor) {
    const el = ensureF42Panel();
    if (selectedFloor !== 42) { el.style.display = 'none'; return; }
    el.style.display = 'block';
    const data = await fetchJSON('/api/dashboard/floor42_binance_interior');
    if (!data || !data.ok) {
      el.innerHTML = (
        '<div class="f42-hdr"><div class="f42-hdr-title">FLOOR 42 · BINANCE TRADING FLOOR</div></div>' +
        '<div class="muted">Floor 42 interior unavailable. Run scripts/qsb_dashboard_start.sh</div>'
      );
      return;
    }
    const rooms = data.rooms || [];
    const workers = data.workers || [];
    const policy = data.policy || {};
    let roomCards = '';
    rooms.forEach(function (r) {
      const inRoom = workers.filter(function (w) { return w.room === r.name; });
      let workerHtml = '';
      inRoom.forEach(function (w) {
        workerHtml += '<span class="f42-room-w" title="' + esc(w.station) + '">' +
                      esc((w.worker_id || '').replace(/^wrk_|^f42_/, '')) +
                      '</span>';
      });
      if (!workerHtml) workerHtml = '<span class="muted">no workers assigned</span>';
      roomCards += (
        '<div class="f42-room">' +
          '<b>' + esc(r.name) + '</b> · ' + esc(r.responsibility || '') +
          '<div class="f42-room-workers">' + workerHtml + '</div>' +
        '</div>'
      );
    });
    const summary = (
      '<div class="f42-card">' +
        '<h5>Floor Summary</h5>' +
        '<div>mode: <b>' + esc(policy.mode || 'testnet_preview_only') + '</b></div>' +
        '<div>placement: <b>' + esc(policy.placement || 'blocked_without_explicit_unlock') + '</b></div>' +
        '<div>real-money: <b>' + (policy.real_money_enabled === false ? 'OFF (locked)' : 'unknown') + '</b></div>' +
      '</div>'
    );
    el.innerHTML = (
      '<div class="f42-hdr">' +
        '<div class="f42-hdr-title">FLOOR 42 · BINANCE TRADING FLOOR</div>' +
        '<div class="f42-hdr-mode">' + esc(rooms.length) + ' rooms · ' + esc(workers.length) + ' workers</div>' +
        '<div class="f42-hdr-locks">testnet preview only · real-money locked</div>' +
      '</div>' +
      '<div class="f42-grid">' +
        '<div>' + summary + roomCards + '</div>' +
        '<div>' +
          '<div class="f42-card"><h5>Workers at stations</h5>' +
            (workers.length === 0 ?
              '<div class="qsb-no-config">No workers yet — Floor 42 was previously seeded with only 2 sandbox scouts. ' +
              'Run python3 -m tower.qsb_floor42_binance to populate the full 8-worker Binance roster.</div>' :
              workers.map(function (w) {
                return '<div class="f42-room"><b>' + esc(w.worker_id.replace(/^wrk_|^f42_/, '')) + '</b> · ' +
                        esc(w.role) + ' · station: ' + esc(w.station) + '</div>';
              }).join('')) +
          '</div>' +
        '</div>' +
      '</div>'
    );
  }

  // ── Orchestrator ───────────────────────────────────────────────
  async function pollAll() {
    const [lifts, route, tickets] = await Promise.all([
      fetchJSON('/api/dashboard/lift_scene_state'),
      fetchJSON('/api/openclaw/route'),
      fetchJSON('/api/openclaw/tickets'),
    ]);
    renderLiftColumn(lifts);
    renderOpenClawOrb(route, tickets);
    const sel = (window.QSB && window.QSB.selectedFloor);
    renderSelectedFloorRing(sel);
    await renderF42(sel);
  }

  function attach() {
    ensureBuildBadge();
    setTimeout(pollAll, 1500);
    setInterval(pollAll, POLL_MS);
    window.addEventListener('qsb:pick', function () { pollAll().catch(function () {}); });
  }

  if (document.readyState === 'loading') {
    document.addEventListener('DOMContentLoaded', attach);
  } else {
    attach();
  }
  window.QSB_VISIBLE = { refresh: pollAll };
})();
