// QSB Tower V1.3 — qsb_floor_interior.js
// Phase: QSB_TOWER_LIVE_FLOOR_INTERIOR_WINDOWS_V1
//
// Reusable animated "operations-room" renderer that mounts an SVG floor map
// inside a floor window body. Each floor type has its own layout of
// section/desk blocks, with worker capsules walking between them and packets
// flowing along the documented internal routes. Live data lines are pulled
// directly from the /api/floor_detail payload (no new ports, no new sidecars).
//
// Public API:
//   window.QSB_FLOOR_INTERIOR_RENDER(host, detail) -> ctx
//   window.QSB_FLOOR_INTERIOR_PAUSE(host, paused)
//   window.QSB_FLOOR_INTERIOR_DISPOSE(host)
//
// Hard contract: read-only / paper-only / advisory-only. The renderer never
// invokes any API that could enable execution. Every interior also paints a
// permanent safety footer with execution_allowed=false and the lock count.

(function () {
  'use strict';

  const NS = 'http://www.w3.org/2000/svg';
  const VIEW_W = 820;
  const VIEW_H = 380;

  // Per-host context registry so Previous/Next can dispose+rebuild cleanly.
  const REGISTRY = new WeakMap();

  const COLORS = {
    worker:   '#4dffb0',
    strategy: '#5ce0ff',
    ledger:   '#ffd24c',
    openclaw: '#b08aff',
    kernel:   '#6ab8ff',
    airllm:   '#7fc8ff',
    paper:    '#ffe066',
    stocks:   '#eaf2ff',
    crypto:   '#ffb86c',
    cross:    '#c8a6ff',
    risk:     '#ff5060',
    routing:  '#8aa8ff',
    fx:       '#5ce0ff',
    ok:       '#00c97a',
    warn:     '#ffaa50',
    bad:      '#ff5060',
    muted:    '#88a3c2',
    text:     '#dbeaff',
  };

  // ── helpers ────────────────────────────────────────────────────────────
  function mk(tag, attrs, parent) {
    const el = document.createElementNS(NS, tag);
    if (attrs) for (const k in attrs) el.setAttribute(k, attrs[k]);
    if (parent) parent.appendChild(el);
    return el;
  }
  function esc(s) {
    return String(s == null ? '' : s).replace(/[&<>"']/g, (c) =>
      ({ '&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;' }[c]));
  }
  function clip(s, n) { s = String(s == null ? '' : s); return s.length > n ? s.slice(0, n - 1) + '…' : s; }
  function pickColor(c) { return COLORS[c] || c || COLORS.text; }
  function fmtNum(n, d) { if (n == null || Number.isNaN(+n)) return '—'; return (+n).toFixed(d == null ? 2 : d); }

  // ── floor-specific layouts ─────────────────────────────────────────────
  // Each layout returns: { title_color, sections: [...], workers: [...], packet_routes: [...] }
  // - section: { id, title, subtitle, x, y, w, h, color, lines: (detail)=>string[] }
  // - worker:  { id, name, initial, color, home, neighbors:[sectionId,...], speed }
  // - packet:  { from:sectionId, to:sectionId, color, period_ms, label }

  function layoutForStocks(detail) {
    const s = detail.stock_exchange || {};
    const cm = s.cross_market_status || {};
    const sigs = s.results || [];
    const symbolRow = (sym) => {
      const m = sigs.find((r) => r.symbol === sym) || {};
      return sym + ' · ' + (m.paper_signal || 'observe');
    };
    return {
      title_color: COLORS.stocks,
      sections: [
        { id: 'mkt_data', title: 'Market Data Desk', subtitle: 'AAPL · MSFT · NVDA · TSLA · SPY · QQQ',
          x: 20,  y: 38,  w: 260, h: 116, color: COLORS.stocks,
          lines: () => [
            'data_ready: ' + (s.public_market_data_ready ? 'ready' : 'waiting'),
            symbolRow('AAPL'), symbolRow('MSFT'), symbolRow('NVDA'),
            symbolRow('TSLA'), symbolRow('SPY'),  symbolRow('QQQ'),
          ],
        },
        { id: 'eq_strategy', title: 'Equity Strategy Desk', subtitle: 'paper-only signals',
          x: 300, y: 38,  w: 260, h: 116, color: COLORS.strategy,
          lines: () => [
            'phase: ' + (s.environment || 'paper'),
            'signal_counts: ' + JSON.stringify(s.signal_counts || {}),
            'result_count: ' + (sigs.length || 0),
            'paper_only: true · not_financial_advice',
          ],
        },
        { id: 'cross_bus', title: 'Cross-Market Bus Desk', subtitle: 'OANDA 41 ⟷ Binance 42 ⟷ Stocks 43',
          x: 20,  y: 168, w: 540, h: 64,  color: COLORS.cross,
          lines: () => [
            'oanda: ' + ((cm.oanda || {}).status || '—') +
              ' · binance: ' + ((cm.binance || {}).status || '—') +
              ' · stocks: ' + ((cm.stocks || {}).status || '—'),
            'labels: ' + ((s.cross_market_labels || ['no_cross_signal']).join(' · ')),
          ],
        },
        { id: 'risk_chk', title: 'Risk Checkpoint', subtitle: 'all stock execution OFF',
          x: 20,  y: 246, w: 260, h: 116, color: COLORS.risk,
          lines: () => [
            'stock_orders: OFF',
            'stock_paper_orders: OFF',
            'stock_live_trading: OFF',
            'cross_market_execution: OFF',
            'lock_count_true: ' + (detail.locks ? Object.values(detail.locks).filter((v) => v === true).length : 0),
          ],
        },
        { id: 'audit_dispatch', title: 'Audit / Ledger Dispatch', subtitle: 'outbound → Floor 31',
          x: 300, y: 246, w: 260, h: 116, color: COLORS.ledger,
          lines: () => [
            'latest_ts: ' + (s.latest_ts || '—'),
            'outbound_route: floor_31 (paper)',
            'kernel_review: → penthouse',
          ],
        },
      ],
      workers: [
        { id: 'equity_market_scout',         name: 'Equity Market Scout',         initial: 'EM', color: COLORS.stocks,   home: 'mkt_data',       neighbors: ['mkt_data', 'eq_strategy'] },
        { id: 'stock_spread_watcher',        name: 'Stock Spread Watcher',        initial: 'SW', color: COLORS.stocks,   home: 'mkt_data',       neighbors: ['mkt_data', 'risk_chk'] },
        { id: 'equity_momentum_analyst',     name: 'Equity Momentum Analyst',     initial: 'EM', color: COLORS.strategy, home: 'eq_strategy',    neighbors: ['eq_strategy', 'mkt_data'] },
        { id: 'cross_market_correlation',    name: 'Cross-Market Correlation Clerk', initial: 'CC', color: COLORS.cross, home: 'cross_bus',     neighbors: ['cross_bus', 'eq_strategy'] },
        { id: 'risk_on_off_observer',        name: 'Risk-On/Risk-Off Observer',   initial: 'RO', color: COLORS.risk,     home: 'risk_chk',       neighbors: ['risk_chk', 'cross_bus'] },
        { id: 'stock_ledger_clerk',          name: 'Stock Ledger Clerk',          initial: 'SL', color: COLORS.ledger,   home: 'audit_dispatch', neighbors: ['audit_dispatch', 'risk_chk'] },
      ],
      packet_routes: [
        { from: 'mkt_data',       to: 'eq_strategy',    color: COLORS.stocks,   period_ms: 2200, label: 'paper ticket' },
        { from: 'eq_strategy',    to: 'risk_chk',       color: COLORS.strategy, period_ms: 2400, label: 'strategy → risk' },
        { from: 'risk_chk',       to: 'audit_dispatch', color: COLORS.ledger,   period_ms: 2600, label: 'risk → audit' },
        { from: 'cross_bus',      to: 'eq_strategy',    color: COLORS.cross,    period_ms: 3000, label: 'cross-market' },
        { from: 'audit_dispatch', to: 'risk_chk',       color: COLORS.kernel,   period_ms: 5000, label: 'kernel review' },
      ],
    };
  }

  function layoutForBinance(detail) {
    const b = detail.binance || {};
    return {
      title_color: COLORS.crypto,
      sections: [
        { id: 'testnet_feed', title: 'Testnet Market Feed', subtitle: 'BTC · ETH · BNB · SOL',
          x: 20,  y: 38,  w: 260, h: 116, color: COLORS.crypto,
          lines: () => [
            'env: ' + (b.environment || 'testnet'),
            'market_data_ready: ' + (b.public_market_data_ready ? 'true' : 'waiting'),
            'symbols: ' + ((b.default_symbols || []).join(', ') || '—'),
            'signal_counts: ' + JSON.stringify(b.signal_counts || {}),
          ],
        },
        { id: 'crypto_strategy', title: 'Crypto Paper Strategy Desk', subtitle: 'paper-only signals',
          x: 300, y: 38,  w: 260, h: 116, color: COLORS.strategy,
          lines: () => {
            const lines = ['phase: paper'];
            (b.results || []).slice(0, 4).forEach((r) => {
              lines.push(r.symbol + ' · ' + (r.paper_signal || 'observe'));
            });
            return lines;
          },
        },
        { id: 'oc_observer', title: 'Sandbox / OpenClaw Observer', subtitle: 'execution_allowed=false',
          x: 20,  y: 168, w: 540, h: 64,  color: COLORS.openclaw,
          lines: () => ['observe_only · OpenClaw execution OFF · paper-only'],
        },
        { id: 'risk_lock', title: 'Risk Lock Station', subtitle: 'order endpoints blocked',
          x: 20,  y: 246, w: 260, h: 116, color: COLORS.risk,
          lines: () => [
            'binance_order_execution: OFF',
            'binance_live_trading: OFF',
            'order_endpoints_blocked: true',
            'lock_count_true: ' + (detail.locks ? Object.values(detail.locks).filter((v) => v === true).length : 0),
          ],
        },
        { id: 'ledger', title: 'Ledger Dispatch', subtitle: 'outbound → Floor 31',
          x: 300, y: 246, w: 260, h: 116, color: COLORS.ledger,
          lines: () => [
            'latest_ts: ' + (b.latest_ts || '—'),
            'outbound_route: floor_31 (paper)',
          ],
        },
      ],
      workers: [
        { id: 'binance_market_scout',  name: 'Binance Market Scout',   initial: 'BM', color: COLORS.crypto,   home: 'testnet_feed',     neighbors: ['testnet_feed', 'crypto_strategy'] },
        { id: 'crypto_spread_watcher', name: 'Crypto Spread Watcher',  initial: 'CW', color: COLORS.crypto,   home: 'testnet_feed',     neighbors: ['testnet_feed', 'risk_lock'] },
        { id: 'crypto_momentum',       name: 'Crypto Momentum Analyst',initial: 'CM', color: COLORS.strategy, home: 'crypto_strategy',  neighbors: ['crypto_strategy', 'testnet_feed'] },
        { id: 'oc_crypto_observer',    name: 'OpenClaw Crypto Observer',initial: 'OC',color: COLORS.openclaw, home: 'oc_observer',      neighbors: ['oc_observer', 'crypto_strategy'] },
        { id: 'binance_risk_guard',    name: 'Binance Risk Guard',     initial: 'RG', color: COLORS.risk,     home: 'risk_lock',        neighbors: ['risk_lock', 'oc_observer'] },
        { id: 'binance_ledger',        name: 'Binance Ledger Clerk',   initial: 'BL', color: COLORS.ledger,   home: 'ledger',           neighbors: ['ledger', 'risk_lock'] },
      ],
      packet_routes: [
        { from: 'testnet_feed',    to: 'crypto_strategy', color: COLORS.crypto,   period_ms: 2200 },
        { from: 'crypto_strategy', to: 'risk_lock',       color: COLORS.strategy, period_ms: 2500 },
        { from: 'risk_lock',       to: 'ledger',          color: COLORS.ledger,   period_ms: 2700 },
        { from: 'oc_observer',     to: 'crypto_strategy', color: COLORS.openclaw, period_ms: 3200 },
      ],
    };
  }

  function layoutForOanda(detail) {
    const o = detail.oanda || {};
    return {
      title_color: COLORS.fx,
      sections: [
        { id: 'fx_pricing', title: 'FX Pricing Desk', subtitle: 'EUR_USD · GBP_USD · USD_JPY',
          x: 20,  y: 38,  w: 260, h: 116, color: COLORS.fx,
          lines: () => {
            const ps = o.paper_signals || [];
            const lines = ['pricing_ready: ' + (o.pricing_ready ? 'true' : '—')];
            ps.slice(0, 3).forEach((p) => {
              const inst = p.instrument || p.symbol;
              const mid = (p.mid || p.last);
              lines.push(inst + ' · mid ' + fmtNum(mid, 5) + ' · spread ' + fmtNum(p.spread_pips, 1) + 'p');
            });
            return lines;
          },
        },
        { id: 'fx_strategy', title: 'FX Paper Strategy Desk', subtitle: 'paper-only signals',
          x: 300, y: 38,  w: 260, h: 116, color: COLORS.strategy,
          lines: () => {
            const lines = [];
            (o.paper_signals || []).slice(0, 4).forEach((p) => {
              lines.push((p.instrument || p.symbol) + ' · ' + (p.paper_signal || p.signal || 'observe'));
            });
            if (!lines.length) lines.push('observe · no aligned momentum pattern');
            lines.unshift('paper_only · not_financial_advice');
            return lines;
          },
        },
        { id: 'practice_acct', title: 'Practice Account Read', subtitle: 'OANDA practice read-only',
          x: 20,  y: 168, w: 540, h: 64,  color: COLORS.kernel,
          lines: () => [
            'environment: ' + (o.environment || 'practice') +
              ' · account_ready: ' + (o.account_ready ? 'true' : '—') +
              ' · pricing_ready: ' + (o.pricing_ready ? 'true' : '—'),
          ],
        },
        { id: 'risk_lock', title: 'Risk Lock Station', subtitle: 'no orders',
          x: 20,  y: 246, w: 260, h: 116, color: COLORS.risk,
          lines: () => [
            'live_trading: OFF',
            'order_execution: OFF',
            'practice_order_execution: OFF',
            'lock_count_true: ' + (detail.locks ? Object.values(detail.locks).filter((v) => v === true).length : 0),
          ],
        },
        { id: 'ledger', title: 'Ledger Dispatch', subtitle: 'outbound → Floor 31',
          x: 300, y: 246, w: 260, h: 116, color: COLORS.ledger,
          lines: () => {
            const e = (o.ledger_latest_entries || []).slice(0, 3);
            const lines = ['latest_ts: ' + (o.latest_ts || '—')];
            e.forEach((x) => lines.push(((x.instrument || '') + ' · ' + (x.paper_signal || '—')).slice(0, 32)));
            return lines;
          },
        },
      ],
      workers: [
        { id: 'market_scout',          name: 'Market Scout',           initial: 'MS', color: COLORS.fx,       home: 'fx_pricing',    neighbors: ['fx_pricing', 'fx_strategy'] },
        { id: 'spread_watcher',        name: 'Spread Watcher',         initial: 'SW', color: COLORS.fx,       home: 'fx_pricing',    neighbors: ['fx_pricing', 'risk_lock'] },
        { id: 'paper_strategy_analyst',name: 'Paper Strategy Analyst', initial: 'PS', color: COLORS.strategy, home: 'fx_strategy',   neighbors: ['fx_strategy', 'practice_acct'] },
        { id: 'risk_sentinel',         name: 'Risk Sentinel',          initial: 'RS', color: COLORS.risk,     home: 'risk_lock',     neighbors: ['risk_lock', 'fx_strategy'] },
        { id: 'ledger_clerk',          name: 'Ledger Clerk',           initial: 'LC', color: COLORS.ledger,   home: 'ledger',        neighbors: ['ledger', 'risk_lock'] },
        { id: 'kernel_commentary',     name: 'Kernel Commentary Runner',initial: 'KC',color: COLORS.kernel,   home: 'practice_acct', neighbors: ['practice_acct', 'fx_strategy'] },
      ],
      packet_routes: [
        { from: 'fx_pricing',  to: 'fx_strategy',  color: COLORS.fx,       period_ms: 2200 },
        { from: 'fx_strategy', to: 'risk_lock',    color: COLORS.strategy, period_ms: 2400 },
        { from: 'risk_lock',   to: 'ledger',       color: COLORS.ledger,   period_ms: 2600 },
        { from: 'practice_acct', to: 'fx_strategy',color: COLORS.kernel,   period_ms: 3300 },
      ],
    };
  }

  function layoutForFloor45Recruitment(detail) {
    // Floor 45 Worker Recruitment Agency — sandbox-only recruitment, onboarding,
    // training, and visual dispatch. Reads from /api/floor_detail?floor=45 which
    // calls tower.worker_recruitment_agency.floor_detail().
    const ra      = detail.recruitment_agency || {};
    const byStg   = ra.by_training_status || {};
    const cands   = detail.candidates || [];
    const queue   = detail.onboarding_queue || [];
    const evs     = detail.latest_recruitment_events || [];
    const routes  = detail.assigned_routes || [];

    const countByTarget = (floor) => cands.filter(
      (c) => c.target_floor === floor || c.target_floor === ('floor_' + floor)).length;
    const targetLine = (label, fid) => label + ' → ' + (countByTarget(fid) || 0);

    return {
      title_color: COLORS.worker,
      sections: [
        { id: 'intake', title: 'Candidate Intake Desk',
          subtitle: ((ra.candidate_count || cands.length || 0) + ' candidates · sandbox-only'),
          x: 20, y: 38, w: 245, h: 110, color: COLORS.worker,
          lines: () => [
            'agency: ' + (ra.agency_name || 'Worker Recruitment Agency'),
            'floor: ' + (ra.agency_floor || 'floor_45'),
            'role categories: market_scout · risk · ledger',
            '                  airllm · kernel · strategy',
            'execution_allowed: false',
          ],
        },
        { id: 'screening', title: 'Screening Desk',
          subtitle: 'safety + sandbox-only + lock check',
          x: 285, y: 38, w: 245, h: 110, color: COLORS.cross,
          lines: () => [
            'screening: ' + (byStg.screening || 0),
            'sandbox_only: true · forced',
            'locks_check: pass (all false)',
            'forbidden_actions: live_trading · order_exec',
          ],
        },
        { id: 'training', title: 'Training Pods',
          subtitle: 'strategy · market · risk · ledger · kernel',
          x: 550, y: 38, w: 250, h: 110, color: COLORS.paper,
          lines: () => [
            'in_training: ' + (byStg.training_pod || 0),
            'queued: ' + (queue.length || 0),
            'skills: read_registries · advisory_only',
            'pods are observation-only',
          ],
        },
        { id: 'assignment', title: 'Assignment Board',
          subtitle: 'route to 25 · 38 · 37 · 30 · 31 · 41 · 42 · 43 · 23',
          x: 20, y: 168, w: 470, h: 100, color: COLORS.fx,
          lines: () => [
            'awaiting_assignment: ' + (byStg.assignment_board || 0),
            targetLine('Floor 25 Agent Coord', 'floor_25') + ' · '
              + targetLine('Floor 38 Sandbox', 'floor_38'),
            targetLine('Floor 37 Strategy', 'floor_37') + ' · '
              + targetLine('Floor 30 Risk', 'floor_30'),
            targetLine('Floor 31 Audit', 'floor_31') + ' · '
              + targetLine('Floor 41 OANDA', 'floor_41'),
            targetLine('Floor 42 Binance', 'floor_42') + ' · '
              + targetLine('Floor 43 Stocks', 'floor_43'),
            targetLine('Floor 23 AirLLM advisory', 'floor_23'),
          ],
        },
        { id: 'dispatch', title: 'Dispatch Gate',
          subtitle: 'animated worker dispatch · visual only',
          x: 510, y: 168, w: 290, h: 100, color: COLORS.strategy,
          lines: () => [
            'dispatched: ' + (byStg.dispatched || 0),
            'route_type: worker_recruitment_sandbox',
            'execution_allowed: false',
            'worker_execution_enabled: false',
          ],
        },
        { id: 'audit_strip', title: 'Recruitment Audit Strip',
          subtitle: 'data/logs/worker_recruitment_agency.jsonl',
          x: 20, y: 288, w: 470, h: 78, color: COLORS.ledger,
          lines: () => [
            (evs[0] ? ((evs[0].event || 'event') + ' · ' + (evs[0].display_name
              || evs[0].worker_id || '—')) : 'no recent events'),
            (evs[1] ? ((evs[1].event || 'event') + ' · ' + (evs[1].display_name
              || evs[1].worker_id || '—')) : 'append-only · sandbox-only'),
            'route count: ' + (routes.length || 0),
          ],
        },
        { id: 'safety', title: 'Safety Footer',
          subtitle: 'all execution gates LOCKED',
          x: 510, y: 288, w: 290, h: 78, color: COLORS.risk,
          lines: () => [
            'worker_execution_enabled: false',
            'provider_execution_enabled: false',
            'openclaw_execution_enabled: false',
            'autonomous_dispatch_enabled: false',
          ],
        },
      ],
      workers: [
        { id: 'intake_clerk',     name: 'Intake Clerk',           initial: 'IC',
          color: COLORS.worker,   home: 'intake',     neighbors: ['intake', 'screening'] },
        { id: 'screening_officer',name: 'Screening Officer',      initial: 'SO',
          color: COLORS.cross,    home: 'screening',  neighbors: ['screening', 'training'] },
        { id: 'training_coach_45',name: 'Training Coach',         initial: 'TC',
          color: COLORS.paper,    home: 'training',   neighbors: ['training', 'assignment'] },
        { id: 'assignment_clerk', name: 'Assignment Clerk',       initial: 'AS',
          color: COLORS.fx,       home: 'assignment', neighbors: ['assignment', 'dispatch'] },
        { id: 'dispatcher',       name: 'Dispatcher',             initial: 'DP',
          color: COLORS.strategy, home: 'dispatch',   neighbors: ['dispatch', 'audit_strip'] },
        { id: 'audit_clerk_45',   name: 'Recruitment Audit Clerk',initial: 'AC',
          color: COLORS.ledger,   home: 'audit_strip',neighbors: ['audit_strip', 'safety'] },
        { id: 'risk_observer',    name: 'Risk Observer',          initial: 'RO',
          color: COLORS.risk,     home: 'safety',     neighbors: ['safety', 'assignment'] },
        // A handful of in-flight recruit capsules walking the visible
        // sections so the floor looks busy.
        { id: 'recruit_a',  name: 'Equity Market Scout',   initial: 'EM',
          color: COLORS.stocks,   home: 'training',   neighbors: ['training', 'assignment', 'dispatch'] },
        { id: 'recruit_b',  name: 'Crypto Market Scout',   initial: 'CM',
          color: COLORS.crypto,   home: 'screening',  neighbors: ['screening', 'training', 'assignment'] },
        { id: 'recruit_c',  name: 'Risk Gatekeeper',       initial: 'RG',
          color: COLORS.risk,     home: 'intake',     neighbors: ['intake', 'screening', 'training'] },
        { id: 'recruit_d',  name: 'Ledger Runner',         initial: 'LR',
          color: COLORS.ledger,   home: 'assignment', neighbors: ['assignment', 'dispatch'] },
      ],
      packet_routes: [
        { from: 'intake',     to: 'screening',   color: COLORS.worker,   period_ms: 1800 },
        { from: 'screening',  to: 'training',    color: COLORS.cross,    period_ms: 2200 },
        { from: 'training',   to: 'assignment',  color: COLORS.paper,    period_ms: 2400 },
        { from: 'assignment', to: 'dispatch',    color: COLORS.fx,       period_ms: 2000 },
        { from: 'dispatch',   to: 'audit_strip', color: COLORS.ledger,   period_ms: 2600 },
        { from: 'dispatch',   to: 'safety',      color: COLORS.risk,     period_ms: 3000 },
      ],
    };
  }

  function layoutForRecruitment(detail) {
    const s = detail.sandbox || {};
    const ra = detail.recruitment_agency || {};
    const byStage = ra.by_stage || {};
    return {
      title_color: COLORS.worker,
      sections: [
        { id: 'reception', title: 'Reception Desk', subtitle: 'arrivals · candidate intake',
          x: 20,  y: 38,  w: 175, h: 100, color: COLORS.worker,
          lines: () => [
            'agency: ' + (ra.agency_name || 'Worker Recruitment Agency'),
            'total: ' + (ra.total_workers || 0),
            'candidates: ' + (byStage.candidate || 0),
            'onboarded: ' + (byStage.onboarded || 0),
          ],
        },
        { id: 'interview', title: 'Interview Rooms', subtitle: 'candidate → interviewed',
          x: 215, y: 38,  w: 175, h: 100, color: COLORS.strategy,
          lines: () => [
            'in interview: ' + (byStage.interviewed || 0),
            'allowed_actions: read_registries · heartbeat',
            'forbidden: live_trading · order_execution',
          ],
        },
        { id: 'training', title: 'Training Room', subtitle: 'capability ramp-up',
          x: 410, y: 38,  w: 175, h: 100, color: COLORS.paper,
          lines: () => [
            'in training: ' + (byStage.onboarded || 0),
            'in probation: ' + (byStage.probation || 0),
            'training is observation-only',
          ],
        },
        { id: 'cap_board', title: 'Capability Board', subtitle: 'skills + roles',
          x: 605, y: 38,  w: 195, h: 100, color: COLORS.cross,
          lines: () => [
            'roles: market_scout · spread_watcher',
            '       strategy_analyst · risk_sentinel',
            '       ledger_clerk · readiness_auditor',
            '       openclaw_observer (advisory)',
          ],
        },
        { id: 'roster_wall', title: 'Worker Roster Wall', subtitle: ((ra.total_workers || 0) + ' total · ' + (ra.active_advisory + ra.active_read_only || 0) + ' active'),
          x: 20,  y: 156, w: 370, h: 100, color: COLORS.fx,
          lines: () => [
            'active_advisory: ' + (ra.active_advisory || 0),
            'active_read_only: ' + (ra.active_read_only || 0),
            'ready_for_openclaw_review: ' + (ra.ready_for_openclaw_review || 0),
            'rejected/retired: ' + (byStage.rejected || 0),
          ],
        },
        { id: 'openclaw_gate', title: 'OpenClaw Review Gate', subtitle: 'advisory readiness only — door LOCKED',
          x: 410, y: 156, w: 390, h: 100, color: COLORS.openclaw,
          lines: () => [
            'OpenClaw_ready: ' + (ra.openclaw_ready_count || 0),
            'OpenClaw_execution_enabled: false',
            'recruitment_openclaw_execution_enabled: false',
            'readiness_badge ≠ execution_permission',
          ],
        },
        { id: 'dispatch_queue', title: 'Dispatch Queue', subtitle: 'paper-only background loop',
          x: 20,  y: 274, w: 280, h: 88, color: COLORS.strategy,
          lines: () => [
            'autoloop: ' + (s.autoloop_status || '—') + ' · cycle ' + (s.autoloop_cycle_index || 0),
            'mode: ' + (s.autoloop_mode || 'paper_only_background_loop'),
            'lift_packets: ' + (s.lift_packet_count || 0),
          ],
        },
        { id: 'audit_desk', title: 'Audit Desk', subtitle: 'logs to data/logs/recruitment_agency.jsonl',
          x: 320, y: 274, w: 230, h: 88, color: COLORS.ledger,
          lines: () => ['append-only audit · advisory_only'],
        },
        { id: 'risk_door', title: 'Risk Approval Door — LOCKED', subtitle: 'execution stays disabled',
          x: 570, y: 274, w: 230, h: 88, color: COLORS.risk,
          lines: () => [
            'live_trading: OFF · order_execution: OFF',
            'openclaw_execution: OFF',
            'autonomous_dispatch: OFF',
            'provider_access: OFF',
          ],
        },
      ],
      workers: [
        { id: 'reception_clerk',         name: 'Reception Clerk',              initial: 'RC', color: COLORS.worker,  home: 'reception',      neighbors: ['reception', 'interview'] },
        { id: 'interview_panel',         name: 'Interview Panel',              initial: 'IP', color: COLORS.strategy,home: 'interview',      neighbors: ['interview', 'training'] },
        { id: 'training_coach',          name: 'Training Coach',               initial: 'TC', color: COLORS.paper,   home: 'training',       neighbors: ['training', 'cap_board'] },
        { id: 'capability_curator',      name: 'Capability Board Curator',     initial: 'CB', color: COLORS.cross,   home: 'cap_board',      neighbors: ['cap_board', 'roster_wall'] },
        { id: 'roster_clerk',            name: 'Roster Wall Clerk',            initial: 'RW', color: COLORS.fx,      home: 'roster_wall',    neighbors: ['roster_wall', 'openclaw_gate'] },
        { id: 'openclaw_gatekeeper',     name: 'OpenClaw Gatekeeper',          initial: 'OG', color: COLORS.openclaw,home: 'openclaw_gate',  neighbors: ['openclaw_gate', 'risk_door'] },
        { id: 'dispatch_dispatcher',     name: 'Dispatch Queue Dispatcher',    initial: 'DD', color: COLORS.strategy,home: 'dispatch_queue', neighbors: ['dispatch_queue', 'audit_desk'] },
        { id: 'audit_clerk',             name: 'Recruitment Audit Clerk',      initial: 'AC', color: COLORS.ledger,  home: 'audit_desk',     neighbors: ['audit_desk', 'roster_wall'] },
      ],
      packet_routes: [
        { from: 'reception',     to: 'interview',      color: COLORS.worker,   period_ms: 2300 },
        { from: 'interview',     to: 'training',       color: COLORS.strategy, period_ms: 2500 },
        { from: 'training',      to: 'cap_board',      color: COLORS.paper,    period_ms: 2700 },
        { from: 'cap_board',     to: 'roster_wall',    color: COLORS.cross,    period_ms: 2900 },
        { from: 'roster_wall',   to: 'openclaw_gate',  color: COLORS.openclaw, period_ms: 3100 },
        { from: 'openclaw_gate', to: 'risk_door',      color: COLORS.risk,     period_ms: 3300 },
        { from: 'dispatch_queue',to: 'audit_desk',     color: COLORS.ledger,   period_ms: 2400 },
        { from: 'audit_desk',    to: 'roster_wall',    color: COLORS.ledger,   period_ms: 3600 },
      ],
    };
  }

  function layoutForSpeech(detail) {
    const sp = detail.speech_floor || {};
    return {
      title_color: COLORS.airllm,
      sections: [
        { id: 'tts_desk', title: 'TTS Output Desk', subtitle: 'browser SpeechSynthesisUtterance',
          x: 20,  y: 38,  w: 380, h: 110, color: COLORS.airllm,
          lines: () => [
            'engine: ' + (sp.tts_engine || 'browser_web_speech_synthesis'),
            'status: ' + (sp.tts_status || 'browser_only'),
            'route: kernel reply → SpeechSynthesisUtterance',
            'local_sidecar_present: ' + String(!!sp.local_sidecar_present),
            'external_speech_provider: ' + (sp.external_speech_provider || 'none'),
          ],
        },
        { id: 'stt_desk', title: 'STT Intake Desk', subtitle: 'browser SpeechRecognition',
          x: 420, y: 38,  w: 380, h: 110, color: COLORS.cross,
          lines: () => [
            'engine: ' + (sp.stt_engine || 'browser_web_speech_recognition'),
            'status: ' + (sp.stt_status || 'browser_only'),
            'route: mic → /api/kernel_chat → sidecar :8766',
          ],
        },
        { id: 'route_pipeline', title: 'Speech ↔ Kernel Route', subtitle: 'browser-native only · no external provider',
          x: 20,  y: 168, w: 780, h: 80, color: COLORS.kernel,
          lines: () => [
            'speech_to_kernel: ' + (sp.speech_to_kernel_route || 'browser → /api/kernel_chat → sidecar:8766'),
            'kernel_reply_to_tts: ' + (sp.kernel_reply_to_tts_route || 'kernel → SpeechSynthesisUtterance'),
          ],
        },
        { id: 'safety_strip', title: 'Safety', subtitle: 'advisory-only · paper-only',
          x: 20,  y: 268, w: 380, h: 94, color: COLORS.ok,
          lines: () => ['advisory_only: true', 'execution_allowed: false', 'no external speech provider'],
        },
        { id: 'media_link', title: 'Media Floor Link', subtitle: '→ Floor 14',
          x: 420, y: 268, w: 380, h: 94, color: COLORS.paper,
          lines: () => ['media_floor: floor_14 · Media Department'],
        },
      ],
      workers: [
        { id: 'tts_clerk', name: 'TTS Output Clerk', initial: 'TT', color: COLORS.airllm, home: 'tts_desk', neighbors: ['tts_desk', 'route_pipeline'] },
        { id: 'stt_clerk', name: 'STT Intake Clerk', initial: 'ST', color: COLORS.cross,  home: 'stt_desk', neighbors: ['stt_desk', 'route_pipeline'] },
        { id: 'media_liaison', name: 'Media Floor Liaison', initial: 'ML', color: COLORS.paper, home: 'media_link', neighbors: ['media_link', 'route_pipeline'] },
      ],
      packet_routes: [
        { from: 'stt_desk',       to: 'route_pipeline', color: COLORS.cross,  period_ms: 2400 },
        { from: 'route_pipeline', to: 'tts_desk',       color: COLORS.airllm, period_ms: 2600 },
        { from: 'media_link',     to: 'route_pipeline', color: COLORS.paper,  period_ms: 3200 },
      ],
    };
  }

  function layoutForMedia(detail) {
    const m = detail.media_floor || {};
    const routes = m.media_routes || {};
    return {
      title_color: COLORS.paper,
      sections: [
        { id: 'media_dispatch', title: 'Media Routing Desk', subtitle: 'paper-only',
          x: 20,  y: 38,  w: 380, h: 110, color: COLORS.paper,
          lines: () => [
            'speech_floor_link: ' + (m.speech_floor_link || 'floor_15'),
            'kernel_chat_audio: ' + (routes.kernel_chat_audio || '—'),
            'advisory_text: ' + (routes.advisory_text || '—'),
            'external_media_provider: ' + (m.external_media_provider || 'none'),
          ],
        },
        { id: 'speech_link', title: 'Speech Floor Link', subtitle: '→ Floor 15',
          x: 420, y: 38,  w: 380, h: 110, color: COLORS.airllm,
          lines: () => ['speech_floor: floor_15 · Speech and Audio Department'],
        },
        { id: 'safety', title: 'Safety', subtitle: 'advisory only',
          x: 20,  y: 168, w: 780, h: 80, color: COLORS.ok,
          lines: () => ['advisory_only: true · execution_allowed: false · no external media provider'],
        },
      ],
      workers: [
        { id: 'media_liaison', name: 'Media Floor Liaison', initial: 'ML', color: COLORS.paper, home: 'media_dispatch', neighbors: ['media_dispatch', 'speech_link'] },
      ],
      packet_routes: [
        { from: 'media_dispatch', to: 'speech_link', color: COLORS.paper, period_ms: 3000 },
      ],
    };
  }

  function layoutForSandbox(detail) {
    const s = detail.sandbox || {};
    return {
      title_color: COLORS.worker,
      sections: [
        { id: 'worker_sandbox', title: 'Worker Sandbox', subtitle: 'sandbox-only · no real execution',
          x: 20,  y: 38,  w: 260, h: 116, color: COLORS.worker,
          lines: () => [
            'latest_tick: ' + (s.worker_sandbox_latest_tick_ts || '—'),
            'lift_packets: ' + (s.lift_packet_count || 0),
            'worker_execution: OFF',
          ],
        },
        { id: 'oc_visual', title: 'OpenClaw Visual Sandbox', subtitle: 'observe_only',
          x: 300, y: 38,  w: 260, h: 116, color: COLORS.openclaw,
          lines: () => [
            'openclaw_ts: ' + (s.openclaw_ts || '—'),
            'recommendations: ' + (s.openclaw_recommendation_count || 0),
            'openclaw_execution: OFF',
          ],
        },
        { id: 'perf_loop', title: 'Sandbox Performance Loop', subtitle: 'paper performance metrics',
          x: 20,  y: 168, w: 540, h: 64,  color: COLORS.strategy,
          lines: () => ['perf_ts: ' + (s.sandbox_performance_ts || '—') + ' · paper-only loop'],
        },
        { id: 'autoloop', title: 'AutoLoop Cycle', subtitle: 'paper_only_background_loop',
          x: 20,  y: 246, w: 260, h: 116, color: COLORS.kernel,
          lines: () => [
            'status: ' + (s.autoloop_status || '—'),
            'cycle_index: ' + (s.autoloop_cycle_index || 0),
            'mode: ' + (s.autoloop_mode || 'paper_only_background_loop'),
          ],
        },
        { id: 'packet_queue', title: 'Packet Queue', subtitle: 'outbound to Risk/Audit',
          x: 300, y: 246, w: 260, h: 116, color: COLORS.ledger,
          lines: () => [
            'packets_queued: ' + (s.lift_packet_count || 0),
            'no_real_execution: true',
          ],
        },
      ],
      workers: [
        { id: 'market_scout',     name: 'Market Scout',      initial: 'MS', color: COLORS.fx,       home: 'worker_sandbox', neighbors: ['worker_sandbox', 'perf_loop'] },
        { id: 'spread_watcher',   name: 'Spread Watcher',    initial: 'SW', color: COLORS.fx,       home: 'worker_sandbox', neighbors: ['worker_sandbox', 'autoloop'] },
        { id: 'risk_sentinel',    name: 'Risk Sentinel',     initial: 'RS', color: COLORS.risk,    home: 'autoloop',        neighbors: ['autoloop', 'packet_queue'] },
        { id: 'paper_strategy',   name: 'Paper Strategy Analyst', initial: 'PS', color: COLORS.strategy, home: 'perf_loop', neighbors: ['perf_loop', 'oc_visual'] },
        { id: 'kernel_commentary',name: 'Kernel Commentary Runner', initial: 'KC', color: COLORS.kernel, home: 'autoloop',  neighbors: ['autoloop', 'worker_sandbox'] },
        { id: 'ledger_clerk',     name: 'Ledger Clerk',      initial: 'LC', color: COLORS.ledger,   home: 'packet_queue',  neighbors: ['packet_queue', 'autoloop'] },
        { id: 'oc_lift_observer', name: 'OpenClaw Lift Observer', initial: 'OL', color: COLORS.openclaw, home: 'oc_visual', neighbors: ['oc_visual', 'packet_queue'] },
      ],
      packet_routes: [
        { from: 'worker_sandbox', to: 'perf_loop',     color: COLORS.worker,   period_ms: 2200 },
        { from: 'perf_loop',      to: 'autoloop',      color: COLORS.strategy, period_ms: 2400 },
        { from: 'autoloop',       to: 'packet_queue',  color: COLORS.kernel,   period_ms: 2600 },
        { from: 'oc_visual',      to: 'packet_queue',  color: COLORS.openclaw, period_ms: 2800 },
      ],
    };
  }

  function layoutForStrategy(detail) {
    const s = detail.strategy || {};
    return {
      title_color: COLORS.strategy,
      sections: [
        { id: 'strat_intel', title: 'Strategy Intelligence', subtitle: 'paper-only intelligence',
          x: 20,  y: 38,  w: 260, h: 116, color: COLORS.strategy,
          lines: () => [
            'phase: ' + (s.phase || '—'),
            'latest_ts: ' + (s.latest_ts || '—'),
            'result_count: ' + (s.result_count || 0),
            'signal_counts: ' + JSON.stringify(s.signal_counts || {}),
          ],
        },
        { id: 'xmkt_inputs', title: 'Cross-Market Inputs', subtitle: 'floors 41 · 42 · 43',
          x: 300, y: 38,  w: 260, h: 116, color: COLORS.cross,
          lines: () => [
            'inputs_from: ' + ((s.inputs_from_floors || []).join(' · ') || 'floor_41 · floor_42 · floor_43'),
            'cross_market_pairs: ' + (s.cross_market_pair_count || 0),
          ],
        },
        { id: 'paper_sigs', title: 'Paper Signals', subtitle: 'observe / long_bias / short_bias / no_trade',
          x: 20,  y: 168, w: 540, h: 64,  color: COLORS.paper,
          lines: () => [
            'paper_only · execution_allowed=false · not_financial_advice',
          ],
        },
        { id: 'sim_status', title: 'Simulation Status', subtitle: 'paper simulation only',
          x: 20,  y: 246, w: 260, h: 116, color: COLORS.kernel,
          lines: () => [
            'correlation_ts: ' + (s.correlation_ts || '—'),
            'correlation_count: ' + (s.correlation_count || 0),
          ],
        },
        { id: 'sim_out', title: 'Simulation Outbound', subtitle: 'to Floor 38 Sandbox',
          x: 300, y: 246, w: 260, h: 116, color: COLORS.worker,
          lines: () => ['outbound_route: floor_38', 'no_real_execution: true'],
        },
      ],
      workers: [
        { id: 'strategy_intel',      name: 'Strategy Intelligence',    initial: 'SI', color: COLORS.strategy, home: 'strat_intel', neighbors: ['strat_intel', 'paper_sigs'] },
        { id: 'correlation_analyst', name: 'Correlation Analyst',      initial: 'CA', color: COLORS.cross,    home: 'xmkt_inputs', neighbors: ['xmkt_inputs', 'sim_status'] },
        { id: 'paper_strategy',      name: 'Paper Strategy Analyst',   initial: 'PS', color: COLORS.paper,    home: 'paper_sigs',  neighbors: ['paper_sigs', 'strat_intel'] },
        { id: 'equity_momentum',     name: 'Equity Momentum Analyst',  initial: 'EM', color: COLORS.stocks,   home: 'xmkt_inputs', neighbors: ['xmkt_inputs', 'paper_sigs'] },
        { id: 'xmkt_correlation',    name: 'Cross-Market Correlation Clerk', initial: 'CC', color: COLORS.cross, home: 'sim_status', neighbors: ['sim_status', 'xmkt_inputs'] },
      ],
      packet_routes: [
        { from: 'xmkt_inputs', to: 'strat_intel', color: COLORS.cross,    period_ms: 2200 },
        { from: 'strat_intel', to: 'paper_sigs',  color: COLORS.strategy, period_ms: 2400 },
        { from: 'paper_sigs',  to: 'sim_out',     color: COLORS.paper,    period_ms: 2600 },
        { from: 'sim_status',  to: 'sim_out',     color: COLORS.worker,   period_ms: 2800 },
      ],
    };
  }

  function layoutForRisk(detail) {
    const r = detail.risk || {};
    const locks = r.locks || {};
    const lockNames = Object.keys(locks);
    const lockGrid = () => {
      const rows = [];
      for (let i = 0; i < lockNames.length; i += 2) {
        const a = lockNames[i], b = lockNames[i + 1];
        rows.push(
          (a ? (a + '=' + (locks[a] ? 'TRUE' : 'false')).slice(0, 36) : '') +
          (b ? ' · ' + (b + '=' + (locks[b] ? 'TRUE' : 'false')).slice(0, 36) : '')
        );
      }
      return rows.slice(0, 6);
    };
    return {
      title_color: COLORS.risk,
      sections: [
        { id: 'lock_matrix', title: 'Lock Matrix', subtitle: (r.lock_count_true || 0) + ' / 17 TRUE — expected 0',
          x: 20,  y: 38,  w: 540, h: 116, color: COLORS.risk,
          lines: lockGrid,
        },
        { id: 'inbound_trading', title: 'Inbound from Trading Floors', subtitle: 'floors 41 · 42 · 43',
          x: 20,  y: 168, w: 260, h: 64, color: COLORS.fx,
          lines: () => ['risk_sources: floor_41 · floor_42 · floor_43 · floor_38'],
        },
        { id: 'inbound_sandbox', title: 'Inbound from Sandbox', subtitle: 'floor 38 OpenClaw',
          x: 300, y: 168, w: 260, h: 64, color: COLORS.openclaw,
          lines: () => ['openclaw_execution: OFF · advisory only'],
        },
        { id: 'outbound_audit', title: 'Outbound to Audit', subtitle: '→ Floor 31 Audit',
          x: 20,  y: 246, w: 260, h: 116, color: COLORS.ledger,
          lines: () => ['route: floor_31 · paper audit trail'],
        },
        { id: 'safety_pulse', title: 'Safety Pulse', subtitle: 'continuous lock check',
          x: 300, y: 246, w: 260, h: 116, color: COLORS.ok,
          lines: () => [
            'execution_allowed: false',
            'paper_only: true',
            'all_locks_closed: ' + ((r.lock_count_true || 0) === 0),
          ],
        },
      ],
      workers: [
        { id: 'risk_sentinel',     name: 'Risk Sentinel',           initial: 'RS', color: COLORS.risk,    home: 'lock_matrix',     neighbors: ['lock_matrix', 'safety_pulse'] },
        { id: 'risk_on_off',       name: 'Risk-On/Risk-Off Observer',initial: 'RO',color: COLORS.cross,   home: 'inbound_trading', neighbors: ['inbound_trading', 'lock_matrix'] },
        { id: 'audit_clerk',       name: 'Audit Clerk',             initial: 'AC', color: COLORS.ledger,  home: 'outbound_audit',  neighbors: ['outbound_audit', 'safety_pulse'] },
        { id: 'oc_risk_guard',     name: 'OpenClaw Risk Guard',     initial: 'OG', color: COLORS.openclaw,home: 'inbound_sandbox', neighbors: ['inbound_sandbox', 'lock_matrix'] },
      ],
      packet_routes: [
        { from: 'inbound_trading', to: 'lock_matrix',     color: COLORS.fx,       period_ms: 2200 },
        { from: 'inbound_sandbox', to: 'lock_matrix',     color: COLORS.openclaw, period_ms: 2400 },
        { from: 'lock_matrix',     to: 'outbound_audit',  color: COLORS.ledger,   period_ms: 2600 },
        { from: 'safety_pulse',    to: 'lock_matrix',     color: COLORS.ok,       period_ms: 3000 },
      ],
    };
  }

  function layoutForAudit(detail) {
    const a = detail.audit || {};
    const entries = a.latest_entries || [];
    return {
      title_color: COLORS.ledger,
      sections: [
        { id: 'ledger_counter', title: 'Ledger Counter', subtitle: 'paper-only audit trail',
          x: 20,  y: 38,  w: 260, h: 116, color: COLORS.ledger,
          lines: () => [
            'entry_count: ' + (a.entry_count || 0),
            'latest_count: ' + (a.latest_count || 0),
            'updated: ' + (a.updated_ts || '—'),
          ],
        },
        { id: 'latest_entries', title: 'Latest Entries', subtitle: 'paper observations only',
          x: 300, y: 38,  w: 260, h: 116, color: COLORS.paper,
          lines: () => {
            const lines = [];
            entries.slice(0, 4).forEach((e) => {
              lines.push(((e.instrument || '') + ' · ' + (e.paper_signal || '—') + ' · ' + clip(e.paper_reason || '', 30)).slice(0, 44));
            });
            if (!lines.length) lines.push('no recent entries');
            return lines;
          },
        },
        { id: 'audit_pulse', title: 'Audit Pulse', subtitle: 'continuous integrity check',
          x: 20,  y: 168, w: 540, h: 64, color: COLORS.ok,
          lines: () => ['paper_only_audit_trail: true · execution_allowed=false · advisory_only'],
        },
        { id: 'outbound_cmd', title: 'Outbound to Command', subtitle: '→ Floor 53',
          x: 20,  y: 246, w: 540, h: 116, color: COLORS.kernel,
          lines: () => [
            'downstream_route: ' + (a.downstream_route || 'floor_53 Tower Command'),
            'kernel_review: → penthouse',
          ],
        },
      ],
      workers: [
        { id: 'ledger_clerk',       name: 'Ledger Clerk',       initial: 'LC', color: COLORS.ledger, home: 'ledger_counter',  neighbors: ['ledger_counter', 'latest_entries'] },
        { id: 'stock_ledger_clerk', name: 'Stock Ledger Clerk', initial: 'SL', color: COLORS.stocks, home: 'latest_entries',  neighbors: ['latest_entries', 'audit_pulse'] },
        { id: 'audit_clerk',        name: 'Audit Clerk',        initial: 'AC', color: COLORS.paper,  home: 'audit_pulse',     neighbors: ['audit_pulse', 'outbound_cmd'] },
      ],
      packet_routes: [
        { from: 'latest_entries', to: 'audit_pulse',  color: COLORS.paper,  period_ms: 2200 },
        { from: 'audit_pulse',    to: 'outbound_cmd', color: COLORS.kernel, period_ms: 2500 },
        { from: 'ledger_counter', to: 'latest_entries',color: COLORS.ledger, period_ms: 2400 },
      ],
    };
  }

  function layoutForAirllm(detail) {
    const a = detail.airllm_chamber || {};
    const pv = a.package_versions || {};
    return {
      title_color: COLORS.airllm,
      sections: [
        { id: 'big_chamber', title: 'Big Model Chamber', subtitle: 'installed · advisory_only',
          x: 20,  y: 38,  w: 540, h: 116, color: COLORS.airllm,
          lines: () => [
            'path: ' + (a.path || '/vaults/ai/airllm_lab'),
            'venv: ' + (a.venv_path || '/vaults/ai/airllm_lab/.venv'),
            'env: ' + (a.env_file || '/vaults/ai/airllm_env.sh'),
            'gpu: ' + (a.gpu_name || 'NVIDIA GeForce RTX 5070 Ti') + ' · cuda: ' + (a.cuda_available ? 'true' : 'false'),
            'locks: airllm=' + (pv.airllm || '—') + ' · torch=' + (pv.torch || '—') + ' · transformers=' + (pv.transformers || '—'),
            'smoke_test: ' + (a.smoke_test_status || '—'),
          ],
        },
        { id: 'advisory_desk', title: 'Advisory Output Desk', subtitle: 'manual Ask Big Air Model only',
          x: 20,  y: 168, w: 260, h: 64, color: COLORS.cross,
          lines: () => ['no model loaded · no sidecar · no port'],
        },
        { id: 'safety_gate', title: 'Safety Isolation Gate', subtitle: 'not wired to anything',
          x: 300, y: 168, w: 260, h: 64, color: COLORS.ok,
          lines: () => ['not wired into AutoLoop / trading / OpenClaw'],
        },
        { id: 'execution_flags', title: 'Execution Flags', subtitle: 'all OFF',
          x: 20,  y: 246, w: 260, h: 116, color: COLORS.risk,
          lines: () => [
            'execution_allowed: false',
            'trading_allowed: false',
            'autoloop_allowed: false',
            'openclaw_execution_allowed: false',
            'direct_provider_access: false',
          ],
        },
        { id: 'future_lane', title: 'Future Manual Ask Lane', subtitle: 'kernel-gated · advisory only',
          x: 300, y: 246, w: 260, h: 116, color: COLORS.kernel,
          lines: () => ['advisory_only: true · advisory output only · gated by kernel review'],
        },
      ],
      workers: [
        { id: 'airllm_model_scout', name: 'AirLLM Model Scout', initial: 'AS', color: COLORS.airllm, home: 'big_chamber', neighbors: ['big_chamber', 'advisory_desk'] },
      ],
      packet_routes: [
        { from: 'big_chamber',    to: 'advisory_desk', color: COLORS.airllm, period_ms: 3600 },
        { from: 'advisory_desk',  to: 'safety_gate',   color: COLORS.cross,  period_ms: 3800 },
      ],
    };
  }

  function layoutForCommand(detail) {
    const c = detail.command || {};
    return {
      title_color: COLORS.kernel,
      sections: [
        { id: 'tower_summary', title: 'Tower Summary', subtitle: 'all floors paper-only',
          x: 20,  y: 38,  w: 260, h: 116, color: COLORS.kernel,
          lines: () => [
            'building: ' + (c.building_name || 'QSB Tower V1'),
            'kernel_installed: ' + (c.kernel_installed ? 'true' : 'false'),
            'instantiated: ' + (c.QSBKernelCore_instantiated ? 'true' : 'false'),
            'source: ' + (c.active_kernel_source || '—'),
          ],
        },
        { id: 'inbound_audit', title: 'Inbound from Audit', subtitle: 'from Floor 31',
          x: 300, y: 38,  w: 260, h: 116, color: COLORS.ledger,
          lines: () => ['paper audit packets · advisory only'],
        },
        { id: 'floor_status', title: 'Floor Status Strip', subtitle: 'all 53 floors',
          x: 20,  y: 168, w: 540, h: 64, color: COLORS.fx,
          lines: () => ['floors 01–53 reporting · highlighted: 23/24/25/30/31/37/38/41/42/43/53'],
        },
        { id: 'kernel_review', title: 'Kernel Review Route', subtitle: '→ Penthouse',
          x: 20,  y: 246, w: 540, h: 116, color: COLORS.kernel,
          lines: () => [
            'activation: ' + (c.activation_status || 'active_local_only'),
            'kernel_review_route: penthouse · advisory only',
            'no_execution_unlocks: true',
          ],
        },
      ],
      workers: [
        { id: 'tower_command_clerk', name: 'Tower Command Clerk', initial: 'TC', color: COLORS.kernel, home: 'tower_summary', neighbors: ['tower_summary', 'kernel_review'] },
        { id: 'audit_arrival',       name: 'Audit Arrival Clerk', initial: 'AA', color: COLORS.ledger, home: 'inbound_audit', neighbors: ['inbound_audit', 'tower_summary'] },
        { id: 'kernel_runner',       name: 'Kernel Commentary Runner', initial: 'KC', color: COLORS.kernel, home: 'kernel_review', neighbors: ['kernel_review', 'floor_status'] },
      ],
      packet_routes: [
        { from: 'inbound_audit', to: 'tower_summary', color: COLORS.ledger, period_ms: 2400 },
        { from: 'tower_summary', to: 'kernel_review', color: COLORS.kernel, period_ms: 2600 },
      ],
    };
  }

  function layoutForPenthouse(detail) {
    const k = detail.penthouse || detail.command || {};
    const rs = k.recruitment_summary || {};
    return {
      title_color: COLORS.kernel,
      kernel_core_special: true,  // hint to renderer to draw the orbiting-ring core
      sections: [
        { id: 'kernel_core', title: 'QSB Kernel Core', subtitle: 'active_local_only · rebased_kernel · ring-bus',
          x: 230, y: 60,  w: 360, h: 200, color: COLORS.kernel,
          lines: () => [
            'activation: ' + (k.activation_status || 'active_local_only'),
            'source: ' + (k.active_kernel_source || 'rebased_kernel'),
            'local_model: ' + (k.selected_model || 'llama3.2:latest'),
            'kernel_installed: ' + (k.kernel_installed === false ? 'false' : 'true'),
            'external_providers: OFF · OpenClaw_execution: OFF',
            'lock_count_true: 0 (expected 0)',
          ],
        },
        { id: 'memory_bus', title: 'Memory Bus', subtitle: 'kernel ↔ registries',
          x: 20,  y: 38,  w: 200, h: 84, color: COLORS.cross,
          lines: () => ['route: /api/unified · /api/floor_detail', 'no_external_persistence'],
        },
        { id: 'audio_bus', title: 'Audio / Speech Bus', subtitle: 'floor_15 → browser',
          x: 20,  y: 130, w: 200, h: 84, color: COLORS.airllm,
          lines: () => [
            'tts: ' + (k.tts_engine || 'browser_web_speech_synthesis'),
            'stt: ' + (k.stt_engine || 'browser_web_speech_recognition'),
            'speech_floor: ' + (k.speech_floor || 'floor_15'),
            'media_floor:  ' + (k.media_floor || 'floor_14'),
          ],
        },
        { id: 'floor_telemetry', title: 'Floor Telemetry Bus', subtitle: 'all 53 floors',
          x: 20,  y: 222, w: 200, h: 80, color: COLORS.strategy,
          lines: () => ['rooms: 1–53 · roof locked · ground active'],
        },
        { id: 'risk_bus', title: 'Risk / Lock Bus', subtitle: '0 / 21 TRUE — expected 0',
          x: 600, y: 38,  w: 200, h: 84, color: COLORS.ok,
          lines: () => ['floor_30 ⟷ kernel · lock_audit each tick'],
        },
        { id: 'airllm_bus', title: 'AirLLM Advisory Bus', subtitle: 'floor_23 advisory_only',
          x: 600, y: 130, w: 200, h: 84, color: COLORS.airllm,
          lines: () => ['airllm_chamber: installed_advisory_only', 'not wired to AutoLoop/trading/OpenClaw'],
        },
        { id: 'recruit_bus', title: 'Recruitment Bus', subtitle: 'floor_38 → kernel_review',
          x: 600, y: 222, w: 200, h: 80, color: COLORS.worker,
          lines: () => [
            'workers: ' + (rs.total_workers || 0) +
              ' · advisory: ' + (rs.active_advisory || 0) +
              ' · read_only: ' + (rs.active_read_only || 0),
            'OpenClaw_ready: ' + (rs.openclaw_ready_count || 0) +
              ' · candidates: ' + (rs.candidates || 0),
            'OpenClaw_execution: OFF · recruitment_OpenClaw: OFF',
          ],
        },
        { id: 'chat_dock', title: 'Kernel Chat Dock', subtitle: 'sidecar :8766 · POST /api/kernel_chat',
          x: 230, y: 282, w: 360, h: 80, color: COLORS.cross,
          lines: () => [
            'embedded live chat below · Web Speech mic/speaker',
            'view-only when sidecar offline',
          ],
        },
      ],
      workers: [
        { id: 'kernel_core_runner', name: 'Kernel Core Runner', initial: 'KR', color: COLORS.kernel, home: 'kernel_core',     neighbors: ['kernel_core', 'chat_dock'] },
        { id: 'local_model_scout',  name: 'Local Model Scout',  initial: 'LM', color: COLORS.airllm, home: 'audio_bus',       neighbors: ['audio_bus', 'kernel_core'] },
        { id: 'memory_runner',      name: 'Memory Runner',      initial: 'MR', color: COLORS.cross,  home: 'memory_bus',      neighbors: ['memory_bus', 'kernel_core'] },
        { id: 'risk_runner',        name: 'Risk Runner',        initial: 'RR', color: COLORS.ok,     home: 'risk_bus',        neighbors: ['risk_bus', 'kernel_core'] },
        { id: 'recruit_runner',     name: 'Recruitment Runner', initial: 'RX', color: COLORS.worker, home: 'recruit_bus',     neighbors: ['recruit_bus', 'kernel_core'] },
        { id: 'airllm_runner',      name: 'AirLLM Advisory Runner', initial: 'AA', color: COLORS.airllm, home: 'airllm_bus',  neighbors: ['airllm_bus', 'kernel_core'] },
      ],
      packet_routes: [
        { from: 'memory_bus',       to: 'kernel_core', color: COLORS.cross,    period_ms: 2200 },
        { from: 'audio_bus',        to: 'kernel_core', color: COLORS.airllm,   period_ms: 2400 },
        { from: 'floor_telemetry',  to: 'kernel_core', color: COLORS.strategy, period_ms: 2600 },
        { from: 'risk_bus',         to: 'kernel_core', color: COLORS.ok,       period_ms: 2800 },
        { from: 'airllm_bus',       to: 'kernel_core', color: COLORS.airllm,   period_ms: 3200 },
        { from: 'recruit_bus',      to: 'kernel_core', color: COLORS.worker,   period_ms: 3400 },
        { from: 'kernel_core',      to: 'chat_dock',   color: COLORS.kernel,   period_ms: 2000 },
      ],
    };
  }

  function layoutGeneric(detail) {
    return {
      title_color: COLORS.muted,
      sections: [
        { id: 'identity', title: detail.canonical_name || ('Floor ' + detail.floor_number),
          subtitle: detail.category || 'infrastructure',
          x: 20, y: 38, w: 540, h: 116, color: COLORS.routing,
          lines: () => [
            'floor_id: ' + (detail.floor_id || '—'),
            'category: ' + (detail.category || '—'),
            'status: ' + (detail.status || '—'),
            'zone: ' + (detail.zone || '—'),
            'manifest: ' + (detail.manifest_path ? 'present' : '—'),
          ],
        },
        { id: 'safety', title: 'Safety',
          subtitle: 'paper-only · read-only',
          x: 20, y: 168, w: 540, h: 64, color: COLORS.ok,
          lines: () => ['execution_allowed: false · paper_only: true · advisory_only: true'],
        },
        { id: 'routes', title: 'Connected Routes',
          subtitle: ((detail.routes && detail.routes.outbound) || []).length + ' out · ' +
                    ((detail.routes && detail.routes.inbound)  || []).length + ' in',
          x: 20, y: 246, w: 540, h: 116, color: COLORS.muted,
          lines: () => {
            const ro = (detail.routes && detail.routes.outbound) || [];
            return ro.slice(0, 4).map((r) => r.source_floor + ' → ' + r.target_floor + ' · ' + (r.route_type || ''));
          },
        },
      ],
      workers: [],
      packet_routes: [],
    };
  }

  function pickLayout(detail) {
    const n = detail.floor_number;
    if (n === 14) return layoutForMedia(detail);
    if (n === 15) return layoutForSpeech(detail);
    if (n === 41) return layoutForOanda(detail);
    if (n === 42) return layoutForBinance(detail);
    if (n === 43) return layoutForStocks(detail);
    // Floor 45 — dedicated Worker Recruitment Agency interior.
    if (n === 45) return layoutForFloor45Recruitment(detail);
    // Floor 38 keeps its sandbox + legacy recruitment overlay layout.
    if (n === 38) return layoutForRecruitment(detail);
    if (n === 37) return layoutForStrategy(detail);
    if (n === 30) return layoutForRisk(detail);
    if (n === 31) return layoutForAudit(detail);
    if (n === 23) return layoutForAirllm(detail);
    if (n === 53) return layoutForCommand(detail);
    if (n === 55 || detail.category === 'kernel') return layoutForPenthouse(detail);
    return layoutGeneric(detail);
  }

  // ── builders ───────────────────────────────────────────────────────────
  function buildSections(ctx) {
    const layout = ctx.layout;
    const svg = ctx.svg;

    // BG glow
    mk('rect', { x: 0, y: 0, width: VIEW_W, height: VIEW_H, fill: 'url(#qsbFiBg)' }, svg);
    // Floor grid (faint)
    for (let x = 0; x < VIEW_W; x += 40) {
      mk('line', { x1: x, y1: 0, x2: x, y2: VIEW_H, stroke: 'rgba(80,140,210,0.06)', 'stroke-width': '1' }, svg);
    }
    for (let y = 0; y < VIEW_H; y += 40) {
      mk('line', { x1: 0, y1: y, x2: VIEW_W, y2: y, stroke: 'rgba(80,140,210,0.06)', 'stroke-width': '1' }, svg);
    }

    // Special kernel core (Penthouse): orbiting rings + glowing reactor
    if (layout.kernel_core_special) {
      const cx = VIEW_W / 2, cy = VIEW_H / 2 + 12;
      const ringGroup = mk('g', { class: 'qsb-fi-rings' }, svg);
      for (let i = 0; i < 5; i++) {
        const r = 70 + i * 22;
        const ring = mk('ellipse', {
          cx: cx, cy: cy, rx: r, ry: r * 0.34,
          fill: 'none',
          stroke: ['#ffd24c', '#6ab8ff', '#7fc8ff', '#4dffb0', '#c8a6ff'][i],
          'stroke-width': '1.2',
          opacity: 0.45 - i * 0.05,
        }, ringGroup);
        ring._phase = i * 0.7;
        ring._speed = 0.12 + i * 0.06;
        if (!layout._rings) layout._rings = [];
        layout._rings.push({ el: ring, base: { rx: r, ry: r * 0.34, cx, cy }, phase: i * 0.7, speed: 0.12 + i * 0.06 });
      }
      // Central reactor orb
      const orb = mk('circle', {
        cx: cx, cy: cy, r: 32,
        fill: 'url(#qsbFiCore)',
        stroke: '#ffe080', 'stroke-width': '1.6',
        filter: 'url(#qsbFiGlow)',
      }, svg);
      layout._orb = orb;
      // Pulse ring around the core (kernel pulse)
      const pulse = mk('circle', {
        cx: cx, cy: cy, r: 32,
        fill: 'none', stroke: '#ffd24c', 'stroke-width': '1.4', opacity: 0.6,
      }, svg);
      layout._pulse = pulse;
    }

    layout.sections.forEach((sec) => {
      const g = mk('g', { class: 'qsb-fi-section' }, svg);
      mk('rect', {
        x: sec.x, y: sec.y, width: sec.w, height: sec.h,
        rx: 8, ry: 8,
        fill: 'rgba(8,18,38,0.7)',
        stroke: sec.color,
        'stroke-width': '1.5',
        'fill-opacity': '0.92',
        filter: 'url(#qsbFiGlow)',
      }, g);
      mk('text', {
        x: sec.x + 10, y: sec.y + 16,
        fill: sec.color,
        'font-size': '11', 'font-weight': '700',
        'font-family': 'Inter,Segoe UI,system-ui',
        'letter-spacing': '0.5',
      }, g).textContent = sec.title;
      if (sec.subtitle) {
        mk('text', {
          x: sec.x + 10, y: sec.y + 30,
          fill: 'rgba(170,200,235,0.7)',
          'font-size': '9', 'font-family': 'Inter,Segoe UI,system-ui',
        }, g).textContent = sec.subtitle;
      }
      // Lines container — repaint each tick via updateLines
      const linesGroup = mk('g', { class: 'qsb-fi-lines' }, g);
      sec._linesGroup = linesGroup;
      sec._cx = sec.x + sec.w / 2;
      sec._cy = sec.y + sec.h / 2;
      ctx.sections[sec.id] = sec;
    });
  }

  function updateLines(ctx) {
    for (const id of Object.keys(ctx.sections)) {
      const sec = ctx.sections[id];
      if (!sec._linesGroup) continue;
      while (sec._linesGroup.firstChild) sec._linesGroup.removeChild(sec._linesGroup.firstChild);
      const lines = (typeof sec.lines === 'function') ? sec.lines(ctx.detail) : (sec.lines || []);
      const startY = sec.y + 48;
      lines.slice(0, Math.floor((sec.h - 44) / 13)).forEach((line, i) => {
        mk('text', {
          x: sec.x + 10, y: startY + i * 13,
          fill: 'rgba(220,234,255,0.9)',
          'font-size': '9.5',
          'font-family': 'Inter,Segoe UI,system-ui,monospace',
        }, sec._linesGroup).textContent = clip(line, 76);
      });
    }
  }

  function buildWorkers(ctx) {
    const layout = ctx.layout;
    layout.workers.forEach((w, idx) => {
      const home = ctx.sections[w.home];
      if (!home) return;
      const startX = home._cx + (Math.random() - 0.5) * (home.w - 30);
      const startY = home._cy + (Math.random() - 0.5) * (home.h - 30);
      const g = mk('g', { class: 'qsb-fi-worker' }, ctx.svg);
      const dot = mk('circle', {
        cx: startX, cy: startY, r: 5.2,
        fill: w.color, stroke: '#0a1428', 'stroke-width': '0.8',
        filter: 'url(#qsbFiGlow)',
      }, g);
      const init = mk('text', {
        x: startX, y: startY + 3.4,
        fill: '#ffffff', 'font-size': '7.4',
        'font-family': 'Inter,Segoe UI,system-ui', 'font-weight': '700',
        'text-anchor': 'middle',
      }, g);
      init.textContent = w.initial || '··';
      const label = mk('text', {
        x: startX + 8, y: startY - 8,
        fill: 'rgba(220,234,255,0.92)', 'font-size': '8.4',
        'font-family': 'Inter,Segoe UI,system-ui',
        'pointer-events': 'none',
        opacity: '0.6',
      }, g);
      label.textContent = w.name;

      const wkr = {
        id: w.id, name: w.name, color: w.color, dot, init, label,
        x: startX, y: startY,
        srcId: w.home, dstId: w.home, t: 1,
        speed: 0.20 + Math.random() * 0.18,
        pulse: Math.random() * Math.PI * 2,
        neighbors: w.neighbors || [w.home],
      };
      ctx.workers.push(wkr);

      g.addEventListener('mouseenter', () => { label.setAttribute('opacity', '1'); });
      g.addEventListener('mouseleave', () => { label.setAttribute('opacity', '0.6'); });
    });
  }

  function tickWorkers(ctx, now, dt) {
    for (const w of ctx.workers) {
      if (w.t >= 1) {
        // pick a new destination from neighbors (not current)
        const opts = w.neighbors.filter((id) => id !== w.dstId);
        const next = opts[Math.floor(Math.random() * opts.length)] || w.neighbors[0];
        w.srcId = w.dstId;
        w.dstId = next;
        w.t = 0;
        const dst = ctx.sections[next];
        if (dst) {
          w._tgtX = dst._cx + (Math.random() - 0.5) * (dst.w - 36);
          w._tgtY = dst._cy + (Math.random() - 0.5) * (dst.h - 36);
        }
        w._srcX = w.x; w._srcY = w.y;
      }
      w.t = Math.min(1, w.t + w.speed * dt);
      const ease = 0.5 - Math.cos(Math.PI * w.t) / 2;
      w.x = (w._srcX || w.x) + ((w._tgtX || w.x) - (w._srcX || w.x)) * ease;
      w.y = (w._srcY || w.y) + ((w._tgtY || w.y) - (w._srcY || w.y)) * ease;
      w.pulse += dt * 3.0;
      const r = 4.6 + Math.sin(w.pulse) * 0.8;
      w.dot.setAttribute('cx', w.x.toFixed(2));
      w.dot.setAttribute('cy', w.y.toFixed(2));
      w.dot.setAttribute('r', r.toFixed(2));
      w.init.setAttribute('x', w.x.toFixed(2));
      w.init.setAttribute('y', (w.y + 3.4).toFixed(2));
      w.label.setAttribute('x', (w.x + 8).toFixed(2));
      w.label.setAttribute('y', (w.y - 8).toFixed(2));
    }
  }

  function maybeSpawnPackets(ctx, now) {
    const layout = ctx.layout;
    for (const r of layout.packet_routes) {
      if (!r._lastFire) r._lastFire = now - Math.random() * r.period_ms;
      if (now - r._lastFire >= r.period_ms) {
        r._lastFire = now;
        spawnPacket(ctx, r);
      }
    }
  }

  function spawnPacket(ctx, r) {
    const src = ctx.sections[r.from]; const dst = ctx.sections[r.to];
    if (!src || !dst) return;
    const sx = src._cx, sy = src._cy, dx = dst._cx, dy = dst._cy;
    const circle = mk('circle', {
      cx: sx, cy: sy, r: 4.0,
      fill: r.color, stroke: '#ffffff', 'stroke-width': '0.5',
      opacity: '0.95',
      filter: 'url(#qsbFiGlow)',
    }, ctx.svg);
    // small curve via control-point offset
    const ctrlX = (sx + dx) / 2 + (Math.random() - 0.5) * 80;
    const ctrlY = (sy + dy) / 2 + (Math.random() - 0.5) * 60;
    ctx.activePackets.push({ el: circle, sx, sy, dx, dy, ctrlX, ctrlY,
      born: performance.now(), dur: 1400 + Math.random() * 600 });
  }

  function tickPackets(ctx) {
    const now = performance.now();
    const remaining = [];
    for (const p of ctx.activePackets) {
      const t = (now - p.born) / p.dur;
      if (t >= 1) { if (p.el.parentNode) p.el.parentNode.removeChild(p.el); continue; }
      // quadratic bezier
      const u = 1 - t;
      const x = u * u * p.sx + 2 * u * t * p.ctrlX + t * t * p.dx;
      const y = u * u * p.sy + 2 * u * t * p.ctrlY + t * t * p.dy;
      p.el.setAttribute('cx', x.toFixed(2));
      p.el.setAttribute('cy', y.toFixed(2));
      p.el.setAttribute('opacity', (0.4 + 0.55 * Math.sin(t * Math.PI)).toFixed(3));
      remaining.push(p);
    }
    ctx.activePackets = remaining;
  }

  function tickKernelCore(ctx, now) {
    const l = ctx.layout;
    if (!l || !l.kernel_core_special) return;
    const t = now / 1000;
    if (l._rings) {
      l._rings.forEach((r, i) => {
        const wob = 1 + Math.sin(t * r.speed + r.phase) * 0.06;
        r.el.setAttribute('rx', (r.base.rx * wob).toFixed(2));
        r.el.setAttribute('ry', (r.base.ry * (2 - wob)).toFixed(2));
        r.el.setAttribute('opacity', (0.30 + 0.20 * Math.abs(Math.sin(t * 0.7 + i))).toFixed(3));
      });
    }
    if (l._pulse) {
      const k = 32 + (Math.sin(t * 1.4) * 0.5 + 0.5) * 38;
      l._pulse.setAttribute('r', k.toFixed(2));
      l._pulse.setAttribute('opacity', (0.65 - (k - 32) / 60).toFixed(3));
    }
    if (l._orb) {
      const g = 32 + Math.sin(t * 2.0) * 1.4;
      l._orb.setAttribute('r', g.toFixed(2));
    }
  }

  function startLoop(ctx) {
    let last = performance.now();
    let lineRefresh = 0;
    function frame() {
      ctx.raf = requestAnimationFrame(frame);
      if (ctx.paused) return;
      const now = performance.now();
      const dt = Math.min(0.05, (now - last) / 1000);
      last = now;
      tickWorkers(ctx, now, dt);
      maybeSpawnPackets(ctx, now);
      tickPackets(ctx);
      tickKernelCore(ctx, now);
      // refresh lines twice/sec
      if (now - lineRefresh > 500) { updateLines(ctx); lineRefresh = now; }
    }
    frame();
  }

  // ── defs (shared filter+gradient) ──────────────────────────────────────
  function injectDefs(svg) {
    const defs = mk('defs', null, svg);
    const bg = mk('radialGradient', { id: 'qsbFiBg', cx: '50%', cy: '0%', r: '90%' }, defs);
    mk('stop', { offset: '0%',  'stop-color': '#0c1a3a' }, bg);
    mk('stop', { offset: '60%', 'stop-color': '#050a1c' }, bg);
    mk('stop', { offset: '100%','stop-color': '#02050d' }, bg);
    const glow = mk('filter', { id: 'qsbFiGlow', x: '-50%', y: '-50%', width: '200%', height: '200%' }, defs);
    mk('feGaussianBlur', { stdDeviation: '1.8', result: 'b' }, glow);
    const merge = mk('feMerge', null, glow);
    mk('feMergeNode', { in: 'b' }, merge);
    mk('feMergeNode', { in: 'SourceGraphic' }, merge);
    // Kernel reactor core gradient
    const core = mk('radialGradient', { id: 'qsbFiCore', cx: '50%', cy: '50%', r: '60%' }, defs);
    mk('stop', { offset: '0%',  'stop-color': '#ffe080' }, core);
    mk('stop', { offset: '50%', 'stop-color': '#ffd24c' }, core);
    mk('stop', { offset: '100%','stop-color': 'rgba(255,201,64,0.0)' }, core);
  }

  // ── public API ─────────────────────────────────────────────────────────
  window.QSB_FLOOR_INTERIOR_RENDER = function (host, detail) {
    if (!host || !detail) return null;
    // Dispose any prior interior on this host
    dispose(host);
    const layout = pickLayout(detail);

    const svg = mk('svg', {
      viewBox: '0 0 ' + VIEW_W + ' ' + VIEW_H,
      preserveAspectRatio: 'xMidYMid meet',
      class: 'qsb-fi-svg',
    }, host);
    injectDefs(svg);

    // Top banner
    mk('text', {
      x: 14, y: 22,
      fill: layout.title_color,
      'font-size': '12', 'font-weight': '700',
      'font-family': 'Inter,Segoe UI,system-ui', 'letter-spacing': '0.6',
    }, svg).textContent = (detail.title || 'Floor ' + detail.floor_number).toUpperCase();

    mk('text', {
      x: VIEW_W - 14, y: 22,
      fill: 'rgba(170,200,235,0.7)',
      'font-size': '10', 'text-anchor': 'end',
      'font-family': 'Inter,Segoe UI,system-ui',
    }, svg).textContent = 'paper-only · execution_allowed=false · advisory';

    const ctx = {
      host, svg, layout, detail,
      sections: {}, workers: [], activePackets: [],
      raf: null, paused: false,
    };
    buildSections(ctx);
    buildWorkers(ctx);
    updateLines(ctx);
    startLoop(ctx);
    REGISTRY.set(host, ctx);
    return ctx;
  };

  window.QSB_FLOOR_INTERIOR_PAUSE = function (host, paused) {
    const ctx = REGISTRY.get(host);
    if (ctx) ctx.paused = !!paused;
  };

  window.QSB_FLOOR_INTERIOR_DISPOSE = function (host) {
    dispose(host);
  };

  function dispose(host) {
    const ctx = REGISTRY.get(host);
    if (!ctx) return;
    if (ctx.raf) { try { cancelAnimationFrame(ctx.raf); } catch (e) {} }
    if (ctx.svg && ctx.svg.parentNode) ctx.svg.parentNode.removeChild(ctx.svg);
    REGISTRY.delete(host);
  }
})();
