/*
 * QSB Floor 43 Stocks — Dashboard Interior Panel
 * Phase: QSB_FLOOR_41_42_43_INTERCOM_AND_FLOOR_43_VISIBLE_V1
 *
 * Mirrors the Floor 42 Binance panel pattern. Renders when ?floor=43.
 */
(function () {
  'use strict';
  if (window.QSB_FLOOR43_STOCKS_INSTALLED) return;
  window.QSB_FLOOR43_STOCKS_INSTALLED = true;

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

  function ensurePanel() {
    let el = document.getElementById('qsbF43Stocks');
    if (el) return el;
    const stage = document.getElementById('stage') || document.body;
    el = document.createElement('div');
    el.id = 'qsbF43Stocks';
    el.className = 'qsb-f43-stocks';
    el.style.display = 'none';
    stage.appendChild(el);
    return el;
  }

  function visible() {
    const sel = window.QSB && window.QSB.selectedFloor;
    return sel === 43;
  }

  async function render() {
    const el = ensurePanel();
    if (!visible()) { el.style.display = 'none'; return; }
    el.style.display = 'block';
    const data = await fetchJSON('/api/trading/stocks/floor43/interior');
    if (!data || !data.ok) {
      el.innerHTML = (
        '<div class="f43-hdr"><div class="f43-hdr-title">FLOOR 43 · STOCK EXCHANGE FLOOR</div></div>' +
        '<div class="muted">Floor 43 interior unavailable. Run python3 -m tower.qsb_floor43_stocks</div>'
      );
      return;
    }
    const rooms = data.rooms || [];
    const workers = data.workers || [];
    const policy = data.policy || {};
    const tel = data.telemetry || {};
    let roomCards = '';
    rooms.forEach(function (r) {
      const inRoom = workers.filter(function (w) { return w.room === r.name; });
      let workerHtml = '';
      inRoom.forEach(function (w) {
        workerHtml += '<span class="f43-room-w" title="' + esc(w.station) + '">' +
                      esc((w.worker_id || '').replace(/^f43_/, '')) +
                      '</span>';
      });
      if (!workerHtml) workerHtml = '<span class="muted">no workers assigned</span>';
      roomCards += (
        '<div class="f43-room">' +
          '<b>' + esc(r.name) + '</b> · ' + esc(r.responsibility || '') +
          '<div class="f43-room-workers">' + workerHtml + '</div>' +
        '</div>'
      );
    });
    const summary = (
      '<div class="f43-card">' +
        '<h5>Floor Summary</h5>' +
        '<div>mode: <b>' + esc(policy.mode || 'paper_placement_unlocked') + '</b></div>' +
        '<div>placement: <b>' + esc(policy.placement || 'blocked_without_explicit_unlock') + '</b></div>' +
        '<div>provider: <b>' + esc(tel.provider || '—') + '</b></div>' +
        '<div>environment: <b>' + esc(tel.environment || '—') + '</b></div>' +
        '<div>market_status: <b>' + esc(tel.market_status || '—') + '</b></div>' +
        '<div>real-money: <b>OFF (locked)</b></div>' +
      '</div>'
    );
    const quotes = tel.quotes || [];
    let quotesHtml = '';
    if (quotes.length) {
      quotesHtml = '<table class="f43-tbl"><thead><tr><th>symbol</th><th>price</th></tr></thead><tbody>';
      quotes.forEach(function (q) {
        const sym = q.symbol || q.ticker || q.S || '';
        const px = q.last || q.close || q.price || q.lastTrade || '—';
        quotesHtml += '<tr><td>' + esc(sym) + '</td><td>' + esc(px) + '</td></tr>';
      });
      quotesHtml += '</tbody></table>';
    } else {
      quotesHtml = '<div class="muted">no quotes (data provider may be sleeping)</div>';
    }
    el.innerHTML = (
      '<div class="f43-hdr">' +
        '<div class="f43-hdr-title">FLOOR 43 · STOCK EXCHANGE FLOOR</div>' +
        '<div class="f43-hdr-mode">' + esc(rooms.length) + ' rooms · ' + esc(workers.length) + ' workers</div>' +
        '<div class="f43-hdr-locks">paper preview only · real-money locked</div>' +
      '</div>' +
      '<div class="f43-grid">' +
        '<div>' + summary +
          '<div class="f43-card"><h5>Quotes (first 8)</h5>' + quotesHtml + '</div>' +
          roomCards + '</div>' +
        '<div>' +
          '<div class="f43-card"><h5>Workers at stations</h5>' +
            workers.map(function (w) {
              return '<div class="f43-room"><b>' + esc(w.worker_id.replace(/^f43_/, '')) +
                      '</b> · ' + esc(w.role) + ' · station: ' + esc(w.station) + '</div>';
            }).join('') +
          '</div>' +
        '</div>' +
      '</div>'
    );
  }

  function attach() {
    setTimeout(render, 1500);
    setInterval(render, POLL_MS);
    window.addEventListener('qsb:pick', function () { render(); });
  }

  if (document.readyState === 'loading') {
    document.addEventListener('DOMContentLoaded', attach);
  } else { attach(); }
  window.QSB_FLOOR43_STOCKS = { render: render };
})();
