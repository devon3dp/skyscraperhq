// QSB Tower V1.5 — Sound Bar
// Ross 2026-06-12: dedicated start/stop, kernel + commentary toggles,
// push-to-talk to Helm and Auger.
//
// All speech is browser-native (Web Speech API + Web SpeechRecognition).
// No cloud STT, no external speech provider. ToS-respecting.

(function () {
  'use strict';

  const $ = (id) => document.getElementById(id);
  let _busyUtterance = null;
  let _ptt = { rec: null, target: null, mediaStream: null };

  function setStatus(msg) {
    const el = $('sbStatus');
    if (el) el.textContent = msg;
  }

  // ─── master speech helpers ───────────────────────────────────────────
  function cancelAllSpeech() {
    try { window.speechSynthesis && window.speechSynthesis.cancel(); } catch (e) {}
    _busyUtterance = null;
  }
  // V2 voices — pick the best available voice per officer instead of the
  // browser default. Helm = lower, calmer (operations bearing). Auger =
  // warmer, slightly higher (logistics, conversational).
  let _voiceCache = null;
  function _getVoices() {
    if (_voiceCache) return _voiceCache;
    if (!('speechSynthesis' in window)) return [];
    _voiceCache = window.speechSynthesis.getVoices() || [];
    return _voiceCache;
  }
  if ('speechSynthesis' in window) {
    window.speechSynthesis.onvoiceschanged = () => { _voiceCache = null; };
  }
  function _pickVoice(profile) {
    const voices = _getVoices();
    if (!voices.length) return null;
    // Profile-based preferences. Each entry is a regex over (voice.name + lang).
    const prefs = {
      helm: [
        /Daniel.*en-GB/i,        // macOS UK male
        /Google UK English Male/i,
        /Microsoft George.*English/i,
        /en-GB.*male/i,
        /en-GB/i,
      ],
      auger: [
        /Samantha.*en-(US|GB)/i, // macOS female
        /Google UK English Female/i,
        /Microsoft Hazel.*English/i,
        /Microsoft Susan/i,
        /en-GB.*female/i,
        /en-GB/i,
      ],
      neutral: [
        /Google UK English/i,
        /en-GB/i,
      ],
    };
    const list = prefs[profile] || prefs.neutral;
    for (const re of list) {
      const v = voices.find(x => re.test((x.name + ' ' + (x.lang || ''))));
      if (v) return v;
    }
    return voices[0];
  }

  function speak(text, opts) {
    if (!('speechSynthesis' in window)) { setStatus('speech api unavailable'); return; }
    cancelAllSpeech();
    const u = new SpeechSynthesisUtterance(String(text || '').slice(0, 1200));
    const profile = (opts && opts.profile) || 'neutral';
    const v = _pickVoice(profile);
    if (v) u.voice = v;
    // Sensible defaults per profile if caller didn't override
    if (profile === 'helm') { u.rate = 0.96; u.pitch = 0.85; u.volume = 1.0; }
    else if (profile === 'auger') { u.rate = 1.02; u.pitch = 1.15; u.volume = 1.0; }
    else { u.rate = 1.0; u.pitch = 1.0; u.volume = 1.0; }
    // Caller overrides win
    if (opts) {
      if (opts.rate != null) u.rate = opts.rate;
      if (opts.pitch != null) u.pitch = opts.pitch;
      if (opts.volume != null) u.volume = opts.volume;
    }
    u.onstart = () => setStatus('speaking · ' + (v ? v.name.slice(0, 24) : 'default'));
    u.onend = () => { setStatus('idle'); _busyUtterance = null; };
    u.onerror = (e) => { setStatus('speech error: ' + (e.error || '')); };
    _busyUtterance = u;
    try { window.speechSynthesis.speak(u); } catch (e) { setStatus('speech error'); }
  }

  // ─── kernel + commentary toggles (mirror the existing header buttons) ─
  function syncToggleFromHeader(sbId, hdrId, label) {
    const sb = $(sbId), hdr = $(hdrId);
    if (!sb || !hdr) return;
    const on = hdr.dataset.on === '1';
    sb.dataset.on = on ? '1' : '0';
    sb.textContent = (on ? label.on : label.off);
  }

  function wireToggle(sbId, hdrId, label, defaultClickFallback) {
    const sb = $(sbId);
    if (!sb) return;
    sb.addEventListener('click', () => {
      const hdr = $(hdrId);
      if (hdr) {
        hdr.click();  // delegate to the existing header button
      } else if (defaultClickFallback) {
        defaultClickFallback();
      }
      // re-sync from the source of truth after a microtask
      setTimeout(() => syncToggleFromHeader(sbId, hdrId, label), 0);
    });
    // initial sync
    syncToggleFromHeader(sbId, hdrId, label);
    // also sync periodically in case header is toggled by other code
    setInterval(() => syncToggleFromHeader(sbId, hdrId, label), 1200);
  }

  // ─── push-to-talk via webkitSpeechRecognition ────────────────────────
  function _SpeechRecognitionCtor() {
    return window.SpeechRecognition || window.webkitSpeechRecognition || null;
  }

  function pttStart(officer, btn) {
    const Ctor = _SpeechRecognitionCtor();
    if (!Ctor) {
      setStatus('speech recognition not supported in this browser');
      return;
    }
    cancelAllSpeech();  // stop any kernel narration so the mic doesn't pick it up
    const rec = new Ctor();
    rec.lang = 'en-GB';
    rec.continuous = false;
    rec.interimResults = true;
    let finalText = '';
    rec.onresult = (e) => {
      let interim = '';
      for (let i = e.resultIndex; i < e.results.length; i++) {
        if (e.results[i].isFinal) finalText += e.results[i][0].transcript;
        else interim += e.results[i][0].transcript;
      }
      setStatus('hearing: ' + (interim || finalText).slice(0, 60));
    };
    rec.onerror = (ev) => {
      setStatus('mic error: ' + (ev.error || 'unknown'));
      btn.classList.remove('holding');
    };
    rec.onend = () => {
      btn.classList.remove('holding');
      _ptt.rec = null;
      const txt = finalText.trim();
      if (!txt) { setStatus('no speech detected'); return; }
      setStatus(officer + ' heard: "' + txt.slice(0, 50) + '"');
      sendToOfficer(officer, txt);
    };
    try { rec.start(); _ptt.rec = rec; _ptt.target = officer; }
    catch (e) { setStatus('mic start failed: ' + (e.message || '')); }
    btn.classList.add('holding');
    setStatus('listening · talk to ' + officer + '…');
  }

  function pttStop() {
    if (_ptt.rec) {
      try { _ptt.rec.stop(); } catch (e) {}
    }
  }

  async function sendToOfficer(officer, text) {
    try {
      const r = await fetch('/api/officers/' + encodeURIComponent(officer) + '/talk', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ text, ts: new Date().toISOString() }),
      });
      const d = await r.json();
      if (d.ok && d.reply) {
        speak(d.reply, { profile: officer.toLowerCase() });
      } else {
        setStatus(officer + ' replied with empty');
      }
    } catch (e) {
      setStatus('officer endpoint error: ' + (e.message || ''));
    }
  }

  // ─── boot ────────────────────────────────────────────────────────────
  function boot() {
    const stopBtn = $('sbStopNow');
    if (stopBtn) stopBtn.addEventListener('click', () => {
      cancelAllSpeech(); pttStop();
      setStatus('stopped · ready');
    });

    wireToggle('sbKernelToggle', 'btnSpeech',
      { on: '🧠 Kernel: On', off: '🧠 Kernel: Off' });
    wireToggle('sbCommentaryToggle', 'btnNarrator',
      { on: '🎙 Commentary: On', off: '🎙 Commentary: Off' });

    const helmBtn = $('sbTalkHelm');
    const augerBtn = $('sbTalkAuger');
    if (helmBtn) {
      helmBtn.addEventListener('mousedown', () => pttStart('Helm', helmBtn));
      helmBtn.addEventListener('mouseup',   () => pttStop());
      helmBtn.addEventListener('mouseleave',() => helmBtn.classList.contains('holding') && pttStop());
      helmBtn.addEventListener('touchstart',(e) => { e.preventDefault(); pttStart('Helm', helmBtn); }, { passive: false });
      helmBtn.addEventListener('touchend',  (e) => { e.preventDefault(); pttStop(); });
    }
    if (augerBtn) {
      augerBtn.addEventListener('mousedown', () => pttStart('Auger', augerBtn));
      augerBtn.addEventListener('mouseup',   () => pttStop());
      augerBtn.addEventListener('mouseleave',() => augerBtn.classList.contains('holding') && pttStop());
      augerBtn.addEventListener('touchstart',(e) => { e.preventDefault(); pttStart('Auger', augerBtn); }, { passive: false });
      augerBtn.addEventListener('touchend',  (e) => { e.preventDefault(); pttStop(); });
    }

    setStatus('idle · ready');
  }

  if (document.readyState === 'loading') {
    document.addEventListener('DOMContentLoaded', boot);
  } else {
    boot();
  }
})();
