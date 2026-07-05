// Lumen AI playground — talks to the local Lumen backend.
(function () {
  const $ = (sel) => document.querySelector(sel);
  let conversationId = null;

  function appendBubble(role, text, meta) {
    const log = $('#chat-log');
    const div = document.createElement('div');
    div.className = 'bubble ' + role;
    div.textContent = text;
    if (meta) {
      const m = document.createElement('div');
      m.className = 'meta';
      m.textContent = meta;
      div.appendChild(m);
    }
    log.appendChild(div);
    log.scrollTop = log.scrollHeight;
  }

  async function send(message) {
    if (!message) return;
    appendBubble('user', message);
    const inp = $('#chat-input');
    inp.value = '';
    inp.disabled = true;
    appendBubble('lumen', 'Thinking…');
    const placeholder = $('#chat-log').lastChild;
    try {
      const res = await fetch('/api/chat', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ message, conversation_id: conversationId }),
      });
      const data = await res.json();
      $('#chat-log').removeChild(placeholder);
      if (!data || !data.ok) {
        appendBubble('lumen', '(error: ' + (data && data.error || res.status) + ')');
      } else {
        conversationId = data.conversation_id || conversationId;
        const matched = (data.matched_topics && data.matched_topics.length)
            ? ('matched: ' + data.matched_topics.join(', '))
            : (data.fallback_reason ? ('fallback: ' + data.fallback_reason) : '');
        appendBubble('lumen', data.reply, matched);
      }
    } catch (err) {
      $('#chat-log').removeChild(placeholder);
      appendBubble('lumen', '(network error: ' + err.message + ')');
    } finally {
      inp.disabled = false;
      inp.focus();
    }
  }

  async function loadTiers() {
    try {
      const res = await fetch('/api/tiers');
      const data = await res.json();
      const grid = $('#tiers-grid');
      grid.innerHTML = '';
      (data.tiers || []).forEach((t, i) => {
        const card = document.createElement('div');
        card.className = 'tier-card' + (i === 1 ? ' featured' : '');
        card.innerHTML = `
          <h3>${t.name}</h3>
          <p class="price">$${(t.price_usd_per_month).toLocaleString()} / mo</p>
          <ul>${t.features.map(f => `<li>${f}</li>`).join('')}</ul>
          <button class="btn primary" disabled>Sign up (gated)</button>
        `;
        grid.appendChild(card);
      });
    } catch (err) {
      $('#tiers-grid').innerHTML = `<p class="loading">Couldn't load tiers (${err.message}).</p>`;
    }
  }

  function bindUi() {
    const form = $('#chat-form');
    form.addEventListener('submit', (ev) => {
      ev.preventDefault();
      const msg = $('#chat-input').value.trim();
      if (msg) send(msg);
    });
    document.querySelectorAll('.chat-suggestions .chip').forEach(btn => {
      btn.addEventListener('click', () => send(btn.getAttribute('data-msg')));
    });
    // Open with a greeting
    appendBubble('lumen',
      "Hi — I'm Lumen. Ask me about the tower. Try one of the chips below.");
  }

  document.addEventListener('DOMContentLoaded', () => {
    bindUi();
    loadTiers();
  });
})();
