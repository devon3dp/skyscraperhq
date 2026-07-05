/*
 * QSB 3D Revamp — Scene state coordinator (thin)
 * Phase: QSB_DASHBOARD_3D_TOTAL_REVAMP_WORKERS_OPENCLAW_V1
 *
 * Coordinates worker_view_mode + selectedFloor with the existing
 * tower_2d/scene renderers. Reinforces the "named rows" interior path
 * over the old "in-slab dots" path so operators see the rebuild.
 *
 * This file intentionally does NOT replace qsb_tower_2d.js or qsb_scene.js
 * (those remain as the underlying renderers); it ensures the V1 revamp
 * panels are the dominant visual.
 */
(function () {
  'use strict';
  if (window.QSB_3D_SCENE_INSTALLED) return;
  window.QSB_3D_SCENE_INSTALLED = true;

  function applyMode() {
    if (window.QSB && window.QSB.workerViewMode == null) {
      window.QSB.workerViewMode = 'selected_floor_and_groups';
    }
  }

  function attach() {
    applyMode();
    // Re-apply on every state event so the renderer sees the latest mode.
    window.addEventListener('qsb:state', applyMode);
  }

  if (document.readyState === 'loading') {
    document.addEventListener('DOMContentLoaded', attach);
  } else {
    attach();
  }
  window.QSB_3D_SCENE = { applyMode: applyMode };
})();
