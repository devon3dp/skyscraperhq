// qsb_wa_bridge.js — Skyscraper WhatsApp always-on bridge.
//
// Extends qsb_wa_inbound.js with an outbound /send HTTP endpoint so the
// same warm session serves BOTH:
//   INBOUND  · WhatsApp Web → F0 receptionist (localhost:8765/api/f0/converse)
//               reply auto-sent back to the caller on WhatsApp
//   OUTBOUND · POST http://127.0.0.1:8790/send {to, text}
//               HQ / Wren / any floor can drive the tower's WA line
//
// Session persisted at ./auth_data (LocalAuth, linked-device to Galaxy).
// Tower WA number = the Galaxy's own SIM (07411410545 → +447411410545).
//
// Endpoints:
//   GET  /status                → {ready, uptime_s, inbound_seen, outbound_sent}
//   GET  /qr                    → base64 QR (only served when session needs re-scan)
//   POST /send {to,text}        → {ok, msg_id}
//
// No auth — bound to 127.0.0.1 only. Every send audited to
// data/registries/qsb_wa_sends.jsonl. Every inbound audited to
// data/registries/qsb_wa_inbound.jsonl.

const { Client, LocalAuth } = require('whatsapp-web.js');
const qrcode = require('qrcode-terminal');
const fs = require('fs');
const path = require('path');
const http = require('http');

const ROOT = '/vaults/nvme0/qsb_tower_v1';
const INBOUND_LOG = path.join(ROOT, 'data/registries/qsb_wa_inbound.jsonl');
const SEND_LOG    = path.join(ROOT, 'data/registries/qsb_wa_sends.jsonl');
const F47         = path.join(ROOT, 'data/registries/qsb_f47_team_records.jsonl');
const F0_BASE     = process.env.QSB_F0_BASE || 'http://127.0.0.1:8765';
const HTTP_PORT   = parseInt(process.env.QSB_WA_BRIDGE_PORT || '8790', 10);

function nowIso() { return new Date().toISOString().replace(/\.\d{3}Z$/, 'Z'); }
function stamp(file, row) {
  try { fs.appendFileSync(file, JSON.stringify(row) + '\n'); } catch (_) {}
}
function f47(kind, body) {
  stamp(F47, { ts: nowIso(), who: 'wa_bridge', kind, ...body });
}

// ── WhatsApp client ───────────────────────────────────────────────
const client = new Client({
  authStrategy: new LocalAuth({ dataPath: path.join(__dirname, 'auth_data') }),
  puppeteer: {
    headless: true,
    executablePath: process.env.QSB_CHROME || '/opt/google/chrome/chrome',
    args: ['--no-sandbox', '--disable-setuid-sandbox', '--disable-dev-shm-usage'],
  },
});

let ready = false;
let started = Date.now();
let lastQr = null;
let inboundSeen = 0;
let outboundSent = 0;

client.on('qr', (qr) => {
  lastQr = qr;
  console.log('[wa_bridge] QR — session needs re-scan');
  qrcode.generate(qr, { small: true });
  f47('qr_shown', {});
});

client.on('ready', () => {
  ready = true;
  lastQr = null;
  console.log('[wa_bridge] READY — tower WA line online');
  f47('ready', { uptime_at_ready_s: Math.floor((Date.now() - started) / 1000) });
});

client.on('auth_failure', (m) => {
  console.error('[wa_bridge] AUTH_FAILURE:', m);
  ready = false;
  f47('auth_failure', { detail: String(m).slice(0, 200) });
});

client.on('disconnected', (reason) => {
  console.error('[wa_bridge] DISCONNECTED:', reason);
  ready = false;
  f47('disconnected', { reason: String(reason).slice(0, 200) });
});

// ── Inbound handler: send to F0, reply to caller with F0's reply ───
client.on('message', async (msg) => {
  try {
    // Skip groups (only 1:1)
    if (msg.from.includes('@g.us')) return;
    // Skip status broadcast
    if (msg.from === 'status@broadcast') return;

    const from = msg.from;                       // e.g. "447481057362@c.us"
    const phone = '+' + from.replace('@c.us','');
    const text = msg.body || '';
    inboundSeen++;

    stamp(INBOUND_LOG, {
      ts: nowIso(), from, phone, text_head: text.slice(0, 240), text_len: text.length,
    });

    // POST to F0 for reply
    const reply = await postJson(`${F0_BASE}/api/f0/converse`, {
      caller_id: `whatsapp:${phone}`,
      text: text,
    });
    const replyText = (reply && reply.reply) ? reply.reply
                    : "🏛️ Skyscraper receptionist is briefly offline — try again shortly.";

    await client.sendMessage(from, replyText);
    outboundSent++;
    stamp(SEND_LOG, {
      ts: nowIso(), to: phone, text_head: replyText.slice(0, 240), text_len: replyText.length,
      ok: true, mode: 'auto_reply',
    });
    f47('inbound_reply', { from: phone, reply_head: replyText.slice(0, 120) });
  } catch (e) {
    console.error('[wa_bridge] inbound error:', e.message || e);
    stamp(INBOUND_LOG, { ts: nowIso(), from: msg.from, err: String(e).slice(0, 200) });
  }
});

function postJson(url, obj) {
  return new Promise((resolve) => {
    try {
      const u = new URL(url);
      const body = Buffer.from(JSON.stringify(obj));
      const req = http.request({
        hostname: u.hostname, port: u.port || 80, path: u.pathname,
        method: 'POST',
        headers: {
          'Content-Type': 'application/json',
          'Content-Length': body.length,
        },
        timeout: 8000,
      }, (res) => {
        let buf = '';
        res.on('data', (c) => { buf += c; });
        res.on('end', () => {
          try { resolve(JSON.parse(buf)); } catch (_) { resolve(null); }
        });
      });
      req.on('error', () => resolve(null));
      req.on('timeout', () => { req.destroy(); resolve(null); });
      req.write(body);
      req.end();
    } catch (_) { resolve(null); }
  });
}

// ── HTTP API for outbound send + status ────────────────────────────
const server = http.createServer((req, res) => {
  const send = (code, obj) => {
    const body = JSON.stringify(obj);
    res.writeHead(code, { 'Content-Type': 'application/json', 'Content-Length': Buffer.byteLength(body) });
    res.end(body);
  };
  if (req.method === 'GET' && (req.url === '/' || req.url === '/status' || req.url === '/health')) {
    return send(200, {
      ok: true, ready, uptime_s: Math.floor((Date.now() - started) / 1000),
      inbound_seen: inboundSeen, outbound_sent: outboundSent, ts: nowIso(),
    });
  }
  if (req.method === 'GET' && req.url === '/qr') {
    return send(200, { qr: lastQr, ready });
  }
  if (req.method === 'POST' && req.url === '/send') {
    let chunks = [];
    req.on('data', (c) => chunks.push(c));
    req.on('end', async () => {
      try {
        const body = JSON.parse(Buffer.concat(chunks).toString() || '{}');
        const to = String(body.to || '').trim();
        const text = String(body.text || '');
        if (!/^\+\d{8,15}$/.test(to)) return send(400, { ok: false, err: 'to_must_be_E164' });
        if (!text) return send(400, { ok: false, err: 'text_required' });
        if (!ready) return send(503, { ok: false, err: 'not_ready' });
        const chatId = to.replace(/^\+/, '') + '@c.us';
        const msg = await client.sendMessage(chatId, text);
        outboundSent++;
        stamp(SEND_LOG, {
          ts: nowIso(), to, text_head: text.slice(0, 240), text_len: text.length,
          ok: true, msg_id: msg.id.id, mode: 'api_send',
          from_who: body.from_who || 'unknown',
        });
        f47('outbound_send', { to, from_who: body.from_who || 'unknown', text_head: text.slice(0, 120) });
        return send(200, { ok: true, msg_id: msg.id.id, ts: nowIso() });
      } catch (e) {
        stamp(SEND_LOG, { ts: nowIso(), ok: false, err: String(e).slice(0, 200) });
        return send(500, { ok: false, err: String(e).slice(0, 200) });
      }
    });
    return;
  }
  return send(404, { ok: false, err: 'not_found' });
});

server.listen(HTTP_PORT, '127.0.0.1', () => {
  console.log(`[wa_bridge] HTTP API on 127.0.0.1:${HTTP_PORT}`);
});

client.initialize();
process.on('SIGTERM', () => { try { client.destroy(); } catch(_){} process.exit(0); });
process.on('SIGINT',  () => { try { client.destroy(); } catch(_){} process.exit(0); });
