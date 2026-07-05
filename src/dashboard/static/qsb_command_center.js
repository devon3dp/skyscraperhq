/*
 * QSB Live Skyscraper Command Center — Frontend
 * Phase: QSB_LIVE_SKYSCRAPER_COMMAND_CENTER_REBUILD_V1
 *
 * Drives three additions to the cockpit:
 *
 *   1. Profit Command panel — reads /api/profit_command
 *   2. Workforce HR panel  — reads /api/workforce/{scorecards,rewards,
 *                                            discipline,promotions}
 *   3. Running Commentary  — header button + mode dropdown; speaks via
 *                            window.speechSynthesis using the text
 *                            returned by /api/narrator/{mode}
 *
 * Hard rules:
 *   * All fetches wrapped in try/catch — one panel failing must not
 *     break the rest of the cockpit.
 *   * No invented data. Empty arrays display "no live data" labels.
 *   * Narrator runs on browser SpeechSynthesis only.
 */
(function () {
  'use strict';

  if (window.QSB_COMMAND_CENTER_INSTALLED) return;
  window.QSB_COMMAND_CENTER_INSTALLED = true;

  const PROFIT_POLL_MS = 8000;
  const WORKFORCE_POLL_MS = 12000;
  const NARRATOR_POLL_MS = 22000;

  // ── Helpers ───────────────────────────────────────────────────────────
  function esc(s) {
    if (s === null || s === undefined) return '—';
    return String(s).replace(/&/g, '&amp;').replace(/</g, '&lt;').replace(/>/g, '&gt;');
  }
  function fmt(n, d) {
    if (n === null || n === undefined || isNaN(Number(n))) return '—';
    return Number(n).toFixed(d == null ? 2 : d);
  }
  function safe(name, fn) {
    return function () {
      try { return fn.apply(null, arguments); }
      catch (e) {
        if (window && window.console) console.warn('[qsb_command_center] ' + name + ': ' + (e && e.message));
        return null;
      }
    };
  }
  async function fetchJSON(url) {
    try {
      const r = await fetch(url + (url.indexOf('?') === -1 ? '?' : '&') + 't=' + Date.now(),
                             { cache: 'no-store' });
      if (!r.ok) throw new Error('HTTP ' + r.status);
      return await r.json();
    } catch (_) { return null; }
  }

  // ── Profit Command panel ──────────────────────────────────────────────
  function renderProfit(d) {
    if (!d || d.ok === false) {
      return '<div class="tagline err">Profit Command unavailable. Try Refresh.</div>';
    }
    const dept = d.best_department_by_contribution || {};
    let topRows = '';
    (d.top_workers || []).forEach(function (t) {
      topRows += '<div class="kv qsb-v2-small">' +
                  '<span>' + esc(t.name) + '</span>' +
                  '<span>+' + fmt(t.realized_pnl_contribution) + ' · pts ' + esc(t.reward_points) + '</span>' +
                '</div>';
    });
    let stratRows = '';
    (d.strategy_performance || []).slice(0, 5).forEach(function (s) {
      stratRows += '<div class="kv qsb-v2-small">' +
                    '<span>' + esc(s.strategy_id) + '</span>' +
                    '<span>' + fmt(s.realized_pnl) + ' (' + esc(s.closed_trades) + 'c/' + esc(s.open_trades) + 'o)</span>' +
                  '</div>';
    });
    let actionRows = '';
    (d.next_profit_focused_actions || []).forEach(function (a) {
      actionRows += '<li class="qsb-v2-small">' + esc(a) + '</li>';
    });

    return (
      '<div class="qsb-v2-note ok">Mission: ' + esc(d.mission) + '</div>' +
      '<div class="qsb-v2-section">' +
        '<h4>Trading State</h4>' +
        '<div class="kv"><span>mode</span><span><code>' + esc(d.trading_mode) + '</code></span></div>' +
        '<div class="kv qsb-v2-small"><span>gateway</span><span>' + esc(d.gateway_status) + '</span></div>' +
        '<div class="kv"><span>open / max</span><span>' + esc(d.open_trade_count) + ' / ' + esc(d.max_open_trades) + '</span></div>' +
        '<div class="kv"><span>remaining slots</span><span>' + esc(d.remaining_trade_slots) + '</span></div>' +
        '<div class="kv"><span>realized PnL</span><span class="ok">' + fmt(d.total_realized_pnl) + '</span></div>' +
        '<div class="kv"><span>closed trades / lessons</span><span>' + esc(d.closed_trade_count) + ' / ' + esc(d.lesson_count) + '</span></div>' +
        '<div class="kv"><span>real-money live</span><span class="warn">' + esc(d.real_money_live_trading_enabled) + '</span></div>' +
      '</div>' +
      '<div class="qsb-v2-section">' +
        '<h4>Best Department</h4>' +
        '<div class="kv"><span>department</span><span>' + esc(dept.department || '—') + '</span></div>' +
        '<div class="kv"><span>realized PnL</span><span>' + fmt(dept.realized_pnl) + '</span></div>' +
        '<div class="kv"><span>profitable trades</span><span>' + esc(dept.profitable_trades) + '</span></div>' +
        '<div class="kv"><span>active workers</span><span>' + esc(dept.active_workers) + '</span></div>' +
      '</div>' +
      '<div class="qsb-v2-section">' +
        '<h4>Top Workers</h4>' +
        (topRows || '<div class="tagline qsb-v2-small">No paper-trade contributions yet.</div>') +
      '</div>' +
      '<div class="qsb-v2-section">' +
        '<h4>Strategy Performance</h4>' +
        (stratRows || '<div class="tagline qsb-v2-small">No strategy contributions yet.</div>') +
      '</div>' +
      '<div class="qsb-v2-section">' +
        '<h4>Next Profit Actions</h4>' +
        '<ol style="margin:0 0 0 18px;">' + actionRows + '</ol>' +
      '</div>'
    );
  }

  async function refreshProfit() {
    const body = document.getElementById('profitBody');
    if (!body) return;
    body.innerHTML = '<div class="tagline">Profit Command — loading…</div>';
    const d = await fetchJSON('/api/profit_command');
    try { body.innerHTML = renderProfit(d); }
    catch (_) { body.innerHTML = '<div class="tagline err">Profit Command render failed.</div>'; }
  }

  async function rebuildAndRefreshAll() {
    try { await fetch('/api/dashboard/command_center_refresh', { method: 'POST' }); } catch (_) {}
    refreshProfit();
    refreshWorkforce();
  }

  // ── Workforce HR panel ────────────────────────────────────────────────
  function renderWorkforce(scs, rewards, discipline, promotions) {
    if (!scs || scs.ok === false) {
      return '<div class="tagline err">Workforce data unavailable.</div>';
    }
    const total = scs.total_scorecards || (scs.scorecards || []).length;
    const rankCounts = (promotions && promotions.by_rank_counts) || {};
    let rankRows = '';
    Object.keys(rankCounts).forEach(function (k) {
      rankRows += '<div class="kv qsb-v2-small"><span>' + esc(k) + '</span><span>' + esc(rankCounts[k]) + '</span></div>';
    });

    let awardRows = '';
    ((rewards && rewards.rewards) || []).forEach(function (a) {
      const nom = a.nominee;
      awardRows += '<div class="kv qsb-v2-small">' +
                    '<span>' + esc(a.award) + '</span>' +
                    '<span>' + (nom ? esc(nom.name) : 'no nominee yet') + '</span>' +
                  '</div>';
    });

    const onWarn = discipline && discipline.total_on_warning || 0;
    const restricted = discipline && discipline.total_restricted || 0;
    const suspended = discipline && discipline.total_suspended || 0;

    // Top 8 highest reward points
    const top = (scs.scorecards || []).slice().sort(function (a, b) {
      return (b.reward_points || 0) - (a.reward_points || 0);
    }).slice(0, 8);
    let topRows = '';
    top.forEach(function (s) {
      topRows += '<div class="kv qsb-v2-small">' +
                  '<span>' + esc(s.name) + '</span>' +
                  '<span>' + esc(s.rank) + ' · pts ' + esc(s.reward_points) +
                    ' · strikes ' + esc(s.strikes) + '</span>' +
                '</div>';
    });

    return (
      '<div class="qsb-v2-section">' +
        '<h4>Workforce Summary</h4>' +
        '<div class="kv"><span>total scorecards</span><span>' + esc(total) + '</span></div>' +
        '<div class="kv"><span>eligible for promotion</span><span class="ok">' + esc(promotions && promotions.total_eligible_now) + '</span></div>' +
        '<div class="kv"><span>on warning</span><span class="' + (onWarn ? 'warn' : '') + '">' + esc(onWarn) + '</span></div>' +
        '<div class="kv"><span>restricted</span><span class="' + (restricted ? 'warn' : '') + '">' + esc(restricted) + '</span></div>' +
        '<div class="kv"><span>suspended</span><span class="' + (suspended ? 'err' : '') + '">' + esc(suspended) + '</span></div>' +
      '</div>' +
      '<div class="qsb-v2-section">' +
        '<h4>Ranks</h4>' + rankRows +
      '</div>' +
      '<div class="qsb-v2-section">' +
        '<h4>Rewards / Awards</h4>' + (awardRows || '<div class="tagline qsb-v2-small">no awards active</div>') +
      '</div>' +
      '<div class="qsb-v2-section">' +
        '<h4>Top 8 by Reward Points</h4>' +
        (topRows || '<div class="tagline qsb-v2-small">no points awarded yet</div>') +
      '</div>' +
      '<div class="qsb-v2-section">' +
        '<h4>Discipline Policy</h4>' +
        '<div class="qsb-v2-small">' +
          'Strike 1: warning + retraining · Strike 2: restricted duties / demotion review · Strike 3: suspended.<br>' +
          'Workers are <b>never</b> struck for paper losses when rules were followed. Losses become lessons, not strikes.<br>' +
          'Redemption: complete retraining task → 3 clean reports → senior worker review → restored confidence score.' +
        '</div>' +
      '</div>' +
      '<div class="qsb-v2-actions">' +
        '<button class="mini-btn" id="workforceRebuildBtn">Rebuild Workforce</button>' +
      '</div>'
    );
  }

  async function refreshWorkforce() {
    const body = document.getElementById('workforceBody');
    if (!body) return;
    body.innerHTML = '<div class="tagline">Workforce HR — loading…</div>';
    const [scs, rewards, discipline, promotions] = await Promise.all([
      fetchJSON('/api/workforce/scorecards'),
      fetchJSON('/api/workforce/rewards'),
      fetchJSON('/api/workforce/discipline'),
      fetchJSON('/api/workforce/promotions'),
    ]);
    try { body.innerHTML = renderWorkforce(scs, rewards, discipline, promotions); }
    catch (_) { body.innerHTML = '<div class="tagline err">Workforce render failed.</div>'; }
    const reb = document.getElementById('workforceRebuildBtn');
    if (reb) reb.addEventListener('click', rebuildAndRefreshAll);
  }

  // ── Running Commentary (browser speechSynthesis) ──────────────────────
  let narratorEnabled = false;
  let narratorMode = 'tower';
  let narratorTimer = null;
  let lastSpokenText = '';

  function pickVoice() {
    if (!window.speechSynthesis) return null;
    const voices = window.speechSynthesis.getVoices() || [];
    return voices.find(function (v) { return /en[-_]US/i.test(v.lang); })
        || voices.find(function (v) { return /English/i.test(v.name); })
        || voices[0] || null;
  }

  function speak(text) {
    if (!window.speechSynthesis) return;
    if (!text || text === lastSpokenText) return;
    lastSpokenText = text;
    window.speechSynthesis.cancel();
    const u = new SpeechSynthesisUtterance(text);
    const v = pickVoice();
    if (v) u.voice = v;
    u.rate = 1.0; u.pitch = 1.0; u.volume = 0.95; u.lang = 'en-US';
    try { window.speechSynthesis.speak(u); } catch (_) {}
  }

  async function fetchNarrationFor(mode) {
    let url = '/api/narrator/tower';
    if (mode === 'profit')          url = '/api/narrator/profit';
    else if (mode === 'openclaw')   url = '/api/narrator/openclaw';
    else if (mode === 'kernel')     url = '/api/narrator/kernel';
    else if (mode === 'critical')   url = '/api/narrator/critical';
    else if (mode === 'selected_floor') {
      // V1 default policy: user pick wins; otherwise OpenClaw current_floor.
      let fid = (window.QSB && window.QSB.selectedFloor);
      if (!fid) {
        try {
          const pol = await fetchJSON('/api/telemetry/selected_floor_default');
          fid = (pol && pol.default_floor) || 53;
        } catch (_) { fid = 53; }
      }
      url = '/api/narrator/floor/' + encodeURIComponent(fid);
    }
    else if (mode === 'worker') {
      const wid = (window.QSB && window.QSB.selectedWorker) || '';
      if (!wid) return null;
      url = '/api/narrator/worker/' + encodeURIComponent(wid);
    }
    return await fetchJSON(url);
  }

  async function narratorTick() {
    if (!narratorEnabled || narratorMode === 'off') return;
    const d = await fetchNarrationFor(narratorMode);
    if (d && d.text) speak(d.text);
  }

  function setNarratorEnabled(on) {
    narratorEnabled = !!on;
    const btn = document.getElementById('btnNarrator');
    if (btn) {
      btn.dataset.on = on ? '1' : '0';
      btn.textContent = on ? '🎙 Commentary: On' : '🎙 Commentary: Off';
    }
    if (on) {
      narratorTick();
      if (!narratorTimer) narratorTimer = setInterval(narratorTick, NARRATOR_POLL_MS);
    } else {
      if (narratorTimer) { clearInterval(narratorTimer); narratorTimer = null; }
      if (window.speechSynthesis) window.speechSynthesis.cancel();
    }
  }

  function setNarratorMode(mode) {
    narratorMode = mode || 'tower';
    if (narratorMode === 'off') {
      setNarratorEnabled(false);
    } else if (narratorEnabled) {
      lastSpokenText = '';
      narratorTick();
    }
  }

  // ── Wiring ────────────────────────────────────────────────────────────
  const safeRefreshProfit    = safe('refreshProfit',    refreshProfit);
  const safeRefreshWorkforce = safe('refreshWorkforce', refreshWorkforce);
  const safeNarratorTick     = safe('narratorTick',     narratorTick);

  function attach() {
    const tabs = document.querySelectorAll('#rightTabs button');
    tabs.forEach(function (b) {
      const tab = b.getAttribute('data-tab');
      if (tab === 'profit') {
        b.addEventListener('click', function () { try { refreshProfit(); } catch (_) {} });
      }
      if (tab === 'workforce') {
        b.addEventListener('click', function () { try { refreshWorkforce(); } catch (_) {} });
      }
    });
    const pBtn = document.getElementById('profitRefreshBtn');
    if (pBtn) pBtn.addEventListener('click', function () { try { refreshProfit(); } catch (_) {} });
    const pNarr = document.getElementById('profitNarrateBtn');
    if (pNarr) pNarr.addEventListener('click', async function () {
      const d = await fetchJSON('/api/narrator/profit');
      if (d && d.text) speak(d.text);
    });
    const wBtn = document.getElementById('workforceRefreshBtn');
    if (wBtn) wBtn.addEventListener('click', function () { try { refreshWorkforce(); } catch (_) {} });

    const nBtn = document.getElementById('btnNarrator');
    if (nBtn) nBtn.addEventListener('click', function () {
      setNarratorEnabled(!narratorEnabled);
    });
    const nMode = document.getElementById('narratorMode');
    if (nMode) {
      nMode.addEventListener('change', function () { setNarratorMode(nMode.value); });
    }

    // Track selected floor (set by the cockpit's onPick handlers).
    window.addEventListener('qsb:pick', function (e) {
      const p = e && e.detail;
      if (!p) return;
      if (p.kind === 'floor') (window.QSB = window.QSB || {}).selectedFloor = p.number;
      if (p.kind === 'worker') (window.QSB = window.QSB || {}).selectedWorker = p.id;
      if (narratorEnabled && (narratorMode === 'selected_floor' || narratorMode === 'worker')) {
        lastSpokenText = '';
        safeNarratorTick();
      }
      // Mark "no live data for this floor" inside the floor inspector
      // header when the V3 telemetry flags the floor as empty.
      if (p.kind === 'floor') {
        setTimeout(function () {
          try {
            const telemetry = (window.QSB_V3 && window.QSB_V3.lastTelemetry()) || null;
            if (!telemetry) return;
            const missing = (telemetry.missing_data_flags || []).some(function (f) {
              return f.floor === p.number;
            });
            // The cockpit's floor window renders into a window with a
            // floor-window class. Find the most recently opened header.
            const headers = document.querySelectorAll('.qwin .qwin-hdr');
            if (!headers.length) return;
            const last = headers[headers.length - 1];
            const existing = last.querySelector('.qsb-cc-no-live-data');
            if (missing && !existing) {
              const tag = document.createElement('span');
              tag.className = 'qsb-cc-no-live-data';
              tag.textContent = 'No live data for this floor';
              last.appendChild(tag);
            } else if (!missing && existing) {
              existing.remove();
            }
          } catch (_) {}
        }, 350);
      }
    });

    // Initial loads
    setTimeout(safeRefreshProfit,    1400);
    setTimeout(safeRefreshWorkforce, 1800);
    setInterval(safeRefreshProfit,    PROFIT_POLL_MS);
    setInterval(safeRefreshWorkforce, WORKFORCE_POLL_MS);
  }

  function safeAttach() {
    try { attach(); } catch (e) {
      if (window && window.console) console.warn('[qsb_command_center] attach failed:', e && e.message);
    }
  }

  if (document.readyState === 'loading') {
    document.addEventListener('DOMContentLoaded', safeAttach);
  } else {
    safeAttach();
  }

  window.QSB_COMMAND_CENTER = {
    refreshProfit:    safeRefreshProfit,
    refreshWorkforce: safeRefreshWorkforce,
    setNarratorMode:  setNarratorMode,
    setNarratorEnabled: setNarratorEnabled,
    speak: speak,
  };
})();
