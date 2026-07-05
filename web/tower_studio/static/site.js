// Tower Studio front-end. Pulls live services from the studio backend.
(function () {
  const $ = (sel) => document.querySelector(sel);

  async function loadServices() {
    try {
      const res = await fetch('/api/services');
      if (!res.ok) throw new Error('status ' + res.status);
      const data = await res.json();
      const grid = $('#services-grid');
      const pricing = $('#pricing-grid');
      grid.innerHTML = '';
      pricing.innerHTML = '';
      const services = (data && data.services) || [];
      services.forEach(s => {
        // Service card
        const card = document.createElement('div');
        card.className = 'service-card';
        card.innerHTML = `
          <div class="cat">${s.category.replace(/_/g, ' ')}</div>
          <h3>${escapeHtml(s.name)}</h3>
          <p>${escapeHtml(s.short_description)}</p>
          <p class="price">$${(s.price_usd).toLocaleString()}</p>
          <p class="turn">Typical turnaround: ${s.typical_turnaround_days} days</p>
          <ul>${s.deliverables.slice(0, 4).map(d => `<li>${escapeHtml(d)}</li>`).join('')}</ul>
          <a class="btn primary" href="#contact" data-sku="${s.sku}">Get a quote</a>
        `;
        grid.appendChild(card);

        // Pricing row
        const row = document.createElement('div');
        row.className = 'pricing-row';
        row.innerHTML = `
          <div class="name">${escapeHtml(s.name)}</div>
          <div class="num">$${(s.price_usd).toLocaleString()}</div>
          <div class="qbc">≈ ${(s.price_usd * (data.qbc_per_usd_advisory || 1)).toLocaleString()} QBC (internal)</div>
        `;
        pricing.appendChild(row);
      });
      // Pre-fill quote in contact form when "Get a quote" clicked
      grid.querySelectorAll('a[data-sku]').forEach(a => {
        a.addEventListener('click', (e) => {
          const sku = a.getAttribute('data-sku');
          const msg = $('#cf-message');
          if (msg && !msg.value.trim()) {
            msg.value = `Hi — I'd like a quote for ${sku}.`;
          }
        });
      });
    } catch (err) {
      $('#services-grid').innerHTML =
        `<p class="loading">Couldn't load services (${err.message}). Local server probably not running.</p>`;
    }
  }

  function escapeHtml(s) {
    return String(s || '').replace(/[&<>"']/g, ch => ({
      '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;'
    })[ch]);
  }

  async function submitContact(ev) {
    ev.preventDefault();
    const form = ev.currentTarget;
    const result = $('#cf-result');
    const payload = Object.fromEntries(new FormData(form).entries());
    if (!payload.name || !payload.email || !payload.message) {
      result.className = 'form-result err';
      result.textContent = 'Name, email, and message are required.';
      return;
    }
    result.className = 'form-result';
    result.textContent = 'Sending…';
    try {
      const res = await fetch('/api/contact', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify(payload),
      });
      const data = await res.json();
      if (!res.ok || !data.ok) throw new Error(data.error || ('status ' + res.status));
      result.className = 'form-result ok';
      result.textContent = `Thanks — logged as ${data.customer_id}. We'll reply within 1 business day.`;
      form.reset();
    } catch (err) {
      result.className = 'form-result err';
      result.textContent = 'Send failed: ' + err.message;
    }
  }

  document.addEventListener('DOMContentLoaded', () => {
    loadServices();
    const form = $('#contact-form');
    if (form) form.addEventListener('submit', submitContact);
  });
})();
