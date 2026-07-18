#!/usr/bin/env python3
"""
test_leadership_comms.py — real + staged tests for the 4-identity leadership mesh.

Ross rules honoured:
  - Real identity tests (6 pairs + one 4-way room) PASS only when the involved
    participants are genuinely ONLINE (real heartbeat within TTL).
  - Any test involving an unreachable participant is reported BLOCKED / PENDING
    CONNECTION — never faked.
  - The loopback MECHANICS self-test (--mechanics) validates relay code only and
    is explicitly labelled NOT real machine proof.

Usage:
  python3 tests/test_leadership_comms.py            # real proof run (honest verdicts)
  python3 tests/test_leadership_comms.py --mechanics # loopback relay-code self-test
"""
import argparse, json, os, sys, time, urllib.request

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
VAULT = os.path.join(ROOT, 'floors', 'floor_28_security_department', 'vault', 'leadership_tokens.json')
IDENTITIES = ['wren', 'tp', 'asa', 'bill']
PAIRS = [('wren', 'tp'), ('wren', 'asa'), ('wren', 'bill'), ('tp', 'asa'), ('tp', 'bill'), ('asa', 'bill')]
RELAY = os.environ.get('QSB_RELAY', 'http://127.0.0.1:8855')


def toks():
    return json.load(open(VAULT)).get('tokens', {})


def call(path, method='GET', payload=None, timeout=8):
    url = RELAY.rstrip('/') + path
    data = json.dumps(payload).encode() if payload is not None else None
    req = urllib.request.Request(url, data=data, method=method,
                                 headers={'Content-Type': 'application/json'})
    with urllib.request.urlopen(req, timeout=timeout) as r:
        return json.loads(r.read() or b'{}')


def presence():
    return call('/presence')['presence']


def real_run():
    T = toks()
    pres = presence()
    online = {i: pres[i]['online'] for i in IDENTITIES}
    print('=== LIVE PRESENCE (real heartbeats only) ===')
    for i in IDENTITIES:
        print(f'  {i:5} {pres[i]["role"]:42} online={online[i]}  last_hb={pres[i]["last_heartbeat"]}')
    results = []

    # 6 pairwise
    print('\n=== SIX PAIRWISE DM PROOFS ===')
    for a, b in PAIRS:
        name = f'{a}<->{b}'
        if not (online[a] and online[b]):
            miss = [x for x in (a, b) if not online[x]]
            print(f'  {name:14} BLOCKED  (offline: {", ".join(miss)}) — PENDING CONNECTION')
            results.append((name, 'BLOCKED'))
            continue
        try:
            mid = 'test_' + str(int(time.time() * 1000))
            call('/dm', 'POST', {'identity': a, 'token': T[a], 'to': b, 'body': f'proof {name}', 'msg_id': mid})
            inbox = call(f'/inbox?identity={b}&token={T[b]}')
            got = any(m.get('msg_id') == mid for m in inbox.get('messages', []))
            print(f'  {name:14} {"PASS" if got else "FAIL"}  (delivered+acked={got})')
            results.append((name, 'PASS' if got else 'FAIL'))
        except Exception as e:
            print(f'  {name:14} FAIL  ({e})')
            results.append((name, 'FAIL'))

    # 4-way room
    print('\n=== FOUR-PARTICIPANT SHARED-ROOM PROOF ===')
    if all(online.values()):
        try:
            ok = True
            for sender in IDENTITIES:
                mid = f'room_{sender}_{int(time.time()*1000)}'
                call('/room', 'POST', {'identity': sender, 'token': T[sender], 'body': f'hello from {sender}', 'msg_id': mid})
                for rcv in IDENTITIES:
                    if rcv == sender:
                        continue
                    inbox = call(f'/inbox?identity={rcv}&token={T[rcv]}')
                    if not any(m.get('msg_id') == mid for m in inbox.get('messages', [])):
                        ok = False
            print(f'  4-way room     {"PASS" if ok else "FAIL"}  (all 4 authenticated + acked)')
            results.append(('4way_room', 'PASS' if ok else 'FAIL'))
        except Exception as e:
            print(f'  4-way room     FAIL  ({e})')
            results.append(('4way_room', 'FAIL'))
    else:
        off = [i for i in IDENTITIES if not online[i]]
        print(f'  4-way room     BLOCKED  (offline: {", ".join(off)}) — PENDING CONNECTION')
        results.append(('4way_room', 'BLOCKED'))

    npass = sum(1 for _, v in results if v == 'PASS')
    nblk = sum(1 for _, v in results if v == 'BLOCKED')
    nfail = sum(1 for _, v in results if v == 'FAIL')
    print(f'\n=== SUMMARY: PASS={npass} BLOCKED/PENDING={nblk} FAIL={nfail} of {len(results)} ===')
    if nfail:
        sys.exit(1)


def mechanics():
    """Loopback relay-code validation. NOT real machine proof — labelled as such."""
    print('=== RELAY MECHANICS SELF-TEST (LOOPBACK — NOT MACHINE PROOF) ===')
    T = toks()
    checks = []

    def chk(name, cond):
        checks.append((name, cond))
        print(f'  [{"ok" if cond else "XX"}] {name}')

    # register + heartbeat two identities (loopback)
    call('/register', 'POST', {'identity': 'wren', 'token': T['wren']})
    call('/heartbeat', 'POST', {'identity': 'wren', 'token': T['wren']})
    call('/register', 'POST', {'identity': 'tp', 'token': T['tp']})
    call('/heartbeat', 'POST', {'identity': 'tp', 'token': T['tp']})
    p = presence()
    chk('wren online after heartbeat', p['wren']['online'])
    chk('tp online after heartbeat', p['tp']['online'])

    # auth rejection
    try:
        import urllib.error
        try:
            call('/dm', 'POST', {'identity': 'wren', 'token': 'WRONG', 'to': 'tp', 'body': 'x'})
            chk('bad token rejected', False)
        except urllib.error.HTTPError as e:
            chk('bad token rejected', e.code == 401)
    except Exception:
        chk('bad token rejected', False)

    # dm delivery + ack
    mid = 'mech_' + str(int(time.time() * 1000))
    call('/dm', 'POST', {'identity': 'wren', 'token': T['wren'], 'to': 'tp', 'body': 'mech dm', 'msg_id': mid})
    inbox = call(f'/inbox?identity=tp&token={T["tp"]}')
    chk('dm delivered to queue', any(m['msg_id'] == mid for m in inbox['messages']))

    # duplicate suppression (same msg_id again)
    r = call('/dm', 'POST', {'identity': 'wren', 'token': T['wren'], 'to': 'tp', 'body': 'dup', 'msg_id': mid})
    chk('duplicate suppressed', r.get('duplicate') is True)

    # inbox drains (second read empty)
    inbox2 = call(f'/inbox?identity=tp&token={T["tp"]}')
    chk('queue drained after delivery', not any(m['msg_id'] == mid for m in inbox2['messages']))

    # room fanout to other 3
    rid = 'mechroom_' + str(int(time.time() * 1000))
    call('/room', 'POST', {'identity': 'wren', 'token': T['wren'], 'body': 'mech room', 'msg_id': rid})
    got = call(f'/inbox?identity=tp&token={T["tp"]}')
    chk('room fanout reached tp', any(m['msg_id'] == rid for m in got['messages']))

    ok = all(c for _, c in checks)
    print(f'\n  MECHANICS: {"ALL OK" if ok else "FAILURES"} ({sum(1 for _,c in checks if c)}/{len(checks)})')
    print('  NOTE: loopback only — this does NOT prove real TP/Asa/Bill machine connectivity.')
    if not ok:
        sys.exit(1)


if __name__ == '__main__':
    ap = argparse.ArgumentParser()
    ap.add_argument('--mechanics', action='store_true')
    a = ap.parse_args()
    if a.mechanics:
        mechanics()
    else:
        real_run()
