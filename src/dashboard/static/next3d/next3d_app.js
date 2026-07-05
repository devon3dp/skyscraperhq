/*
 * QSB Next3D — App Orchestrator
 * Phase: QSB_NEXTGEN_3D_DASHBOARD_GREENFIELD_REBUILD_V1
 *
 * Boots the scene, fetches telemetry, drives subsystem updates,
 * wires header buttons, and shows the interior panel when a floor is
 * selected.
 */
(function () {
  'use strict';

  const POLL_MS = 4000;
  let scene = null;
  let interior = null;
  let hud = null;
  let lastState = null;
  let labelsOn = false;

  function showError(msg) {
    const err = document.getElementById('next3d-webgl-unavailable');
    if (err) {
      err.hidden = false;
      err.textContent = msg;
    }
  }

  async function boot() {
    const canvas = document.getElementById('n3dCanvas');
    if (!canvas) { showError('Canvas not found'); return; }

    // First telemetry fetch so the tower can be built with worker counts
    const t0 = await window.NEXT3D_TELEMETRY.fetchAll();
    lastState = t0;
    scene = window.NEXT3D_SCENE.build(canvas, t0.floors);
    if (!scene.ready) {
      showError(scene.error === 'webgl_unavailable'
        ? 'WebGL is not available. Enable hardware acceleration in your browser.'
        : 'Babylon.js not loaded.');
      return;
    }
    interior = window.NEXT3D_INTERIORS.build();
    hud = window.NEXT3D_HUD.build();

    wireHeader();
    applyTelemetry(t0);

    setInterval(function () { pollAndApply(); }, POLL_MS);
  }

  function wireHeader() {
    const focus = document.getElementById('n3dBtnFocus');
    if (focus) focus.addEventListener('click', function () {
      const sel = scene.floors.currentSelection();
      if (sel === null) return;
      scene.camera.focusOnFloor(scene.tower.geometry.floorYCenter(sel));
    });
    const reset = document.getElementById('n3dBtnReset');
    if (reset) reset.addEventListener('click', function () {
      scene.camera.resetView();
    });
    const labels = document.getElementById('n3dBtnLabels');
    if (labels) labels.addEventListener('click', function () {
      labelsOn = !labelsOn;
      labels.style.background = labelsOn ? 'rgba(80,140,220,0.8)' : '';
    });
  }

  async function pollAndApply() {
    const t = await window.NEXT3D_TELEMETRY.fetchAll();
    lastState = t;
    applyTelemetry(t);
  }

  function applyTelemetry(state) {
    if (!scene || !scene.ready) return;
    // 1) Lifts
    scene.lifts.applyLifts(state.lifts || []);
    // 2) Workers density glow
    if (state.workers && state.workers.per_floor) {
      scene.workers.applyDensityGlow(state.workers.per_floor);
    }
    // 3) OpenClaw
    scene.openclaw.apply(state.openclaw);
    // 4) Roster
    scene.floors.renderRoster(state.floors);
    // 5) Selected floor → interior + worker dots
    const sel = scene.floors.currentSelection();
    if (sel !== null) {
      const density = state.workers && state.workers.per_floor &&
        state.workers.per_floor.find(function (r) { return r.floor === sel; });
      scene.workers.setSelectedFloor(sel, density);
      interior.show(sel, state);
    } else {
      scene.workers.setSelectedFloor(null);
      interior.show(null, state);
    }
    // 6) HUD pills + footer
    hud.update(state, 'babylon');
  }

  function onSelectionChanged(num) {
    if (!lastState) return;
    if (num !== null) {
      const density = lastState.workers && lastState.workers.per_floor &&
        lastState.workers.per_floor.find(function (r) { return r.floor === num; });
      scene.workers.setSelectedFloor(num, density);
      interior.show(num, lastState);
    } else {
      scene.workers.setSelectedFloor(null);
      interior.show(null, lastState);
    }
    if (lastState && lastState.floors) {
      scene.floors.renderRoster(lastState.floors);
    }
  }

  function selectFloor(num) {
    if (scene && scene.floors) scene.floors.select(num);
  }

  window.NEXT3D_APP = {
    boot: boot,
    onSelectionChanged: onSelectionChanged,
    selectFloor: selectFloor,
    state: function () { return lastState; },
  };

  if (document.readyState === 'loading') {
    document.addEventListener('DOMContentLoaded', boot);
  } else { boot(); }
})();
