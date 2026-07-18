#!/usr/bin/env python3
"""
qsb_leadership_enroll.py — mint a ONE-TIME enrollment code for a leadership identity.

The code is single-use and expires (default 15 min). Only its SHA-256 is stored on
the relay (data/registries/leadership_comms/enroll.json). A machine redeems it once at
POST /enroll to receive that identity's token securely — the token is NEVER printed.

  python3 tools/qsb_leadership_enroll.py --identity bill            # mint + show code
  python3 tools/qsb_leadership_enroll.py --identity bill --telegram # also push code to Ross
"""
import argparse, hashlib, json, os, secrets, time

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
COMMS = os.path.join(ROOT, 'data', 'registries', 'leadership_comms')
STORE = os.path.join(COMMS, 'enroll.json')
IDENTITIES = ['wren', 'tp', 'asa', 'bill']


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('--identity', required=True, choices=IDENTITIES)
    ap.add_argument('--ttl', type=int, default=900, help='seconds until expiry (default 900=15min)')
    ap.add_argument('--telegram', action='store_true', help='also push the code to Ross via Telegram')
    a = ap.parse_args()
    os.makedirs(COMMS, exist_ok=True)

    code = secrets.token_urlsafe(9)          # short, single-use
    rec = {'identity': a.identity, 'code_sha256': hashlib.sha256(code.encode()).hexdigest(),
           'created_epoch': time.time(), 'expires_epoch': time.time() + a.ttl, 'used': False}
    try:
        store = json.load(open(STORE))
    except Exception:
        store = {'codes': []}
    # expire/trim old codes
    store['codes'] = [c for c in store.get('codes', []) if not c.get('used')][-50:]
    store['codes'].append(rec)
    json.dump(store, open(STORE, 'w'), indent=2)

    delivered = None
    if a.telegram:
        try:
            import urllib.request, urllib.parse
            def envf(p):
                d = {}
                for l in open(p):
                    l = l.strip()
                    if l and not l.startswith('#') and '=' in l:
                        k, v = l.split('=', 1); d[k] = v.strip().strip('"').strip("'")
                return d
            tg = envf(os.path.join(ROOT, 'floors/floor_28_security_department/vault/.env.telegram'))
            bot = tg.get('QSB_TELEGRAM_BOT_TOKEN')
            chat = tg.get('QSB_TELEGRAM_ALLOWED_CHAT_IDS', '').split(',')[0].strip()
            msg = (f"QSB one-time enrollment code for {a.identity} (expires {a.ttl//60} min, single use):\n"
                   f"{code}\nRun the installer and paste this when asked. Not the token.")
            data = urllib.parse.urlencode({'chat_id': chat, 'text': msg}).encode()
            r = urllib.request.urlopen(f'https://api.telegram.org/bot{bot}/sendMessage', data=data, timeout=15)
            delivered = json.load(r).get('ok')
        except Exception as e:
            delivered = f'FAILED: {e}'

    print(json.dumps({'identity': a.identity, 'ttl_s': a.ttl,
                      'code': code,  # one-time, expiring — NOT the token
                      'telegram_delivered': delivered,
                      'note': 'single-use enrollment code; useless after redemption or expiry'}, indent=2))


if __name__ == '__main__':
    main()
