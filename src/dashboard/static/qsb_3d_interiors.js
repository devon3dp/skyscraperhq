/*
 * QSB 3D Revamp — Floor Interior coordinator (thin)
 * Phase: QSB_DASHBOARD_3D_TOTAL_REVAMP_WORKERS_OPENCLAW_V1
 *
 * Light coordinator that bridges floor pick events and the panel
 * renderer in qsb_3d_workers.js. Keeps qsb_3d_workers focused on
 * rendering and this module focused on event wiring.
 */
(function () {
  'use strict';
  if (window.QSB_3D_INTERIORS_INSTALLED) return;
  window.QSB_3D_INTERIORS_INSTALLED = true;

  function onFloorPick(meta) {
    if (!meta || meta.kind !== 'floor') return;
    if (window.QSB_3D_WORKERS && window.QSB_3D_WORKERS.onFloorPick) {
      window.QSB_3D_WORKERS.onFloorPick(meta.number);
    }
  }

  function attach() {
    window.addEventListener('qsb:pick', function (e) { onFloorPick(e && e.detail); });
  }

  if (document.readyState === 'loading') {
    document.addEventListener('DOMContentLoaded', attach);
  } else {
    attach();
  }
  window.QSB_3D_INTERIORS = {};
})();
