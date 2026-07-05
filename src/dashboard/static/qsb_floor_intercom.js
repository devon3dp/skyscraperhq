/*
 * QSB Floor Intercom — visible inter-floor packet bus 41/42/43
 * Phase: QSB_FLOOR_41_42_43_INTERCOM_AND_FLOOR_43_VISIBLE_V1
 *
 * When any of 41/42/43 is selected, paints a small "intercom strip" at
 * the bottom of the stage showing the most recent sealed packets that
 * involve the selected floor (sent or received). Each packet shows:
 *   src → dst via <lift>, kind, summary, ts
 *
 * Per CLAUDE.md: floors do not talk directly — every packet shown here
 * was routed via a lift. This panel is read-only.
 */
(function () {
  'use strict';
  if (window.QSB_FLOOR_INTERCOM_INSTALLED) return;
  window.QSB_FLOOR_INTERCOM_INSTALLED = true;

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

  function ensureStrip() {
    let el = document.getElementById('qsbIntercomStrip');
    if (el) return el;
    const stage = document.getElementById('stage') || document.body;
    el = document.createElement('div');
    el.id = 'qsbIntercomStrip';
    el.className = 'qsb-intercom-strip';
    el.style.display = 'none';
    stage.appendChild(el);
    return el;
  }

  function floorKey(n) {
    if (n === 41) return 'floor_41';
    if (n === 42) return 'floor_42';
    if (n === 43) return 'floor_43';
    if (n === 31) return 'floor_31';
    return null;
  }

  async function render() {
    const el = ensureStrip();
    const sel = window.QSB && window.QSB.selectedFloor;
    if (sel !== 41 && sel !== 42 && sel !== 43) {
      el.style.display = 'none';
      return;
    }
    el.style.display = 'block';
    const data = await fetchJSON('/api/dashboard/intercom_packets');
    if (!data || !data.packets) {
      el.innerHTML = '<div class="ic-hdr">INTERCOM BUS — no packets (run python3 -m tower.qsb_floor_intercom_bus)</div>';
      return;
    }
    const key = floorKey(sel);
    const relevant = data.packets.filter(function (p) {
      return p.from_floor === key || p.to_floor === key;
    }).slice(-10);
    const sent = relevant.filter(function (p) { return p.from_floor === key; }).length;
    const recv = relevant.filter(function (p) { return p.to_floor === key; }).length;
    let rows = '';
    relevant.forEach(function (p) {
      const isSend = p.from_floor === key;
      const arrow = isSend ? '→' : '←';
      const other = isSend ? p.to_floor : p.from_floor;
      const ts = (p.ts || '').slice(11, 19);
      rows += (
        '<div class="ic-pkt ' + (isSend ? 'send' : 'recv') + '">' +
          '<span class="ic-arrow">' + arrow + '</span>' +
          '<span class="ic-other">' + esc(other.replace('floor_', 'F')) + '</span>' +
          '<span class="ic-lift">via ' + esc(p.lift) + '</span>' +
          '<span class="ic-kind">' + esc(p.kind) + '</span>' +
          '<span class="ic-summary">' + esc(((p.body || {}).summary || '').slice(0, 70)) + '</span>' +
          '<span class="ic-ts">' + esc(ts) + '</span>' +
        '</div>'
      );
    });
    el.innerHTML = (
      '<div class="ic-hdr">INTERCOM BUS · F' + sel + ' · sent ' + sent + ' / recv ' + recv +
        ' · sealed packets via lifts only (no direct floor-to-floor channel)' +
      '</div>' +
      rows
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
  window.QSB_FLOOR_INTERCOM = { render: render };
})();
