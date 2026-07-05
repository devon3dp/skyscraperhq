// QSB Tower V1.3 — qsb_scene.js (V2)
// Phase: QSB_TOWER_3D_COCKPIT_VISUAL_REFINEMENT_V2
//
// Big, bright, animated Babylon.js skyscraper with:
//  - explicit WebGL probe + debug callbacks
//  - 53 stacked floors, glowing penthouse, locked roof
//  - 9 vertical lift shafts with continuously-moving capsules
//  - workers as glowing spheres + DOM-overlay name labels orbiting home floors
//  - packets as bright spheres with curved travel arcs
//  - click/hover handlers on floors and workers (cockpit.js opens windows)
//  - hard fallback only when WebGL truly unavailable

(function () {
  'use strict';

  const HIGHLIGHT_FLOORS = {
    23: { label: 'AirLLM Big Model Chamber',   color: [0.45, 0.78, 1.0],  glow: 1.05 },
    30: { label: 'Permissions / Risk',         color: [0.69, 0.54, 1.0],  glow: 0.85 },
    31: { label: 'Audit / Ledger',             color: [1.0,  0.79, 0.25], glow: 1.0  },
    37: { label: 'Simulation Labs',            color: [0.36, 0.88, 1.0],  glow: 0.80 },
    38: { label: 'Sandbox Operations',         color: [0.30, 1.0,  0.69], glow: 0.85 },
    41: { label: 'OANDA Trading Floor',        color: [0.36, 0.88, 1.0],  glow: 1.10 },
    42: { label: 'Binance Trading Floor',      color: [1.0,  0.66, 0.31], glow: 1.10 },
    43: { label: 'Stock Exchange Trading Floor', color: [0.85, 0.92, 1.0], glow: 1.18 },
    53: { label: 'Tower Command',              color: [0.42, 0.72, 1.0],  glow: 1.05 },
  };

  // Tower geometry — larger and brighter than V1
  const FLOOR_HEIGHT = 0.70;
  const FLOOR_GAP    = 0.05;
  const FLOOR_WIDTH  = 7.0;
  const FLOOR_DEPTH  = 4.4;
  const SHAFT_INSET  = 0.22;
  const NUM_SHAFTS   = 9;

  const PACKET_COLORS = {
    worker:   [0.30, 1.0,  0.69],
    strategy: [0.36, 0.88, 1.0],
    ledger:   [1.0,  0.79, 0.25],
    openclaw: [0.69, 0.54, 1.0],
    kernel:   [0.45, 0.75, 1.0],
    airllm:   [0.50, 0.80, 1.0],
    paper:    [1.0,  0.88, 0.4],
    stocks:   [0.92, 0.96, 1.0],
    crypto:   [1.0,  0.74, 0.30],
    cross:    [0.78, 0.50, 1.0],
    risk:     [1.0,  0.36, 0.36],
    default:  [0.55, 0.70, 0.95],
  };

  const COLOR_BY_LABEL = {
    green:   PACKET_COLORS.worker,
    cyan:    PACKET_COLORS.strategy,
    gold:    PACKET_COLORS.ledger,
    purple:  PACKET_COLORS.cross,
    white:   PACKET_COLORS.stocks,
    blue:    PACKET_COLORS.kernel,
    yellow:  PACKET_COLORS.paper,
    orange:  PACKET_COLORS.crypto,
    red:     PACKET_COLORS.risk,
  };

  const S = {
    engine: null, scene: null, camera: null,
    BJS: null,
    floorMeshes: {},
    shaftMeshes: [],
    capsuleMeshes: [],
    workerMeshes: {},
    workerData:   {},
    packetPool: [],
    activePackets: [],
    paused: false,
    fallback: false,
    hudTipEl: null,
    workerLabelsEl: null,
    hoveredFloor: null,
    lastPacketSig: null,
    ready: false,
    onPick: null,
    diag: {
      webgl: null,
      webgl2: null,
      engine: false,
      render: false,
      err: '',
      fps: 0,
      // Granular per-step diagnostics
      babylon_global_present: null,
      canvas_found: null,
      canvas_width: 0,
      canvas_height: 0,
      engine_created: false,
      scene_created: false,
      camera_created: false,
      lights_created: false,
      meshes_created: 0,
      render_loop_started: false,
      first_frame_rendered: false,
      babylon_error_stack: '',
    },
    diagCb: null,
  };
  window.QSB_SCENE = S;

  // ── helpers ────────────────────────────────────────────────────────────
  function floorYCenter(num) {
    return num * (FLOOR_HEIGHT + FLOOR_GAP);
  }
  function parseFloorNum(s) {
    if (s == null) return null;
    if (typeof s === 'number') return s;
    if (s === 'ground') return 0;
    if (s === 'roof' || s === 'roof_lock') return 54;
    if (s === 'penthouse') return 53;
    const m = /^(?:floor_)?(\d{1,2})$/.exec(s);
    if (m) return parseInt(m[1], 10);
    return null;
  }
  function hashStr(s) {
    let h = 0; if (!s) return 0;
    for (let i = 0; i < s.length; i++) { h = ((h << 5) - h) + s.charCodeAt(i); h |= 0; }
    return h;
  }
  // Deterministic positive small int from any string. Used to anchor
  // workers to fixed positions on their floor slab in LIVE_DATA_ONLY mode.
  function stableHashInt(s) { return Math.abs(hashStr(String(s || ''))) | 0; }
  function escapeHtml(s) {
    return String(s == null ? '' : s).replace(/[&<>"']/g, (c) =>
      ({ '&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;' }[c]));
  }
  function pushDiag() {
    if (typeof S.diagCb === 'function') {
      try { S.diagCb(S.diag); } catch (e) {}
    }
  }

  // ── WebGL probe (independent of Babylon) ───────────────────────────────
  function probeWebGL() {
    const testCanvas = document.createElement('canvas');
    let webgl2 = null, webgl = null;
    try { webgl2 = testCanvas.getContext('webgl2'); } catch (e) {}
    if (!webgl2) {
      try { webgl  = testCanvas.getContext('webgl') || testCanvas.getContext('experimental-webgl'); } catch (e) {}
    }
    S.diag.webgl2 = !!webgl2;
    S.diag.webgl  = !!(webgl2 || webgl);
    return S.diag.webgl;
  }

  // ── materials ─────────────────────────────────────────────────────────
  function makeEmissive(scene, name, rgb, glow) {
    const BJS = S.BJS;
    const m = new BJS.StandardMaterial(name, scene);
    m.diffuseColor  = new BJS.Color3(rgb[0] * 0.55, rgb[1] * 0.55, rgb[2] * 0.55);
    m.specularColor = new BJS.Color3(0.12, 0.12, 0.18);
    m.emissiveColor = new BJS.Color3(rgb[0] * glow, rgb[1] * glow, rgb[2] * glow);
    return m;
  }

  // ── scene construction ────────────────────────────────────────────────
  function buildScene(canvas) {
    const BJS = S.BJS;
    // Granular diag: record canvas dimensions at the moment of init
    S.diag.canvas_found = !!canvas;
    if (canvas) {
      S.diag.canvas_width  = canvas.clientWidth  | 0;
      S.diag.canvas_height = canvas.clientHeight | 0;
    }
    const engine = new BJS.Engine(canvas, true, {
      preserveDrawingBuffer: true, stencil: true, antialias: true, adaptToDeviceRatio: true,
    });
    S.diag.engine_created = true;
    pushDiag();
    const scene = new BJS.Scene(engine);
    S.diag.scene_created = true;
    pushDiag();
    scene.clearColor = new BJS.Color4(0.014, 0.030, 0.078, 1);
    // V18.4 — fog tinted to match twilight sky so city horizon blends into sky, not into void
    scene.fogMode = BJS.Scene.FOGMODE_EXP2;
    scene.fogColor = new BJS.Color3(0.12, 0.16, 0.34);
    scene.fogDensity = 0.0028;

    // V18 — camera sized for 165-floor tower (was 53)
    // Tower is 7×4.4×124 units. Default radius 90 places camera ~30 wide of tower —
    // wide enough to see the whole stack, close enough to stay INSIDE the city ring.
    const cam = new BJS.ArcRotateCamera(
      'cam',
      -Math.PI * 0.58,
      Math.PI / 2.65,
      90,                                   // was 54 (53-floor) → 180 (broke: inside city) → 90 (right)
      new BJS.Vector3(0, floorYCenter(62), 0),  // was floor 28 — frame ~middle of 165
      scene
    );
    cam.attachControl(canvas, true);
    cam.lowerRadiusLimit = 14;
    cam.upperRadiusLimit = 300;             // can zoom out to see all + sky
    cam.lowerBetaLimit = 0.18;
    cam.upperBetaLimit = Math.PI / 2 + 0.05;
    cam.wheelPrecision = 4;
    cam.panningSensibility = 80;
    cam.minZ = 0.05;
    cam.maxZ = 1500;                        // far plane covers skydome
    S.diag.camera_created = true;
    pushDiag();

    // Brighter lighting (V1 was too dark)
    const hemi = new BJS.HemisphericLight('hemi', new BJS.Vector3(0, 1, 0), scene);
    hemi.intensity = 0.9;
    hemi.groundColor = new BJS.Color3(0.06, 0.08, 0.16);
    hemi.diffuse = new BJS.Color3(0.65, 0.78, 1.0);

    const dir = new BJS.DirectionalLight('dir', new BJS.Vector3(-0.55, -0.9, -0.45), scene);
    dir.intensity = 0.85;
    dir.diffuse = new BJS.Color3(0.95, 0.92, 1.0);

    const rim = new BJS.DirectionalLight('rim', new BJS.Vector3(0.6, -0.2, 0.7), scene);
    rim.intensity = 0.35;
    rim.diffuse = new BJS.Color3(0.6, 0.55, 1.0);
    S.diag.lights_created = true;
    pushDiag();

    // V18.2 — change the scene clearColor itself so the "sky" is always
    // visible behind everything else. Use Babylon's gradient approach via
    // a large box that's always behind the camera frustum.
    // V18.3 — much brighter twilight skybox so it's obviously visible
    scene.clearColor = new BJS.Color4(0.12, 0.16, 0.34, 1);
    const stars = BJS.MeshBuilder.CreateSphere('skydome',
        { diameter: 1400, segments: 32, sideOrientation: BJS.Mesh.DOUBLESIDE }, scene);
    const starsMat = new BJS.StandardMaterial('skydomeMat', scene);
    starsMat.emissiveColor = new BJS.Color3(0.22, 0.28, 0.50);  // bright twilight purple-blue
    starsMat.diffuseColor = new BJS.Color3(0, 0, 0);
    starsMat.specularColor = new BJS.Color3(0, 0, 0);
    starsMat.backFaceCulling = false;
    starsMat.disableLighting = true;
    stars.material = starsMat;
    stars.isPickable = false;
    stars.infiniteDistance = true;
    stars.applyFog = false;

    // V18 — Stars: ~120 emissive specks scattered on the dome
    const starsRoot = new BJS.TransformNode('stars_root', scene);
    for (let i = 0; i < 120; i++) {
      const a = Math.random() * Math.PI * 2;
      const b = Math.random() * Math.PI * 0.45 + Math.PI * 0.05;  // upper hemisphere
      const r = 520;
      const star = BJS.MeshBuilder.CreateSphere('s_' + i, { diameter: 0.6 + Math.random() * 1.2, segments: 4 }, scene);
      star.position.x = r * Math.cos(a) * Math.sin(b);
      star.position.z = r * Math.sin(a) * Math.sin(b);
      star.position.y = r * Math.cos(b);
      const sm = new BJS.StandardMaterial('sm_' + i, scene);
      sm.emissiveColor = new BJS.Color3(0.85, 0.92, 1.0);
      sm.diffuseColor = new BJS.Color3(0, 0, 0);
      star.material = sm;
      star.isPickable = false;
      star.parent = starsRoot;
    }

    // V18 — Distant city ground plane (big dark city instead of empty void)
    const ground = BJS.MeshBuilder.CreateDisc('plaza', { radius: 380, tessellation: 96 }, scene);
    ground.rotation.x = Math.PI / 2;
    ground.position.y = -0.55;
    const gm = new BJS.StandardMaterial('plazaMat', scene);
    gm.diffuseColor = new BJS.Color3(0.06, 0.09, 0.14);
    gm.emissiveColor = new BJS.Color3(0.05, 0.08, 0.16);
    gm.specularColor = new BJS.Color3(0.2, 0.3, 0.45);
    ground.material = gm;

    // V18.4 — Distant city silhouette: low skyline ring so it sits BELOW the horizon line
    // from the default camera (y≈80 looking at y≈46). Heights capped at 30 so sky always
    // peeks over the buildings at screen mid-height.
    const cityRoot = new BJS.TransformNode('city_root', scene);
    for (let i = 0; i < 80; i++) {
      const angle = (i / 80) * Math.PI * 2 + Math.random() * 0.05;
      const dist = 350 + Math.random() * 350;
      const bw = 12 + Math.random() * 18;
      const bd = 12 + Math.random() * 18;
      const bh = 10 + Math.random() * 20;        // V18.4: 10-30m (was 18-98m)
      const b = BJS.MeshBuilder.CreateBox('city_' + i, { width: bw, height: bh, depth: bd }, scene);
      b.position.x = Math.cos(angle) * dist;
      b.position.z = Math.sin(angle) * dist;
      b.position.y = bh / 2 - 0.55;
      const bm = new BJS.StandardMaterial('cm_' + i, scene);
      const tone = 0.07 + Math.random() * 0.08;
      bm.diffuseColor = new BJS.Color3(tone * 0.8, tone, tone * 1.3);
      bm.emissiveColor = new BJS.Color3(tone * 0.4, tone * 0.5, tone * 0.9);
      bm.specularColor = new BJS.Color3(0.15, 0.18, 0.30);
      b.material = bm;
      b.isPickable = false;
      b.parent = cityRoot;
    }

    // V18 — Moon: large emissive sphere in the upper sky
    const moon = BJS.MeshBuilder.CreateSphere('moon', { diameter: 32, segments: 24 }, scene);
    moon.position.x = -350; moon.position.y = 340; moon.position.z = -180;
    const moonMat = new BJS.StandardMaterial('moonMat', scene);
    moonMat.emissiveColor = new BJS.Color3(0.92, 0.94, 1.0);
    moonMat.diffuseColor = new BJS.Color3(0.40, 0.42, 0.50);
    moonMat.specularColor = new BJS.Color3(0, 0, 0);
    moon.material = moonMat;
    moon.isPickable = false;

    // V18.5 — richer department-coded materials so the 165 floors are visibly distinct
    scene._qsbMats = {
      zoneA:    makeEmissive(scene, 'zoneA',    [0.30, 0.85, 0.78], 0.34),  // Lobby / shop · teal-cyan
      zoneB:    makeEmissive(scene, 'zoneB',    [0.36, 0.66, 0.92], 0.34),  // Reception, HR · light blue
      zoneC:    makeEmissive(scene, 'zoneC',    [0.42, 0.92, 0.62], 0.36),  // Ops support · green
      zoneTrade:makeEmissive(scene, 'zoneTrade',[0.98, 0.58, 0.22], 0.55),  // F41-45 trading · orange
      zoneFin:  makeEmissive(scene, 'zoneFin',  [1.00, 0.82, 0.30], 0.48),  // Finance / accounts · gold
      zoneRes:  makeEmissive(scene, 'zoneRes',  [0.78, 0.50, 1.00], 0.42),  // Research / strategy · purple
      zoneExp:  makeEmissive(scene, 'zoneExp',  [0.30, 0.46, 0.95], 0.30),  // Expansion / departments · deep blue
      zoneTop:  makeEmissive(scene, 'zoneTop',  [0.90, 0.80, 1.00], 0.55),  // Above penthouse · lavender
      zonePent: makeEmissive(scene, 'zonePent', [1.00, 0.85, 0.40], 0.95),  // F153 Penthouse · gold glow
      vacant:   makeEmissive(scene, 'vacant',   [0.30, 0.36, 0.50], 0.16),
      ground: makeEmissive(scene, 'ground', [0.50, 0.65, 1.00], 0.55),
      roof:   makeEmissive(scene, 'roof',   [0.74, 0.55, 1.00], 0.42),
      shaft:  (() => {
        const m = new BJS.StandardMaterial('shaft', scene);
        m.diffuseColor = new BJS.Color3(0.10, 0.22, 0.36);
        m.emissiveColor = new BJS.Color3(0.06, 0.22, 0.42);
        m.specularColor = new BJS.Color3(0.15, 0.25, 0.4);
        m.alpha = 0.55;
        return m;
      })(),
      capsule: (() => {
        const m = new BJS.StandardMaterial('cap', scene);
        m.diffuseColor = new BJS.Color3(0.18, 0.40, 0.70);
        m.emissiveColor = new BJS.Color3(0.45, 0.78, 1.0);
        m.specularColor = new BJS.Color3(0.6, 0.7, 1.0);
        return m;
      })(),
    };

    S.engine = engine;
    S.scene = scene;
    S.camera = cam;

    buildTowerSkeleton(scene);
    S.diag.meshes_created = Object.keys(S.floorMeshes).length;
    pushDiag();
    buildLiftShafts(scene);
    S.diag.meshes_created += S.shaftMeshes.length;
    pushDiag();
    buildLiftCapsules(scene);
    S.diag.meshes_created += S.capsuleMeshes.length;
    pushDiag();

    // ── pointer (hover/click) ─────────────────────────────────────────
    scene.onPointerObservable.add((info) => {
      if (info.type === BJS.PointerEventTypes.POINTERMOVE) {
        const pick = scene.pick(scene.pointerX, scene.pointerY, (m) => m.metadata && (m.metadata.kind === 'floor' || m.metadata.kind === 'worker'));
        if (pick && pick.hit) {
          showTip(pick.pickedMesh.metadata);
          S.hoveredFloor = pick.pickedMesh.metadata.number;
        } else {
          hideTip();
          S.hoveredFloor = null;
        }
      } else if (info.type === BJS.PointerEventTypes.POINTERTAP) {
        const pick = scene.pick(scene.pointerX, scene.pointerY, (m) => m.metadata && (m.metadata.kind === 'floor' || m.metadata.kind === 'worker'));
        if (pick && pick.hit && typeof S.onPick === 'function') {
          const md = pick.pickedMesh.metadata || {};
          // Pass through the enriched metadata so cockpit.js can open the
          // right named floor window.
          S.onPick(Object.assign({}, md));
        }
      }
    });

    // Render loop with FPS measurement
    let frameCount = 0; let lastFps = performance.now();
    engine.runRenderLoop(() => {
      if (S.paused) return;
      try {
        tickAnimations();
        scene.render();
        S.diag.render = true;
        if (!S.diag.first_frame_rendered) {
          S.diag.first_frame_rendered = true;
          pushDiag();
        }
        frameCount++;
        const now = performance.now();
        if (now - lastFps >= 1000) {
          S.diag.fps = Math.round((frameCount * 1000) / (now - lastFps));
          frameCount = 0; lastFps = now;
          pushDiag();
        }
        updateWorkerLabels();
      } catch (e) {
        S.diag.render = false;
        S.diag.err = String(e && e.message ? e.message : e).slice(0, 200);
        S.diag.babylon_error_stack = (e && e.stack ? String(e.stack) : '').slice(0, 600);
        pushDiag();
      }
    });
    S.diag.render_loop_started = true;
    pushDiag();
    window.addEventListener('resize', () => engine.resize());
    setTimeout(() => engine.resize(), 60);    // catch late layout
    setTimeout(() => engine.resize(), 300);

    return true;
  }

  function buildTowerSkeleton(scene) {
    const BJS = S.BJS;
    const mats = scene._qsbMats;

    // Ground / lobby slab
    const g = BJS.MeshBuilder.CreateBox('ground_slab',
      { width: FLOOR_WIDTH * 1.18, height: FLOOR_HEIGHT * 1.4, depth: FLOOR_DEPTH * 1.18 }, scene);
    g.position.y = -FLOOR_HEIGHT * 0.7;
    g.material = mats.ground;
    g.metadata = { kind: 'floor', number: 0, label: 'Ground / Reception Lobby' };
    S.floorMeshes[0] = g;

    // V18 — 165-floor tower (was 53). Penthouse moved from F53 to F153.
    for (let n = 1; n <= 165; n++) {
      const isPent = (n === 153);
      const h = isPent ? FLOOR_HEIGHT * 1.45 : FLOOR_HEIGHT;
      const w = isPent ? FLOOR_WIDTH * 1.08 : FLOOR_WIDTH;
      const d = isPent ? FLOOR_DEPTH * 1.08 : FLOOR_DEPTH;
      const slab = BJS.MeshBuilder.CreateBox('floor_' + n, { width: w, height: h, depth: d }, scene);
      slab.position.y = floorYCenter(n);

      // V18.5 — narrower bands tied to department reality of the 165-floor tower
      let mat;
      if (isPent)            mat = mats.zonePent;   // F153 Penthouse · gold glow
      else if (n <= 10)      mat = mats.zoneA;      // 1-10  Lobby / shop · teal
      else if (n <= 20)      mat = mats.zoneB;      // 11-20 Reception / HR · light blue
      else if (n <= 30)      mat = mats.zoneC;      // 21-30 Ops support · green
      else if (n <= 40)      mat = mats.zoneB;      // 31-40 Ops · light blue
      else if (n <= 45)      mat = mats.zoneTrade;  // 41-45 Trading floors · orange
      else if (n <= 65)      mat = mats.zoneFin;    // 46-65 Finance + advisers · gold
      else if (n <= 100)     mat = mats.zoneRes;    // 66-100 Research + strategy · purple
      else if (n <= 152)     mat = mats.zoneExp;    // 101-152 Expansion / departments · deep blue
      else                   mat = mats.zoneTop;    // 154-165 above-penthouse · lavender

      // Vacant marker only for never-built sub-bands (none in 165-floor build)
      const isVacant = false;
      if (isVacant) mat = mats.vacant;

      slab.material = mat;
      slab.metadata = { kind: 'floor', number: n, label: null, vacant: isVacant };
      S.floorMeshes[n] = slab;
    }

    // V18 — Penthouse halo/core moved to F153 (was F53)
    const halo = BJS.MeshBuilder.CreateTorus('pent_halo',
      { diameter: FLOOR_WIDTH * 1.65, thickness: 0.16, tessellation: 56 }, scene);
    halo.position.y = floorYCenter(153) + FLOOR_HEIGHT * 0.95;
    const haloMat = new BJS.StandardMaterial('haloMat', scene);
    haloMat.emissiveColor = new BJS.Color3(1.0, 0.82, 0.35);
    haloMat.diffuseColor = new BJS.Color3(0.15, 0.10, 0.02);
    halo.material = haloMat;
    halo.isPickable = false;
    S.pentHalo = halo;

    // Penthouse glow sphere (a soft inner core) — V18 moved to F153
    const core = BJS.MeshBuilder.CreateSphere('pent_core', { diameter: FLOOR_WIDTH * 0.55, segments: 16 }, scene);
    core.position.y = floorYCenter(153) + FLOOR_HEIGHT * 0.15;
    const coreMat = new BJS.StandardMaterial('coreMat', scene);
    coreMat.emissiveColor = new BJS.Color3(1.0, 0.85, 0.45);
    coreMat.diffuseColor = new BJS.Color3(0.05, 0.04, 0.0);
    coreMat.alpha = 0.55;
    core.material = coreMat;
    core.isPickable = false;
    S.pentCore = core;

    // ── OpenClaw supervisor mesh — persistent avatar ────────────────
    // Mirrors the SVG marker on the Babylon scene. Moves only when the
    // backend qsb_openclaw_route.current_floor changes; otherwise
    // hovers in place. NEVER orbits, never random.
    const ocBase = BJS.MeshBuilder.CreateSphere('openclaw_core',
      { diameter: 0.55, segments: 18 }, scene);
    const ocBaseMat = new BJS.StandardMaterial('ocBaseMat', scene);
    ocBaseMat.emissiveColor = new BJS.Color3(0.69, 0.54, 1.0);  // PACKET_COLORS.openclaw
    ocBaseMat.diffuseColor  = new BJS.Color3(0.18, 0.12, 0.32);
    ocBaseMat.specularColor = new BJS.Color3(0.5, 0.4, 0.8);
    ocBase.material = ocBaseMat;
    ocBase.isPickable = false;
    ocBase.metadata = { kind: 'openclaw' };

    const ocRing = BJS.MeshBuilder.CreateTorus('openclaw_ring',
      { diameter: 1.05, thickness: 0.06, tessellation: 36 }, scene);
    const ocRingMat = new BJS.StandardMaterial('ocRingMat', scene);
    ocRingMat.emissiveColor = new BJS.Color3(0.55, 0.42, 0.95);
    ocRingMat.diffuseColor  = new BJS.Color3(0.10, 0.08, 0.20);
    ocRingMat.alpha = 0.65;
    ocRing.material = ocRingMat;
    ocRing.isPickable = false;
    ocRing.rotation.x = Math.PI / 2;

    S.openclawCore = ocBase;
    S.openclawRing = ocRing;
    // Park at floor 53 until live telemetry says otherwise.
    ocBase.position.x = 0; ocBase.position.z = 0;
    ocBase.position.y = floorYCenter(153) + FLOOR_HEIGHT * 0.5;
    ocRing.position.copyFrom(ocBase.position);

    // Roof = external provider lock layer
    const roof = BJS.MeshBuilder.CreateBox('roof_lock',
      { width: FLOOR_WIDTH * 1.22, height: FLOOR_HEIGHT * 1.0, depth: FLOOR_DEPTH * 1.22 }, scene);
    roof.position.y = floorYCenter(153) + FLOOR_HEIGHT * 2.2;
    roof.material = mats.roof;
    roof.metadata = { kind: 'roof', number: 166, label: 'Roof — External Providers (LOCKED)' };
    S.floorMeshes[166] = roof;

    // Roof lock rings (visible "locked" markers)
    for (let i = 0; i < 2; i++) {
      const ring = BJS.MeshBuilder.CreateTorus('lock_ring_' + i,
        { diameter: FLOOR_WIDTH * 0.85, thickness: 0.10, tessellation: 32 }, scene);
      ring.position.y = floorYCenter(153) + FLOOR_HEIGHT * (2.5 + i * 0.4);
      ring.rotation.z = Math.PI / 2;
      ring.rotation.y = i * 0.6;
      const rmat = new BJS.StandardMaterial('lr_' + i, scene);
      rmat.emissiveColor = new BJS.Color3(0.74, 0.55, 1.00);
      rmat.diffuseColor = new BJS.Color3(0.04, 0.02, 0.10);
      ring.material = rmat;
      ring.isPickable = false;
    }

    // Spire
    const spire = BJS.MeshBuilder.CreateCylinder('spire',
      { height: 3.0, diameterTop: 0.02, diameterBottom: 0.50, tessellation: 16 }, scene);
    spire.position.y = floorYCenter(153) + FLOOR_HEIGHT * 2.2 + 1.65;
    const spireMat = new BJS.StandardMaterial('spireMat', scene);
    spireMat.emissiveColor = new BJS.Color3(0.55, 0.75, 1.0);
    spireMat.diffuseColor = new BJS.Color3(0.10, 0.20, 0.40);
    spire.material = spireMat;
    spire.isPickable = false;

    // Highlighted floors: brighter, slightly wider
    for (const k of Object.keys(HIGHLIGHT_FLOORS)) {
      const n = parseInt(k, 10);
      const info = HIGHLIGHT_FLOORS[n];
      const mesh = S.floorMeshes[n];
      if (!mesh) continue;
      const mat = new BJS.StandardMaterial('hl_' + n, scene);
      mat.diffuseColor  = new BJS.Color3(info.color[0] * 0.5, info.color[1] * 0.5, info.color[2] * 0.5);
      mat.emissiveColor = new BJS.Color3(info.color[0] * info.glow, info.color[1] * info.glow, info.color[2] * info.glow);
      mat.specularColor = new BJS.Color3(0.25, 0.3, 0.4);
      mesh.material = mat;
      mesh.metadata.label = info.label;
      mesh.scaling = new BJS.Vector3(1.09, 1.10, 1.09);
    }
  }

  function buildLiftShafts(scene) {
    const BJS = S.BJS;
    const mats = scene._qsbMats;
    const yBottom = -FLOOR_HEIGHT * 0.7;
    const yTop = floorYCenter(153) + FLOOR_HEIGHT * 1.5;
    const totalH = yTop - yBottom;
    const centerY = (yBottom + yTop) / 2;

    // Distribute 9 shafts along the back face of the building
    const z = -FLOOR_DEPTH / 2 - SHAFT_INSET - 0.06;
    const span = FLOOR_WIDTH - 0.6;
    for (let i = 0; i < NUM_SHAFTS; i++) {
      const x = -span / 2 + (i * span) / (NUM_SHAFTS - 1);
      const shaft = BJS.MeshBuilder.CreateBox('shaft_' + i,
        { width: 0.16, height: totalH, depth: 0.16 }, scene);
      shaft.position.set(x, centerY, z);
      shaft.material = mats.shaft;
      shaft.isPickable = false;
      S.shaftMeshes.push({ mesh: shaft, x, z, yBottom, yTop });
    }
  }

  function buildLiftCapsules(scene) {
    const BJS = S.BJS;
    const mats = scene._qsbMats;
    for (let i = 0; i < NUM_SHAFTS; i++) {
      const s = S.shaftMeshes[i];
      const cap = BJS.MeshBuilder.CreateBox('cap_' + i,
        { width: 0.50, height: 0.42, depth: 0.50 }, scene);
      cap.position.set(s.x, floorYCenter(1 + i * 6), s.z);
      cap.material = mats.capsule;
      cap.isPickable = false;
      S.capsuleMeshes.push({
        mesh: cap, shaft: s,
        phase: Math.random() * Math.PI * 2,
        speed: 0.22 + Math.random() * 0.22,
      });
    }
  }

  // ── workers ────────────────────────────────────────────────────────────
  function colorForWorker(w) {
    const n = (w.name || w.id || '').toLowerCase();
    if (n.includes('openclaw')) return { rgb: PACKET_COLORS.openclaw, cls: 'openclaw' };
    if (n.includes('airllm'))   return { rgb: PACKET_COLORS.airllm,   cls: 'airllm' };
    if (n.includes('ledger'))   return { rgb: PACKET_COLORS.ledger,   cls: 'ledger' };
    if (n.includes('correlation') || n.includes('risk-on') || n.includes('risk_on')) return { rgb: PACKET_COLORS.cross, cls: 'cross' };
    if (n.includes('equity') || n.includes('stock'))         return { rgb: PACKET_COLORS.stocks,   cls: 'stocks' };
    if (n.includes('strategy')) return { rgb: PACKET_COLORS.strategy, cls: 'strategy' };
    if (n.includes('kernel'))   return { rgb: PACKET_COLORS.kernel,   cls: 'kernel' };
    if (n.includes('paper'))    return { rgb: PACKET_COLORS.paper,    cls: 'paper' };
    return { rgb: PACKET_COLORS.worker, cls: 'worker' };
  }

  function refreshWorkers(state) {
    if (!S.ready || !state) return;
    const BJS = S.BJS;
    const scene = S.scene;
    const workers = state.workers || [];

    // V18.7 — selected_floor_and_groups + capped operational rendering so the
    // tower is visibly populated without melting fps at 9k workers.
    const mode = (window.QSB && window.QSB.workerViewMode) || 'selected_floor_and_groups';
    const selFloor = (window.QSB && Number(window.QSB.selectedFloor)) || null;
    const TRADING = new Set([41, 42, 43, 44, 45]);
    const ADMIN   = new Set([28, 47, 48, 49, 53, 153]);
    let renderSet = new Set();
    const CAP_SFG = 220;
    const CAP_OPS = 500;
    if (mode === 'all_workers_visible') {
      workers.forEach((w) => renderSet.add(w.id));
    } else if (mode === 'operational_only') {
      let n = 0;
      for (const w of workers) {
        if (w.is_simulation) continue;
        renderSet.add(w.id); if (++n >= CAP_OPS) break;
      }
    } else if (mode === 'worker_problems') {
      workers.forEach((w) => { if (w.flagged || w.problem || w.has_problem) renderSet.add(w.id); });
    } else if (mode === 'counts_only') {
      // intentionally render no individual meshes
    } else {
      // 'selected_floor_and_groups' (default): show a small even sample so the
      // tower looks staffed without melting fps. Bucket-cap per floor (=8) and
      // global cap (=80). Selected floor gets its own larger bucket.
      const PER_FLOOR_CAP = 4;
      const SEL_FLOOR_CAP = 12;
      const bucket = {};
      let nTotal = 0;
      for (const w of workers) {
        if (nTotal >= 40) break;
        const f = parseFloorNum(w.home_floor);
        const onSel = selFloor != null && f === selFloor;
        const onTrade = TRADING.has(f);
        const onAdmin = ADMIN.has(f);
        if (!(onSel || onTrade || onAdmin)) continue;
        const cap = onSel ? SEL_FLOOR_CAP : PER_FLOOR_CAP;
        bucket[f] = bucket[f] || 0;
        if (bucket[f] >= cap) continue;
        bucket[f]++;
        renderSet.add(w.id);
        nTotal++;
      }
    }

    // Remove stale (and any that should no longer render under this mode)
    for (const id of Object.keys(S.workerMeshes)) {
      if (!renderSet.has(id)) {
        S.workerMeshes[id].dispose();
        delete S.workerMeshes[id];
        delete S.workerData[id];
        const lbl = document.querySelector('#workerLabels .wlbl[data-wid="' + CSS.escape(id) + '"]');
        if (lbl && lbl.parentNode) lbl.parentNode.removeChild(lbl);
      }
    }
    // Filter the rest of refreshWorkers to renderSet only.
    const _origWorkers = workers;
    state = Object.assign({}, state, {
      workers: _origWorkers.filter((w) => renderSet.has(w.id))
    });
    const ids = new Set(state.workers.map((w) => w.id));

    // Add new — only those that survived the renderSet filter.
    state.workers.forEach((w, idx) => {
      if (S.workerMeshes[w.id]) {
        S.workerData[w.id] = w;
        return;
      }
      const floorNum = parseFloorNum(w.home_floor) || 38;
      const dot = BJS.MeshBuilder.CreateSphere('w_' + w.id, { diameter: 0.50, segments: 12 }, scene);
      const c = colorForWorker(w);
      const m = new BJS.StandardMaterial('wm_' + w.id, scene);
      m.diffuseColor  = new BJS.Color3(c.rgb[0] * 0.45, c.rgb[1] * 0.45, c.rgb[2] * 0.45);
      m.emissiveColor = new BJS.Color3(c.rgb[0] * 1.10, c.rgb[1] * 1.10, c.rgb[2] * 1.10);
      m.specularColor = new BJS.Color3(0.3, 0.4, 0.6);
      dot.material = m;
      dot.metadata = { kind: 'worker', id: w.id, name: w.name, floor: floorNum, role: w.role };
      // V3: workers are ANCHORED to a deterministic spot on their floor
      // slab using a stable hash of worker_id. No orbiting. Movement
      // happens only when state.qsb_dashboard_live_telemetry.worker_movements
      // says so. This eliminates the fake "worker band" around the tower.
      const slot = stableHashInt(w.id || w.name || ('w' + idx));
      // 7-slot ring across the slab: -3..+3 quarter-floor-widths.
      const slotX = ((slot % 7) - 3) * (FLOOR_WIDTH * 0.20);
      // 3-row depth: -1..+1 quarter-floor-depths.
      const slotZ = ((Math.floor(slot / 7) % 3) - 1) * (FLOOR_DEPTH * 0.25);
      dot._qsbBase = {
        floor: floorNum,
        y: floorYCenter(floorNum) + FLOOR_HEIGHT * 0.45,
        anchorX: slotX,
        anchorZ: slotZ,
        phase: (slot * 0.41) % (Math.PI * 2),
        cls: c.cls,
        // Movement is data-driven; populated by the V3 telemetry consumer.
        in_transit: false,
        transit_from: null,
        transit_to: null,
        transit_started_ms: 0,
        transit_dur_ms: 0,
      };
      // Park the mesh at the anchor right away so it never flashes through
      // the orbit ring before the next frame.
      dot.position.x = slotX;
      dot.position.z = slotZ;
      dot.position.y = floorYCenter(floorNum) + FLOOR_HEIGHT * 0.45;
      S.workerMeshes[w.id] = dot;
      S.workerData[w.id] = w;

      // DOM label — cache ref on the mesh so updateWorkerLabels doesn't
      // querySelector once per worker per frame (the 2-3fps killer).
      if (S.workerLabelsEl) {
        const lbl = document.createElement('div');
        lbl.className = 'wlbl ' + c.cls;
        lbl.dataset.wid = w.id;
        lbl.textContent = abbrev(w.name || w.id);
        lbl.style.opacity = '0';
        S.workerLabelsEl.appendChild(lbl);
        dot._qsbLbl = lbl;
      }
    });
  }

  function abbrev(name) {
    if (!name) return '';
    if (name.length <= 18) return name;
    return name.replace(/(\w+)\s/g, (m, w) => w[0].toUpperCase() + '·');
  }

  // Project 3D worker positions to 2D screen for DOM labels
  let _lblTick = 0;
  function updateWorkerLabels() {
    if (!S.workerLabelsEl || !S.engine) return;
    // Throttle: project + reflow only every 3rd frame. Browsers don't visibly
    // ghost at 20Hz label updates and per-worker cost drops 66%.
    if ((++_lblTick % 3) !== 0) return;
    const cam = S.camera;
    const engine = S.engine;
    const w = engine.getRenderWidth();
    const h = engine.getRenderHeight();
    const ratioX = S.workerLabelsEl.clientWidth / w;
    const ratioY = S.workerLabelsEl.clientHeight / h;
    const viewport = cam.viewport.toGlobal(w, h);
    const transformMatrix = S.scene.getTransformMatrix();
    const BJS = S.BJS;
    const camFwd = cam.getForwardRay().direction;
    const camPos = cam.position;
    const identity = BJS.Matrix.Identity();
    for (const id of Object.keys(S.workerMeshes)) {
      const mesh = S.workerMeshes[id];
      if (!mesh) continue;
      const lbl = mesh._qsbLbl;
      if (!lbl) continue;
      const ap = mesh.getAbsolutePosition();
      const toCamX = ap.x - camPos.x, toCamY = ap.y - camPos.y, toCamZ = ap.z - camPos.z;
      if ((toCamX * camFwd.x + toCamY * camFwd.y + toCamZ * camFwd.z) < 0) {
        if (lbl.style.opacity !== '0') lbl.style.opacity = '0';
        continue;
      }
      const pos = BJS.Vector3.Project(ap, identity, transformMatrix, viewport);
      // transform: translate3d() is GPU-accelerated; left/top forces layout.
      // Preserve CSS centering offset (-50%,-150%) by chaining transforms.
      lbl.style.transform = 'translate3d(' + (pos.x * ratioX | 0) + 'px,' + (pos.y * ratioY | 0) + 'px,0) translate(-50%,-150%)';
      if (lbl.style.opacity !== '0.92') lbl.style.opacity = '0.92';
    }
  }

  // ── packets ────────────────────────────────────────────────────────────
  function spawnPacketsFromState(state) {
    if (!S.ready || !state) return;
    const sig = (state.packets || []).map((p) => p.ts + ':' + p.source_floor + ':' + p.target_floor).join('|');
    if (sig === S.lastPacketSig) return;
    S.lastPacketSig = sig;
    (state.packets || []).forEach((p, i) => {
      setTimeout(() => spawnPacket(p), i * 220);
    });
    // Fire sound tick if audio module wants it
    if (window.QSB_AUDIO && window.QSB_AUDIO.tickPacket) {
      try { window.QSB_AUDIO.tickPacket(state.packets || []); } catch (e) {}
    }
  }

  // V18.6 — floor activity pulse: brief brighten + pop when activity touches a floor
  function pulseFloor(n, intensity) {
    if (!S.ready || n == null) return;
    const mesh = S.floorMeshes[n];
    if (!mesh || !mesh.material) return;
    S.floorPulses = S.floorPulses || {};
    const em = mesh.material.emissiveColor;
    if (!S.floorPulses[n]) {
      S.floorPulses[n] = {
        baseEm: { r: em.r, g: em.g, b: em.b },
        baseScaleY: mesh.scaling.y || 1,
      };
    }
    S.floorPulses[n].started = performance.now();
    S.floorPulses[n].intensity = Math.max(0.6, Math.min(2.0, intensity || 1.1));
  }

  function tickFloorPulses() {
    if (!S.floorPulses) return;
    const DUR = 700;
    const now = performance.now();
    for (const k of Object.keys(S.floorPulses)) {
      const p = S.floorPulses[k];
      if (!p.started) continue;
      const t = (now - p.started) / DUR;
      const mesh = S.floorMeshes[k];
      if (!mesh || !mesh.material) { delete S.floorPulses[k]; continue; }
      if (t >= 1) {
        mesh.material.emissiveColor.set(p.baseEm.r, p.baseEm.g, p.baseEm.b);
        mesh.scaling.y = p.baseScaleY;
        p.started = 0;
        continue;
      }
      const k2 = (1 - t) * p.intensity;
      mesh.material.emissiveColor.set(
        Math.min(1, p.baseEm.r + 0.55 * k2),
        Math.min(1, p.baseEm.g + 0.55 * k2),
        Math.min(1, p.baseEm.b + 0.30 * k2));
      mesh.scaling.y = p.baseScaleY * (1 + 0.18 * k2);
    }
  }

  function spawnPacket(p) {
    if (!S.ready) return;
    const src = parseFloorNum(p.source_floor); const dst = parseFloorNum(p.target_floor);
    if (src == null || dst == null) return;
    // V18.6 — pulse source on dispatch + dest on arrival
    pulseFloor(src, 1.0);
    setTimeout(() => pulseFloor(dst, 1.3), 1600);
    const BJS = S.BJS;
    const scene = S.scene;

    const rgb = COLOR_BY_LABEL[(p.color || 'green').toLowerCase()] || PACKET_COLORS[p.type] || PACKET_COLORS.default;
    const sphere = BJS.MeshBuilder.CreateSphere('pkt', { diameter: 0.32, segments: 8 }, scene);
    const m = new BJS.StandardMaterial('pktm', scene);
    m.diffuseColor  = new BJS.Color3(rgb[0] * 0.35, rgb[1] * 0.35, rgb[2] * 0.35);
    m.emissiveColor = new BJS.Color3(rgb[0] * 1.2, rgb[1] * 1.2, rgb[2] * 1.2);
    m.specularColor = new BJS.Color3(0.3, 0.3, 0.3);
    sphere.material = m;
    sphere.isPickable = false;

    const shaftIdx = Math.abs(hashStr(p.lift_id || p.title || 'main_low_rise')) % NUM_SHAFTS;
    const s = S.shaftMeshes[shaftIdx];
    const ySrc = floorYCenter(src);
    const yDst = floorYCenter(dst);

    S.activePackets.push({
      mesh: sphere, x: s.x, z: s.z, ySrc, yDst,
      dur: 1.8 + Math.abs(dst - src) * 0.06, born: performance.now(),
    });
  }

  // ── per-frame animations ──────────────────────────────────────────────
  function tickAnimations() {
    const now = performance.now() / 1000;
    const BJS = S.BJS;

    for (const c of S.capsuleMeshes) {
      const s = c.shaft;
      // V3 LIVE_DATA_ONLY: capsules park at parked_y unless a real
      // lift_movements record drives their motion. parked_y is the
      // bottom of the shaft + a tiny offset; movement is set by the
      // V3 telemetry consumer in cockpit.js / qsb_skyscraper_v3.js.
      const range = s.yTop - s.yBottom - 0.8;
      if (c.live_dest_y != null && c.live_start_y != null && c.live_started_ms) {
        const dur = Math.max(400, c.live_dur_ms || 1800);
        const t = Math.min(1, Math.max(0, (performance.now() - c.live_started_ms) / dur));
        const ease = 0.5 - Math.cos(Math.PI * t) / 2;
        c.mesh.position.y = c.live_start_y + (c.live_dest_y - c.live_start_y) * ease;
        if (t >= 1) {
          c.live_start_y = c.live_dest_y;
          c.live_dest_y = null;
          c.live_started_ms = 0;
          c.parked_y = c.mesh.position.y;
        }
      } else {
        c.parked_y = c.parked_y != null ? c.parked_y :
                     (s.yBottom + 0.4 + range * 0.5);
        c.mesh.position.y = c.parked_y;
      }
    }

    // V3 LIVE_DATA_ONLY: workers stay parked at their anchor on the
    // assigned floor slab. The only motion comes from a real
    // transit record sourced from qsb_dashboard_live_telemetry.worker_movements.
    for (const id of Object.keys(S.workerMeshes)) {
      const mesh = S.workerMeshes[id];
      const b = mesh._qsbBase;
      if (!b) continue;
      if (b.in_transit && b.transit_dur_ms > 0) {
        const t = Math.min(1, Math.max(0,
          (performance.now() - b.transit_started_ms) / b.transit_dur_ms));
        const fromY = floorYCenter(b.transit_from || b.floor) + FLOOR_HEIGHT * 0.45;
        const toY   = floorYCenter(b.transit_to   || b.floor) + FLOOR_HEIGHT * 0.45;
        mesh.position.y = fromY + (toY - fromY) * t;
        if (t >= 1) {
          b.in_transit = false;
          b.floor = b.transit_to || b.floor;
          // V18.6 — pulse the arrival floor so it visibly registers
          pulseFloor(b.floor, 0.9);
        }
      } else {
        mesh.position.x = b.anchorX;
        mesh.position.z = b.anchorZ;
        mesh.position.y = b.y;
      }
      // Subtle deterministic emissive breathing (decorative only) — same
      // visual per frame for every worker, no random per-worker phase.
      const breathe = 0.92 + Math.sin(now * 1.6) * 0.06;
      const palette = PACKET_COLORS[b.cls] || PACKET_COLORS.worker;
      mesh.material.emissiveColor.r = palette[0] * 1.10 * breathe;
      mesh.material.emissiveColor.g = palette[1] * 1.10 * breathe;
      mesh.material.emissiveColor.b = palette[2] * 1.10 * breathe;
    }

    const remaining = [];
    const ms = performance.now();
    for (const p of S.activePackets) {
      const t = (ms - p.born) / 1000 / p.dur;
      if (t >= 1) { p.mesh.dispose(); continue; }
      const ease = 0.5 - Math.cos(Math.PI * t) / 2;
      p.mesh.position.x = p.x + Math.sin(t * Math.PI) * 0.35;
      p.mesh.position.z = p.z + Math.cos(t * Math.PI) * 0.18;
      p.mesh.position.y = p.ySrc + (p.yDst - p.ySrc) * ease;
      remaining.push(p);
    }
    S.activePackets = remaining;

    tickFloorPulses();

    if (S.pentHalo) {
      const k = 0.85 + Math.sin(now * 1.8) * 0.18;
      S.pentHalo.material.emissiveColor.set(1.0 * k, 0.82 * k, 0.38 * k);
      S.pentHalo.rotation.y = now * 0.35;
    }
    if (S.pentCore) {
      const k = 0.85 + Math.sin(now * 2.4) * 0.18;
      S.pentCore.material.emissiveColor.set(1.0 * k, 0.85 * k, 0.45 * k);
      S.pentCore.scaling.x = S.pentCore.scaling.y = S.pentCore.scaling.z = 1 + Math.sin(now * 1.6) * 0.06;
    }

    // ── OpenClaw avatar: anchor at current_floor; glow + slow bob ───
    if (S.openclawCore && S.openclawRing) {
      const ocFloor = (window.QSB && window.QSB.openclawCurrentFloor) || 53;
      const targetY = floorYCenter(ocFloor) + FLOOR_HEIGHT * 0.55;
      // Smooth move (ease toward target).
      const curY = S.openclawCore.position.y;
      S.openclawCore.position.y = curY + (targetY - curY) * 0.06;
      S.openclawRing.position.y = S.openclawCore.position.y;
      // Park beside the tower on the right.
      const sideX = FLOOR_WIDTH * 0.85;
      S.openclawCore.position.x = sideX;
      S.openclawRing.position.x = sideX;
      // Glow pulse — deterministic
      const ocK = 0.85 + Math.sin(now * 1.4) * 0.16;
      S.openclawCore.material.emissiveColor.set(0.69 * ocK, 0.54 * ocK, 1.0 * ocK);
      S.openclawRing.rotation.z = now * 0.6;
      S.openclawRing.scaling.x = S.openclawRing.scaling.y =
        S.openclawRing.scaling.z = 1 + Math.sin(now * 1.8) * 0.05;
    }
  }

  function applyStateToScene(state) {
    if (!S.ready || !state) return;
    // Stamp display_name / category / status onto every floor mesh's metadata
    // so 3D picks always carry the canonical name (not just the floor number).
    const sf = state.floors || [];
    sf.forEach((f) => {
      const mesh = S.floorMeshes[f.number];
      if (!mesh) return;
      const md = mesh.metadata || (mesh.metadata = {});
      md.display_name = f.display_name || f.canonical_name || f.department || ('Floor ' + f.number);
      md.canonical_name = f.canonical_name || md.display_name;
      md.category = f.category || 'infrastructure';
      md.status = f.status || 'active';
      md.floor_id = f.id || ('floor_' + f.number);
      md.route_ids = (f.route_ids || []).map((r) => r && r.target ? r.target : null).filter(Boolean);
      // Keep existing fields (kind, number, vacant)
    });
    const active = state.kernel && state.kernel.activation_status === 'active_local_only';
    if (S.pentHalo) {
      S.pentHalo.material.emissiveColor = active
        ? new S.BJS.Color3(1.0, 0.82, 0.35)
        : new S.BJS.Color3(0.30, 0.25, 0.18);
    }
    const anyLockTrue = (state.lock_count_true || 0) > 0;
    const roof = S.floorMeshes[54];
    if (roof) {
      roof.material.emissiveColor = anyLockTrue
        ? new S.BJS.Color3(0.95, 0.18, 0.22)
        : new S.BJS.Color3(0.74, 0.55, 1.00);
    }
    refreshWorkers(state);
    spawnPacketsFromState(state);
  }

  // ── tooltip ────────────────────────────────────────────────────────────
  function showTip(meta) {
    const el = S.hudTipEl;
    if (!el) return;
    let title, sub;
    if (meta.kind === 'floor') {
      title = meta.label || ('Floor ' + meta.number);
      if (meta.number === 0) sub = 'Ground · reception lobby';
      else if (meta.number === 54) sub = 'External provider lock layer · LOCKED';
      else if (meta.number === 53) sub = 'Penthouse · QSB Kernel (active_local_only)';
      else if (meta.vacant) sub = 'Floor ' + meta.number + ' · vacant (expansion-ready)';
      else sub = 'Floor ' + meta.number + ' — click for details';
    } else if (meta.kind === 'worker') {
      title = meta.name || meta.id;
      sub = (meta.role || '') + ' · home floor ' + meta.floor + ' — click for details';
    }
    el.innerHTML = '<div class="ht-title">' + escapeHtml(title) + '</div>' +
      '<div class="ht-sub">' + escapeHtml(sub) + '</div>';
    el.classList.add('on');
  }
  function hideTip() {
    if (S.hudTipEl) S.hudTipEl.classList.remove('on');
  }

  // ── 2D fallback ────────────────────────────────────────────────────────
  function buildFallback2D(host) {
    if (!host) return;
    host.innerHTML = '';
    const items = [];
    items.push({ n: 54, label: 'Roof — External Providers (LOCKED)', cls: 'roof' });
    items.push({ n: 53, label: 'Penthouse — QSB Kernel (active_local_only)', cls: 'penthouse' });
    for (let n = 52; n >= 1; n--) {
      const info = HIGHLIGHT_FLOORS[n];
      let cls = '';
      if (info) cls = 'glow';
      else if (n >= 43 && n <= 45) cls = 'vacant';
      items.push({ n, label: info ? info.label : ('Floor ' + n), cls });
    }
    items.push({ n: 0, label: 'Ground / Reception Lobby', cls: 'ground' });
    for (const it of items) {
      const row = document.createElement('div');
      row.className = 'fl ' + it.cls;
      row.innerHTML = '<span class="num">' + it.n + '</span><span>' + escapeHtml(it.label) + '</span>';
      host.appendChild(row);
    }
  }

  // ── public API ─────────────────────────────────────────────────────────
  window.QSB_SCENE_INIT = function init(opts) {
    const canvas = opts.canvas;
    const hudTipEl = opts.hudTipEl;
    const workerLabelsEl = opts.workerLabelsEl;
    S.hudTipEl = hudTipEl;
    S.workerLabelsEl = workerLabelsEl;
    S.diagCb = opts.onDiag || null;
    S.onPick = opts.onPick || null;
    const onReady = opts.onReady || null;   // called when 3D successfully renders the first frame
    const onFail  = opts.onFail  || null;   // called with a reason string if 3D cannot start

    // 1. Probe WebGL regardless of Babylon presence so the debug strip is accurate
    probeWebGL();
    pushDiag();

    // 2. Check Babylon presence
    S.diag.babylon_global_present = (typeof BABYLON !== 'undefined');
    if (!S.diag.babylon_global_present) {
      S.diag.engine = false;
      S.diag.err = 'Babylon.js not loaded';
      pushDiag();
      if (onFail) onFail('Babylon.js engine failed to load.');
      return false;
    }
    S.BJS = BABYLON;

    if (!S.diag.webgl) {
      S.diag.engine = false;
      S.diag.err = 'No WebGL context';
      pushDiag();
      if (onFail) onFail('This browser does not provide a WebGL context.');
      return false;
    }

    // 3. Defer Babylon construction until a render frame so flex/grid layout has resolved
    requestAnimationFrame(() => {
      try {
        const ok = buildScene(canvas);
        if (!ok) throw new Error('buildScene returned false');
        S.diag.engine = true;
        S.ready = true;
        pushDiag();
        if (window.QSB && window.QSB.state) applyStateToScene(window.QSB.state);
        if (onReady) {
          // Notify on next frame so we know rendering actually proceeded
          requestAnimationFrame(() => { try { onReady(); } catch (e) {} });
        }
      } catch (e) {
        S.diag.engine = false;
        S.diag.err = (e && e.message ? e.message : String(e)).slice(0, 200);
        S.diag.babylon_error_stack = (e && e.stack ? String(e.stack) : '').slice(0, 600);
        pushDiag();
        if (onFail) onFail('WebGL is supported but the 3D scene failed to initialise: ' + S.diag.err);
      }
    });

    window.addEventListener('qsb:state', (e) => applyStateToScene(e.detail));
    return true;
  };

  window.QSB_SCENE_PAUSE = function (paused) { S.paused = !!paused; };
  window.QSB_SCENE_RESET = function () {
    if (!S.camera || !S.BJS) return;
    S.camera.alpha = -Math.PI * 0.58;
    S.camera.beta  = Math.PI / 2.65;
    S.camera.radius = 54;
    S.camera.target = new S.BJS.Vector3(0, floorYCenter(28), 0);
  };
  window.QSB_SCENE_FOCUS = function (floorNum) {
    if (!S.camera || !S.BJS) return;
    S.camera.target = new S.BJS.Vector3(0, floorYCenter(floorNum), 0);
    S.camera.radius = 22;
  };

  // Expose for cockpit click handlers
  window.QSB_SCENE_INFO = function () {
    return {
      ready: S.ready, fallback: S.fallback, diag: S.diag,
      floors: Object.keys(S.floorMeshes).length,
      workers: Object.keys(S.workerMeshes).length,
      packets: S.activePackets.length,
    };
  };
})();
