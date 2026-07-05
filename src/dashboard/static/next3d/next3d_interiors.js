/*
 * QSB Next3D — Floor Interior Panels
 * Phase: QSB_NEXTGEN_3D_DASHBOARD_GREENFIELD_REBUILD_V1
 *
 * Each major floor has a custom interior layout. Generic floors fall
 * back to a "rooms + workers" summary. Designed to look visually
 * different from the old cockpit — uses cards, gauges, tables, never
 * generic repeated boxes.
 */
(function () {
  'use strict';

  function esc(s) {
    if (s === null || s === undefined) return '';
    return String(s).replace(/&/g, '&amp;').replace(/</g, '&lt;').replace(/>/g, '&gt;');
  }

  function fmtNum(n, d) {
    if (n === null || n === undefined || isNaN(n)) return '—';
    return Number(n).toFixed(d || 2);
  }

  function pnlClass(n) {
    if (n > 0) return 'pos';
    if (n < 0) return 'neg';
    return '';
  }

  // ── Floor 55 Penthouse ───────────────────────────────────────────
  function renderPenthouse(state) {
    const ph = state.penthouse || {};
    const cmd = ph.command || {};
    const gauges = ph.gauges || [];
    const zones = ph.zones || [];
    const repair = ph.repair || [];
    if (!cmd && !gauges.length) {
      return '<div class="n3d-no-data">Penthouse state unavailable. Run python -m tower.qsb_penthouse</div>';
    }
    let gaugeHtml = '';
    gauges.forEach(function (g) {
      gaugeHtml += (
        '<div class="n3d-gauge ' + esc(g.status || 'ok') + '" title="' + esc(g.source) + '">' +
          '<div class="n3d-gauge-label">' + esc(g.label) + '</div>' +
          '<div class="n3d-gauge-value">' + esc(g.value) +
            (g.unit ? ' <span class="n3d-gauge-unit">' + esc(g.unit) + '</span>' : '') +
          '</div>' +
        '</div>'
      );
    });
    let zoneHtml = '';
    zones.slice(0, 12).forEach(function (z) {
      zoneHtml += (
        '<div class="n3d-room">' +
          '<span class="n3d-room-name">' + esc(z.name) + '</span> ' +
          '<span class="n3d-room-resp">· ' + esc(z.responsibility) + '</span>' +
        '</div>'
      );
    });
    let repairHtml = '';
    repair.forEach(function (r) {
      repairHtml += '<div class="n3d-room"><b>[' + esc(r.severity) + ']</b> ' +
        esc(r.issue) + '</div>';
    });
    return (
      '<div class="n3d-card" style="grid-column:span 2">' +
        '<h5>Kernel + Guardian gauges</h5>' +
        '<div style="display:grid;grid-template-columns:repeat(auto-fill,minmax(150px,1fr));gap:6px">' +
          gaugeHtml +
        '</div>' +
      '</div>' +
      '<div class="n3d-card"><h5>Zones (' + zones.length + ')</h5>' + zoneHtml + '</div>' +
      '<div class="n3d-card"><h5>Repair priority (' + repair.length + ')</h5>' + repairHtml + '</div>'
    );
  }

  // ── Floor 41 OANDA ───────────────────────────────────────────────
  function renderOANDA(state) {
    const o = state.floor41 || {};
    const acct = o.account || {};
    const pnl = o.pnl || {};
    const open = o.open_trades || [];
    const closed = o.closed_trades || [];
    const prices = o.prices || [];
    const thoughts = o.thoughts || [];

    let pricesHtml = '<table><thead><tr><th>instr</th><th>bid</th><th>ask</th><th>spread</th></tr></thead><tbody>';
    prices.forEach(function (p) {
      pricesHtml += '<tr>' +
        '<td>' + esc(p.instrument) + '</td>' +
        '<td>' + esc(p.bid) + '</td>' +
        '<td>' + esc(p.ask) + '</td>' +
        '<td>' + esc((p.spread_pips || 0).toFixed(2)) + ' p</td>' +
      '</tr>';
    });
    pricesHtml += '</tbody></table>';
    if (!prices.length) pricesHtml = '<div class="n3d-no-data">no quotes</div>';

    let openHtml = '<table><thead><tr><th>id</th><th>instr</th><th>dir</th><th>u</th><th>entry</th><th>mark</th><th>uPnL</th></tr></thead><tbody>';
    open.forEach(function (t) {
      const up = t.unrealized_pnl || 0;
      openHtml += '<tr>' +
        '<td>' + esc(t.trade_id) + '</td>' +
        '<td>' + esc(t.instrument) + '</td>' +
        '<td>' + esc(t.direction) + '</td>' +
        '<td>' + esc(t.units) + '</td>' +
        '<td>' + esc(t.entry_price) + '</td>' +
        '<td>' + esc(t.mark_price === null ? '—' : t.mark_price) + '</td>' +
        '<td class="n3d-row b ' + pnlClass(up) + '">' + fmtNum(up, 4) + '</td>' +
      '</tr>';
    });
    openHtml += '</tbody></table>';
    if (!open.length) openHtml = '<div class="n3d-no-data">no open paper trades</div>';

    let closedHtml = '<table><thead><tr><th>id</th><th>instr</th><th>entry</th><th>exit</th><th>pnl</th></tr></thead><tbody>';
    closed.slice(-8).reverse().forEach(function (c) {
      const p = c.pnl_amount || 0;
      closedHtml += '<tr>' +
        '<td>' + esc(c.trade_id) + '</td>' +
        '<td>' + esc(c.instrument) + '</td>' +
        '<td>' + esc(c.entry_price) + '</td>' +
        '<td>' + esc(c.exit_price) + '</td>' +
        '<td class="n3d-row b ' + pnlClass(p) + '">' + fmtNum(p, 4) + '</td>' +
      '</tr>';
    });
    closedHtml += '</tbody></table>';
    if (!closed.length) closedHtml = '<div class="n3d-no-data">no closed trades</div>';

    let thoughtHtml = '';
    thoughts.slice(-8).reverse().forEach(function (t) {
      thoughtHtml += '<div class="n3d-room">' +
        '<b>' + esc((t.worker_id || '').replace(/^f41_/, '')) + '</b>' +
        ' · ' + esc(t.topic) + ' · ' + esc(t.thought) +
      '</div>';
    });
    if (!thoughts.length) thoughtHtml = '<div class="n3d-no-data">no thoughts</div>';

    return (
      '<div class="n3d-card"><h5>Account · paper / practice</h5>' +
        '<div class="n3d-row"><span>account</span><b>' + esc(acct.account_id || '—') + '</b></div>' +
        '<div class="n3d-row"><span>balance</span><b>' + fmtNum(acct.balance, 2) + ' ' + esc(acct.currency || '') + '</b></div>' +
        '<div class="n3d-row"><span>NAV</span><b>' + fmtNum(acct.NAV, 2) + '</b></div>' +
        '<div class="n3d-row"><span>realized</span><b class="' + pnlClass(pnl.realized_pnl_total) + '">' + fmtNum(pnl.realized_pnl_total, 4) + '</b></div>' +
        '<div class="n3d-row"><span>unrealized</span><b class="' + pnlClass(pnl.unrealized_pnl_total) + '">' + fmtNum(pnl.unrealized_pnl_total, 4) + '</b></div>' +
        '<div class="n3d-row"><span>total</span><b class="' + pnlClass(pnl.total_pnl) + '">' + fmtNum(pnl.total_pnl, 4) + '</b></div>' +
      '</div>' +
      '<div class="n3d-card"><h5>Live prices · spreads</h5>' + pricesHtml + '</div>' +
      '<div class="n3d-card"><h5>Open trades</h5>' + openHtml + '</div>' +
      '<div class="n3d-card"><h5>Closed trades (last 8)</h5>' + closedHtml + '</div>' +
      '<div class="n3d-card" style="grid-column:span 2"><h5>Worker thoughts</h5>' + thoughtHtml + '</div>'
    );
  }

  // ── Floor 42 Binance ─────────────────────────────────────────────
  function renderBinance(state) {
    const b = state.floor42 || {};
    if (!b.ok) return '<div class="n3d-no-data">Floor 42 Binance interior unavailable</div>';
    const rooms = b.rooms || [];
    const workers = b.workers || [];
    const policy = b.policy || {};

    let roomsHtml = '';
    rooms.forEach(function (r) {
      const wkrs = workers.filter(function (w) { return w.room === r.name; });
      let wkrHtml = '';
      wkrs.forEach(function (w) {
        wkrHtml += '<span class="n3d-room-worker">' + esc((w.worker_id || '').replace(/^f42_/, '')) + '</span>';
      });
      roomsHtml += (
        '<div class="n3d-room">' +
          '<span class="n3d-room-name">' + esc(r.name) + '</span>' +
          '<div class="n3d-room-resp">' + esc(r.responsibility || '') + '</div>' +
          '<div class="n3d-room-workers">' + (wkrHtml || '<span class="n3d-no-data">no workers</span>') + '</div>' +
        '</div>'
      );
    });

    return (
      '<div class="n3d-card"><h5>Policy</h5>' +
        '<div class="n3d-row"><span>mode</span><b>' + esc(policy.mode) + '</b></div>' +
        '<div class="n3d-row"><span>placement</span><b>' + esc(policy.placement) + '</b></div>' +
        '<div class="n3d-row"><span>real money</span><b class="neg">OFF (locked)</b></div>' +
      '</div>' +
      '<div class="n3d-card"><h5>Workers at stations</h5>' +
        workers.map(function (w) {
          return '<div class="n3d-row"><span>' + esc(w.role) + '</span><b>' +
                 esc((w.worker_id || '').replace(/^f42_/, '')) + '</b></div>';
        }).join('') +
      '</div>' +
      '<div class="n3d-card" style="grid-column:span 2"><h5>Rooms (' + rooms.length + ')</h5>' +
        roomsHtml +
      '</div>'
    );
  }

  // ── Floor 43 Stocks ──────────────────────────────────────────────
  function renderStocks(state) {
    const s = state.floor43 || {};
    if (!s.ok) return '<div class="n3d-no-data">Floor 43 Stocks interior unavailable</div>';
    const rooms = s.rooms || [];
    const workers = s.workers || [];
    const policy = s.policy || {};
    const tel = s.telemetry || {};
    let quotesHtml = '<table><thead><tr><th>symbol</th><th>price</th></tr></thead><tbody>';
    (tel.quotes || []).forEach(function (q) {
      quotesHtml += '<tr><td>' + esc(q.symbol || q.S || q.ticker || '') + '</td>' +
        '<td>' + esc(q.last || q.close || q.price || '—') + '</td></tr>';
    });
    quotesHtml += '</tbody></table>';
    if (!(tel.quotes || []).length) quotesHtml = '<div class="n3d-no-data">no quotes</div>';

    let roomsHtml = '';
    rooms.forEach(function (r) {
      const wkrs = workers.filter(function (w) { return w.room === r.name; });
      let wkrHtml = '';
      wkrs.forEach(function (w) {
        wkrHtml += '<span class="n3d-room-worker">' + esc((w.worker_id || '').replace(/^f43_/, '')) + '</span>';
      });
      roomsHtml += (
        '<div class="n3d-room">' +
          '<span class="n3d-room-name">' + esc(r.name) + '</span>' +
          '<div class="n3d-room-resp">' + esc(r.responsibility || '') + '</div>' +
          '<div class="n3d-room-workers">' + (wkrHtml || '<span class="n3d-no-data">no workers</span>') + '</div>' +
        '</div>'
      );
    });

    return (
      '<div class="n3d-card"><h5>Stocks · paper preview only</h5>' +
        '<div class="n3d-row"><span>provider</span><b>' + esc(tel.provider || '—') + '</b></div>' +
        '<div class="n3d-row"><span>environment</span><b>' + esc(tel.environment || '—') + '</b></div>' +
        '<div class="n3d-row"><span>market</span><b>' + esc(tel.market_status || '—') + '</b></div>' +
        '<div class="n3d-row"><span>placement</span><b>' + esc(policy.placement) + '</b></div>' +
        '<div class="n3d-row"><span>real money</span><b class="neg">OFF (locked)</b></div>' +
      '</div>' +
      '<div class="n3d-card"><h5>Quotes (first 8)</h5>' + quotesHtml + '</div>' +
      '<div class="n3d-card" style="grid-column:span 2"><h5>Rooms (' + rooms.length + ')</h5>' + roomsHtml + '</div>'
    );
  }

  // ── Generic floor ────────────────────────────────────────────────
  function renderGeneric(floorNum, state) {
    const f = (state.floors || []).find(function (x) { return x.num === floorNum; });
    if (!f) return '<div class="n3d-no-data">No floor catalog entry for floor ' + floorNum + '.</div>';
    const cls = f.classes || {};
    let densityHtml = '';
    Object.keys(cls).forEach(function (k) {
      densityHtml += '<div class="n3d-row"><span>' + esc(k.replace(/_worker$/, '')) + '</span><b>' + esc(cls[k]) + '</b></div>';
    });
    if (!Object.keys(cls).length) densityHtml = '<div class="n3d-no-data">No worker density recorded for this floor</div>';
    return (
      '<div class="n3d-card"><h5>Floor summary</h5>' +
        '<div class="n3d-row"><span>category</span><b>' + esc(f.category) + '</b></div>' +
        '<div class="n3d-row"><span>worker total</span><b>' + esc(f.worker_total) + '</b></div>' +
        '<div class="n3d-row"><span>special</span><b>' + esc(f.special) + '</b></div>' +
      '</div>' +
      '<div class="n3d-card"><h5>Worker class breakdown</h5>' + densityHtml + '</div>' +
      '<div id="n3dFloorCardSlot" class="n3d-card n3d-floor-card-slot"><h5>Floor card</h5>' +
        '<div class="n3d-no-data">loading…</div></div>'
    );
  }

  // ── Async floor_card.json renderer ───────────────────────────────
  // Called from show() after the synchronous panel is in the DOM. Fetches
  // /api/floor_card/<n> and fills in the #n3dFloorCardSlot div.
  function renderFloorCardInto(floorNum) {
    const slot = document.getElementById('n3dFloorCardSlot');
    if (!slot) return;
    fetch('/api/floor_card/' + floorNum, { cache: 'no-store' })
      .then(function (r) { return r.ok ? r.json() : null; })
      .then(function (card) {
        if (!card) {
          slot.innerHTML = '<h5>Floor card</h5><div class="n3d-no-data">no card available</div>';
          return;
        }
        if (card._card_missing) {
          slot.innerHTML = '<h5>Floor card</h5>' +
            '<div class="n3d-no-data">no floor_card.json on disk for ' +
            esc(card._floor_dir || ('floor ' + floorNum)) + '</div>';
          return;
        }
        let html = '<h5>Floor card</h5>';
        // Header rows from card top level
        const headerFields = [
          ['department', card.department],
          ['zone', card.zone],
          ['archetype', card.archetype],
          ['staff_lead', card.staff_lead],
        ];
        headerFields.forEach(function (pair) {
          if (pair[1]) {
            html += '<div class="n3d-row"><span>' + esc(pair[0]) +
              '</span><b>' + esc(pair[1]) + '</b></div>';
          }
        });
        if (card.tour_blurb) {
          html += '<div class="n3d-row n3d-row-block"><span>tour</span><div class="n3d-blurb">' +
            esc(String(card.tour_blurb).slice(0, 360)) + '</div></div>';
        }
        // Live signals subsection
        const ls = card.live_signals;
        if (ls && typeof ls === 'object' && Object.keys(ls).length) {
          html += '</div><div class="n3d-card"><h5>Live signals</h5>';
          Object.keys(ls).slice(0, 12).forEach(function (k) {
            const v = ls[k];
            let display;
            if (v === null || v === undefined) display = '—';
            else if (typeof v === 'object') display = JSON.stringify(v).slice(0, 80);
            else display = String(v).slice(0, 80);
            html += '<div class="n3d-row"><span>' + esc(k) +
              '</span><b>' + esc(display) + '</b></div>';
          });
        }
        // Gate posture subsection
        const gp = card.gate_posture;
        if (gp && typeof gp === 'object' && Object.keys(gp).length) {
          html += '</div><div class="n3d-card"><h5>Gate posture</h5>';
          Object.keys(gp).forEach(function (k) {
            const v = gp[k];
            const sigil = v === true ? 'TRUE' : v === false ? 'FALSE' : esc(String(v));
            const cls = v === true ? 'n3d-flag-on' : v === false ? 'n3d-flag-off' : '';
            html += '<div class="n3d-row"><span>' + esc(k) +
              '</span><b class="' + cls + '">' + sigil + '</b></div>';
          });
        }
        slot.innerHTML = html;
      })
      .catch(function () {
        slot.innerHTML = '<h5>Floor card</h5><div class="n3d-no-data">network error</div>';
      });
  }
  // expose so the dispatcher can call after DOM is written
  window.__N3D_renderFloorCardInto = renderFloorCardInto;

  // ── Dispatcher ───────────────────────────────────────────────────
  function renderForFloor(floorNum, state) {
    if (floorNum === 55) return renderPenthouse(state);
    if (floorNum === 41) return renderOANDA(state);
    if (floorNum === 42) return renderBinance(state);
    if (floorNum === 43) return renderStocks(state);
    return renderGeneric(floorNum, state);
  }

  function build() {
    function show(floorNum, state) {
      const el = document.getElementById('n3dInteriorPanel');
      if (!el) return;
      if (floorNum === null) { el.hidden = true; el.innerHTML = ''; return; }
      const f = (state.floors || []).find(function (x) { return x.num === floorNum; });
      const title = f ? f.name : ('Floor ' + floorNum);
      el.hidden = false;
      el.innerHTML = (
        '<div class="n3d-interior-hdr">' +
          '<div>' +
            '<div class="n3d-interior-title">Floor ' + floorNum + ' · ' + esc(title) + '</div>' +
            '<div class="n3d-interior-sub">' +
              'workers ' + ((f && f.worker_total) || 0) +
              ' · category ' + ((f && f.category) || 'generic') +
            '</div>' +
          '</div>' +
          '<button class="n3d-interior-close" id="n3dInteriorCloseBtn">close ✕</button>' +
        '</div>' +
        '<div class="n3d-interior-grid">' +
          renderForFloor(floorNum, state) +
        '</div>'
      );
      const close = document.getElementById('n3dInteriorCloseBtn');
      if (close) close.addEventListener('click', function () { window.NEXT3D_APP && window.NEXT3D_APP.selectFloor(null); });
      // Kick off async floor_card.json fetch for the generic-path floors so
      // every floor surfaces its live_signals + gate_posture without bespoke
      // renderers. Hardcoded renderers (55/41/42/43) already cover their own.
      if (window.__N3D_renderFloorCardInto && [55, 41, 42, 43].indexOf(floorNum) === -1) {
        window.__N3D_renderFloorCardInto(floorNum);
      }
    }
    return { show: show };
  }

  window.NEXT3D_INTERIORS = { build: build };
})();
