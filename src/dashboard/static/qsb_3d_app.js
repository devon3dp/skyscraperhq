/*
 * QSB Dashboard 3D Revamp — App Entry
 * Phase: QSB_DASHBOARD_3D_TOTAL_REVAMP_WORKERS_OPENCLAW_V1
 *
 * Orchestrates the V1 revamp overlay set. Boots:
 *   - qsb_3d_telemetry.js  (top-left truth panel)
 *   - qsb_3d_floors.js     (per-floor activity badges + left rail)
 *   - qsb_3d_workers.js    (right-side floor interior panel)
 *   - qsb_3d_openclaw.js   (bottom-right supervisor card)
 *
 * The existing SVG/Babylon renderer remains intact; this layer adds the
 * cockpit chrome the operator perceives as the "rebuild."
 */
(function () {
  'use strict';
  if (window.QSB_3D_APP_INSTALLED) return;
  window.QSB_3D_APP_INSTALLED = true;

  const POLL_MS = 6000;
  let cache = { scene: null, truth: null, oc: null, tasks: null, route: null };

  async function fetchJSON(url) {
    try {
      const r = await fetch(url + (url.indexOf('?') === -1 ? '?' : '&') + 't=' + Date.now(),
                             { cache: 'no-store' });
      if (!r.ok) return null;
      return await r.json();
    } catch (_) { return null; }
  }

  async function pollAll() {
    const [scene, truth, oc, tasks, route] = await Promise.all([
      fetchJSON('/api/rebuild/visible_scene_state'),
      fetchJSON('/api/worker_truth/contract'),
      fetchJSON('/api/openclaw/tickets'),
      fetchJSON('/api/tasks/active'),
      fetchJSON('/api/openclaw/route'),
    ]);
    const live = await fetchJSON('/api/dashboard/live_telemetry');
    const sceneState = await fetchJSON('/api/dashboard/scene_state');
    cache.scene = sceneState || scene;
    cache.truth = truth;
    cache.oc = oc;
    cache.tasks = tasks;
    cache.route = route;
    cache.live = live;

    // Drive each panel
    if (window.QSB_3D_TELEMETRY) window.QSB_3D_TELEMETRY.update(cache);
    if (window.QSB_3D_FLOORS)    window.QSB_3D_FLOORS.update(cache);
    if (window.QSB_3D_OPENCLAW)  window.QSB_3D_OPENCLAW.update(cache);
    if (window.QSB_3D_WORKERS)   window.QSB_3D_WORKERS.update(cache);
  }

  function attach() {
    // First poll, then heartbeat.
    setTimeout(function () { pollAll().catch(function () {}); }, 1200);
    setInterval(function () { pollAll().catch(function () {}); }, POLL_MS);

    // Refresh on floor pick.
    window.addEventListener('qsb:pick', function (e) {
      const m = e && e.detail;
      if (m && m.kind === 'floor') {
        if (window.QSB_3D_WORKERS) window.QSB_3D_WORKERS.onFloorPick(m.number);
        if (window.QSB_3D_FLOORS)  window.QSB_3D_FLOORS.onFloorPick(m.number);
      }
    });
  }

  if (document.readyState === 'loading') {
    document.addEventListener('DOMContentLoaded', attach);
  } else {
    attach();
  }
  window.QSB_3D_APP = { refresh: pollAll, cache: cache };
})();
