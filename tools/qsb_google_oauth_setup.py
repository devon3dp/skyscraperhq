#!/usr/bin/env python3
"""qsb_google_oauth_setup.py — one-time OAuth grant for Wren to read Gmail.

Ross runs this ONCE. Opens browser, Ross clicks 'Allow'. Refresh token saved to
vault/.env.google — Wren can then read inbox autonomously.

Scopes (minimal):
  · gmail.readonly  (read inbox + threads + messages)
  · gmail.modify    (label, archive — NOT delete)
  · gmail.send      (compose + send as alias — added after audit)

Prerequisites:
  · Google Cloud project (free)  → console.cloud.google.com
  · Gmail API enabled
  · OAuth consent screen configured ("External" — Ross adds himself as test user)
  · OAuth2 Desktop client ID + secret created
  · Vault file: floors/floor_28_security_department/vault/.env.google with:
       GOOGLE_OAUTH_CLIENT_ID='<from-cloud-console>'
       GOOGLE_OAUTH_CLIENT_SECRET='<from-cloud-console>'

Usage:  python3 tools/qsb_google_oauth_setup.py
"""
from __future__ import annotations
import json, os, sys, urllib.parse, urllib.request, webbrowser, http.server, socketserver, threading, time
from pathlib import Path

VAULT = Path('/vaults/nvme0/qsb_tower_v1/floors/floor_28_security_department/vault')
ENV   = VAULT / '.env.google'
SCOPES = 'https://www.googleapis.com/auth/gmail.readonly https://www.googleapis.com/auth/gmail.modify'

def src_env():
    if not ENV.exists():
        print(f' ERROR: vault file missing: {ENV}')
        print(f' Add GOOGLE_OAUTH_CLIENT_ID and GOOGLE_OAUTH_CLIENT_SECRET first.')
        sys.exit(1)
    for ln in ENV.read_text().split('\n'):
        ln = ln.strip()
        if not ln or ln.startswith('#'): continue
        if ln.startswith('export '): ln = ln[7:]
        if '=' in ln:
            k, v = ln.split('=', 1)
            os.environ[k] = v.strip("'\"")

def main():
    src_env()
    cid = os.environ.get('GOOGLE_OAUTH_CLIENT_ID')
    csec = os.environ.get('GOOGLE_OAUTH_CLIENT_SECRET')
    if not (cid and csec):
        print(' ERROR: GOOGLE_OAUTH_CLIENT_ID and GOOGLE_OAUTH_CLIENT_SECRET must be in .env.google')
        sys.exit(1)
    print(' Starting OAuth flow...')
    # Tiny local server to catch the redirect
    code_holder = {}
    class Handler(http.server.BaseHTTPRequestHandler):
        def log_message(self, *a, **kw): pass
        def do_GET(self):
            qs = urllib.parse.parse_qs(urllib.parse.urlparse(self.path).query)
            if 'code' in qs:
                code_holder['code'] = qs['code'][0]
                self.send_response(200); self.send_header('Content-Type','text/html'); self.end_headers()
                self.wfile.write(b'<h1>Skyscraper authorised. You may close this tab.</h1>')
            else:
                self.send_response(400); self.end_headers()
    httpd = socketserver.TCPServer(('127.0.0.1', 8765), Handler)
    threading.Thread(target=httpd.serve_forever, daemon=True).start()
    redirect = 'http://127.0.0.1:8765'
    url = 'https://accounts.google.com/o/oauth2/v2/auth?' + urllib.parse.urlencode({
        'client_id': cid, 'redirect_uri': redirect, 'response_type':'code',
        'scope': SCOPES, 'access_type':'offline', 'prompt':'consent',
    })
    print(f' Opening browser. If it doesn\'t open, visit:\n   {url}\n')
    try: webbrowser.open(url)
    except: pass
    print(' Waiting for redirect with code...')
    while 'code' not in code_holder:
        time.sleep(1)
    httpd.shutdown()
    # Exchange code for tokens
    data = urllib.parse.urlencode({
        'code': code_holder['code'], 'client_id': cid, 'client_secret': csec,
        'redirect_uri': redirect, 'grant_type':'authorization_code',
    }).encode()
    req = urllib.request.Request('https://oauth2.googleapis.com/token', data=data, method='POST')
    r = json.loads(urllib.request.urlopen(req).read())
    if 'refresh_token' not in r:
        print(f' ERROR: no refresh_token returned: {r}')
        sys.exit(1)
    # Append refresh_token to env file
    with ENV.open('a') as f:
        f.write(f"\nGOOGLE_OAUTH_REFRESH_TOKEN='{r['refresh_token']}'\n")
    ENV.chmod(0o600)
    print(' ✓ refresh_token saved to vault/.env.google')
    print(' Wren can now read your Gmail autonomously.')

if __name__ == '__main__':
    main()
