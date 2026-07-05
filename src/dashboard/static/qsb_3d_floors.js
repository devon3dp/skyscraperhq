/*
 * QSB 3D Revamp — Floor Activity Badges + Pulse
 * Phase: QSB_DASHBOARD_3D_TOTAL_REVAMP_WORKERS_OPENCLAW_V1
 *
 * Per-floor activity badge layer painted ON the SVG tower. Each floor
 * shows a compact bar: ops·moving·training, color-coded. The selected
 * floor gets a yellow pulse outline.
 */
(function () {
  'use strict';
  if (window.QSB_3D_FLOORS_INSTALLED) return;
  window.QSB_3D_FLOORS_INSTALLED = true;

  const NS = 'http://www.w3.org/2000/svg';

  function getTower() { return window.QSB_TOWER_2D || null; }

  function ensureLayer() {
    const tower = getTower();
    if (!tower || !tower.svg) return null;
    let layer = tower.svg.querySelector('#qsb3dFloorActivity');
    if (!layer) {
      layer = document.createElementNS(NS, 'g');
      layer.setAttribute('id', 'qsb3dFloorActivity');
      tower.svg.appendChild(layer);
    }
    return layer;
  }

  function parseFloorNum(label) {
    if (label === null || label === undefined) return null;
    const m = /floor[_-]?0*(\d+)/.exec(String(label));
    if (m) return parseInt(m[1], 10);
    return null;
  }

  function update(cache) {
    const tower = getTower();
    if (!tower || !tower.svg || !tower.floorRects) return;
    const layer = ensureLayer();
    if (!layer) return;
    layer.innerHTML = '';
    const scene = cache && cache.scene;
    const byFloor = (scene && scene.by_floor_activity) || {};
    const selFloor = (window.QSB && window.QSB.selectedFloor) || null;

    Object.keys(byFloor).forEach(function (floorKey) {
      const n = parseFloorNum(floorKey);
      if (n === null) return;
      const r = tower.floorRects[n];
      if (!r) return;
      const x = Number(r.getAttribute('x'));
      const y = Number(r.getAttribute('y'));
      const w = Number(r.getAttribute('width'));
      const h = Number(r.getAttribute('height'));
      const a = byFloor[floorKey] || {};
      const ops = a.active || 0;
      const mv  = a.moving || 0;
      const tr  = a.training || 0;
      // Right-edge activity badge: "ops · mv · tr"
      const g = document.createElementNS(NS, 'g');
      g.setAttribute('class', 'qsb-3d-actbadge');
      g.setAttribute('transform', 'translate(' + (x + w + 24) + ',' + (y + h / 2) + ')');
      const bgWidth = 56;
      g.innerHTML = (
        '<rect x="-' + (bgWidth/2) + '" y="-7" width="' + bgWidth + '" height="14" rx="3" ' +
              'fill="rgba(12,20,32,0.78)" stroke="rgba(120,160,200,0.45)" stroke-width="0.6"/>' +
        '<text x="-19" y="3" text-anchor="middle" fill="#a4f3c6">' + ops + '</text>' +
        '<text x="-3"  y="3" text-anchor="middle" fill="#ffe066">' + mv + '</text>' +
        '<text x="13"  y="3" text-anchor="middle" fill="#fbd784">' + tr + '</text>' +
        '<text x="33"  y="3" text-anchor="middle" fill="#9fb6d4" font-size="6">o m t</text>'
      );
      layer.appendChild(g);

      // Selected floor pulse outline
      if (selFloor && selFloor === n) {
        const pulse = document.createElementNS(NS, 'rect');
        pulse.setAttribute('x', x - 3); pulse.setAttribute('y', y - 3);
        pulse.setAttribute('width', w + 6); pulse.setAttribute('height', h + 6);
        pulse.setAttribute('rx', '5');
        pulse.setAttribute('class', 'qsb-3d-floor-pulse');
        layer.appendChild(pulse);
      }
    });
  }

  function onFloorPick(_n) { /* re-render driven by update() on next tick */ }

  window.QSB_3D_FLOORS = { update: update, onFloorPick: onFloorPick };
})();
