/*
 * QSB Next3D — Lift Shafts + Cars
 * Phase: QSB_NEXTGEN_3D_DASHBOARD_GREENFIELD_REBUILD_V1
 *
 * 9 vertical shafts running outside the tower envelope so they're
 * obvious. Each shaft has one car that lerps smoothly to its current
 * floor from the live telemetry.
 */
(function () {
  'use strict';

  const NUM_SHAFTS = 9;

  function build(scene, BJS, towerGeo) {
    const FW = towerGeo.FLOOR_W;
    const FD = towerGeo.FLOOR_D;
    const yc = towerGeo.floorYCenter;

    // Position shafts on the back-left + back-right edges so the
    // front of the building stays visible.
    const positions = [
      // x, z relative to tower center
      [-FW/2 - 0.9, -FD/2 - 0.4],
      [-FW/2 - 0.9, -FD/4],
      [-FW/2 - 0.9, +FD/4],
      [-FW/2 - 0.9, +FD/2 + 0.4],
      [+FW/2 + 0.9, -FD/2 - 0.4],
      [+FW/2 + 0.9, -FD/4],
      [+FW/2 + 0.9, +FD/4],
      [+FW/2 + 0.9, +FD/2 + 0.4],
      [0,           -FD/2 - 1.4],   // 9th shaft = service, behind the tower
    ];

    const records = [];
    for (let i = 0; i < NUM_SHAFTS; i++) {
      const [x, z] = positions[i];
      // Vertical shaft as a thin glass column
      const shaft = BJS.MeshBuilder.CreateBox('n3dShaft_' + i, {
        width: 0.30, height: yc(54) + 1.0, depth: 0.30,
      }, scene);
      shaft.position.x = x;
      shaft.position.z = z;
      shaft.position.y = (yc(54) + 1.0) / 2;
      const sMat = new BJS.StandardMaterial('shaftMat_' + i, scene);
      sMat.diffuseColor = new BJS.Color3(0.08, 0.14, 0.24);
      sMat.specularColor = new BJS.Color3(0.45, 0.65, 0.95);
      sMat.emissiveColor = new BJS.Color3(0.10, 0.25, 0.50);
      sMat.alpha = 0.55;
      shaft.material = sMat;
      shaft.isPickable = false;

      // Lift car
      const car = BJS.MeshBuilder.CreateBox('n3dLiftCar_' + i, {
        width: 0.55, height: 0.55, depth: 0.55,
      }, scene);
      car.position.x = x;
      car.position.z = z;
      car.position.y = yc(0);
      const cMat = new BJS.StandardMaterial('carMat_' + i, scene);
      cMat.diffuseColor = new BJS.Color3(0.12, 0.20, 0.32);
      cMat.emissiveColor = new BJS.Color3(0.40, 0.85, 1.0);
      cMat.specularColor = new BJS.Color3(0.85, 0.95, 1.0);
      car.material = cMat;
      car.isPickable = true;
      car.metadata = { kind: 'lift', shaft_idx: i };

      records.push({
        shaft: shaft, car: car, shaftIdx: i,
        targetY: yc(0),
        currentLift: null,
      });
    }

    function applyLifts(lifts) {
      for (let i = 0; i < records.length; i++) {
        const rec = records[i];
        const L = lifts[i];
        if (!L) {
          rec.targetY = yc(0);
          continue;
        }
        rec.currentLift = L;
        const cf = (L.current_floor !== null && L.current_floor !== undefined)
          ? Number(L.current_floor) : 0;
        rec.targetY = yc(cf);
        const moving = !!L.moving;
        const mat = rec.car.material;
        if (moving) {
          mat.emissiveColor = new BJS.Color3(0.30, 1.0, 0.55);
        } else {
          mat.emissiveColor = new BJS.Color3(0.40, 0.85, 1.0);
        }
        rec.car.metadata.lift_id = L.lift_id;
        rec.car.metadata.status = L.status;
        rec.car.metadata.current_floor = cf;
      }
    }

    function tick() {
      for (let i = 0; i < records.length; i++) {
        const r = records[i];
        const cur = r.car.position.y;
        const dy = r.targetY - cur;
        if (Math.abs(dy) > 0.005) {
          r.car.position.y = cur + dy * 0.08;
        }
      }
    }

    return { records: records, applyLifts: applyLifts, tick: tick };
  }

  window.NEXT3D_LIFTS = { build: build };
})();
