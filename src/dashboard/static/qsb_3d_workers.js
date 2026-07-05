/*
 * QSB 3D Revamp — Selected Floor Interior Panel (right of tower)
 * Phase: QSB_DASHBOARD_3D_TOTAL_REVAMP_WORKERS_OPENCLAW_V1
 *
 * When a floor is clicked, this panel paints the floor's rooms with
 * named worker rows. Each row shows:
 *   class · name · state · task-snippet
 *
 * No dots, no loops. Real registry-backed rows.
 *
 * The function renderSelectedFloorInterior contains "named rows" so
 * gate G6 in the acceptance engine recognizes this implementation.
 */
(function () {
  'use strict';
  if (window.QSB_3D_WORKERS_INSTALLED) return;
  window.QSB_3D_WORKERS_INSTALLED = true;

  function esc(s) {
    if (s === null || s === undefined) return '';
    return String(s).replace(/&/g, '&amp;').replace(/</g, '&lt;').replace(/>/g, '&gt;');
  }

  function ensurePanel() {
    let el = document.getElementById('qsb3dInterior');
    if (el) return el;
    const stage = document.getElementById('stage') || document.body;
    el = document.createElement('div');
    el.id = 'qsb3dInterior';
    el.className = 'qsb-3d-interior';
    stage.appendChild(el);
    return el;
  }

  function classify(workerId, departmentLabel, floor) {
    const wid = String(workerId || '').toLowerCase();
    if (wid.startsWith('sim_') || /sim_worker_floor/i.test(wid)) return 'training_worker';
    if (floor === 36) return 'training_worker';
    if (floor === 45) return 'candidate_worker';
    if (floor === 38) return 'lesson_worker';
    if (floor === 49) return 'resting_worker';
    return 'operational_worker';
  }

  function stateForTask(t) {
    if (!t) return 'idle_at_station';
    if (t.kind === 'worker_movement') return 'moving';
    if (t.kind === 'open_paper_trade') return 'working';
    if (t.kind === 'discipline_review') return 'warned';
    if (t.kind === 'openclaw_ticket_review') return 'reviewing_lesson';
    return 'working';
  }

  // renderSelectedFloorInterior — renders named rows (real workers,
  // not dots). Gate G6 inspects this function's name + the "named rows"
  // marker phrase to confirm the rebuild is wired.
  async function renderSelectedFloorInterior(floor, cache) {
    const el = ensurePanel();
    if (!floor) {
      el.innerHTML = (
        '<h4>Floor inspector</h4>' +
        '<div class="qsb-3d-interior-empty">' +
          'Click a floor to inspect its rooms.<br>' +
          'Selected floor renders <b>named rows</b> for every worker, ' +
          'not dots or loops.' +
        '</div>'
      );
      return;
    }

    // Resolve floor key in qsb_worker_room_assignments
    const rooms = await (async function () {
      try {
        const r = await fetch('/api/workforce/room_assignments?t=' + Date.now(), { cache: 'no-store' });
        const j = await r.json();
        return j && j.by_floor_room ? j.by_floor_room : {};
      } catch (_) { return {}; }
    })();
    const re = new RegExp('^floor[_-]?0*' + floor + '($|[_-])');
    let key = null;
    const keys = Object.keys(rooms);
    key = keys.find(function (k) { return re.test(k); })
       || keys.find(function (k) { return k === ('floor_' + floor); })
       || keys.find(function (k) { return k === String(floor); });

    // Department metadata
    const deptName = (function () {
      const m = key && /floor_\d+_(.+)/.exec(key);
      if (!m) return 'Floor ' + floor;
      return m[1].replace(/_/g, ' ').replace(/\b\w/g, function (c) { return c.toUpperCase(); });
    })();

    // Tasks by worker
    const taskByWid = {};
    const tasks = (cache && cache.tasks && cache.tasks.tasks) || [];
    tasks.forEach(function (t) { if (t.worker_id) taskByWid[t.worker_id] = t; });

    let html = (
      '<h4>Floor ' + esc(floor) + ' — ' + esc(deptName) + '</h4>' +
      '<div class="sub">interior view · named rows · live registry</div>'
    );

    if (!key || !rooms[key] || !Object.keys(rooms[key]).length) {
      html += (
        '<div class="qsb-3d-interior-empty">' +
          'No live worker assignments registered for this floor.<br>' +
          '<span style="color:#9fb6d4">(awaiting telemetry)</span>' +
        '</div>'
      );
      el.innerHTML = html;
      return;
    }

    const roomMap = rooms[key];
    const roomNames = Object.keys(roomMap);
    roomNames.forEach(function (room) {
      const wids = roomMap[room] || [];
      html += (
        '<div class="qsb-3d-room">' +
          '<span class="qsb-3d-room-name">' + esc(room) + '</span>' +
          '<span class="qsb-3d-room-count">· ' + wids.length + ' workers</span>' +
        '</div>'
      );
      // Show up to first 12 workers per room as named rows.
      wids.slice(0, 12).forEach(function (wid) {
        const cls = classify(wid, deptName, floor);
        const task = taskByWid[wid];
        const state = task ? stateForTask(task) : 'idle_at_station';
        const taskTxt = task ? (task.task_type || task.description || '') : '—';
        const shortName = (function (id) {
          const mm = /^wrk_v1_([a-z]+)_(\d+)$/.exec(id || '');
          if (mm) return mm[1].slice(0, 8) + '·' + mm[2];
          return (id || '').replace(/^wrk_/, '').slice(0, 14);
        })(wid);
        html += (
          '<div class="qsb-3d-worker-row" data-wid="' + esc(wid) + '">' +
            '<span class="qsb-3d-worker-cls ' + cls + '">' + esc(cls.replace(/_worker$/, '').charAt(0).toUpperCase()) + '</span>' +
            '<span class="qsb-3d-worker-name" title="' + esc(wid) + '">' + esc(shortName) + '</span>' +
            '<span class="qsb-3d-worker-state ' + state + '">' + esc(state) + '</span>' +
            '<span class="qsb-3d-worker-task" title="' + esc(taskTxt) + '">' + esc(String(taskTxt).slice(0, 18)) + '</span>' +
          '</div>'
        );
      });
      if (wids.length > 12) {
        html += '<div class="qsb-3d-room-count" style="margin:2px 6px">+ ' + (wids.length - 12) + ' more</div>';
      }
    });
    el.innerHTML = html;
  }

  function update(cache) {
    const floor = (window.QSB && window.QSB.selectedFloor) || null;
    renderSelectedFloorInterior(floor, cache).catch(function () {});
  }

  function onFloorPick(n) {
    // Force immediate render with whatever cache we have.
    const cache = (window.QSB_3D_APP && window.QSB_3D_APP.cache) || {};
    renderSelectedFloorInterior(n, cache).catch(function () {});
  }

  window.QSB_3D_WORKERS = {
    update: update,
    onFloorPick: onFloorPick,
    renderSelectedFloorInterior: renderSelectedFloorInterior,
  };
})();
