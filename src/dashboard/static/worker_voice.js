// QSB Tower V1.5 — Worker / Floor / Colonel voice narration + correction panel.
// Browser-only SpeechSynthesis. No external providers. Add-on; never replaces cockpit.js logic.

(function () {
  'use strict';

  const STATE = {
    // V17 — default voiceOn TRUE unless explicitly disabled
    voiceOn:        localStorage.getItem('qsb.v15.voiceOn') !== '0',
    autoSpeak:      localStorage.getItem('qsb.v15.autoSpeak') !== '0',
    speed:          parseFloat(localStorage.getItem('qsb.v15.speed') || '1.0'),
    pitch:          parseFloat(localStorage.getItem('qsb.v15.pitch') || '1.0'),
    voiceIndex:     parseInt(localStorage.getItem('qsb.v15.voiceIndex') || '0', 10),
    lastSelectedId: null,
  };

  function ssAvailable() { return typeof window.speechSynthesis !== 'undefined'; }

  function fetchJSON(path) {
    return fetch(path, { cache: 'no-store' }).then((r) => r.json()).catch(() => null);
  }

  function postJSON(path, body) {
    return fetch(path, {
      method:  'POST',
      headers: { 'Content-Type': 'application/json' },
      body:    JSON.stringify(body || {}),
    }).then((r) => r.json()).catch(() => null);
  }

  function speakText(text) {
    if (!STATE.voiceOn) { return false; }
    // Delegate to QSB_SPEECH (English-first, voice-preference aware).
    if (window.QSB_SPEECH) {
      return window.QSB_SPEECH.speak(text);
    }
    // Hard fallback if QSB_SPEECH hasn't loaded yet — force lang=en-GB.
    if (!ssAvailable()) return false;
    try {
      window.speechSynthesis.cancel();
      const u = new SpeechSynthesisUtterance(String(text || '').slice(0, 1200));
      u.rate = STATE.speed; u.pitch = STATE.pitch; u.lang = 'en-GB';
      const voices = window.speechSynthesis.getVoices() || [];
      const en = voices.find(function (v) { return v.lang && v.lang.toLowerCase().startsWith('en'); });
      if (en) u.voice = en;
      window.speechSynthesis.speak(u);
      return true;
    } catch (e) { return false; }
  }

  // ──────── Worker click narration ────────
  async function narrateWorker(workerId) {
    if (!workerId) return null;
    STATE.lastSelectedId = workerId;
    const data = await fetchJSON('/api/workers/narration?id=' + encodeURIComponent(workerId));
    if (!data || !data.ok) {
      console.warn('[QSBv15] worker_narration failed for', workerId, data);
      return data;
    }
    postJSON('/api/workers/select', { id: workerId });
    showWorkerCard(data);
    if (STATE.autoSpeak) speakText(data.spoken_text);
    return data;
  }

  function showWorkerCard(data) {
    let card = document.getElementById('qsbV15WorkerCard');
    if (!card) {
      card = document.createElement('div');
      card.id = 'qsbV15WorkerCard';
      card.style.cssText = [
        'position:fixed', 'right:20px', 'bottom:200px', 'z-index:9000',
        'background:rgba(8,18,32,0.94)', 'color:#cde6ff',
        'border:1px solid #2a64a0', 'border-radius:8px',
        'padding:12px 14px', 'width:340px', 'max-height:60vh',
        'overflow:auto', 'font:13px/1.35 system-ui, sans-serif',
        'box-shadow:0 6px 20px rgba(0,0,0,.45)',
      ].join(';');
      document.body.appendChild(card);
    }
    const v = data.voice_summary || {};
    card.innerHTML = ''
      + '<div style="display:flex;justify-content:space-between;align-items:center;'
      + 'border-bottom:1px solid #1f3e64;margin-bottom:8px;padding-bottom:6px">'
      +   '<strong style="color:#9ccff7">' + escapeHtml(data.display_name || data.worker_id) + '</strong>'
      +   '<span style="cursor:pointer;color:#8aa9c6" id="qsbV15WCclose">✕</span>'
      + '</div>'
      + '<div style="font-size:11px;color:#7fa6cc;margin-bottom:8px">'
      +   escapeHtml(data.badge_id || '—') + '</div>'
      + row('Job',     v.job)
      + row('Task',    v.current_task)
      + row('Route',   v.route)
      + row('Manager', v.manager)
      + row('Allowed', v.access)
      + row('Forbidden', v.forbidden)
      + '<div style="margin-top:10px;display:flex;gap:6px;flex-wrap:wrap">'
      + btn('🔊 Speak Again',  'qsbV15WCSpeak')
      + btn('🎙 Speak Floor',  'qsbV15WCSpeakFloor')
      + btn('🏠 Home Floor',   'qsbV15WCHome')
      + btn('🎯 Target Floor', 'qsbV15WCTarget')
      + '</div>';
    document.getElementById('qsbV15WCclose').onclick = () => card.remove();
    document.getElementById('qsbV15WCSpeak').onclick = () => speakText(data.spoken_text);
    document.getElementById('qsbV15WCSpeakFloor').onclick = () =>
      narrateFloor((data.voice_summary || {}).home_floor || 'floor_41');
    const homeBtn = document.getElementById('qsbV15WCHome');
    homeBtn.onclick = () => openFloorIfAvailable((data.voice_summary || {}).home_floor);
    const targetBtn = document.getElementById('qsbV15WCTarget');
    targetBtn.onclick = () => openFloorIfAvailable((data.voice_summary || {}).route);
  }

  function row(label, value) {
    if (!value) return '';
    return '<div style="display:flex;gap:6px;margin:2px 0">'
      + '<span style="color:#7fa6cc;min-width:78px">' + escapeHtml(label) + '</span>'
      + '<span style="color:#cde6ff;flex:1">' + escapeHtml(value) + '</span></div>';
  }
  function btn(label, id) {
    return '<button id="' + id + '" style="background:#1f3e64;border:1px solid #2a64a0;'
      + 'color:#cde6ff;border-radius:4px;padding:4px 8px;font-size:12px;cursor:pointer">'
      + escapeHtml(label) + '</button>';
  }
  function escapeHtml(s) {
    return String(s == null ? '' : s).replace(/[&<>"']/g, (c) => ({
      '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;',
    }[c]));
  }

  // ──────── Floor narration ────────
  async function narrateFloor(floorRef) {
    let floor = floorRef;
    if (typeof floor === 'string' && floor.startsWith('floor_')) {
      floor = parseInt(floor.replace('floor_', ''), 10);
    }
    if (!Number.isFinite(floor)) return null;
    const data = await fetchJSON('/api/floors/narration?floor=' + encodeURIComponent(floor));
    if (!data || !data.ok) return data;
    speakText(data.spoken_text);
    return data;
  }

  function openFloorIfAvailable(ref) {
    if (!ref) return;
    if (typeof window.openFloorWindow === 'function') {
      const f = parseInt(String(ref).replace(/[^0-9]/g, ''), 10);
      if (Number.isFinite(f)) window.openFloorWindow(f);
    } else {
      narrateFloor(ref);
    }
  }

  // ──────── Colonel briefing ────────
  async function colonelBriefing() {
    const data = await fetchJSON('/api/colonel/audio_briefing');
    if (data && data.spoken_text) {
      speakText(data.spoken_text);
      showColonelCard(data);
    }
    return data;
  }

  function showColonelCard(data) {
    let c = document.getElementById('qsbV15ColonelCard');
    if (!c) {
      c = document.createElement('div');
      c.id = 'qsbV15ColonelCard';
      c.style.cssText = [
        'position:fixed', 'left:20px', 'bottom:200px', 'z-index:9000',
        'background:rgba(20,12,40,0.95)', 'color:#e7d6ff',
        'border:1px solid #6f4ec0', 'border-radius:8px',
        'padding:12px 14px', 'width:360px', 'max-height:60vh',
        'overflow:auto', 'font:13px/1.4 system-ui, sans-serif',
      ].join(';');
      document.body.appendChild(c);
    }
    c.innerHTML = ''
      + '<div style="display:flex;justify-content:space-between;align-items:center;'
      + 'border-bottom:1px solid #4a338a;margin-bottom:8px;padding-bottom:6px">'
      +   '<strong style="color:#cdb3ff">👑 Colonel Observation</strong>'
      +   '<span style="cursor:pointer;color:#9c87c6" id="qsbV15CCclose">✕</span>'
      + '</div>'
      + '<div style="font-size:12px">' + escapeHtml(data.spoken_text || '') + '</div>'
      + '<div style="margin-top:10px;display:flex;gap:6px;flex-wrap:wrap">'
      +   btn('🔊 Speak Again',          'qsbV15CCSpeak')
      +   btn('🏃 Run Correction Pass',  'qsbV15CCCorr')
      + '</div>';
    document.getElementById('qsbV15CCclose').onclick = () => c.remove();
    document.getElementById('qsbV15CCSpeak').onclick = () => speakText(data.spoken_text);
    document.getElementById('qsbV15CCCorr').onclick  = () => runCorrectionPass();
  }

  // ──────── Correction loop panel ────────
  async function runCorrectionPass() {
    showCorrectionPanel({ loading: true });
    const data = await postJSON('/api/correction/run_once', {});
    showCorrectionPanel(data);
    return data;
  }
  async function runUntilClean() {
    showCorrectionPanel({ loading: true });
    const data = await postJSON('/api/correction/run_until_clean', {});
    showCorrectionPanel(data);
    return data;
  }
  async function refreshCorrectionLatest() {
    const data = await fetchJSON('/api/correction/latest');
    showCorrectionPanel(data);
    return data;
  }

  function showCorrectionPanel(data) {
    let p = document.getElementById('qsbV15CorrectionPanel');
    if (!p) {
      p = document.createElement('div');
      p.id = 'qsbV15CorrectionPanel';
      p.style.cssText = [
        'position:fixed', 'top:60px', 'right:20px', 'z-index:9001',
        'background:rgba(8,28,18,0.95)', 'color:#cffce6',
        'border:1px solid #2e7a52', 'border-radius:8px',
        'padding:12px 14px', 'width:380px', 'max-height:70vh',
        'overflow:auto', 'font:12px/1.4 system-ui, sans-serif',
      ].join(';');
      document.body.appendChild(p);
    }
    if (data && data.loading) {
      p.innerHTML = '<div>Running correction loop…</div>';
      return;
    }
    const d = data || {};
    const remaining = (d.issues_remaining || []).slice(0, 8).map((r) =>
      '<li>' + escapeHtml(r.item || r.title || '?') + ' — ' + escapeHtml(r.severity || '') + '</li>').join('');
    const applied = (d.actions_applied || []).slice(0, 8).map((a) =>
      '<li>' + escapeHtml(a.action || '?') + (a.ok ? ' ✓' : ' ✗') + '</li>').join('');
    p.innerHTML = ''
      + '<div style="display:flex;justify-content:space-between;align-items:center;'
      + 'border-bottom:1px solid #1e5a3a;margin-bottom:8px;padding-bottom:6px">'
      +   '<strong style="color:#9ef0c0">🔧 Correction Loop</strong>'
      +   '<span style="cursor:pointer;color:#8fc8a4" id="qsbV15CorrClose">✕</span>'
      + '</div>'
      + '<div>Before → After: <b>' + (d.issues_before == null ? '—' : d.issues_before)
      + '</b> → <b>' + (d.issues_after == null ? '—' : d.issues_after) + '</b></div>'
      + '<div>Resolved: <b>' + (d.issues_resolved == null ? '—' : d.issues_resolved) + '</b></div>'
      + '<div style="margin-top:8px;color:#9ef0c0">Actions applied</div>'
      + '<ul style="margin:4px 0 8px 18px;color:#cffce6">' + applied + '</ul>'
      + '<div style="color:#f0d29e">Issues remaining</div>'
      + '<ul style="margin:4px 0 8px 18px;color:#f6e2c2">' + remaining + '</ul>'
      + '<div style="display:flex;gap:6px;flex-wrap:wrap">'
      +   btn('🏃 Run Once',         'qsbV15CorrRunOnce')
      +   btn('🔁 Run Until Clean',  'qsbV15CorrRunClean')
      +   btn('🔄 Refresh',          'qsbV15CorrRefresh')
      + '</div>';
    document.getElementById('qsbV15CorrClose').onclick    = () => p.remove();
    document.getElementById('qsbV15CorrRunOnce').onclick  = runCorrectionPass;
    document.getElementById('qsbV15CorrRunClean').onclick = runUntilClean;
    document.getElementById('qsbV15CorrRefresh').onclick  = refreshCorrectionLatest;
  }

  // ──────── Voice control panel (header bar add-on) ────────
  function injectVoicePanel() {
    if (document.getElementById('qsbV15VoiceBar')) return;
    const bar = document.createElement('div');
    bar.id = 'qsbV15VoiceBar';
    bar.style.cssText = [
      'position:fixed', 'top:60px', 'left:50%', 'transform:translateX(-50%)',
      'z-index:8500',
      'background:rgba(10,20,40,0.92)', 'color:#cde6ff',
      'border:1px solid #2a64a0', 'border-radius:8px',
      'padding:6px 10px', 'display:flex', 'gap:6px', 'align-items:center',
      'font:12px/1 system-ui, sans-serif',
    ].join(';');
    bar.innerHTML = ''
      + voiceBtn('🎙 Talk', 'qsbV15Talk')
      + voiceBtn(STATE.voiceOn ? '🔊 Voice ON' : '🔇 Voice OFF', 'qsbV15Toggle')
      + voiceBtn(STATE.autoSpeak ? '⚡ Auto ON' : '⚡ Auto OFF', 'qsbV15Auto')
      + voiceBtn('👑 Colonel', 'qsbV15Col')
      + voiceBtn('🔧 Correction', 'qsbV15Corr')
      + voiceBtn('📋 Not Working', 'qsbV15NW');
    document.body.appendChild(bar);

    document.getElementById('qsbV15Toggle').onclick = () => {
      STATE.voiceOn = !STATE.voiceOn;
      localStorage.setItem('qsb.v15.voiceOn', STATE.voiceOn ? '1' : '0');
      document.getElementById('qsbV15Toggle').textContent =
        STATE.voiceOn ? '🔊 Voice ON' : '🔇 Voice OFF';
    };
    document.getElementById('qsbV15Auto').onclick = () => {
      STATE.autoSpeak = !STATE.autoSpeak;
      localStorage.setItem('qsb.v15.autoSpeak', STATE.autoSpeak ? '1' : '0');
      document.getElementById('qsbV15Auto').textContent =
        STATE.autoSpeak ? '⚡ Auto ON' : '⚡ Auto OFF';
    };
    document.getElementById('qsbV15Talk').onclick = pushToTalkPrompt;
    document.getElementById('qsbV15Col').onclick  = colonelBriefing;
    document.getElementById('qsbV15Corr').onclick = showCorrectionPanel.bind(null, null);
    document.getElementById('qsbV15NW').onclick   = showNotWorkingPanel;
  }
  function voiceBtn(label, id) {
    return '<button id="' + id + '" style="background:#1f3e64;border:1px solid #2a64a0;'
      + 'color:#cde6ff;border-radius:4px;padding:5px 10px;cursor:pointer;font-size:12px">'
      + escapeHtml(label) + '</button>';
  }

  // ──────── Push-to-talk (mic transcript → kernel) ────────
  function pushToTalkPrompt() {
    const SR = window.SpeechRecognition || window.webkitSpeechRecognition;
    if (!SR) {
      alert('Speech recognition unavailable in this browser.');
      return;
    }
    const rec = new SR();
    rec.lang = 'en-GB';
    rec.continuous = false;
    rec.interimResults = false;
    rec.onresult = (ev) => {
      const transcript = ev.results[0][0].transcript;
      postJSON('/api/kernel/talk_transcript', { transcript }).then((reply) => {
        if (reply && reply.reply) speakText(reply.reply);
      });
    };
    rec.onerror = (e) => console.warn('[QSBv15] STT error', e);
    rec.start();
  }

  // ──────── Not-working panel ────────
  async function showNotWorkingPanel() {
    const data = await fetchJSON('/api/tower_ops/not_working');
    let p = document.getElementById('qsbV15NWPanel');
    if (!p) {
      p = document.createElement('div');
      p.id = 'qsbV15NWPanel';
      p.style.cssText = [
        'position:fixed', 'top:100px', 'left:20px', 'z-index:9002',
        'background:rgba(36,18,8,0.95)', 'color:#ffe7c2',
        'border:1px solid #a06a2c', 'border-radius:8px',
        'padding:12px 14px', 'width:380px', 'max-height:70vh',
        'overflow:auto', 'font:12px/1.4 system-ui, sans-serif',
      ].join(';');
      document.body.appendChild(p);
    }
    const items = (data && data.items || []).map((i) =>
      '<li><b style="color:' +
        ((i.severity === 'WARN') ? '#f6c46a' : '#9af0c0') + '">' +
        escapeHtml(i.severity || '—') + '</b> ' +
        escapeHtml(i.item) + ' — ' + escapeHtml(i.status || '') + '</li>').join('');
    p.innerHTML = ''
      + '<div style="display:flex;justify-content:space-between;align-items:center;'
      + 'border-bottom:1px solid #7a4a18;margin-bottom:8px;padding-bottom:6px">'
      +   '<strong style="color:#f4c87a">📋 What Still Needs Work</strong>'
      +   '<span style="cursor:pointer;color:#c08a5a" id="qsbV15NWClose">✕</span>'
      + '</div>'
      + '<ul style="margin:0 0 0 18px">' + items + '</ul>';
    document.getElementById('qsbV15NWClose').onclick = () => p.remove();
  }

  // ──────── Click delegation: worker rows / SVG worker icons ────────
  function handleClick(ev) {
    const tgt = ev.target.closest('[data-wid], [data-worker-id], [data-badge-id]');
    if (!tgt) return;
    const wid = tgt.getAttribute('data-wid')
              || tgt.getAttribute('data-worker-id')
              || tgt.getAttribute('data-badge-id');
    if (!wid) return;
    narrateWorker(wid);
  }

  function init() {
    document.addEventListener('click', handleClick, true);
    injectVoicePanel();
    if (ssAvailable()) {
      window.speechSynthesis.onvoiceschanged = () => {};
    }
    // Expose for cockpit.js use
    window.QSBv15 = {
      narrateWorker, narrateFloor, colonelBriefing,
      runCorrectionPass, runUntilClean, refreshCorrectionLatest,
      speakText, state: STATE,
    };
  }

  if (document.readyState === 'loading') {
    document.addEventListener('DOMContentLoaded', init);
  } else {
    init();
  }
})();
