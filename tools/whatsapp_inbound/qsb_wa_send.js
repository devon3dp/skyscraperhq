// qsb_wa_send.js — one-shot WhatsApp sender using the existing LocalAuth session.
//
// Reuses /vaults/nvme0/qsb_tower_v1/tools/whatsapp_inbound/auth_data
// (same session the inbound bridge uses — Galaxy linked-device from 2026-06-17).
//
// Usage:
//   node qsb_wa_send.js --to +447481057362 --text "hello"
//   node qsb_wa_send.js --to +447481057362 --file /tmp/msg.txt
//
// Audits to data/registries/qsb_wa_sends.jsonl.

const { Client, LocalAuth } = require('whatsapp-web.js');
const fs = require('fs');
const path = require('path');

const ROOT = '/vaults/nvme0/qsb_tower_v1';
const AUDIT = path.join(ROOT, 'data/registries/qsb_wa_sends.jsonl');

function nowIso() { return new Date().toISOString().replace(/\.\d{3}Z$/, 'Z'); }
function audit(row) {
  try { fs.appendFileSync(AUDIT, JSON.stringify(row) + '\n'); } catch (_) {}
}

const args = process.argv.slice(2);
let to = null, text = null;
for (let i = 0; i < args.length; i++) {
  if (args[i] === '--to') to = args[++i];
  else if (args[i] === '--text') text = args[++i];
  else if (args[i] === '--file') text = fs.readFileSync(args[++i], 'utf8');
}
if (!to || !text) {
  console.error('Usage: node qsb_wa_send.js --to +447... --text "..." | --file path');
  process.exit(2);
}
const chatId = to.replace(/^\+/, '') + '@c.us';

const client = new Client({
  authStrategy: new LocalAuth({ dataPath: path.join(__dirname, 'auth_data') }),
  puppeteer: { headless: true, args: ['--no-sandbox', '--disable-setuid-sandbox'] },
});

let sent = false;
const timer = setTimeout(() => {
  if (!sent) {
    console.error('TIMEOUT waiting for ready — session may need re-scan');
    audit({ ts: nowIso(), to, text_len: text.length, ok: false, err: 'timeout' });
    try { client.destroy(); } catch (_) {}
    process.exit(3);
  }
}, 60000);

client.on('qr', (qr) => {
  console.error('QR scan required — session expired. Re-scan via qsb_wa_inbound.js first.');
  clearTimeout(timer);
  process.exit(4);
});

client.on('ready', async () => {
  try {
    const msg = await client.sendMessage(chatId, text);
    sent = true;
    console.log(JSON.stringify({ ok: true, ts: nowIso(), to, msg_id: msg.id.id, text_len: text.length }));
    audit({ ts: nowIso(), to, text_head: text.slice(0, 80), text_len: text.length, ok: true, msg_id: msg.id.id });
    clearTimeout(timer);
    setTimeout(() => { client.destroy().catch(()=>{}); process.exit(0); }, 1500);
  } catch (e) {
    audit({ ts: nowIso(), to, text_len: text.length, ok: false, err: String(e).slice(0, 200) });
    console.error('SEND FAILED:', e.message || e);
    clearTimeout(timer);
    try { client.destroy(); } catch (_) {}
    process.exit(5);
  }
});

client.on('auth_failure', (m) => {
  console.error('AUTH FAILURE:', m);
  clearTimeout(timer);
  process.exit(6);
});

client.initialize();
