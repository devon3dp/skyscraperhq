/*
 * QSB Workforce Operations Panel
 * Phase: QSB_NEXT_SAFE_IMPROVEMENTS_V1
 *
 * Consumes /api/tasks/active + /api/openclaw/tickets and renders a real
 * operational panel in the right rail. Also exposes a "Tick" button that
 * triggers the paper-strategy runner.
 */
(function () {
  'use strict';
  if (window.QSB_OPS_PANEL_INSTALLED) return;
  window.QSB_OPS_PANEL_INSTALLED = true;

  const POLL_MS = 8000;

  function esc(s) {
    if (s === null || s === undefined) return '—';
    return String(s).replace(/&/g, '&amp;').replace(/</g, '&lt;').replace(/>/g, '&gt;');
  }
  function fmt(n, d) {
    if (n === null || n === undefined || isNaN(Number(n))) return '—';
    return Number(n).toFixed(d == null ? 2 : d);
  }
  async function fetchJSON(url) {
    try {
      const r = await fetch(url + (url.indexOf('?') === -1 ? '?' : '&') + 't=' + Date.now(),
                             { cache: 'no-store' });
      if (!r.ok) return null;
      return await r.json();
    } catch (_) { return null; }
  }
  function safe(name, fn) {
    return function () {
      try { return fn.apply(null, arguments); }
      catch (e) { if (window.console) console.warn('[qsb_ops_panel] ' + name + ': ' + (e && e.message)); }
    };
  }

  function renderTickets(tickets) {
    if (!tickets || !tickets.length) {
      return '<div class="tagline qsb-v2-small">No open tickets.</div>';
    }
    let html = '';
    tickets.forEach(function (t) {
      const sev = String(t.severity || 'info').toLowerCase();
      const sevCls = sev === 'critical' ? 'err' : sev === 'warning' ? 'warn' : 'ok';
      html += (
        '<div class="qsb-ops-ticket">' +
          '<div class="qsb-ops-ticket-hdr">' +
            '<span class="qsb-ops-sev ' + sevCls + '">' + esc(sev) + '</span>' +
            '<span class="qsb-ops-tid">' + esc(t.ticket_id) + '</span>' +
          '</div>' +
          '<div class="qsb-ops-ticket-title">' + esc(t.title) + '</div>' +
          '<div class="qsb-ops-ticket-evidence qsb-v2-small">' + esc((t.evidence || '').slice(0, 240)) + '</div>' +
          '<div class="qsb-ops-ticket-action qsb-v2-small">↳ ' + esc(t.advised_action || '—') + '</div>' +
        '</div>'
      );
    });
    return html;
  }

  function renderActiveTasks(tasks) {
    if (!tasks || !tasks.length) {
      return '<div class="tagline qsb-v2-small">No active tasks.</div>';
    }
    let html = '<div class="qsb-ops-tasks">';
    tasks.slice(0, 20).forEach(function (t) {
      const kindCls =
        t.kind === 'worker_movement' ? 'kind-move' :
        t.kind === 'open_paper_trade' ? 'kind-trade' :
        t.kind === 'openclaw_ticket_review' ? 'kind-oc' :
        t.kind === 'discipline_review' ? 'kind-disc' : 'kind-other';
      html += (
        '<div class="qsb-ops-task ' + kindCls + '">' +
          '<div class="qsb-ops-task-row1">' +
            '<span class="qsb-ops-kind">' + esc(t.kind) + '</span>' +
            '<span class="qsb-ops-wid">' + esc(t.worker_id) + '</span>' +
          '</div>' +
          '<div class="qsb-ops-task-row2 qsb-v2-small">' +
            esc(t.department) + ' · ' + esc(t.room) +
          '</div>' +
          '<div class="qsb-ops-task-desc">' + esc(t.description) + '</div>' +
        '</div>'
      );
    });
    html += '</div>';
    return html;
  }

  async function refresh() {
    const body = document.getElementById('opsBody');
    if (!body) return;
    body.innerHTML = '<div class="tagline">Workforce Ops — loading…</div>';
    const [tasks, tickets, route, role, findings] = await Promise.all([
      fetchJSON('/api/tasks/active'),
      fetchJSON('/api/openclaw/tickets'),
      fetchJSON('/api/openclaw/route'),
      fetchJSON('/api/openclaw/role'),
      fetchJSON('/api/openclaw/worker_findings'),
    ]);
    const tickResp = await fetchJSON('/api/dashboard/live_telemetry');
    const tick = (tickResp && tickResp.workforce_v1 && tickResp.workforce_v1.task_count) || 0;

    let html = '';
    html += (
      '<div class="qsb-v2-note ok">execution_allowed=<b>false</b> · real-money trading <b>off</b></div>' +
      '<div class="qsb-v2-section">' +
        '<h4>OpenClaw Supervisor</h4>' +
        '<div class="kv"><span>role</span><span class="qsb-v2-small">' + esc((role && role.role || '—').slice(0, 80)) + '</span></div>' +
        '<div class="kv"><span>current floor</span><span>' + esc(route && route.current_floor) + '</span></div>' +
        '<div class="kv qsb-v2-small"><span>advanced by</span><span>' + esc(route && route.advanced_by) + '</span></div>' +
        '<div class="kv"><span>tickets open</span><span class="warn">' + esc(tickets && tickets.ticket_count || 0) + '</span></div>' +
        '<div class="kv"><span>worker findings</span><span>' + esc(findings && findings.finding_count || 0) + '</span></div>' +
      '</div>' +
      '<div class="qsb-v2-section">' +
        '<h4>OpenClaw Tickets (' + esc((tickets && tickets.tickets || []).length) + ')</h4>' +
        renderTickets(tickets && tickets.tickets) +
      '</div>' +
      '<div class="qsb-v2-section">' +
        '<h4>Active Tasks (' + esc((tasks && tasks.count) || 0) + ' total)</h4>' +
        renderActiveTasks(tasks && tasks.tasks) +
      '</div>' +
      '<div class="qsb-v2-actions">' +
        '<button class="mini-btn" id="opsTickAllBtn">Run Paper Strategy Tick</button>' +
      '</div>'
    );
    body.innerHTML = html;
    const tickAll = document.getElementById('opsTickAllBtn');
    if (tickAll) tickAll.addEventListener('click', tickStrategy);
  }

  async function tickStrategy() {
    try {
      const r = await fetch('/api/ops/strategy_tick', { method: 'POST' });
      await r.json();
    } catch (_) {}
    refresh();
  }

  const safeRefresh = safe('refresh', refresh);
  const safeTickStrategy = safe('tickStrategy', tickStrategy);

  function attach() {
    document.querySelectorAll('#rightTabs button').forEach(function (b) {
      if (b.getAttribute('data-tab') === 'ops') {
        b.addEventListener('click', function () { try { refresh(); } catch (_) {} });
      }
    });
    const r = document.getElementById('opsRefreshBtn');
    if (r) r.addEventListener('click', function () { try { refresh(); } catch (_) {} });
    const t = document.getElementById('opsTickBtn');
    if (t) t.addEventListener('click', safeTickStrategy);
    setTimeout(refresh, 1600);
    setInterval(refresh, POLL_MS * 3);
  }

  if (document.readyState === 'loading') {
    document.addEventListener('DOMContentLoaded', attach);
  } else {
    attach();
  }
  window.QSB_OPS_PANEL = { refresh: safeRefresh, tick: safeTickStrategy };
})();
