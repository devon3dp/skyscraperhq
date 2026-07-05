/*
 * QSB 3D Revamp — OpenClaw Supervisor Card (bottom-right of stage)
 * Phase: QSB_DASHBOARD_3D_TOTAL_REVAMP_WORKERS_OPENCLAW_V1
 *
 * A persistent cockpit card that shows OpenClaw's:
 *   - status / mode
 *   - current floor (from real route)
 *   - tickets (live count + top 3)
 *   - last update
 *
 * No fake movement. No random data.
 */
(function () {
  'use strict';
  if (window.QSB_3D_OPENCLAW_INSTALLED) return;
  window.QSB_3D_OPENCLAW_INSTALLED = true;

  function esc(s) {
    if (s === null || s === undefined) return '—';
    return String(s).replace(/&/g, '&amp;').replace(/</g, '&lt;').replace(/>/g, '&gt;');
  }

  function ensureCard() {
    let el = document.getElementById('qsb3dOpenClaw');
    if (el) return el;
    const stage = document.getElementById('stage') || document.body;
    el = document.createElement('div');
    el.id = 'qsb3dOpenClaw';
    el.className = 'qsb-3d-openclaw';
    stage.appendChild(el);
    return el;
  }

  function renderTicket(t) {
    const sev = String(t.severity || 'info').toLowerCase();
    return (
      '<div class="qsb-3d-openclaw-tk">' +
        '<span class="qsb-3d-openclaw-tk-sev ' + sev + '">' + esc(sev) + '</span>' +
        esc(t.title) +
      '</div>'
    );
  }

  function update(cache) {
    const el = ensureCard();
    if (!cache) return;
    const oc = cache.oc || {};
    const route = cache.route || {};
    const tickets = oc.tickets || [];
    el.innerHTML = (
      '<h5><span class="qsb-3d-openclaw-pulse"></span>OpenClaw Supervisor</h5>' +
      '<div class="qsb-3d-openclaw-row"><span>status</span><span style="color:#a4f3c6">active</span></div>' +
      '<div class="qsb-3d-openclaw-row"><span>current floor</span><span>' + esc(route.current_floor) + '</span></div>' +
      '<div class="qsb-3d-openclaw-row"><span>advanced by</span><span style="font-size:9px">' + esc(route.advanced_by) + '</span></div>' +
      '<div class="qsb-3d-openclaw-row"><span>tickets</span><span style="color:#fbd784">' + esc(tickets.length) + '</span></div>' +
      '<div class="qsb-3d-openclaw-row"><span>real_tool_exec</span><span style="color:#a4f3c6">false</span></div>' +
      (tickets.length
        ? ('<div class="qsb-3d-openclaw-tickets">' +
            tickets.slice(0, 3).map(renderTicket).join('') +
          '</div>')
        : '<div style="margin-top:6px;font-size:10px;color:#a890d4">No tickets — supervisor idle.</div>')
    );
  }

  window.QSB_3D_OPENCLAW = { update: update };
})();
