/*
 * QSB 3D Penthouse — Kernel Command Floor panel
 * Phase: QSB_KERNEL_CHAT_PENTHOUSE_AND_3D_DASHBOARD_REALITY_FIX_V1
 *
 * Renders when floor=55 (or any virtual Penthouse anchor) is selected.
 * Shows 11 zones, ~10 gauges, repair priority board — all source-backed.
 * No decorative particles. Moving elements only react to cadence/event.
 */
(function () {
  'use strict';
  if (window.QSB_3D_PENTHOUSE_INSTALLED) return;
  window.QSB_3D_PENTHOUSE_INSTALLED = true;

  const POLL_MS = 6000;

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
    let el = document.getElementById('qsbPenthousePanel');
    if (el) return el;
    const stage = document.getElementById('stage') || document.body;
    el = document.createElement('div');
    el.id = 'qsbPenthousePanel';
    el.className = 'qsb-penthouse-panel';
    el.style.display = 'none';
    stage.appendChild(el);
    return el;
  }

  function visible() {
    const sel = window.QSB && window.QSB.selectedFloor;
    return sel === 55 || sel === 53 || sel === 54;
  }

  function gaugeCard(g) {
    const cls = 'gauge gauge-' + (g.status || 'ok');
    return (
      '<div class="' + cls + '" title="' + esc(g.source) + '">' +
        '<div class="gauge-label">' + esc(g.label) + '</div>' +
        '<div class="gauge-value">' + esc(g.value) +
          (g.unit ? ' <span class="gauge-unit">' + esc(g.unit) + '</span>' : '') +
        '</div>' +
      '</div>'
    );
  }

  function zoneCard(z) {
    return (
      '<div class="ph-zone">' +
        '<div class="ph-zone-name">' + esc(z.name) + '</div>' +
        '<div class="ph-zone-resp">' + esc(z.responsibility) + '</div>' +
      '</div>'
    );
  }

  function repairCard(r) {
    return (
      '<div class="ph-repair sev-' + esc((r.severity || 'INFO').toLowerCase()) + '">' +
        '<b>[' + esc(r.severity) + ']</b> ' + esc(r.issue) +
        '<div class="ph-repair-fix">fix: ' + esc(r.fix) + '</div>' +
      '</div>'
    );
  }

  async function render() {
    const el = ensurePanel();
    if (!visible()) { el.style.display = 'none'; return; }
    el.style.display = 'block';
    const [cmd, gauges, layout, repair] = await Promise.all([
      fetchJSON('/api/dashboard/penthouse_command_state'),
      fetchJSON('/api/dashboard/penthouse_gauges'),
      fetchJSON('/api/dashboard/penthouse_layout'),
      fetchJSON('/api/dashboard/penthouse_repair_priority'),
    ]);
    if (!cmd) {
      el.innerHTML = '<div class="ph-empty">Penthouse state unavailable. Run python -m tower.qsb_penthouse</div>';
      return;
    }
    const gs = (gauges && gauges.gauges) || [];
    const zs = (layout && layout.zones) || [];
    const rs = (repair && repair.priorities) || [];
    el.innerHTML = (
      '<div class="ph-hdr">' +
        '<div class="ph-hdr-title">PENTHOUSE · KERNEL COMMAND FLOOR</div>' +
        '<div class="ph-hdr-sub">' +
          'cadence ' + esc(cmd.cadence_tick) + ' · ' +
          'guardian ' + esc(cmd.guardian_state) + ' · ' +
          'openclaw f' + esc(cmd.openclaw_current_floor) + ' · ' +
          'locks open ' + esc(cmd.locks_open) + ' / 13' +
        '</div>' +
      '</div>' +
      '<div class="ph-section">' +
        '<h5>Gauges (' + gs.length + ')</h5>' +
        '<div class="ph-gauges">' + gs.map(gaugeCard).join('') + '</div>' +
      '</div>' +
      '<div class="ph-section">' +
        '<h5>Zones (' + zs.length + ')</h5>' +
        '<div class="ph-zones">' + zs.map(zoneCard).join('') + '</div>' +
      '</div>' +
      '<div class="ph-section">' +
        '<h5>Repair Priority Board (' + rs.length + ')</h5>' +
        '<div class="ph-repairs">' + rs.map(repairCard).join('') + '</div>' +
      '</div>' +
      '<div class="ph-section">' +
        '<h5>Decorative elements REMOVED (no fake motion)</h5>' +
        '<div class="ph-removed">' +
          (cmd.decorative_removed || []).map(function (x) {
            return '<span class="ph-removed-tag">' + esc(x) + '</span>';
          }).join('') +
        '</div>' +
        '<div class="ph-tag-line">All moving elements now telemetry-bound: ' +
          (cmd.moving_elements_now_telemetry_bound || []).join(' · ') +
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
  window.QSB_3D_PENTHOUSE = { render: render };
})();
