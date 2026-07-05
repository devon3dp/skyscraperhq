// QSB Tower V1.3 — qsb_audio.js
// Phase: QSB_TOWER_3D_COCKPIT_VISUAL_REFINEMENT_V2
//
// Optional sound + speech. Both are OFF by default and require a user
// gesture (button click) to enable, per browser autoplay policy.
//
// - sound:  Web Audio API short ticks for packet movement, low alert for
//           any execution-lock-true transition.
// - speech: Web Speech API speechSynthesis. No external speech provider.
//           No AirLLM. No heavy TTS packages.

(function () {
  'use strict';

  const A = {
    soundOn: false,
    speechOn: false,
    ctx: null,
    lastTickAt: 0,
    lastLockAlertAt: 0,
    lastSpokenSig: null,
    initialized: false,
    spokenOnce: {},   // throttle event speech (sig -> last spoken ts)
  };
  window.QSB_AUDIO = A;

  function ensureCtx() {
    if (A.ctx) return A.ctx;
    try {
      const Ctx = window.AudioContext || window.webkitAudioContext;
      A.ctx = new Ctx();
    } catch (e) {
      A.ctx = null;
    }
    return A.ctx;
  }

  function tone(freq, dur, gain, type) {
    if (!A.soundOn) return;
    const ctx = ensureCtx();
    if (!ctx) return;
    const o = ctx.createOscillator();
    const g = ctx.createGain();
    o.type = type || 'sine';
    o.frequency.value = freq;
    g.gain.value = 0;
    g.gain.linearRampToValueAtTime(gain, ctx.currentTime + 0.005);
    g.gain.exponentialRampToValueAtTime(0.0001, ctx.currentTime + dur);
    o.connect(g); g.connect(ctx.destination);
    o.start();
    o.stop(ctx.currentTime + dur + 0.02);
  }

  A.setSoundOn = function (on) {
    A.soundOn = !!on;
    if (A.soundOn) {
      ensureCtx();
      // brief acknowledge chirp so the user knows it's enabled
      tone(880, 0.06, 0.05, 'sine');
      setTimeout(() => tone(1320, 0.05, 0.05, 'sine'), 80);
    }
  };

  A.setSpeechOn = function (on) {
    A.speechOn = !!on;
    if (A.speechOn) A.say('Sound advisory enabled.');
  };

  A.tickPacket = function (packets) {
    if (!A.soundOn) return;
    const now = performance.now();
    if (now - A.lastTickAt < 200) return;       // throttle
    A.lastTickAt = now;
    // tiny soft tick
    tone(1600 + Math.random() * 400, 0.04, 0.025, 'triangle');
  };

  A.alertLock = function () {
    if (!A.soundOn) return;
    const now = performance.now();
    if (now - A.lastLockAlertAt < 1500) return;
    A.lastLockAlertAt = now;
    // 3-tone descending alert
    tone(660, 0.18, 0.07, 'square');
    setTimeout(() => tone(440, 0.20, 0.07, 'square'), 200);
    setTimeout(() => tone(330, 0.30, 0.07, 'square'), 420);
  };

  // Soft chime for a newly recruited sandbox worker. Same throttle bucket
  // as packet ticks so a rapid recruit burst doesn't spam the headphones.
  A.chimeRecruit = function () {
    if (!A.soundOn) return;
    const now = performance.now();
    if (now - A.lastTickAt < 200) return;
    A.lastTickAt = now;
    tone(880, 0.10, 0.05, 'sine');
    setTimeout(() => tone(1320, 0.12, 0.045, 'sine'), 90);
  };

  // Cancel any pending speech + reset toggles. Bound to a Mute-All button.
  A.muteAll = function () {
    A.soundOn = false;
    A.speechOn = false;
    try { window.speechSynthesis && window.speechSynthesis.cancel(); } catch (e) {}
  };

  // ── speech ─────────────────────────────────────────────────────────
  function speak(text) {
    if (!A.speechOn) return;
    if (!('speechSynthesis' in window)) return;
    try {
      const u = new SpeechSynthesisUtterance(text);
      u.rate = 1.0;
      u.pitch = 1.0;
      u.volume = 0.9;
      window.speechSynthesis.speak(u);
    } catch (e) {}
  }
  A.say = function (text) { speak(text); };

  // Announce significant events based on state — throttled per signature.
  // Called from cockpit.js whenever a new state arrives.
  A.observeState = function (state, prev) {
    if (!A.speechOn || !state) return;
    const k = state.kernel || {};
    const prevK = (prev && prev.kernel) || {};
    const sig = (key, val) => {
      const last = A.spokenOnce[key];
      if (last === val) return false;
      A.spokenOnce[key] = val;
      return true;
    };

    if (k.activation_status === 'active_local_only' && sig('kernel_active', k.activation_status)) {
      speak('Kernel active, local only.');
    }
    if ((state.lock_count_true || 0) === 0 && sig('locks_zero', 'zero')) {
      speak('All execution locks closed.');
    }
    if ((state.lock_count_true || 0) > 0) {
      const prevTrue = (prev && prev.lock_count_true) || 0;
      if ((state.lock_count_true || 0) > prevTrue) {
        speak('Warning. Execution lock changed.');
        A.alertLock();
      }
    }
    const oandaTs = state.oanda_floor && state.oanda_floor.latest_ts;
    if (oandaTs && sig('oanda_ts', oandaTs)) speak('OANDA floor updated.');
    const binanceTs = state.binance && state.binance.strategy_latest_ts;
    if (binanceTs && sig('binance_ts', binanceTs)) speak('Binance floor updated.');
    const stockTs = state.stock_exchange && (state.stock_exchange.latest_ts ||
                                              state.stock_exchange.status_ts);
    if (stockTs && sig('stock_ts', stockTs)) speak('Stock floor updated.');
    const air = state.airllm_chamber || {};
    if (air.registered && sig('airllm_chamber', 'installed')) {
      speak('AirLLM advisory chamber online.');
    }
    // Floor 30 Risk — "checkpoint clear" when locks stay zero.
    const risk = state.risk || {};
    if (risk.lock_count_true === 0 && sig('risk_clear', risk.last_check_ts || 'zero')) {
      speak('Risk checkpoint clear.');
    }
    // Recruitment Agency on Floor 45 — speak the latest recruit/assign event.
    const rec = state.recruitment_agency_floor45 || state.recruitment_agency || {};
    const lastEv = (rec.latest_events || rec.events || [])[0] || {};
    if (lastEv.event === 'recruit' && lastEv.worker_id && sig('rec_recruit', lastEv.worker_id)) {
      speak('Worker recruited.');
      try { A.chimeRecruit(); } catch (_e) {}
    }
    if (lastEv.event === 'assign' && lastEv.worker_id && lastEv.target_floor &&
        sig('rec_assign:' + lastEv.target_floor, lastEv.worker_id)) {
      if (String(lastEv.target_floor).indexOf('38') >= 0) {
        speak('Worker assigned to sandbox.');
      } else {
        speak('Worker assigned to ' + String(lastEv.target_floor).replace('_', ' ') + '.');
      }
    }
    // Paper bias candidate detection
    const bias = (state.instruments || []).find((i) => i.paper_signal && i.paper_signal !== 'observe');
    if (bias) {
      const s = 'paper_bias:' + bias.instrument + ':' + bias.paper_signal;
      if (sig('paper_bias', s)) speak('Paper bias candidate detected on ' + bias.instrument.replace('_', ' '));
    }
  };

  // Allow the cockpit.js layer to mute everything (e.g., on page unload)
  A.shutdown = function () {
    A.soundOn = false; A.speechOn = false;
    try { window.speechSynthesis && window.speechSynthesis.cancel(); } catch (e) {}
  };
})();
