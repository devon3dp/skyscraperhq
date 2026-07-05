/*
 * QSB Next3D — HUD overlays (top pills, lift panel, openclaw panel, footer)
 * Phase: QSB_NEXTGEN_3D_DASHBOARD_GREENFIELD_REBUILD_V1
 */
(function () {
  'use strict';

  function esc(s) {
    if (s === null || s === undefined) return '';
    return String(s).replace(/&/g, '&amp;').replace(/</g, '&lt;').replace(/>/g, '&gt;');
  }

  function pill(id, text, cls) {
    const el = document.getElementById(id);
    if (!el) return;
    el.textContent = text;
    el.className = 'n3d-pill' + (cls ? (' ' + cls) : '');
  }

  function setText(id, txt) {
    const el = document.getElementById(id);
    if (el) el.textContent = txt;
  }

  function renderTopPills(state, engineMode) {
    pill('n3dEngineMeta', 'engine: ' + (engineMode || 'babylon'),
         engineMode === 'webgl_unavailable' ? 'fail' : 'ok');
    const k = state.penthouse && state.penthouse.command;
    pill('n3dKernelMeta', 'kernel: ' + (k && k.kernel_active ? 'active' : '—'),
         k && k.kernel_active ? 'ok' : 'warn');
    const locksOpen = (k && k.locks_open) || 0;
    pill('n3dLockMeta', 'locks ' + locksOpen + '/13',
         locksOpen === 0 ? 'ok' : 'fail');
    const w = state.workers || {};
    pill('n3dWorkerMeta', 'workers ' + (w.canonical_total || 0));
    pill('n3dLiftMeta', 'lifts ' + (state.lifts || []).length);
    pill('n3dOcMeta', 'openclaw f' + (state.openclaw.current_floor || '—') +
         ' · ' + (state.openclaw.ticket_count || 0) + ' tk',
         (state.openclaw.ticket_count || 0) === 0 ? 'ok' : 'warn');
    pill('n3dCadenceMeta', 'cadence ' + state.cadence_tick);
  }

  function renderLiftPanel(state) {
    const el = document.getElementById('n3dLiftPanel');
    if (!el) return;
    const lifts = state.lifts || [];
    let html = '<h4>LIFTS · ' + lifts.length + '</h4>';
    if (!lifts.length) {
      html += '<div class="n3d-no-data">no lift telemetry</div>';
      el.innerHTML = html;
      return;
    }
    lifts.forEach(function (L) {
      const status = L.moving ? 'MOVING' : (L.status === 'online' ? 'IDLE' : (L.status || '').toUpperCase());
      const cls = L.moving ? 'moving' : 'idle';
      const cf = L.current_floor === null || L.current_floor === undefined ? '—' : ('f' + L.current_floor);
      html += (
        '<div class="n3d-lift-row ' + cls + '" data-lift="' + esc(L.lift_id) + '">' +
          '<span class="n3d-lift-id">' + esc((L.lift_id || '').replace(/_/g, ' ')) + '</span>' +
          '<span class="n3d-lift-type">' + esc(L.type || 'main') + '</span>' +
          '<span class="n3d-lift-floor">' + esc(cf) + '</span>' +
          '<span class="n3d-lift-status ' + cls + '">' + esc(status) + '</span>' +
        '</div>'
      );
    });
    el.innerHTML = html;
  }

  function renderOpenClawPanel(state) {
    const el = document.getElementById('n3dOpenClawPanel');
    if (!el) return;
    const oc = state.openclaw || {};
    let html = '<h4>OPENCLAW · SUPERVISOR</h4>';
    html += '<div class="n3d-oc-row"><span>current floor</span><b>' + esc(oc.current_floor || '—') + '</b></div>';
    html += '<div class="n3d-oc-row"><span>advanced by</span><b>' + esc(oc.advanced_by || '—') + '</b></div>';
    html += '<div class="n3d-oc-row"><span>is random</span><b>' + esc(oc.is_random) + '</b></div>';
    html += '<div class="n3d-oc-row"><span>real tool exec</span><b style="color:#ff8aa0">FALSE</b></div>';
    html += '<div class="n3d-oc-row"><span>tickets</span><b>' + esc(oc.ticket_count || 0) + '</b></div>';
    html += '<div style="margin-top:6px"><b style="color:#d8b4ff;font-size:9.6px">RECENT TICKETS</b></div>';
    if (!(oc.tickets || []).length) {
      html += '<div class="n3d-no-data">none</div>';
    } else {
      oc.tickets.slice(0, 4).forEach(function (t) {
        html += '<div class="n3d-oc-ticket">[' + esc(t.severity || '?') + '] ' +
          esc((t.issue || t.description || '').slice(0, 80)) + '</div>';
      });
    }
    el.innerHTML = html;
  }

  function renderFooter(state) {
    const pnl = state.floor41 && state.floor41.pnl || {};
    setText('n3dPnl', (pnl.total_pnl !== undefined ? pnl.total_pnl.toFixed(2) : '—'));
    setText('n3dOpenTrades', String((state.floor41.open_trades || []).length));
    setText('n3dClosed', String((state.floor41.closed_trades || []).length));
  }

  function build() {
    function update(state, engineMode) {
      renderTopPills(state, engineMode);
      renderLiftPanel(state);
      renderOpenClawPanel(state);
      renderFooter(state);
    }
    return { update: update };
  }

  window.NEXT3D_HUD = { build: build };
})();
