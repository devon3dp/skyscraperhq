/*
 * QSB Next3D — Camera + Orbit Controls
 * Phase: QSB_NEXTGEN_3D_DASHBOARD_GREENFIELD_REBUILD_V1
 */
(function () {
  'use strict';

  function buildCamera(scene, canvas, BJS) {
    // ArcRotateCamera lets the user orbit, pan, and wheel-zoom.
    const cam = new BJS.ArcRotateCamera(
      'n3dCam',
      Math.PI * 1.45,   // alpha (yaw)
      Math.PI * 0.42,   // beta (pitch — slight above horizon)
      72,               // radius
      new BJS.Vector3(0, 18, 0),  // target — about half tower height
      scene
    );
    cam.attachControl(canvas, true);
    cam.lowerRadiusLimit = 22;
    cam.upperRadiusLimit = 180;
    cam.lowerBetaLimit = 0.20;
    cam.upperBetaLimit = Math.PI * 0.62;
    cam.wheelDeltaPercentage = 0.012;
    cam.angularSensibilityX = 1500;
    cam.angularSensibilityY = 1500;
    cam.panningSensibility = 90;
    cam.useAutoRotationBehavior = true;
    if (cam.autoRotationBehavior) {
      cam.autoRotationBehavior.idleRotationSpeed = 0.10;
      cam.autoRotationBehavior.idleRotationWaitTime = 4000;
      cam.autoRotationBehavior.idleRotationSpinupTime = 1800;
    }
    cam.inertia = 0.82;
    cam.minZ = 0.1;
    cam.maxZ = 600;

    // Smooth focus on a target Y (used when a floor is selected)
    cam.focusOnFloor = function (floorY) {
      const start = cam.target.clone();
      const end = new BJS.Vector3(0, floorY, 0);
      let t = 0;
      const dur = 25;  // frames
      scene.onBeforeRenderObservable.addOnce(function tick() {
        function step() {
          t++;
          const k = Math.min(1, t / dur);
          // Ease-out
          const e = 1 - Math.pow(1 - k, 3);
          cam.target = BJS.Vector3.Lerp(start, end, e);
          if (k < 1) scene.onBeforeRenderObservable.addOnce(step);
        }
        step();
      });
    };

    cam.resetView = function () {
      cam.alpha = Math.PI * 1.45;
      cam.beta = Math.PI * 0.42;
      cam.radius = 72;
      cam.target = new BJS.Vector3(0, 18, 0);
    };

    return cam;
  }

  window.NEXT3D_CAMERA = { build: buildCamera };
})();
