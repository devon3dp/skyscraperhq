/*
 * QSB V2 Right-Rail Panel
 * Phase: QSB_OPENCLAW_PAPER_TRADE_WORKERS_3D_SKYSCRAPER_V2
 *
 * Renders the V2 tab content: OpenClaw, paper trades, PnL, lessons,
 * worker reconciliation, 3D dashboard status. All endpoints are
 * read-only or sandbox-only — no live execution buttons.
 */
(function () {
  'use strict';

  if (window.QSB_V2_PANEL_INSTALLED) return;
  window.QSB_V2_PANEL_INSTALLED = true;

  function esc(s) {
    if (s === null || s === undefined) return '—';
    return String(s)
      .replace(/&/g, '&amp;').replace(/</g, '&lt;').replace(/>/g, '&gt;');
  }
  function fmt(n, d) { if (n === null || n === undefined || isNaN(Number(n))) return '—'; return Number(n).toFixed(d || 2); }

  async function fetchPanel() {
    try {
      const r = await fetch('/api/qsb_v2/penthouse_combined?t=' + Date.now(),
                             { cache: 'no-store' });
      return await r.json();
    } catch (_) {
      return null;
    }
  }

  function renderOpenclaw(d) {
    const oc = d.openclaw || {};
    return (
      '<div class="qsb-v2-section">' +
        '<h4>OpenClaw — Supervision Limb</h4>' +
        '<div class="kv"><span>status</span><span class="ok">' + esc(oc.status) + '</span></div>' +
        '<div class="kv"><span>visual</span><span>' + esc(oc.openclaw_visual_enabled) + '</span></div>' +
        '<div class="kv"><span>sandbox</span><span>' + esc(oc.openclaw_sandbox_enabled) + '</span></div>' +
        '<div class="kv"><span>trade supervision</span><span>' + esc(oc.openclaw_trade_supervision_enabled) + '</span></div>' +
        '<div class="kv"><span>diagnostic ticketing</span><span>' + esc(oc.openclaw_diagnostic_ticketing_enabled) + '</span></div>' +
        '<div class="kv"><span>real_tool_execution</span><span class="warn">' + esc(oc.openclaw_real_tool_execution_enabled) + '</span></div>' +
        '<div class="kv"><span>tickets</span><span>' + esc(oc.diagnostic_ticket_count) + '</span></div>' +
      '</div>'
    );
  }

  function renderPaperTrades(d) {
    const pt = d.paper_trading || {};
    const cur = pt.current_open_trade_count || 0;
    const max = pt.max_open_trades || 20;
    const pctW = Math.min(100, (cur / max) * 100);
    return (
      '<div class="qsb-v2-section">' +
        '<h4>Paper / Testnet Trades</h4>' +
        '<div class="kv"><span>mode</span><span><code>' + esc(pt.active_mode) + '</code></span></div>' +
        '<div class="kv"><span>gateway</span><span class="qsb-v2-small">' + esc(pt.gateway_status) + '</span></div>' +
        '<div class="kv"><span>open / max</span><span>' + esc(cur) + ' / ' + esc(max) + '</span></div>' +
        '<div class="kv"><span>remaining slots</span><span>' + esc(pt.remaining_trade_slots) + '</span></div>' +
        '<div class="qsb-v2-meter"><div class="fill" style="width:' + pctW + '%"></div></div>' +
        '<div class="kv"><span>current PnL (open)</span><span>' + esc(fmt(pt.total_current_pnl)) + '</span></div>' +
        '<div class="kv"><span>realized PnL</span><span>' + esc(fmt(pt.total_realized_pnl)) + '</span></div>' +
        '<div class="kv"><span>closed trades</span><span>' + esc(pt.closed_trade_count) + '</span></div>' +
        '<div class="kv"><span>lessons learned</span><span>' + esc(pt.lesson_count) + '</span></div>' +
        '<div class="qsb-v2-actions">' +
          '<button class="mini-btn" id="qsbV2BtnRefresh">↻ Refresh</button>' +
          '<button class="mini-btn" id="qsbV2BtnSeed">Seed Training</button>' +
          '<button class="mini-btn" id="qsbV2BtnReconcile">Reconcile Workers</button>' +
        '</div>' +
      '</div>'
    );
  }

  function renderWorkers(d) {
    const w = d.workers || {};
    const bf = w.by_home_floor_counts || {};
    const top = Object.keys(bf).sort(function (a, b) { return bf[b] - bf[a]; }).slice(0, 6);
    let rows = '';
    top.forEach(function (k) {
      rows += '<div class="kv"><span class="qsb-v2-small">' + esc(k) + '</span><span>' + esc(bf[k]) + '</span></div>';
    });
    return (
      '<div class="qsb-v2-section">' +
        '<h4>Worker Reconciliation</h4>' +
        '<div class="kv"><span>canonical workers</span><span>' + esc(w.total_canonical_workers) + '</span></div>' +
        '<div class="kv"><span>active / reporting</span><span>' + esc(w.total_active_workers) + ' / ' + esc(w.total_reporting_workers) + '</span></div>' +
        '<div class="kv"><span>newly employed (V2)</span><span class="ok">' + esc(w.total_newly_employed_workers) + '</span></div>' +
        '<div class="qsb-v2-small">Top floors:</div>' +
        rows +
        '<details><summary>Why did counts mismatch?</summary>' +
          '<p class="qsb-v2-small">' + esc((w.mismatch_reason || '').slice(0, 600)) + '</p>' +
        '</details>' +
      '</div>'
    );
  }

  function render3DStatus(d) {
    const eqsb = d.eqsb || {};
    return (
      '<div class="qsb-v2-section">' +
        '<h4>3D Skyscraper Upgrade</h4>' +
        '<div class="kv"><span>upgrade level</span><span>v2_living_skyscraper</span></div>' +
        '<div class="kv"><span>distinct floors</span><span>7</span></div>' +
        '<div class="kv"><span>OpenClaw avatar</span><span class="ok">visible</span></div>' +
        '<div class="kv"><span>worker badges</span><span class="ok">visible</span></div>' +
        '<div class="kv"><span>HUD</span><span class="ok">slots + PnL + OpenClaw + workers</span></div>' +
        '<div class="kv"><span>EQSB self-audit</span><span>' + esc(eqsb.self_audit_verdict) + '</span></div>' +
        '<div class="kv"><span>EQSB Guardian</span><span>' + esc(eqsb.guardian_safety_state) + '</span></div>' +
        '<div class="kv"><span>EQSB quantum mode</span><span>' + esc(eqsb.quantum_mode) + '</span></div>' +
      '</div>'
    );
  }

  function renderPanel(d) {
    if (!d || !d.ok) {
      return '<div class="tagline">QSB V2 panel — loading…</div>';
    }
    const note = (
      '<div class="qsb-v2-note">' +
        'execution_allowed=<b>' + esc(d.execution_allowed) + '</b> · ' +
        'active_local_only=<b>' + esc(d.active_local_only) + '</b> · ' +
        'real_money_live=<b>' + esc(d.real_money_live_trading_enabled) + '</b>' +
      '</div>'
    );
    return note +
      renderOpenclaw(d) +
      renderPaperTrades(d) +
      renderWorkers(d) +
      render3DStatus(d);
  }

  async function refresh() {
    const body = document.getElementById('qsbV2Body');
    if (!body) return;
    body.innerHTML = '<div class="tagline">QSB V2 panel — loading…</div>';
    let d = null;
    try { d = await fetchPanel(); } catch (_) {}
    try { body.innerHTML = renderPanel(d); }
    catch (_) { body.innerHTML = '<div class="tagline err">QSB V2 panel render failed — backend returned malformed data.</div>'; }
    try { bindButtons(); } catch (_) {}
  }

  async function postRefreshAll() {
    try {
      const r = await fetch('/api/qsb_v2/refresh_all', { method: 'POST' });
      await r.json();
    } catch (_) {}
    refresh();
    if (window.QSB_V2 && window.QSB_V2.refresh) { window.QSB_V2.refresh(); }
  }

  async function postSeed() {
    try {
      await fetch('/api/qsb_v2/paper/seed_training', { method: 'POST' });
    } catch (_) {}
    refresh();
    if (window.QSB_V2 && window.QSB_V2.refresh) { window.QSB_V2.refresh(); }
  }

  async function postReconcile() {
    try {
      await fetch('/api/qsb_v2/reconcile_workers', { method: 'POST' });
    } catch (_) {}
    refresh();
    if (window.QSB_V2 && window.QSB_V2.refresh) { window.QSB_V2.refresh(); }
  }

  function bindButtons() {
    const r = document.getElementById('qsbV2BtnRefresh');
    if (r) r.addEventListener('click', postRefreshAll);
    const s = document.getElementById('qsbV2BtnSeed');
    if (s) s.addEventListener('click', postSeed);
    const x = document.getElementById('qsbV2BtnReconcile');
    if (x) x.addEventListener('click', postReconcile);
  }

  function attach() {
    document.querySelectorAll('#rightTabs button').forEach(function (b) {
      if (b.getAttribute('data-tab') === 'qsbv2') {
        b.addEventListener('click', function () { try { refresh(); } catch (_) {} });
      }
    });
    const btn = document.getElementById('qsbV2RefreshBtn');
    if (btn) btn.addEventListener('click', function () { try { refresh(); } catch (_) {} });
    setTimeout(function () { try { refresh(); } catch (_) {} }, 1200);
    setInterval(function () { try { refresh(); } catch (_) {} }, 30000);
  }

  function safeAttach() {
    try { attach(); } catch (e) {
      if (window && window.console) console.warn('[qsb_v2_panel] attach failed:', e && e.message);
    }
  }

  if (document.readyState === 'loading') {
    document.addEventListener('DOMContentLoaded', safeAttach);
  } else {
    safeAttach();
  }
})();
