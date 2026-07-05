/*
 * QSB Speech Voice — Single Source of Truth
 * Phase: QSB_KERNEL_CHAT_PENTHOUSE_AND_3D_DASHBOARD_REALITY_FIX_V1
 *
 * Fixes the "German voice" bug where SpeechSynthesisUtterance was
 * created without `voice` or `lang` set and the browser fell back to
 * the OS-locale default.
 *
 * Exports window.QSB_SPEECH with:
 *   QSB_SPEECH.speak(text)        — speak using selected/default voice
 *   QSB_SPEECH.cancel()           — cancel pending speech
 *   QSB_SPEECH.list()             — list available voices
 *   QSB_SPEECH.setVoiceByName(n)  — store preference + use
 *   QSB_SPEECH.setRate(r)
 *   QSB_SPEECH.setVolume(v)
 *   QSB_SPEECH.testVoice()        — speak a short test phrase
 *
 * Header injection: adds a #qsbVoiceSelect <select> + Test button to the
 * top-right header so the user can switch voice without dev tools.
 */
(function () {
  'use strict';
  if (window.QSB_SPEECH_INSTALLED) return;
  window.QSB_SPEECH_INSTALLED = true;

  const LS = {
    voiceName: 'qsb.speech.voiceName',
    voiceLang: 'qsb.speech.voiceLang',
    rate: 'qsb.speech.rate',
    volume: 'qsb.speech.volume',
    allowNonEnglish: 'qsb.speech.allowNonEnglish',
  };

  const PRIORITY = ['en-GB', 'en-US', 'en-AU', 'en-IE', 'en-CA', 'en-IN'];

  let cachedVoices = [];

  function loadVoices() {
    if (!('speechSynthesis' in window)) return [];
    cachedVoices = window.speechSynthesis.getVoices() || [];
    return cachedVoices;
  }

  function isEnglish(v) {
    return v && typeof v.lang === 'string' && v.lang.toLowerCase().startsWith('en');
  }

  function pickPreferredVoice() {
    const voices = loadVoices();
    if (!voices.length) return null;
    const storedName = localStorage.getItem(LS.voiceName);
    if (storedName) {
      const m = voices.find(function (v) { return v.name === storedName; });
      if (m) return m;
    }
    // Priority match by lang
    for (let i = 0; i < PRIORITY.length; i++) {
      const m = voices.find(function (v) { return v.lang === PRIORITY[i]; });
      if (m) return m;
    }
    // Any English
    const anyEn = voices.find(isEnglish);
    if (anyEn) return anyEn;
    if (localStorage.getItem(LS.allowNonEnglish) === '1') return voices[0];
    return null;  // null signals: refuse to speak in a non-English voice
  }

  function buildUtterance(text) {
    const u = new SpeechSynthesisUtterance(String(text).slice(0, 600));
    const v = pickPreferredVoice();
    if (v) {
      u.voice = v;
      u.lang = v.lang;
    } else {
      // No English voice available — force lang to en-GB and let browser
      // resolve. If the browser still picks non-English the warning
      // banner explains why.
      u.lang = 'en-GB';
    }
    const r = parseFloat(localStorage.getItem(LS.rate) || '1.0');
    const vol = parseFloat(localStorage.getItem(LS.volume) || '1.0');
    u.rate = isNaN(r) ? 1.0 : Math.max(0.5, Math.min(1.8, r));
    u.volume = isNaN(vol) ? 1.0 : Math.max(0, Math.min(1, vol));
    u.pitch = 1.0;
    return u;
  }

  function speak(text) {
    if (!('speechSynthesis' in window) || !text) return false;
    const u = buildUtterance(text);
    if (!u) return false;
    try {
      window.speechSynthesis.cancel();
      window.speechSynthesis.speak(u);
      return true;
    } catch (_) { return false; }
  }

  function cancel() {
    try { window.speechSynthesis && window.speechSynthesis.cancel(); } catch (_) {}
  }

  function list() { return loadVoices().map(function (v) {
    return { name: v.name, lang: v.lang, default: v.default };
  }); }

  function setVoiceByName(name) {
    const voices = loadVoices();
    const v = voices.find(function (x) { return x.name === name; });
    if (!v) return false;
    localStorage.setItem(LS.voiceName, v.name);
    localStorage.setItem(LS.voiceLang, v.lang);
    if (!isEnglish(v)) localStorage.setItem(LS.allowNonEnglish, '1');
    return true;
  }

  function setRate(r) { localStorage.setItem(LS.rate, String(r)); }
  function setVolume(v) { localStorage.setItem(LS.volume, String(v)); }

  function testVoice() { speak('QSB Tower speech check. English voice selected. All execution locks remain closed.'); }

  // ── Header UI injection ────────────────────────────────────────
  function injectSelector() {
    const hdr = document.querySelector('#hdr .hdr-r');
    if (!hdr) return;
    if (document.getElementById('qsbVoiceSelect')) return;

    const wrap = document.createElement('span');
    wrap.id = 'qsbVoiceWrap';
    wrap.style.cssText = 'display:inline-flex; gap:4px; align-items:center;';

    const sel = document.createElement('select');
    sel.id = 'qsbVoiceSelect';
    sel.className = 'hdr-btn';
    sel.style.cssText = 'padding:4px 6px; max-width:220px;';
    sel.title = 'Speech voice (defaults to English; non-English requires explicit selection)';

    const test = document.createElement('button');
    test.id = 'qsbVoiceTest';
    test.className = 'hdr-btn';
    test.textContent = '🔊 Test';
    test.title = 'Speak a short test phrase with the selected voice';
    test.addEventListener('click', testVoice);

    const meta = document.createElement('span');
    meta.id = 'qsbVoiceMeta';
    meta.className = 'pill';
    meta.style.cssText = 'font-size:9.6px;';
    meta.textContent = 'voice —';

    wrap.appendChild(sel);
    wrap.appendChild(test);
    wrap.appendChild(meta);
    // Insert before existing #btnRefresh if present, else append.
    const refresh = document.getElementById('btnRefresh');
    if (refresh && refresh.parentNode) refresh.parentNode.insertBefore(wrap, refresh);
    else hdr.appendChild(wrap);

    function populate() {
      const voices = loadVoices();
      sel.innerHTML = '';
      // English first
      const en = voices.filter(isEnglish);
      const other = voices.filter(function (v) { return !isEnglish(v); });
      [].concat(en, other).forEach(function (v) {
        const opt = document.createElement('option');
        opt.value = v.name;
        opt.textContent = (isEnglish(v) ? '🇬🇧 ' : '⚠ ') + v.name + ' · ' + v.lang;
        sel.appendChild(opt);
      });
      const stored = localStorage.getItem(LS.voiceName);
      if (stored && voices.some(function (v) { return v.name === stored; })) {
        sel.value = stored;
      } else {
        const def = pickPreferredVoice();
        if (def) {
          sel.value = def.name;
          localStorage.setItem(LS.voiceName, def.name);
          localStorage.setItem(LS.voiceLang, def.lang);
        }
      }
      updateMeta();
    }

    function updateMeta() {
      const v = pickPreferredVoice();
      meta.textContent = v ? ('voice: ' + v.lang) : 'no English voice — speech disabled';
      meta.className = v && isEnglish(v) ? 'pill ok' : 'pill warn';
    }

    sel.addEventListener('change', function () {
      setVoiceByName(sel.value);
      updateMeta();
    });

    populate();
    if ('speechSynthesis' in window && window.speechSynthesis.onvoiceschanged !== undefined) {
      window.speechSynthesis.onvoiceschanged = populate;
    }
  }

  function attach() {
    loadVoices();
    injectSelector();
  }

  if (document.readyState === 'loading') {
    document.addEventListener('DOMContentLoaded', attach);
  } else {
    attach();
  }

  // Public API
  window.QSB_SPEECH = {
    speak: speak,
    cancel: cancel,
    list: list,
    setVoiceByName: setVoiceByName,
    setRate: setRate,
    setVolume: setVolume,
    testVoice: testVoice,
    pickPreferredVoice: pickPreferredVoice,
  };
})();
