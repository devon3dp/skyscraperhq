#!/usr/bin/env python3
"""qsb_tunnel_monitor.py — keep the public tunnel alive.

Checks: is preview server up? is tunnel reachable? is URL serving?
If anything fails, attempt restart.

Runs every 5 min via bg_loop. State in qsb_tunnel_monitor_state.json.
"""
from __future__ import annotations
import json, os, subprocess, sys, time, urllib.request
from pathlib import Path
from datetime import datetime, timezone

ROOT = Path('/vaults/nvme0/qsb_tower_v1')
STATE = ROOT / 'data/registries/qsb_tunnel_monitor_state.json'
TOMBSTONE_FILE = ROOT / 'data/registries/qsb_tombstoned_daemons.json'
LOG_TUNNEL = '/tmp/skyscraper/tunnel.log'


def _is_tombstoned(name: str) -> bool:
    try:
        if not TOMBSTONE_FILE.exists():
            return False
        return name in set(json.loads(TOMBSTONE_FILE.read_text()).get('tombstoned', []) or [])
    except Exception:
        return False

def utcnow():
    return datetime.now(timezone.utc).isoformat().replace('+00:00','Z')

def load_state():
    if STATE.exists():
        return json.loads(STATE.read_text())
    return {'last_check': None, 'tunnel_restarts': 0, 'preview_restarts': 0, 'current_url': None}

def save_state(s):
    STATE.write_text(json.dumps(s, indent=2))

def preview_alive():
    try:
        urllib.request.urlopen('http://127.0.0.1:9876/', timeout=3)
        return True
    except: return False

def tunnel_pid():
    r = subprocess.run(['pgrep','-f','cloudflared'], capture_output=True, text=True)
    return r.stdout.strip() if r.returncode == 0 else None

def get_url():
    if not Path(LOG_TUNNEL).exists():
        return None
    import re
    t = Path(LOG_TUNNEL).read_text()
    m = re.findall(r'https://[a-z0-9-]+\.trycloudflare\.com', t)
    return m[-1] if m else None

def url_serving(url):
    if not url: return False
    try:
        r = urllib.request.urlopen(url + '/', timeout=10)
        return r.getcode() == 200
    except: return False

def start_preview():
    Path('logs').mkdir(exist_ok=True)
    subprocess.Popen(['python3','-m','http.server','9876','--bind','127.0.0.1','--directory','web/shops'],
                     stdout=open('/tmp/preview.log','w'), stderr=subprocess.STDOUT, start_new_session=True)
    time.sleep(2)

def start_tunnel():
    Path('/tmp/skyscraper').mkdir(parents=True, exist_ok=True)
    subprocess.Popen(['/tmp/bin/cloudflared','tunnel','--no-autoupdate','--url','http://localhost:9876'],
                     stdout=open(LOG_TUNNEL,'w'), stderr=subprocess.STDOUT, start_new_session=True)
    time.sleep(12)

def main():
    s = load_state()
    s['last_check'] = utcnow()
    actions = []

    # Tombstone short-circuit. If cloudflared is tombstoned, do NOT revive,
    # do NOT start preview just to feed it. Honour the registry.
    if _is_tombstoned('cloudflared'):
        s['current_url'] = None
        s['tombstoned'] = True
        save_state(s)
        print('  tunnel monitor: cloudflared is tombstoned — skipping revive')
        return 0

    # Preview server
    if not preview_alive():
        start_preview()
        s['preview_restarts'] += 1
        actions.append('restarted_preview')

    # Tunnel
    if not tunnel_pid():
        start_tunnel()
        s['tunnel_restarts'] += 1
        actions.append('restarted_tunnel')

    # URL check
    url = get_url()
    if url and not url_serving(url):
        # Tunnel may be alive but unhealthy; restart
        if tunnel_pid():
            subprocess.run(['pkill','-9','-f','cloudflared'])
            time.sleep(2)
            start_tunnel()
            s['tunnel_restarts'] += 1
            actions.append('restarted_unhealthy_tunnel')
        url = get_url()
    
    s['current_url'] = url
    save_state(s)
    
    if actions:
        print(f'  ✓ tunnel monitor: {", ".join(actions)} → URL {url}')
    else:
        print(f'  tunnel ok · URL {url}')
    return 0

if __name__ == '__main__':
    sys.exit(main())
