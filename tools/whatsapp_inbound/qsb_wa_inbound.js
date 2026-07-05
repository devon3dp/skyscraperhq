// qsb_wa_inbound.js — WhatsApp Web inbound bridge for the QSB receptionist.
//
// What it does:
//   Boots a headless Chromium that runs WhatsApp Web. Ross scans the QR
//   from the Galaxy ONCE (Settings → Linked devices → Link a device). On
//   every inbound message, the bridge:
//     1. Logs the message + sender to data/registries/qsb_wa_inbound.jsonl
//     2. POSTs to http://127.0.0.1:8765/api/f0/converse with caller_id
//        formed from the sender's phone (whatsapp:+44…)
//     3. Replies on WhatsApp with the F0 response (which includes the
//        receptionist menu on first contact)
//
// Hard rules:
//   - Reply-text is taken straight from /api/f0/converse — no client-side
//     creativity.
//   - Skips messages from groups; replies only on 1:1 chats.
//   - Auth state persisted to ./auth_data (LocalAuth) so subsequent boots
//     resume without re-scanning.
//
// Run:  node tools/whatsapp_inbound/qsb_wa_inbound.js
//
// Source: built in-session 2026-06-17 under Ross's helm authority. F47
// stamp accompanies first message.

const { Client, LocalAuth } = require('whatsapp-web.js');
const qrcode = require('qrcode-terminal');
const fs = require('fs');
const path = require('path');
const http = require('http');

const ROOT = '/vaults/nvme0/qsb_tower_v1';
const INBOUND_LOG = path.join(ROOT, 'data/registries/qsb_wa_inbound.jsonl');
const F47 = path.join(ROOT, 'data/registries/qsb_f47_team_records.jsonl');
const F0_BASE = process.env.QSB_F0_BASE || 'http://127.0.0.1:8765';

function nowIso() {
  return new Date().toISOString().replace(/\.\d{3}Z$/, 'Z');
}

function stamp(file, row) {
  fs.appendFileSync(file, JSON.stringify(row) + '\n');
}

// POST helper using Node's built-in http (no extra deps)
function postJson(url, body) {
  return new Promise((resolve) => {
    const u = new URL(url);
    const data = JSON.stringify(body);
    const req = http.request({
      hostname: u.hostname,
      port: u.port || 80,
      path: u.pathname + (u.search || ''),
      method: 'POST',
      headers: {
        'Content-Type': 'application/json',
        'Content-Length': Buffer.byteLength(data),
      },
      timeout: 6000,
    }, (res) => {
      let chunks = '';
      res.on('data', (c) => chunks += c);
      res.on('end', () => {
        try {
          resolve(JSON.parse(chunks));
        } catch (e) {
          resolve({ ok: false, error: 'bad_json', raw: chunks.slice(0, 200) });
        }
      });
    });
    req.on('error', (e) => resolve({ ok: false, error: e.message }));
    req.on('timeout', () => { req.destroy(); resolve({ ok: false, error: 'timeout' }); });
    req.write(data);
    req.end();
  });
}

const client = new Client({
  authStrategy: new LocalAuth({
    dataPath: path.join(__dirname, 'auth_data'),
  }),
  puppeteer: {
    headless: true,
    // Use the system Chrome instead of Puppeteer's bundled (which isn't
    // downloaded). Falls back via env QSB_CHROME if Ross moves Chrome.
    executablePath: process.env.QSB_CHROME || '/opt/google/chrome/chrome',
    args: [
      '--no-sandbox',
      '--disable-setuid-sandbox',
      '--disable-dev-shm-usage',
    ],
  },
});

client.on('qr', (qr) => {
  console.log('\n[QSB-WA-INBOUND] Scan this QR from Galaxy WhatsApp → Settings → Linked devices → Link a device:');
  qrcode.generate(qr, { small: true });
  try { fs.writeFileSync('/tmp/wa_qr.txt', qr); } catch (_) {}
});

client.on('authenticated', () => {
  console.log(`[${nowIso()}] authenticated — auth state cached locally`);
});

client.on('auth_failure', (msg) => {
  console.error(`[${nowIso()}] auth_failure: ${msg}`);
  stamp(F47, {
    ts: nowIso(), kind: 'wa_inbound_auth_failure',
    operator: 'wa_inbound', summary: String(msg).slice(0, 300),
  });
});

client.on('ready', () => {
  console.log(`[${nowIso()}] WA Web client ready. Listening for inbound 1:1 messages.`);
  stamp(F47, {
    ts: nowIso(), kind: 'wa_inbound_started',
    operator: 'wa_inbound',
    summary: 'WhatsApp Web inbound bridge online — connecting incoming chats to /api/f0/converse',
  });
});

client.on('message', async (msg) => {
  try {
    // Skip own messages and groups
    if (msg.fromMe) return;
    const chat = await msg.getChat();
    if (chat.isGroup) return;

    const from = msg.from || '';        // e.g. "447481057362@c.us"
    const body = msg.body || '';
    const phone = from.replace(/@c\.us$/, '');
    const callerId = `whatsapp:+${phone}`;

    stamp(INBOUND_LOG, {
      ts: nowIso(), from: phone, body_head: body.slice(0, 200),
      body_len: body.length,
    });
    console.log(`[${nowIso()}] inbound from +${phone}: ${body.slice(0, 120)}`);

    // Route to F0 — same pipeline the Telegram receptionist uses
    const reply = await postJson(`${F0_BASE}/api/f0/converse`, {
      caller_id: callerId,
      text: body,
    });

    const replyText = (reply && reply.text)
      || 'Sorry, the front desk is briefly unreachable. Try again in a moment.';

    await msg.reply(replyText);
    stamp(F47, {
      ts: nowIso(), kind: 'wa_inbound_replied',
      operator: 'wa_inbound',
      summary: `+${phone} · in=${body.length}c · out=${replyText.length}c`,
    });
  } catch (e) {
    console.error(`[${nowIso()}] message-handler error:`, e.message);
    stamp(F47, {
      ts: nowIso(), kind: 'wa_inbound_handler_error',
      operator: 'wa_inbound', summary: String(e.message).slice(0, 300),
    });
  }
});

client.on('disconnected', (reason) => {
  console.log(`[${nowIso()}] disconnected: ${reason}`);
  stamp(F47, {
    ts: nowIso(), kind: 'wa_inbound_disconnected',
    operator: 'wa_inbound', summary: String(reason).slice(0, 300),
  });
});

process.on('SIGTERM', async () => {
  console.log('SIGTERM, destroying client');
  try { await client.destroy(); } catch (_) {}
  process.exit(0);
});
process.on('SIGINT', async () => {
  console.log('SIGINT, destroying client');
  try { await client.destroy(); } catch (_) {}
  process.exit(0);
});

client.initialize();
