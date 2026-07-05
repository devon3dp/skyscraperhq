/*
 * QSB Floor 41 OANDA — Dashboard Interior Panel
 * Phase: QSB_FLOOR_41_OANDA_FULL_TRADING_FLOOR_REBUILD_V1
 *
 * Renders a complete OANDA Trading Floor interior when floor=41 is
 * selected. Cards/tables/boards:
 *   - Account + Engine Mode (top strip)
 *   - Instruments + live prices/spreads
 *   - Open Trades Board (with mark + uPnL)
 *   - Closed Trades + Realized PnL
 *   - Worker Thoughts stream
 *   - OpenClaw Floor 41 findings + tickets
 *   - Open/Close trade entry forms (paper-only)
 *   - Risk rules + rooms + workers
 *
 * Source-backed only. Paper/practice labelled everywhere.
 */
(function () {
  'use strict';
  if (window.QSB_FLOOR41_OANDA_INSTALLED) return;
  window.QSB_FLOOR41_OANDA_INSTALLED = true;

  const POLL_MS = 7000;

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

  async function postJSON(url, body) {
    try {
      const r = await fetch(url, {
        method: 'POST',
        headers: {'Content-Type': 'application/json'},
        body: JSON.stringify(body),
      });
      return await r.json();
    } catch (e) { return {ok: false, error: String(e)}; }
  }

  function ensurePanel() {
    let el = document.getElementById('qsbFloor41Oanda');
    if (el) return el;
    const stage = document.getElementById('stage') || document.body;
    el = document.createElement('div');
    el.id = 'qsbFloor41Oanda';
    el.className = 'qsb-f41-oanda';
    el.style.display = 'none';
    stage.appendChild(el);
    return el;
  }

  function visible() {
    const sel = (window.QSB && window.QSB.selectedFloor);
    return sel === 41;
  }

  function pnlClass(n) {
    if (n > 0) return 'pnl-up';
    if (n < 0) return 'pnl-down';
    return 'pnl-flat';
  }

  function renderHeader(d) {
    const acct = d.account || {};
    const engine = d.engine_mode || '—';
    const pnl = d.pnl || {};
    const oc = d.openclaw || {};
    const ocTickets = (oc.tickets || []).length;
    return (
      '<div class="f41-hdr">' +
        '<div class="f41-hdr-title">FLOOR 41 · OANDA TRADING FLOOR</div>' +
        '<div class="f41-hdr-mode">mode: <b>' + esc(engine) + '</b> · paper/practice only</div>' +
        '<div class="f41-hdr-acct">' +
          'acct ' + esc(acct.account_id || '—') + ' · ' +
          'bal ' + esc(acct.balance || 0) + ' ' + esc(acct.currency || 'USD') + ' · ' +
          'NAV ' + esc(acct.NAV || 0) +
        '</div>' +
        '<div class="f41-hdr-pnl">' +
          '<span class="' + pnlClass(pnl.realized_pnl_total) + '">R ' + (pnl.realized_pnl_total || 0).toFixed(4) + '</span> · ' +
          '<span class="' + pnlClass(pnl.unrealized_pnl_total) + '">U ' + (pnl.unrealized_pnl_total || 0).toFixed(4) + '</span> · ' +
          '<span class="' + pnlClass(pnl.total_pnl) + '">T ' + (pnl.total_pnl || 0).toFixed(4) + '</span>' +
        '</div>' +
        '<div class="f41-hdr-oc">OpenClaw: <b>' + ocTickets + '</b> tickets</div>' +
      '</div>'
    );
  }

  function renderPrices(d) {
    const prices = d.prices || [];
    if (!prices.length) return '<div class="f41-card"><h5>Prices</h5><div class="muted">no quotes</div></div>';
    let rows = '';
    prices.forEach(function (p) {
      rows += '<tr>' +
        '<td>' + esc(p.instrument) + '</td>' +
        '<td>' + esc(p.bid) + '</td>' +
        '<td>' + esc(p.ask) + '</td>' +
        '<td>' + esc((p.spread_pips || 0).toFixed(2)) + ' pip</td>' +
      '</tr>';
    });
    return (
      '<div class="f41-card">' +
        '<h5>Instruments · Prices · Spreads</h5>' +
        '<table class="f41-tbl"><thead><tr><th>instr</th><th>bid</th><th>ask</th><th>spread</th></tr></thead>' +
        '<tbody>' + rows + '</tbody></table>' +
      '</div>'
    );
  }

  function renderOpenTrades(d) {
    const trades = d.open_trades || [];
    let body = '';
    if (!trades.length) {
      body = '<div class="muted">no open paper trades</div>';
    } else {
      let rows = '';
      trades.forEach(function (t) {
        const up = t.unrealized_pnl || 0;
        rows += '<tr>' +
          '<td>' + esc(t.trade_id) + '</td>' +
          '<td>' + esc(t.instrument) + '</td>' +
          '<td>' + esc(t.direction) + '</td>' +
          '<td>' + esc(t.units) + '</td>' +
          '<td>' + esc(t.entry_price) + '</td>' +
          '<td>' + esc(t.mark_price === null ? '—' : t.mark_price) + '</td>' +
          '<td class="' + pnlClass(up) + '">' + up.toFixed(4) + '</td>' +
          '<td><button class="f41-close-btn" data-tid="' + esc(t.trade_id) + '">close</button></td>' +
        '</tr>';
      });
      body = '<table class="f41-tbl"><thead><tr><th>id</th><th>instr</th><th>dir</th><th>units</th><th>entry</th><th>mark</th><th>uPnL</th><th></th></tr></thead>' +
             '<tbody>' + rows + '</tbody></table>';
    }
    return '<div class="f41-card"><h5>Open Trades Board (paper/practice)</h5>' + body + '</div>';
  }

  function renderClosedTrades(d) {
    const trades = d.closed_trades || [];
    if (!trades.length) return '<div class="f41-card"><h5>Closed Trades</h5><div class="muted">no closed trades yet</div></div>';
    let rows = '';
    trades.slice(-12).reverse().forEach(function (t) {
      const pnl = t.pnl_amount || 0;
      rows += '<tr>' +
        '<td>' + esc(t.trade_id) + '</td>' +
        '<td>' + esc(t.instrument) + '</td>' +
        '<td>' + esc(t.direction) + '</td>' +
        '<td>' + esc(t.entry_price) + '</td>' +
        '<td>' + esc(t.exit_price) + '</td>' +
        '<td class="' + pnlClass(pnl) + '">' + pnl.toFixed(4) + '</td>' +
        '<td title="' + esc(t.close_reason) + '">' + esc((t.close_reason || '').slice(0, 14)) + '</td>' +
      '</tr>';
    });
    return (
      '<div class="f41-card">' +
        '<h5>Closed Trades (last 12)</h5>' +
        '<table class="f41-tbl"><thead><tr><th>id</th><th>instr</th><th>dir</th><th>entry</th><th>exit</th><th>pnl</th><th>reason</th></tr></thead>' +
        '<tbody>' + rows + '</tbody></table>' +
      '</div>'
    );
  }

  function renderThoughts(d) {
    const ths = d.thoughts || [];
    if (!ths.length) return '<div class="f41-card"><h5>Worker Thoughts</h5><div class="muted">no thoughts</div></div>';
    let body = '';
    ths.slice(-15).reverse().forEach(function (t) {
      body += '<div class="f41-thought">' +
        '<span class="f41-thought-w">' + esc(t.worker_id.replace(/^f41_/, '')) + '</span>' +
        '<span class="f41-thought-topic">' + esc(t.topic) + '</span>' +
        '<span class="f41-thought-txt">' + esc(t.thought) + '</span>' +
      '</div>';
    });
    return '<div class="f41-card"><h5>Worker Thoughts (paper/practice)</h5>' + body + '</div>';
  }

  function renderOpenClaw(d) {
    const oc = d.openclaw || {};
    const findings = oc.findings || [];
    const tickets = oc.tickets || [];
    let body = '';
    findings.forEach(function (f) {
      body += '<div class="f41-finding sev-' + esc((f.severity || '').toLowerCase()) + '">' +
        '<b>' + esc(f.severity) + '</b> · ' + esc(f.kind) + ' — ' + esc(f.detail) +
      '</div>';
    });
    let tk = '';
    tickets.forEach(function (t) {
      tk += '<div class="f41-ticket sev-' + esc((t.severity || '').toLowerCase()) + '">' +
        '<b>' + esc(t.id) + '</b> ' + esc(t.severity) + ' · ' + esc(t.issue) +
      '</div>';
    });
    return (
      '<div class="f41-card">' +
        '<h5>OpenClaw Supervision (read-only)</h5>' +
        body +
        (tk ? '<div class="f41-tickets-hdr">Tickets</div>' + tk : '') +
      '</div>'
    );
  }

  function renderForms() {
    return (
      '<div class="f41-card">' +
        '<h5>Order Entry (paper/practice only)</h5>' +
        '<div class="f41-form-row">' +
          '<select id="f41-open-instr">' +
            '<option>EUR_USD</option><option>GBP_USD</option><option>USD_JPY</option>' +
            '<option>AUD_USD</option><option>USD_CAD</option>' +
          '</select>' +
          '<select id="f41-open-dir"><option>buy</option><option>sell</option></select>' +
          '<input id="f41-open-units" type="number" value="1000" min="1" max="50000" placeholder="units">' +
          '<input id="f41-open-reason" type="text" placeholder="entry_reason (required)">' +
          '<button id="f41-open-btn">Open Paper Trade</button>' +
        '</div>' +
        '<div class="f41-form-note">' +
          'Entry reason required · risk + Guardian gates enforced · ' +
          'live trading disabled at module level.' +
        '</div>' +
        '<div id="f41-action-result" class="f41-action-result"></div>' +
      '</div>'
    );
  }

  function renderRoomsWorkers(d) {
    const rooms = d.rooms || [];
    const workers = d.workers || [];
    let html = '<div class="f41-card"><h5>Rooms (' + rooms.length + ') · Workers (' + workers.length + ')</h5>';
    rooms.forEach(function (r) {
      const inRoom = workers.filter(function (w) { return w.room === r.name; });
      html += '<div class="f41-room"><b>' + esc(r.name) + '</b> · ' + esc(r.responsibility) + '<div class="f41-room-workers">';
      inRoom.forEach(function (w) {
        html += '<span class="f41-room-w" title="' + esc(w.station) + '">' +
                  esc(w.worker_id.replace(/^f41_/, '')) +
                  ' <i>' + esc(w.state) + '</i>' +
                '</span>';
      });
      html += '</div></div>';
    });
    html += '</div>';
    return html;
  }

  async function render() {
    const el = ensurePanel();
    if (!visible()) { el.style.display = 'none'; return; }
    el.style.display = 'block';
    const data = await fetchJSON('/api/trading/oanda/floor41/dashboard_interior');
    if (!data) {
      el.innerHTML = '<div class="f41-empty">Floor 41 telemetry unavailable. Run scripts/qsb_floor41_oanda_refresh.sh</div>';
      return;
    }
    el.innerHTML = (
      renderHeader(data) +
      '<div class="f41-grid">' +
        '<div class="f41-col">' +
          renderPrices(data) +
          renderOpenTrades(data) +
          renderClosedTrades(data) +
          renderForms() +
        '</div>' +
        '<div class="f41-col">' +
          renderThoughts(data) +
          renderOpenClaw(data) +
          renderRoomsWorkers(data) +
        '</div>' +
      '</div>'
    );
    attachHandlers(el);
  }

  function attachHandlers(root) {
    const ob = root.querySelector('#f41-open-btn');
    if (ob) ob.onclick = async function () {
      const inst = root.querySelector('#f41-open-instr').value;
      const dir = root.querySelector('#f41-open-dir').value;
      const units = parseInt(root.querySelector('#f41-open-units').value, 10);
      const reason = root.querySelector('#f41-open-reason').value.trim();
      const out = root.querySelector('#f41-action-result');
      if (!reason) { out.textContent = 'entry_reason is required'; return; }
      out.textContent = 'opening…';
      const r = await postJSON('/api/trading/oanda/floor41/open_trade', {
        instrument: inst, direction: dir, units: units, entry_reason: reason,
      });
      out.textContent = JSON.stringify(r).slice(0, 360);
      render();
    };
    root.querySelectorAll('.f41-close-btn').forEach(function (btn) {
      btn.onclick = async function () {
        const tid = btn.getAttribute('data-tid');
        const reason = prompt('close_reason for ' + tid + ':');
        if (!reason) return;
        const out = root.querySelector('#f41-action-result');
        if (out) out.textContent = 'closing ' + tid + '…';
        const r = await postJSON('/api/trading/oanda/floor41/close_trade', {
          trade_id: tid, close_reason: reason,
        });
        if (out) out.textContent = JSON.stringify(r).slice(0, 360);
        render();
      };
    });
  }

  function attach() {
    setInterval(render, POLL_MS);
    window.addEventListener('qsb:pick', function (e) {
      if (e && e.detail && e.detail.kind === 'floor') render();
    });
    setTimeout(render, 1200);
  }

  if (document.readyState === 'loading') {
    document.addEventListener('DOMContentLoaded', attach);
  } else {
    attach();
  }
  window.QSB_FLOOR41_OANDA = { render: render };
})();
