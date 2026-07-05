/*
 * QSB Next3D — Scene Builder
 * Phase: QSB_NEXTGEN_3D_DASHBOARD_GREENFIELD_REBUILD_V1
 *
 * Builds the Babylon scene: engine, lighting, fog, glow, env probe.
 * Returns the assembled subsystems (camera, tower, lifts, workers,
 * openclaw, floors) so next3d_app can drive them.
 */
(function () {
  'use strict';

  function probeWebGL() {
    try {
      const c = document.createElement('canvas');
      const gl = c.getContext('webgl2') || c.getContext('webgl');
      return !!gl;
    } catch (_) { return false; }
  }

  function build(canvas, initialFloors) {
    if (!probeWebGL()) {
      const err = document.getElementById('next3d-webgl-unavailable');
      if (err) err.hidden = false;
      return { ready: false, error: 'webgl_unavailable' };
    }
    if (!window.BABYLON) {
      const err = document.getElementById('next3d-webgl-unavailable');
      if (err) {
        err.hidden = false;
        err.textContent = 'Babylon.js not loaded.';
      }
      return { ready: false, error: 'babylon_unavailable' };
    }
    const BJS = window.BABYLON;

    const engine = new BJS.Engine(canvas, true, {
      preserveDrawingBuffer: true,
      stencil: true,
      antialias: true,
      adaptToDeviceRatio: true,
    });

    const scene = new BJS.Scene(engine);
    scene.clearColor = new BJS.Color4(0.008, 0.018, 0.034, 1);
    scene.fogMode = BJS.Scene.FOGMODE_LINEAR;
    scene.fogColor = new BJS.Color3(0.012, 0.025, 0.045);
    scene.fogStart = 80;
    scene.fogEnd = 230;
    scene.ambientColor = new BJS.Color3(0.05, 0.10, 0.18);

    // Lighting — hemispheric ambient + key directional + Penthouse spot
    const hemi = new BJS.HemisphericLight('n3dHemi',
      new BJS.Vector3(0, 1, 0), scene);
    hemi.intensity = 0.55;
    hemi.groundColor = new BJS.Color3(0.06, 0.08, 0.14);
    hemi.diffuse = new BJS.Color3(0.55, 0.70, 0.95);

    const key = new BJS.DirectionalLight('n3dKey',
      new BJS.Vector3(-0.6, -0.5, 0.4), scene);
    key.intensity = 0.85;
    key.diffuse = new BJS.Color3(1.0, 0.95, 0.85);
    key.specular = new BJS.Color3(0.6, 0.65, 0.85);

    const rim = new BJS.DirectionalLight('n3dRim',
      new BJS.Vector3(0.55, -0.2, -0.6), scene);
    rim.intensity = 0.40;
    rim.diffuse = new BJS.Color3(0.40, 0.65, 1.0);

    // Glow layer for emissive materials
    const glow = new BJS.GlowLayer('n3dGlow', scene, {
      mainTextureSamples: 2,
      blurKernelSize: 32,
    });
    glow.intensity = 0.95;

    // Camera
    const cam = window.NEXT3D_CAMERA.build(scene, canvas, BJS);

    // Default rendering pipeline — restrained: just FXAA + a tiny bloom on
    // the bright spires + edge sharpen. No tonemap (it washed out the
    // emissive floors that ARE the data viz).
    try {
      const pipeline = new BJS.DefaultRenderingPipeline(
        'n3dPipeline', true, scene, [cam]);
      pipeline.samples = 2;
      pipeline.fxaaEnabled = true;
      pipeline.bloomEnabled = true;
      pipeline.bloomThreshold = 0.92;
      pipeline.bloomWeight = 0.22;
      pipeline.bloomKernel = 48;
      pipeline.bloomScale = 0.45;
      pipeline.imageProcessingEnabled = true;
      pipeline.imageProcessing.toneMappingEnabled = false;
      pipeline.imageProcessing.contrast = 1.03;
      pipeline.imageProcessing.exposure = 0.95;
      pipeline.imageProcessing.vignetteEnabled = true;
      pipeline.imageProcessing.vignetteWeight = 1.2;
      pipeline.imageProcessing.vignetteCameraFov = 0.30;
      pipeline.sharpenEnabled = true;
      pipeline.sharpen.edgeAmount = 0.20;
    } catch (e) {
      // older Babylon builds may not have DefaultRenderingPipeline; ignore
    }
    // Restrain the glow so emissive doesn't smear into the bloom
    glow.intensity = 0.55;

    // Tower
    const towerBuilt = window.NEXT3D_TOWER.build(scene, BJS, initialFloors || []);

    // Lifts
    const liftsBuilt = window.NEXT3D_LIFTS.build(scene, BJS, towerBuilt.geometry);

    // Workers
    const workersBuilt = window.NEXT3D_WORKERS.build(
      scene, BJS, towerBuilt.meshes, towerBuilt.geometry);

    // OpenClaw
    const ocBuilt = window.NEXT3D_OPENCLAW.build(scene, BJS, towerBuilt.geometry);

    // Floors (selection / roster / halo / camera focus)
    const floorsBuilt = window.NEXT3D_FLOORS.build(
      scene, BJS, cam, towerBuilt.meshes, towerBuilt.geometry,
      function onFloorChange(num) {
        if (window.NEXT3D_APP) window.NEXT3D_APP.onSelectionChanged(num);
      });

    // Render loop with per-frame animation hooks
    engine.runRenderLoop(function () {
      const t = performance.now();
      liftsBuilt.tick();
      ocBuilt.tick(t);
      workersBuilt.tick(t);
      scene.render();
    });
    window.addEventListener('resize', function () { engine.resize(); });

    // Tooltip handling
    const tipEl = document.getElementById('n3dTip');
    function showTip(text, ev) {
      if (!tipEl) return;
      tipEl.textContent = text;
      tipEl.style.left = (ev.clientX + 14) + 'px';
      tipEl.style.top = (ev.clientY + 14) + 'px';
      tipEl.hidden = false;
    }
    function hideTip() { if (tipEl) tipEl.hidden = true; }
    canvas.addEventListener('pointermove', function (ev) {
      const pick = scene.pick(scene.pointerX, scene.pointerY);
      if (pick && pick.hit && pick.pickedMesh && pick.pickedMesh.metadata) {
        const m = pick.pickedMesh.metadata;
        let txt = null;
        if (m.kind === 'floor') txt = 'Floor ' + m.number + ' · ' + m.name;
        else if (m.kind === 'lift') txt = (m.lift_id || ('lift ' + m.shaft_idx)) +
          ' · current floor ' + (m.current_floor || '—') + ' · ' + (m.status || '');
        else if (m.kind === 'openclaw') txt = 'OpenClaw supervisor (read-only)';
        if (txt) showTip(txt, ev);
        else hideTip();
      } else hideTip();
    });
    canvas.addEventListener('pointerleave', hideTip);

    return {
      ready: true,
      engine: engine, scene: scene, BJS: BJS, camera: cam,
      tower: towerBuilt,
      lifts: liftsBuilt,
      workers: workersBuilt,
      openclaw: ocBuilt,
      floors: floorsBuilt,
      glow: glow,
    };
  }

  window.NEXT3D_SCENE = { build: build, probeWebGL: probeWebGL };
})();
