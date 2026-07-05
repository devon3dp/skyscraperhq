/*
 * QSB Next3D — Tower Geometry
 * Phase: QSB_NEXTGEN_3D_DASHBOARD_GREENFIELD_REBUILD_V1
 *
 * Builds 55 stacked floor slabs (floor 0 = ground, 54 = roof,
 * 55 = penthouse hat). No SVG. Each floor is a Babylon Box.
 */
(function () {
  'use strict';

  // Geometry constants — different from the old cockpit numbers.
  const FLOOR_H = 1.0;
  const FLOOR_GAP = 0.05;
  const FLOOR_W = 12;
  const FLOOR_D = 8;
  const PENTHOUSE_W = 9;
  const PENTHOUSE_D = 6;
  const ROOF_H = 0.6;

  function floorYCenter(num) {
    return num * (FLOOR_H + FLOOR_GAP) + FLOOR_H / 2;
  }

  function floorMaterial(scene, BJS, info, density) {
    const m = new BJS.StandardMaterial('flMat_' + info.num, scene);
    const c = categoryColor(info.category);
    m.diffuseColor = new BJS.Color3(c[0] * 0.40, c[1] * 0.40, c[2] * 0.45);
    m.specularColor = new BJS.Color3(0.15, 0.18, 0.25);
    const glow = info.special ? 0.55 : 0.20;
    // Density boost — operational workers give extra glow
    const ops = (info.classes && info.classes.operational_worker) || 0;
    const boost = Math.min(0.18, ops / 1000);
    m.emissiveColor = new BJS.Color3(
      c[0] * glow + boost,
      c[1] * glow + boost,
      c[2] * glow + boost
    );
    m.alpha = 0.94;
    return m;
  }

  function categoryColor(cat) {
    switch (cat) {
      case 'kernel':       return [1.0, 0.85, 0.40];
      case 'command':      return [0.45, 0.70, 1.0];
      case 'recruitment':  return [0.55, 1.0,  0.75];
      case 'accounts':     return [1.0, 0.78, 0.30];
      case 'stocks':       return [0.40, 1.0,  0.55];
      case 'binance':      return [1.0, 0.80, 0.20];
      case 'oanda':        return [0.36, 0.85, 1.0];
      case 'sandbox':      return [0.62, 1.0,  0.85];
      case 'strategy':     return [0.85, 0.65, 1.0];
      case 'hardware':     return [0.75, 0.85, 0.95];
      case 'audit':        return [1.0, 0.75, 0.45];
      case 'guardian':     return [1.0, 0.40, 0.55];
      case 'airllm':       return [0.45, 0.78, 1.0];
      case 'lifts':        return [0.65, 0.90, 1.0];
      case 'security':     return [1.0, 0.50, 0.60];
      default:             return [0.55, 0.65, 0.80];
    }
  }

  function buildTower(scene, BJS, floors) {
    const meshes = {};

    // Ground plate
    const ground = BJS.MeshBuilder.CreateGround('n3dGround',
      { width: 80, height: 80 }, scene);
    const gMat = new BJS.StandardMaterial('groundMat', scene);
    gMat.diffuseColor = new BJS.Color3(0.04, 0.07, 0.12);
    gMat.specularColor = new BJS.Color3(0.05, 0.08, 0.16);
    gMat.emissiveColor = new BJS.Color3(0.01, 0.02, 0.05);
    ground.material = gMat;

    // Build a slab for every floor 0..54 (54 = roof), plus 55 = penthouse hat
    const floorInfoByNum = {};
    floors.forEach(function (f) { floorInfoByNum[f.num] = f; });

    for (let n = 0; n <= 54; n++) {
      const info = floorInfoByNum[n] || {
        num: n, category: 'generic', special: false,
        worker_total: 0, classes: {},
      };
      const w = (n === 53 || n === 54) ? PENTHOUSE_W : FLOOR_W;
      const d = (n === 53 || n === 54) ? PENTHOUSE_D : FLOOR_D;
      const h = (n === 54) ? ROOF_H : FLOOR_H;
      const slab = BJS.MeshBuilder.CreateBox('n3dFl_' + n,
        { width: w, height: h, depth: d }, scene);
      slab.position.y = floorYCenter(n);
      slab.material = floorMaterial(scene, BJS, info, info.worker_total);
      slab.metadata = {
        kind: 'floor', number: n,
        name: info.name || ('Floor ' + n),
        category: info.category,
        special: info.special,
      };
      slab.isPickable = true;
      meshes[n] = slab;
    }

    // Penthouse crown (decorative top spire)
    const crown = BJS.MeshBuilder.CreateCylinder('n3dCrown',
      { diameterTop: 0.4, diameterBottom: 4.5, height: 2.4 }, scene);
    crown.position.y = floorYCenter(54) + 1.6;
    const crownMat = new BJS.StandardMaterial('crownMat', scene);
    crownMat.diffuseColor = new BJS.Color3(0.85, 0.65, 0.20);
    crownMat.emissiveColor = new BJS.Color3(1.0, 0.82, 0.35);
    crownMat.specularColor = new BJS.Color3(1.0, 0.95, 0.6);
    crown.material = crownMat;
    crown.metadata = { kind: 'floor', number: 55, name: 'Penthouse · Kernel' };
    crown.isPickable = true;
    meshes[55] = crown;

    // Building shell — translucent glass + edge highlight wireframe so the
    // silhouette reads clearly against the background.
    const shell = BJS.MeshBuilder.CreateBox('n3dShell', {
      width: FLOOR_W + 0.4, height: floorYCenter(54) + 0.6,
      depth: FLOOR_D + 0.4,
    }, scene);
    shell.position.y = (floorYCenter(54) + 0.6) / 2;
    const sMat = new BJS.StandardMaterial('shellMat', scene);
    sMat.diffuseColor = new BJS.Color3(0.08, 0.14, 0.22);
    sMat.specularColor = new BJS.Color3(0.28, 0.40, 0.65);
    sMat.emissiveColor = new BJS.Color3(0.03, 0.05, 0.10);
    sMat.alpha = 0.14;
    sMat.backFaceCulling = false;
    shell.material = sMat;
    shell.isPickable = false;

    // Edge highlight — only the 12 silhouette edges of the bounding box,
    // drawn as glow lines (no diagonal triangulation, unlike wireframe=true
    // on a Box which would split each face).
    const eW = FLOOR_W + 0.5;
    const eD = FLOOR_D + 0.5;
    const eY0 = 0;
    const eY1 = floorYCenter(54) + 0.7;
    const v = function (x, y, z) { return new BJS.Vector3(x, y, z); };
    const corners = [
      v(-eW/2, eY0, -eD/2), v(eW/2, eY0, -eD/2),
      v(eW/2, eY0,  eD/2), v(-eW/2, eY0,  eD/2),
      v(-eW/2, eY1, -eD/2), v(eW/2, eY1, -eD/2),
      v(eW/2, eY1,  eD/2), v(-eW/2, eY1,  eD/2),
    ];
    const edgePaths = [
      // bottom rectangle
      [corners[0], corners[1], corners[2], corners[3], corners[0]],
      // top rectangle
      [corners[4], corners[5], corners[6], corners[7], corners[4]],
      // 4 vertical pillars
      [corners[0], corners[4]],
      [corners[1], corners[5]],
      [corners[2], corners[6]],
      [corners[3], corners[7]],
    ];
    for (let ei = 0; ei < edgePaths.length; ei++) {
      const ln = BJS.MeshBuilder.CreateLines('n3dEdge_' + ei,
        { points: edgePaths[ei] }, scene);
      ln.color = new BJS.Color3(0.45, 0.85, 1.0);
      ln.alpha = 0.55;
      ln.isPickable = false;
    }

    return { meshes: meshes, ground: ground, shell: shell, geometry: {
      FLOOR_H, FLOOR_GAP, FLOOR_W, FLOOR_D,
      floorYCenter: floorYCenter,
    }};
  }

  window.NEXT3D_TOWER = {
    build: buildTower,
    floorYCenter: floorYCenter,
    FLOOR_H: FLOOR_H, FLOOR_GAP: FLOOR_GAP,
    FLOOR_W: FLOOR_W, FLOOR_D: FLOOR_D,
  };
})();
