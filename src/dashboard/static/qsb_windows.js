// QSB Tower V1.3 — qsb_windows.js
// Phase: QSB_TOWER_3D_COCKPIT_VISUAL_REFINEMENT_V2
//
// Minimal floating/dockable window manager: draggable title bars,
// closable, resizable. Windows are appended to #windowLayer and stay
// inside the browser viewport. Pure DOM — no framework. Read-only:
// never invokes any API that could enable execution.

(function () {
  'use strict';

  const W = {
    layerEl: null,
    windows: {},        // id -> { el, body, opts }
    zTop: 1000,
  };
  window.QSB_WINDOWS = W;

  function el(id) { return document.getElementById(id); }
  function ensureLayer() {
    if (!W.layerEl) W.layerEl = el('windowLayer') || document.body;
    return W.layerEl;
  }
  function focusWindow(id) {
    const w = W.windows[id];
    if (!w) return;
    W.zTop += 1;
    w.el.style.zIndex = W.zTop;
    for (const k of Object.keys(W.windows)) W.windows[k].el.classList.remove('active');
    w.el.classList.add('active');
  }

  function makeDraggable(win, handle) {
    let startX = 0, startY = 0, baseX = 0, baseY = 0, dragging = false;
    handle.addEventListener('mousedown', (e) => {
      if (e.target.tagName === 'BUTTON') return;
      dragging = true;
      startX = e.clientX; startY = e.clientY;
      const r = win.getBoundingClientRect();
      baseX = r.left; baseY = r.top;
      focusWindow(win.dataset.qid);
      e.preventDefault();
    });
    document.addEventListener('mousemove', (e) => {
      if (!dragging) return;
      const dx = e.clientX - startX;
      const dy = e.clientY - startY;
      const nx = Math.max(0, Math.min(window.innerWidth - 40,  baseX + dx));
      const ny = Math.max(0, Math.min(window.innerHeight - 40, baseY + dy));
      win.style.left = nx + 'px';
      win.style.top  = ny + 'px';
    });
    document.addEventListener('mouseup', () => { dragging = false; });
  }

  function makeResizable(win, handle, edge) {
    // edge: one of 'br' (default corner), 'r', 'b', 'l', 't'
    edge = edge || 'br';
    let startX = 0, startY = 0, baseW = 0, baseH = 0, baseL = 0, baseT = 0, resizing = false;
    handle.addEventListener('mousedown', (e) => {
      resizing = true;
      startX = e.clientX; startY = e.clientY;
      const r = win.getBoundingClientRect();
      baseW = r.width; baseH = r.height; baseL = r.left; baseT = r.top;
      e.preventDefault(); e.stopPropagation();
    });
    document.addEventListener('mousemove', (e) => {
      if (!resizing) return;
      const dx = e.clientX - startX;
      const dy = e.clientY - startY;
      let nw = baseW, nh = baseH, nl = baseL, nt = baseT;
      if (edge.includes('r')) nw = Math.max(260, Math.min(window.innerWidth - 20, baseW + dx));
      if (edge.includes('b')) nh = Math.max(140, Math.min(window.innerHeight - 60, baseH + dy));
      if (edge.includes('l')) {
        nw = Math.max(260, Math.min(window.innerWidth - 20, baseW - dx));
        nl = baseL + (baseW - nw);
      }
      if (edge.includes('t')) {
        nh = Math.max(140, Math.min(window.innerHeight - 60, baseH - dy));
        nt = baseT + (baseH - nh);
      }
      win.style.width  = nw + 'px';
      win.style.height = nh + 'px';
      win.style.left   = nl + 'px';
      win.style.top    = nt + 'px';
    });
    document.addEventListener('mouseup', () => { resizing = false; });
  }

  // V17 — toggle maximize. Stores previous geometry on the win.
  function toggleMaximize(win) {
    if (win.dataset.maximized === '1') {
      win.style.left   = win.dataset.prevL || '80px';
      win.style.top    = win.dataset.prevT || '90px';
      win.style.width  = win.dataset.prevW || '380px';
      win.style.height = win.dataset.prevH || '320px';
      win.dataset.maximized = '0';
    } else {
      win.dataset.prevL = win.style.left;
      win.dataset.prevT = win.style.top;
      win.dataset.prevW = win.style.width;
      win.dataset.prevH = win.style.height;
      win.style.left   = '8px';
      win.style.top    = '40px';
      win.style.width  = (window.innerWidth  - 16) + 'px';
      win.style.height = (window.innerHeight - 50) + 'px';
      win.dataset.maximized = '1';
    }
  }

  // V17 — detach: open a new browser window with a snapshot of this window's
  // content. The detached copy is static (no live updates) but readable
  // and printable. The original stays open.
  function detachWindow(id, opts, body) {
    const popup = window.open('', 'qsb_detach_' + id,
      'width=' + (body.parentElement.offsetWidth + 30) +
      ',height=' + (body.parentElement.offsetHeight + 60) +
      ',scrollbars=yes,resizable=yes');
    if (!popup) {
      alert('Popup blocked. Allow popups for 127.0.0.1:8765 to detach windows.');
      return;
    }
    const title = (opts && opts.title) || 'QSB Window';
    popup.document.write(`<!doctype html><html><head><title>${title} (detached)</title>
      <style>
        body { background:#0a0f1c; color:#e6f0ff; font-family:system-ui,sans-serif; margin:0; padding:14px; }
        h1 { font-size:14px; color:#9ac; margin:0 0 12px 0; padding-bottom:8px; border-bottom:1px solid #234; }
        h1 small { color:#789; font-weight:normal; margin-left:8px; }
        .kv { display:flex; gap:12px; padding:3px 0; font-size:12px; }
        .kv .k { color:#789; min-width:90px; }
        .kv .v { color:#e6f0ff; }
        .ok { color:#4ade80; }
        .chat-log, pre { background:rgba(8,16,28,.7); padding:8px; border-radius:6px; max-height:none !important; }
        button, input { background:#1a2030; color:#e6f0ff; border:1px solid #345; border-radius:4px; padding:4px 8px; }
      </style></head><body>
      <h1>${title} <small>· detached snapshot · ${new Date().toLocaleTimeString()}</small></h1>
      <div id="content"></div>
    </body></html>`);
    popup.document.close();
    const content = popup.document.getElementById('content');
    content.innerHTML = body.innerHTML;
  }

  // Create or re-focus a window
  W.open = function (id, opts) {
    ensureLayer();
    if (W.windows[id]) {
      const w = W.windows[id];
      // Re-render body content if a render fn is supplied
      if (opts && typeof opts.render === 'function') opts.render(w.body);
      if (opts && opts.title) w.el.querySelector('.qwin-title').textContent = opts.title;
      focusWindow(id);
      return w;
    }
    const layer = W.layerEl;
    const win = document.createElement('div');
    win.className = 'qwin';
    win.dataset.qid = id;
    // Stagger position so windows don't pile up
    const n = Object.keys(W.windows).length;
    const x = 80 + (n % 6) * 36;
    const y = 90 + (n % 6) * 30;
    const w = (opts && opts.width)  || 380;
    const h = (opts && opts.height) || 320;
    win.style.left  = x + 'px';
    win.style.top   = y + 'px';
    win.style.width = w + 'px';
    win.style.height = h + 'px';

    const hdr = document.createElement('div');
    hdr.className = 'qwin-hdr';
    const title = document.createElement('span');
    title.className = 'qwin-title';
    title.textContent = (opts && opts.title) || 'Window';
    const actions = document.createElement('span');
    actions.className = 'qwin-actions';

    // V17 — detach button: pops the snapshot into a new browser window
    const detachBtn = document.createElement('button');
    detachBtn.textContent = '⛶';
    detachBtn.title = 'Detach to new browser window';
    detachBtn.addEventListener('click', () => detachWindow(id, opts, body));
    actions.appendChild(detachBtn);

    // V17 — maximize toggle
    const maxBtn = document.createElement('button');
    maxBtn.textContent = '□';
    maxBtn.title = 'Maximize / restore';
    maxBtn.addEventListener('click', () => toggleMaximize(win));
    actions.appendChild(maxBtn);

    const closeBtn = document.createElement('button');
    closeBtn.textContent = '×';
    closeBtn.title = 'Close';
    closeBtn.addEventListener('click', () => W.close(id));
    actions.appendChild(closeBtn);
    hdr.appendChild(title);
    hdr.appendChild(actions);

    const body = document.createElement('div');
    body.className = 'qwin-body';

    // V17 — edge resize handles (in addition to corner)
    const resizeR = document.createElement('div');
    resizeR.className = 'qwin-edge-r';
    resizeR.style.cssText = 'position:absolute;right:0;top:24px;bottom:14px;width:6px;cursor:ew-resize;z-index:5;';
    const resizeB = document.createElement('div');
    resizeB.className = 'qwin-edge-b';
    resizeB.style.cssText = 'position:absolute;left:14px;right:14px;bottom:0;height:6px;cursor:ns-resize;z-index:5;';
    const resizeL = document.createElement('div');
    resizeL.className = 'qwin-edge-l';
    resizeL.style.cssText = 'position:absolute;left:0;top:24px;bottom:14px;width:6px;cursor:ew-resize;z-index:5;';
    const resizeT = document.createElement('div');
    resizeT.className = 'qwin-edge-t';
    resizeT.style.cssText = 'position:absolute;left:14px;right:14px;top:0;height:6px;cursor:ns-resize;z-index:5;';

    const resize = document.createElement('div');
    resize.className = 'qwin-resize';

    win.appendChild(hdr);
    win.appendChild(body);
    win.appendChild(resize);
    win.appendChild(resizeR);
    win.appendChild(resizeB);
    win.appendChild(resizeL);
    win.appendChild(resizeT);
    layer.appendChild(win);

    makeDraggable(win, hdr);
    makeResizable(win, resize, 'br');
    makeResizable(win, resizeR, 'r');
    makeResizable(win, resizeB, 'b');
    makeResizable(win, resizeL, 'l');
    makeResizable(win, resizeT, 't');

    // V17 — double-click header maximizes
    hdr.addEventListener('dblclick', () => toggleMaximize(win));

    W.windows[id] = { el: win, body, opts: opts || {} };
    focusWindow(id);

    if (opts && typeof opts.render === 'function') {
      opts.render(body);
    }
    return W.windows[id];
  };

  W.close = function (id) {
    const w = W.windows[id];
    if (!w) return;
    w.el.parentNode && w.el.parentNode.removeChild(w.el);
    delete W.windows[id];
  };

  W.exists = function (id) { return !!W.windows[id]; };

  W.update = function (id, renderFn) {
    const w = W.windows[id];
    if (!w) return false;
    if (typeof renderFn === 'function') renderFn(w.body);
    return true;
  };
})();
