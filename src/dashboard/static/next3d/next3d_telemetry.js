/*
 * QSB Next3D — Telemetry Adapter
 * Phase: QSB_NEXTGEN_3D_DASHBOARD_GREENFIELD_REBUILD_V1
 *
 * Single source of truth that fetches all backend data the Next3D
 * scene needs and normalizes it into a small, stable shape.
 *
 * No fake data. No randomness. If a source is missing, the field is
 * null and downstream renderers must label it as missing.
 */
(function () {
  'use strict';

  async function fetchJSON(url) {
    try {
      const sep = url.indexOf('?') === -1 ? '?' : '&';
      const r = await fetch(url + sep + 'ts=' + Date.now(), { cache: 'no-store' });
      if (!r.ok) return null;
      return await r.json();
    } catch (_) { return null; }
  }

  async function fetchAll() {
    const [unified, sky, lifts, workers, route, tickets, role,
           f41State, f41Acct, f41Open, f41Closed, f41Pnl, f41Prices, f41Thoughts,
           f42, f43,
           penthouseState, penthouseGauges, penthouseLayout, penthouseRepair,
           intercom, intercomState] = await Promise.all([
      fetchJSON('/api/unified'),
      fetchJSON('/api/dashboard/3d_skyscraper_state'),
      fetchJSON('/api/dashboard/lift_scene_state'),
      fetchJSON('/api/dashboard/worker_scene_state'),
      fetchJSON('/api/openclaw/route'),
      fetchJSON('/api/openclaw/tickets'),
      fetchJSON('/api/openclaw/role'),
      fetchJSON('/api/trading/oanda/floor41/state'),
      fetchJSON('/api/trading/oanda/floor41/account'),
      fetchJSON('/api/trading/oanda/floor41/open_trades'),
      fetchJSON('/api/trading/oanda/floor41/closed_trades'),
      fetchJSON('/api/trading/oanda/floor41/pnl'),
      fetchJSON('/api/trading/oanda/floor41/prices'),
      fetchJSON('/api/trading/oanda/floor41/thoughts'),
      fetchJSON('/api/dashboard/floor42_binance_interior'),
      fetchJSON('/api/trading/stocks/floor43/interior'),
      fetchJSON('/api/dashboard/penthouse_command_state'),
      fetchJSON('/api/dashboard/penthouse_gauges'),
      fetchJSON('/api/dashboard/penthouse_layout'),
      fetchJSON('/api/dashboard/penthouse_repair_priority'),
      fetchJSON('/api/dashboard/intercom_packets'),
      fetchJSON('/api/dashboard/intercom_state'),
    ]);

    // Build floor catalog
    const FLOOR_CATALOG = [
      { num: 55, name: 'Penthouse · Kernel',         category: 'kernel',        special: true  },
      { num: 53, name: 'Tower Command',              category: 'command',       special: true  },
      { num: 49, name: 'Resource Management',        category: 'ops',           special: false },
      { num: 47, name: 'Executive Operations',       category: 'exec',          special: false },
      { num: 45, name: 'Worker Recruitment',         category: 'recruitment',   special: true  },
      { num: 44, name: 'Accounts / PnL',             category: 'accounts',      special: true  },
      { num: 43, name: 'Stock Exchange',             category: 'stocks',        special: true  },
      { num: 42, name: 'Binance',                    category: 'binance',       special: true  },
      { num: 41, name: 'OANDA',                      category: 'oanda',         special: true  },
      { num: 38, name: 'Sandbox Operations',         category: 'sandbox',       special: true  },
      { num: 37, name: 'Strategy Labs',              category: 'strategy',      special: true  },
      { num: 36, name: 'Expansion Planning',         category: 'ops',           special: false },
      { num: 35, name: 'Hardware Systems',           category: 'hardware',      special: true  },
      { num: 31, name: 'Audit / Ledger',             category: 'audit',         special: true  },
      { num: 30, name: 'Guardian / Risk',            category: 'guardian',      special: true  },
      { num: 25, name: 'Model Lanes',                category: 'models',        special: false },
      { num: 23, name: 'AirLLM Chamber',             category: 'airllm',        special: true  },
      { num: 22, name: 'Lifts Department',           category: 'lifts',         special: true  },
      { num: 21, name: 'Memory Floor',               category: 'memory',        special: false },
      { num: 16, name: 'Knowledge Graph',            category: 'knowledge',     special: false },
      { num: 11, name: 'Security / Secrets',         category: 'security',      special: true  },
      { num: 7,  name: 'Speech / TTS',               category: 'speech',        special: false },
    ];

    // Floor density map from worker_scene_state
    const densityByFloor = {};
    if (workers && workers.per_floor) {
      workers.per_floor.forEach(function (rec) {
        densityByFloor[rec.floor] = rec;
      });
    }

    // Build floors[] with density
    const floors = FLOOR_CATALOG.map(function (f) {
      const d = densityByFloor[f.num] || {};
      return Object.assign({}, f, {
        worker_total: d.total || 0,
        classes: d.classes || {},
      });
    });

    return {
      ts: new Date().toISOString(),
      unified: unified,
      sky: sky,
      lifts: (lifts && lifts.lifts) || [],
      workers: {
        canonical_total: (workers && workers.canonical_total) || 0,
        classes_overall: (workers && workers.classes_overall) || {},
        per_floor: (workers && workers.per_floor) || [],
      },
      openclaw: {
        current_floor: route && route.current_floor,
        advanced_by: route && route.advanced_by,
        is_random: route && route.is_random,
        ticket_count: (tickets && tickets.ticket_count)
                       || (tickets && (tickets.tickets || []).length) || 0,
        tickets: (tickets && tickets.tickets) || [],
        role: role && role.role,
        real_tool_execution: false,
      },
      floors: floors,
      floor41: {
        state: f41State,
        account: f41Acct,
        open_trades: (f41Open && f41Open.open_trades) || [],
        closed_trades: (f41Closed && f41Closed.closed_trades) || [],
        pnl: f41Pnl,
        prices: (f41Prices && f41Prices.prices) || [],
        thoughts: (f41Thoughts && f41Thoughts.thoughts) || [],
      },
      floor42: f42,
      floor43: f43,
      penthouse: {
        command: penthouseState,
        gauges: (penthouseGauges && penthouseGauges.gauges) || [],
        zones: (penthouseLayout && penthouseLayout.zones) || [],
        repair: (penthouseRepair && penthouseRepair.priorities) || [],
      },
      intercom: {
        packets: (intercom && intercom.packets) || [],
        state: intercomState,
      },
      cadence_tick: (sky && sky.cadence_tick) || 0,
      guardian_state: 'OK',
    };
  }

  window.NEXT3D_TELEMETRY = { fetchAll: fetchAll };
})();
