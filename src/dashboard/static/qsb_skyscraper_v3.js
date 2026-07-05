/*
 * QSB Skyscraper V3 — Data-Driven Cockpit Layer
 * Phase: QSB_DASHBOARD_DATA_DRIVEN_SKYSCRAPER_REBUILD_V2
 *
 * Hard contract:
 *   * DASHBOARD_VISUAL_MODE = "LIVE_DATA_ONLY"
 *   * NO_RANDOM_LIVE_GRAPHICS
 *   * Reads /api/dashboard/live_telemetry and applies real-data hints
 *     onto the existing 2D SVG (qsb_tower_2d.js) and 3D Babylon scene
 *     (qsb_scene.js). It NEVER invents workers, packets, lifts, or
 *     OpenClaw movement.
 *
 * What this layer does:
 *   * Sets in_transit / recent_event flags on existing worker nodes
 *     (in both renderers) so pulse animation fires only for workers
 *     with a real movement / recent event.
 *   * Tags lift capsules with live_start_y / live_dest_y / live_started_ms
 *     when telemetry reports a lift_movement; capsules stay parked
 *     otherwise.
 *   * Renders a right-rail "Live Telemetry" panel.
 *   * Renders a bottom-ticker overlay using the real event_ticker.
 *   * Surfaces per-floor "no live data" badges for floors with zero
 *     real activity.
 *
 * If the telemetry endpoint is unreachable, this layer degrades to
 * an inert no-op — the rest of the cockpit must keep working.
 */
(function () {
  'use strict';

  if (window.QSB_SKYSCRAPER_V3_INSTALLED) return;
  window.QSB_SKYSCRAPER_V3_INSTALLED = true;

  // ── Hard mode contract ────────────────────────────────────────────────
  const DASHBOARD_VISUAL_MODE = 'LIVE_DATA_ONLY';
  const POLICY = 'NO_RANDOM_LIVE_GRAPHICS';
  window.QSB_V3_MODE = DASHBOARD_VISUAL_MODE;
  window.QSB_V3_POLICY = POLICY;

  const POLL_MS = 5000;
  let lastTelemetry = null;

  function safe(name, fn) {
    return function () {
      try { return fn.apply(null, arguments); }
      catch (e) {
        if (window && window.console && console.warn) {
          console.warn('[qsb_skyscraper_v3] ' + name + ' failed:', e && e.message);
        }
        return null;
      }
    };
  }

  // ── Fetch live telemetry ──────────────────────────────────────────────
  async function fetchTelemetry() {
    try {
      const r = await fetch('/api/dashboard/live_telemetry?t=' + Date.now(),
                             { cache: 'no-store' });
      if (!r.ok) throw new Error('HTTP ' + r.status);
      const d = await r.json();
      return d && d.ok ? d : null;
    } catch (e) {
      return null;
    }
  }

  // ── Apply worker movement / recent-event flags to existing nodes ──────
  function applyWorkerHints(telemetry) {
    const t2d = window.QSB_TOWER_2D;
    const moves = (telemetry && telemetry.worker_movements) || [];
    const moveIds = new Set();
    moves.forEach(function (m) { if (m && m.worker_id) moveIds.add(m.worker_id); });

    // Worker IDs with a kernel event in the last 30 s.
    const recent = new Set();
    const events = (telemetry && telemetry.kernel_events) || [];
    const nowMs = Date.now();
    events.forEach(function (ev) {
      const w = ev && ev.extra && ev.extra.worker_id;
      if (!w) return;
      try {
        const ts = new Date(ev.ts).getTime();
        if (nowMs - ts < 30000) recent.add(w);
      } catch (_) {}
    });

    // Apply to 2D
    if (t2d && t2d.workerNodes) {
      Object.keys(t2d.workerNodes).forEach(function (id) {
        const node = t2d.workerNodes[id];
        if (!node) return;
        node.in_transit  = moveIds.has(id);
        node.recent_event = recent.has(id);
      });
    }

    // Apply to 3D (Babylon)
    const scene = window.QSB_SCENE || null;
    if (scene && scene.workerMeshes) {
      Object.keys(scene.workerMeshes).forEach(function (id) {
        const mesh = scene.workerMeshes[id];
        if (!mesh || !mesh._qsbBase) return;
        const b = mesh._qsbBase;
        if (moveIds.has(id) && !b.in_transit) {
          const mv = moves.find(function (m) { return m && m.worker_id === id; });
          if (mv) {
            b.in_transit = true;
            b.transit_from = mv.from_floor;
            b.transit_to   = mv.to_floor;
            b.transit_started_ms = performance.now();
            b.transit_dur_ms = mv.duration_ms || 2400;
          }
        }
      });
    }
  }

  // ── Apply lift movements ──────────────────────────────────────────────
  function applyLiftHints(telemetry) {
    const moves = (telemetry && telemetry.lift_movements) || [];
    if (!moves.length) return;
    const t2d = window.QSB_TOWER_2D;
    const scene = window.QSB_SCENE || null;
    moves.forEach(function (m) {
      const shaftIdx = m.shaft_index | 0;
      // 2D
      if (t2d && t2d.capsules && t2d.capsules[shaftIdx]) {
        const cap = t2d.capsules[shaftIdx];
        if (!cap.live_started_ms) {
          const yTop = 36 + 30 + 8;  // matches TOWER_TOP_Y + ROOF_H + 8
          const yBot = 1116 - 28 - 8; // matches TOWER_BOT_Y - GROUND_H - 8
          const range = yBot - yTop;
          const slabH = range / 53;
          const yAt = function (n) { return yBot - (n - 0.5) * slabH; };
          if (cap.parked_y == null) cap.parked_y = yAt(m.from_floor || 1);
          cap.live_start_y    = cap.parked_y;
          cap.live_dest_y     = yAt(m.to_floor || m.from_floor || 1);
          cap.live_started_ms = performance.now();
          cap.live_dur_ms     = m.duration_ms || 1800;
        }
      }
      // 3D
      if (scene && scene.capsuleMeshes && scene.capsuleMeshes[shaftIdx]) {
        const cap3 = scene.capsuleMeshes[shaftIdx];
        if (!cap3.live_started_ms) {
          const s = cap3.shaft;
          const range = s.yTop - s.yBottom - 0.8;
          const yAt = function (n) { return s.yBottom + 0.4 + ((n - 0.5) / 53) * range; };
          if (cap3.parked_y == null) cap3.parked_y = yAt(m.from_floor || 1);
          cap3.live_start_y    = cap3.parked_y;
          cap3.live_dest_y     = yAt(m.to_floor || m.from_floor || 1);
          cap3.live_started_ms = performance.now();
          cap3.live_dur_ms     = m.duration_ms || 1800;
        }
      }
    });
  }

  // ── Per-floor "no live data" badges (overlay on SVG) ──────────────────
  function paintMissingDataBadges(telemetry) {
    const t2d = window.QSB_TOWER_2D;
    if (!t2d || !t2d.svg || !t2d.floorRects) return;
    let layer = t2d.svg.querySelector('#v3MissingDataLayer');
    if (!layer) {
      layer = document.createElementNS('http://www.w3.org/2000/svg', 'g');
      layer.setAttribute('id', 'v3MissingDataLayer');
      t2d.svg.appendChild(layer);
    }
    layer.innerHTML = '';
    const flags = (telemetry && telemetry.missing_data_flags) || [];
    flags.slice(0, 30).forEach(function (f) {
      const n = f.floor;
      const r = t2d.floorRects[n];
      if (!r) return;
      const x = Number(r.getAttribute('x'));
      const y = Number(r.getAttribute('y'));
      const h = Number(r.getAttribute('height'));
      const g = document.createElementNS('http://www.w3.org/2000/svg', 'g');
      g.setAttribute('transform', 'translate(' + (x - 38) + ',' + (y + h / 2) + ')');
      g.innerHTML = (
        '<rect x="-18" y="-7" width="36" height="14" rx="3" ' +
              'fill="rgba(30,30,40,0.72)" stroke="rgba(120,120,140,0.5)"/>' +
        '<text x="0" y="3" text-anchor="middle" fill="#aab1c6" ' +
              'font-size="8" font-family="JetBrains Mono, monospace">no live data</text>'
      );
      layer.appendChild(g);
    });
  }

  // ── Right-rail V3 panel ───────────────────────────────────────────────
  function esc(s) {
    if (s === null || s === undefined) return '—';
    return String(s).replace(/&/g, '&amp;').replace(/</g, '&lt;').replace(/>/g, '&gt;');
  }

  function renderRailPanel(d) {
    if (!d) return '<div class="tagline err">live_telemetry unavailable</div>';
    const wc = d.worker_counts || {};
    const oc = d.openclaw_state || {};
    const route = d.openclaw_route || {};
    const pt = d.paper_testnet_trades || {};
    const sf = d.stale_flags || [];
    const md = d.missing_data_flags || [];
    let staleRows = '';
    sf.slice(0, 5).forEach(function (f) {
      staleRows += '<div class="kv qsb-v2-small"><span>' + esc(f.path) + '</span><span>' + esc(f.reason) + '</span></div>';
    });
    let mdRows = '';
    md.slice(0, 5).forEach(function (f) {
      mdRows += '<div class="kv qsb-v2-small"><span>floor ' + esc(f.floor) + '</span><span>' + esc(f.reason) + '</span></div>';
    });

    return (
      '<div class="qsb-v2-note ok">DASHBOARD_VISUAL_MODE=<b>LIVE_DATA_ONLY</b> · ' +
        'NO_RANDOM_LIVE_GRAPHICS · execution_allowed=<b>false</b>' +
      '</div>' +
      '<div class="qsb-v2-section">' +
        '<h4>Live Telemetry — Worker Counts</h4>' +
        '<div class="kv"><span>canonical</span><span>' + esc(wc.total_canonical) + '</span></div>' +
        '<div class="kv"><span>active / reporting</span><span>' + esc(wc.total_active) + ' / ' + esc(wc.total_reporting) + '</span></div>' +
        '<div class="kv"><span>visible on skyscraper</span><span class="ok">' + esc(wc.total_visible_on_skyscraper) + '</span></div>' +
        '<div class="kv"><span>newly employed</span><span>' + esc(wc.total_newly_employed) + '</span></div>' +
        '<details><summary>Mismatch reason</summary>' +
          '<p class="qsb-v2-small">' + esc((wc.mismatch_reason || '').slice(0, 600)) + '</p>' +
        '</details>' +
      '</div>' +
      '<div class="qsb-v2-section">' +
        '<h4>OpenClaw (deterministic route)</h4>' +
        '<div class="kv"><span>status</span><span class="ok">' + esc(oc.status) + '</span></div>' +
        '<div class="kv"><span>tool execution</span><span class="warn">' + esc(oc.openclaw_real_tool_execution_enabled) + '</span></div>' +
        '<div class="kv"><span>current floor</span><span>' + esc(route.current_floor) + '</span></div>' +
        '<div class="kv qsb-v2-small"><span>advanced by</span><span>' + esc(route.advanced_by) + '</span></div>' +
        '<div class="kv"><span>tickets</span><span>' + esc(oc.diagnostic_ticket_count) + '</span></div>' +
      '</div>' +
      '<div class="qsb-v2-section">' +
        '<h4>Paper / Testnet (live)</h4>' +
        '<div class="kv"><span>mode</span><span><code>' + esc(pt.active_mode) + '</code></span></div>' +
        '<div class="kv"><span>open / max</span><span>' + esc(pt.open_trade_count) + ' / ' + esc(pt.max_open_trades) + '</span></div>' +
        '<div class="kv"><span>realized PnL</span><span>' + esc(pt.total_realized_pnl) + '</span></div>' +
        '<div class="kv"><span>closed trades</span><span>' + esc(pt.closed_trade_count) + '</span></div>' +
        '<div class="kv"><span>lessons</span><span>' + esc(pt.lesson_count) + '</span></div>' +
      '</div>' +
      '<div class="qsb-v2-section">' +
        '<h4>Movement (real only)</h4>' +
        '<div class="kv"><span>worker movements</span><span>' + esc((d.worker_movements || []).length) + '</span></div>' +
        '<div class="kv"><span>lift movements</span><span>' + esc((d.lift_movements || []).length) + '</span></div>' +
        '<div class="kv"><span>packets</span><span>' + esc((d.packets || []).length) + '</span></div>' +
        '<div class="kv"><span>kernel events</span><span>' + esc((d.kernel_events || []).length) + '</span></div>' +
      '</div>' +
      '<div class="qsb-v2-section">' +
        '<h4>Data Health</h4>' +
        '<div class="kv"><span>stale flags</span><span>' + esc(sf.length) + '</span></div>' +
        staleRows +
        '<div class="kv"><span>floors w/ no live data</span><span>' + esc(md.length) + '</span></div>' +
        mdRows +
      '</div>'
    );
  }

  function renderTickerOverlay(d) {
    const host = document.getElementById('tickerBody');
    if (!host) return;
    const rows = (d && d.event_ticker) || [];
    if (!rows.length) {
      host.innerHTML = '<div class="tagline">No live events yet. ' +
        '<span class="qsb-v2-small">(NO_RANDOM_LIVE_GRAPHICS)</span></div>';
      return;
    }
    let html = '<div class="qsb-v3-ticker">';
    rows.slice(0, 18).forEach(function (r) {
      html += (
        '<div class="qsb-v3-ticker-row">' +
          '<span class="qsb-v3-ticker-ts">' + esc((r.ts || '').slice(11, 19)) + '</span>' +
          '<span class="qsb-v3-ticker-src qsb-v3-src-' + esc(r.source) + '">' + esc(r.source) + '</span>' +
          '<span class="qsb-v3-ticker-msg">' + esc(r.summary) + '</span>' +
        '</div>'
      );
    });
    html += '</div>';
    host.innerHTML = html;
  }

  // ── HUD chip in stage header ──────────────────────────────────────────
  function paintModeChip(d) {
    let chip = document.getElementById('qsbV3ModeChip');
    if (!chip) {
      const meta = document.getElementById('stageMeta');
      if (!meta) return;
      chip = document.createElement('span');
      chip.id = 'qsbV3ModeChip';
      chip.className = 'qsb-v3-mode-chip';
      meta.parentNode.insertBefore(chip, meta);
    }
    const stale = d ? ((d.stale_flags || []).length) : 0;
    chip.textContent = 'LIVE_DATA_ONLY · ' + (stale ? stale + ' stale' : 'sources fresh');
    chip.classList.toggle('warn', stale > 0);
  }

  // ── Tick + wiring ─────────────────────────────────────────────────────
  const safeApplyWorkerHints = safe('applyWorkerHints', applyWorkerHints);
  const safeApplyLiftHints   = safe('applyLiftHints',   applyLiftHints);
  const safePaintMissing     = safe('paintMissingDataBadges', paintMissingDataBadges);
  const safeRenderRail       = safe('renderRailPanel', renderRailPanel);
  const safeRenderTicker     = safe('renderTickerOverlay', renderTickerOverlay);
  const safePaintModeChip    = safe('paintModeChip', paintModeChip);

  // ── EQSB scene overlay: per-floor safety badges + Penthouse glow ──
  async function paintSceneOverlay() {
    try {
      const r = await fetch('/api/telemetry/scene_overlay?t=' + Date.now(),
                             { cache: 'no-store' });
      if (!r.ok) return;
      const o = await r.json();
      if (!o || o.ok === false) return;
      const tower = window.QSB_TOWER_2D;
      if (!tower || !tower.svg) return;
      let layer = tower.svg.querySelector('#v1SceneOverlay');
      if (!layer) {
        layer = document.createElementNS('http://www.w3.org/2000/svg', 'g');
        layer.setAttribute('id', 'v1SceneOverlay');
        tower.svg.appendChild(layer);
      }
      layer.innerHTML = '';
      const safety = o.per_floor_safety_state || {};
      Object.keys(safety).forEach(function (k) {
        const n = Number(k);
        const r = tower.floorRects && tower.floorRects[n];
        if (!r) return;
        const x = Number(r.getAttribute('x'));
        const y = Number(r.getAttribute('y'));
        const w = Number(r.getAttribute('width'));
        const h = Number(r.getAttribute('height'));
        const state = String(safety[k] || 'UNKNOWN');
        const color = state === 'OK' || state === 'OK_PAPER_ONLY' ? '#3fcf6e'
                    : state === 'DEGRADED' ? '#e2b14e'
                    : state === 'BLOCKED'  ? '#ff6b6b'
                    : '#9fb6d4';
        const dot = document.createElementNS('http://www.w3.org/2000/svg', 'circle');
        dot.setAttribute('cx', x + w + 4);
        dot.setAttribute('cy', y + h / 2);
        dot.setAttribute('r', 3);
        dot.setAttribute('fill', color);
        dot.setAttribute('stroke', 'rgba(8,12,22,0.6)');
        dot.setAttribute('stroke-width', '1');
        layer.appendChild(dot);
      });
      // Penthouse crown glow tied to cadence tick_count
      const pent = tower.floorRects && tower.floorRects[53];
      if (pent && o.penthouse_glow) {
        const glow = document.createElementNS('http://www.w3.org/2000/svg', 'circle');
        const x = Number(pent.getAttribute('x'));
        const y = Number(pent.getAttribute('y'));
        const w = Number(pent.getAttribute('width'));
        const phase = Number(o.penthouse_glow.glow_phase_0_to_1 || 0);
        const rad = 28 + Math.sin(phase * 2 * Math.PI) * 6;
        glow.setAttribute('cx', x + w / 2);
        glow.setAttribute('cy', y - 6);
        glow.setAttribute('r', rad.toFixed(1));
        glow.setAttribute('fill', 'none');
        glow.setAttribute('stroke', '#ffd24c');
        glow.setAttribute('stroke-opacity', '0.55');
        glow.setAttribute('stroke-width', '2');
        layer.appendChild(glow);
      }
    } catch (_) { /* non-fatal */ }
  }

  const safePaintSceneOverlay = safe('paintSceneOverlay', paintSceneOverlay);

  async function tick() {
    const d = await fetchTelemetry();
    if (!d) {
      safePaintModeChip(null);
      const body = document.getElementById('qsbV3Body');
      if (body) body.innerHTML = '<div class="tagline err">live_telemetry unavailable — backend reachable?</div>';
      return;
    }
    lastTelemetry = d;
    // Expose OpenClaw current_floor to the Babylon renderer (qsb_scene.js)
    // so the persistent OpenClaw mesh can anchor itself.
    try {
      const ocf = (d.openclaw_route && d.openclaw_route.current_floor)
                  || (d.openclaw_state && d.openclaw_state.openclaw_current_floor);
      if (ocf) (window.QSB = window.QSB || {}).openclawCurrentFloor = ocf;
    } catch (_) {}
    // Build the problem-worker set from OpenClaw findings + discipline.
    try {
      const set = new Set();
      const tickets = (d.openclaw_state && d.openclaw_state.diagnostic_tickets) || [];
      tickets.forEach(function (t) {
        // Tickets that reference workers do so via routing — leave for future.
      });
      // Fetch /api/openclaw/worker_findings + /api/workforce/discipline in
      // parallel so the set is real. Cached in window.QSB until next tick.
      Promise.all([
        fetch('/api/openclaw/worker_findings').then(function (r) { return r.ok ? r.json() : null; }).catch(function () { return null; }),
        fetch('/api/workforce/discipline').then(function (r) { return r.ok ? r.json() : null; }).catch(function () { return null; }),
      ]).then(function (results) {
        const findings = results[0] || {};
        const discipline = results[1] || {};
        (findings.worker_findings || []).forEach(function (f) { if (f.worker_id) set.add(f.worker_id); });
        (discipline.on_warning_workers || []).forEach(function (w) { if (w.worker_id) set.add(w.worker_id); });
        (discipline.restricted_workers || []).forEach(function (w) { if (w.worker_id) set.add(w.worker_id); });
        (discipline.suspended_workers || []).forEach(function (w) { if (w.worker_id) set.add(w.worker_id); });
        (window.QSB = window.QSB || {}).problemWorkerIds = set;
      });
    } catch (_) {}
    safeApplyWorkerHints(d);
    safeApplyLiftHints(d);
    safePaintMissing(d);
    safePaintModeChip(d);
    safePaintSceneOverlay();
    const body = document.getElementById('qsbV3Body');
    if (body) {
      try { body.innerHTML = safeRenderRail(d); }
      catch (_) { body.innerHTML = '<div class="tagline err">V3 render failed</div>'; }
    }
    safeRenderTicker(d);
  }

  function attach() {
    document.querySelectorAll('#rightTabs button').forEach(function (b) {
      if (b.getAttribute('data-tab') === 'qsbv3') {
        b.addEventListener('click', function () { try { tick(); } catch (_) {} });
      }
    });
    const r = document.getElementById('qsbV3RefreshBtn');
    if (r) r.addEventListener('click', function () { try { tick(); } catch (_) {} });
    setTimeout(function () { try { tick(); } catch (_) {} }, 1500);
    setInterval(function () { try { tick(); } catch (_) {} }, POLL_MS);
  }

  function safeAttach() {
    try { attach(); } catch (e) {
      if (window && window.console) console.warn('[qsb_skyscraper_v3] attach failed:', e && e.message);
    }
  }

  if (document.readyState === 'loading') {
    document.addEventListener('DOMContentLoaded', safeAttach);
  } else {
    safeAttach();
  }

  window.QSB_V3 = {
    refresh: tick,
    lastTelemetry: function () { return lastTelemetry; },
    mode: DASHBOARD_VISUAL_MODE,
    policy: POLICY,
  };
})();
