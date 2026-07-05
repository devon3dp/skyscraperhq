/*
 * QSB Next3D — OpenClaw Supervisor Marker
 * Phase: QSB_NEXTGEN_3D_DASHBOARD_GREENFIELD_REBUILD_V1
 *
 * A purple emissive sphere that floats next to the tower at the height
 * of the floor OpenClaw is currently supervising. Orbits slowly. Never
 * moves randomly — Y is from /api/openclaw/route.current_floor.
 */
(function () {
  'use strict';

  function build(scene, BJS, towerGeo) {
    const yc = towerGeo.floorYCenter;
    const FW = towerGeo.FLOOR_W;

    const orb = BJS.MeshBuilder.CreateSphere('n3dOpenClawOrb',
      { diameter: 1.1, segments: 24 }, scene);
    orb.position.set(FW * 0.85, yc(31), 0);
    const m = new BJS.StandardMaterial('ocOrbMat', scene);
    m.diffuseColor = new BJS.Color3(0.20, 0.06, 0.32);
    m.emissiveColor = new BJS.Color3(0.85, 0.50, 1.0);
    m.specularColor = new BJS.Color3(1.0, 0.7, 1.0);
    orb.material = m;
    orb.isPickable = true;
    orb.metadata = { kind: 'openclaw' };

    // Halo torus
    const halo = BJS.MeshBuilder.CreateTorus('n3dOcHalo',
      { diameter: 2.0, thickness: 0.08, tessellation: 36 }, scene);
    halo.parent = orb;
    const hm = new BJS.StandardMaterial('ocHaloMat', scene);
    hm.diffuseColor = new BJS.Color3(0.5, 0.3, 0.9);
    hm.emissiveColor = new BJS.Color3(0.9, 0.6, 1.0);
    hm.alpha = 0.55;
    halo.material = hm;
    halo.isPickable = false;

    let targetFloor = 31;

    function apply(oc) {
      if (!oc) return;
      const cf = oc.current_floor;
      if (cf !== null && cf !== undefined) targetFloor = Number(cf);
      // Recolour halo by ticket count
      const tc = oc.ticket_count || 0;
      if (tc > 3) {
        hm.emissiveColor = new BJS.Color3(1.0, 0.55, 0.55);
      } else if (tc > 0) {
        hm.emissiveColor = new BJS.Color3(1.0, 0.85, 0.45);
      } else {
        hm.emissiveColor = new BJS.Color3(0.9, 0.6, 1.0);
      }
    }

    function tick(t) {
      // Smoothly approach target Y
      const tgtY = yc(targetFloor) + 0.4;
      const curY = orb.position.y;
      const dy = tgtY - curY;
      if (Math.abs(dy) > 0.01) orb.position.y = curY + dy * 0.05;
      // Slow horizontal orbit
      const theta = t * 0.0004;
      const r = FW * 0.85;
      orb.position.x = Math.cos(theta) * r;
      orb.position.z = Math.sin(theta) * 3.2;
      halo.rotation.y += 0.015;
    }

    return { orb: orb, apply: apply, tick: tick };
  }

  window.NEXT3D_OPENCLAW = { build: build };
})();
