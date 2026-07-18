#!/usr/bin/env python3
"""
qsb_leadership_client.py — outbound client for a single leadership identity.

Run one instance per machine, one per identity: wren, tp, asa, bill.
It maintains an AUTHENTICATED OUTBOUND session to the canonical relay — no
inbound port is opened on the client, so it works behind NAT / macOS security /
firewalls (Ross order #6).

    python3 tools/qsb_leadership_client.py --identity tp \
        --relay http://192.168.1.84:8855 --token-file /path/to/token

Behaviour:
  - registers, then heartbeats every --hb seconds (keeps presence "online")
  - polls /inbox every --poll seconds, prints + acks received messages
  - auto-reconnects with backoff on any network/relay failure (Ross order:
    "Automatic reconnection after network or relay failure")
  - send a message ad-hoc:  --send-room "hello all"   or   --send-dm wren "hi"

The token can be supplied via --token, --token-file, or env QSB_LEADER_TOKEN.
On Wren's own box the token is read from the vault automatically if present.
"""
import argparse, json, os, sys, time, urllib.request, urllib.error

IDENTITIES = ['wren', 'tp', 'asa', 'bill']
ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
VAULT = os.path.join(ROOT, 'floors', 'floor_28_security_department', 'vault', 'leadership_tokens.json')


def get_token(ident, args):
    if args.token:
        return args.token
    if args.token_file and os.path.exists(args.token_file):
        return open(args.token_file).read().strip()
    if os.environ.get('QSB_LEADER_TOKEN'):
        return os.environ['QSB_LEADER_TOKEN']
    if os.path.exists(VAULT):  # local (Wren's box) convenience
        try:
            return json.load(open(VAULT)).get('tokens', {}).get(ident)
        except Exception:
            pass
    return None


def call(relay, path, method='GET', payload=None, timeout=8):
    url = relay.rstrip('/') + path
    data = json.dumps(payload).encode() if payload is not None else None
    req = urllib.request.Request(url, data=data, method=method,
                                 headers={'Content-Type': 'application/json'})
    with urllib.request.urlopen(req, timeout=timeout) as r:
        return json.loads(r.read() or b'{}')


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('--identity', required=True, choices=IDENTITIES)
    ap.add_argument('--relay', default='http://127.0.0.1:8855')
    ap.add_argument('--token', default=None)
    ap.add_argument('--token-file', default=None)
    ap.add_argument('--hb', type=int, default=5, help='heartbeat seconds')  # 2026-07-18 Ross: 5s live presence (was 30s)
    ap.add_argument('--poll', type=int, default=5, help='inbox poll seconds')
    ap.add_argument('--send-room', default=None)
    ap.add_argument('--send-dm', nargs=2, metavar=('TO', 'BODY'), default=None)
    ap.add_argument('--once', action='store_true', help='register+heartbeat+drain once then exit')
    a = ap.parse_args()

    token = get_token(a.identity, a)
    if not token:
        print(f'FATAL: no token for {a.identity} (use --token/--token-file/QSB_LEADER_TOKEN)', file=sys.stderr)
        sys.exit(2)
    auth = {'identity': a.identity, 'token': token}

    # one-shot sends
    if a.send_room is not None:
        print(json.dumps(call(a.relay, '/room', 'POST', dict(auth, body=a.send_room))))
        return
    if a.send_dm is not None:
        to, body = a.send_dm
        print(json.dumps(call(a.relay, '/dm', 'POST', dict(auth, to=to, body=body))))
        return

    def register():
        r = call(a.relay, '/register', 'POST', dict(auth, addr=None))
        print(f'[{a.identity}] registered session={r.get("session_id")}')

    def heartbeat():
        call(a.relay, '/heartbeat', 'POST', auth)

    def drain():
        r = call(a.relay, f'/inbox?identity={a.identity}&token={token}')
        for m in r.get('messages', []):
            print(f'[{a.identity}] <- {m.get("kind")} from {m.get("from")}: {m.get("body")}  ({m.get("msg_id")})')
            try:
                call(a.relay, '/ack', 'POST', dict(auth, msg_id=m.get('msg_id')))
            except Exception:
                pass
        return r.get('count', 0)

    if a.once:
        register(); heartbeat(); drain(); return

    # persistent loop with auto-reconnect + backoff
    backoff = 1
    last_hb = 0
    print(f'[{a.identity}] outbound client -> {a.relay} (hb={a.hb}s poll={a.poll}s)')
    while True:
        try:
            register()
            backoff = 1
            while True:
                now = time.time()
                if now - last_hb >= a.hb:
                    heartbeat(); last_hb = now
                drain()
                time.sleep(a.poll)
        except (urllib.error.URLError, ConnectionError, OSError) as e:
            print(f'[{a.identity}] relay unreachable ({e}); reconnect in {backoff}s', file=sys.stderr)
            time.sleep(backoff)
            backoff = min(backoff * 2, 60)  # exponential backoff, capped
        except KeyboardInterrupt:
            print(f'[{a.identity}] stopped'); return


if __name__ == '__main__':
    main()
