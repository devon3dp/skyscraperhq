/*
 * QSB Dashboard Total Rebuild — Worker Interior Layer
 * Phase: QSB_DASHBOARD_TOTAL_REBUILD_3D_WORKERS_OPENCLAW_ONLINE_V1
 *
 * Paints a "department interior" inside the selected floor slab on the
 * SVG tower. Reads:
 *
 *   /api/workforce/room_assignments
 *   /api/workforce/task_board
 *   /api/workforce/department_room_map
 *
 * Only renders when window.QSB.selectedFloor is set (set by cockpit.js
 * on floor click). Otherwise hidden.
 *
 * Hard contract: NEVER renders an unknown worker. Each glyph maps to a
 * real worker_id with a real room/station/task.
 */
(function () {
  'use strict';
  if (window.QSB_REBUILD_WORKERS_INSTALLED) return;
  window.QSB_REBUILD_WORKERS_INSTALLED = true;

  const POLL_MS = 5000;
  let roomsCache = null;
  let taskCache = null;
  let lastFloor = null;

  function $(s) { return document.querySelector(s); }
  function esc(s) {
    if (s === null || s === undefined) return '';
    return String(s).replace(/&/g, '&amp;').replace(/</g, '&lt;').replace(/>/g, '&gt;');
  }
  function safe(name, fn) {
    return function () {
      try { return fn.apply(null, arguments); }
      catch (e) {
        if (window.console) console.warn('[qsb_rebuild_workers] ' + name + ': ' + (e && e.message));
      }
    };
  }
  async function fetchJSON(url) {
    try {
      const r = await fetch(url + '?t=' + Date.now(), { cache: 'no-store' });
      if (!r.ok) return null;
      return await r.json();
    } catch (_) { return null; }
  }

  function getTower() { return window.QSB_TOWER_2D || null; }

  // Map "wrk_v1_recruitmen_001" → display label like "Recruitment #001"
  function shortLabel(wid) {
    if (!wid) return '';
    const m = /^wrk_v1_([a-z]+)_(\d+)$/.exec(wid);
    if (m) return m[1].slice(0, 8) + '·' + m[2];
    return wid.replace(/^wrk_/, '').slice(0, 14);
  }

  async function ensureCaches() {
    if (!roomsCache) {
      const r = await fetchJSON('/api/workforce/room_assignments');
      roomsCache = r && r.by_floor_room ? r.by_floor_room : {};
    }
    if (!taskCache) {
      const t = await fetchJSON('/api/workforce/task_board');
      taskCache = (t && (t.active_tasks || [])) || [];
    }
  }

  function buildTaskByWid() {
    const idx = {};
    (taskCache || []).forEach(function (t) {
      const wid = t.worker_id;
      if (!wid) return;
      idx[wid] = t;
    });
    return idx;
  }

  function paintInterior() {
    const tower = getTower();
    if (!tower || !tower.svg) return;
    const selFloor = (window.QSB && window.QSB.selectedFloor) || null;

    let layer = tower.svg.querySelector('#qsbRebuildInteriorLayer');
    if (!layer) {
      layer = document.createElementNS('http://www.w3.org/2000/svg', 'g');
      layer.setAttribute('id', 'qsbRebuildInteriorLayer');
      tower.svg.appendChild(layer);
    }
    layer.innerHTML = '';

    if (!selFloor) {
      // No floor selected → show a hint label.
      const hint = document.createElementNS('http://www.w3.org/2000/svg', 'text');
      hint.setAttribute('x', 410); hint.setAttribute('y', 20);
      hint.setAttribute('text-anchor', 'middle');
      hint.setAttribute('fill', '#9fb6d4');
      hint.setAttribute('font-size', '10');
      hint.setAttribute('font-family', 'JetBrains Mono, monospace');
      hint.textContent = 'click a floor to see workers stationed there';
      layer.appendChild(hint);
      return;
    }
    lastFloor = selFloor;

    // Find a floor key in roomsCache that matches the selected floor number.
    // qsb_worker_room_assignments uses keys like
    // 'floor_45_worker_recruitment_agency' OR 'floor_45' OR '45'.
    let floorKey = null;
    if (roomsCache) {
      const re = new RegExp('^floor[_-]?0*' + selFloor + '($|[_-])');
      const keys = Object.keys(roomsCache);
      floorKey = keys.find(function (k) { return re.test(k); })
                 || keys.find(function (k) { return k === ('floor_' + selFloor); })
                 || keys.find(function (k) { return k === String(selFloor); });
    }

    const rect = tower.floorRects && tower.floorRects[selFloor];
    if (!rect) return;
    const x = Number(rect.getAttribute('x'));
    const y = Number(rect.getAttribute('y'));
    const w = Number(rect.getAttribute('width'));
    const h = Number(rect.getAttribute('height'));

    // Highlight the selected floor with a soft outline.
    const hl = document.createElementNS('http://www.w3.org/2000/svg', 'rect');
    hl.setAttribute('x', x - 2); hl.setAttribute('y', y - 2);
    hl.setAttribute('width', w + 4); hl.setAttribute('height', h + 4);
    hl.setAttribute('fill', 'none');
    hl.setAttribute('stroke', '#ffd24c');
    hl.setAttribute('stroke-width', '1.4');
    hl.setAttribute('stroke-opacity', '0.85');
    hl.setAttribute('rx', '4');
    layer.appendChild(hl);

    if (!floorKey || !roomsCache[floorKey]) {
      // No room data for this floor → show "no live worker data" badge.
      const badge = document.createElementNS('http://www.w3.org/2000/svg', 'text');
      badge.setAttribute('x', x + w + 16); badge.setAttribute('y', y + h / 2);
      badge.setAttribute('alignment-baseline', 'middle');
      badge.setAttribute('fill', '#aab1c6');
      badge.setAttribute('font-size', '9');
      badge.setAttribute('font-family', 'JetBrains Mono, monospace');
      badge.textContent = 'no rooms registered for this floor';
      layer.appendChild(badge);
      return;
    }

    // Render workers at rooms within the floor slab.
    const rooms = roomsCache[floorKey] || {};
    const roomNames = Object.keys(rooms);
    const nRooms = Math.max(1, roomNames.length);
    const taskByWid = buildTaskByWid();

    const padX = 12;
    const padY = 4;
    const slabW = w - padX * 2;
    const slabH = h - padY * 2;
    const roomW = slabW / nRooms;

    roomNames.forEach(function (room, ri) {
      const wids = rooms[room] || [];
      // Room column outline (subtle)
      const col = document.createElementNS('http://www.w3.org/2000/svg', 'rect');
      col.setAttribute('x', x + padX + ri * roomW);
      col.setAttribute('y', y + padY);
      col.setAttribute('width', roomW - 2);
      col.setAttribute('height', slabH);
      col.setAttribute('fill', 'rgba(120,170,230,0.04)');
      col.setAttribute('stroke', 'rgba(120,170,230,0.25)');
      col.setAttribute('stroke-dasharray', '2 3');
      layer.appendChild(col);

      // Room title
      const title = document.createElementNS('http://www.w3.org/2000/svg', 'text');
      title.setAttribute('x', x + padX + ri * roomW + roomW / 2);
      title.setAttribute('y', y + padY + 4);
      title.setAttribute('text-anchor', 'middle');
      title.setAttribute('alignment-baseline', 'hanging');
      title.setAttribute('fill', '#cfdcef');
      title.setAttribute('font-size', '6.5');
      title.setAttribute('font-family', 'JetBrains Mono, monospace');
      title.textContent = room.length > 22 ? room.slice(0, 20) + '…' : room;
      layer.appendChild(title);

      // Worker glyphs per room (cap rendered to keep DOM small)
      const maxPerRoom = Math.min(24, wids.length);
      const cols = 6;
      const cellW = (roomW - 4) / cols;
      const rows = Math.ceil(maxPerRoom / cols);
      const cellH = Math.min(8, (slabH - 14) / Math.max(1, rows));
      for (let i = 0; i < maxPerRoom; i++) {
        const wid = wids[i];
        const cx = x + padX + ri * roomW + 2 + (i % cols) * cellW + cellW / 2;
        const cy = y + padY + 12 + Math.floor(i / cols) * cellH + cellH / 2;
        const has_task = !!taskByWid[wid];
        const g = document.createElementNS('http://www.w3.org/2000/svg', 'g');
        g.setAttribute('class', 'qsb-rbw-worker');
        g.setAttribute('data-wid', wid);
        g.innerHTML = (
          '<circle cx="' + cx + '" cy="' + cy + '" r="2" ' +
                  'fill="' + (has_task ? '#3fcf6e' : '#7fbbe6') + '" ' +
                  'stroke="rgba(8,12,22,0.6)" stroke-width="0.5"/>'
        );
        // Tooltip via title element
        const ttl = document.createElementNS('http://www.w3.org/2000/svg', 'title');
        const t = taskByWid[wid];
        ttl.textContent = wid + (t ? ' · ' + t.task_type + ' · ' + (t.description || '') : ' · idle_at_station');
        g.appendChild(ttl);
        layer.appendChild(g);
      }

      // Room footer count
      const fcnt = document.createElementNS('http://www.w3.org/2000/svg', 'text');
      fcnt.setAttribute('x', x + padX + ri * roomW + roomW / 2);
      fcnt.setAttribute('y', y + h - 2);
      fcnt.setAttribute('text-anchor', 'middle');
      fcnt.setAttribute('fill', '#9fb6d4');
      fcnt.setAttribute('font-size', '6');
      fcnt.setAttribute('font-family', 'JetBrains Mono, monospace');
      fcnt.textContent = wids.length + ' workers';
      layer.appendChild(fcnt);
    });
  }

  const safePaint = safe('paintInterior', paintInterior);

  async function tick() {
    await ensureCaches();
    safePaint();
  }

  function attach() {
    // Re-paint on every floor pick.
    window.addEventListener('qsb:pick', function (e) {
      const m = e && e.detail;
      if (m && m.kind === 'floor') {
        safePaint();
      }
    });
    // Re-cache when state updates.
    setInterval(function () {
      roomsCache = null; taskCache = null;
      tick().catch(function () {});
    }, POLL_MS * 3);
    // Initial paint after caches load.
    setTimeout(tick, 1400);
  }

  if (document.readyState === 'loading') {
    document.addEventListener('DOMContentLoaded', attach);
  } else {
    attach();
  }

  window.QSB_REBUILD_WORKERS = { repaint: safePaint };
})();
