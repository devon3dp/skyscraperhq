/*
 * QSB Next3D — Floor selection + roster
 * Phase: QSB_NEXTGEN_3D_DASHBOARD_GREENFIELD_REBUILD_V1
 *
 * Owns:
 *   - the left-side roster of named floors
 *   - the selected-floor highlight (yellow torus around the slab)
 *   - the camera focus on selection
 *   - URL ?floor=N parsing on boot
 */
(function () {
  'use strict';

  function build(scene, BJS, camera, towerMeshes, towerGeo, onChange) {
    const yc = towerGeo.floorYCenter;

    // Build halo ring
    const halo = BJS.MeshBuilder.CreateTorus('n3dSelHalo',
      { diameter: towerGeo.FLOOR_W * 1.50, thickness: 0.12, tessellation: 64 },
      scene);
    halo.rotation.x = Math.PI / 2;
    const hm = new BJS.StandardMaterial('selHaloMat', scene);
    hm.diffuseColor = new BJS.Color3(0.5, 0.45, 0.10);
    hm.emissiveColor = new BJS.Color3(1.0, 0.85, 0.30);
    hm.alpha = 0.75;
    halo.material = hm;
    halo.setEnabled(false);
    halo.isPickable = false;

    let selected = null;

    function urlFloor() {
      try {
        const u = new URLSearchParams(window.location.search);
        const v = parseInt(u.get('floor'), 10);
        if (isNaN(v) || v < 0 || v > 55) return null;
        return v;
      } catch (_) { return null; }
    }

    function select(num) {
      selected = (num === null || num === undefined) ? null : Number(num);
      if (selected === null) {
        halo.setEnabled(false);
      } else {
        halo.setEnabled(true);
        halo.position.y = yc(selected);
        camera.focusOnFloor(yc(selected));
        // Brighten the selected slab briefly
        const m = towerMeshes[selected] && towerMeshes[selected].material;
        if (m && m.emissiveColor) {
          m.emissiveColor = new BJS.Color3(
            Math.min(1.0, m.emissiveColor.r + 0.18),
            Math.min(1.0, m.emissiveColor.g + 0.10),
            Math.min(1.0, m.emissiveColor.b + 0.05));
        }
      }
      try {
        const params = new URLSearchParams(window.location.search);
        if (selected === null) params.delete('floor');
        else params.set('floor', String(selected));
        const newQS = params.toString();
        const url = window.location.pathname + (newQS ? '?' + newQS : '');
        window.history.replaceState(null, '', url);
      } catch (_) {}
      if (typeof onChange === 'function') onChange(selected);
    }

    // Wire SVG-style roster on the left
    function renderRoster(floors) {
      const el = document.getElementById('n3dFloorRoster');
      if (!el) return;
      let html = '<div class="n3d-roster-hdr">Floors · click to select</div>';
      // Show floors sorted descending
      const sorted = floors.slice().sort(function (a, b) { return b.num - a.num; });
      sorted.forEach(function (f) {
        const cls = 'n3d-roster-row' + (f.special ? ' special' : '') +
                    (selected === f.num ? ' selected' : '');
        const ops = (f.classes && f.classes.operational_worker) || 0;
        html += (
          '<div class="' + cls + '" data-floor="' + f.num + '">' +
            '<span class="n3d-roster-num">F' + f.num + '</span>' +
            '<span class="n3d-roster-name">' + escapeHtml(f.name) + '</span>' +
            '<span class="n3d-roster-density">' + (f.worker_total || 0) + 'w</span>' +
          '</div>'
        );
      });
      el.innerHTML = html;
      // Wire clicks
      el.querySelectorAll('.n3d-roster-row').forEach(function (row) {
        row.addEventListener('click', function () {
          const n = parseInt(row.getAttribute('data-floor'), 10);
          select(n);
        });
      });
    }

    function escapeHtml(s) {
      return String(s || '').replace(/&/g, '&amp;').replace(/</g, '&lt;').replace(/>/g, '&gt;');
    }

    // Click pick on tower meshes
    scene.onPointerObservable.add(function (info) {
      if (info.type !== BJS.PointerEventTypes.POINTERPICK) return;
      const pick = info.pickInfo;
      if (!pick || !pick.hit) return;
      const meta = pick.pickedMesh && pick.pickedMesh.metadata;
      if (!meta) return;
      if (meta.kind === 'floor') select(meta.number);
      // worker_dot etc handled elsewhere
    });

    // Initialize from URL
    const urlF = urlFloor();
    if (urlF !== null) setTimeout(function () { select(urlF); }, 250);

    return {
      select: select,
      currentSelection: function () { return selected; },
      renderRoster: renderRoster,
      halo: halo,
    };
  }

  window.NEXT3D_FLOORS = { build: build };
})();
