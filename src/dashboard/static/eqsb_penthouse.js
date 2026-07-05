/* EQSB Penthouse Panel — Major Phase
 * Phase: EQSB_KERNEL_MAJOR_DEEP_SYMBOLIC_QUANTUM_CORE_V1
 * Read-only. Reads /api/eqsb/penthouse_panel and renders the deep-kernel
 * sections. Never enables execution. The Tick button calls
 * /api/eqsb/cadence_tick which is registry maintenance only.
 */
(function () {
  'use strict';

  function esc(s) {
    if (s === null || s === undefined) return '—';
    return String(s)
      .replace(/&/g, '&amp;').replace(/</g, '&lt;').replace(/>/g, '&gt;');
  }
  function pct(v) {
    if (v === null || v === undefined || isNaN(Number(v))) return '—';
    return Number(v).toFixed(1);
  }
  function bool(v) {
    if (v === true)  return '<span class="ok">false</span>'.replace('false', 'TRUE');
    if (v === false) return '<span class="warn">FALSE</span>';
    return '—';
  }
  // Meter bar 0..100
  function meter(label, v, cls) {
    const n = Math.max(0, Math.min(100, Number(v) || 0));
    return (
      '<div class="eqsb-meter">' +
        '<div class="eqsb-meter-label">' + esc(label) + ': <b>' + pct(n) + '</b></div>' +
        '<div class="eqsb-meter-bar"><div class="eqsb-meter-fill ' + (cls || '') + '" style="width:' + n + '%"></div></div>' +
      '</div>'
    );
  }

  function renderSelfAudit(d) {
    const sa = d.self_audit || {};
    const cls = (sa.verdict === 'kernel_healthy') ? 'ok'
              : (sa.verdict === 'kernel_blocked') ? 'err'
              : 'warn';
    return (
      '<div class="eqsb-section">' +
        '<h4>Kernel Self-Audit</h4>' +
        '<div class="eqsb-kv"><span>Verdict</span><span class="' + cls + '">' + esc(sa.verdict) + '</span></div>' +
        '<div class="eqsb-kv"><span>Reasons</span><span>' + esc((sa.verdict_reasons || []).join('; ')) + '</span></div>' +
        '<div class="eqsb-kv"><span>Missing registries</span><span>' + esc(sa.missing_registry_count) + '</span></div>' +
      '</div>'
    );
  }

  function renderIdentity(d) {
    const id = d.identity || {};
    return (
      '<div class="eqsb-section">' +
        '<h4>Kernel Identity</h4>' +
        '<div class="eqsb-kv"><span>Name</span><span>' + esc(id.name) + '</span></div>' +
        '<div class="eqsb-kv"><span>Role</span><span>' + esc(id.role) + '</span></div>' +
        '<div class="eqsb-kv"><span>Mode</span><span>' + esc(id.mode) + '</span></div>' +
        '<div class="eqsb-kv"><span>Active source</span><span>' + esc(id.active_source) + '</span></div>' +
        '<div class="eqsb-quote">' + esc(id.identity_statement) + '</div>' +
      '</div>'
    );
  }

  function renderAxioms(d) {
    return (
      '<div class="eqsb-section">' +
        '<h4>Constitution / Axiom Chamber</h4>' +
        '<div class="eqsb-kv"><span>Axiom count</span><span>' + esc(d.axiom_count) + '</span></div>' +
        '<div class="eqsb-kv"><span>Categories</span><span>' + esc((d.axiom_categories || []).join(', ')) + '</span></div>' +
      '</div>'
    );
  }

  function renderGuardian(d) {
    const g = d.guardian || {};
    const cls = g.safety_state === 'OK' ? 'ok'
              : g.safety_state === 'BLOCKED' ? 'err'
              : 'warn';
    return (
      '<div class="eqsb-section">' +
        '<h4>Guardian Core</h4>' +
        '<div class="eqsb-kv"><span>Safety state</span><span class="' + cls + '">' + esc(g.safety_state) + '</span></div>' +
        '<div class="eqsb-kv"><span>Default verdict</span><span>' + esc(g.default_verdict) + '</span></div>' +
        '<details><summary>Blocked reasons</summary><pre>' + esc(JSON.stringify(g.blocked_reasons || {}, null, 2)) + '</pre></details>' +
      '</div>'
    );
  }

  function renderCadence(d) {
    const c = d.cadence || {};
    return (
      '<div class="eqsb-section">' +
        '<h4>Cadence / Heartbeat</h4>' +
        '<div class="eqsb-kv"><span>Tick count</span><span>' + esc(c.tick_count) + '</span></div>' +
        '<div class="eqsb-kv"><span>Loop completeness</span><span>' + pct(c.loop_completeness_pct) + '%</span></div>' +
        '<div class="eqsb-kv"><span>Last tick</span><span>' + esc(c.last_tick_ts) + '</span></div>' +
      '</div>'
    );
  }

  function renderMemory(d) {
    const m = d.memory || {};
    const postureCls = m.boot_posture === 'NORMAL' ? 'ok'
                       : m.boot_posture === 'DRIFT_ALERT' ? 'err' : 'warn';
    return (
      '<div class="eqsb-section">' +
        '<h4>Memory / Continuity Chamber</h4>' +
        '<div class="eqsb-kv"><span>Boot posture</span><span class="' + postureCls + '">' + esc(m.boot_posture) + '</span></div>' +
        '<div class="eqsb-kv"><span>History count</span><span>' + esc(m.history_count) + '</span></div>' +
        '<div class="eqsb-kv"><span>Drift alerts</span><span>' + esc(m.drift_alert_count) + '</span></div>' +
        '<div class="eqsb-kv"><span>Stale memory flags</span><span>' + esc(m.stale_memory_flag_count) + '</span></div>' +
      '</div>'
    );
  }

  function renderBeliefs(d) {
    const b = d.beliefs || {};
    const sc = b.state_counts || {};
    const rows = Object.keys(sc).map(function (k) {
      return '<div class="eqsb-kv"><span>' + esc(k) + '</span><span>' + esc(sc[k]) + '</span></div>';
    }).join('');
    return (
      '<div class="eqsb-section">' +
        '<h4>Belief Lifecycle Engine</h4>' +
        '<div class="eqsb-kv"><span>Belief count</span><span>' + esc(b.belief_count) + '</span></div>' +
        rows +
      '</div>'
    );
  }

  function renderSymbolicGraph(d) {
    const g = d.symbolic_graph || {};
    return (
      '<div class="eqsb-section">' +
        '<h4>Symbolic Graph</h4>' +
        '<div class="eqsb-kv"><span>Nodes</span><span>' + esc(g.node_count) + '</span></div>' +
        '<div class="eqsb-kv"><span>Edges</span><span>' + esc(g.edge_count) + '</span></div>' +
        '<div class="eqsb-kv"><span>Orphan symbols</span><span>' + esc(g.orphan_symbols) + '</span></div>' +
        '<div class="eqsb-kv"><span>Contradicted beliefs</span><span>' + esc(g.contradicted_beliefs) + '</span></div>' +
      '</div>'
    );
  }

  function renderEntropy(d) {
    const e = d.entropy || {};
    return (
      '<div class="eqsb-section">' +
        '<h4>Entropy Core</h4>' +
        meter('Entropy',       e.entropy_score,       'm-entropy') +
        meter('Stability',     e.stability_score,     'm-ok') +
        meter('Drift',         e.drift_score,         'm-drift') +
        meter('Confidence',    e.confidence_score,    'm-ok') +
        meter('Contradiction', e.contradiction_score, 'm-err') +
        meter('Urgency',       e.urgency_score,       'm-warn') +
      '</div>'
    );
  }

  function renderQuantum(d) {
    const q = d.quantum_signal || {};
    return (
      '<div class="eqsb-section">' +
        '<h4>Quantum Signal Well</h4>' +
        '<div class="eqsb-kv"><span>Mode</span><span><code>' + esc(q.mode) + '</code></span></div>' +
        '<div class="eqsb-kv"><span>Real quantum connected</span><span>' + bool(q.real_quantum_source_connected) + '</span></div>' +
        '<div class="eqsb-kv"><span>Qiskit connected</span><span>' + bool(q.qiskit_connected) + '</span></div>' +
        '<div class="eqsb-kv"><span>IBM Quantum connected</span><span>' + bool(q.ibm_quantum_connected) + '</span></div>' +
        '<div class="eqsb-kv"><span>Quantum hardware active</span><span>' + bool(q.quantum_hardware_active) + '</span></div>' +
        '<div class="eqsb-kv"><span>Uncertainty</span><span>' + esc(q.uncertainty_score) + '</span></div>' +
        '<div class="eqsb-kv"><span>Selected hypothesis</span><span>' + esc(q.selected_hypothesis_id) + '</span></div>' +
        '<div class="eqsb-kv"><span>Collapse reason</span><span class="eqsb-small">' + esc(q.collapse_reason) + '</span></div>' +
      '</div>'
    );
  }

  function renderHypotheses(d) {
    const h = d.hypotheses || {};
    return (
      '<div class="eqsb-section">' +
        '<h4>Hypothesis Chamber</h4>' +
        '<div class="eqsb-kv"><span>Hypotheses</span><span>' + esc(h.count) + '</span></div>' +
        '<div class="eqsb-kv"><span>Selected</span><span>' + esc(h.selected_hypothesis_id) + '</span></div>' +
        '<div class="eqsb-kv"><span>By severity</span><span>' + esc(JSON.stringify(h.by_severity || {})) + '</span></div>' +
      '</div>'
    );
  }

  function renderContradictions(d) {
    const c = d.contradictions || {};
    const cls = (c.count > 0) ? 'warn' : 'ok';
    return (
      '<div class="eqsb-section">' +
        '<h4>Contradiction Monitor</h4>' +
        '<div class="eqsb-kv"><span>Count</span><span class="' + cls + '">' + esc(c.count) + '</span></div>' +
        '<div class="eqsb-kv"><span>By severity</span><span>' + esc(JSON.stringify(c.by_severity || {})) + '</span></div>' +
      '</div>'
    );
  }

  function renderModelGovernance(d) {
    const g = d.model_governance || {};
    const rows = (g.lanes || []).map(function (l) {
      return '<div class="eqsb-kv"><span>' + esc(l.lane_id) + '</span><span class="eqsb-small">' + esc(l.role) + ' · exec=' + bool(l.execution_allowed) + '</span></div>';
    }).join('');
    return (
      '<div class="eqsb-section">' +
        '<h4>Model Lane Governance</h4>' +
        '<div class="eqsb-kv"><span>Lane count</span><span>' + esc(g.lane_count) + '</span></div>' +
        rows +
      '</div>'
    );
  }

  function renderReplay(d) {
    const r = d.replay_ledger || {};
    return (
      '<div class="eqsb-section">' +
        '<h4>Replay / Audit Ledger</h4>' +
        '<div class="eqsb-kv"><span>Event count</span><span>' + esc(r.event_count_total) + '</span></div>' +
        '<details><summary>Events by kind</summary><pre>' + esc(JSON.stringify(r.events_by_kind || {}, null, 2)) + '</pre></details>' +
      '</div>'
    );
  }

  function renderArchitecture(d) {
    const a = d.architecture || {};
    const names = (a.layer_names || []).map(function (n) { return '<li>' + esc(n) + '</li>'; }).join('');
    return (
      '<div class="eqsb-section">' +
        '<h4>Architecture Layers</h4>' +
        '<div class="eqsb-kv"><span>Phase</span><span class="eqsb-small">' + esc(a.phase) + '</span></div>' +
        '<div class="eqsb-kv"><span>Layer count</span><span>' + esc(a.layer_count) + '</span></div>' +
        '<details><summary>Layers</summary><ol>' + names + '</ol></details>' +
      '</div>'
    );
  }

  function renderPenthouse(d) {
    const noteCls = d.execution_allowed === false ? 'ok' : 'err';
    const head = (
      '<div class="eqsb-head">' +
        '<div class="eqsb-quote eqsb-note ' + noteCls + '">' +
          'EQSB is the persistent symbolic kernel. Models paraphrase; ' +
          'registries are truth. execution_allowed=<b>' + esc(d.execution_allowed) + '</b>, ' +
          'active_local_only=<b>' + esc(d.active_local_only) + '</b>.' +
        '</div>' +
      '</div>'
    );
    return head +
      renderSelfAudit(d) +
      renderIdentity(d) +
      renderAxioms(d) +
      renderGuardian(d) +
      renderCadence(d) +
      renderMemory(d) +
      renderBeliefs(d) +
      renderSymbolicGraph(d) +
      renderEntropy(d) +
      renderQuantum(d) +
      renderHypotheses(d) +
      renderContradictions(d) +
      renderModelGovernance(d) +
      renderReplay(d) +
      renderArchitecture(d);
  }

  async function fetchPanel() {
    try {
      const r = await fetch('/api/eqsb/penthouse_panel?t=' + Date.now(), { cache: 'no-store' });
      return await r.json();
    } catch (e) {
      return { ok: false, error: String(e) };
    }
  }

  async function refresh() {
    const body = document.getElementById('eqsbBody');
    if (!body) return;
    const sub = document.getElementById('eqsbSub');
    body.innerHTML = '<div class="tagline">EQSB panel — loading…</div>';
    let d = null;
    try { d = await fetchPanel(); } catch (_) {}
    if (!d || d.ok === false) {
      body.innerHTML = '<div class="tagline err">EQSB panel unavailable: ' + esc((d && d.error) || 'unknown') + '</div>';
      if (sub) sub.textContent = 'unavailable';
      return;
    }
    try { body.innerHTML = renderPenthouse(d); }
    catch (_) { body.innerHTML = '<div class="tagline err">EQSB panel render failed — backend returned malformed data.</div>'; }
    if (sub) {
      const sa = d.self_audit || {};
      sub.textContent = (sa.verdict || 'deep kernel') + ' · ' + (d.execution_allowed === false ? 'locked' : '?');
    }
  }

  async function tick() {
    try {
      await fetch('/api/eqsb/cadence_tick', { method: 'POST' });
    } catch (e) { /* ignore */ }
    refresh();
  }

  function attach() {
    const btn = document.getElementById('eqsbRefreshBtn');
    if (btn) btn.addEventListener('click', refresh);
    const tickBtn = document.getElementById('eqsbTickBtn');
    if (tickBtn) tickBtn.addEventListener('click', tick);
    // Refresh whenever the EQSB tab is shown.
    document.querySelectorAll('#rightTabs button').forEach(function (b) {
      if (b.getAttribute('data-tab') === 'eqsb') {
        b.addEventListener('click', refresh);
      }
    });
    // First load if the tab is already active.
    setTimeout(refresh, 600);
    // Polite background refresh every 30s.
    setInterval(refresh, 30000);
  }

  function safeAttach() {
    try { attach(); } catch (e) {
      if (window && window.console) console.warn('[eqsb_penthouse] attach failed:', e && e.message);
    }
  }

  if (document.readyState === 'loading') {
    document.addEventListener('DOMContentLoaded', safeAttach);
  } else {
    safeAttach();
  }
})();
