// QSB Tower V1.3 — cockpit.js (V2)
// Phase: QSB_TOWER_3D_COCKPIT_VISUAL_REFINEMENT_V2
//
// Orchestration: wires header pills, tabs, collapsibles, focus/layout/reset
// buttons, debug strip, sound + speech toggles, floating windows
// (kernel chat, lock detail, worker detail, floor detail, OANDA/Binance/
// AirLLM/OpenClaw/strategy/ledger details), and 3D scene click handlers.

(function () {
  'use strict';

  const LOCK_LABELS = [
    ['live_trading_enabled',                'Live Trading'],
    ['order_execution_enabled',             'Order Execution'],
    ['practice_order_execution_enabled',    'Practice Orders'],
    ['binance_order_execution_enabled',     'Binance Orders'],
    ['binance_live_trading_enabled',        'Binance Live'],
    ['stock_order_execution_enabled',       'Stock Orders'],
    ['stock_live_trading_enabled',          'Stock Live Trading'],
    ['stock_paper_order_execution_enabled', 'Stock Paper Orders'],
    ['cross_market_execution_enabled',      'Cross-Market Execution'],
    ['worker_execution_enabled',            'Worker Execution'],
    ['provider_execution_enabled',          'Provider Exec'],
    ['external_provider_execution_enabled', 'External Provider Exec'],
    ['openclaw_execution_enabled',          'OpenClaw Exec'],
    ['openclaw_real_tool_execution_enabled','OpenClaw Real Tools'],
    ['autonomous_dispatch_enabled',         'Autonomous Dispatch'],
    ['live_dispatch_enabled',               'Live Dispatch'],
    ['direct_provider_access',              'Direct Provider Access'],
  ];

  const FLOOR_DETAIL = {
    23: 'AirLLM Big Model Chamber',
    30: 'Permissions / Risk',
    31: 'Audit / Ledger',
    37: 'Simulation Labs',
    38: 'Sandbox Operations',
    41: 'OANDA Trading Floor',
    42: 'Binance Trading Floor',
    43: 'Stock Exchange Trading Floor',
    53: 'Tower Command (Penthouse)',
  };

  function el(id) { return document.getElementById(id); }
  function qsa(sel, root) { return Array.from((root || document).querySelectorAll(sel)); }
  function esc(s) {
    return String(s == null ? '' : s).replace(/[&<>"']/g, (c) =>
      ({ '&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;' }[c]));
  }
  function fmtNum(n, d = 2) { if (n == null || Number.isNaN(+n)) return '—'; return (+n).toFixed(d); }
  function fmtPips(n) { return n == null ? '—' : (+n).toFixed(1) + 'p'; }

  // ── header ────────────────────────────────────────────────────────────
  function renderHeader(state) {
    el('hdrPhase').textContent = 'dashboard build · ' + (state.phase ? String(state.phase).toLowerCase().replace(/_/g, ' ').slice(0, 60) : 'live');

    const k = state.kernel || {};
    const pKernel = el('pillKernel');
    pKernel.textContent = 'kernel ' + (k.activation_status || '—');
    pKernel.className = 'pill ' + (k.activation_status === 'active_local_only' ? 'ok' : 'warn');

    const lockTrue = state.lock_count_true || 0;
    const pLocks = el('pillLocks');
    pLocks.textContent = lockTrue === 0 ? 'locks 0 / 13 closed' : 'locks ' + lockTrue + ' / 13 OPEN';
    pLocks.className = 'pill ' + (lockTrue === 0 ? 'ok' : 'alert');

    const pkts = (state.packets || []).length;
    const pAuto = el('pillAuto');
    pAuto.textContent = 'autoloop ' + (pkts > 0 ? 'flowing' : 'idle');
    pAuto.className = 'pill ' + (pkts > 0 ? 'ok' : 'dim');

    const air = state.airllm_chamber || {};
    const pAir = el('pillAir');
    const advisory = air.airllm_big_model_chamber === 'installed_advisory_only' || !!air.advisory_only;
    pAir.textContent = 'airllm ' + (advisory ? 'advisory' : (air.status || 'unknown'));
    pAir.className = 'pill ' + (advisory ? 'dim' : 'warn');

    const banner = el('alertBanner');
    if (lockTrue > 0) {
      banner.textContent = '⚠ EXECUTION LOCK OPEN — ' + lockTrue + ' lock(s) reporting TRUE. Review immediately.';
      banner.classList.add('on');
    } else {
      banner.classList.remove('on');
    }
  }

  // ── kernel pane ───────────────────────────────────────────────────────
  function renderKernel(state) {
    const k = state.kernel || {};
    const rows = [
      ['Activation', k.activation_status || '—', k.activation_status === 'active_local_only' ? 'ok' : 'warn'],
      ['Source', k.active_kernel_source || '—', 'blue'],
      ['Installed', String(!!k.kernel_installed), k.kernel_installed ? 'ok' : 'warn'],
      ['Instantiated', String(!!k.QSBKernelCore_instantiated), k.QSBKernelCore_instantiated ? 'ok' : 'warn'],
      ['Local model', String(!!k.local_model_enabled), k.local_model_enabled ? 'ok' : 'warn'],
      ['Ollama inference', String(!!k.ollama_local_inference_enabled), k.ollama_local_inference_enabled ? 'ok' : 'warn'],
      ['External providers', String(!!k.external_providers_enabled), k.external_providers_enabled ? 'alert' : 'ok'],
      ['Kernel health', k.kernel_health || '—', k.kernel_health === 'healthy' ? 'ok' : 'warn'],
      ['Kernel chat', k.kernel_chat_health || '—', k.kernel_chat_health === 'healthy' ? 'ok' : 'warn'],
    ];
    el('kernelBody').innerHTML = rows.map(([key, val, cls]) =>
      `<div class="kv"><span class="k">${esc(key)}</span><span class="v ${esc(cls)}">${esc(val)}</span></div>`
    ).join('');
    el('kernelSub').textContent = k.kernel_health || '—';
  }

  // ── locks ─────────────────────────────────────────────────────────────
  function renderLocks(state) {
    const locks = state.locks || {};
    el('locksSub').textContent = (state.lock_count_true || 0) + ' true';
    el('locksBody').innerHTML = '<div class="locks">' + LOCK_LABELS.map(([key, label]) => {
      const v = !!locks[key];
      return `<div class="lock ${v ? 'true' : ''}"><span class="lk">${esc(label)}</span><span class="lv">${v ? 'TRUE' : 'false'}</span></div>`;
    }).join('') + '</div>';
  }

  // ── counts ────────────────────────────────────────────────────────────
  function renderCounts(state) {
    const floors = (state.floors || []).length;
    const lifts = (state.lifts || []).length;
    // V1 worker truth: prefer canonical count for "Workers" tile; the
    // legacy state.workers[] view is labelled "showing X of Y" with the
    // SIM share called out.
    const truth = state.worker_truth_debug || {};
    const visibleLegacy = (state.workers || []).length;
    const canonical = truth.canonical_count || visibleLegacy;
    const simCount = truth.simulated_count || 0;
    const packets = (state.packets || []).length;
    const ledger = state.ledger ? (state.ledger.entry_count || 0) : 0;
    el('countsBody').innerHTML = `
      <div class="counts">
        <div class="count"><div class="cv">${floors}</div><div class="ck">Floors</div></div>
        <div class="count"><div class="cv">${lifts}</div><div class="ck">Lifts</div></div>
        <div class="count" title="${esc(truth.label_when_legacy_view_active || '')}">
          <div class="cv">${canonical}</div>
          <div class="ck">Workers <span class="wt-sub">canonical · ${visibleLegacy} legacy · ${simCount} SIM</span></div>
        </div>
        <div class="count"><div class="cv">${packets}</div><div class="ck">Packets</div></div>
        <div class="count"><div class="cv">${ledger}</div><div class="ck">Ledger</div></div>
        <div class="count"><div class="cv">${state.lock_count_true || 0}</div><div class="ck">Locks ON</div></div>
      </div>`;
    el('stageMeta').textContent =
      `${floors} floors · ${lifts} lifts · ${canonical} canonical workers (${visibleLegacy} visible, ${simCount} SIM) · ${packets} packets`;
  }

  // ── Command Suggestions (advisory only — never auto-runs anything) ────
  function renderSuggestions(state) {
    const host = el('suggestBody');
    if (!host) return;
    const s = state || {};
    const ra = s.recruitment_agency_floor45 || {};
    const recAg = s.recruitment_agency || {};
    const air = s.airllm_chamber || {};
    const stockReady = ((s.stock_exchange || {}).public_market_data_ready);
    const fxReady = ((s.oanda_floor || s.oanda || {}).pricing_ready);
    const cryptoReady = ((s.binance || {}).public_market_data_ready);
    const locks = +(s.lock_count_true || 0);
    const k = s.kernel || {};

    // Each suggestion is advisory only — clicking opens the relevant floor
    // window or chat. NOTHING here invokes execution endpoints.
    const sugg = [];
    if ((ra.candidate_count || 0) < 20) {
      sugg.push({ icon: '🧑‍🤝‍🧑', label: 'Recruit sandbox workers',
        hint: 'Open Floor 45 to recruit/advance sandbox candidates',
        floor: 45 });
    }
    sugg.push({ icon: '🧪', label: 'Run strategy backtest',
      hint: 'Open Floor 37 Simulation/Strategy', floor: 37 });
    sugg.push({ icon: '🛡', label: 'Review risk locks',
      hint: locks === 0 ? 'All locks closed — confirm Floor 30 still clean'
                       : ('Floor 30 — ' + locks + ' lock(s) reporting TRUE'),
      floor: 30 });
    sugg.push({ icon: '📈', label: 'Open Floor 37 Strategy',
      hint: 'Cross-market paper signals + correlations', floor: 37 });
    sugg.push({ icon: '🏢', label: 'Open Floor 45 Recruitment',
      hint: 'Worker Recruitment Agency · sandbox-only', floor: 45 });
    sugg.push({ icon: '💬', label: 'Ask Kernel for summary',
      hint: (k.activation_status === 'active_local_only'
              ? 'Kernel is active_local_only — chat dock is ready'
              : 'Kernel chat may be view-only'),
      action: 'kernel-chat' });
    sugg.push({ icon: '🧑‍🤝‍🧑', label: 'Chat with Wren (F47)',
      hint: 'Personal channel · claude_cli → local_kernel → floor_wisdom',
      action: 'f47-chat' });
    sugg.push({ icon: '📡', label: 'Live team status',
      hint: 'Watch the team work in real time · polls every 3s',
      action: 'team-live' });
    sugg.push({ icon: '👩‍💻', label: "Wren's Code Crew (F47, 100 workers)",
      hint: 'Live commentary · backlog · forgotten items · pair programmers',
      action: 'code-crew' });
    sugg.push({ icon: '🏗️', label: 'Live Dispatch · 12 teams working',
      hint: '/api/dispatch/live — see jobs given + jobs completed in real time',
      action: 'live-dispatch' });
    sugg.push({ icon: '🔍', label: 'Truth Audit · cross-dashboard mismatches',
      hint: 'every count traced to its source · F47.CODE crew sniffs drift',
      action: 'truth-audit' });
    sugg.push({ icon: '🚨', label: 'Fire drill — muster at car park',
      hint: 'POST /api/fire_drill/start · 2500+ workers head count',
      action: 'fire-drill' });
    sugg.push({ icon: '🏙️', label: 'Open 3D cockpit (Godot)',
      hint: 'Spawns or reports the live 3D tower window',
      action: 'cockpit-launch' });
    sugg.push({ icon: '🎯', label: 'Helm briefing (F53)',
      hint: 'Operational adviser · reads F44 + venues + tail',
      action: 'helm-briefing' });
    sugg.push({ icon: '🪞', label: 'Auger consult log (F47)',
      hint: "Wren's private adviser · recent second-opinion calls",
      action: 'auger-recent' });
    sugg.push({ icon: '🎥', label: 'Vision Feed',
      hint: 'F165 · Orbbec live MJPEG + person detections · 127.0.0.1 only',
      action: 'vision-feed' });
    sugg.push({ icon: '📊', label: 'Tick Pulse',
      hint: 'Live 5-min heartbeat indicators · last 50 ticks across all sub-tools',
      action: 'tick-pulse' });
    if (stockReady) sugg.push({ icon: '📊', label: 'Open Floor 43 Stocks',
      hint: 'Equity paper data ready', floor: 43 });
    if (fxReady)    sugg.push({ icon: '💱', label: 'Open Floor 41 OANDA',
      hint: 'OANDA practice pricing ready', floor: 41 });
    if (cryptoReady) sugg.push({ icon: '🪙', label: 'Open Floor 42 Binance',
      hint: 'Binance testnet market data ready', floor: 42 });
    if (air && air.registered) sugg.push({ icon: '🧠', label: 'Open Floor 23 AirLLM',
      hint: 'AirLLM advisory chamber online · advisory only', floor: 23 });

    host.innerHTML = sugg.map((x, idx) => `
      <button class="svc cmd-sugg" data-sugg="${idx}" title="${esc(x.hint)}"
              style="width:100%;text-align:left;display:flex;justify-content:space-between;gap:8px;padding:7px 9px;border:1px solid var(--border);background:rgba(15,30,60,.45);border-radius:6px;margin-bottom:4px;color:var(--text);cursor:pointer">
        <span class="name">${esc(x.icon)} ${esc(x.label)}</span>
        <span class="st dim" style="font-size:10px;color:var(--muted)">${esc(x.hint)}</span>
      </button>`).join('') +
      '<div class="tagline" style="margin-top:6px;color:var(--muted)">' +
      'Advisory only · clicking opens a window, never runs a command.</div>';

    qsa('button.cmd-sugg', host).forEach((btn) => {
      btn.addEventListener('click', () => {
        const i = parseInt(btn.dataset.sugg, 10);
        const x = sugg[i];
        if (!x) return;
        if (x.floor != null) openFloorWindow(x.floor);
        else if (x.action === 'kernel-chat') openKernelChatWindow(window.QSB.state);
        else if (x.action === 'f47-chat') openF47ChatWindow();
        else if (x.action === 'team-live') openTeamLiveWindow();
        else if (x.action === 'code-crew') openCodeCrewWindow();
        else if (x.action === 'live-dispatch') openLiveDispatchWindow();
        else if (x.action === 'truth-audit') openTruthAuditWindow();
        else if (x.action === 'helm-briefing') openHelmBriefingWindow();
        else if (x.action === 'auger-recent') openAugerRecentWindow();
        else if (x.action === 'vision-feed') openVisionWindow();
        else if (x.action === 'tick-pulse') { try { window.openTickPulseWindow && window.openTickPulseWindow(); } catch (_e) {} }
        else if (x.action === 'fire-drill') {
          if (!confirm('Start the fire drill?\\n\\nAll workers will be mustered at the car park.\\nAdvisory only · no actual evacuation.')) return;
          fetch('/api/fire_drill/start', {method: 'POST', headers: {'Content-Type':'application/json'}, body: '{}'})
            .then(r => r.json())
            .then(d => {
              if (d.ok) {
                const msg = '🚨 FIRE DRILL · ' + d.present_total + ' / ' + d.expected_total + ' present (' + d.percentage_present + '%). ' + (d.all_clear ? 'ALL CLEAR.' : 'Missing workers!');
                alert(msg);
                if (window.speechSynthesis) {
                  try { window.speechSynthesis.cancel(); } catch (e) {}
                  const u = new SpeechSynthesisUtterance('Fire drill all clear. ' + d.present_total + ' workers mustered at the car park.');
                  window.speechSynthesis.speak(u);
                }
              } else {
                alert('Drill failed: ' + (d.error || 'unknown'));
              }
            }).catch(e => alert('Network: ' + e.message));
        }
        else if (x.action === 'cockpit-launch') {
          fetch('/api/cockpit/launch', {method: 'POST'})
            .then((r) => r.json())
            .then((d) => {
              if (d.ok) alert('3D cockpit ' + d.status + ' (pid ' + d.pid + ')\n\nIf you don\'t see it, check other workspaces or alt-tab.');
              else alert('Cockpit launch failed: ' + (d.error || 'unknown'));
            }).catch((e) => alert('Network error: ' + e.message));
        }
      });
    });
  }

  function renderServices(state) {
    const svcs = state.services || {};
    const rows = Object.keys(svcs).map((key) => {
      const v = svcs[key] || {};
      const status = v.status || (v.healthy ? 'ok' : '—');
      let cls = 'dim';
      if (status === 'ok' || status === 'healthy') cls = 'ok';
      else if (status === 'warn' || status === 'stale') cls = 'warn';
      else if (status === 'down' || status === 'error') cls = 'bad';
      return `<div class="svc"><span class="name">${esc(key)}</span><span class="st ${cls}">${esc(status)}</span></div>`;
    });
    el('servicesBody').innerHTML = rows.length ? rows.join('') :
      '<div class="tagline">No service registry exposed via /api/unified.</div>';
  }

  // ── strategy / instruments ────────────────────────────────────────────
  function renderInstruments(state) {
    const list = state.instruments || [];
    if (!list.length) {
      el('instrumentsBody').innerHTML = '<div class="tagline">No paper instruments reported.</div>';
      return;
    }
    const rows = list.map((i, idx) => `
      <tr data-inst="${esc(i.instrument)}">
        <td><b>${esc(i.instrument)}</b></td>
        <td>${fmtNum(i.mid, 5)}</td>
        <td>${fmtPips(i.spread_pips)}</td>
        <td class="sig-${esc(i.paper_signal)}">${esc(i.paper_signal)}</td>
        <td class="sig-${esc(i.strategy_signal)}">${esc(i.strategy_signal)}</td>
        <td>${fmtPips(i.performance_delta_pips)}</td>
        <td>${esc(i.openclaw_recommendation || '—')}</td>
      </tr>`).join('');
    el('instrumentsBody').innerHTML = `
      <table class="instr-tbl">
        <thead><tr>
          <th>Inst</th><th>Mid</th><th>Spread</th><th>Paper</th><th>Strat</th><th>ΔPips</th><th>OpenClaw</th>
        </tr></thead>
        <tbody>${rows}</tbody>
      </table>
      <div class="tagline ok">paper-only · not financial advice · all execution locks closed</div>`;
    qsa('.instr-tbl tr[data-inst]').forEach((row) => {
      row.addEventListener('click', () => {
        const inst = row.dataset.inst;
        const data = (window.QSB.state.instruments || []).find((x) => x.instrument === inst);
        if (!data) return;
        window.QSB_WINDOWS.open('inst-' + inst, {
          title: inst + ' — strategy detail',
          width: 420, height: 320,
          render: (body) => {
            const ks = Object.keys(data);
            body.innerHTML = '<table class="detail-tbl">' +
              ks.map((k) => `<tr><td>${esc(k)}</td><td>${esc(JSON.stringify(data[k]))}</td></tr>`).join('') +
              '</table>';
          },
        });
      });
    });
  }

  // ── OANDA + Binance + AirLLM + OpenClaw panes ─────────────────────────
  function renderOanda(state) {
    const o = state.oanda_floor || state.oanda || {};
    const rows = [
      ['Department', o.department || 'OANDA Trading Floor'],
      ['Phase', o.phase || '—'],
      ['Environment', o.environment || 'practice'],
      ['Live trading', String(!!o.live_trading_enabled || !!(state.locks||{}).live_trading_enabled)],
      ['Order execution', String(!!o.order_execution_enabled || !!(state.locks||{}).order_execution_enabled)],
      ['Practice orders', String(!!o.practice_order_execution_enabled || !!(state.locks||{}).practice_order_execution_enabled)],
      ['Latest tick', o.latest_ts || '—'],
    ];
    el('oandaBody').innerHTML =
      rows.map(([k, v]) => `<div class="kv"><span class="k">${esc(k)}</span><span class="v">${esc(v)}</span></div>`).join('') +
      '<div class="tagline ok">paper-only · OANDA practice endpoint · execution locks closed</div>';
  }

  function renderBinance(state) {
    const b = state.binance || {};
    const sym = state.binance_instruments || [];
    el('binanceSub').textContent = b.environment || 'read-only';
    const rows = [
      ['Phase', b.phase || '—'],
      ['Environment', b.environment || '—'],
      ['Public market data', String(!!b.public_market_data_ready)],
      ['Account read', String(!!b.account_read_ready)],
      ['Order endpoints blocked', String(!!b.order_endpoints_blocked)],
      ['Order execution', String(!!b.binance_order_execution_enabled)],
      ['Live trading', String(!!b.binance_live_trading_enabled)],
      ['Paper-only', String(!!b.paper_only)],
      ['Symbols (top)', sym.slice(0, 3).map((s) => s.symbol || s.instrument || '').filter(Boolean).join(', ') || '—'],
    ];
    el('binanceBody').innerHTML =
      rows.map(([k, v]) => `<div class="kv"><span class="k">${esc(k)}</span><span class="v">${esc(v)}</span></div>`).join('') +
      '<div class="tagline ok">read-only · paper-only · not financial advice</div>';
  }

  function renderStocks(state) {
    const s = state.stock_exchange || {};
    const cp = s.credentials_present || {};
    el('stocksSub').textContent = (s.environment || 'paper') + ' · ' + (s.provider || 'alpaca');
    const sym = (state.stock_instruments || []).slice(0, 6);
    const rows = [
      ['Provider', s.provider || 'alpaca'],
      ['Environment', s.environment || 'paper'],
      ['Market data ready', String(!!s.public_market_data_ready)],
      ['Credentials present', String(!!(cp.api_key_present && cp.api_secret_present))],
      ['Account read', s.account_read_ready ? 'ready' : 'not ready'],
      ['Order execution', 'OFF'],
      ['Live trading', 'OFF'],
      ['Paper order execution', 'OFF'],
      ['Symbols', (s.default_symbols || []).join(', ') || '—'],
      ['Latest update', s.strategy_latest_ts || '—'],
      ['Data quality', s.data_quality || 'no_data'],
      ['Stale', String(!!s.stale)],
      ['Market status', s.market_status || 'unknown'],
    ];
    let symHtml = '';
    if (sym.length) {
      symHtml = '<table class="instr-tbl" style="margin-top:6px"><thead><tr>' +
        '<th>Sym</th><th>Mid</th><th>Spread%</th><th>Paper</th><th>Mom10%</th><th>Vol%</th><th>Status</th>' +
        '</tr></thead><tbody>' +
        sym.map((i) => `<tr>
          <td><b>${esc(i.instrument)}</b></td>
          <td>${fmtNum(i.mid, 2)}</td>
          <td>${fmtNum(i.spread_pips, 3)}</td>
          <td class="sig-${esc(i.paper_signal)}">${esc(i.paper_signal)}</td>
          <td>${fmtNum(i.momentum_10_pips, 2)}</td>
          <td>${fmtNum(i.performance_score, 2)}</td>
          <td>${esc(i.market_status || '—')}</td>
        </tr>`).join('') + '</tbody></table>';
    }
    el('stocksBody').innerHTML =
      rows.map(([k, v]) => `<div class="kv"><span class="k">${esc(k)}</span><span class="v">${esc(v)}</span></div>`).join('') +
      symHtml +
      '<div class="tagline ok">paper-only · stock orders OFF · paper stock orders OFF · live trading OFF · not financial advice</div>';
  }

  function renderCrossMarket(state) {
    const c = state.cross_market_bus || {};
    el('crossSub').textContent = (c.cross_market_labels || []).join(' · ').slice(0, 36) || 'no_cross_signal';
    const statusChip = (label, status) =>
      `<span class="mkt ${esc(status || 'unknown')}">${esc(label)}: ${esc(status || 'unknown')}</span>`;
    const labelChips = (c.cross_market_labels || []).map((l) => {
      const cls = l === 'risk_off_watch' ? 'alert'
                : l === 'risk_on_watch'  ? 'ok'
                : l === 'no_cross_signal'? '' : 'warn';
      return `<span class="label-chip ${cls}">${esc(l)}</span>`;
    }).join('');
    const rows = [
      ['Bus', c.bus || 'QSB Cross-Market Bus V1'],
      ['Updated', c.ts || '—'],
      ['OANDA',   statusChip('OANDA',   c.oanda_status)],
      ['Binance', statusChip('Binance', c.binance_status)],
      ['Stocks',  statusChip('Stocks',  c.stocks_status)],
      ['Packet count', String(c.packet_count || 0)],
      ['Correlation pairs', String(c.correlation_count || 0)],
    ];
    el('crossBody').innerHTML =
      rows.map(([k, v]) => `<div class="kv"><span class="k">${esc(k)}</span><span class="v">${v}</span></div>`).join('') +
      '<div style="margin-top:6px">' + (labelChips || '<span class="label-chip">no_cross_signal</span>') + '</div>' +
      '<div class="tagline ok">advisory only · execution_allowed=false · paper_only=true · not financial advice</div>';
  }

  function renderAirllm(state) {
    const air = state.airllm_chamber || {};
    const advisory = air.airllm_big_model_chamber === 'installed_advisory_only' || !!air.advisory_only;
    const versions = air.versions || {};
    const rows = [
      ['Chamber ID', air.chamber_id || '—'],
      ['Name', air.chamber_name || '—'],
      ['Status', air.airllm_big_model_chamber || (advisory ? 'installed_advisory_only' : 'unknown')],
      ['Path', air.path || '/vaults/ai/airllm_lab'],
      ['Venv', air.venv_path || '/vaults/ai/airllm_lab/.venv'],
      ['Env file', air.env_file || '/vaults/ai/airllm_env.sh'],
      ['AirLLM version', versions.airllm || air.airllm || '—'],
      ['Torch', versions.torch || '—'],
      ['Transformers', versions.transformers || '—'],
      ['Local Ollama', air.local_ollama || '—'],
    ];
    el('airllmBody').innerHTML =
      rows.map(([k, v]) => `<div class="kv"><span class="k">${esc(k)}</span><span class="v">${esc(v)}</span></div>`).join('') +
      '<div class="tagline">AirLLM is advisory-only on floor 23. Not wired into AutoLoop, trading, OpenClaw, workers, providers, or execution.</div>';
  }

  function renderOpenClaw(state) {
    const workers = (state.workers || []).filter((w) => /openclaw/i.test(w.name || w.id));
    const rows = workers.map((w) =>
      `<div class="worker-row openclaw" data-wid="${esc(w.id)}">
         <span class="wn">${esc(w.name)}</span>
         <span class="wf">floor ${esc(w.home_floor)}</span>
       </div>`);
    el('openclawBody').innerHTML = rows.join('') +
      '<div class="tagline">OpenClaw sandbox observers only · real tool execution disabled.</div>';
    qsa('#openclawBody .worker-row').forEach((r) => {
      r.addEventListener('click', () => openWorkerWindow(r.dataset.wid));
    });
  }

  function renderWorkers(state) {
    const list = state.workers || [];
    const truth = state.worker_truth_debug || {};
    const canonical = truth.canonical_count;
    // V1 truth: label "showing X of Y" instead of "N total".
    if (canonical && canonical !== list.length) {
      el('workersSub').textContent =
        'showing ' + list.length + ' of ' + canonical +
        ' canonical · ' + (truth.simulated_count || 0) + ' SIM seeds';
    } else {
      el('workersSub').textContent = list.length + ' visible';
    }
    el('workersBody').innerHTML = list.map((w) => {
      const cls = workerCssClass(w);
      const simBadge = w.is_simulation
        ? '<span class="wt-sim">SIM</span> '
        : '';
      return `<div class="worker-row ${cls}${w.is_simulation ? ' is-sim' : ''}" data-wid="${esc(w.id)}">
        <span class="wn">${simBadge}${esc(w.name || w.id)}</span>
        <span class="wf">${esc(w.home_floor)}</span></div>`;
    }).join('');
    qsa('#workersBody .worker-row').forEach((r) => {
      r.addEventListener('click', () => openWorkerWindow(r.dataset.wid));
    });
  }
  function workerCssClass(w) {
    const n = (w.name || w.id || '').toLowerCase();
    if (n.includes('openclaw')) return 'openclaw';
    if (n.includes('airllm'))   return 'airllm';
    if (n.includes('ledger'))   return 'ledger';
    if (n.includes('strategy') || n.includes('correlation')) return 'strategy';
    return '';
  }

  // ── ticker (bottom) ───────────────────────────────────────────────────
  // V17: filter pills, pause, click-to-expand JSON, slide-in animation,
  // pulse on the newest entry, pop-out detached window.
  const TICKER_STATE = {
    filters: new Set(['worker','strategy','ledger','openclaw','kernel','airllm','paper','packet']),
    paused: false,
    search: '',
    expanded: new Set(),     // row ids that are expanded
    knownIds: new Set(),     // signatures we've already rendered
    raw: [],                  // last-seen rows so detach can copy
  };

  function _rowSig(p) {
    return (p.ts || '') + '|' + (p.type || '') + '|' + (p.title || '').slice(0, 50);
  }
  function _ensureTickerToolbar() {
    let bar = document.getElementById('tickerToolbar');
    if (bar) return bar;
    const hdr = document.getElementById('bottomHdr');
    if (!hdr) return null;
    bar = document.createElement('span');
    bar.id = 'tickerToolbar';
    bar.className = 'tk-toolbar';
    bar.style.cssText = 'margin-left:auto';
    const pills = ['worker','strategy','ledger','openclaw','kernel','airllm','paper','packet'];
    const pillsHtml = pills.map((p) =>
      `<span class="tk-pill on" data-flt="${p}">${p}</span>`).join('');
    bar.innerHTML = `${pillsHtml}
      <input class="tk-search" id="tickerSearch" placeholder="filter…">
      <span class="tk-pill" id="tickerPause" title="Pause/resume">⏸</span>
      <span class="tk-pill" id="tickerPopout" title="Pop out to new window">⛶</span>`;
    // Insert before any existing .bottom-actions
    const actions = hdr.querySelector('.bottom-actions');
    if (actions) hdr.insertBefore(bar, actions); else hdr.appendChild(bar);
    // Wire pill toggles
    bar.querySelectorAll('.tk-pill[data-flt]').forEach((pill) => {
      pill.addEventListener('click', () => {
        const k = pill.dataset.flt;
        if (TICKER_STATE.filters.has(k)) {
          TICKER_STATE.filters.delete(k);
          pill.classList.remove('on'); pill.classList.add('off');
        } else {
          TICKER_STATE.filters.add(k);
          pill.classList.add('on'); pill.classList.remove('off');
        }
        _redrawFromRaw();
      });
    });
    bar.querySelector('#tickerSearch').addEventListener('input', (e) => {
      TICKER_STATE.search = (e.target.value || '').toLowerCase();
      _redrawFromRaw();
    });
    bar.querySelector('#tickerPause').addEventListener('click', () => {
      TICKER_STATE.paused = !TICKER_STATE.paused;
      const btn = bar.querySelector('#tickerPause');
      btn.textContent = TICKER_STATE.paused ? '▶' : '⏸';
      btn.title = TICKER_STATE.paused ? 'Resume' : 'Pause';
      document.body.classList.toggle('tk-paused', TICKER_STATE.paused);
    });
    bar.querySelector('#tickerPopout').addEventListener('click', _popOutTicker);
    return bar;
  }
  function _redrawFromRaw() { _renderTickerRows(TICKER_STATE.raw, false); }
  function _popOutTicker() {
    const popup = window.open('', 'qsb_ticker_detached',
      'width=900,height=600,scrollbars=yes,resizable=yes');
    if (!popup) return alert('Popup blocked. Allow popups for 127.0.0.1:8765.');
    const body = document.getElementById('tickerBody');
    popup.document.write(`<!doctype html><html><head><title>QSB Live Ticker (detached)</title>
      <style>
        body{background:#0a0f1c;color:#e6f0ff;font-family:system-ui,sans-serif;margin:0;padding:14px}
        h1{font-size:13px;color:#9ac;margin:0 0 10px;padding-bottom:6px;border-bottom:1px solid #234}
        .tk{display:grid;grid-template-columns:74px 84px 1fr 1.4fr;gap:10px;padding:3px 6px;
          border-radius:5px;background:rgba(10,20,40,.45);border:1px solid rgba(40,80,130,.3);margin-bottom:2px;font-size:11px}
        .tk .ts{color:#7c93b3}
        .tk .ty{font-weight:700}
      </style></head><body>
      <h1>QSB Live Ticker · detached · ${new Date().toLocaleTimeString()}</h1>
      <div id="content"></div></body></html>`);
    popup.document.close();
    popup.document.getElementById('content').innerHTML = body.innerHTML;
  }

  function _renderTickerRows(rows, markNew) {
    const out = [];
    const matchFilter = (kind) => TICKER_STATE.filters.has(kind);
    const matchSearch = (text) => !TICKER_STATE.search ||
      text.toLowerCase().indexOf(TICKER_STATE.search) >= 0;
    rows.forEach((r) => {
      const kind = r.kind;        // packet/worker/ledger/etc
      if (!matchFilter(kind)) return;
      const search_blob = `${r.ts}|${r.type}|${r.from}|${r.to}|${r.title}|${r.detail}|${r.raw||''}`;
      if (!matchSearch(search_blob)) return;
      const sig = _rowSig(r);
      const isNew = markNew && !TICKER_STATE.knownIds.has(sig);
      if (isNew) TICKER_STATE.knownIds.add(sig);
      const expanded = TICKER_STATE.expanded.has(sig);
      if (expanded) {
        out.push(`<div class="tk t-${esc(r.type || 'worker')} tk-expanded" data-sig="${esc(sig)}">
          <span class="ts">${esc((r.ts || '').slice(11, 19))}</span>
          <div><div><b>${esc(r.type || '—')}</b> · ${esc(r.from)} → ${esc(r.to)}</div>
            <div>${esc(r.title)} ${esc(r.detail)}</div>
            <pre>${esc(r.raw || JSON.stringify(r.full || r, null, 2))}</pre></div></div>`);
      } else {
        out.push(`<div class="tk t-${esc(r.type || 'worker')}${isNew ? ' tk-new' : ''}" data-sig="${esc(sig)}">
          <span class="ts">${esc((r.ts || '').slice(11, 19))}</span>
          <span class="ty">${esc(r.type || '—')}</span>
          <span class="fl">${esc(r.from)}${r.to ? ' → ' + esc(r.to) : ''}</span>
          <span class="tx">${esc(r.title)} ${esc(r.detail)}</span></div>`);
      }
    });
    const body = el('tickerBody');
    body.innerHTML = out.join('') ||
      '<div class="tagline">No matching ticker entries.</div>';
    if (markNew && rows.some((r) => !TICKER_STATE.knownIds.has(_rowSig(r)))) {
      body.classList.remove('tk-flash');
      void body.offsetWidth;  // force reflow
      body.classList.add('tk-flash');
    }
    // Wire click-to-expand
    body.querySelectorAll('.tk').forEach((row) => {
      row.addEventListener('click', () => {
        const sig = row.dataset.sig;
        if (!sig) return;
        if (TICKER_STATE.expanded.has(sig)) TICKER_STATE.expanded.delete(sig);
        else TICKER_STATE.expanded.add(sig);
        _redrawFromRaw();
      });
    });
  }

  function renderTicker(state) {
    if (TICKER_STATE.paused) return;
    _ensureTickerToolbar();
    const ledger = state.ledger || {};
    const entries = ledger.latest_entries || [];
    el('tickerSub').textContent = (ledger.entry_count || 0) + ' entries · last ' + (ledger.updated_ts || '—');

    // V18 — REAL events from /api/feed/activity (replaces template packets)
    fetch('/api/feed/activity', { cache: 'no-store' })
      .then(r => r.json())
      .then(feed => {
        const rows = [];
        (feed.events || []).slice(0, 18).forEach(ev => {
          rows.push({
            ts: ev.ts,
            type: ev.kind || 'event',
            kind: ev.kind || 'event',
            title: (ev.kind || 'event') + (ev.floor ? (' · F' + ev.floor) : ''),
            from: 'F' + (ev.floor || 'tower'),
            to: '',
            detail: ev.summary || '',
            full: ev,
          });
        });
        entries.slice(0, 12).forEach(e => {
          rows.push({
            ts: e.ts, type: 'ledger', kind: 'ledger',
            title: e.title || e.message || JSON.stringify(e).slice(0, 80),
            from: e.floor || 'ledger', to: '',
            detail: '', full: e,
          });
        });
        TICKER_STATE.raw = rows;
        _renderTickerRows(rows, true);
      })
      .catch(() => {
        // If feed unreachable, render only ledger entries (no template packets)
        const rows = entries.slice(0, 18).map(e => ({
          ts: e.ts, type: 'ledger', kind: 'ledger',
          title: e.title || e.message || JSON.stringify(e).slice(0, 80),
          from: e.floor || 'ledger', to: '',
          detail: '', full: e,
        }));
        TICKER_STATE.raw = rows;
        _renderTickerRows(rows, true);
      });
  }

  // ── debug strip ───────────────────────────────────────────────────────
  function renderDebug(diag) {
    const dw = el('dbgWebgl');
    dw.textContent = 'WebGL: ' + (diag.webgl ? (diag.webgl2 ? 'WebGL2 ✓' : 'WebGL1 ✓') : '✗');
    dw.className = 'dbg ' + (diag.webgl ? 'ok' : 'bad');
    const de = el('dbgEngine');
    de.textContent = 'Engine: ' + (diag.engine ? '✓' : '✗');
    de.className = 'dbg ' + (diag.engine ? 'ok' : 'bad');
    const dr = el('dbgRender');
    dr.textContent = 'Render: ' + (diag.render ? '✓' : '–');
    dr.className = 'dbg ' + (diag.render ? 'ok' : 'warn');
    el('dbgFps').textContent = 'FPS: ' + (diag.fps || '—');
    const derr = el('dbgErr');
    derr.textContent = diag.err ? ('err: ' + diag.err) : '';
    derr.className = 'dbg ' + (diag.err ? 'bad' : '');
  }

  // ── floating windows ──────────────────────────────────────────────────

  // F47 Ops Console — single-pane view of bench state.
  // Ross 2026-06-13: "we can operate from there" — F47 as joint ops base.
  function openF47OpsWindow() {
    const W = window.QSB_WINDOWS;
    W.open('f47-ops', {
      title: 'F47 · Wren Ops Console · bench state',
      width: 720, height: 580,
      render: (body) => {
        body.innerHTML =
          '<div class="kv"><span class="k">Channel</span><span class="v ok">F47 operations · advisory + bench</span></div>' +
          '<div class="kv"><span class="k">Auto-refresh</span><span class="v">' +
            '<label style="font-size:11px"><input type="checkbox" id="opsAuto" checked> every 15s</label> ' +
            '<button class="mini-btn" id="opsRefresh">↻ Refresh now</button> ' +
            '<button class="mini-btn" id="opsTick" title="Manually run audit+sigs+applier">▶ Run cycle</button>' +
          '</span></div>' +
          '<div id="opsBody" style="background:rgba(8,16,28,.7);min-height:380px;max-height:430px;overflow-y:auto;padding:8px;border:1px solid rgba(154,108,255,.3);border-radius:6px;margin-top:6px;font-family:monospace;font-size:11px;line-height:1.5;color:#cfd6e3">loading…</div>' +
          '<div style="margin-top:6px;color:var(--muted);font-size:11px">' +
            'bench: workers propose · sandbox runs · auto-sigs add wren_crew + team_assistants · applier writes when 3 sigs + green' +
          '</div>';
        const out = body.querySelector('#opsBody');
        const refreshBtn = body.querySelector('#opsRefresh');
        const tickBtn = body.querySelector('#opsTick');
        const autoCb = body.querySelector('#opsAuto');
        let timer = null;

        function fmtTs(ts) {
          if (!ts) return '—';
          return ts.slice(0, 19).replace('T', ' ');
        }
        function pill(text, color) {
          return '<span style="display:inline-block;padding:1px 6px;border-radius:8px;font-size:10px;background:' +
            color + ';color:#fff">' + text + '</span>';
        }

        function refresh() {
          fetch('/api/f47_ops', {method: 'POST', headers: {'Content-Type': 'application/json'}, body: '{}'})
            .then(r => r.json())
            .then(d => {
              if (!d.ok) { out.textContent = 'error: ' + (d.error || 'unknown'); return; }
              const hb = d.heartbeat_service === 'active' ?
                pill('heartbeat ' + d.heartbeat_service, '#3a8c4e') :
                pill('heartbeat ' + d.heartbeat_service, '#a44');
              const q = d.proposal_queue || {};
              const r = d.f47_roster || {};
              const gx = d.graphics_research || {};
              const recs = d.recent_f47_records || [];
              let html = '';
              html += '<div style="margin-bottom:8px">' + hb + ' ' +
                pill('roster ' + (r.team_size || 0), '#7a4ec4') + ' ' +
                pill('queue ' + (q.queue_depth || 0), '#c47a4e') + ' ' +
                pill('ready ' + (q.ready_count || 0), '#3a8c4e') + ' ' +
                pill('waiting ' + (q.waiting_count || 0), '#888') + '</div>';
              html += '<div style="margin-bottom:8px;color:#9a6cff">── F47 roster ──</div>';
              const rc = r.role_counts || {};
              const roles = Object.keys(rc).sort();
              html += roles.map(k => '  ' + k.padEnd(24) + ' ' + rc[k]).join('<br>');
              html += '<div style="margin:10px 0 6px 0;color:#9a6cff">── graphics crew ──</div>';
              html += '  runs: ' + (gx.runs || 0) + ' · screenshots analyzed: ' +
                (gx.analyzed_hashes ? gx.analyzed_hashes.length : 0) +
                ' · proposals written: ' + (gx.proposals_written || 0);
              html += '<div style="margin:10px 0 6px 0;color:#9a6cff">── recent F47 records (last ' + recs.length + ') ──</div>';
              recs.slice(0, 12).forEach(rec => {
                const kind = (rec.kind || '?').padEnd(28);
                html += '  <span style="color:#8aa0b8">' + fmtTs(rec.ts) + '</span>  <span style="color:#ff8c28">' + kind + '</span>';
                if (rec.kind === 'audit_crew_tick') html += ' track=' + rec.track + ' wrote=' + rec.proposals_written;
                else if (rec.kind === 'auto_sigs_tick') html += ' signed=' + (rec.actions ? rec.actions.auto_signed : '?');
                else if (rec.kind === 'applier_tick') html += ' applied=' + rec.applied_count;
                else if (rec.kind === 'graphics_research_tick') html += ' analyzed=' + rec.screenshots_analyzed;
                else if (rec.kind === 'heartbeat_tick') html += ' (5min)';
                html += '<br>';
              });
              out.innerHTML = html;
            })
            .catch(e => { out.textContent = 'fetch error: ' + e; });
        }

        function setAuto() {
          if (timer) { clearInterval(timer); timer = null; }
          if (autoCb.checked) timer = setInterval(refresh, 15000);
        }

        refresh();
        setAuto();
        refreshBtn.addEventListener('click', refresh);
        autoCb.addEventListener('change', setAuto);
        tickBtn.addEventListener('click', () => {
          tickBtn.disabled = true; tickBtn.textContent = '⟳ running…';
          fetch('/api/f47_ops/run_cycle', {method: 'POST', headers: {'Content-Type': 'application/json'}, body: '{}'})
            .then(r => r.json()).then(j => {
              tickBtn.textContent = '▶ Run cycle';
              tickBtn.disabled = false;
              refresh();
            })
            .catch(e => { tickBtn.textContent = 'err'; tickBtn.disabled = false; });
        });
      },
    });
  }

  // F47 chat room — personal channel Ross ↔ Wren.
  // Layered reply: claude_cli (Wren herself if logged in), local_kernel,
  // floor_wisdom. Distinct from the kernel chat (F55).
  function openF47ChatWindow() {
    const W = window.QSB_WINDOWS;
    W.open('f47-chat', {
      title: 'F47 · Wren · personal channel',
      width: 580, height: 500,
      render: (body) => {
        body.innerHTML = `
          <div class="kv"><span class="k">Channel</span><span class="v ok">personal · Ross ↔ Wren</span></div>
          <div class="kv"><span class="k">Voice</span><span class="v"><select id="f47Voice" style="background:rgba(8,16,28,.85);color:#fff;border:1px solid #456;border-radius:4px;padding:2px 4px;font-size:11px"><option value="">(pick a voice)</option></select> <label style="font-size:11px;margin-left:8px"><input type="checkbox" id="f47AutoTalk" checked> auto-speak Wren</label></span></div>
          <div class="kv"><span class="k">Show layers</span><span class="v"><label style="font-size:11px"><input type="checkbox" id="f47ShowWren" checked> 🟠 Wren</label> <label style="font-size:11px"><input type="checkbox" id="f47ShowKernel"> 🔵 kernel</label> <label style="font-size:11px"><input type="checkbox" id="f47ShowWisdom"> 🟡 wisdom</label></span></div>
          <div class="kv"><span class="k">History</span><span class="v" id="f47ChatHistMeta">loading…</span></div>
          <div id="f47ChatLog" class="chat-log" style="background:rgba(8,16,28,.7);min-height:220px;max-height:300px;overflow-y:auto;padding:8px;border:1px solid rgba(255,140,40,.3);border-radius:6px;margin-top:6px"></div>
          <div class="chat-row" style="margin-top:8px;display:flex;gap:6px">
            <input id="f47ChatInput" type="text" placeholder="speak to Wren…" style="flex:1">
            <button id="f47ChatMic" title="Hold to talk · uses browser SpeechRecognition" style="padding:6px 9px">🎤 Mic</button>
            <button id="f47ChatTalk" title="Re-speak the last Wren reply" style="padding:6px 9px">🔊 Talk</button>
            <button id="f47ChatSend">Send</button>
          </div>
          <div style="margin-top:6px;color:var(--muted);font-size:11px">
            advisory · every exchange persists · 🟠 = Wren (claude_cli) · 🔵 = kernel fallback · 🟡 = floor wisdom
          </div>`;
        const log    = body.querySelector('#f47ChatLog');
        const input  = body.querySelector('#f47ChatInput');
        const sendBt = body.querySelector('#f47ChatSend');
        const micBt  = body.querySelector('#f47ChatMic');
        const talkBt = body.querySelector('#f47ChatTalk');
        const histEl = body.querySelector('#f47ChatHistMeta');
        const voiceSel = body.querySelector('#f47Voice');
        const autoTalk = body.querySelector('#f47AutoTalk');
        const showWren = body.querySelector('#f47ShowWren');
        const showKernel = body.querySelector('#f47ShowKernel');
        const showWisdom = body.querySelector('#f47ShowWisdom');

        // ── voice picker setup (Riva first, browser SpeechSynthesis fallback) ──
        // The "🎙️ Wren (NVIDIA Riva)" entry is always at the top. If the
        // browser exposes SpeechSynthesisUtterance, those voices are listed
        // below as fallbacks. When Riva is unreachable (503), the talk path
        // silently falls back to the next-best browser voice.
        let lastWrenReply = '';
        let rivaAudioEl = null;

        function populateVoices() {
          voiceSel.innerHTML = '';
          // Always add the Riva option first
          const rivaOpt = document.createElement('option');
          rivaOpt.value = 'riva:English-US.Female-1';
          rivaOpt.textContent = '🎙️ Wren (NVIDIA Riva · neural)';
          voiceSel.appendChild(rivaOpt);

          const vs = window.speechSynthesis ? window.speechSynthesis.getVoices() : [];
          if (vs && vs.length) {
            // English voices first, then sorted
            const sorted = vs.slice().sort((a, b) => {
              const aEn = a.lang && a.lang.startsWith('en') ? 0 : 1;
              const bEn = b.lang && b.lang.startsWith('en') ? 0 : 1;
              return aEn - bEn || a.name.localeCompare(b.name);
            });
            sorted.forEach((v) => {
              const opt = document.createElement('option');
              opt.value = 'browser:' + v.name;
              opt.textContent = v.name + ' (' + (v.lang || '?') + ')';
              voiceSel.appendChild(opt);
            });
          }
          // Default to Riva — falls back automatically if not reachable
          voiceSel.value = 'riva:English-US.Female-1';
        }
        populateVoices();
        if (window.speechSynthesis) {
          window.speechSynthesis.onvoiceschanged = populateVoices;
        }

        function speakWithBrowser(text, browserVoiceName) {
          if (!window.speechSynthesis || !text) return;
          try { window.speechSynthesis.cancel(); } catch (e) {}
          const u = new SpeechSynthesisUtterance(text);
          if (browserVoiceName) {
            const v = window.speechSynthesis.getVoices().find((x) => x.name === browserVoiceName);
            if (v) u.voice = v;
          } else {
            // No specific browser voice picked — choose a sensible English female
            const all = window.speechSynthesis.getVoices();
            const pref = all.find((v) => /samantha|fiona|kate|en-GB|female|allison/i.test(v.name + ' ' + v.lang))
                       || all.find((v) => v.lang && v.lang.startsWith('en'));
            if (pref) u.voice = pref;
          }
          u.rate = 1.02;
          u.pitch = 1.0;
          window.speechSynthesis.speak(u);
        }

        async function speakWithRiva(text, rivaVoice) {
          // POST to /api/voice/wren; play returned audio blob.
          // On 503 or network error → fall back to browser TTS.
          try {
            const resp = await fetch('/api/voice/wren', {
              method: 'POST',
              headers: {'Content-Type': 'application/json'},
              body: JSON.stringify({text: text, voice: rivaVoice, language: 'en-US'}),
            });
            if (!resp.ok) {
              // 503 = Riva unreachable. Fall back silently.
              speakWithBrowser(text, null);
              return;
            }
            const blob = await resp.blob();
            const url = URL.createObjectURL(blob);
            if (rivaAudioEl) { try { rivaAudioEl.pause(); URL.revokeObjectURL(rivaAudioEl.src); } catch (e) {} }
            rivaAudioEl = new Audio(url);
            rivaAudioEl.play().catch(() => speakWithBrowser(text, null));
          } catch (e) {
            speakWithBrowser(text, null);
          }
        }

        function speakAsWren(text) {
          if (!text) return;
          const sel = voiceSel.value || 'riva:English-US.Female-1';
          if (sel.startsWith('riva:')) {
            speakWithRiva(text, sel.slice(5));
          } else if (sel.startsWith('browser:')) {
            speakWithBrowser(text, sel.slice(8));
          } else {
            // Legacy / unknown — try Riva first
            speakWithRiva(text, 'English-US.Female-1');
          }
        }
        talkBt.addEventListener('click', () => {
          if (lastWrenReply) speakAsWren(lastWrenReply);
          else speakAsWren('No reply to read yet — send Wren a message first.');
        });

        function appendRow(cls, text) {
          // Respect the layer-visibility toggles
          if (cls === 'claude_cli' && !showWren.checked) return;
          if (cls === 'local_kernel' && !showKernel.checked) return;
          if (cls === 'floor_wisdom' && !showWisdom.checked) return;
          const row = document.createElement('div');
          row.className = 'row ' + cls;
          row.textContent = text;
          row.style.padding = '4px 0';
          if (cls === 'user') { row.style.color = '#9ac'; }
          if (cls === 'claude_cli') { row.style.color = '#ff8b3a'; }
          if (cls === 'local_kernel') { row.style.color = '#80b2ff'; }
          if (cls === 'floor_wisdom') { row.style.color = '#ffd359'; }
          if (cls === 'system') { row.style.color = '#888'; row.style.fontStyle = 'italic'; }
          log.appendChild(row);
          log.scrollTop = log.scrollHeight;
        }

        // Load history first
        fetch('/api/f47_chat/history?tail=10', { cache: 'no-store' })
          .then((r) => r.ok ? r.json() : null)
          .then((j) => {
            if (j && Array.isArray(j.history) && j.history.length) {
              histEl.textContent = j.history.length + ' prior exchange(s)';
              j.history.forEach((h) => {
                if (h.you) appendRow('user', '> ' + h.you);
                if (h.claude_cli) appendRow('claude_cli', '── claude (cli) ──\n' + h.claude_cli);
                if (h.kernel) appendRow('local_kernel', '── local kernel ──\n' + (h.kernel || '').slice(0, 600));
                if (h.floor_wisdom) appendRow('floor_wisdom', '── F47 wisdom ──\n' + h.floor_wisdom);
              });
            } else {
              histEl.textContent = 'new conversation';
              appendRow('system', 'F47 Chat Room — personal channel. Type below or use the mic.');
            }
          })
          .catch(() => { histEl.textContent = 'history unreachable'; });

        function send() {
          const msg = (input.value || '').trim();
          if (!msg) return;
          appendRow('user', '> ' + msg);
          input.value = '';
          sendBt.disabled = true;
          fetch('/api/f47_chat', {
            method: 'POST',
            headers: {'Content-Type':'application/json'},
            body: JSON.stringify({message: msg, speak: false}),
          })
            .then((r) => r.json())
            .then((j) => {
              if (!j.ok) {
                appendRow('system', 'error: ' + (j.error || 'unknown'));
                return;
              }
              const ls = j.layers || {};
              if (ls.claude_cli) {
                appendRow('claude_cli', '── 🟠 Wren ──\n' + ls.claude_cli);
                lastWrenReply = ls.claude_cli;
                if (autoTalk.checked) speakAsWren(ls.claude_cli);
              }
              if (ls.local_kernel) appendRow('local_kernel', '── 🔵 kernel ──\n' + ls.local_kernel.slice(0, 600));
              if (ls.floor_wisdom) appendRow('floor_wisdom', '── 🟡 wisdom ──\n' + ls.floor_wisdom);
              if (!ls.claude_cli && !ls.local_kernel && !ls.floor_wisdom) {
                appendRow('system', '(no backend responded — your message was logged for the next Wren)');
              }
            })
            .catch((e) => appendRow('system', 'send failed: ' + e))
            .finally(() => { sendBt.disabled = false; input.focus(); });
        }

        sendBt.addEventListener('click', send);
        input.addEventListener('keydown', (e) => { if (e.key === 'Enter') send(); });

        // Mic — same pattern as kernel chat window
        let micOn = false; let recog = null;
        micBt.addEventListener('click', () => {
          const SR = window.SpeechRecognition || window.webkitSpeechRecognition;
          if (!SR) {
            appendRow('system', 'SpeechRecognition not available — Chrome/Edge required.');
            return;
          }
          if (micOn && recog) {
            try { recog.stop(); } catch (e) {}
            micOn = false; micBt.textContent = '🎤 Mic'; micBt.classList.remove('active');
            return;
          }
          recog = new SR();
          recog.continuous = false;
          recog.interimResults = false;
          recog.lang = navigator.language || 'en-US';
          recog.onresult = (ev) => {
            const txt = ev.results[0][0].transcript;
            input.value = txt;
            appendRow('system', '🎤 heard: ' + txt);
            send();
          };
          recog.onerror = (ev) => {
            appendRow('system', 'mic error: ' + (ev.error || 'unknown'));
            micOn = false; micBt.textContent = '🎤 Mic'; micBt.classList.remove('active');
          };
          recog.onend = () => {
            micOn = false; micBt.textContent = '🎤 Mic'; micBt.classList.remove('active');
          };
          try {
            recog.start();
            micOn = true; micBt.textContent = '🎙 Listening…'; micBt.classList.add('active');
            appendRow('system', '🎤 listening — speak now…');
          } catch (e) {
            appendRow('system', 'mic start failed: ' + e);
          }
        });

        input.focus();
      },
    });
  }

  // F165 Vision Feed — live MJPEG from the Orbbec vision daemon.
  // Daemon binds 127.0.0.1:8821 only (no LAN). Cross-origin from :8765
  // is fine for <img> tags; status polling uses fetch with no-store.
  // Advisory only · no recording · workers cannot drive the feed.
  function openVisionWindow() {
    const W = window.QSB_WINDOWS;
    const VISION_BASE = 'http://127.0.0.1:8821';
    W.open('vision-feed', {
      title: 'F165 — Vision Feed (Orbbec)',
      width: 540, height: 520,
      render: (body) => {
        body.innerHTML = `
          <div class="kv"><span class="k">Source</span><span class="v">Orbbec Astra Pro · ${VISION_BASE}</span></div>
          <div class="kv"><span class="k">Bind</span><span class="v ok">127.0.0.1 only · no LAN · no recording</span></div>
          <div style="display:flex;justify-content:center;margin:8px 0">
            <img id="visionStream" src="${VISION_BASE}/api/vision/stream"
                 width="480" height="360"
                 alt="Orbbec live feed"
                 style="width:480px;height:360px;border:1px solid #ffb347;border-radius:4px;background:#000;object-fit:contain">
          </div>
          <div class="kv">
            <span class="k">Status</span>
            <span class="v" id="visionStatusPill">
              <span id="visionDot" style="display:inline-block;width:10px;height:10px;border-radius:50%;background:#666;margin-right:6px;vertical-align:middle"></span>
              <span id="visionStatusText">connecting…</span>
            </span>
          </div>
          <div style="margin-top:8px;display:flex;gap:6px;align-items:center">
            <button id="visionSnapBtn" style="padding:6px 10px">📸 Snapshot</button>
            <button id="visionReloadBtn" style="padding:6px 10px" title="Reload the MJPEG stream">🔄 Reload stream</button>
            <span id="visionFpsBig" style="margin-left:auto;font-size:11px;color:var(--muted)">—</span>
          </div>
          <div style="margin-top:8px;color:var(--muted);font-size:11px">
            advisory only · 127.0.0.1 only · no recording
          </div>`;

        const dot      = body.querySelector('#visionDot');
        const txt      = body.querySelector('#visionStatusText');
        const fpsBig   = body.querySelector('#visionFpsBig');
        const snapBtn  = body.querySelector('#visionSnapBtn');
        const reloadBt = body.querySelector('#visionReloadBtn');
        const streamEl = body.querySelector('#visionStream');

        snapBtn.addEventListener('click', () => {
          window.open(VISION_BASE + '/api/vision/snapshot.jpg', '_blank');
        });
        reloadBt.addEventListener('click', () => {
          // Force the MJPEG connection to re-establish
          streamEl.src = VISION_BASE + '/api/vision/stream?t=' + Date.now();
        });

        let stopped = false;
        async function poll() {
          if (stopped) return;
          try {
            const r = await fetch(VISION_BASE + '/api/vision/status', {cache: 'no-store'});
            if (!r.ok) throw new Error('http ' + r.status);
            const j = await r.json();
            const open  = !!j.camera_open;
            const fps   = (typeof j.fps === 'number') ? j.fps.toFixed(1) : '?';
            const dets  = Array.isArray(j.detections) ? j.detections.length
                        : (typeof j.person_count === 'number' ? j.person_count : 0);
            dot.style.background = open ? '#3fcf5a' : '#cf3f3f';
            txt.textContent = 'fps · ' + fps + ' · detections: ' + dets;
            fpsBig.textContent = open ? ('camera ok · ' + fps + ' fps') : 'camera closed';
          } catch (e) {
            dot.style.background = '#cf3f3f';
            txt.textContent = 'vision daemon unreachable (' + (e.message || e) + ')';
            fpsBig.textContent = 'offline';
          }
        }
        poll();
        const iv = setInterval(poll, 3000);

        // QSB_WINDOWS exposes onclose for cleanup; if not present, fall back
        // to a MutationObserver on the window node. Best-effort either way.
        try {
          const win = body.closest('.qsb-window') || body.parentElement;
          if (win) {
            const mo = new MutationObserver(() => {
              if (!document.body.contains(win)) {
                stopped = true;
                clearInterval(iv);
                mo.disconnect();
              }
            });
            mo.observe(document.body, {childList: true, subtree: true});
          }
        } catch (e) { /* non-fatal */ }
      },
    });
  }

  // Shared TTS helper used by Helm + Auger. Tries Riva /api/voice/wren
  // first, falls back to browser SpeechSynthesis. Voice differs by adviser.
  function _speakAdvice(text, role) {
    if (!text) return;
    // Helm = deeper male; Auger = softer female
    const rivaVoice = role === 'helm' ? 'English-US.Male-1' : 'English-US.Female-1';
    fetch('/api/voice/wren', {
      method: 'POST', headers: {'Content-Type': 'application/json'},
      body: JSON.stringify({text: text.slice(0, 800), voice: rivaVoice, language: 'en-US'}),
    }).then((r) => {
      if (!r.ok) throw new Error('fallback');
      return r.blob();
    }).then((b) => {
      const url = URL.createObjectURL(b);
      new Audio(url).play();
    }).catch(() => {
      // Browser fallback
      if (!window.speechSynthesis) return;
      try { window.speechSynthesis.cancel(); } catch (e) {}
      const u = new SpeechSynthesisUtterance(text.slice(0, 800));
      const voices = window.speechSynthesis.getVoices();
      const pref = role === 'helm'
        ? (voices.find((v) => /male|alex|daniel|fred/i.test(v.name)) || voices.find((v) => v.lang && v.lang.startsWith('en')))
        : (voices.find((v) => /samantha|fiona|kate|en-GB|female|allison/i.test(v.name + ' ' + v.lang)) || voices.find((v) => v.lang && v.lang.startsWith('en')));
      if (pref) u.voice = pref;
      u.rate = role === 'helm' ? 0.97 : 1.02;
      u.pitch = role === 'helm' ? 0.85 : 1.05;
      window.speechSynthesis.speak(u);
    });
  }

  // Helm briefing — operational adviser. Reads F44 + venues + tail; POSTs
  // to /api/helm/briefing with optional focus. OpenAI-backed under the
  // existing provider consult budget ($1/day, $0.05/call).
  function openHelmBriefingWindow() {
    const W = window.QSB_WINDOWS;
    W.open('helm-briefing', {
      title: '🎯 Helm · F53 Tower Command adviser',
      width: 640, height: 540,
      render: (body) => {
        body.innerHTML = `
          <div class="kv"><span class="k">Adviser</span><span class="v ok">Helm · operational · OpenAI gpt-4o-mini</span></div>
          <div class="kv"><span class="k">Reads</span><span class="v">F44 PnL · venue state · strategy splits · sentinels · spend</span></div>
          <div class="kv"><span class="k">Last briefing</span><span class="v" id="hbWhen">—</span></div>
          <div class="kv"><span class="k">Voice</span><span class="v">
            <label style="font-size:11px"><input type="checkbox" id="hbSpeak" checked> 🔊 Helm speaks aloud</label>
            <button id="hbReplay" style="margin-left:8px;padding:3px 7px;font-size:11px">🔊 Replay last</button>
          </span></div>
          <div style="margin-top:8px;display:flex;gap:6px">
            <input id="hbFocus" type="text" placeholder="ask Helm a specific question (optional)…" style="flex:1">
            <button id="hbAsk" title="Pull a fresh briefing">Brief me</button>
          </div>
          <div id="hbStatus" style="margin-top:6px;font-size:11px;color:var(--muted)">click "Brief me" or type a question · advisory only</div>
          <div id="hbOut" style="margin-top:6px;background:rgba(8,16,28,.7);padding:10px;border:1px solid rgba(120,200,255,.3);border-radius:6px;min-height:240px;max-height:340px;overflow-y:auto;font-size:12px;line-height:1.5;color:var(--text);white-space:pre-wrap"></div>
        `;
        const askBt = body.querySelector('#hbAsk');
        const focus = body.querySelector('#hbFocus');
        const out = body.querySelector('#hbOut');
        const status = body.querySelector('#hbStatus');
        const whenEl = body.querySelector('#hbWhen');
        const speakChk = body.querySelector('#hbSpeak');
        const replayBt = body.querySelector('#hbReplay');
        let _lastHelm = '';
        async function askHelm() {
          const f = (focus.value || '').trim() || null;
          status.textContent = 'Helm is thinking…';
          askBt.disabled = true; askBt.textContent = '⌛';
          try {
            const r = await fetch('/api/helm/briefing', {
              method: 'POST', headers: {'Content-Type': 'application/json'},
              body: JSON.stringify({focus: f}),
            });
            const d = await r.json();
            if (d.ok) {
              out.textContent = d.briefing || '(empty briefing)';
              whenEl.textContent = (d.ts || '').slice(11, 19);
              status.textContent = 'spend today: $' + (d.state_summary?.spend_today ?? '?') + ' · ts ' + (d.ts || '?');
              _lastHelm = d.briefing || '';
              if (speakChk.checked && _lastHelm) _speakAdvice(_lastHelm, 'helm');
            } else {
              out.textContent = 'Helm error: ' + (d.error || 'unknown');
              status.textContent = '✗ failed';
            }
          } catch (e) {
            out.textContent = 'Network error: ' + e.message;
            status.textContent = '✗ network';
          } finally {
            askBt.disabled = false; askBt.textContent = 'Brief me';
          }
        }
        askBt.addEventListener('click', askHelm);
        focus.addEventListener('keydown', (e) => { if (e.key === 'Enter') askHelm(); });
        replayBt.addEventListener('click', () => { if (_lastHelm) _speakAdvice(_lastHelm, 'helm'); });
      },
    });
  }

  // Auger recent — Wren's private adviser. Shows the recent consult log.
  // Auger is invoked from inside Wren's modules (not exposed for direct chat
  // here — that's Wren's channel) but Ross can see what Auger has been
  // saying via this read-only panel.
  function openAugerRecentWindow() {
    const W = window.QSB_WINDOWS;
    W.open('auger-recent', {
      title: '🪞 Auger · Wren\'s private adviser · recent consults',
      width: 700, height: 520,
      render: (body) => {
        body.innerHTML = `
          <div class="kv"><span class="k">Adviser</span><span class="v ok">Auger · philosophical · DeepSeek chat</span></div>
          <div class="kv"><span class="k">Channel</span><span class="v">Wren only · not a Ross↔Auger chat</span></div>
          <div class="kv"><span class="k">Recent</span><span class="v" id="agCount">—</span></div>
          <div class="kv"><span class="k">Voice</span><span class="v">
            <label style="font-size:11px"><input type="checkbox" id="agSpeak" checked> 🔊 Auger speaks on explicit ask</label>
          </span></div>
          <div style="margin-top:6px;display:flex;gap:6px;align-items:center">
            <button id="agRefresh">⟳ refresh</button>
            <button id="agAsk" title="Ask Auger something explicitly">+ ask Auger (explicit)</button>
            <span id="agStatus" style="font-size:11px;color:var(--muted)">—</span>
          </div>
          <div id="agOut" style="margin-top:8px;background:rgba(8,16,28,.7);padding:8px;border:1px solid rgba(200,160,255,.3);border-radius:6px;max-height:320px;overflow-y:auto;font-size:12px"></div>
        `;
        const out = body.querySelector('#agOut');
        const cnt = body.querySelector('#agCount');
        const status = body.querySelector('#agStatus');
        async function loadRecent() {
          status.textContent = 'loading…';
          try {
            // Read directly from the registry via /api/registry passthrough
            const r = await fetch('/api/registry/qsb_auger_consults.jsonl');
            if (!r.ok) { out.textContent = '(no consults yet)'; cnt.textContent = '0'; status.textContent = ''; return; }
            const txt = await r.text();
            const lines = txt.split('\\n').filter(Boolean);
            cnt.textContent = lines.length + ' total';
            status.textContent = '✓';
            const rows = lines.slice(-12).reverse().map(line => {
              try {
                const d = JSON.parse(line);
                return `<div style="padding:6px;border-bottom:1px solid rgba(200,160,255,.15);margin-bottom:4px">
                  <div style="color:var(--muted);font-size:10.5px">${esc((d.ts||'').slice(11,19))} · reason: ${esc(d.reason||'')} · ${esc(d.provider||'')}/${esc(d.model||'')}</div>
                  <div style="color:#cce;margin-top:3px"><b>Q:</b> ${esc((d.question_head||'').slice(0,180))}</div>
                  <div style="color:#e8d8ff;margin-top:3px"><b>Auger:</b> ${esc((d.advice_head||'').slice(0,240))}</div>
                </div>`;
              } catch (e) { return ''; }
            }).join('');
            out.innerHTML = rows || '(no consults yet)';
          } catch (e) {
            out.textContent = 'error: ' + e.message;
            status.textContent = '✗';
          }
        }
        async function explicitAsk() {
          const q = prompt('Ask Auger (explicit):');
          if (!q) return;
          status.textContent = 'Auger thinking…';
          try {
            const r = await fetch('/api/auger/consult', {
              method: 'POST', headers: {'Content-Type': 'application/json'},
              body: JSON.stringify({question: q, reason: 'ross_explicit'}),
            });
            const d = await r.json();
            if (d.ok) { status.textContent = '✓ ' + (d.ts||'').slice(11,19); loadRecent(); }
            else { status.textContent = '✗ ' + (d.error || 'failed'); }
          } catch (e) { status.textContent = '✗ ' + e.message; }
        }
        body.querySelector('#agRefresh').addEventListener('click', loadRecent);
        body.querySelector('#agAsk').addEventListener('click', explicitAsk);
        loadRecent();
      },
    });
  }

  // Live team status — polls /api/team/live every 3 seconds. Lets Ross watch
  // the F47 + F37 workforce + cohort runs + governor decisions in real time.
  function openTeamLiveWindow() {
    const W = window.QSB_WINDOWS;
    W.open('team-live', {
      title: 'Team Live · F47 + F37 + activity tail',
      width: 720, height: 540,
      render: (body) => {
        body.innerHTML = `
          <div class="kv"><span class="k">Channel</span><span class="v ok">live activity tail · polls every 3s</span></div>
          <div class="kv"><span class="k">Mode</span><span class="v blue" id="tlMode">—</span></div>
          <div class="kv"><span class="k">Active team workers</span><span class="v ok" id="tlActiveCount">—</span></div>
          <div id="tlCounts" style="display:flex;flex-wrap:wrap;gap:6px;margin-top:6px;font-size:11px"></div>
          <div style="margin-top:8px;font-size:11px;color:#ff8c33;font-weight:600">TEAM BUCKETS · last 10 F47 records per team</div>
          <div id="tlBuckets" style="display:grid;grid-template-columns:1fr 1fr;gap:4px;margin-top:4px;font-size:10px;max-height:200px;overflow-y:auto"></div>
          <div style="margin-top:8px;font-size:11px;color:#ff8c33;font-weight:600">RECENT EVENTS</div>
          <div id="tlEvents" style="background:rgba(8,16,28,.7);min-height:200px;max-height:280px;overflow-y:auto;padding:8px;border:1px solid rgba(255,140,40,.25);border-radius:6px;margin-top:4px;font-family:monospace;font-size:11px;line-height:1.5"></div>
          <div style="margin-top:6px;color:var(--muted);font-size:10px">advisory · all events from qsb_tower_activity_tail.jsonl + qsb_f47_team_records.jsonl</div>`;
        const modeEl = body.querySelector('#tlMode');
        const activeEl = body.querySelector('#tlActiveCount');
        const countsEl = body.querySelector('#tlCounts');
        const eventsEl = body.querySelector('#tlEvents');
        const bucketsEl = body.querySelector('#tlBuckets');
        const BUCKET_COLOR = {
          architects: '#80b2ff', web_design: '#66f2b2', graphics: '#ffd359',
          fitters: '#ff8c33', trading: '#4ade80', email: '#c780ff',
          training: '#9aaec5', advisers: '#ff8b3a', infra: '#5fa8ff', other: '#aab',
        };
        function paintBuckets() {
          fetch('/api/team/output', {cache: 'no-store'})
            .then((r) => r.json())
            .then((j) => {
              const b = j.buckets || {};
              bucketsEl.innerHTML = '';
              Object.keys(b).forEach((k) => {
                const slot = b[k] || {};
                // Endpoint shape: {team: "...", events: [...]}.
                // Fall back to raw array shape just in case.
                const recs = Array.isArray(slot) ? slot : (slot.events || []);
                const teamName = (slot.team || k);
                const card = document.createElement('div');
                card.style.cssText = 'background:rgba(8,16,28,.6);padding:4px 6px;border-radius:4px;border-left:3px solid ' + (BUCKET_COLOR[k]||'#456');
                const head = '<div style="color:' + (BUCKET_COLOR[k]||'#aab') + ';font-weight:600">' + k + ' · ' + recs.length + ' <span style="color:#789;font-weight:400;font-size:9px">' + esc(teamName) + '</span></div>';
                const rows = recs.slice(0, 3).map((r) => {
                  const s = (r.summary || r.kind || '').slice(0, 70);
                  const ts = (r.ts || '').slice(11, 16);
                  return '<div style="color:#cde;font-size:9px">' + ts + ' · ' + esc(s) + '</div>';
                }).join('');
                card.innerHTML = head + rows;
                bucketsEl.appendChild(card);
              });
            })
            .catch(() => {});
        }

        const KIND_COLOR = {
          'trade_close':       '#4ade80',
          'trade_open':        '#5fa8ff',
          'strategy_proposed': '#ff8c33',
          'auto_close_tick':   '#9aaec5',
          'team_dispatch':     '#c780ff',
          'team_output':       '#ffd359',
          'provider_call':     '#66f2b2',
          'kernel_chat_query': '#80b2ff',
          'audit_event':       '#bbb',
          'f47_record':        '#ff8b3a',
          'lineage_stamp':     '#ff8b3a',
        };

        function paint() {
          fetch('/api/team/live?tail=40', {cache: 'no-store'})
            .then((r) => r.json())
            .then((j) => {
              if (!j.ok) return;
              modeEl.textContent = j.kernel_mode || '—';
              activeEl.textContent = (j.team_workers_active_count || 0) + ' (of 250 F47+F37 roster)';
              countsEl.innerHTML = '';
              const c = j.event_counts_last_500 || {};
              Object.keys(c).sort((a,b) => c[b] - c[a]).slice(0, 8).forEach((k) => {
                const chip = document.createElement('span');
                chip.style.padding = '3px 7px';
                chip.style.borderRadius = '4px';
                chip.style.background = 'rgba(15,30,60,.7)';
                chip.style.color = KIND_COLOR[k] || '#aab';
                chip.style.border = '1px solid ' + (KIND_COLOR[k] || '#456') + '55';
                chip.textContent = c[k] + '× ' + k;
                countsEl.appendChild(chip);
              });
              eventsEl.innerHTML = '';
              (j.events_tail || []).slice().reverse().forEach((e) => {
                const row = document.createElement('div');
                const color = KIND_COLOR[e.event_kind] || '#aab';
                const ts = (e.ts || '').slice(11, 19);
                const floor = (e.floor || '-').padEnd(4);
                const kind = (e.event_kind || '-').padEnd(20).slice(0, 20);
                const summary = (e.summary || '').slice(0, 110);
                row.innerHTML = '<span style="color:#5a6">' + ts + '</span>  ' +
                                '<span style="color:#9ac">' + floor + '</span>  ' +
                                '<span style="color:' + color + '">' + kind + '</span>  ' +
                                '<span style="color:#cde">' + esc(summary) + '</span>';
                eventsEl.appendChild(row);
              });
            })
            .catch(() => {});
        }
        paint();
        paintBuckets();
        const t = setInterval(paint, 3000);
        const tb = setInterval(paintBuckets, 8000);
        // stop polling when this window closes
        const qwin = body.closest('.qwin');
        if (qwin) {
          const closeBt = qwin.querySelector('.qwin-close');
          if (closeBt) closeBt.addEventListener('click', () => { clearInterval(t); clearInterval(tb); });
        }
      },
    });
  }

  // V18 — Wren's Code Crew window. 100 workers on F47 watching every code touch.
  function openCodeCrewWindow() {
    const W = window.QSB_WINDOWS;
    W.open('code-crew', {
      title: "Wren's Code Crew · F47 · 100 workers",
      width: 760, height: 600,
      render: (body) => {
        body.innerHTML = `
          <div class="kv"><span class="k">Crew Lead</span><span class="v ok" id="ccLead">F47.CODE.001</span></div>
          <div class="kv"><span class="k">Certified</span><span class="v ok" id="ccCertified">—</span></div>
          <div class="kv"><span class="k">Training Level</span><span class="v ok" id="ccTraining">—</span></div>
          <div class="kv"><span class="k">Window</span><span class="v" id="ccWindow">last 15 min</span></div>
          <div class="kv"><span class="k">Commentary</span><span class="v" id="ccComment" style="font-style:italic;color:#ffd359">—</span></div>
          <div style="margin-top:8px;font-size:11px;color:#ff5555;font-weight:700">⚠⚠ SYNTAX ERRORS (code will not run)</div>
          <div id="ccSyntax" style="background:rgba(40,12,12,.7);padding:6px;border:1px solid rgba(255,80,80,.5);border-radius:4px;margin-top:4px;font-family:monospace;font-size:10px;color:#ffcccc;min-height:18px">—</div>
          <div style="margin-top:8px;font-size:11px;color:#ff8c33;font-weight:600">RECENT FILES TOUCHED</div>
          <div id="ccFiles" style="background:rgba(8,16,28,.7);max-height:140px;overflow-y:auto;padding:6px;border:1px solid rgba(255,140,40,.25);border-radius:4px;margin-top:4px;font-family:monospace;font-size:10px"></div>
          <div style="margin-top:8px;font-size:11px;color:#ff8c33;font-weight:600">TODO / FIXME BACKLOG</div>
          <div id="ccTodos" style="background:rgba(8,16,28,.7);max-height:140px;overflow-y:auto;padding:6px;border:1px solid rgba(255,140,40,.25);border-radius:4px;margin-top:4px;font-family:monospace;font-size:10px"></div>
          <div style="margin-top:8px;font-size:11px;color:#ff8c33;font-weight:600">OPEN PHASES (not yet stamped complete)</div>
          <div id="ccOpenPhases" style="background:rgba(8,16,28,.7);padding:6px;border:1px solid rgba(255,140,40,.25);border-radius:4px;margin-top:4px;font-family:monospace;font-size:11px;color:#80b2ff">—</div>
          <div style="margin-top:8px;font-size:11px;color:#ff8c33;font-weight:600">STUB / UNFINISHED PATTERNS</div>
          <div id="ccStubs" style="background:rgba(8,16,28,.7);padding:6px;border:1px solid rgba(255,140,40,.25);border-radius:4px;margin-top:4px;font-family:monospace;font-size:10px;color:#ff8b3a"></div>
          <div style="margin-top:6px;color:var(--muted);font-size:10px">advisory · 100 workers · trained to high standard · access: ML/DL/QDNN/Library</div>`;
        function paint() {
          fetch('/api/code_crew/status', {cache:'no-store'})
            .then((r) => r.json())
            .then((j) => {
              if (!j.ok) { el('ccComment').textContent = j.error || 'status error'; return; }
              el('ccComment').textContent = j.commentary || '—';
              el('ccWindow').textContent = 'last ' + (j.window_minutes||15) + ' min · ts ' + (j.ts||'').slice(11,19);
              const fEl = el('ccFiles'); fEl.innerHTML = '';
              (j.recent_files||[]).slice(0, 18).forEach((f) => {
                const row = document.createElement('div');
                const t = (f.mtime_iso || '').slice(11,19);
                row.innerHTML = '<span style="color:#789">' + t + '</span> · <span style="color:#cde">' + esc(f.path) + '</span> <span style="color:#5a6">[' + esc(f.ext) + ']</span>';
                fEl.appendChild(row);
              });
              const tEl = el('ccTodos'); tEl.innerHTML = '';
              (j.todo_markers||[]).slice(0, 14).forEach((t) => {
                const row = document.createElement('div');
                row.innerHTML = '<span style="color:#ff8b3a">' + esc(t.marker) + '</span> ' +
                                '<span style="color:#5fa8ff">' + esc(t.file) + ':' + t.line + '</span> ' +
                                '<span style="color:#cde">' + esc(t.text) + '</span>';
                tEl.appendChild(row);
              });
              const ops = j.open_phases || [];
              el('ccOpenPhases').textContent = ops.length ? ops.join(', ') : '(none — all phases stamped complete)';
              const sEl = el('ccStubs'); sEl.innerHTML = (j.stub_warnings || []).map((s) => '· ' + esc(s)).join('<br>') || '(none)';
              const synEl = el('ccSyntax');
              const errs = j.syntax_errors || [];
              if (errs.length === 0) {
                synEl.innerHTML = '<span style="color:#4ade80">✓ no syntax errors — all py + js parses clean</span>';
              } else {
                synEl.innerHTML = errs.map((e) =>
                  '<div><b style="color:#ff5555">' + esc(e.lang) + '</b> ' + esc(e.file) + '<br><span style="padding-left:14px">' + esc(e.error) + '</span></div>'
                ).join('');
              }
            })
            .catch(() => { el('ccComment').textContent = 'fetch failed'; });
          fetch('/api/code_crew/roster', {cache:'no-store'})
            .then((r) => r.json())
            .then((j) => {
              if (!j.workers) return;
              const cert = j.workers.filter((w) => w.certified).length;
              el('ccCertified').textContent = cert + ' / ' + j.workers.length;
              const hi = j.workers.filter((w) => (w.training||{}).training_level==='high').length;
              el('ccTraining').textContent = 'high (' + hi + '/' + j.workers.length + ')';
            })
            .catch(() => {});
        }
        paint();
        const t = setInterval(paint, 5000);
        const qwin = body.closest('.qwin');
        if (qwin) {
          const closeBt = qwin.querySelector('.qwin-close');
          if (closeBt) closeBt.addEventListener('click', () => clearInterval(t));
        }
      },
    });
  }

  // V18 — Truth Audit window. Cross-checks every displayed count vs canonical source.
  function openTruthAuditWindow() {
    const W = window.QSB_WINDOWS;
    W.open('truth-audit', {
      title: '🔍 Truth Audit · cross-dashboard mismatches',
      width: 760, height: 540,
      render: (body) => {
        body.innerHTML = `
          <div class="kv"><span class="k">Buckets checked</span><span class="v ok" id="taChecked">—</span></div>
          <div class="kv"><span class="k">Mismatches</span><span class="v" id="taCount">—</span></div>
          <div class="kv"><span class="k">Last audit</span><span class="v" id="taTs">—</span></div>
          <div style="margin-top:8px;font-size:11px;color:#ff8c33;font-weight:600">CONCEPT BUCKETS · canonical → alternates</div>
          <div id="taBuckets" style="background:rgba(8,16,28,.75);max-height:280px;overflow-y:auto;padding:8px;border:1px solid rgba(255,140,40,.25);border-radius:4px;margin-top:4px;font-family:monospace;font-size:10px;line-height:1.55"></div>
          <div style="margin-top:8px;font-size:11px;color:#ff8b3a;font-weight:600">MISMATCHES FLAGGED BY F47.CODE CREW</div>
          <div id="taMismatches" style="background:rgba(40,16,12,.55);max-height:140px;overflow-y:auto;padding:8px;border:1px solid rgba(255,80,40,.4);border-radius:4px;margin-top:4px;font-family:monospace;font-size:10px;line-height:1.55"></div>
          <div style="margin-top:6px;color:var(--muted);font-size:10px">refreshed every 60s by qsb_truth_audit.py · advisory</div>`;
        function paint() {
          fetch('/api/truth/audit', {cache:'no-store'})
            .then((r) => r.json())
            .then((d) => {
              const buckets = d.buckets || {};
              el('taChecked').textContent = Object.keys(buckets).length;
              const mc = d.mismatch_count || 0;
              const taCnt = el('taCount');
              taCnt.textContent = mc + ' ' + (mc === 0 ? '(all aligned)' : '(needs reconciling)');
              taCnt.style.color = mc === 0 ? '#4ade80' : '#ff8b3a';
              el('taTs').textContent = (d.ts || '').slice(11,19);
              const bEl = el('taBuckets'); bEl.innerHTML = '';
              Object.keys(buckets).forEach((k) => {
                const b = buckets[k];
                const head = document.createElement('div');
                head.innerHTML = '<span style="color:#ff8c33;font-weight:600">' + esc(k) + '</span> ' +
                                 '<span style="color:#4ade80">canonical=' + esc(String(b.canonical.value)) + '</span> ' +
                                 '<span style="color:#789">[' + esc(b.canonical.source + '/' + b.canonical.path) + ']</span>';
                bEl.appendChild(head);
                (b.alternates || []).forEach((a) => {
                  const same = String(a.value) === String(b.canonical.value);
                  const r = document.createElement('div');
                  r.style.paddingLeft = '14px';
                  r.innerHTML = '<span style="color:' + (same?'#4ade80':'#ff8b3a') + '">' +
                                (same?'✓':'✗') + '</span> ' +
                                '<span style="color:#cde">' + esc(String(a.value)) + '</span> ' +
                                '<span style="color:#789">[' + esc(a.source + '/' + a.path) + ']</span>';
                  bEl.appendChild(r);
                });
              });
              const mEl = el('taMismatches'); mEl.innerHTML = '';
              if (mc === 0) {
                mEl.innerHTML = '<span style="color:#4ade80">No mismatches. All displayed counts trace to canonical source.</span>';
              } else {
                (d.mismatches || []).forEach((m) => {
                  const r = document.createElement('div');
                  r.innerHTML = '<span style="color:#ff8b3a">' + esc(m.concept) + '</span> ' +
                                '<span style="color:#cde">canonical=' + esc(String(m.canonical_value)) + '</span> ' +
                                '<span style="color:#ff5555">vs ' + esc(String(m.alt_value)) + '</span> ' +
                                '<span style="color:#789">[' + esc(m.alt_source) + ']</span> ' +
                                '<span style="color:#9ac">Δ=' + esc(String(m.delta)) + '</span>';
                  mEl.appendChild(r);
                });
              }
            })
            .catch((e) => { el('taCount').textContent = 'fetch failed: ' + e.message; });
        }
        paint();
        const t = setInterval(paint, 6000);
        const qwin = body.closest('.qwin');
        if (qwin) {
          const closeBt = qwin.querySelector('.qwin-close');
          if (closeBt) closeBt.addEventListener('click', () => clearInterval(t));
        }
      },
    });
  }

  // V18 — Live Dispatch window. Shows what every team is being told to do + when it's done.
  function openLiveDispatchWindow() {
    const W = window.QSB_WINDOWS;
    W.open('live-dispatch', {
      title: '🏗️ Live Dispatch · 12 teams',
      width: 800, height: 580,
      render: (body) => {
        body.innerHTML = `
          <div class="kv"><span class="k">Teams dispatched</span><span class="v ok" id="ldTeams">—</span></div>
          <div class="kv"><span class="k">Tasks complete</span><span class="v ok" id="ldComplete">—</span></div>
          <div class="kv"><span class="k">Errors</span><span class="v" id="ldErrors">—</span></div>
          <div class="kv"><span class="k">Last update</span><span class="v" id="ldTs">—</span></div>
          <div style="margin-top:8px;font-size:11px;color:#ff8c33;font-weight:600">LIVE JOB STREAM (newest first)</div>
          <div id="ldEvents" style="background:rgba(8,16,28,.75);max-height:420px;overflow-y:auto;padding:8px;border:1px solid rgba(255,140,40,.3);border-radius:6px;margin-top:6px;font-family:monospace;font-size:10px;line-height:1.5"></div>
          <div style="margin-top:6px;color:var(--muted);font-size:10px">polls every 4s · run <code>tools/qsb_mass_dispatch.py</code> to assign new round</div>`;
        const STATUS_COLOR = {
          ASSIGNED: '#5fa8ff', COMPLETE: '#4ade80', ERROR: '#ff5555', WORKING: '#ffd359',
        };
        function paint() {
          fetch('/api/dispatch/live', {cache:'no-store'})
            .then((r) => r.json())
            .then((j) => {
              const s = j.state || {};
              el('ldTeams').textContent = (s.teams_dispatched || 0);
              el('ldComplete').textContent = (s.tasks_complete || 0) + ' / ' + (s.tasks_assigned || 0);
              el('ldErrors').textContent = (s.tasks_error || 0);
              el('ldTs').textContent = (s.ts || j.ts || '').slice(11,19);
              const evEl = el('ldEvents'); evEl.innerHTML = '';
              (j.events_tail || []).slice().reverse().forEach((e) => {
                const row = document.createElement('div');
                const ts = (e.ts || '').slice(11,19);
                const color = STATUS_COLOR[e.status] || '#aab';
                row.innerHTML = '<span style="color:#789">' + ts + '</span>  ' +
                                '<span style="color:#c780ff">' + esc((e.team||'').padEnd(22).slice(0,22)) + '</span>  ' +
                                '<span style="color:' + color + ';font-weight:600">' + esc((e.status||'').padEnd(8)) + '</span>  ' +
                                '<span style="color:#cde">' + esc((e.task||'').slice(0,40).padEnd(40)) + '</span>  ' +
                                '<span style="color:#9ac">' + esc((e.detail||'').slice(0,70)) + '</span>';
                evEl.appendChild(row);
              });
            }).catch(() => {});
        }
        paint();
        const t = setInterval(paint, 4000);
        const qwin = body.closest('.qwin');
        if (qwin) {
          const closeBt = qwin.querySelector('.qwin-close');
          if (closeBt) closeBt.addEventListener('click', () => clearInterval(t));
        }
      },
    });
  }

  function openKernelChatWindow(state) {
    const W = window.QSB_WINDOWS;
    W.open('kernel-chat', {
      title: 'QSB Kernel Chat',
      width: 520, height: 460,
      render: (body) => {
        const k = (state || window.QSB.state || {}).kernel || {};
        body.innerHTML = `
          <div class="kv"><span class="k">Activation</span><span class="v ok">${esc(k.activation_status || '—')}</span></div>
          <div class="kv"><span class="k">Source</span><span class="v blue">${esc(k.active_kernel_source || '—')}</span></div>
          <div class="kv"><span class="k">Local model</span><span class="v ${k.local_model_enabled ? 'ok' : 'warn'}">${esc(k.local_model_enabled ? 'enabled' : 'disabled')}</span></div>
          <div class="kv"><span class="k">Locks</span><span class="v ok">all closed</span></div>
          <div class="kv"><span class="k">Chat sidecar</span><span class="v warn" id="chatSidecarStatus">probing…</span></div>
          <div id="chatLog" class="chat-log"></div>
          <div class="chat-row">
            <input id="chatInput" type="text" placeholder="probing kernel chat sidecar…" disabled>
            <button id="chatMic" title="Hold-to-talk · uses browser SpeechRecognition" style="padding:6px 9px">🎤 Mic</button>
            <button id="chatSend" disabled>Send</button>
            <button id="chatProbe" title="Re-probe sidecar" style="padding:6px 9px">⟳</button>
          </div>`;
        const log    = body.querySelector('#chatLog');
        const input  = body.querySelector('#chatInput');
        const sendBt = body.querySelector('#chatSend');
        const micBt  = body.querySelector('#chatMic');
        const probeBt= body.querySelector('#chatProbe');
        const statusEl = body.querySelector('#chatSidecarStatus');

        function setAvailable(avail, label) {
          statusEl.textContent = label;
          statusEl.className = 'v ' + (avail ? 'ok' : 'warn');
          input.disabled = !avail;
          sendBt.disabled = !avail;
          input.placeholder = avail
            ? 'Ask the kernel…'
            : 'Kernel core active. Chat endpoint offline. View-only.';
        }
        function probe() {
          setAvailable(false, 'probing…');
          fetch('/api/kernel_chat_status', { cache: 'no-store' })
            .then((r) => r.json())
            .then((s) => {
              const route = s.active_route || (s.sidecar_available ? 'sidecar' :
                              s.dashboard_local_kernel_dialogue ? 'dashboard-local' : 'view_only');
              const label = s.available
                ? (route === 'kernel_chat_sidecar_8766'
                    ? ('sidecar :8766 · ' + (s.selected_model || 'kernel'))
                    : ('dashboard-local · ' + (s.selected_model || 'kernel')))
                : (s.sidecar_listening ? 'listening · ' + (s.sidecar_health || 'unknown') : 'offline');
              setAvailable(!!s.available, label);
              if (s.available) {
                const msg = (route === 'kernel_chat_sidecar_8766')
                  ? ('Connected to kernel chat sidecar on :' + (s.sidecar_port || 8766) +
                     ' · model: ' + (s.selected_model || 'kernel'))
                  : ('Connected · dashboard-local kernel dialogue · model: ' + (s.selected_model || 'kernel'));
                appendChatRow(log, 'system', msg);
                loadHistory(log);
              } else {
                appendChatRow(log, 'system', s.view_only_message || 'Kernel core active. Chat endpoint offline. View-only.');
              }
            })
            .catch((e) => {
              setAvailable(false, 'status probe failed');
              appendChatRow(log, 'system', 'Status probe failed: ' + e);
            });
        }
        function loadHistory(log) {
          fetch('/api/kernel_chat_history', { cache: 'no-store' })
            .then((r) => r.ok ? r.json() : null)
            .then((j) => {
              if (j && Array.isArray(j.history)) {
                j.history.slice(-12).forEach((h) => {
                  const msg = (h.message || '').slice(0, 240);
                  const reply = (h.reply || '').slice(0, 240);
                  if (msg) appendChatRow(log, 'user',   '> ' + msg);
                  if (reply) appendChatRow(log, 'kernel', reply);
                });
              }
            }).catch(() => {});
        }
        probeBt.addEventListener('click', probe);
        sendBt.addEventListener('click', () => sendChat(body, log));
        input.addEventListener('keydown', (e) => { if (e.key === 'Enter') sendChat(body, log); });
        // V14 — mic button: browser SpeechRecognition → transcribe → send
        let micOn = false; let recog = null;
        micBt.addEventListener('click', () => {
          const SR = window.SpeechRecognition || window.webkitSpeechRecognition;
          if (!SR) {
            appendChatRow(log, 'system', 'Browser SpeechRecognition not available — Chrome/Edge supports it; Firefox does not. Type instead.');
            return;
          }
          if (micOn && recog) {
            try { recog.stop(); } catch (e) {}
            micOn = false; micBt.textContent = '🎤 Mic'; micBt.classList.remove('active');
            return;
          }
          if (input.disabled) {
            appendChatRow(log, 'system', 'Chat endpoint offline — re-probe first.');
            return;
          }
          recog = new SR();
          recog.continuous = false;
          recog.interimResults = false;
          recog.lang = navigator.language || 'en-US';
          recog.onresult = (ev) => {
            const txt = ev.results[0][0].transcript;
            input.value = txt;
            appendChatRow(log, 'system', '🎤 heard: ' + txt);
            sendChat(body, log);
          };
          recog.onerror = (ev) => {
            appendChatRow(log, 'system', 'mic error: ' + (ev.error || ev.message || 'unknown'));
            micOn = false; micBt.textContent = '🎤 Mic'; micBt.classList.remove('active');
          };
          recog.onend = () => {
            micOn = false; micBt.textContent = '🎤 Mic'; micBt.classList.remove('active');
          };
          try {
            recog.start();
            micOn = true; micBt.textContent = '🎙 Listening…'; micBt.classList.add('active');
            appendChatRow(log, 'system', '🎤 listening — speak now…');
          } catch (e) {
            appendChatRow(log, 'system', 'mic start failed: ' + e);
          }
        });
        probe();
      },
    });
  }
  function appendChatRow(log, cls, text) {
    const row = document.createElement('div');
    row.className = 'row ' + cls;
    row.textContent = text;
    log.appendChild(row);
    log.scrollTop = log.scrollHeight;
  }
  async function sendChat(body, log) {
    const inp = body.querySelector('#chatInput');
    const txt = (inp.value || '').trim();
    if (!txt) return;
    appendChatRow(log, 'user', '> ' + txt);
    inp.value = '';
    try {
      const r = await fetch('/api/kernel_chat', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ message: txt, text: txt }),
      });
      const j = await r.json();
      appendChatRow(log, 'kernel', (j && (j.reply || j.text || j.message)) || JSON.stringify(j).slice(0, 200));
    } catch (e) {
      appendChatRow(log, 'system', 'send failed: ' + e);
    }
  }

  function openLockDetailWindow() {
    const state = window.QSB.state || {};
    const locks = state.locks || {};
    window.QSB_WINDOWS.open('lock-detail', {
      title: 'Execution Lock Matrix — Detail',
      width: 480, height: 460,
      render: (body) => {
        body.innerHTML = '<table class="detail-tbl">' +
          LOCK_LABELS.map(([k, label]) =>
            `<tr><td>${esc(label)}</td><td><span class="${locks[k] ? 'bad' : 'ok'}">${locks[k] ? 'TRUE' : 'false'}</span> · <code style="color:#88a3c2">${esc(k)}</code></td></tr>`).join('') +
          '</table>' +
          `<div class="tagline ${state.lock_count_true ? 'warn' : 'ok'}">
             ${esc(state.lock_count_true || 0)} / 13 locks reporting TRUE.
           </div>`;
      },
    });
  }

  function openWorkerWindow(wid) {
    const state = window.QSB.state || {};
    const wCached = (state.workers || []).find((x) => x.id === wid) || { id: wid };
    window.QSB_WINDOWS.open('worker-' + wid, {
      title: 'Worker ID Card — ' + (wCached.name || wid),
      width: 460, height: 540,
      render: (body) => {
        body.innerHTML = '<div id="wcBody">loading…</div>';
        const wcBody = body.querySelector('#wcBody');
        // Try to pull the rich record from the new Tower Ops directory
        fetch('/api/workers/directory', { cache: 'no-store' }).then((r) => r.json()).then((d) => {
          const w = (d.directory || []).find((x) => x.worker_id === wid || x.display_name === wCached.name) || wCached;
          const rows = [
            ['Display name', w.display_name || wCached.name],
            ['Badge ID',     '<code style="color:var(--gold2)">' + esc(w.badge_id || '—') + '</code>'],
            ['Short code',   '<code>' + esc(w.short_code || '—') + '</code>'],
            ['Role',         w.role || wCached.role || '—'],
            ['Department',   w.department || w.team || '—'],
            ['Home floor',   '<code data-route-floor="' + esc(String(w.home_floor || '').replace('floor_', '')) + '">' + esc(w.home_floor || '—') + '</code>'],
            ['Current floor','<code>' + esc(w.current_floor || w.home_floor || '—') + '</code>'],
            ['Current room', esc(w.current_room || '—')],
            ['Stage',        esc(w.recruitment_stage || '—')],
            ['Access level', '<b>' + esc(w.access_level || '—') + '</b>'],
            ['Allowed floors', esc((w.allowed_floors || []).join(', ') || '—')],
            ['Allowed actions', esc((w.allowed_actions || []).join(', ') || '—')],
            ['Forbidden actions', '<span class="warn">' + esc((w.forbidden_actions || []).join(', ') || '—') + '</span>'],
            ['Data access',  esc((w.data_access || []).join(', '))],
            ['Trading data', esc((w.trading_data_access || []).join(', ') || '—')],
            ['Model access', esc((w.model_access || []).join(', '))],
            ['OpenClaw access', esc(w.openclaw_access || '—')],
            ['Kernel access', esc(w.kernel_access || '—')],
            ['AirLLM access', esc(w.airllm_access || '—')],
            ['Quantum access', esc(w.quantum_access || '—')],
            ['Accounting access', esc(w.accounting_access || '—')],
            ['Web access',   '<span class="ok">' + esc(w.web_access || 'denied') + '</span>'],
            ['Audio access', esc(w.audio_access || '—')],
            ['Heartbeat',    esc((w.heartbeat_ts || '').slice(11, 19))],
            ['Current task', esc(w.current_task || '—')],
            ['OpenClaw ready', '<span class="' + (w.openclaw_ready ? 'ok' : 'warn') + '">' + String(!!w.openclaw_ready) + '</span>'],
            ['OpenClaw execution', '<span class="ok">false</span>'],
            ['Trading execution',  '<span class="ok">false</span>'],
            ['Provider access',    '<span class="ok">false</span>'],
            ['Autonomous dispatch','<span class="ok">false</span>'],
          ];
          wcBody.innerHTML =
            '<table class="detail-tbl">' +
            rows.map(([k, v]) => '<tr><td>' + esc(k) + '</td><td>' + (typeof v === 'string' && v.indexOf('<') === 0 ? v : esc(String(v == null ? '' : v))) + '</td></tr>').join('') +
            '</table>' +
            // V18.12 Worker Chat — Ross 2026-06-12 "I cant talk to the workers still"
            '<div style="margin-top:12px;padding-top:10px;border-top:1px solid var(--border2)">' +
            '<input id="wkChatInput-' + esc(wid) + '" type="text" placeholder="Ask this worker something…" ' +
            '   style="width:75%;padding:6px 10px;background:rgba(20,32,56,.7);color:var(--text);' +
            '   border:1px solid var(--border2);border-radius:6px;font-size:12px" />' +
            '<button id="wkChatSend-' + esc(wid) + '" ' +
            '   style="margin-left:6px;padding:6px 14px;background:linear-gradient(90deg,#ffb45a,#ff8a3c);' +
            '   color:#1a0c00;border:0;border-radius:6px;cursor:pointer;font-weight:500;font-size:12px">Talk</button>' +
            '<div id="wkChatLog-' + esc(wid) + '" style="margin-top:10px;font-size:12px;color:var(--text);' +
            '   max-height:140px;overflow:auto"></div>' +
            '</div>';
          const sendBtn = wcBody.querySelector('#wkChatSend-' + CSS.escape(wid));
          const input   = wcBody.querySelector('#wkChatInput-' + CSS.escape(wid));
          const log     = wcBody.querySelector('#wkChatLog-' + CSS.escape(wid));
          async function send() {
            const text = input.value.trim();
            if (!text) return;
            const youLine = document.createElement('div');
            youLine.innerHTML = '<b style="color:var(--cyan)">you:</b> ' + esc(text);
            log.appendChild(youLine);
            input.value = '';
            try {
              const r = await fetch('/api/workers/' + encodeURIComponent(wid) + '/talk', {
                method: 'POST', headers: {'Content-Type': 'application/json'},
                body: JSON.stringify({ text })
              });
              const d = await r.json();
              const wkLine = document.createElement('div');
              wkLine.innerHTML = '<b style="color:var(--gold2)">' + esc(d.worker || wid) + ':</b> ' + esc(d.reply || '(no reply)');
              log.appendChild(wkLine);
              log.scrollTop = log.scrollHeight;
              // Speak the reply with a neutral worker voice if speech is on
              if (window.QSB_AUDIO && window.QSB_AUDIO.say && window.QSB_AUDIO.isSpeechOn && window.QSB_AUDIO.isSpeechOn()) {
                try { window.QSB_AUDIO.say(d.reply); } catch (e) {}
              }
            } catch (e) {
              const err = document.createElement('div');
              err.innerHTML = '<span class="warn">error: ' + esc(e.message || 'unknown') + '</span>';
              log.appendChild(err);
            }
          }
          sendBtn.addEventListener('click', send);
          input.addEventListener('keydown', (e) => { if (e.key === 'Enter') send(); });
          input.focus();
        }).catch(() => {
          wcBody.innerHTML = '<div class="tagline warn">Directory fetch failed — showing cached record only.</div>';
        });
      },
    });
  }

  // Pinned floor windows survive Previous/Next navigation.
  const PINNED_FLOORS = new Set();

  // V17 — floor speaks when its window is opened. Hits /api/floor/<n>/intro
  // then browser SpeechSynthesis. Falls back to a static line if endpoint fails.
  function _speakFloorIntro(floorNum) {
    if (!window.speechSynthesis) return;
    fetch('/api/floor/' + floorNum + '/intro')
      .then(r => r.ok ? r.json() : null)
      .then(d => {
        const text = (d && d.intro) || ('Floor ' + floorNum + ' selected.');
        try { window.speechSynthesis.cancel(); } catch (e) {}
        const u = new SpeechSynthesisUtterance(text);
        u.rate = 1.05; u.pitch = 1.0;
        const v = window.speechSynthesis.getVoices().find(
          (vv) => /samantha|kate|fiona|en-GB|allison|female/i.test(vv.name + ' ' + vv.lang));
        if (v) u.voice = v;
        window.speechSynthesis.speak(u);
      })
      .catch(() => {});
  }

  // V17 — worker speaks when clicked. Pulls from /api/worker/<id> if available,
  // else composes from worker_id.
  function _speakWorkerIntro(workerId) {
    if (!window.speechSynthesis) return;
    // Try to find floor + role from the id pattern: <floor>.<group>.<role>.<num>
    let text = "Worker " + workerId + " here.";
    const m = workerId.match(/^f(\d+)\.[^.]+\.([^.]+)\.\d+$/i);
    if (m) {
      const flo = parseInt(m[1], 10);
      const role = m[2].replace(/_/g, ' ');
      text = `Worker on floor ${flo}. Role: ${role}.`;
    }
    try { window.speechSynthesis.cancel(); } catch (e) {}
    const u = new SpeechSynthesisUtterance(text);
    u.rate = 1.10; u.pitch = 1.05;
    window.speechSynthesis.speak(u);
  }
  // Expose globally so other JS files (e.g. worker click handlers) can use
  window.QSB_SPEAK_FLOOR = _speakFloorIntro;
  window.QSB_SPEAK_WORKER = _speakWorkerIntro;

  function openFloorWindow(floorNum) {
    _speakFloorIntro(floorNum);

    floorNum = Number(floorNum);
    if (!Number.isFinite(floorNum)) return;

    // Single shared "floor-window" id so Previous/Next reuse one window —
    // unless the floor is pinned, in which case it opens its own "floor-pinned-N".
    const wid = PINNED_FLOORS.has(floorNum) ? ('floor-pinned-' + floorNum) : 'floor-window';
    const state = window.QSB.state || {};
    const cached = (state.floors || []).find((f) => f.number === floorNum) || {};
    const tentativeName = cached.display_name || cached.canonical_name || cached.department ||
                          FLOOR_DETAIL[floorNum] || (floorNum === 0 ? 'Ground / Reception Lobby' :
                                                    floorNum === 54 ? 'Roof - External Providers (LOCKED)' :
                                                    'Floor ' + floorNum);
    const dash = ' — ';
    const tentativeTitle = floorNum >= 1 && floorNum <= 53
      ? ('Floor ' + floorNum + dash + tentativeName)
      : tentativeName;

    if (window.QSB_TOWER_2D_FOCUS_FLOOR) window.QSB_TOWER_2D_FOCUS_FLOOR(floorNum);

    window.QSB_WINDOWS.open(wid, {
      title: tentativeTitle,
      width: 640, height: 520,
      render: (body) => {
        // V14 — Chat + Talk buttons are universally useful but most prominent
        // on F47 (the embassy where Wren takes questions) and F55 (kernel).
        var chatTalkBtns = '';
        if (floorNum === 47 || floorNum === 55) {
          chatTalkBtns =
            '<button class="mini-btn" id="fwChat" title="Open kernel chat" ' +
            'style="background:rgba(255,140,40,0.18);border-color:rgba(255,140,40,0.5)">💬 Chat</button>' +
            (floorNum === 47 ? '<button class="mini-btn" id="fwOps" title="Open F47 ops console" ' +
              'style="background:rgba(154,108,255,0.18);border-color:rgba(154,108,255,0.5)">🛠 Ops</button>' : '') +
            '<button class="mini-btn" id="fwTalk" title="Speak this floor briefing">🔊 Talk</button>';
        } else {
          chatTalkBtns =
            '<button class="mini-btn" id="fwTalk" title="Speak this floor briefing">🔊 Talk</button>';
        }
        body.innerHTML = '<div class="floor-window-header">' +
          '<div class="floor-window-title-row">' +
          '<div class="floor-window-title" id="fwTitle">' + esc(tentativeTitle) + '</div>' +
          '<div class="floor-window-actions">' +
          chatTalkBtns +
          '<button class="mini-btn" id="fwPause" title="Pause floor interior">⏸ Interior</button>' +
          '<button class="mini-btn" id="fwExpand" title="Expand window">⤢ Expand</button>' +
          '<button class="mini-btn" id="fwPrev" title="Previous floor">‹ Prev</button>' +
          '<button class="mini-btn" id="fwNext" title="Next floor">Next ›</button>' +
          '<button class="mini-btn" id="fwPin" title="Pin this window">📌 ' +
          (PINNED_FLOORS.has(floorNum) ? 'Pinned' : 'Pin') + '</button>' +
          '</div></div>' +
          '<div class="floor-window-sub" id="fwSub">loading live data…</div>' +
          '</div>' +
          '<div id="fwInterior" class="floor-window-interior"></div>' +
          '<div id="fwBody" class="floor-window-body"></div>';

        const sub      = body.querySelector('#fwSub');
        const main     = body.querySelector('#fwBody');
        const titleEl  = body.querySelector('#fwTitle');
        const interior = body.querySelector('#fwInterior');

        body.querySelector('#fwPrev').addEventListener('click', () => openFloorWindow(Math.max(0, floorNum - 1)));
        body.querySelector('#fwNext').addEventListener('click', () => openFloorWindow(Math.min(55, floorNum + 1)));
        body.querySelector('#fwPin').addEventListener('click', () => {
          if (PINNED_FLOORS.has(floorNum)) PINNED_FLOORS.delete(floorNum);
          else PINNED_FLOORS.add(floorNum);
          openFloorWindow(floorNum);
        });
        let interiorPaused = false;
        body.querySelector('#fwPause').addEventListener('click', (e) => {
          interiorPaused = !interiorPaused;
          window.QSB_FLOOR_INTERIOR_PAUSE && window.QSB_FLOOR_INTERIOR_PAUSE(interior, interiorPaused);
          e.target.textContent = interiorPaused ? '▶ Interior' : '⏸ Interior';
        });
        // V14 — Chat + Talk button wiring.
        // F47 chat = personal channel Ross↔Wren (f47_chat_room module).
        // F55 chat = kernel chat (general kernel queries).
        const chatBtn = body.querySelector('#fwChat');
        if (chatBtn) {
          chatBtn.addEventListener('click', () => {
            if (floorNum === 47) openF47ChatWindow();
            else openKernelChatWindow(window.QSB.state);
          });
        }
        const opsBtn = body.querySelector('#fwOps');
        if (opsBtn) {
          opsBtn.addEventListener('click', () => openF47OpsWindow());
        }
        const talkBtn = body.querySelector('#fwTalk');
        if (talkBtn) {
          talkBtn.addEventListener('click', () => {
            talkBtn.disabled = true;
            talkBtn.textContent = '🔊 Speaking…';
            fetch('/api/floors/speak', {
              method: 'POST',
              headers: {'Content-Type':'application/json'},
              body: JSON.stringify({floor: floorNum}),
            }).then(r => r.json()).then(j => {
              setTimeout(() => {
                talkBtn.disabled = false;
                talkBtn.textContent = '🔊 Talk';
              }, 2000);
            }).catch(() => {
              talkBtn.disabled = false;
              talkBtn.textContent = '🔊 Talk';
            });
          });
        }
        body.querySelector('#fwExpand').addEventListener('click', () => {
          // Find the floating qwin that wraps this body and resize it large.
          const qwin = body.closest('.qwin');
          if (qwin) {
            qwin.style.width  = Math.min(window.innerWidth  - 60, 1080) + 'px';
            qwin.style.height = Math.min(window.innerHeight - 60, 820)  + 'px';
            qwin.style.left   = Math.max(20, (window.innerWidth  - parseInt(qwin.style.width))  / 2) + 'px';
            qwin.style.top    = Math.max(20, (window.innerHeight - parseInt(qwin.style.height)) / 2) + 'px';
          }
        });

        try {
          const u = new URL(window.location.href);
          u.searchParams.set('floor', String(floorNum));
          window.history.replaceState({}, '', u.toString());
        } catch (e) {}

        fetch('/api/floor_detail?floor=' + encodeURIComponent(floorNum), { cache: 'no-store' })
          .then((r) => r.json())
          .then((d) => {
            paintFloorWindow(d, main, sub, titleEl);
            if (window.QSB_FLOOR_INTERIOR_RENDER) {
              try { window.QSB_FLOOR_INTERIOR_RENDER(interior, d); }
              catch (e) { interior.innerHTML = '<div class="tagline warn">Interior renderer failed: ' + esc(String(e)) + '</div>'; }
            }
            // Floor-specific live consoles
            if (d.floor_number === 55) mountPenthouseConsole(main, d);
            if (d.floor_number === 38) mountRecruitmentConsole(main, d);
            if (d.floor_number === 15) mountSpeechFloorConsole(main, d);
            if (d.floor_number === 33) mountMaintenanceConsole(main, d);
            if (d.floor_number === 28) mountSecurityConsole(main, d);
            if (d.floor_number === 35) mountITConsole(main, d);
            if (d.floor_number ===  3) mountResearchConsole(main, d);
            if (d.floor_number === 41) {
              mountOandaTelemetryConsole(main, d);
              mountOandaPracticeTradingRoom(main, d);
            }
            if (d.floor_number === 42) mountBinanceTelemetryConsole(main, d);
            if (d.floor_number === 43) mountStocksTelemetryConsole(main, d);
            if (d.floor_number === 55) mountColonelConsole(main, d);
            if (d.floor_number === 44) mountAccountsConsole(main, d);
            if (d.floor_number === 45) mountQuantumConsole(main, d);
            if (d.floor_number === 22) mountLiftsConsole(main, d);
            if (d.floor_number === 24) mountModelOpsConsole(main, d);
            if (d.floor_number === 55) mountMissingFloorsPanel(main, d);
            if (d.floor_number === 53) mountMissingFloorsPanel(main, d);
          })
          .catch((e) => {
            main.innerHTML = '<div class="tagline warn">Failed to load /api/floor_detail: ' + esc(String(e)) + '</div>';
            sub.textContent = 'error - falling back to cached state';
            paintFloorWindowFromCache(floorNum, cached, main);
          });
      },
    });
  }

  function paintFloorWindow(d, main, sub, titleEl) {
    if (!d || !d.ok) { paintFloorWindowFromCache(d && d.floor_number, {}, main); return; }
    if (titleEl) titleEl.textContent = d.title || ('Floor ' + d.floor_number);
    sub.innerHTML = '<span class="floor-cat cat-' + esc(d.category || 'infrastructure') + '">' + esc(d.category) + '</span>' +
                    ' · status: ' + esc(d.status || '—') +
                    ' · zone: ' + esc(d.zone || '—') +
                    ' · floor_id: <code>' + esc(d.floor_id || '—') + '</code>' +
                    (d.manifest_path ? ' · manifest ✓' : ' · no manifest') +
                    ' · ' + esc(d.ts || '');

    const blocks = [];
    blocks.push('<div class="fw-block"><h4>Identity</h4><table class="detail-tbl">' +
      kv('Floor number', d.floor_number) +
      kv('Floor ID', '<code>' + esc(d.floor_id || '—') + '</code>') +
      kv('Canonical name', d.canonical_name) +
      kv('Display name', d.display_name) +
      kv('Short label', d.short_label) +
      kv('Category', d.category) +
      kv('Status', d.status) +
      kv('Zone', d.zone) +
      kv('Department (registry)', d.department) +
      kv('Manifest', d.manifest_path ? '<code>' + esc(d.manifest_path) + '</code>' : '—') +
      '</table></div>');

    blocks.push(towerOpsBlock(d));      // manager office / overseer balcony / roster wall
    blocks.push(routesBlock(d));
    blocks.push(workersBlock(d));

    if (d.oanda) blocks.push(oandaBlock(d));
    if (d.binance) blocks.push(binanceBlock(d));
    if (d.stock_exchange) blocks.push(stocksBlock(d));
    if (d.airllm_chamber) blocks.push(airllmBlock(d));
    if (d.risk) blocks.push(riskBlock(d));
    if (d.audit) blocks.push(auditBlock(d));
    if (d.strategy) blocks.push(strategyBlock(d));
    if (d.sandbox) blocks.push(sandboxBlock(d));
    if (d.command) blocks.push(commandBlock(d));
    if (d.roof) blocks.push(roofBlock(d));
    if (d.ground) blocks.push(groundBlock(d));

    blocks.push(safetyBlock(d));
    main.innerHTML = blocks.join('');
  }

  function paintFloorWindowFromCache(floorNum, cached, main) {
    main.innerHTML = '<div class="fw-block"><h4>Cached (no /api/floor_detail response)</h4><table class="detail-tbl">' +
      kv('Floor number', floorNum) +
      kv('Display name', cached.display_name || cached.department) +
      kv('Category', cached.category) +
      kv('Status', cached.status) +
      '</table></div>';
  }

  function kv(k, v) {
    const value = v == null ? '—' : (typeof v === 'string' && v.indexOf('<') === 0 ? v : esc(v));
    return '<tr><td>' + esc(k) + '</td><td>' + value + '</td></tr>';
  }
  function routesBlock(d) {
    const out = (d.routes && d.routes.outbound) || [];
    const inb = (d.routes && d.routes.inbound)  || [];
    const linkTarget = (id) => {
      if (!id) return '';
      const m = /^floor_(\d{1,2})$/.exec(id);
      if (m) return ' data-route-floor="' + m[1] + '"';
      if (id === 'penthouse' || id === 'penthouse_kernel_review') return ' data-route-floor="55"';
      return '';
    };
    const row = (r) => '<tr class="route-row">' +
      '<td><code' + linkTarget(r.source_floor) + '>' + esc(r.source_floor) + '</code> → ' +
        '<code' + linkTarget(r.target_floor) + '>' + esc(r.target_floor) + '</code></td>' +
      '<td><span class="lg lg-' + esc(r.color || 'cyan') + '">' + esc(r.route_type || 'route') + '</span>' +
      (r.advisory_only ? ' · advisory_only' : '') + '</td></tr>';
    const html = '<div class="fw-block"><h4>Connected routes <span class="sub">' +
      out.length + ' out · ' + inb.length + ' in · paper_only · execution_allowed=false · click a floor to open</span></h4>' +
      '<table class="detail-tbl">' +
      (out.length ? '<tr><td><b>Outbound</b></td><td></td></tr>' + out.map(row).join('') : '') +
      (inb.length ? '<tr><td><b>Inbound</b></td><td></td></tr>' + inb.map(row).join('') : '') +
      ((out.length + inb.length) === 0 ? '<tr><td>none</td><td>—</td></tr>' : '') +
      '</table></div>';
    return html;
  }
  // Delegated click handler — any code[data-route-floor] inside a window opens the linked floor.
  document.addEventListener('click', (e) => {
    const t = e.target;
    if (t && t.tagName === 'CODE' && t.dataset && t.dataset.routeFloor != null) {
      const n = Number(t.dataset.routeFloor);
      if (Number.isFinite(n)) {
        e.preventDefault();
        if (window.QSB_TOWER_2D_FOCUS_FLOOR) window.QSB_TOWER_2D_FOCUS_FLOOR(n);
        openFloorWindow(n);
      }
    }
  });
  function workersBlock(d) {
    const ws = d.workers || [];
    if (!ws.length) return '<div class="fw-block"><h4>Workers</h4><div class="tagline">No workers homed at this floor.</div></div>';
    return '<div class="fw-block"><h4>Workers <span class="sub">' + ws.length + '</span></h4>' +
      '<table class="detail-tbl">' +
      ws.map((w) => '<tr><td><b>' + esc(w.name || w.id) + '</b></td><td>' + esc(w.role || '—') +
        ' · <code>' + esc(w.id) + '</code></td></tr>').join('') +
      '</table></div>';
  }
  function oandaBlock(d) {
    const o = d.oanda;
    const sigRows = (o.paper_signals || []).map((s) => '<tr><td><b>' + esc(s.instrument || s.symbol) + '</b></td>' +
      '<td>' + esc(s.paper_signal || s.signal || s.status || '—') +
      ' · mid ' + fmtNum(s.mid || s.last, 5) +
      ' · spread ' + fmtPips(s.spread_pips) + '</td></tr>').join('');
    const ledger = (o.ledger_latest_entries || []).map((e) => '<tr><td>' + esc((e.ts || '').slice(11, 19)) + '</td>' +
      '<td>' + esc(e.instrument || '') + ' · ' + esc(e.paper_signal || '—') +
      ' · ' + esc(e.paper_reason || '') + '</td></tr>').join('');
    return '<div class="fw-block"><h4>OANDA Floor 41 — live <span class="sub">paper · read-only · ' +
      esc(o.environment || 'practice') + '</span></h4><table class="detail-tbl">' +
      kv('Status', o.status) + kv('Environment', o.environment) +
      kv('Pricing ready', o.pricing_ready === null ? '—' : String(!!o.pricing_ready)) +
      kv('Account ready', o.account_ready === null ? '—' : String(!!o.account_ready)) +
      kv('Instruments', (o.default_instruments || []).join(', ')) +
      kv('Latest update', o.latest_ts) +
      kv('Live trading', '<span class="ok">OFF</span>') +
      kv('Order execution', '<span class="ok">OFF</span>') +
      kv('Practice orders', '<span class="ok">OFF</span>') + '</table>' +
      (sigRows ? '<h4 style="margin-top:8px">Paper signals</h4><table class="detail-tbl">' + sigRows + '</table>' : '') +
      (ledger ? '<h4 style="margin-top:8px">Ledger latest entries</h4><table class="detail-tbl">' + ledger + '</table>' : '') +
      '</div>';
  }
  function binanceBlock(d) {
    const b = d.binance;
    const rows = (b.results || []).map((r) => '<tr><td><b>' + esc(r.symbol) + '</b></td>' +
      '<td>' + esc(r.paper_signal || '—') + ' · mid ' + fmtNum(r.mid, 4) +
      ' · 24h Δ ' + fmtNum(r.pct_change_24h, 2) + '%</td></tr>').join('');
    return '<div class="fw-block"><h4>Binance Floor 42 — live <span class="sub">paper · read-only · ' +
      esc(b.environment || 'testnet') + '</span></h4><table class="detail-tbl">' +
      kv('Status', b.status) + kv('Environment', b.environment) +
      kv('Public market data ready', String(!!b.public_market_data_ready)) +
      kv('Account read ready', String(!!b.account_read_ready)) +
      kv('Symbols', (b.default_symbols || []).join(', ')) +
      kv('Latest update', b.latest_ts) +
      kv('Signal counts', JSON.stringify(b.signal_counts || {})) +
      kv('Binance order execution', '<span class="ok">OFF</span>') +
      kv('Binance live trading', '<span class="ok">OFF</span>') + '</table>' +
      (rows ? '<h4 style="margin-top:8px">Paper signals</h4><table class="detail-tbl">' + rows + '</table>' : '') +
      '</div>';
  }
  function stocksBlock(d) {
    const s = d.stock_exchange;
    const rows = (s.results || []).map((r) => '<tr><td><b>' + esc(r.symbol) + '</b></td>' +
      '<td>' + esc(r.paper_signal || '—') + ' · ' + esc(r.paper_reason || '') + '</td></tr>').join('');
    const cmStatus = s.cross_market_status || {};
    return '<div class="fw-block"><h4>Stock Exchange Floor 43 — live <span class="sub">paper · read-only · provider ' +
      esc(s.provider || 'alpaca') + '</span></h4><table class="detail-tbl">' +
      kv('Status', s.status) + kv('Provider', s.provider) + kv('Environment', s.environment) +
      kv('Market data ready', String(!!s.public_market_data_ready)) +
      kv('Account read ready', String(!!s.account_read_ready)) +
      kv('Symbols', (s.default_symbols || []).join(', ')) +
      kv('Latest update', s.latest_ts) +
      kv('Cross-market labels', (s.cross_market_labels || []).join(' · ')) +
      kv('OANDA bus', (cmStatus.oanda || {}).status) +
      kv('Binance bus', (cmStatus.binance || {}).status) +
      kv('Stocks bus', (cmStatus.stocks || {}).status) +
      kv('Stock order execution', '<span class="ok">OFF</span>') +
      kv('Stock paper orders', '<span class="ok">OFF</span>') +
      kv('Stock live trading', '<span class="ok">OFF</span>') + '</table>' +
      (rows ? '<h4 style="margin-top:8px">Paper signals</h4><table class="detail-tbl">' + rows + '</table>' : '') +
      '</div>';
  }
  function airllmBlock(d) {
    const a = d.airllm_chamber; const pv = a.package_versions || {};
    return '<div class="fw-block"><h4>AIR LLM Operations / AirLLM Big Model Chamber ' +
      '<span class="sub">advisory_only · not wired into AutoLoop/trading/OpenClaw</span></h4>' +
      '<table class="detail-tbl">' +
      kv('Chamber', a.chamber_name) + kv('Status', a.status) +
      kv('Path', '<code>' + esc(a.path) + '</code>') +
      kv('Venv', '<code>' + esc(a.venv_path) + '</code>') +
      kv('Env file', '<code>' + esc(a.env_file) + '</code>') +
      kv('Storage mount', '<code>' + esc(a.storage_mount) + '</code>') +
      kv('GPU', a.gpu_name) +
      kv('CUDA available', String(!!a.cuda_available)) +
      kv('AirLLM version', pv.airllm) + kv('Torch', pv.torch) + kv('Transformers', pv.transformers) +
      kv('Smoke test status', a.smoke_test_status) +
      kv('advisory_only', '<span class="ok">true</span>') +
      kv('execution_allowed', '<span class="ok">false</span>') +
      kv('trading_allowed', '<span class="ok">false</span>') +
      kv('autoloop_allowed', '<span class="ok">false</span>') +
      kv('openclaw_execution_allowed', '<span class="ok">false</span>') +
      kv('direct_provider_access', '<span class="ok">false</span>') +
      '</table>' +
      '<div class="tagline">Future manual "Ask Big Air Model" lane only. Never wired into the AutoLoop, trading floors, OpenClaw, or execution.</div>' +
      '</div>';
  }
  function riskBlock(d) {
    const r = d.risk; const locks = r.locks || {};
    const rows = Object.keys(locks).map((k) => '<tr><td><code>' + esc(k) + '</code></td>' +
      '<td><span class="' + (locks[k] ? 'bad' : 'ok') + '">' + (locks[k] ? 'TRUE' : 'false') + '</span></td></tr>').join('');
    return '<div class="fw-block"><h4>Permissions / Risk — lock matrix ' +
      '<span class="sub">' + esc(r.lock_count_true || 0) + ' / ' + esc(Object.keys(locks).length) + ' TRUE</span></h4>' +
      '<table class="detail-tbl">' + rows + '</table>' +
      '<div class="tagline ' + (r.lock_count_true ? 'warn' : 'ok') + '">Risk sources: ' +
      esc((r.risk_sources || []).join(' · ')) + '</div></div>';
  }
  function auditBlock(d) {
    const a = d.audit;
    const entries = (a.latest_entries || []).map((e) => '<tr><td>' + esc((e.ts || '').slice(11, 19)) + '</td>' +
      '<td>' + esc(e.instrument || '') + ' · ' + esc(e.paper_signal || '—') +
      ' · ' + esc(e.paper_reason || '') + '</td></tr>').join('');
    return '<div class="fw-block"><h4>Audit / Ledger <span class="sub">' + esc(a.entry_count || 0) +
      ' entries · paper-only audit trail</span></h4>' +
      '<table class="detail-tbl">' +
      kv('Entry count', a.entry_count) + kv('Latest count', a.latest_count) +
      kv('Updated', a.updated_ts) + kv('Downstream route', a.downstream_route) +
      '</table>' +
      (entries ? '<h4 style="margin-top:8px">Latest entries</h4><table class="detail-tbl">' + entries + '</table>' : '') +
      '</div>';
  }
  function strategyBlock(d) {
    const s = d.strategy;
    return '<div class="fw-block"><h4>Simulation Labs / Strategy Intelligence</h4><table class="detail-tbl">' +
      kv('Phase', s.phase) + kv('Latest', s.latest_ts) +
      kv('Signal counts', JSON.stringify(s.signal_counts || {})) +
      kv('Result count', s.result_count) + kv('Correlation ts', s.correlation_ts) +
      kv('Correlation count', s.correlation_count) +
      kv('Cross-market pairs', s.cross_market_pair_count) +
      kv('Inputs from', (s.inputs_from_floors || []).join(' · ')) +
      '</table></div>';
  }
  function sandboxBlock(d) {
    const s = d.sandbox;
    return '<div class="fw-block"><h4>Sandbox Operations <span class="sub">paper_only_background_loop</span></h4>' +
      '<table class="detail-tbl">' +
      kv('Worker tick ts', s.worker_sandbox_latest_tick_ts) +
      kv('Lift packet count', s.lift_packet_count) +
      kv('OpenClaw ts', s.openclaw_ts) +
      kv('OpenClaw recs', s.openclaw_recommendation_count) +
      kv('Sandbox perf ts', s.sandbox_performance_ts) +
      kv('AutoLoop status', s.autoloop_status) +
      kv('AutoLoop cycle', s.autoloop_cycle_index) +
      kv('AutoLoop mode', s.autoloop_mode) +
      kv('worker_execution_enabled', '<span class="ok">false</span>') +
      kv('openclaw_execution_enabled', '<span class="ok">false</span>') +
      '</table></div>';
  }
  function commandBlock(d) {
    const c = d.command;
    return '<div class="fw-block"><h4>Tower Command Department</h4><table class="detail-tbl">' +
      kv('Building', c.building_name) +
      kv('Kernel installed', String(!!c.kernel_installed)) +
      kv('QSBKernelCore instantiated', String(!!c.QSBKernelCore_instantiated)) +
      kv('Activation', c.activation_status) +
      kv('Kernel source', c.active_kernel_source) +
      kv('Routes to penthouse', String(!!c.command_routes_to_penthouse)) +
      '</table></div>';
  }
  function roofBlock(d) {
    return '<div class="fw-block"><h4>Roof — External Providers (LOCKED)</h4><table class="detail-tbl">' +
      kv('Status', 'LOCKED') +
      kv('external_providers_enabled', '<span class="ok">false</span>') +
      kv('direct_provider_access', '<span class="ok">false</span>') +
      '</table></div>';
  }
  function groundBlock(d) {
    return '<div class="fw-block"><h4>Ground / Reception Lobby</h4><table class="detail-tbl">' +
      kv('Department', d.ground.department) +
      kv('Lift access', String(!!d.ground.lift_access)) +
      '</table></div>';
  }
  function towerOpsBlock(d) {
    const fm = d.floor_manager || {};
    const zm = d.zone_manager || {};
    const tom = d.tower_operations_manager || {};
    const kl = d.kernel_liaison_manager || {};
    const ovs = d.overseers || [];
    const roster = d.roster || [];
    const rosterLabel = d.roster_label || 'Real Local Workers';
    const fmName = fm.display_name || '—';
    const zmName = zm.display_name || '—';
    return '<div class="fw-block tower-ops-block"><h4>Tower Operations — Management Chain ' +
      '<span class="sub">' + esc(rosterLabel) + ' · ' + (d.worker_count || roster.length) + ' on this floor</span></h4>' +
      '<table class="detail-tbl">' +
        kv('Floor Manager', esc(fmName)) +
        kv('Zone Manager', esc(zmName) + (zm.assigned_scope && zm.assigned_scope.floors ? ' (zone covers ' + (zm.assigned_scope.floors || []).length + ' floors)' : '')) +
        kv('Tower Operations Manager', esc(tom.display_name || 'Tower Operations Manager')) +
        kv('Kernel Liaison Manager', esc(kl.display_name || 'Kernel Liaison Manager')) +
        kv('Reports to', esc((fm.reports_to || zm.display_name || 'Tower Operations Manager') + ' → ' + (tom.reports_to || 'QSB Kernel'))) +
        kv('Overseers', ovs.length ? ovs.map((o) => esc(o.display_name)).join(' · ') : '—') +
      '</table>' +
      (roster.length ?
        '<h4 style="margin-top:8px">Worker Roster Wall <span class="sub">' + roster.length + '</span></h4>' +
        '<div class="rc-roster">' + roster.slice(0, 20).map((w) =>
          '<div class="rc-card">' +
          '<div class="rc-card-row">' +
            '<span class="rc-name">' + esc(w.display_name || w.id) + '</span>' +
            '<span class="rc-stage rc-stage-' + esc(w.stage) + '">' + esc(w.stage || '') + '</span>' +
          '</div>' +
          '<div class="rc-card-meta">' + esc(w.role || '') + '</div>' +
          '<div class="rc-card-row">' +
            '<span class="rc-floor">desk: ' + esc(w.desk_assignment || '—') + '</span>' +
            '<span class="rc-pill ' + (w.openclaw_ready ? 'rc-pill-ready' : 'rc-pill-locked') + '">OC ready: ' + String(!!w.openclaw_ready) + '</span>' +
          '</div>' +
          '<div class="rc-card-row">' +
            '<span class="rc-meta">hb: ' + esc((w.heartbeat_ts || '').slice(11, 19)) + '</span>' +
            '<span class="rc-meta">task: ' + esc(w.current_task || '—') + '</span>' +
          '</div>' +
          '</div>').join('') +
        '</div>' +
        (roster.length > 20 ? '<div class="tagline">… ' + (roster.length - 20) + ' more</div>' : '')
        : '<div class="tagline">No real workers homed at this floor yet.</div>') +
      '</div>';
  }

  function safetyBlock(d) {
    const locks = d.locks || {};
    const lockTrue = Object.values(locks).filter((v) => v === true).length;
    return '<div class="fw-block"><h4>Safety <span class="sub">' + lockTrue + ' / ' +
      Object.keys(locks).length + ' locks TRUE — expected 0</span></h4><table class="detail-tbl">' +
      kv('execution_allowed', '<span class="ok">' + esc(String(d.execution_allowed)) + '</span>') +
      kv('paper_only', '<span class="ok">' + esc(String(d.paper_only)) + '</span>') +
      kv('not_financial_advice', '<span class="ok">' + esc(String(d.not_financial_advice)) + '</span>') +
      kv('advisory_only', String(!!d.advisory_only)) +
      kv('read_only', String(!!d.read_only)) +
      '</table></div>';
  }

  // ── Penthouse live console — kernel chat + speech strip ──────────────
  function mountPenthouseConsole(main, d) {
    const p = d.penthouse || {};
    const box = document.createElement('div');
    box.className = 'fw-block penthouse-console';
    box.innerHTML = '<h4>Penthouse Kernel Command Chamber — Live Console ' +
      '<span class="sub" id="pcStatus">probing…</span></h4>' +
      '<div class="pc-speech-strip">' +
      '<button class="mini-btn" id="pcMic" title="Voice in (browser STT)">🎤 Mic: Off</button>' +
      '<button class="mini-btn" id="pcSpeaker" title="Voice out (browser TTS)">🔈 Speaker: Off</button>' +
      '<button class="mini-btn" id="pcMute" title="Cancel current speech">⏹ Mute</button>' +
      '<span class="pc-engine">tts: ' + esc(p.tts_engine || 'browser_web_speech_synthesis') + '</span>' +
      '<span class="pc-engine">stt: ' + esc(p.stt_engine || 'browser_web_speech_recognition') + '</span>' +
      '<span class="pc-engine">speech: <code data-route-floor="15">floor_15</code></span>' +
      '<span class="pc-engine">media: <code data-route-floor="14">floor_14</code></span>' +
      '</div>' +
      '<div id="pcChatLog" class="chat-log pc-chat-log"></div>' +
      '<div class="chat-row">' +
      '<input id="pcChatInput" placeholder="probing sidecar…" disabled>' +
      '<button id="pcChatSend" disabled>Send</button>' +
      '<button class="mini-btn" id="pcChatProbe" title="Re-probe sidecar">⟳</button>' +
      '<button class="mini-btn" id="pcChatDiag" title="Kernel chat diagnostics">🩺 Diag</button>' +
      '</div>';
    main.appendChild(box);

    const status = box.querySelector('#pcStatus');
    const log    = box.querySelector('#pcChatLog');
    const input  = box.querySelector('#pcChatInput');
    const sendBt = box.querySelector('#pcChatSend');
    const probe  = box.querySelector('#pcChatProbe');
    const micBt  = box.querySelector('#pcMic');
    const spkBt  = box.querySelector('#pcSpeaker');
    const muteBt = box.querySelector('#pcMute');

    let speakerOn = false;
    let micOn = false;
    let recog = null;

    function setSidecar(avail, label) {
      status.textContent = label;
      status.className = 'sub ' + (avail ? 'ok' : 'warn');
      input.disabled = !avail;
      sendBt.disabled = !avail;
      input.placeholder = avail ? 'Talk to Kernel…' :
                                  'Kernel core active. Chat endpoint offline. View-only.';
    }

    function appendRow(cls, text) {
      const row = document.createElement('div');
      row.className = 'row ' + cls;
      row.textContent = text;
      log.appendChild(row);
      log.scrollTop = log.scrollHeight;
    }

    async function fetchStatus() {
      setSidecar(false, 'probing…');
      try {
        const r = await fetch('/api/kernel_chat_status', { cache: 'no-store' });
        const s = await r.json();
        const route = s.active_route || (s.sidecar_available ? 'kernel_chat_sidecar_8766' :
                       s.dashboard_local_kernel_dialogue ? 'dashboard_local_kernel_dialogue' : 'view_only');
        const lab = s.available
          ? (route === 'kernel_chat_sidecar_8766'
              ? ('sidecar :8766 · ' + (s.selected_model || 'kernel'))
              : ('dashboard-local · ' + (s.selected_model || 'kernel')))
          : 'disconnected';
        setSidecar(!!s.available, lab);
        if (s.available) {
          appendRow('system', (route === 'kernel_chat_sidecar_8766'
            ? 'Connected · sidecar :8766 · model: '
            : 'Connected · dashboard-local · model: ') + (s.selected_model || 'kernel'));
          // Load short history
          try {
            const h = await fetch('/api/kernel_chat_history', { cache: 'no-store' }).then((r) => r.json());
            (h && h.history || []).slice(-6).forEach((x) => {
              if (x.message) appendRow('user',   '> ' + String(x.message).slice(0, 200));
              if (x.reply)   appendRow('kernel', String(x.reply).slice(0, 240));
            });
          } catch (e) {}
        } else {
          appendRow('system', s.view_only_message || 'Kernel core active. Chat endpoint offline. View-only.');
        }
      } catch (e) {
        setSidecar(false, 'status probe failed');
      }
    }

    async function sendMsg() {
      const msg = (input.value || '').trim();
      if (!msg) return;
      appendRow('user', '> ' + msg);
      input.value = '';
      setSidecar(true, 'thinking…');
      try {
        const r = await fetch('/api/kernel_chat', {
          method: 'POST',
          headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify({ message: msg, text: msg }),
        });
        const j = await r.json();
        const reply = (j && (j.reply || j.text || j.message)) || JSON.stringify(j).slice(0, 240);
        appendRow('kernel', reply);
        setSidecar(true, 'response received');
        if (speakerOn && window.QSB_SPEECH) {
          window.QSB_SPEECH.speak(String(reply).slice(0, 600));
        }
      } catch (e) {
        appendRow('system', 'send failed: ' + e);
        setSidecar(false, 'error');
      }
    }

    probe.addEventListener('click', fetchStatus);
    sendBt.addEventListener('click', sendMsg);
    input.addEventListener('keydown', (e) => { if (e.key === 'Enter') sendMsg(); });
    const pcDiag = box.querySelector('#pcChatDiag');
    if (pcDiag) pcDiag.addEventListener('click', () => {
      fetch('/api/kernel_chat_diagnostics').then((r) => r.json()).then((j) => {
        window.QSB_WINDOWS.open('chat-diag', {
          title: 'Kernel Chat Diagnostics',
          width: 560, height: 460,
          render: (b) => {
            b.innerHTML = '<pre style="background:rgba(0,8,22,.6);padding:8px;border-radius:6px;font-size:11px;color:#cfe6ff;white-space:pre-wrap">' +
              esc(JSON.stringify(j, null, 2)) + '</pre>';
          },
        });
      });
    });

    spkBt.addEventListener('click', () => {
      speakerOn = !speakerOn;
      spkBt.textContent = speakerOn ? '🔊 Speaker: On' : '🔈 Speaker: Off';
      spkBt.classList.toggle('active', speakerOn);
      if (speakerOn && window.QSB_SPEECH) {
        window.QSB_SPEECH.speak('Speaker on');
      }
    });

    micBt.addEventListener('click', () => {
      const SR = window.SpeechRecognition || window.webkitSpeechRecognition;
      if (!SR) { appendRow('system', 'Browser SpeechRecognition not supported here.'); return; }
      if (micOn && recog) { try { recog.stop(); } catch (e) {} micOn = false; micBt.textContent = '🎤 Mic: Off'; micBt.classList.remove('active'); return; }
      recog = new SR();
      recog.continuous = false; recog.interimResults = false; recog.lang = navigator.language || 'en-US';
      recog.onresult = (ev) => {
        const txt = ev.results[0][0].transcript;
        input.value = txt;
        sendMsg();
      };
      recog.onerror = (ev) => { appendRow('system', 'mic error: ' + (ev.error || ev.message || 'unknown')); };
      recog.onend = () => { micOn = false; micBt.textContent = '🎤 Mic: Off'; micBt.classList.remove('active'); };
      try { recog.start(); micOn = true; micBt.textContent = '🎤 Mic: Listening'; micBt.classList.add('active'); }
      catch (e) { appendRow('system', 'mic start failed: ' + e); }
    });

    muteBt.addEventListener('click', () => {
      try { window.speechSynthesis && window.speechSynthesis.cancel(); } catch (e) {}
    });

    fetchStatus();
  }

  // ── Floor 38 Recruitment Agency live console ──────────────────────────
  function mountRecruitmentConsole(main, d) {
    const ra = d.recruitment_agency || {};
    const box = document.createElement('div');
    box.className = 'fw-block recruitment-console';
    box.innerHTML = '<h4>Worker Recruitment Agency — Real Local Workers · Live Console ' +
      '<span class="sub">total ' + (ra.total_workers || 0) + ' · advisory ' + (ra.active_advisory || 0) +
      ' · read-only ' + (ra.active_read_only || 0) + ' · ready_for_openclaw_review ' + (ra.ready_for_openclaw_review || 0) +
      ' · openclaw_ready ' + (ra.openclaw_ready_count || 0) + '</span></h4>' +
      '<div class="rc-actions">' +
      '<button class="mini-btn" id="rcRefresh">⟳ Refresh</button>' +
      '<button class="mini-btn" id="rcRecruit">+ Recruit Worker</button>' +
      '<span class="rc-lock"><span class="ok">OpenClaw execution: false</span> · <span class="ok">recruitment_openclaw_execution_enabled: false</span></span>' +
      '</div>' +
      '<div id="rcRoster" class="rc-roster"></div>';
    main.appendChild(box);

    const roster = box.querySelector('#rcRoster');
    function paintRoster(workers) {
      roster.innerHTML = workers.map((w) =>
        '<div class="rc-card" data-wid="' + esc(w.id) + '">' +
        '<div class="rc-card-row">' +
          '<span class="rc-name">' + esc(w.display_name) + '</span>' +
          '<span class="rc-stage rc-stage-' + esc(w.stage) + '">' + esc(w.stage) + '</span>' +
        '</div>' +
        '<div class="rc-card-meta">' + esc(w.role || '') + '</div>' +
        '<div class="rc-card-row">' +
          '<span class="rc-floor">home: <code data-route-floor="' + esc(parseFloorFromId(w.floor_assignment)) + '">' + esc(w.floor_assignment) + '</code></span>' +
          '<span class="rc-floor">desk: ' + esc(w.desk_assignment || '—') + '</span>' +
        '</div>' +
        '<div class="rc-card-row">' +
          '<span class="rc-pill ' + (w.openclaw_ready ? 'rc-pill-ready' : 'rc-pill-locked') + '">OpenClaw ready: ' + String(!!w.openclaw_ready) + '</span>' +
          '<span class="rc-pill rc-pill-locked">execution: OFF</span>' +
          '<span class="rc-pill rc-pill-locked">provider: OFF</span>' +
        '</div>' +
        '<div class="rc-card-row">' +
          '<span class="rc-meta">heartbeat: ' + esc((w.heartbeat_ts || '').slice(11, 19)) + '</span>' +
          '<span class="rc-meta">task: ' + esc(w.current_task || '—') + '</span>' +
        '</div>' +
        '<div class="rc-card-actions">' +
          '<button class="mini-btn" data-rc-act="openclaw_review" data-wid="' + esc(w.id) + '">Send to OpenClaw Review</button>' +
          '<button class="mini-btn" data-rc-act="onboard" data-wid="' + esc(w.id) + '">Onboard</button>' +
          '<button class="mini-btn" data-rc-act="probation" data-wid="' + esc(w.id) + '">Probation</button>' +
          '<button class="mini-btn" data-rc-act="advisory" data-wid="' + esc(w.id) + '">Active Advisory</button>' +
          '<button class="mini-btn" data-rc-act="retire" data-wid="' + esc(w.id) + '">Retire</button>' +
        '</div>' +
        '</div>').join('');
      roster.querySelectorAll('button[data-rc-act]').forEach((b) => {
        b.addEventListener('click', () => handleRecruitAction(b.dataset.rcAct, b.dataset.wid));
      });
    }
    function parseFloorFromId(id) {
      const m = /^floor_(\d{1,2})$/.exec(id || '');
      return m ? m[1] : '';
    }
    async function refresh() {
      const w = await fetch('/api/recruitment/workers', { cache: 'no-store' }).then((r) => r.json());
      paintRoster(w.workers || []);
    }
    box.querySelector('#rcRefresh').addEventListener('click', refresh);
    box.querySelector('#rcRecruit').addEventListener('click', async () => {
      const name = prompt('Display name for the new worker:');
      if (!name) return;
      const role = prompt('Role (one line):') || 'Recruited worker.';
      const team = prompt('Team (e.g. trading_fx, openclaw_advisory, speech_media, airllm_advisory):') || 'general';
      await fetch('/api/recruitment/recruit', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ display_name: name, role, team, floor_assignment: 'floor_38', desk_assignment: 'Reception Desk' }),
      });
      refresh();
    });

    async function handleRecruitAction(action, wid) {
      let route = '', body = { worker_id: wid };
      if (action === 'openclaw_review') route = '/api/recruitment/openclaw_review';
      else if (action === 'onboard')    { route = '/api/recruitment/assign'; body.stage = 'onboarded'; }
      else if (action === 'probation')  { route = '/api/recruitment/assign'; body.stage = 'probation'; }
      else if (action === 'advisory')   { route = '/api/recruitment/assign'; body.stage = 'active_advisory'; }
      else if (action === 'retire')     route = '/api/recruitment/retire';
      else return;
      const r = await fetch(route, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify(body),
      });
      const j = await r.json();
      if (j && j.ok) refresh();
      else alert((j && j.error) || 'unknown error');
    }

    refresh();
  }

  // ── Accounts console (Floor 44) ─────────────────────────────────────
  function mountAccountsConsole(main, d) {
    const box = document.createElement('div');
    box.className = 'fw-block dept-console';
    box.innerHTML = '<h4>Accounts Department — Tower-wide read-only ledger summary ' +
      '<span class="sub" id="acSub">loading…</span></h4>' +
      '<div id="acBody"></div>';
    main.appendChild(box);
    Promise.all([
      fetch('/api/accounts/status').then((r)=>r.json()),
      fetch('/api/accounts/trading_summary').then((r)=>r.json()),
      fetch('/api/accounts/paper_ledger_summary').then((r)=>r.json()),
      fetch('/api/accounts/floor_accountants').then((r)=>r.json()),
      fetch('/api/accounts/not_configured').then((r)=>r.json()),
    ]).then(([s, t, p, fa, nc]) => {
      const sub = box.querySelector('#acSub');
      const bd = box.querySelector('#acBody');
      sub.textContent = s.policy || 'READ_ONLY';
      sub.className = 'sub ok';
      const trading = t || {};
      const html =
        '<h4 style="margin-top:8px">Trading Summary</h4><table class="detail-tbl">' +
        kv('OANDA account label',   esc((trading.oanda||{}).account_label || '—')) +
        kv('OANDA pnl label',       esc((trading.oanda||{}).pnl_label || '—')) +
        kv('OANDA balance / NAV',   esc(((trading.oanda||{}).balance || '—') + ' / ' + ((trading.oanda||{}).NAV || '—'))) +
        kv('Binance account label', esc((trading.binance||{}).account_label || '—')) +
        kv('Binance pnl label',     esc((trading.binance||{}).pnl_label || '—')) +
        kv('Stocks account label',  esc((trading.stocks||{}).account_label || '—')) +
        kv('Stocks pnl label',      esc((trading.stocks||{}).pnl_label || '—')) +
        '</table>' +
        '<h4 style="margin-top:8px">Paper Ledger</h4><table class="detail-tbl">' +
        kv('entry_count',  (p.paper_ledger||{}).entry_count || 0) +
        kv('latest_count', (p.paper_ledger||{}).latest_count || 0) +
        kv('updated_ts',   (p.paper_ledger||{}).updated_ts) +
        '</table>' +
        '<h4 style="margin-top:8px">Not Configured Board</h4><table class="detail-tbl">' +
        (nc.not_configured || []).map((x) => kv(esc(x.endpoint), esc(x.reason))).join('') +
        '</table>' +
        '<h4 style="margin-top:8px">Floor Accountants Index</h4>' +
        '<div class="tagline">Floor accountants reach each populated floor via the per-floor Worker Roster Wall.</div>';
      bd.innerHTML = html;
    });
  }

  // ── Quantum console (Floor 45) ──────────────────────────────────────
  function mountQuantumConsole(main, d) {
    const box = document.createElement('div');
    box.className = 'fw-block dept-console';
    box.innerHTML = '<h4>Quantum Operations Department <span class="sub" id="qSub">loading…</span></h4>' +
      '<div id="qBody"></div>';
    main.appendChild(box);
    fetch('/api/quantum/status').then((r) => r.json()).then((s) => {
      const sub = box.querySelector('#qSub');
      const bd  = box.querySelector('#qBody');
      sub.textContent = s.label || 'QUANTUM LAB';
      sub.className = 'sub ' + (s.any_quantum_runtime_installed ? 'ok' : 'warn');
      const runtimes = (s.runtimes_detected || []).map((r) =>
        '<tr><td>' + esc(r.package) + '</td><td>' +
        (r.installed ? '<span class="ok">installed · ' + esc(r.version || '') + '</span>' : '<span class="warn">not installed</span>') +
        '</td></tr>').join('');
      bd.innerHTML = '<table class="detail-tbl">' +
        kv('Label', esc(s.label)) +
        kv('Policy', esc(s.policy)) +

        '</table>' +
        '<h4 style="margin-top:8px">Runtime Detection</h4>' +
        '<table class="detail-tbl">' + runtimes + '</table>';
    });
  }

  // ── Lifts console (Floor 22 — Lift Operations) ──────────────────────
  function mountLiftsConsole(main, d) {
    const box = document.createElement('div');
    box.className = 'fw-block dept-console';
    box.innerHTML = '<h4>Lift Operations — 9 lifts (read-only) <span class="sub" id="lSub">loading…</span></h4>' +
      '<div id="lBody"></div>';
    main.appendChild(box);
    function refresh() {
      fetch('/api/lifts/status').then((r) => r.json()).then((s) => {
        box.querySelector('#lSub').textContent = (s.lifts || []).length + ' lifts active';
        box.querySelector('#lSub').className = 'sub ok';
        const rows = (s.lifts || []).map((L) =>
          '<tr><td><b>' + esc(L.lift_id) + '</b> · ' + esc(L.name) + '</td>' +
          '<td>floor ' + esc(L.current_floor) + ' → ' + esc(L.target_floor) +
          ' · <span class="' + (L.status === 'moving' ? 'ok' : 'warn') + '">' + esc(L.status) + '</span>' +
          ' · occupancy ' + L.occupancy_count + '</td></tr>' +
          (L.workers_inside || []).map((w) =>
            '<tr><td style="padding-left:18px;color:#9fc4ff">↳ ' + esc(w.short_code || w.display_name) + '</td>' +
            '<td>' + esc(w.display_name) + '</td></tr>').join('')).join('');
        box.querySelector('#lBody').innerHTML = '<table class="detail-tbl">' + rows + '</table>';
      });
    }
    refresh();
    box._timer = setInterval(refresh, 4000);
  }

  // ── Model Ops console (Floor 24) ────────────────────────────────────
  function mountModelOpsConsole(main, d) {
    const box = document.createElement('div');
    box.className = 'fw-block dept-console';
    box.innerHTML = '<h4>Model Operations — Lane Router <span class="sub" id="moSub">loading…</span></h4>' +
      '<div id="moBody"></div>';
    main.appendChild(box);
    Promise.all([fetch('/api/models/status').then((r)=>r.json()),
                  fetch('/api/models/lanes').then((r)=>r.json()),
                  fetch('/api/models/router').then((r)=>r.json())])
      .then(([s, l, r]) => {
        box.querySelector('#moSub').textContent = 'selected: ' + (s.selected_model || '—');
        box.querySelector('#moSub').className = 'sub ok';
        const lanes = (l.lanes || []).map((ln) =>
          '<tr><td><b>' + esc(ln.lane) + '</b></td>' +
          '<td>status: <span class="' + (ln.status === 'active' || ln.status === 'reachable' || ln.status === 'installed_advisory_only' ? 'ok' : ln.status === 'LOCKED' ? 'warn' : 'warn') + '">' + esc(ln.status) + '</span>' +
          ' · model: ' + esc(ln.model || '—') + '</td></tr>').join('');
        const router = r.router || {};
        const routerRows = Object.keys(router).map((k) => kv(esc(k), esc(router[k]))).join('');
        box.querySelector('#moBody').innerHTML =
          '<h4 style="margin-top:8px">Lanes</h4><table class="detail-tbl">' + lanes + '</table>' +
          '<h4 style="margin-top:8px">Router</h4><table class="detail-tbl">' + routerRows + '</table>';
      });
  }

  // ── Missing Floors Panel ────────────────────────────────────────────
  function mountMissingFloorsPanel(main, d) {
    const box = document.createElement('div');
    box.className = 'fw-block missing-panel';
    box.innerHTML = '<h4>Missing / Unbuilt Floors Inventory <span class="sub" id="mfSub">loading…</span></h4>' +
      '<div id="mfBody"></div>';
    main.appendChild(box);
    fetch('/api/tower_ops/missing').then((r) => r.json()).then((m) => {
      box.querySelector('#mfSub').textContent = 'live ' + m.fully_live_count + ' · staffed ' +
        m.staffed_only_count + ' · missing ' + m.missing_count;
      box.querySelector('#mfSub').className = 'sub ' + (m.missing_count > 0 ? 'warn' : 'ok');
      const rows = '<tr><th>Department</th><th>Floor</th><th>Status</th><th>Next action</th></tr>' +
        (m.departments || []).map((r) =>
          '<tr><td>' + esc(r.department) + '</td>' +
          '<td>' + (r.floor_id ? '<code data-route-floor="' + esc(String(r.floor_id).replace('floor_','')) + '">' + esc(r.floor_id) + '</code>' : '—') + '</td>' +
          '<td><span class="' + (r.status === 'live' ? 'ok' : r.status === 'staffed' ? 'warn' : 'bad') + '">' + esc(r.status) + '</span></td>' +
          '<td>' + esc(r.next_action) + '</td></tr>').join('');
      box.querySelector('#mfBody').innerHTML = '<table class="detail-tbl">' + rows + '</table>';
    });
  }

  // ── Generic department-status console builder (Maintenance / Security / IT / Research) ──
  function mountDepartmentConsole(main, title, statusUrl, extraUrls) {
    const box = document.createElement('div');
    box.className = 'fw-block dept-console';
    box.innerHTML = '<h4>' + esc(title) + ' <span class="sub" id="dcSub">probing…</span></h4>' +
      '<div id="dcBody"></div>';
    main.appendChild(box);
    const sub = box.querySelector('#dcSub');
    const body = box.querySelector('#dcBody');
    fetch(statusUrl, { cache: 'no-store' }).then((r) => r.json()).then((d) => {
      sub.textContent = (d.overall_status || (d.ok ? 'ok' : 'error')) + ' · ' + (d.policy || '');
      sub.className = 'sub ' + (d.overall_status === 'healthy' ? 'ok' : 'warn');
      const rows = Object.keys(d).filter((k) => !['ok','ts','phase','policy','overall_status','locks'].includes(k) &&
                                                  !k.endsWith('_enabled') && k !== 'paper_only' && k !== 'execution_allowed' &&
                                                  k !== 'advisory_only' && k !== 'read_only' && k !== 'not_financial_advice');
      let html = '<table class="detail-tbl">';
      for (const k of rows.slice(0, 12)) {
        let v = d[k];
        if (typeof v === 'object') v = JSON.stringify(v).slice(0, 140);
        html += kv(k, esc(String(v)));
      }
      html += '</table>';
      body.innerHTML = html;
      // Append additional endpoints inline
      if (extraUrls) {
        for (const [label, url] of extraUrls) {
          const sub2 = document.createElement('div');
          sub2.innerHTML = '<h4 style="margin-top:8px">' + esc(label) + ' <span class="sub">loading…</span></h4><div></div>';
          body.appendChild(sub2);
          fetch(url, { cache: 'no-store' }).then((r) => r.json()).then((d2) => {
            sub2.innerHTML = '<h4 style="margin-top:8px">' + esc(label) + '</h4>' +
              '<pre class="dept-pre">' + esc(JSON.stringify(d2, null, 2).slice(0, 1800)) + '</pre>';
          }).catch((e) => { sub2.querySelector('.sub') && (sub2.querySelector('.sub').textContent = 'error: ' + e); });
        }
      }
    }).catch((e) => { sub.textContent = 'fetch failed: ' + e; });
  }
  function mountMaintenanceConsole(main, d) {
    mountDepartmentConsole(main, 'Diagnostics / Maintenance — Live Checks (read-only, no auto-repair)',
      '/api/maintenance/checks', [['Service health', '/api/maintenance/status']]);
  }
  function mountSecurityConsole(main, d) {
    mountDepartmentConsole(main, 'Security — Lock Matrix Wall', '/api/security/status',
      [['Locks', '/api/security/locks'], ['Incidents', '/api/security/incidents']]);
  }
  function mountITConsole(main, d) {
    mountDepartmentConsole(main, 'IT / Networking — Observability', '/api/it/status',
      [['Ports', '/api/it/ports'], ['Sidecars', '/api/it/sidecars'],
       ['DNS connectivity', '/api/it/connectivity'], ['Dashboard routes', '/api/it/routes']]);
  }
  function mountResearchConsole(main, d) {
    mountDepartmentConsole(main, 'Research Facility — Local Task Queue (web gate LOCKED)', '/api/research/status',
      [['Tasks', '/api/research/tasks']]);
  }

  // ── Live read-only trading telemetry consoles ───────────────────────
  function _telemetryBlock(title, url) {
    const wrapId = 'tb_' + Math.random().toString(36).slice(2, 8);
    const html = '<div class="fw-block telemetry-console" id="' + wrapId + '">' +
      '<h4>' + esc(title) + ' <span class="sub">loading…</span></h4>' +
      '<div class="tb-body">probing…</div></div>';
    return { html, wrapId, url };
  }
  function _populateTelemetry(main, blocks) {
    main.insertAdjacentHTML('beforeend', blocks.map((b) => b.html).join(''));
    blocks.forEach((b) => {
      fetch(b.url, { cache: 'no-store' }).then((r) => r.json()).then((d) => {
        const box = main.querySelector('#' + b.wrapId);
        if (!box) return;
        const isLive = d.label === 'LIVE READ-ONLY';
        const isNotConfigured = d.status === 'not_configured';
        const labelClass = isLive ? 'ok' : (isNotConfigured ? 'warn' : 'bad');
        const labelText = isLive ? 'LIVE READ-ONLY' :
                          isNotConfigured ? 'NOT CONFIGURED' : 'ERROR';
        let bodyHtml = '<table class="detail-tbl">';
        const skip = new Set(['ok','ts','phase','policy','label','status']);
        Object.keys(LOCK_LABELS_MAP).forEach((k) => skip.add(k));
        for (const k of Object.keys(d)) {
          if (skip.has(k)) continue;
          if (k.endsWith('_enabled')) continue;
          if (['execution_allowed','paper_only','advisory_only','read_only','not_financial_advice'].includes(k)) continue;
          let v = d[k];
          if (typeof v === 'object') v = JSON.stringify(v).slice(0, 200);
          bodyHtml += kv(k, esc(String(v)));
        }
        bodyHtml += '</table>';
        bodyHtml += '<div class="tagline ' + (isLive ? 'ok' : 'warn') + '">' +
          'reason: ' + esc(d.reason || (isLive ? 'live data available' : '—')) + '</div>';
        box.querySelector('h4 .sub').textContent = labelText;
        box.querySelector('h4 .sub').className = 'sub ' + labelClass;
        box.querySelector('.tb-body').innerHTML = bodyHtml;
      }).catch((e) => {
        const box = main.querySelector('#' + b.wrapId);
        if (box) box.querySelector('.tb-body').innerHTML = '<div class="tagline warn">fetch error: ' + esc(e) + '</div>';
      });
    });
  }
  const LOCK_LABELS_MAP = LOCK_LABELS.reduce((m, [k]) => (m[k] = true, m), {});
  // ── Floor 41 PRACTICE TRADING ROOM — production-grade ─────────────────
  function mountOandaPracticeTradingRoom(main, d) {
    const box = document.createElement('div');
    box.className = 'fw-block oanda-practice-room';
    box.innerHTML =
      '<h4>OANDA PRACTICE TRADING ROOM — PRACTICE ACCOUNT ONLY ' +
      '<span class="sub" id="otSub">loading…</span></h4>' +
      '<div class="oanda-banner">' +
      '<span class="oanda-chip ok">OANDA PRACTICE: ON</span>' +
      '<span class="oanda-chip ok">LIVE REAL MONEY: OFF</span>' +
      '<span class="oanda-chip ok">OPENCLAW REAL EXECUTION: OFF</span>' +
      '<span class="oanda-chip warn" id="otKill">KILL SWITCH: probing…</span>' +
      '</div>' +
      '<div class="oanda-grid">' +
      '<div class="oanda-cell" id="otAccount">' +
        '<h5>Account Wall</h5><div>loading…</div></div>' +
      '<div class="oanda-cell" id="otPricing">' +
        '<h5>Live Pricing Stream</h5><div>loading…</div></div>' +
      '<div class="oanda-cell" id="otPositions">' +
        '<h5>Open Positions Board</h5><div>loading…</div></div>' +
      '<div class="oanda-cell" id="otTrades">' +
        '<h5>Open Trades Board</h5><div>loading…</div></div>' +
      '<div class="oanda-cell" id="otLedger">' +
        '<h5>Practice Ledger</h5><div>loading…</div></div>' +
      '<div class="oanda-cell" id="otGuards">' +
        '<h5>Guardrails</h5><div>loading…</div></div>' +
      '</div>' +
      '<div class="oanda-actions">' +
      '<button class="mini-btn" data-ot="preflight">Run Practice Preflight</button>' +
      '<button class="mini-btn" data-ot="preview_buy_eur">Preview 100 Unit EUR_USD Buy</button>' +
      '<button class="mini-btn" data-ot="preview_sell_eur">Preview 100 Unit EUR_USD Sell</button>' +
      '<button class="mini-btn" data-ot="preview_custom">Preview Custom Practice Order</button>' +
      '<button class="mini-btn" id="otConfirmBtn" data-ot="place_confirmed" disabled>Place Confirmed Practice Order</button>' +
      '<button class="mini-btn" data-ot="refresh">Refresh Open Trades + P&L</button>' +
      '<button class="mini-btn" data-ot="kill_on">Activate Kill Switch</button>' +
      '<button class="mini-btn" data-ot="kill_off">Deactivate Kill Switch</button>' +
      '<button class="mini-btn" data-ot="open_ledger">Open Practice Ledger</button>' +
      '</div>' +
      '<div id="otLastPreview" class="oanda-preview"></div>';
    main.appendChild(box);

    let pendingOrder = null;
    const sub      = box.querySelector('#otSub');
    const killChip = box.querySelector('#otKill');
    const confirmBt= box.querySelector('#otConfirmBtn');
    const previewBox = box.querySelector('#otLastPreview');

    function refreshAll() {
      Promise.all([
        fetch('/api/trading/oanda/account').then((r)=>r.json()),
        fetch('/api/trading/oanda/pricing').then((r)=>r.json()),
        fetch('/api/trading/oanda/open_positions').then((r)=>r.json()),
        fetch('/api/trading/oanda/open_trades').then((r)=>r.json()),
        fetch('/api/trading/oanda/practice_ledger').then((r)=>r.json()),
        fetch('/api/trading/oanda/order_guard').then((r)=>r.json()),
      ]).then(([ac, pr, pos, tr, led, gu]) => {
        sub.textContent = (ac.ok ? ac.label + ' · ' + (ac.environment || 'practice') : 'not configured');
        sub.className = 'sub ' + (ac.ok ? 'ok' : 'warn');
        // Account Wall
        box.querySelector('#otAccount div').innerHTML = ac.ok ?
          '<table class="detail-tbl">' +
          kv('account_id', '<code>' + esc(ac.account_id_redacted || '—') + '</code>') +
          kv('environment', esc(ac.environment)) +
          kv('balance',    fmtNum(ac.balance, 2)) +
          kv('NAV',        fmtNum(ac.NAV, 2)) +
          kv('margin_used',     fmtNum(ac.margin_used, 2)) +
          kv('margin_available',fmtNum(ac.margin_available, 2)) +
          kv('unrealized_pl',   fmtNum(ac.unrealized_pl, 2)) +
          kv('realized_pl_today', fmtNum(ac.realized_pl_today, 2)) +
          kv('open_trade_count',    String(ac.open_trade_count || 0)) +
          kv('open_position_count', String(ac.open_position_count || 0)) +
          kv('currency', esc(ac.currency)) +
          kv('live_trading_enabled', '<span class="ok">false</span>') +
          '</table>' :
          '<div class="tagline warn">' + esc(ac.reason || ac.error || 'not configured') + '</div>';
        // Pricing
        const priceRows = (pr.prices || []).map((p) =>
          '<tr><td><b>' + esc(p.instrument) + '</b></td>' +
          '<td>' + fmtNum(p.bid, 5) + ' / ' + fmtNum(p.ask, 5) + '</td>' +
          '<td>' + fmtNum(p.spread_pips, 2) + 'p ' +
          (p.spread_warning ? '<span class="bad">WIDE</span>' : '<span class="ok">OK</span>') +
          '</td></tr>').join('');
        box.querySelector('#otPricing div').innerHTML = priceRows ?
          '<table class="detail-tbl">' + priceRows + '</table>' :
          '<div class="tagline warn">no pricing</div>';
        // Positions
        const posRows = (pos.positions || []).map((p) =>
          '<tr><td><b>' + esc(p.instrument) + '</b></td>' +
          '<td>long ' + esc((p.long || {}).units || '0') +
          ' · short ' + esc((p.short || {}).units || '0') +
          ' · uPL ' + fmtNum(p.unrealizedPL, 2) + '</td></tr>').join('');
        box.querySelector('#otPositions div').innerHTML = posRows ?
          '<table class="detail-tbl">' + posRows + '</table>' :
          '<div class="tagline">no open positions</div>';
        // Trades
        const trRows = (tr.trades || []).map((t) =>
          '<tr><td><b>' + esc(t.instrument) + '</b> · id ' + esc(t.id) + '</td>' +
          '<td>units ' + esc(t.currentUnits) + ' @ ' + esc(t.price) +
          ' · uPL ' + fmtNum(t.unrealizedPL, 2) +
          ' <button class="mini-btn" data-ot-close="' + esc(t.id) + '">Close</button></td></tr>').join('');
        box.querySelector('#otTrades div').innerHTML = trRows ?
          '<table class="detail-tbl">' + trRows + '</table>' :
          '<div class="tagline">no open trades</div>';
        // Wire close buttons
        box.querySelectorAll('button[data-ot-close]').forEach((b) => {
          b.addEventListener('click', () => {
            fetch('/api/trading/oanda/close_practice_trade', {
              method: 'POST', headers: {'Content-Type': 'application/json'},
              body: JSON.stringify({trade_id: b.dataset.otClose, units: 'ALL'}),
            }).then((r) => r.json()).then((j) => {
              alert('Close result: ' + (j.label || j.error || 'unknown'));
              refreshAll();
            });
          });
        });
        // Ledger
        const lRows = (led.entries || []).slice(-6).reverse().map((e) =>
          '<tr><td>' + esc((e.ts || '').slice(11, 19)) + '</td>' +
          '<td>' + esc(e.event) + ' · ' + esc(e.instrument || '') + ' ' + esc(e.units || '') +
          ' ' + esc(e.side || '') + '</td></tr>').join('');
        box.querySelector('#otLedger div').innerHTML =
          '<div class="tagline">entries: ' + (led.entries || []).length + '</div>' +
          (lRows ? '<table class="detail-tbl">' + lRows + '</table>' : '<div class="tagline">empty</div>');
        // Guards
        const G = gu.guards || {};
        const ks = (gu.kill_switch || {});
        killChip.textContent = 'KILL SWITCH: ' + (ks.kill_switch_on ? 'ON' : 'OFF');
        killChip.className = 'oanda-chip ' + (ks.kill_switch_on ? 'bad' : 'ok');
        box.querySelector('#otGuards div').innerHTML = '<table class="detail-tbl">' +
          kv('allowed_instruments', esc((G.allowed_instruments || []).join(', '))) +
          kv('default_units',       String(G.default_units)) +
          kv('max_units_per_trade', String(G.max_units_per_trade)) +
          kv('max_open_trades',     String(G.max_open_trades)) +
          kv('max_trades_per_hour', String(G.max_trades_per_hour)) +
          kv('max_spread_pips',     String(G.max_spread_pips)) +
          kv('max_daily_loss_gbp',  String(G.max_daily_practice_loss_gbp)) +
          kv('manual_confirm',      '<span class="ok">required</span>') +
          kv('execution_mode',      '<span class="ok">PRACTICE_ONLY</span>') +
          '</table>';
      });
    }

    function showPreview(preview, payload) {
      const ok = preview.passed_guards;
      pendingOrder = ok ? payload : null;
      confirmBt.disabled = !ok;
      previewBox.innerHTML =
        '<div class="oanda-preview-card ' + (ok ? 'ok' : 'bad') + '">' +
        '<b>Preview Result:</b> ' + (ok ? '<span class="ok">PASSED — ready for confirmed placement</span>' :
          '<span class="bad">BLOCKED</span>') +
        '<table class="detail-tbl">' +
        kv('instrument', esc(preview.preview.instrument)) +
        kv('units', String(preview.preview.units)) +
        kv('side', esc(preview.preview.side)) +
        kv('estimated_fill_price', fmtNum(preview.preview.estimated_fill_price, 5)) +
        kv('spread_pips', fmtNum(preview.preview.spread_pips, 2)) +
        kv('mode', '<span class="ok">PRACTICE_ONLY</span>') +
        (preview.guard_failures && preview.guard_failures.length ?
          kv('guard_failures', '<span class="bad">' + esc(preview.guard_failures.join(', ')) + '</span>') : '') +
        '</table></div>';
    }

    function doPreview(payload) {
      fetch('/api/trading/oanda/practice_order_preview', {
        method: 'POST', headers: {'Content-Type': 'application/json'},
        body: JSON.stringify(payload),
      }).then((r) => r.json()).then((p) => showPreview(p, payload));
    }
    function doPlaceConfirmed() {
      if (!pendingOrder) return alert('Preview an order first.');
      if (!confirm('PLACE PRACTICE ORDER on the OANDA practice account?\n\n' +
                     pendingOrder.side + ' ' + pendingOrder.units + ' ' + pendingOrder.instrument +
                     '\n\nThis is PRACTICE ACCOUNT only — no real money.')) return;
      fetch('/api/trading/oanda/place_practice_order', {
        method: 'POST', headers: {'Content-Type': 'application/json'},
        body: JSON.stringify(Object.assign({}, pendingOrder, {confirm_practice_order: true})),
      }).then((r) => r.json()).then((j) => {
        previewBox.innerHTML += '<div class="oanda-preview-card ' + (j.ok ? 'ok' : 'bad') + '">' +
          '<b>Place Result:</b> ' + (j.ok ? '<span class="ok">' + esc(j.label) + '</span>' : '<span class="bad">BLOCKED</span>') +
          '<pre style="background:rgba(0,8,22,.55);padding:6px;border-radius:5px;font-size:10px;color:#cfe6ff;overflow:auto;max-height:240px">' +
          esc(JSON.stringify(j, null, 2).slice(0, 2400)) +
          '</pre></div>';
        pendingOrder = null; confirmBt.disabled = true;
        refreshAll();
      });
    }

    box.querySelectorAll('button[data-ot]').forEach((b) => {
      b.addEventListener('click', () => {
        const k = b.dataset.ot;
        if (k === 'preflight') fetch('/api/trading/oanda/practice_preflight').then((r) => r.json()).then((j) =>
          alert('Preflight: ' + (j.ok ? 'OK · account_ready=' + j.account_ready + ' · pricing_ready=' + j.pricing_ready : 'NOT OK')));
        else if (k === 'preview_buy_eur')  doPreview({mode: 'PRACTICE_ONLY', instrument: 'EUR_USD', units: 100, side: 'buy',  confirm_practice_order: false});
        else if (k === 'preview_sell_eur') doPreview({mode: 'PRACTICE_ONLY', instrument: 'EUR_USD', units: 100, side: 'sell', confirm_practice_order: false});
        else if (k === 'preview_custom') {
          const inst = prompt('Instrument? (EUR_USD / GBP_USD / USD_JPY)', 'EUR_USD');
          const units = parseInt(prompt('Units? (100-1000)', '100'), 10);
          const side = prompt('Side? (buy / sell)', 'buy');
          if (!inst || !units || !side) return;
          doPreview({mode: 'PRACTICE_ONLY', instrument: inst, units, side, confirm_practice_order: false});
        }
        else if (k === 'place_confirmed') doPlaceConfirmed();
        else if (k === 'refresh') refreshAll();
        else if (k === 'kill_on')  fetch('/api/trading/oanda/practice_kill_switch', {method: 'POST', headers: {'Content-Type':'application/json'}, body: JSON.stringify({kill_switch_on: true, reason: 'operator'})}).then(() => refreshAll());
        else if (k === 'kill_off') fetch('/api/trading/oanda/practice_kill_switch', {method: 'POST', headers: {'Content-Type':'application/json'}, body: JSON.stringify({kill_switch_on: false})}).then(() => refreshAll());
        else if (k === 'open_ledger') fetch('/api/trading/oanda/practice_ledger').then((r) => r.json()).then((j) => {
          window.QSB_WINDOWS.open('oanda-ledger', {title: 'OANDA Practice Ledger',
            width: 720, height: 520,
            render: (body) => {
              body.innerHTML = '<pre style="background:rgba(0,8,22,.6);padding:8px;border-radius:6px;font-size:11px;color:#cfe6ff;overflow:auto">' +
                esc(JSON.stringify(j, null, 2).slice(0, 6000)) + '</pre>';
            }});
        });
      });
    });

    refreshAll();
    box._otTimer = setInterval(refreshAll, 6000);
  }

  function mountOandaTelemetryConsole(main, d) {
    _populateTelemetry(main, [
      _telemetryBlock('OANDA — Account Wall',  '/api/trading/oanda/account'),
      _telemetryBlock('OANDA — Open Positions','/api/trading/oanda/positions'),
      _telemetryBlock('OANDA — Open Trades / Transactions','/api/trading/oanda/trades'),
      _telemetryBlock('OANDA — P&L',           '/api/trading/oanda/pnl'),
    ]);
  }
  function mountBinanceTelemetryConsole(main, d) {
    _populateTelemetry(main, [
      _telemetryBlock('Binance — Account / Balances', '/api/trading/binance/account'),
      _telemetryBlock('Binance — Positions (balances view)', '/api/trading/binance/positions'),
      _telemetryBlock('Binance — Open Orders', '/api/trading/binance/orders'),
      _telemetryBlock('Binance — P&L',         '/api/trading/binance/pnl'),
    ]);
  }
  function mountStocksTelemetryConsole(main, d) {
    _populateTelemetry(main, [
      _telemetryBlock('Stocks — Account Read', '/api/trading/stocks/account'),
      _telemetryBlock('Stocks — Positions',    '/api/trading/stocks/positions'),
      _telemetryBlock('Stocks — P&L',          '/api/trading/stocks/pnl'),
    ]);
  }

  // ── Colonel Concierge + Butler cards (Penthouse) ────────────────────
  function mountColonelConsole(main, d) {
    const box = document.createElement('div');
    box.className = 'fw-block colonel-console';
    box.innerHTML =
      '<h4>Penthouse Staff — Colonel Concierge &amp; Colonel Butler</h4>' +
      '<div class="colonel-cards">' +
      '<div class="colonel-card" id="colConcierge"><h5>🎩 Colonel Concierge</h5><div>loading…</div>' +
      '<div class="colonel-actions" id="colConciergeActions"></div></div>' +
      '<div class="colonel-card" id="colButler"><h5>🛎 Colonel Butler — Daily Briefing</h5><div>loading…</div></div>' +
      '</div>';
    main.appendChild(box);
    // V3 Concierge buttons (added before fetch)
    function addV3ConciergeButtons(panel) {
      const extras = [
        ['Run Full Tower Audit', 'tower_audit'],
        ['Open Audit Report',    'audit_report'],
        ['Ask Tower What Next?', 'next_steps'],
        ['Open Training Academy', 'training_open'],
      ];
      const wrapper = document.createElement('div');
      wrapper.style.marginTop = '6px';
      wrapper.innerHTML = extras.map(([label, key]) =>
        '<button class="mini-btn" data-v3="' + key + '" style="margin-right:4px;margin-bottom:4px">' + esc(label) + '</button>').join('');
      panel.appendChild(wrapper);
      wrapper.querySelectorAll('button[data-v3]').forEach((b) => {
        b.addEventListener('click', () => {
          const k = b.dataset.v3;
          if (k === 'training_open') openFloorWindow(8);
          else if (k === 'tower_audit') {
            b.textContent = 'Running…';
            fetch('/api/audit/run_full', { method: 'POST' }).then((r) => r.json()).then((j) => {
              openAuditWindow(j);
              b.textContent = 'Run Full Tower Audit';
            });
          } else if (k === 'audit_report') {
            fetch('/api/audit/latest').then((r) => r.json()).then((j) => openAuditWindow(j));
          } else if (k === 'next_steps') {
            fetch('/api/audit/next_steps').then((r) => r.json()).then((j) => openNextStepsWindow(j));
          }
        });
      });
    }
    function openAuditWindow(j) {
      window.QSB_WINDOWS.open('audit-report', {
        title: 'Full Tower Audit — score ' + (j.overall_score || '—') + '/100',
        width: 760, height: 600,
        render: (b) => {
          const cats = j.category_scores || {};
          const catRows = Object.keys(cats).map((k) =>
            '<tr><td>' + esc(k) + '</td><td>' + cats[k] + '/100</td></tr>').join('');
          const critRows = (j.critical_failures || []).map((c) =>
            '<tr><td><span class="bad">CRITICAL</span></td><td>' + esc(c.category) + '</td><td>' + esc(c.message) + '</td></tr>').join('');
          const failRows = (j.failures || []).map((c) =>
            '<tr><td><span class="warn">FAIL</span></td><td>' + esc(c.category) + '</td><td>' + esc(c.message) + '</td></tr>').join('');
          const warnRows = (j.warnings || []).map((c) =>
            '<tr><td><span class="warn">WARN</span></td><td>' + esc(c.category) + '</td><td>' + esc(c.message) + '</td></tr>').join('');
          b.innerHTML =
            '<div class="fw-block"><h4>Overall <span class="sub">' + esc(j.overall_status) + ' · ' + (j.overall_score || '—') + '/100</span></h4>' +
            '<table class="detail-tbl">' + catRows + '</table></div>' +
            (critRows ? '<div class="fw-block"><h4>Critical Failures</h4><table class="detail-tbl">' + critRows + '</table></div>' : '') +
            (failRows ? '<div class="fw-block"><h4>Failures</h4><table class="detail-tbl">' + failRows + '</table></div>' : '') +
            (warnRows ? '<div class="fw-block"><h4>Warnings (' + (j.warnings || []).length + ')</h4><table class="detail-tbl">' + warnRows + '</table></div>' : '');
        },
      });
    }
    function openNextStepsWindow(j) {
      window.QSB_WINDOWS.open('next-steps', {
        title: 'Tower Architect — Next Steps',
        width: 760, height: 640,
        render: (b) => {
          const wellList = (j.what_is_working_well || []).map((l) => '<li>' + esc(l) + '</li>').join('');
          const halfList = (j.what_is_half_built  || []).map((l) => '<li>' + esc(l) + '</li>').join('');
          const missList = (j.what_is_missing     || []).map((l) => '<li>' + esc(l) + '</li>').join('');
          const phases = (j.next_5_build_phases || []).map((p) =>
            '<div class="fw-block"><h4>Priority ' + p.priority + ' — ' + esc(p.title) + '</h4>' +
            '<p><b>Reason:</b> ' + esc(p.reason) + '</p>' +
            '<p><b>Files likely involved:</b> <code>' + esc((p.files_likely_involved || []).join(', ')) + '</code></p>' +
            '<p><b>Risk:</b> ' + esc(p.risk) + '</p>' +
            '<p><b>Acceptance test:</b> ' + esc(p.acceptance_test) + '</p></div>').join('');
          b.innerHTML =
            '<div class="fw-block"><h4>What is working well</h4><ul>' + wellList + '</ul></div>' +
            '<div class="fw-block"><h4>What is half-built</h4><ul>' + halfList + '</ul></div>' +
            '<div class="fw-block"><h4>What is missing</h4><ul>' + missList + '</ul></div>' +
            '<div class="fw-block"><h4>Highest priority recommendation</h4><p>' + esc(j.highest_priority_recommendation) + '</p></div>' +
            '<div class="fw-block"><h4>Single bug blocking the most functionality</h4><p>' + esc(j.single_bug_blocking_most_functionality) + '</p></div>' +
            phases;
        },
      });
    }
    setTimeout(() => addV3ConciergeButtons(box.querySelector('#colConciergeActions') || box), 200);
    fetch('/api/colonel/concierge', { cache: 'no-store' }).then((r) => r.json()).then((c) => {
      const lines = [
        '<div><b>Status:</b> ' + esc(c.concierge_status) + '</div>',
        '<div><b>Tower state:</b> ' + esc(c.tower_state) + '</div>',
        '<div><b>Workers:</b> ' + (c.worker_count || 0) +
          ' · <b>Managers:</b> ' + (c.manager_count || 0) +
          ' · <b>Overseers:</b> ' + (c.overseer_count || 0) + '</div>',
        '<div><b>OpenClaw ready:</b> ' + (c.openclaw_ready_count || 0) +
          ' · <b>advisory:</b> ' + (c.active_advisory || 0) +
          ' · <b>read-only:</b> ' + (c.active_read_only || 0) + '</div>',
        '<div><b>Speech floor:</b> <code data-route-floor="15">floor_15</code> · ' +
          '<b>Media floor:</b> <code data-route-floor="14">floor_14</code></div>',
      ].join('');
      box.querySelector('#colConcierge div').innerHTML = lines;
      const actions = (c.actions || []).map((a) => {
        if (a.target_floor) return '<button class="mini-btn" data-col-target="' + a.target_floor + '">' + esc(a.label) + '</button>';
        if (a.target === 'tower_report') return '<button class="mini-btn" data-col-action="tower_report">' + esc(a.label) + '</button>';
        return '<button class="mini-btn" data-col-action="' + esc(a.target) + '">' + esc(a.label) + '</button>';
      }).join(' ');
      box.querySelector('#colConciergeActions').innerHTML = actions;
      box.querySelectorAll('button[data-col-target]').forEach((b) => {
        b.addEventListener('click', () => {
          const n = Number(b.dataset.colTarget);
          if (Number.isFinite(n)) openFloorWindow(n);
        });
      });
      box.querySelectorAll('button[data-col-action]').forEach((b) => {
        b.addEventListener('click', () => {
          const act = b.dataset.colAction;
          if (act === 'tower_report') {
            fetch('/api/tower_ops/tower_report').then((r) => r.json()).then((t) =>
              alert('Tower Report:\n' + (t.zones || []).map((z) => z.zone_name + ': ' + z.health).join('\n') +
                    '\nOverall health: ' + (t.overall_health || '—')));
          }
        });
      });
    });
    fetch('/api/colonel/butler', { cache: 'no-store' }).then((r) => r.json()).then((b) => {
      const html = '<ul style="margin-left:1.2em;line-height:1.5">' +
        (b.briefing || []).map((l) => '<li>' + esc(l) + '</li>').join('') + '</ul>';
      box.querySelector('#colButler div').innerHTML = html;
    });
  }

  // ── Floor 15 Speech & Audio Department console ───────────────────────
  function mountSpeechFloorConsole(main, d) {
    const sp = d.speech_floor || {};
    const box = document.createElement('div');
    box.className = 'fw-block speech-console';
    const ttsOk = ('speechSynthesis' in window);
    const sttOk = !!(window.SpeechRecognition || window.webkitSpeechRecognition);
    box.innerHTML = '<h4>Speech & Audio Department — Live Probe</h4>' +
      '<table class="detail-tbl">' +
      kv('Browser SpeechSynthesis', '<span class="' + (ttsOk ? 'ok' : 'warn') + '">' + (ttsOk ? 'available' : 'NOT available') + '</span>') +
      kv('Browser SpeechRecognition', '<span class="' + (sttOk ? 'ok' : 'warn') + '">' + (sttOk ? 'available' : 'NOT available') + '</span>') +
      kv('TTS engine reported', sp.tts_engine) +
      kv('STT engine reported', sp.stt_engine) +
      kv('Local sidecar present', String(!!sp.local_sidecar_present)) +
      kv('External speech provider', sp.external_speech_provider) +
      kv('Speech route', sp.speech_to_kernel_route) +
      kv('Reply route', sp.kernel_reply_to_tts_route) +
      '</table>' +
      '<div class="rc-actions">' +
      '<button class="mini-btn" id="spkProbe" ' + (ttsOk ? '' : 'disabled') + '>🔊 Test TTS</button>' +
      '<button class="mini-btn" id="micProbe" ' + (sttOk ? '' : 'disabled') + '>🎤 Test STT (5 s)</button>' +
      '<button class="mini-btn" id="spkMute">⏹ Cancel</button>' +
      '</div>' +
      '<div id="speechLog" class="chat-log" style="max-height:120px"></div>';
    main.appendChild(box);

    const log = box.querySelector('#speechLog');
    function row(t) { const r = document.createElement('div'); r.className = 'row system'; r.textContent = t; log.appendChild(r); log.scrollTop = log.scrollHeight; }

    box.querySelector('#spkProbe').addEventListener('click', () => {
      if (window.QSB_SPEECH) {
        const ok = window.QSB_SPEECH.speak('Speech and audio department test. All execution locks remain false.');
        row(ok ? 'TTS spoken (English voice).' : 'TTS failed — no English voice available.');
      } else {
        row('TTS failed: QSB_SPEECH not loaded.');
      }
    });
    box.querySelector('#micProbe').addEventListener('click', () => {
      const SR = window.SpeechRecognition || window.webkitSpeechRecognition;
      if (!SR) { row('STT not supported.'); return; }
      const r = new SR(); r.continuous = false; r.interimResults = false; r.lang = navigator.language || 'en-US';
      r.onresult = (ev) => row('STT heard: ' + ev.results[0][0].transcript);
      r.onerror = (ev) => row('STT error: ' + (ev.error || 'unknown'));
      try { r.start(); row('STT listening 5 s…'); setTimeout(() => { try { r.stop(); } catch (e) {} }, 5000); }
      catch (e) { row('STT start failed: ' + e); }
    });
    box.querySelector('#spkMute').addEventListener('click', () => { try { window.speechSynthesis.cancel(); } catch (e) {} });
  }

  function openStrategyDetailWindow() {
    const state = window.QSB.state || {};
    const list = state.instruments || [];
    window.QSB_WINDOWS.open('strategy-detail', {
      title: 'Strategy / Trading — Detail',
      width: 720, height: 460,
      render: (body) => {
        body.innerHTML = `<table class="instr-tbl">
          <thead><tr><th>Inst</th><th>Mid</th><th>Spread</th><th>Paper</th><th>Strat</th><th>Conf</th><th>Mom10</th><th>ΔPips</th><th>Score</th><th>OpenClaw</th><th>Align</th></tr></thead>
          <tbody>${list.map((i) => `
            <tr><td><b>${esc(i.instrument)}</b></td>
                <td>${fmtNum(i.mid, 5)}</td>
                <td>${fmtPips(i.spread_pips)}</td>
                <td class="sig-${esc(i.paper_signal)}">${esc(i.paper_signal)}</td>
                <td class="sig-${esc(i.strategy_signal)}">${esc(i.strategy_signal)}</td>
                <td>${fmtNum(i.confidence, 2)}</td>
                <td>${fmtPips(i.momentum_10_pips)}</td>
                <td>${fmtPips(i.performance_delta_pips)}</td>
                <td>${fmtNum(i.performance_score, 3)}</td>
                <td>${esc(i.openclaw_recommendation)}</td>
                <td>${esc(i.alignment_label)}</td></tr>`).join('')}</tbody></table>
          <div class="tagline ok">paper-only · execution locks closed · not financial advice</div>`;
      },
    });
  }

  function openLedgerDetailWindow() {
    const state = window.QSB.state || {};
    const ledger = state.ledger || {};
    const entries = ledger.latest_entries || [];
    window.QSB_WINDOWS.open('ledger-detail', {
      title: 'Ledger / Audit — ' + (ledger.entry_count || 0) + ' entries',
      width: 560, height: 420,
      render: (body) => {
        body.innerHTML = '<table class="detail-tbl">' +
          entries.map((e) => `<tr><td>${esc((e.ts || '').slice(11, 19))}</td><td>${esc(e.title || e.message || JSON.stringify(e).slice(0, 120))}</td></tr>`).join('') +
          '</table>' + '<div class="tagline">' + esc(ledger.entry_count || 0) + ' total entries · latest update ' + esc(ledger.updated_ts || '—') + '</div>';
      },
    });
  }

  function openDetailFromButton(key) {
    const map = {
      'kernel-chat': () => openKernelChatWindow(window.QSB.state),
      'lock-detail': () => openLockDetailWindow(),
      'strategy-detail': () => openStrategyDetailWindow(),
      'ledger-detail': () => openLedgerDetailWindow(),
      'oanda-detail': () => openSimpleDetail('oanda-detail', 'OANDA Floor 41 — detail', window.QSB.state.oanda_floor || window.QSB.state.oanda || {}),
      'binance-detail': () => openSimpleDetail('binance-detail', 'Binance Floor 42 — detail', window.QSB.state.binance || {}),
      'stocks-detail':  () => openSimpleDetail('stocks-detail', 'Stock Exchange Floor 43 — detail', window.QSB.state.stock_exchange || {}),
      'cross-detail':   () => openSimpleDetail('cross-detail', 'Cross-Market Bus — detail', window.QSB.state.cross_market_bus || {}),
      'airllm-detail': () => openSimpleDetail('airllm-detail', 'AirLLM Chamber (advisory) — detail', window.QSB.state.airllm_chamber || {}),
      'openclaw-detail': () => openSimpleDetail('openclaw-detail', 'OpenClaw — detail', {
        workers: (window.QSB.state.workers || []).filter((w) => /openclaw/i.test(w.name || w.id)).map((w) => w.name),
        recommendations: (window.QSB.state.instruments || []).map((i) => ({ i: i.instrument, rec: i.openclaw_recommendation })),
      }),
    };
    const fn = map[key];
    if (fn) fn();
  }
  function openFloorDirectoryWindow() {
    const state = window.QSB.state || {};
    const render = state.dashboard_render_model || {};
    const nameMap = state.floor_name_map || {};
    const renderFloors = (render.floors || []).filter((f) => typeof f.number === 'number' && f.number >= 1 && f.number <= 53);
    const all = renderFloors.length ? renderFloors : Array.from({ length: 53 }, (_, i) => {
      const n = i + 1;
      return { number: n, name: nameMap[n] || ('Floor ' + n), category: 'infrastructure', highlight: false };
    });
    window.QSB_WINDOWS.open('floor-directory', {
      title: 'Floor Directory — ' + all.length + ' floors',
      width: 480, height: 540,
      render: (body) => {
        body.innerHTML = `
          <div class="chat-row" style="margin-bottom:8px">
            <input id="floorDirSearch" placeholder="Search by number, name, or category…">
          </div>
          <div id="floorDirList" style="max-height:62vh;overflow:auto;display:flex;flex-direction:column;gap:2px"></div>
          <div class="tagline">Click a floor to focus the tower and open its detail window.</div>`;
        const list = body.querySelector('#floorDirList');
        function paint(filter) {
          const f = (filter || '').toLowerCase().trim();
          const rows = all
            .filter((x) => !f || ('' + x.number).indexOf(f) >= 0 ||
                                (x.name || '').toLowerCase().indexOf(f) >= 0 ||
                                (x.category || '').toLowerCase().indexOf(f) >= 0)
            .sort((a, b) => b.number - a.number)
            .map((x) => {
              const cat = (x.category || 'infrastructure').replace(/_/g, ' ');
              const hl = x.highlight ? ' ★' : '';
              return `<div class="worker-row" data-fn="${x.number}">
                <span class="wn"><b>${esc(('' + x.number).padStart(2, '0'))}</b> · ${esc(x.name)}${hl}</span>
                <span class="wf">${esc(cat)}</span>
              </div>`;
            });
          list.innerHTML = rows.join('') || '<div class="tagline">no match</div>';
          list.querySelectorAll('.worker-row').forEach((r) => {
            r.addEventListener('click', () => {
              const n = parseInt(r.dataset.fn, 10);
              window.QSB_TOWER_2D_FOCUS_FLOOR && window.QSB_TOWER_2D_FOCUS_FLOOR(n);
              openFloorWindow(n);
            });
          });
        }
        body.querySelector('#floorDirSearch').addEventListener('input', (e) => paint(e.target.value));
        paint('');
      },
    });
  }

  function openSimpleDetail(id, title, obj) {
    window.QSB_WINDOWS.open(id, {
      title, width: 520, height: 360,
      render: (body) => {
        const rows = Object.keys(obj).map((k) =>
          `<tr><td>${esc(k)}</td><td>${esc(JSON.stringify(obj[k]).slice(0, 200))}</td></tr>`).join('');
        body.innerHTML = '<table class="detail-tbl">' + rows + '</table>';
      },
    });
  }

  // ── tabs + collapsibles + focus mode ──────────────────────────────────
  function wireTabs(tabsEl, paneRoot) {
    qsa('button[data-tab]', tabsEl).forEach((btn) => {
      btn.addEventListener('click', () => {
        qsa('button[data-tab]', tabsEl).forEach((b) => b.classList.toggle('active', b === btn));
        qsa('.pane', paneRoot).forEach((p) => p.classList.toggle('active', p.dataset.pane === btn.dataset.tab));
      });
    });
  }

  function wireLayoutControls() {
    const app = el('app');
    el('leftCollapse').addEventListener('click', () => app.classList.toggle('left-collapsed'));
    el('rightCollapse').addEventListener('click', () => app.classList.toggle('right-collapsed'));
    el('bottomCollapse').addEventListener('click', () => app.classList.toggle('bottom-collapsed'));
    el('btnFocus').addEventListener('click', () => {
      app.classList.toggle('focus');
      el('btnFocus').classList.toggle('active', app.classList.contains('focus'));
      setTimeout(() => { if (window.QSB_SCENE && window.QSB_SCENE.engine) window.QSB_SCENE.engine.resize(); }, 280);
    });
    el('btnLayoutReset').addEventListener('click', () => {
      app.classList.remove('focus', 'left-collapsed', 'right-collapsed', 'bottom-collapsed');
      el('btnFocus').classList.remove('active');
      document.documentElement.style.removeProperty('--bottom-h');
      setTimeout(() => { if (window.QSB_SCENE && window.QSB_SCENE.engine) window.QSB_SCENE.engine.resize(); }, 280);
    });

    // bottom resize drag
    const resize = el('bottomResize');
    let resizing = false, startY = 0, baseH = 0;
    resize.addEventListener('mousedown', (e) => {
      resizing = true; startY = e.clientY;
      baseH = parseInt(getComputedStyle(document.documentElement).getPropertyValue('--bottom-h')) || 180;
      e.preventDefault();
    });
    document.addEventListener('mousemove', (e) => {
      if (!resizing) return;
      const dy = e.clientY - startY;
      const nh = Math.max(60, Math.min(window.innerHeight * 0.6, baseH - dy));
      document.documentElement.style.setProperty('--bottom-h', nh + 'px');
    });
    document.addEventListener('mouseup', () => {
      if (resizing) { resizing = false; if (window.QSB_SCENE && window.QSB_SCENE.engine) window.QSB_SCENE.engine.resize(); }
    });
  }

  function wireDetailButtons() {
    qsa('button[data-window]').forEach((btn) => {
      btn.addEventListener('click', () => openDetailFromButton(btn.dataset.window));
    });
  }

  function wireHeaderButtons() {
    let paused = false;
    el('btnPause').addEventListener('click', () => {
      paused = !paused;
      window.QSB_SCENE_PAUSE && window.QSB_SCENE_PAUSE(paused);
      window.QSB_TOWER_2D_PAUSE && window.QSB_TOWER_2D_PAUSE(paused);
      window.QSB.setPaused(paused);
      el('btnPause').textContent = paused ? '▶ Resume' : '⏸ Pause';
      el('btnPause').classList.toggle('active', paused);
    });
    el('btnReset').addEventListener('click', () => window.QSB_SCENE_RESET && window.QSB_SCENE_RESET());
    el('btnRefresh').addEventListener('click', () => window.QSB.refresh());
    el('btnSound').addEventListener('click', () => {
      const next = el('btnSound').dataset.on !== '1';
      el('btnSound').dataset.on = next ? '1' : '0';
      el('btnSound').textContent = next ? '🔊 Sound: On' : '🔇 Sound: Off';
      window.QSB_AUDIO.setSoundOn(next);
    });
    el('btnSpeech').addEventListener('click', () => {
      const next = el('btnSpeech').dataset.on !== '1';
      el('btnSpeech').dataset.on = next ? '1' : '0';
      el('btnSpeech').textContent = next ? '🗣 Speech: On' : '🗣 Speech: Off';
      window.QSB_AUDIO.setSpeechOn(next);
    });
    const muteBtn = el('btnMute');
    if (muteBtn) {
      muteBtn.addEventListener('click', () => {
        try { window.QSB_AUDIO && window.QSB_AUDIO.muteAll && window.QSB_AUDIO.muteAll(); } catch (e) {}
        const s = el('btnSound');  if (s) { s.dataset.on = '0'; s.textContent = '🔇 Sound: Off'; }
        const sp = el('btnSpeech'); if (sp) { sp.dataset.on = '0'; sp.textContent = '🗣 Speech: Off'; }
      });
    }
  }

  // ── scene click → open detail window ───────────────────────────────────
  function handleScenePick(meta) {
    // V1 rebuild: track selected floor globally so the renderer can
    // surface its workers inside the slab.
    try {
      if (meta && meta.kind === 'floor') {
        (window.QSB = window.QSB || {}).selectedFloor = meta.number;
        // Force a re-paint so workers on the selected floor appear.
        if (window.QSB.state) {
          window.dispatchEvent(new CustomEvent('qsb:state', { detail: window.QSB.state }));
        }
      }
      window.dispatchEvent(new CustomEvent('qsb:pick', { detail: meta }));
    } catch (_) {}
    if (meta.kind === 'floor') openFloorWindow(meta.number);
    else if (meta.kind === 'worker') openWorkerWindow(meta.id);
  }

  // ── V1 worker view mode toggle ─────────────────────────────────────
  // V1 Total Rebuild: default is now `selected_floor_and_groups` so
  // workers are visibly present (no more hidden behind counts_only).
  (function initWorkerViewMode() {
    (window.QSB = window.QSB || {}).workerViewMode = 'selected_floor_and_groups';
    const sel = document.getElementById('workerViewMode');
    if (!sel) return;
    function applyMode(m) {
      window.QSB.workerViewMode = m;
      if (window.QSB.state) {
        try {
          window.dispatchEvent(new CustomEvent('qsb:state', { detail: window.QSB.state }));
        } catch (_) {}
      }
    }
    sel.addEventListener('change', function () { applyMode(sel.value); });
    applyMode(sel.value);
  })();

  // ── Renderer debug aggregator ────────────────────────────────────────
  const RENDERER = {
    diag2d: null,
    diag3d: null,
    active: 'svg_2d',     // 'svg_2d' | 'webgl_3d'
    wantWebGL: true,      // auto-attempt 3D on boot; user can force 2D via Renderer Debug
    webglProbe: {},
  };
  function probeWebGLCanvas() {
    const c = document.createElement('canvas');
    let w2 = null, w1 = null;
    try { w2 = c.getContext('webgl2'); } catch (e) {}
    if (!w2) { try { w1 = c.getContext('webgl') || c.getContext('experimental-webgl'); } catch (e) {} }
    return { webgl: !!(w2 || w1), webgl2: !!w2, source: w2 ? 'webgl2' : (w1 ? 'webgl1' : 'none') };
  }
  function pushDebugStrip() {
    const d2 = RENDERER.diag2d || {};
    const d3 = RENDERER.diag3d || {};
    const probe = RENDERER.webglProbe || {};
    const dw = el('dbgWebgl');
    if (dw) {
      const txt = probe.webgl ? (probe.webgl2 ? 'WebGL2 ✓' : 'WebGL1 ✓') : '✗';
      dw.textContent = 'WebGL: ' + txt;
      dw.className = 'dbg ' + (probe.webgl ? 'ok' : 'warn');
    }
    const de = el('dbgEngine');
    if (de) {
      const e3d = d3.engine;
      de.textContent = 'Engine: ' + (e3d === true ? '3D ✓' : '2D');
      de.className = 'dbg ' + (e3d === true ? 'ok' : 'warn');
    }
    const dr = el('dbgRender');
    if (dr) {
      const active = RENDERER.active;
      dr.textContent = 'Render: ' + (active === 'webgl_3d' ? '3D' : '2D SVG');
      dr.className = 'dbg ok';
    }
    const df = el('dbgFps');
    if (df) df.textContent = 'FPS: ' + (d3.fps || '—');
    const der = el('dbgErr');
    if (der) {
      const errSrc = d3.err || d2.last_error || '';
      der.textContent = errSrc ? ('err: ' + errSrc) : '';
      der.className = 'dbg ' + (errSrc ? 'bad' : '');
    }
  }
  function renderDebug3D(d)  { RENDERER.diag3d = d; pushDebugStrip(); updateRendererWindow(); }
  function renderDebug2D(d)  { RENDERER.diag2d = d; pushDebugStrip(); updateRendererWindow(); }

  function openRendererWindow() {
    window.QSB_WINDOWS.open('renderer-debug', {
      title: 'Renderer Debug',
      width: 460, height: 420,
      render: (body) => {
        body.innerHTML = `
          <div id="rendererDebugBody"></div>
          <div style="margin-top:10px;display:flex;gap:6px;flex-wrap:wrap">
            <button class="mini-btn" id="rdForce2D">Force 2D SVG</button>
            <button class="mini-btn" id="rdTry3D">Try WebGL 3D</button>
            <button class="mini-btn" id="rdReprobe">Re-probe WebGL</button>
            <button class="mini-btn" id="rdOpenTest">Open render_test=1</button>
          </div>
          <div class="tagline">2D SVG renderer is always-on. WebGL is enhancement only.</div>`;
        body.querySelector('#rdForce2D').addEventListener('click', () => {
          RENDERER.wantWebGL = false;
          document.querySelector('.stage-body').classList.remove('use-3d');
          RENDERER.active = 'svg_2d';
          pushDebugStrip(); updateRendererWindow();
        });
        body.querySelector('#rdTry3D').addEventListener('click', () => {
          RENDERER.wantWebGL = true;
          tryInitWebGL();
        });
        body.querySelector('#rdReprobe').addEventListener('click', () => {
          RENDERER.webglProbe = probeWebGLCanvas();
          pushDebugStrip(); updateRendererWindow();
        });
        body.querySelector('#rdOpenTest').addEventListener('click', () => {
          window.location.href = '/?v=unified&render_test=1';
        });
        updateRendererWindow();
      },
    });
  }
  function updateRendererWindow() {
    const host = document.querySelector('#rendererDebugBody');
    if (!host) return;
    const d2 = RENDERER.diag2d || {};
    const d3 = RENDERER.diag3d || {};
    const p  = RENDERER.webglProbe || {};
    const rows = [
      ['Active renderer',       RENDERER.active],
      ['WebGL available',       p.webgl ? 'true' : 'false'],
      ['WebGL2 available',      p.webgl2 ? 'true' : 'false'],
      ['Probe source',          p.source || '—'],
      ['Babylon global present',(d3.babylon_global_present === true || typeof BABYLON !== 'undefined') ? 'true' : 'false'],
      ['Canvas found',          d3.canvas_found === true ? 'true' : (d3.canvas_found === false ? 'false' : '—')],
      ['Canvas width',          String(d3.canvas_width || 0)],
      ['Canvas height',         String(d3.canvas_height || 0)],
      ['Engine created',        d3.engine_created ? 'true' : 'false'],
      ['Scene created',         d3.scene_created ? 'true' : 'false'],
      ['Camera created',        d3.camera_created ? 'true' : 'false'],
      ['Lights created',        d3.lights_created ? 'true' : 'false'],
      ['Meshes created',        String(d3.meshes_created || 0)],
      ['Render loop started',   d3.render_loop_started ? 'true' : 'false'],
      ['First frame rendered',  d3.first_frame_rendered ? 'true' : 'false'],
      ['3D engine running',     d3.engine ? 'true' : 'false'],
      ['3D render produced',    d3.render ? 'true' : 'false'],
      ['3D FPS',                String(d3.fps || 0)],
      ['3D last error',         d3.err || '—'],
      ['Babylon error stack',   d3.babylon_error_stack || '—'],
      ['Stage size',            (function () { const b = document.querySelector('.stage-body'); return b ? b.clientWidth + ' × ' + b.clientHeight : '—'; })()],
      ['2D floors rendered',    String(d2.floors_rendered || 0)],
      ['2D shafts rendered',    String(d2.shafts_rendered || 0)],
      ['2D capsules rendered',  String(d2.capsules_rendered || 0)],
      ['2D workers rendered',   String(d2.workers_rendered || 0)],
      ['2D routes rendered',    String(d2.routes_rendered || 0)],
      ['2D packets active',     String(d2.packets_active || 0)],
      ['2D last error',         d2.last_error || '—'],
      ['render_test=1 mode',    window.QSB && window.QSB.renderTest ? 'true' : 'false'],
    ];
    host.innerHTML = '<table class="detail-tbl">' +
      rows.map(([k, v]) => `<tr><td>${esc(k)}</td><td>${esc(v)}</td></tr>`).join('') + '</table>';
  }

  // ── Init renderers ────────────────────────────────────────────────────
  let webGLAttempted = false;
  function tryInitWebGL() {
    if (webGLAttempted) {
      if (RENDERER.diag3d && RENDERER.diag3d.engine) {
        document.querySelector('.stage-body').classList.add('use-3d');
        RENDERER.active = 'webgl_3d';
        pushDebugStrip(); updateRendererWindow();
      }
      return;
    }
    webGLAttempted = true;
    const canvas = el('qsbCanvas');
    const hudTip = el('hudTip');
    const workerLabels = el('workerLabels');
    if (!window.QSB_SCENE_INIT) return;
    window.QSB_SCENE_INIT({
      canvas,
      hudTipEl: hudTip,
      workerLabelsEl: workerLabels,
      onDiag: (d) => {
        renderDebug3D(d);
        // Auto-promote to webgl_3d the moment a real frame is actually drawn.
        if (d && d.first_frame_rendered && RENDERER.wantWebGL && RENDERER.active !== 'webgl_3d') {
          const stage = document.querySelector('.stage-body');
          if (stage) stage.classList.add('use-3d');
          RENDERER.active = 'webgl_3d';
          pushDebugStrip(); updateRendererWindow();
        }
      },
      onPick: handleScenePick,
      onReady: () => {
        // Scene built; render loop is now polling. Promotion happens on first
        // frame via onDiag above so we never advertise 3D before pixels exist.
        pushDebugStrip(); updateRendererWindow();
      },
      onFail: (msg) => {
        if (RENDERER.diag3d) { RENDERER.diag3d.err = msg; }
        else { RENDERER.diag3d = { engine: false, err: msg, fps: 0 }; }
        pushDebugStrip(); updateRendererWindow();
      },
    });
  }

  // ── boot ──────────────────────────────────────────────────────────────
  function injectProBanner() {
    if (document.getElementById('proBanner')) return;
    const hdr = document.getElementById('hdr');
    if (!hdr) return;
    const bar = document.createElement('div');
    bar.id = 'proBanner';
    bar.className = 'pro-banner';
    bar.innerHTML = '<span class="pb-label">EXECUTION STATUS</span>' +
      '<span class="pb-label">' +
      '<span class="pb-chip">OANDA PRACTICE: ON</span>' +
      '<span class="pb-chip">LIVE REAL MONEY: OFF</span>' +
      '<span class="pb-chip">ALL REAL EXECUTION LOCKS: CLOSED</span>' +
      '<span class="pb-chip" id="proBalance">probing…</span>' +
      '</span>';
    hdr.parentNode.insertBefore(bar, hdr.nextSibling);
    function updateBalance() {
      fetch('/api/dashboard/pro_state').then((r) => r.json()).then((s) => {
        const o = s.oanda_practice || {};
        const c = document.getElementById('proBalance');
        if (c) c.textContent = o.credentials_present ?
          'OANDA Practice NAV: ' + (o.NAV || '—') + ' · open_trades: ' + (o.open_trade_count || 0) :
          'OANDA Practice: not configured';
      }).catch(() => {});
    }
    updateBalance();
    setInterval(updateBalance, 10000);
  }

  function boot() {
    wireTabs(el('leftTabs'), el('leftPane'));
    wireTabs(el('rightTabs'), el('rightPane'));
    injectProBanner();
    wireLayoutControls();
    wireDetailButtons();
    wireHeaderButtons();

    RENDERER.webglProbe = probeWebGLCanvas();

    // 1. Always mount the SVG 2D tower first — guaranteed visible.
    if (window.QSB_TOWER_2D_INIT) {
      try {
        window.QSB_TOWER_2D_INIT({
          hostEl: el('qsbTower2D'),
          hudTipEl: el('hudTip'),
          onPick: handleScenePick,
          onDiag: renderDebug2D,
        });
        RENDERER.active = 'svg_2d';
      } catch (e) {
        renderDebug2D({ last_error: String(e).slice(0, 200) });
      }
    }
    pushDebugStrip();

    // 2. Auto-attempt Babylon 3D as enhancement if WebGL is available
    //    The SVG remains visible until 3D actually renders its first frame.
    if (RENDERER.webglProbe.webgl && typeof BABYLON !== 'undefined' && !window.QSB.renderTest) {
      setTimeout(() => tryInitWebGL(), 120);  // give layout one paint cycle
    }

    // 3. Renderer Debug button
    const btnR = el('btnRenderer');
    if (btnR) btnR.addEventListener('click', openRendererWindow);

    // 3b. Tower-Only toggle — hide side panels so the 3D tower fills the cockpit
    const btnTO = el('btnTowerOnly');
    if (btnTO) {
      btnTO.addEventListener('click', () => {
        const on = btnTO.dataset.on !== '1';
        btnTO.dataset.on = on ? '1' : '0';
        btnTO.classList.toggle('active', on);
        const app = el('app');
        if (app) app.classList.toggle('focus', on);
        document.body.classList.toggle('tower-only', on);
        if (on) document.querySelectorAll('.qwin').forEach((w) => w.style.display = 'none');
        else document.querySelectorAll('.qwin').forEach((w) => w.style.display = '');
        setTimeout(() => { if (window.QSB_SCENE && window.QSB_SCENE.engine) window.QSB_SCENE.engine.resize(); }, 80);
      });
    }

    // 3. Tower mode buttons (rotate / show-all-names / highlight groups)
    const btnRotate = el('btnRotate');
    if (btnRotate) {
      btnRotate.addEventListener('click', () => {
        const next = btnRotate.dataset.on !== '1';
        btnRotate.dataset.on = next ? '1' : '0';
        btnRotate.classList.toggle('active', next);
        window.QSB_TOWER_2D_SET_ROTATE && window.QSB_TOWER_2D_SET_ROTATE(next);
      });
    }
    const btnAllNames = el('btnAllNames');
    if (btnAllNames) {
      btnAllNames.addEventListener('click', () => {
        const next = btnAllNames.dataset.on !== '1';
        btnAllNames.dataset.on = next ? '1' : '0';
        btnAllNames.classList.toggle('active', next);
        window.QSB_TOWER_2D_SET_SHOW_ALL_NAMES && window.QSB_TOWER_2D_SET_SHOW_ALL_NAMES(next);
      });
    }
    function wireHl(btnId, group) {
      const b = el(btnId);
      if (!b) return;
      b.addEventListener('click', () => {
        const wasActive = b.classList.contains('active');
        ['btnHlTrading', 'btnHlModels', 'btnHlRisk'].forEach((id) => el(id) && el(id).classList.remove('active'));
        if (wasActive) {
          window.QSB_TOWER_2D_SET_HIGHLIGHT_GROUP && window.QSB_TOWER_2D_SET_HIGHLIGHT_GROUP(null);
        } else {
          b.classList.add('active');
          window.QSB_TOWER_2D_SET_HIGHLIGHT_GROUP && window.QSB_TOWER_2D_SET_HIGHLIGHT_GROUP(group);
        }
      });
    }
    wireHl('btnHlTrading', 'trading');
    wireHl('btnHlModels',  'models');
    wireHl('btnHlRisk',    'risk');

    // 4. Floor Directory + Kernel Chat shortcuts
    const btnDir  = el('btnDirectory');
    if (btnDir)   btnDir.addEventListener('click', openFloorDirectoryWindow);
    const btnKc   = el('btnKernelChat');
    if (btnKc)    btnKc.addEventListener('click', () => openKernelChatWindow(window.QSB.state));

    // 5. Auto-open ?floor=N once /api/unified has populated state.floors
    try {
      const u = new URL(window.location.href);
      const f = u.searchParams.get('floor');
      if (f != null) {
        const fn = Number(f);
        if (Number.isFinite(fn)) {
          window.addEventListener('qsb:state', function once() {
            window.removeEventListener('qsb:state', once);
            setTimeout(() => openFloorWindow(fn), 80);
          });
        }
      }
    } catch (e) {}

    window.addEventListener('qsb:state', (e) => {
      const s = e.detail;
      if (!s) return;
      renderHeader(s);
      renderKernel(s);
      renderLocks(s);
      renderCounts(s);
      try { renderSuggestions(s); } catch (_e) {}
      renderServices(s);
      renderInstruments(s);
      renderOanda(s);
      renderBinance(s);
      renderStocks(s);
      renderCrossMarket(s);
      renderAirllm(s);
      renderOpenClaw(s);
      renderWorkers(s);
      renderTicker(s);
      // speech advisor watches transitions
      try { window.QSB_AUDIO && window.QSB_AUDIO.observeState(s, window.QSB.prev); } catch (e) {}
    });
    window.addEventListener('qsb:state-error', () => {
      el('pillKernel').textContent = 'kernel offline';
      el('pillKernel').className = 'pill alert';
    });

    // Force one resize after CSS settles
    setTimeout(() => { if (window.QSB_SCENE && window.QSB_SCENE.engine) window.QSB_SCENE.engine.resize(); }, 100);
  }

  if (document.readyState === 'loading') {
    document.addEventListener('DOMContentLoaded', boot);
  } else {
    boot();
  }

  // ──────────────────────────────────────────────────────────────────────
  // TICK PULSE — live heartbeat indicators
  // Shipped 2026-06-14 by f47.fleet.persistence.alert_router.01.
  // 9 dots, one per heartbeat sub-tick. Polls /api/f47/recent_ticks every 5s.
  // Each dot pulses (opacity 1.0→0.3→1.0 over 1s) when its kind arrives.
  // ──────────────────────────────────────────────────────────────────────
  const TICK_DOTS = [
    { key: 'daemon',   label: 'daemon',   match: (k) => k === 'heartbeat_tick' || /^daemon_/.test(k) },
    { key: 'dispatch', label: 'dispatch', match: (k) => k === 'mass_dispatch' || k.indexOf('dispatch') !== -1 },
    { key: 'oanda',    label: 'oanda',    match: (k) => k.indexOf('oanda') !== -1 || k.indexOf('position_monitor') !== -1 },
    { key: 'graphics', label: 'graphics', match: (k) => k.indexOf('graphics') !== -1 },
    { key: 'bench',    label: 'bench',    match: (k) => k === 'auto_sigs_tick' || k === 'applier_tick' || k === 'proposal_checker' || k === 'proposal_checker_tick' },
    { key: 'chat',     label: 'chat',     match: (k) => k === 'chat_mirror_tick' || k.indexOf('chat_mirror') !== -1 },
    { key: 'buffer',   label: 'buffer',   match: (k) => k.indexOf('buffer_snapshot') !== -1 },
    { key: 'brief',    label: 'brief',    match: (k) => k.indexOf('wake_briefing') !== -1 || k.indexOf('steward_briefing') !== -1 },
    { key: 'super',    label: 'super',    match: (k) => k === 'supervisor_tick' || k === 'supervisor_escalation' || k.indexOf('supervisor') !== -1 },
  ];

  const TickPulse = {
    lastSince: null,
    lastTickTs: null,
    pulseTimers: {},
    bigWindow: null,
    bigWindowList: [],

    init() {
      this._injectStyles();
      this._mountWidget();
      // Initial poll seeded with NOW so we only see fresh ticks.
      const now = new Date();
      this.lastSince = now.toISOString().replace(/\.\d+/, '').replace('Z', '') + 'Z';
      this.poll();
      setInterval(() => this.poll(), 5000);
      setInterval(() => this._tickAge(), 1000);
    },

    _injectStyles() {
      if (document.getElementById('tickPulseStyle')) return;
      const s = document.createElement('style');
      s.id = 'tickPulseStyle';
      s.textContent = `
        #tickPulse {
          position: fixed; top: 60px; right: 12px; z-index: 9000;
          background: rgba(6,12,22,.85); border: 1.5px solid #d09a3a;
          border-radius: 8px; padding: 6px 9px;
          font: 11px/1.2 ui-monospace, Menlo, monospace; color: #e7d9b3;
          box-shadow: 0 4px 18px rgba(0,0,0,.55);
          backdrop-filter: blur(6px);
          user-select: none; cursor: pointer;
        }
        #tickPulse .tp-title {
          font-size: 9px; letter-spacing: 1.5px; color: #d09a3a;
          margin-bottom: 4px; font-weight: 600;
        }
        #tickPulse .tp-row { display: flex; gap: 4px; align-items: center; }
        #tickPulse .tp-dot {
          display: inline-flex; align-items: center; gap: 3px;
          padding: 2px 4px; border-radius: 4px; opacity: .35;
          transition: opacity 1s ease, background .3s;
          background: rgba(255,255,255,.04);
        }
        #tickPulse .tp-dot .tp-bullet {
          width: 8px; height: 8px; border-radius: 50%;
          background: #4ade80; box-shadow: 0 0 4px #4ade80;
        }
        #tickPulse .tp-dot.live { opacity: 1; }
        #tickPulse .tp-dot.pulse { animation: tpPulse 1s ease; }
        #tickPulse .tp-foot {
          margin-top: 4px; font-size: 9.5px; color: #aaa;
        }
        @keyframes tpPulse {
          0%   { opacity: 1; transform: scale(1.0); }
          50%  { opacity: .3; transform: scale(1.25); }
          100% { opacity: 1; transform: scale(1.0); }
        }
        #tickPulseWin {
          position: fixed; top: 80px; right: 12px; width: 460px; height: 520px;
          background: rgba(6,12,22,.96); border: 1.5px solid #d09a3a;
          border-radius: 8px; z-index: 9100; display: flex; flex-direction: column;
          font: 12px/1.35 ui-monospace, Menlo, monospace; color: #e7d9b3;
          box-shadow: 0 8px 28px rgba(0,0,0,.7);
        }
        #tickPulseWin .tpw-hdr {
          padding: 8px 10px; border-bottom: 1px solid #4a3a18;
          display: flex; justify-content: space-between; align-items: center;
          color: #d09a3a; font-weight: 600; letter-spacing: 1px; font-size: 11px;
        }
        #tickPulseWin .tpw-close {
          cursor: pointer; padding: 2px 8px; border: 1px solid #d09a3a;
          border-radius: 4px; background: transparent; color: #d09a3a;
        }
        #tickPulseWin .tpw-body {
          flex: 1; overflow-y: auto; padding: 8px 10px;
        }
        #tickPulseWin .tpw-row {
          padding: 4px 0; border-bottom: 1px dotted #1a2940;
          display: grid; grid-template-columns: 80px 90px 1fr; gap: 6px;
        }
        #tickPulseWin .tpw-row .tpw-ts { color: #6dbfe6; }
        #tickPulseWin .tpw-row .tpw-cat { color: #d09a3a; }
        #tickPulseWin .tpw-row .tpw-kind { color: #ccc; }
      `;
      document.head.appendChild(s);
    },

    _mountWidget() {
      const host = document.createElement('div');
      host.id = 'tickPulse';
      host.title = 'Heartbeat tick pulse — click for full timeline';
      const dots = TICK_DOTS.map((d) =>
        `<span class="tp-dot" data-tp="${d.key}">` +
        `<span class="tp-bullet"></span>` +
        `<span class="tp-lbl">${d.label}</span></span>`
      ).join('');
      host.innerHTML =
        '<div class="tp-title">TICK PULSE · 5min heartbeat</div>' +
        '<div class="tp-row">' + dots + '</div>' +
        '<div class="tp-foot" id="tpFoot">last tick: — · waiting…</div>';
      host.addEventListener('click', () => this.openBigWindow());
      document.body.appendChild(host);
    },

    _tickAge() {
      const foot = document.getElementById('tpFoot');
      if (!foot) return;
      if (!this.lastTickTs) { foot.textContent = 'last tick: — · waiting…'; return; }
      const d = new Date(this.lastTickTs);
      if (isNaN(d.getTime())) { foot.textContent = 'last tick: — · waiting…'; return; }
      const ageSec = Math.max(0, Math.floor((Date.now() - d.getTime()) / 1000));
      const min = Math.floor(ageSec / 60);
      const sec = ageSec % 60;
      const hhmmss = d.toISOString().slice(11, 19);
      const ago = min > 0 ? (min + ' min ago') : (sec + 's ago');
      foot.textContent = 'last tick: ' + hhmmss + ' UTC · ' + ago;
    },

    poll() {
      const url = '/api/f47/recent_ticks' + (this.lastSince ? ('?since=' + encodeURIComponent(this.lastSince)) : '');
      fetch(url, { cache: 'no-store' })
        .then((r) => r.json())
        .then((d) => {
          if (!d || !d.ok || !Array.isArray(d.ticks)) return;
          if (d.now) this.lastSince = d.now;
          if (!d.ticks.length) return;
          // Update last tick time + maintain rolling 50-tick window.
          d.ticks.forEach((t) => {
            if (t.ts) this.lastTickTs = t.ts;
            // Fire dot pulse for each matching key.
            TICK_DOTS.forEach((dot) => {
              if (dot.match(String(t.kind || ''))) this._pulse(dot.key);
            });
            this.bigWindowList.push(t);
            if (this.bigWindowList.length > 50) this.bigWindowList.shift();
          });
          this._refreshBigWindow();
        })
        .catch(() => {});
    },

    _pulse(key) {
      const el = document.querySelector('#tickPulse .tp-dot[data-tp="' + key + '"]');
      if (!el) return;
      el.classList.add('live', 'pulse');
      if (this.pulseTimers[key]) clearTimeout(this.pulseTimers[key]);
      this.pulseTimers[key] = setTimeout(() => {
        el.classList.remove('pulse');
        // keep "live" lit dim-bright after first hit
      }, 1100);
    },

    openBigWindow() {
      if (document.getElementById('tickPulseWin')) {
        document.getElementById('tickPulseWin').remove();
        return;
      }
      const w = document.createElement('div');
      w.id = 'tickPulseWin';
      w.innerHTML =
        '<div class="tpw-hdr">' +
        '<span>F47 TICK TIMELINE · last 50 ticks</span>' +
        '<button class="tpw-close">close</button>' +
        '</div>' +
        '<div class="tpw-body" id="tpwBody"></div>';
      w.querySelector('.tpw-close').addEventListener('click', () => w.remove());
      document.body.appendChild(w);
      this._refreshBigWindow();
    },

    _refreshBigWindow() {
      const body = document.getElementById('tpwBody');
      if (!body) return;
      const rows = this.bigWindowList.slice().reverse().map((t) => {
        const ts = (t.ts || '').slice(11, 19);
        const cat = (TICK_DOTS.find((d) => d.match(String(t.kind || ''))) || {}).label || '·';
        return '<div class="tpw-row">' +
          '<span class="tpw-ts">' + ts + '</span>' +
          '<span class="tpw-cat">' + cat + '</span>' +
          '<span class="tpw-kind">' + (t.kind || '') + '</span>' +
          '</div>';
      });
      body.innerHTML = rows.length ? rows.join('') :
        '<div style="color:#888;padding:8px">waiting for first tick…</div>';
    },
  };

  // Boot it once the DOM is ready (after the main boot()).
  if (document.readyState === 'loading') {
    document.addEventListener('DOMContentLoaded', () => TickPulse.init());
  } else {
    TickPulse.init();
  }

  // Expose launcher hook + global for debug.
  window.openTickPulseWindow = () => TickPulse.openBigWindow();
  window.QSB_TICK_PULSE = TickPulse;
})();
