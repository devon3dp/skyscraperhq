// QSB Tower V1.3 — qsb_state.js (V3)
// Phase: QSB_TOWER_VISIBLE_SKYSCRAPER_RENDERER_FIX_V1
//
// Polls /api/unified every 4s, exposes latest snapshot at window.QSB.state,
// dispatches a "qsb:state" CustomEvent on window each tick.
//
// If the URL has ?render_test=1, skip API polling and emit a synthetic
// 53-floor state every 4s so the renderer is visually testable without
// any backend signal. The synthetic state still stamps locks closed,
// kernel active_local_only, and all advisory_only/paper_only fields true.

(function () {
  'use strict';

  const POLL_INTERVAL_MS = 4000;

  const QSB = {
    state: null,
    prev: null,
    lastFetchOk: null,
    lastFetchTs: null,
    pollMs: POLL_INTERVAL_MS,
    fetchErrors: 0,
    paused: false,
    renderTest: false,
  };
  window.QSB = QSB;

  // ── URL flags ──────────────────────────────────────────────────────────
  try {
    const url = new URL(window.location.href);
    QSB.renderTest = url.searchParams.get('render_test') === '1';
  } catch (e) {}

  // ── /api/unified poll ──────────────────────────────────────────────────
  async function pollOnce() {
    try {
      const res = await fetch('/api/unified?t=' + Date.now(), { cache: 'no-store' });
      if (!res.ok) throw new Error('HTTP ' + res.status);
      const data = await res.json();
      QSB.prev = QSB.state;
      QSB.state = data;
      QSB.lastFetchOk = true;
      QSB.lastFetchTs = Date.now();
      QSB.fetchErrors = 0;
      window.dispatchEvent(new CustomEvent('qsb:state', { detail: data }));
    } catch (e) {
      QSB.lastFetchOk = false;
      QSB.fetchErrors += 1;
      window.dispatchEvent(new CustomEvent('qsb:state-error', { detail: { error: String(e) } }));
    }
  }

  // ── Synthetic test state ───────────────────────────────────────────────
  function syntheticState() {
    const now = new Date().toISOString();
    const floors = [];
    const labelMap = {
      23: 'AirLLM Big Model Chamber',
      24: 'Model Routing',
      25: 'Agent Coordination',
      30: 'Permissions / Risk',
      31: 'Audit / Ledger',
      37: 'Simulation Labs',
      38: 'Sandbox Operations',
      41: 'OANDA Trading Floor',
      42: 'Binance Trading Floor',
      43: 'Stock Exchange Trading Floor',
      53: 'Tower Command',
    };
    for (let n = 1; n <= 53; n++) {
      const hl = !!labelMap[n];
      floors.push({
        id: 'floor_' + n,
        number: n,
        zone: n <= 14 ? 'ZONE A' : n <= 28 ? 'ZONE B' : n <= 42 ? 'ZONE C' : 'ZONE D',
        department: labelMap[n] || ('Floor ' + n),
        vacant: (n >= 44 && n <= 45),
        highlight: hl,
        highlight_label: labelMap[n] || '',
        lift_access: true,
        workers: [],
      });
    }
    const lifts = [];
    for (let i = 0; i < 9; i++) lifts.push({ id: 'lift_' + i, name: 'Lift ' + (i + 1), status: 'online', serves: [] });
    const workers = [
      { id: 'market_scout',                  name: 'Market Scout',                  role: 'OANDA quote read',           home_floor: 'floor_41' },
      { id: 'spread_watcher',                name: 'Spread Watcher',                role: 'Spread measurement',         home_floor: 'floor_41' },
      { id: 'risk_sentinel',                 name: 'Risk Sentinel',                 role: 'Lock verification',          home_floor: 'floor_30' },
      { id: 'paper_strategy_analyst',        name: 'Paper Strategy Analyst',        role: 'Paper strategy synthesis',   home_floor: 'floor_37' },
      { id: 'kernel_commentary_runner',      name: 'Kernel Commentary Runner',      role: 'Local kernel commentary',    home_floor: 'floor_53' },
      { id: 'ledger_clerk',                  name: 'Ledger Clerk',                  role: 'Audit ledger upkeep',        home_floor: 'floor_31' },
      { id: 'openclaw_market_probe',         name: 'OpenClaw Market Probe',         role: 'OpenClaw sandbox probe',     home_floor: 'floor_38' },
      { id: 'openclaw_strategy_mapper',      name: 'OpenClaw Strategy Mapper',      role: 'OpenClaw strategy mapping',  home_floor: 'floor_37' },
      { id: 'equity_market_scout',           name: 'Equity Market Scout',           role: 'Stock quote read',           home_floor: 'floor_43' },
      { id: 'stock_spread_watcher',          name: 'Stock Spread Watcher',          role: 'Stock spread measurement',   home_floor: 'floor_43' },
      { id: 'cross_market_correlation_clerk',name: 'Cross-Market Correlation Clerk',role: 'Cross-market correlation',   home_floor: 'floor_37' },
      { id: 'airllm_model_scout',            name: 'AirLLM Model Scout',            role: 'AirLLM advisory read',       home_floor: 'floor_23' },
    ];
    const routes = [
      ['floor_41', 'floor_37', 'strategy', 'cyan',   'OANDA → Strategy'],
      ['floor_42', 'floor_37', 'strategy', 'orange', 'Binance → Strategy'],
      ['floor_43', 'floor_37', 'stocks',   'white',  'Stocks → Strategy'],
      ['floor_37', 'floor_38', 'worker',   'green',  'Strategy → Sandbox'],
      ['floor_38', 'floor_30', 'openclaw', 'purple', 'Sandbox → Risk'],
      ['floor_30', 'floor_31', 'ledger',   'gold',   'Risk → Audit'],
      ['floor_31', 'floor_53', 'ledger',   'gold',   'Audit → Command'],
      ['floor_53', 'penthouse','kernel',   'blue',   'Command → Penthouse'],
      ['floor_23', 'penthouse','airllm',   'cyan',   'AirLLM advisory → Penthouse'],
      ['floor_41', 'floor_31', 'ledger',   'gold',   'OANDA → Audit'],
      ['floor_42', 'floor_31', 'ledger',   'gold',   'Binance → Audit'],
      ['floor_43', 'floor_31', 'ledger',   'gold',   'Stocks → Audit'],
    ];
    const packets = routes.map(([s, t, ty, c, title]) => ({
      ts: now, type: ty, color: c,
      source_floor: s, target_floor: t,
      lift_id: 'lift_render_test',
      title, detail: 'visual placeholder only',
    }));
    return {
      ts: now,
      phase: 'QSB_TOWER_VISIBLE_SKYSCRAPER_RENDERER_FIX_V1',
      mode: 'render_test_only',
      render_test: true,
      kernel: {
        activation_status: 'active_local_only',
        kernel_installed: true,
        QSBKernelCore_instantiated: true,
        active_kernel_source: 'rebased_kernel',
        local_model_enabled: true,
        ollama_local_inference_enabled: true,
        external_providers_enabled: false,
        kernel_health: 'healthy',
        kernel_chat_health: 'healthy',
        active: true,
      },
      locks: {
        live_trading_enabled: false,
        order_execution_enabled: false,
        practice_order_execution_enabled: false,
        binance_order_execution_enabled: false,
        binance_live_trading_enabled: false,
        stock_order_execution_enabled: false,
        stock_live_trading_enabled: false,
        stock_paper_order_execution_enabled: false,
        cross_market_execution_enabled: false,
        worker_execution_enabled: false,
        provider_execution_enabled: false,
        external_provider_execution_enabled: false,
        openclaw_execution_enabled: false,
        openclaw_real_tool_execution_enabled: false,
        autonomous_dispatch_enabled: false,
        live_dispatch_enabled: false,
        direct_provider_access: false,
      },
      lock_count_true: 0,
      warnings: [],
      building: { name: 'QSB Tower (render_test)', floors: 53, kernel_installed: true },
      floors,
      lifts,
      workers,
      packets,
      ledger: { entry_count: 999, latest_count: 12, updated_ts: now, latest_entries: [] },
      instruments: [],
      binance: { phase: 'render_test', environment: 'testnet', public_market_data_ready: false, paper_only: true, not_financial_advice: true },
      binance_instruments: [],
      stock_exchange: { phase: 'render_test', provider: 'stub', environment: 'paper', credentials_present: { api_key_present: false, api_secret_present: false }, public_market_data_ready: false, default_symbols: ['AAPL','MSFT','NVDA','TSLA','SPY','QQQ'], stock_order_execution_enabled: false, stock_live_trading_enabled: false, stock_paper_order_execution_enabled: false, execution_allowed: false, paper_only: true, not_financial_advice: true },
      stock_instruments: [],
      cross_market_bus: { bus: 'QSB Cross-Market Bus V1 (render_test)', oanda_status: 'ready', binance_status: 'ready', stocks_status: 'ready', cross_market_labels: ['no_cross_signal'], packet_count: 0, advisory_only: true, execution_allowed: false, paper_only: true, not_financial_advice: true },
      airllm_chamber: { registered: true, chamber_name: 'AirLLM Big Model Chamber', airllm_big_model_chamber: 'installed_advisory_only', advisory_only: true, execution_allowed: false },
      model_lanes: { local_ollama: 'active_local_only', airllm_big_model_chamber: 'installed_advisory_only', external_providers: 'locked', direct_provider_access: 'off' },
      openclaw: {},
      autoloop: { status: 'running', mode: 'paper_only_background_loop' },
      paper_trade_simulator: {},
      services: {},
      highlighted_floors: ['floor_23','floor_24','floor_25','floor_30','floor_31','floor_37','floor_38','floor_41','floor_42','floor_43','floor_53'],
      execution_allowed: false,
      paper_only: true,
      not_financial_advice: true,
    };
  }

  function emitSynthetic() {
    const data = syntheticState();
    QSB.prev = QSB.state;
    QSB.state = data;
    QSB.lastFetchOk = true;
    QSB.lastFetchTs = Date.now();
    window.dispatchEvent(new CustomEvent('qsb:state', { detail: data }));
  }

  function schedule() {
    setTimeout(async () => {
      if (!QSB.paused) {
        if (QSB.renderTest) emitSynthetic();
        else await pollOnce();
      }
      schedule();
    }, QSB.pollMs);
  }

  if (QSB.renderTest) {
    emitSynthetic();
    schedule();
  } else {
    pollOnce().finally(schedule);
  }

  QSB.refresh = function () { return QSB.renderTest ? Promise.resolve(emitSynthetic()) : pollOnce(); };
  QSB.setPaused = (p) => { QSB.paused = !!p; };
})();
