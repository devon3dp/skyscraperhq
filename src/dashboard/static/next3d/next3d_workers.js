/*
 * QSB Next3D — Worker Density Glow + Selected-Floor Worker Sprites
 * Phase: QSB_NEXTGEN_3D_DASHBOARD_GREENFIELD_REBUILD_V1
 *
 * Zoomed-out: floor emissive gets a small green boost proportional to
 * the operational worker count (no individual labels — would be 1191).
 *
 * Selected floor: a small ring of glowing dots above the slab,
 * count-capped at 18, representing classes by color. Never random.
 */
(function () {
  'use strict';

  function build(scene, BJS, towerMeshes, towerGeo) {
    const yc = towerGeo.floorYCenter;
    let selectedFloor = null;
    let selectedDots = [];

    function applyDensityGlow(perFloor) {
      perFloor.forEach(function (rec) {
        const mesh = towerMeshes[rec.floor];
        if (!mesh || !mesh.material) return;
        const m = mesh.material;
        const cur = m.emissiveColor || new BJS.Color3(0.1, 0.1, 0.1);
        const ops = (rec.classes && rec.classes.operational_worker) || 0;
        const boost = Math.min(0.16, ops / 1100);
        const tint = Math.min(0.12, ops / 1500);
        m.emissiveColor = new BJS.Color3(
          Math.min(1.0, cur.r + boost * 0.1),
          Math.min(1.0, cur.g + boost + tint),
          Math.min(1.0, cur.b + boost * 0.5));
      });
    }

    function clearSelected() {
      selectedDots.forEach(function (d) { try { d.dispose(); } catch (_) {} });
      selectedDots = [];
    }

    function classColor(cls) {
      switch (cls) {
        case 'operational_worker': return [0.40, 0.85, 1.00];
        case 'training_worker':    return [1.00, 0.78, 0.40];
        case 'candidate_worker':   return [0.55, 1.00, 0.75];
        case 'lesson_worker':      return [1.00, 0.65, 0.45];
        case 'resting_worker':     return [0.65, 0.65, 0.85];
        case 'sim_worker':         return [0.85, 0.55, 1.00];
        default:                   return [0.70, 0.80, 0.95];
      }
    }

    function setSelectedFloor(floorNum, density) {
      clearSelected();
      selectedFloor = floorNum;
      if (floorNum === null || floorNum === undefined) return;
      const yBase = yc(floorNum);
      const classes = (density && density.classes) || {};
      const total = (density && density.total) || 0;
      if (total === 0) return;
      // Build up to 18 glowing dots arranged in a ring above the slab.
      // One dot per ~max(1, total/18) workers. Class-coloured.
      const dotCount = Math.min(18, Math.max(3, Math.ceil(total / 18)));
      const radius = 7.2;
      let idx = 0;
      const classPool = [];
      Object.keys(classes).forEach(function (cls) {
        const n = Math.max(1, Math.round((classes[cls] / total) * dotCount));
        for (let i = 0; i < n; i++) classPool.push(cls);
      });
      while (classPool.length < dotCount) classPool.push('operational_worker');
      for (let i = 0; i < dotCount; i++) {
        const angle = (i / dotCount) * Math.PI * 2;
        const x = Math.cos(angle) * radius;
        const z = Math.sin(angle) * radius;
        const dot = BJS.MeshBuilder.CreateSphere('n3dWkrDot_' + floorNum + '_' + i,
          { diameter: 0.32, segments: 10 }, scene);
        dot.position.x = x;
        dot.position.z = z;
        dot.position.y = yBase + 0.9;
        const cls = classPool[i % classPool.length];
        const c = classColor(cls);
        const m = new BJS.StandardMaterial('wkrDotMat_' + i, scene);
        m.diffuseColor = new BJS.Color3(c[0] * 0.4, c[1] * 0.4, c[2] * 0.4);
        m.emissiveColor = new BJS.Color3(c[0], c[1], c[2]);
        m.specularColor = new BJS.Color3(0.9, 0.9, 0.95);
        dot.material = m;
        dot.metadata = { kind: 'worker_dot', floor: floorNum, cls: cls };
        dot.isPickable = false;
        selectedDots.push(dot);
      }
    }

    function tick(t) {
      // Soft rotation of the worker ring so it reads as "active"
      const w = 0.4;
      for (let i = 0; i < selectedDots.length; i++) {
        const d = selectedDots[i];
        const angle = (i / selectedDots.length) * Math.PI * 2 + t * w * 0.0005;
        const radius = 7.2;
        d.position.x = Math.cos(angle) * radius;
        d.position.z = Math.sin(angle) * radius;
      }
    }

    return {
      applyDensityGlow: applyDensityGlow,
      setSelectedFloor: setSelectedFloor,
      tick: tick,
    };
  }

  window.NEXT3D_WORKERS = { build: build };
})();
