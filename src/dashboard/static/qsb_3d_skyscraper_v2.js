/*
 * QSB 3D Skyscraper V2 — Live Data-Bound Babylon Upgrade
 * Phase: QSB_3D_SKYSCRAPER_LIVE_REBUILD_V2
 *
 * 1) Auto-promotes the dashboard to .use-3d mode so the existing
 *    967-line Babylon scene (qsb_scene.js) actually shows up.
 * 2) Adds NEW visible meshes on top:
 *      - 9 LIFT CARS that smoothly animate between source/target floors
 *        bound to /api/dashboard/lift_scene_state
 *      - OPENCLAW ORB (purple emissive sphere) floating at the
 *        current_floor from /api/openclaw/route
 *      - SELECTED FLOOR HALO (yellow torus) around the slab when
 *        URL ?floor=N is set
 *      - WORKER DENSITY GLOW — modulates floor mesh emissive brightness
 *        by per-floor worker count from /api/dashboard/worker_scene_state
 *      - CADENCE PULSE on Penthouse — emissive pulse synced to tick
 *      - PnL HALO around Floor 41 — green/red per realized PnL sign
 *      - INTERCOM FLASHES — light pulses along lift columns when
 *        sealed packets transit between 41/42/43
 *
 * Polls every 3 seconds. No random motion. Everything tied to real
 * registry data.
 */
(function () {
  'use strict';
  if (window.QSB_3D_V2_INSTALLED) return;
  window.QSB_3D_V2_INSTALLED = true;

  const POLL_MS = 3000;
  let scene = null;
  let BJS = null;
  let mounts = {
    liftCars: [],   // one Mesh per lift
    openclaw: null, // sphere
    selectedHalo: null,
    pnlHalo: null,
    cadenceLight: null,
    intercomTrails: [], // transient particle meshes
  };
  let lastState = null;

  // ── floor Y helper (mirrors qsb_scene.js floorYCenter) ──────────
  // qsb_scene.js used FLOOR_HEIGHT=0.70, FLOOR_GAP=0.05.
  function floorYCenter(num) {
    const h = 0.70;
    const gap = 0.05;
    return (num * (h + gap)) + (h / 2);
  }

  // Tower geometry knobs (must mirror qsb_scene.js so meshes align)
  const FLOOR_WIDTH = 7.0;
  const FLOOR_DEPTH = 4.4;
  const SHAFT_INSET = 0.22;
  const NUM_SHAFTS = 9;

  function shaftX(idx) {
    // 9 shafts spaced across tower width
    const spread = (FLOOR_WIDTH - 2 * SHAFT_INSET);
    const dx = spread / (NUM_SHAFTS - 1);
    return -spread / 2 + dx * idx;
  }
  function shaftZ() { return 0; }  // lift cars run on a single Z plane

  async function fetchJSON(url) {
    try {
      const sep = url.indexOf('?') === -1 ? '?' : '&';
      const r = await fetch(url + sep + 't=' + Date.now(), { cache: 'no-store' });
      if (!r.ok) return null;
      return await r.json();
    } catch (_) { return null; }
  }

  // ── 1. Promote dashboard to 3D-active ──────────────────────────
  function promoteTo3D() {
    const stage = document.querySelector('.stage-body');
    if (stage && !stage.classList.contains('use-3d')) {
      stage.classList.add('use-3d');
    }
    // Make sure RENDERER active flag stays in sync
    if (window.RENDERER) {
      window.RENDERER.active = 'webgl_3d';
      window.RENDERER.wantWebGL = true;
    }
  }

  // ── 2. Wait for Babylon scene to be ready ──────────────────────
  function waitForScene(maxTries) {
    return new Promise(function (resolve) {
      let tries = 0;
      const id = setInterval(function () {
        tries++;
        const S = window.QSB_SCENE;
        if (S && S.ready && S.scene && S.BJS) {
          clearInterval(id);
          scene = S.scene;
          BJS = S.BJS;
          resolve(true);
          return;
        }
        if (tries > (maxTries || 60)) {
          clearInterval(id);
          resolve(false);
        }
      }, 500);
    });
  }

  // ── 3. Build new V2 meshes on top of existing scene ────────────
  function buildLiftCars() {
    if (mounts.liftCars.length > 0) return;
    for (let i = 0; i < NUM_SHAFTS; i++) {
      const car = BJS.MeshBuilder.CreateBox(
        'qsbV2LiftCar' + i,
        { width: 0.42, height: 0.34, depth: 0.42 }, scene);
      car.position.x = shaftX(i);
      car.position.y = floorYCenter(0);
      car.position.z = shaftZ();
      const m = new BJS.StandardMaterial('liftMat' + i, scene);
      m.diffuseColor = new BJS.Color3(0.10, 0.18, 0.32);
      m.emissiveColor = new BJS.Color3(0.32, 0.66, 1.00);
      m.specularColor = new BJS.Color3(0.6, 0.6, 0.85);
      car.material = m;
      car.metadata = { lift_idx: i, kind: 'lift_v2' };
      mounts.liftCars.push({ mesh: car, target: 0, current: 0, lift_id: null });
    }
  }

  function buildOpenClawOrb() {
    if (mounts.openclaw) return;
    const orb = BJS.MeshBuilder.CreateSphere(
      'qsbV2OpenClawOrb', { diameter: 0.7, segments: 24 }, scene);
    orb.position.x = FLOOR_WIDTH * 0.6;
    orb.position.y = floorYCenter(53);
    orb.position.z = 0;
    const m = new BJS.StandardMaterial('ocMatV2', scene);
    m.diffuseColor = new BJS.Color3(0.18, 0.05, 0.30);
    m.emissiveColor = new BJS.Color3(0.85, 0.40, 1.0);
    m.specularColor = new BJS.Color3(0.95, 0.65, 1.0);
    orb.material = m;
    orb.metadata = { kind: 'openclaw_v2' };
    // Halo: torus around it
    const halo = BJS.MeshBuilder.CreateTorus(
      'qsbV2OcHalo', { diameter: 1.5, thickness: 0.05, tessellation: 36 }, scene);
    halo.parent = orb;
    const hm = new BJS.StandardMaterial('ocHaloMat', scene);
    hm.diffuseColor = new BJS.Color3(0.6, 0.4, 1.0);
    hm.emissiveColor = new BJS.Color3(0.9, 0.6, 1.0);
    hm.alpha = 0.55;
    halo.material = hm;
    mounts.openclaw = { orb: orb, halo: halo, current_floor: 53, target_floor: 53 };
  }

  function buildSelectedFloorHalo() {
    if (mounts.selectedHalo) return;
    const halo = BJS.MeshBuilder.CreateTorus(
      'qsbV2SelectedHalo',
      { diameter: FLOOR_WIDTH * 1.32, thickness: 0.10, tessellation: 64 },
      scene);
    halo.position.y = floorYCenter(0);
    halo.rotation.x = Math.PI / 2;
    const m = new BJS.StandardMaterial('selHaloMat', scene);
    m.diffuseColor = new BJS.Color3(0.6, 0.5, 0.1);
    m.emissiveColor = new BJS.Color3(1.0, 0.85, 0.30);
    m.alpha = 0.75;
    halo.material = m;
    halo.setEnabled(false);
    mounts.selectedHalo = halo;
  }

  function buildPnLHalo() {
    if (mounts.pnlHalo) return;
    const halo = BJS.MeshBuilder.CreateTorus(
      'qsbV2PnLHalo',
      { diameter: FLOOR_WIDTH * 1.20, thickness: 0.06, tessellation: 48 },
      scene);
    halo.position.y = floorYCenter(41);
    halo.rotation.x = Math.PI / 2;
    const m = new BJS.StandardMaterial('pnlHaloMat', scene);
    m.diffuseColor = new BJS.Color3(0.1, 0.4, 0.2);
    m.emissiveColor = new BJS.Color3(0.3, 1.0, 0.55);
    m.alpha = 0.5;
    halo.material = m;
    mounts.pnlHalo = halo;
  }

  function buildCadenceLight() {
    if (mounts.cadenceLight) return;
    // A point light at the Penthouse that pulses with cadence.
    const light = new BJS.PointLight(
      'qsbV2CadenceLight',
      new BJS.Vector3(0, floorYCenter(53), 0), scene);
    light.diffuse = new BJS.Color3(1.0, 0.85, 0.4);
    light.specular = new BJS.Color3(1.0, 0.9, 0.5);
    light.intensity = 0.6;
    mounts.cadenceLight = light;
  }

  function buildAllMeshes() {
    buildLiftCars();
    buildOpenClawOrb();
    buildSelectedFloorHalo();
    buildPnLHalo();
    buildCadenceLight();
  }

  // ── 4. Update meshes from live data ────────────────────────────
  function lerp(a, b, t) { return a + (b - a) * t; }

  function updateLiftCars(state) {
    const lifts = (state && state.lifts) || [];
    for (let i = 0; i < mounts.liftCars.length; i++) {
      const rec = mounts.liftCars[i];
      const data = lifts[i];
      if (!data) continue;
      const tgt = data.current_floor !== null && data.current_floor !== undefined
        ? Number(data.current_floor) : 0;
      rec.target = tgt;
      rec.lift_id = data.lift_id;
      // Color by moving/idle
      const moving = !!data.moving;
      const mat = rec.mesh.material;
      if (moving) {
        mat.emissiveColor = new BJS.Color3(0.30, 1.00, 0.65);  // green
      } else {
        mat.emissiveColor = new BJS.Color3(0.32, 0.66, 1.00);  // blue
      }
    }
  }

  function tickLiftCars() {
    // Smooth lerp from current y → target floor y each frame.
    for (let i = 0; i < mounts.liftCars.length; i++) {
      const rec = mounts.liftCars[i];
      const targetY = floorYCenter(rec.target);
      const curY = rec.mesh.position.y;
      const dy = targetY - curY;
      if (Math.abs(dy) > 0.005) {
        rec.mesh.position.y = curY + dy * 0.06;  // 6% per frame ~= 0.5s settle
      }
    }
  }

  function updateOpenClaw(state) {
    if (!mounts.openclaw) return;
    const cf = state.openclaw_current_floor;
    if (cf === null || cf === undefined) return;
    mounts.openclaw.target_floor = Number(cf);
  }

  function tickOpenClaw() {
    if (!mounts.openclaw) return;
    const tgtY = floorYCenter(mounts.openclaw.target_floor);
    const curY = mounts.openclaw.orb.position.y;
    if (Math.abs(tgtY - curY) > 0.01) {
      mounts.openclaw.orb.position.y = curY + (tgtY - curY) * 0.04;
    }
    // Continuous orbit around the tower
    const t = performance.now() * 0.0006;
    mounts.openclaw.orb.position.x = Math.cos(t) * (FLOOR_WIDTH * 0.62);
    mounts.openclaw.orb.position.z = Math.sin(t) * 1.4;
    mounts.openclaw.halo.rotation.y += 0.01;
  }

  function updateSelectedHalo() {
    if (!mounts.selectedHalo) return;
    const sel = (window.QSB && window.QSB.selectedFloor);
    if (sel === null || sel === undefined) {
      mounts.selectedHalo.setEnabled(false);
      return;
    }
    mounts.selectedHalo.setEnabled(true);
    mounts.selectedHalo.position.y = floorYCenter(Number(sel));
  }

  function updatePnLHalo(state) {
    if (!mounts.pnlHalo) return;
    const t = (state.trading_pnl && state.trading_pnl.total) || 0;
    const m = mounts.pnlHalo.material;
    if (t > 0) {
      m.emissiveColor = new BJS.Color3(0.30, 1.0, 0.55);  // green
    } else if (t < 0) {
      m.emissiveColor = new BJS.Color3(1.0, 0.45, 0.55);  // red
    } else {
      m.emissiveColor = new BJS.Color3(0.7, 0.7, 0.7);    // neutral
    }
  }

  function updateCadenceLight(state) {
    if (!mounts.cadenceLight) return;
    const tick = Number(state.cadence_tick || 0);
    // Pulse intensity each new tick
    const phase = (performance.now() * 0.002 + tick * 0.7) % (Math.PI * 2);
    mounts.cadenceLight.intensity = 0.45 + 0.35 * Math.max(0, Math.cos(phase));
  }

  // Worker density glow: boost emissive of each floor mesh by /pf.total/
  function updateFloorDensityGlow(state) {
    const S = window.QSB_SCENE;
    if (!S || !S.floorMeshes) return;
    const per = state.per_floor || [];
    per.forEach(function (rec) {
      const mesh = S.floorMeshes[rec.floor];
      if (!mesh || !mesh.material) return;
      const cur = mesh.material.emissiveColor;
      if (!cur) return;
      const boost = Math.min(0.25, (rec.total || 0) / 1200);
      // Add small green tint scaled by ops count
      const ops = rec.ops || 0;
      const g = Math.min(0.20, ops / 800);
      mesh.material.emissiveColor = new BJS.Color3(
        Math.min(1.0, cur.r + boost),
        Math.min(1.0, cur.g + boost + g),
        Math.min(1.0, cur.b + boost));
    });
  }

  // ── 5. Intercom flashes ────────────────────────────────────────
  function spawnIntercomFlash(fromFloor, toFloor, lift) {
    if (fromFloor === null || toFloor === null) return;
    const ball = BJS.MeshBuilder.CreateSphere(
      'qsbV2Flash', { diameter: 0.20, segments: 12 }, scene);
    ball.position.x = 0;
    ball.position.y = floorYCenter(fromFloor);
    ball.position.z = 0;
    const m = new BJS.StandardMaterial('flashMat', scene);
    m.diffuseColor = new BJS.Color3(1.0, 0.95, 0.4);
    m.emissiveColor = new BJS.Color3(1.0, 0.95, 0.45);
    ball.material = m;
    mounts.intercomTrails.push({
      mesh: ball,
      fromY: floorYCenter(fromFloor),
      toY: floorYCenter(toFloor),
      t: 0,
      lift: lift,
    });
  }

  function tickIntercomTrails() {
    for (let i = mounts.intercomTrails.length - 1; i >= 0; i--) {
      const tr = mounts.intercomTrails[i];
      tr.t += 0.02;
      if (tr.t >= 1) {
        tr.mesh.dispose();
        mounts.intercomTrails.splice(i, 1);
        continue;
      }
      tr.mesh.position.y = lerp(tr.fromY, tr.toY, tr.t);
    }
  }

  let lastFlashIndex = 0;
  function maybeSpawnIntercom(state) {
    const flashes = (state && state.intercom_flashes) || [];
    // Spawn one new flash per poll (cap visual noise)
    if (flashes.length > 0) {
      lastFlashIndex = (lastFlashIndex + 1) % flashes.length;
      const f = flashes[lastFlashIndex];
      if (f && f.from_floor != null && f.to_floor != null) {
        spawnIntercomFlash(f.from_floor, f.to_floor, f.lift);
      }
    }
  }

  // ── 6. Build badge ─────────────────────────────────────────────
  function ensureBadge() {
    let b = document.getElementById('qsb3dV2Badge');
    if (b) return b;
    b = document.createElement('div');
    b.id = 'qsb3dV2Badge';
    b.className = 'qsb-3d-v2-badge';
    b.textContent = 'LIVE 3D · V2 · lifts/openclaw/pnl/cadence bound';
    document.body.appendChild(b);
    return b;
  }

  // ── 7. Orchestrator ────────────────────────────────────────────
  async function pollAndApply() {
    const state = await fetchJSON('/api/dashboard/3d_skyscraper_state');
    if (!state) return;
    lastState = state;
    updateLiftCars(state);
    updateOpenClaw(state);
    updatePnLHalo(state);
    updateCadenceLight(state);
    updateFloorDensityGlow(state);
    maybeSpawnIntercom(state);
    // Badge stats
    const b = ensureBadge();
    b.textContent = 'LIVE 3D · V2 · lifts=' + (state.lift_count || 0) +
      ' · openclaw f' + (state.openclaw_current_floor || '—') +
      ' · cadence ' + (state.cadence_tick || 0) +
      ' · pnl ' + (state.trading_pnl ?
        ((state.trading_pnl.total || 0).toFixed(2)) : '—');
  }

  function tickAnimations() {
    tickLiftCars();
    tickOpenClaw();
    updateSelectedHalo();
    tickIntercomTrails();
  }

  async function start() {
    promoteTo3D();
    ensureBadge();
    const ready = await waitForScene(60);
    if (!ready) {
      const b = ensureBadge();
      b.textContent = 'LIVE 3D · V2 · Babylon scene NOT READY — WebGL may be unavailable';
      b.classList.add('error');
      return;
    }
    buildAllMeshes();
    // Hook into Babylon render loop for smooth animation
    scene.registerBeforeRender(tickAnimations);
    // Poll live data
    pollAndApply().catch(function () {});
    setInterval(function () { pollAndApply().catch(function () {}); }, POLL_MS);
  }

  if (document.readyState === 'loading') {
    document.addEventListener('DOMContentLoaded', start);
  } else { start(); }

  window.QSB_3D_V2 = {
    refresh: pollAndApply,
    state: function () { return lastState; },
    mounts: mounts,
  };
})();
