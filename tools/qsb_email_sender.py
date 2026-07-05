#!/usr/bin/env python3
"""qsb_email_sender.py — flush outbound queue via SMTP.

Reads qsb_email_outbound_queue.jsonl, sends each, audits, marks sent.
Provider config: same vault file as receiver.

Maps IMAP host → SMTP host:
  outlook.office365.com  → smtp.office365.com:587 STARTTLS
  imap.mail.yahoo.com    → smtp.mail.yahoo.com:587 STARTTLS
  imap.zoho.eu           → smtp.zoho.eu:587 STARTTLS
  imap.fastmail.com      → smtp.fastmail.com:587 STARTTLS
  imap.gmx.com           → mail.gmx.com:587 STARTTLS
  imap.aol.com           → smtp.aol.com:587 STARTTLS
  imap.gmail.com         → smtp.gmail.com:587 STARTTLS
"""
from __future__ import annotations
import json, os, smtplib, sys
from pathlib import Path
from datetime import datetime, timezone
from email.message import EmailMessage

ROOT = Path('/vaults/nvme0/qsb_tower_v1')
REG = ROOT / 'data/registries'
VAULT = ROOT / 'floors/floor_28_security_department/vault'
QUEUE = REG / 'qsb_email_outbound_queue.jsonl'
SENT = REG / 'qsb_email_sent_log.jsonl'

IMAP_TO_SMTP = {
    'outlook.office365.com': ('smtp.office365.com', 587),
    'imap.mail.yahoo.com':   ('smtp.mail.yahoo.com', 587),
    'imap.zoho.eu':          ('smtp.zoho.eu', 587),
    'imap.fastmail.com':     ('smtp.fastmail.com', 587),
    'imap.gmx.com':          ('mail.gmx.com', 587),
    'imap.aol.com':          ('smtp.aol.com', 587),
    'imap.gmail.com':        ('smtp.gmail.com', 587),
}

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
    for f in ['.env.outlook.imap','.env.yahoo.imap','.env.zoho_eu.imap','.env.fastmail.imap',
             '.env.gmx.imap','.env.aol.imap','.env.google.imap','.env.custom.imap']:
        if (VAULT/f).exists() and src_env(f):
            return f
    return None

def main():
    if not QUEUE.exists() or QUEUE.stat().st_size == 0:
        print('  outbound queue empty')
        return 0
    cfg = find_imap_config()
    if not cfg:
        print('  no email config — cannot send')
        return 0
    imap_host = os.environ.get('IMAP_HOST') or os.environ.get('GMAIL_IMAP_HOST')
    smtp = IMAP_TO_SMTP.get(imap_host)
    if not smtp:
        print(f'  no SMTP mapping for {imap_host}')
        return 0
    smtp_host, smtp_port = smtp
    user = os.environ.get('IMAP_EMAIL') or os.environ.get('GMAIL_ADDRESS')
    pwd  = os.environ.get('IMAP_PASSWORD') or os.environ.get('GMAIL_APP_PASSWORD')

    rows = [json.loads(l) for l in QUEUE.read_text().strip().split('\n') if l.strip()]
    if not rows:
        print('  no rows'); return 0

    sent = 0; errors = 0
    try:
        s = smtplib.SMTP(smtp_host, smtp_port, timeout=30)
        s.starttls()
        s.login(user, pwd)
        for r in rows:
            msg = EmailMessage()
            msg['From'] = r.get('from_alias') or user
            msg['To'] = r['to']
            msg['Subject'] = r['subject']
            msg.set_content(r['body'])
            try:
                s.send_message(msg)
                sent += 1
                with SENT.open('a') as f:
                    f.write(json.dumps({**r, 'sent_ts': utcnow()})+'\n')
            except Exception as e:
                errors += 1
                print(f'  ✗ send err to {r["to"]}: {e}')
        s.quit()
    except Exception as e:
        print(f'  ✗ smtp err: {e}')
        return 1
    # Clear the queue (only kept sent + not-yet-sent semantics simple by clearing on success)
    if sent == len(rows):
        QUEUE.write_text('')
    print(f'  ✓ sent {sent}, errors {errors}')
    return 0

if __name__ == '__main__':
    sys.exit(main() or 0)
