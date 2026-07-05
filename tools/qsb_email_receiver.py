#!/usr/bin/env python3
"""qsb_email_receiver.py — poll any IMAP inbox + triage + queue replies.

Reads vault/.env.outlook.imap or whichever IMAP config exists. Polls INBOX
for new messages since last_seen_uid, runs qsb_email_triage classifier on
each, drafts replies, queues to qsb_email_outbound_queue.jsonl.

Runs every 5 min via bg_loop.
"""
from __future__ import annotations
import imaplib, json, os, email, sys, subprocess
from pathlib import Path
from datetime import datetime, timezone
from email.header import decode_header

ROOT = Path('/vaults/nvme0/qsb_tower_v1')
REG  = ROOT / 'data/registries'
VAULT = ROOT / 'floors/floor_28_security_department/vault'
STATE = REG / 'qsb_email_receiver_state.json'
INBOX_LOG = REG / 'qsb_email_inbox_log.jsonl'
OUTBOUND_Q = REG / 'qsb_email_outbound_queue.jsonl'

def utcnow():
    return datetime.now(timezone.utc).isoformat().replace('+00:00','Z')

def src_env(filename):
    p = VAULT / filename
    if not p.exists(): return False
    for ln in p.read_text().split('\n'):
        ln = ln.strip()
        if not ln or ln.startswith('#'): continue
        if ln.startswith('export '): ln = ln[7:]
        if '=' in ln:
            k, v = ln.split('=', 1)
            os.environ[k] = v.strip("'\"")
    return True

def find_imap_config():
    """Try IMAP configs in order of preference."""
    for f in ['.env.outlook.imap', '.env.yahoo.imap', '.env.zoho_eu.imap', '.env.fastmail.imap',
             '.env.gmx.imap', '.env.aol.imap', '.env.google.imap', '.env.custom.imap']:
        if (VAULT / f).exists() and src_env(f):
            return f
    return None

def load_state():
    if STATE.exists():
        return json.loads(STATE.read_text())
    return {'last_uid': 0, 'total_processed': 0}

def save_state(s):
    STATE.write_text(json.dumps(s, indent=2))

def decode(s):
    if not s: return ''
    parts = decode_header(s)
    out = []
    for txt, enc in parts:
        if isinstance(txt, bytes):
            out.append(txt.decode(enc or 'utf-8', errors='ignore'))
        else:
            out.append(txt)
    return ''.join(out)

def extract_body(msg):
    if msg.is_multipart():
        for part in msg.walk():
            ct = part.get_content_type()
            if ct == 'text/plain':
                try: return part.get_payload(decode=True).decode(errors='ignore')
                except: pass
    else:
        try: return msg.get_payload(decode=True).decode(errors='ignore')
        except: return ''
    return ''

def main():
    cfg = find_imap_config()
    if not cfg:
        print('  no IMAP config found in vault — skip')
        return 0
    host = os.environ.get('IMAP_HOST') or os.environ.get('GMAIL_IMAP_HOST')
    port = int(os.environ.get('IMAP_PORT') or os.environ.get('GMAIL_IMAP_PORT') or 993)
    user = os.environ.get('IMAP_EMAIL') or os.environ.get('GMAIL_ADDRESS')
    pwd  = os.environ.get('IMAP_PASSWORD') or os.environ.get('GMAIL_APP_PASSWORD')
    if not (host and user and pwd):
        print(f'  incomplete IMAP config in {cfg} — skip')
        return 0
    s = load_state()
    try:
        m = imaplib.IMAP4_SSL(host, port)
        m.login(user, pwd)
        m.select('INBOX')
        typ, data = m.search(None, f'UID {s["last_uid"]+1}:*')
        uids = data[0].split() if data and data[0] else []
        new_count = 0
        for uid in uids:
            uid_n = int(uid)
            if uid_n <= s['last_uid']: continue
            typ, msg_data = m.uid('FETCH', uid, '(RFC822)')
            if typ != 'OK' or not msg_data or not msg_data[0]: continue
            raw = msg_data[0][1]
            msg = email.message_from_bytes(raw)
            from_addr = decode(msg.get('From',''))
            to_addr = decode(msg.get('To',''))
            subj = decode(msg.get('Subject',''))
            body = extract_body(msg)
            # Classify
            result = subprocess.run(
                ['python3', 'tools/qsb_email_triage.py'],
                input=body, capture_output=True, text=True, timeout=10
            )
            triage = json.loads(result.stdout) if result.stdout else {'class':'unknown','suggested_action':'escalate','reply_draft':''}
            # Identify shop by + tag in to_addr
            shop = None
            import re
            m_tag = re.search(r'\+([a-z]+)@', to_addr)
            if m_tag: shop = m_tag.group(1)
            # Log inbox
            row = {
                'ts': utcnow(), 'uid': uid_n,
                'from': from_addr, 'to': to_addr,
                'subject': subj,
                'shop_inferred': shop,
                'class': triage['class'],
                'suggested_action': triage['suggested_action'],
            }
            with INBOX_LOG.open('a') as f:
                f.write(json.dumps(row) + '\n')
            # Queue auto-reply (subject to leak audit)
            if triage['reply_draft'] and triage['class'] not in ('spam_or_marketing','order_confirmation'):
                # leak-audit reply draft first
                la = subprocess.run(
                    ['python3', 'tools/qsb_leak_audit.py', '--string', triage['reply_draft']],
                    capture_output=True, text=True, timeout=5
                )
                if la.returncode == 0:  # clean
                    with OUTBOUND_Q.open('a') as f:
                        f.write(json.dumps({
                            'ts': utcnow(), 'to': from_addr,
                            'subject': f'Re: {subj}',
                            'body': triage['reply_draft'],
                            'from_alias': to_addr,
                            'in_reply_to_uid': uid_n,
                            'class': triage['class'],
                        }) + '\n')
                else:
                    print(f'  ⚠ reply draft for uid {uid_n} blocked by leak audit')
            new_count += 1
            s['last_uid'] = uid_n
            s['total_processed'] += 1
        m.logout()
        save_state(s)
        if new_count:
            print(f'  ✓ {new_count} new email(s) processed and triaged')
        else:
            print(f'  no new email (total processed lifetime: {s["total_processed"]})')
    except Exception as e:
        print(f'  err: {e}')
        return 1
    return 0

if __name__ == '__main__':
    sys.exit(main() or 0)
