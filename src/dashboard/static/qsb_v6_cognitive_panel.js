/* V6 cognitive overlay — adds a floating panel showing everything I've
   built across V1-V6 on top of the existing dashboard. */

(function () {
  const ENDPOINT = '/api/cognitive_unified';
  const REFRESH_MS = 8000;

  function el(tag, cls, txt) {
    const e = document.createElement(tag);
    if (cls) e.className = cls;
    if (txt !== undefined) e.textContent = txt;
    return e;
  }

  function row(k, v, cls) {
    const r = el('div', 'v6-row');
    r.appendChild(el('span', 'v6-k', k));
    const val = el('span', 'v6-v' + (cls ? ' ' + cls : ''));
    val.textContent = (v === null || v === undefined || v === '') ? '—' : String(v);
    r.appendChild(val);
    return r;
  }

  function section(title, bodyBuilder, opts) {
    const o = opts || {};
    const sec = el('section', 'v6-section');
    if (o.collapsedByDefault) sec.classList.add('collapsed');
    const h = el('h3');
    h.appendChild(el('span', null, title));
    h.appendChild(el('span', 'v6-collapse-marker', '▾'));
    h.addEventListener('click', () => sec.classList.toggle('collapsed'));
    sec.appendChild(h);
    const body = el('div', 'v6-body');
    bodyBuilder(body);
    sec.appendChild(body);
    return sec;
  }

  function fmt(v, suffix) {
    if (v === null || v === undefined) return '—';
    if (typeof v === 'number') {
      const s = v.toLocaleString(undefined, {maximumFractionDigits: 4});
      return suffix ? s + suffix : s;
    }
    return String(v);
  }

  function pill(text) {
    const p = el('span', 'v6-mini-pill', text);
    return p;
  }

  function panelHTML(data) {
    const container = document.createDocumentFragment();
    if (!data || !data.ok) {
      container.appendChild(el('div', 'v6-warning', 'cognitive unified endpoint failed'));
      return container;
    }

    // Headline
    const head = el('div', 'v6-headline');
    head.textContent = data.headline || data.briefing?.headline || 'Tower steady';
    container.appendChild(head);

    // Briefing
    container.appendChild(section('Tower briefing', (body) => {
      const b = data.briefing || {};
      const ul = el('ul', 'v6-bullets');
      (b.bullets || []).forEach(line => {
        const li = el('li', null, line);
        ul.appendChild(li);
      });
      body.appendChild(ul);
      if ((b.pending || []).length) {
        body.appendChild(el('div', null, '◆ Awaiting Ross:'));
        const u = el('ul', 'v6-bullets');
        (b.pending || []).forEach(p => u.appendChild(el('li', 'pending', p)));
        body.appendChild(u);
      }
      if ((b.risks || []).length) {
        body.appendChild(el('div', null, '⚠ Risks:'));
        const u = el('ul', 'v6-bullets');
        (b.risks || []).forEach(p => u.appendChild(el('li', 'risk', p)));
        body.appendChild(u);
      }
    }));

    // Trading sessions
    container.appendChild(section('World clock + trading sessions', (body) => {
      const s = data.trading_sessions || {};
      body.appendChild(row('utc_now', s.utc_now));
      body.appendChild(row('regime', s.regime,
        s.regime === 'peak_liquidity' ? 'good'
        : (s.regime === 'low_liquidity' ? 'warn' : '')));
      const pr = el('div', 'v6-pillrow');
      (s.open_sessions || []).forEach(x => pr.appendChild(pill('● ' + x)));
      (s.active_overlaps || []).forEach(x => {
        const p = pill('↔ ' + x); p.style.background = '#6b8cff'; p.style.color = '#0c0e14';
        pr.appendChild(p);
      });
      body.appendChild(pr);
      (s.instrument_advice || []).forEach(ia => {
        const cls = ia.advice === 'peak' ? 'good'
                  : (ia.advice === 'thin' ? 'warn' : '');
        body.appendChild(row(ia.instrument, ia.advice, cls));
      });
    }));

    // OANDA live
    container.appendChild(section('OANDA practice — LIVE account', (body) => {
      const a = (data.oanda_account || {}).account_summary || {};
      body.appendChild(row('balance', fmt(a.balance, ' ' + (a.currency || ''))));
      body.appendChild(row('NAV', fmt(a.NAV)));
      body.appendChild(row('open_trade_count', a.openTradeCount));
      body.appendChild(row('unrealizedPL', a.unrealizedPL, parseFloat(a.unrealizedPL) > 0 ? 'good' : (parseFloat(a.unrealizedPL) < 0 ? 'bad' : '')));
      body.appendChild(row('realizedPL_today', a.pl, parseFloat(a.pl) > 0 ? 'good' : (parseFloat(a.pl) < 0 ? 'bad' : '')));
      const trades = (data.oanda_account || {}).open_trades || [];
      if (trades.length) {
        body.appendChild(el('div', null, 'Open trades:'));
        trades.forEach(t => {
          const owners = (data.oanda_account || {}).worker_ownership || {};
          const owner = owners[String(t.id)] || '(no worker)';
          body.appendChild(row(
            `id=${t.id} ${t.instrument} ${t.initialUnits}`,
            `unrealizedPL=${t.unrealizedPL}  • ${owner}`
          ));
        });
      }
    }));

    // Bank
    container.appendChild(section('Bank — QBC', (body) => {
      const b = data.bank || {};
      body.appendChild(row('outstanding', fmt(b.outstanding_supply, ' QBC')));
      body.appendChild(row('utilisation', (b.utilisation * 100).toFixed(2) + '%'));
      body.appendChild(row('accounts', b.account_count));
      body.appendChild(row('txn_count', b.txn_count));
      body.appendChild(row('top10_concentration', (b.top10_concentration * 100).toFixed(1) + '%'));
      (b.top_balances || []).forEach(a => {
        body.appendChild(row(a.worker_id, fmt(a.balance, ' QBC')));
      });
    }));

    // Lineage
    container.appendChild(section('Lineage — friends + family tree', (body) => {
      const l = data.lineage || {};
      body.appendChild(row('friend_edges', l.friend_edge_count));
      body.appendChild(row('child_edges', l.child_edge_count));
      body.appendChild(row('generations', JSON.stringify(l.generation_counts || {})));
      (l.friends || []).forEach(f => body.appendChild(row(f.a + ' ↔ ' + f.b, '')));
      (l.children || []).forEach(c => body.appendChild(row(c.parent_id + ' → ' + c.child_id, c.status)));
    }));

    // Certifications + worker PnL
    container.appendChild(section('Workers — certs + PnL', (body) => {
      const c = data.certifications || {};
      const p = data.worker_pnl || {};
      body.appendChild(row('certified workers', JSON.stringify(c.by_status || {})));
      body.appendChild(row('PnL workers tracked', p.worker_count));
      body.appendChild(row('total practice PnL', fmt(p.total_realized_pnl_practice, ' £')));
      (p.top_earners || []).slice(0, 4).forEach(r => {
        const cls = r.realized_pnl > 0 ? 'good' : (r.realized_pnl < 0 ? 'bad' : '');
        body.appendChild(row(r.worker_id, fmt(r.realized_pnl, ' £'), cls));
      });
    }));

    // Floor 46 — Commerce
    container.appendChild(section('Floor 46 — Commerce Wing', (body) => {
      const c = data.commerce_floor_46 || {};
      body.appendChild(row('status', c.status));
      body.appendChild(row('products', c.product_count));
      body.appendChild(row('proj. revenue', fmt(c.projected_monthly_revenue, ' $/mo')));
      body.appendChild(row('proj. profit', fmt(c.projected_monthly_profit, ' $/mo')));
    }));

    // Floor 48 — Lumen
    container.appendChild(section('Floor 48 — Lumen AI', (body) => {
      const l = data.lumen_ai_floor_48 || {};
      body.appendChild(row('status', l.status));
      body.appendChild(row('brand', l.brand_name));
      body.appendChild(row('conversations', l.conversation_count));
      const a = document.createElement('a');
      a.className = 'v6-link'; a.target = '_blank';
      a.href = l.website || '#'; a.textContent = l.website || '—';
      const r = el('div', 'v6-row');
      r.appendChild(el('span', 'v6-k', 'website'));
      r.appendChild(a);
      body.appendChild(r);
    }));

    // Floor 49 — Tower Studio
    container.appendChild(section('Floor 49 — Tower Studio', (body) => {
      const s = data.tower_studio_floor_49 || {};
      body.appendChild(row('status', s.status));
      body.appendChild(row('workers', s.worker_count));
      body.appendChild(row('services', s.service_count));
      body.appendChild(row('customers', s.customer_count));
      body.appendChild(row('projects', s.project_count));
      body.appendChild(row('quoted total', fmt(s.total_quoted_usd, ' USD')));
      const a = document.createElement('a');
      a.className = 'v6-link'; a.target = '_blank';
      a.href = s.website || '#'; a.textContent = s.website || '—';
      const r = el('div', 'v6-row');
      r.appendChild(el('span', 'v6-k', 'website'));
      r.appendChild(a);
      body.appendChild(r);
    }));

    // Floor 42 — Binance testnet
    container.appendChild(section('Floor 42 — Binance Testnet', (body) => {
      const b = data.binance_testnet || {};
      body.appendChild(row('status', b.status, b.status === 'ready_for_orders' ? 'good' : 'warn'));
      const creds = b.credentials || {};
      body.appendChild(row('credentials ready', creds.ready ? 'YES' : 'no', creds.ready ? 'good' : 'warn'));
      (creds.missing || []).forEach(m => body.appendChild(row('missing', m, 'warn')));
    }));

    // Comms scaffold
    container.appendChild(section('Comms — Telegram / SMS / Email', (body) => {
      const c = data.comms || {};
      const ch = c.channels || {};
      Object.entries(ch).forEach(([name, val]) => {
        body.appendChild(row(name, val.configured ? 'configured ✓' : 'not configured',
          val.configured ? 'good' : 'warn'));
      });
      body.appendChild(row('any outbound enabled', c.any_outbound_enabled ? 'YES' : 'no'));
    }, {collapsedByDefault: true}));

    // Audit
    container.appendChild(section('Self-audit', (body) => {
      const a = data.audit || {};
      body.appendChild(row('findings', a.finding_count));
      body.appendChild(row('by_severity', JSON.stringify(a.by_severity || {})));
      (a.findings || []).forEach(f => {
        const cls = f.severity === 'RED' ? 'bad' : (f.severity === 'AMBER' ? 'warn' : '');
        body.appendChild(row(f.severity + ' ' + f.code, f.description, cls));
      });
    }, {collapsedByDefault: true}));

    // Research queue
    container.appendChild(section('Research queue', (body) => {
      const r = data.research_queue || {};
      body.appendChild(row('items', r.item_count));
      body.appendChild(row('by_status', JSON.stringify(r.by_status || {})));
      (r.items || []).slice(-3).forEach(item => {
        body.appendChild(row(item.requested_by, item.question?.slice(0, 70) + '...'));
      });
    }, {collapsedByDefault: true}));

    // Free image catalog
    container.appendChild(section('Free image catalog', (body) => {
      const f = data.free_image_catalog || {};
      body.appendChild(row('sources', f.source_count));
      body.appendChild(row('drafts (full synth)', f.draft_count));
      body.appendChild(row('proj. revenue', fmt(f.proj_monthly_revenue, ' $/mo')));
      body.appendChild(row('proj. profit', fmt(f.proj_monthly_profit, ' $/mo')));
    }, {collapsedByDefault: true}));

    // Reward engine
    container.appendChild(section('Reward grants', (body) => {
      const r = data.reward_engine || {};
      body.appendChild(row('grants', r.grant_count));
      body.appendChild(row('by_status', JSON.stringify(r.by_status || {})));
      (r.grants || []).slice(0, 3).forEach(g => {
        body.appendChild(row(g.grant_id, g.kind + ' • ' + g.candidate_worker_id));
      });
    }, {collapsedByDefault: true}));

    // Last tick
    const t = data.last_tick || {};
    const meta = el('div', 'v6-meta',
      `last tick: ${t.tick_id || '—'}  ·  ${t.duration_seconds || '—'}s  ·  ` +
      `${t.conclusions || 0} conclusions, ${t.reflections || 0} reflections`);
    container.appendChild(meta);

    return container;
  }

  function createBanner() {
    let b = document.getElementById('qsb_v6_banner');
    if (b) return b;
    b = el('div');
    b.id = 'qsb_v6_banner';
    b.textContent = '★ V6 COGNITIVE PANEL ACTIVE — see the orange-bordered panel on the right →';
    b.addEventListener('click', () => {
      const p = document.getElementById('qsb_v6_panel');
      if (p) {
        p.scrollTop = 0;
        p.style.borderColor = '#ff4444';
        setTimeout(() => { p.style.borderColor = '#ffd05d'; }, 800);
      }
    });
    document.body.appendChild(b);
    return b;
  }

  function createPanel() {
    createBanner();
    let panel = document.getElementById('qsb_v6_panel');
    if (panel) return panel;
    panel = el('div');
    panel.id = 'qsb_v6_panel';
    const title = el('h2', null, 'Cognitive · V6');
    title.appendChild(el('span', 'v6-pill', 'LIVE'));
    panel.appendChild(title);
    const toggle = el('button', 'v6-toggle', '–');
    toggle.title = 'Collapse';
    toggle.addEventListener('click', () => {
      panel.classList.toggle('collapsed');
      toggle.textContent = panel.classList.contains('collapsed') ? '+' : '–';
    });
    panel.appendChild(toggle);
    const body = el('div'); body.id = 'qsb_v6_body';
    panel.appendChild(body);
    document.body.appendChild(panel);
    return panel;
  }

  async function refresh() {
    try {
      const res = await fetch(ENDPOINT, {cache: 'no-store'});
      const data = await res.json();
      const panel = createPanel();
      const body = document.getElementById('qsb_v6_body');
      if (body) {
        body.innerHTML = '';
        body.appendChild(panelHTML(data));
      }
    } catch (err) {
      const panel = createPanel();
      const body = document.getElementById('qsb_v6_body');
      if (body) {
        body.innerHTML = '';
        const w = el('div', 'v6-warning', 'cognitive unified fetch failed: ' + err.message);
        body.appendChild(w);
      }
    }
  }

  function start() {
    refresh();
    setInterval(refresh, REFRESH_MS);
  }

  if (document.readyState === 'loading') {
    document.addEventListener('DOMContentLoaded', start);
  } else {
    start();
  }
})();
