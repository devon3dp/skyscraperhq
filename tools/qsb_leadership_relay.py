#!/usr/bin/env python3
"""
qsb_leadership_relay.py — canonical leadership communications relay.

Ross canonical correction (2026-07-17):
    "Claude HQ is retired. Claude is a governed specialist service caged under
     Wren. The active leadership roster is Wren, TP, Asa, and Bill."

Exactly FOUR identities: wren, tp, asa, bill.
  - one shared four-member leadership room
  - six bidirectional direct-message relationships
  - token authentication, stable canonical identities
  - presence + heartbeat monitoring (online ONLY on a received heartbeat)
  - message ids + timestamps, delivery acknowledgements
  - persistent offline queues, duplicate suppression
  - persistent history / audit evidence
  - health + status endpoints, automatic startup (systemd)

Design constraints from Ross:
  - Clients maintain AUTHENTICATED OUTBOUND connections to this relay
    (works behind NAT / macOS security; no unsolicited inbound needed).
  - EXPLICIT SEPARATION from executable Task Council work: this relay only
    moves messages. It NEVER executes code or tower actions. Any operational
    request that arrives as a message must be submitted to the Task Council
    separately — the relay will not act on message content.
  - Claude is NOT a participant. There is no claude/hq identity here.

Storage (all under data/registries/leadership_comms/):
    room.jsonl                 append-only shared-room history (audit)
    dm/<a>__<b>.jsonl          append-only per-pair DM history (audit)
    queues/<id>.jsonl          per-identity offline queue (pending delivery)
    delivered/<id>.jsonl       per-identity delivered+acked log (audit)
    acks.jsonl                 append-only delivery acknowledgements
    presence.json              live presence (rebuilt from heartbeats)
    seen/<id>.json             per-sender msg_id set (duplicate suppression)

Tokens live in the vault (leadership_tokens.json, 0600) — never in this file,
never in logs, never in evidence.
"""
import json, os, sys, time, uuid, threading, argparse
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from urllib.parse import urlparse, parse_qs

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
COMMS = os.path.join(ROOT, 'data', 'registries', 'leadership_comms')
VAULT = os.path.join(ROOT, 'floors', 'floor_28_security_department', 'vault', 'leadership_tokens.json')

IDENTITIES = ['wren', 'tp', 'asa', 'bill']
ROLES = {'wren': 'Resident Governor (Linux MSI/Fortress 3)', 'tp': 'ThinkPad CEO',
         'asa': 'Acer CEO', 'bill': 'MacBook Executive Concierge AI'}
HEARTBEAT_TTL = 20  # seconds; online only if last heartbeat within this window
# 2026-07-18 Ross: heartbeat every 5s -> TTL 20s (tolerates ~3 missed beats over
# the Pi/wifi). Was 90s/30s-beat. Clients must beat at <=5s or they read stale.

_LOCK = threading.Lock()


def now_iso():
    return time.strftime('%Y-%m-%dT%H:%M:%SZ', time.gmtime())


def pair_key(a, b):
    return '__'.join(sorted([a, b]))


def _paths():
    for sub in ('', 'dm', 'queues', 'delivered', 'seen'):
        os.makedirs(os.path.join(COMMS, sub), exist_ok=True)


def load_tokens():
    try:
        return json.load(open(VAULT)).get('tokens', {})
    except Exception:
        return {}


ENROLL_STORE = os.path.join(COMMS, 'enroll.json')


def _sha256(s):
    import hashlib
    return hashlib.sha256(s.encode()).hexdigest()


def consume_enroll(code):
    """One-time enrollment: return identity's token if code valid+unused+unexpired, else None.
    Stored file holds only the SHA256 of the code (never the plaintext code or token)."""
    try:
        recs = json.load(open(ENROLL_STORE))
    except Exception:
        return None, None
    h = _sha256(code)
    now = time.time()
    changed = False
    ident = None
    for r in recs.get('codes', []):
        if r.get('code_sha256') == h and not r.get('used') and now < r.get('expires_epoch', 0):
            r['used'] = True
            r['used_at'] = now_iso()
            ident = r.get('identity')
            changed = True
            break
    if changed:
        json.dump(recs, open(ENROLL_STORE, 'w'), indent=2)
    if ident:
        return ident, load_tokens().get(ident)
    return None, None


def append_jsonl(path, obj):
    with open(path, 'a') as f:
        f.write(json.dumps(obj) + '\n')


def read_jsonl(path):
    if not os.path.exists(path):
        return []
    out = []
    for line in open(path):
        line = line.strip()
        if not line:
            continue
        try:
            out.append(json.loads(line))
        except Exception:
            pass
    return out


def seen_path(sender):
    return os.path.join(COMMS, 'seen', sender + '.json')


def already_seen(sender, msg_id):
    p = seen_path(sender)
    try:
        s = set(json.load(open(p)))
    except Exception:
        s = set()
    if msg_id in s:
        return True
    s.add(msg_id)
    json.dump(sorted(s)[-5000:], open(p, 'w'))  # cap growth
    return False


def load_presence():
    p = os.path.join(COMMS, 'presence.json')
    try:
        return json.load(open(p))
    except Exception:
        return {}


def save_presence(pres):
    json.dump(pres, open(os.path.join(COMMS, 'presence.json'), 'w'), indent=2)


def live_presence():
    """Return online/offline for the 4 identities based on heartbeat TTL."""
    pres = load_presence()
    now = time.time()
    out = {}
    for i in IDENTITIES:
        rec = pres.get(i, {})
        last = rec.get('last_heartbeat_epoch')
        online = bool(last and (now - last) <= HEARTBEAT_TTL)
        out[i] = {
            'id': i, 'role': ROLES[i],
            'registered': rec.get('registered', False),
            'online': online,
            'last_heartbeat': rec.get('last_heartbeat'),
            'reachable_addr': rec.get('reachable_addr'),
            'session_id': rec.get('session_id'),
            'age_s': (round(now - last) if last else None),
        }
    return out


def enqueue(recipient, msg):
    append_jsonl(os.path.join(COMMS, 'queues', recipient + '.jsonl'), msg)


def drain_inbox(identity):
    """Return pending msgs, move them to delivered, write acks. Atomic-ish under lock."""
    qpath = os.path.join(COMMS, 'queues', identity + '.jsonl')
    pending = read_jsonl(qpath)
    if not pending:
        return []
    dlv = os.path.join(COMMS, 'delivered', identity + '.jsonl')
    for m in pending:
        m2 = dict(m, delivered_at=now_iso())
        append_jsonl(dlv, m2)
        append_jsonl(os.path.join(COMMS, 'acks.jsonl'),
                     {'msg_id': m.get('msg_id'), 'to': identity, 'from': m.get('from'),
                      'kind': m.get('kind'), 'delivered_at': now_iso()})
    open(qpath, 'w').close()  # clear queue (delivered+acked recorded above)
    return pending


class Handler(BaseHTTPRequestHandler):
    server_version = 'QSBLeadershipRelay/1'

    def log_message(self, *a):
        pass  # quiet; audit is in the jsonl files, not stderr

    # ---- helpers ----
    def _send(self, code, obj):
        body = json.dumps(obj).encode()
        self.send_response(code)
        self.send_header('Content-Type', 'application/json')
        self.send_header('Content-Length', str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def _body(self):
        n = int(self.headers.get('Content-Length', 0) or 0)
        if not n:
            return {}
        try:
            return json.loads(self.rfile.read(n) or b'{}')
        except Exception:
            return {}

    def _auth(self, data):
        """Return identity if token valid, else None. Token via body or X-QSB-Token header."""
        ident = (data.get('identity') or data.get('from') or data.get('frm')
                 or self.headers.get('X-QSB-Identity') or '').lower().strip()
        token = data.get('token') or self.headers.get('X-QSB-Token') or ''
        toks = load_tokens()
        if ident in IDENTITIES and token and token == toks.get(ident):
            return ident
        return None

    # ---- routes ----
    def do_GET(self):
        u = urlparse(self.path)
        path, q = u.path, parse_qs(u.query)
        if path == '/health':
            return self._send(200, {'ok': True, 'service': 'qsb_leadership_relay',
                                    'ts': now_iso(), 'identities': IDENTITIES,
                                    'roster': 'Wren, TP, Asa, Bill', 'claude_hq': 'retired'})
        if path in ('/client', '/install'):
            # serve source files so a machine with no inbound access (e.g. Bill's Mac)
            # can fetch + run them. /client = python client; /install = macOS installer.
            fn = 'qsb_leadership_client.py' if path == '/client' else 'qsb_bill_mac_install.sh'
            ctype = 'text/x-python' if path == '/client' else 'text/x-shellscript'
            try:
                src = open(os.path.join(ROOT, 'tools', fn), 'rb').read()
            except Exception:
                return self._send(500, {'error': f'{fn} unavailable'})
            self.send_response(200)
            self.send_header('Content-Type', ctype)
            self.send_header('Content-Length', str(len(src)))
            self.end_headers()
            self.wfile.write(src)
            return
        if path == '/presence':
            return self._send(200, {'ts': now_iso(), 'presence': live_presence()})
        if path == '/status':
            with _LOCK:
                pres = live_presence()
                qd = {i: len(read_jsonl(os.path.join(COMMS, 'queues', i + '.jsonl'))) for i in IDENTITIES}
                room_n = len(read_jsonl(os.path.join(COMMS, 'room.jsonl')))
                dmc = {}
                dmdir = os.path.join(COMMS, 'dm')
                if os.path.isdir(dmdir):
                    for fn in os.listdir(dmdir):
                        dmc[fn[:-6]] = len(read_jsonl(os.path.join(dmdir, fn)))
            return self._send(200, {
                'ts': now_iso(), 'service': 'qsb_leadership_relay',
                'canonical_statement': ('Claude HQ is retired. Claude is a governed specialist service '
                                        'caged under Wren. The active leadership roster is Wren, TP, Asa, and Bill.'),
                'presence': pres, 'queue_depth': qd, 'room_messages': room_n,
                'dm_pair_messages': dmc, 'heartbeat_ttl_s': HEARTBEAT_TTL,
                'separation': 'Messaging only. Relay never executes code or Task Council work.'})
        if path == '/inbox':
            ident = (q.get('identity', [''])[0] or '').lower()
            token = q.get('token', [''])[0]
            if not (ident in IDENTITIES and token == load_tokens().get(ident)):
                return self._send(401, {'error': 'unauthorized'})
            with _LOCK:
                msgs = drain_inbox(ident)
            return self._send(200, {'identity': ident, 'count': len(msgs), 'messages': msgs})
        return self._send(404, {'error': 'not found', 'path': path})

    def do_POST(self):
        u = urlparse(self.path)
        path = u.path
        data = self._body()

        if path == '/register':
            ident = self._auth(data)
            if not ident:
                return self._send(401, {'error': 'unauthorized'})
            addr = data.get('addr') or self.client_address[0]
            sid = 'sess_' + uuid.uuid4().hex[:12]
            with _LOCK:
                pres = load_presence()
                rec = pres.get(ident, {})
                rec.update({'registered': True, 'reachable_addr': addr, 'session_id': sid,
                            'registered_at': now_iso()})
                # registration does NOT mark online — only a heartbeat does
                pres[ident] = rec
                save_presence(pres)
            return self._send(200, {'ok': True, 'identity': ident, 'session_id': sid,
                                    'role': ROLES[ident], 'note': 'registered; send /heartbeat to go online'})

        if path == '/heartbeat':
            ident = self._auth(data)
            if not ident:
                return self._send(401, {'error': 'unauthorized'})
            with _LOCK:
                pres = load_presence()
                rec = pres.get(ident, {})
                rec['last_heartbeat'] = now_iso()
                rec['last_heartbeat_epoch'] = time.time()
                if data.get('addr'):
                    rec['reachable_addr'] = data['addr']
                pres[ident] = rec
                save_presence(pres)
            return self._send(200, {'ok': True, 'identity': ident, 'online': True, 'ts': now_iso()})

        if path == '/dm':
            frm = self._auth(data)
            to = (data.get('to') or '').lower().strip()
            body = data.get('body')
            if not frm:
                return self._send(401, {'error': 'unauthorized'})
            if to not in IDENTITIES or to == frm or body is None:
                return self._send(400, {'error': 'bad dm (to must be another identity, body required)'})
            msg_id = data.get('msg_id') or ('m_' + uuid.uuid4().hex[:16])
            ts = data.get('ts') or now_iso()
            with _LOCK:
                if already_seen(frm, msg_id):
                    return self._send(200, {'ok': True, 'duplicate': True, 'msg_id': msg_id})
                msg = {'msg_id': msg_id, 'kind': 'dm', 'from': frm, 'to': to, 'ts': ts, 'body': body}
                append_jsonl(os.path.join(COMMS, 'dm', pair_key(frm, to) + '.jsonl'), msg)
                enqueue(to, msg)
            return self._send(200, {'ok': True, 'msg_id': msg_id, 'queued_to': to})

        if path == '/room':
            frm = self._auth(data)
            body = data.get('body')
            if not frm:
                return self._send(401, {'error': 'unauthorized'})
            if body is None:
                return self._send(400, {'error': 'body required'})
            msg_id = data.get('msg_id') or ('r_' + uuid.uuid4().hex[:16])
            ts = data.get('ts') or now_iso()
            with _LOCK:
                if already_seen(frm, msg_id):
                    return self._send(200, {'ok': True, 'duplicate': True, 'msg_id': msg_id})
                msg = {'msg_id': msg_id, 'kind': 'room', 'from': frm, 'to': 'room', 'ts': ts, 'body': body}
                append_jsonl(os.path.join(COMMS, 'room.jsonl'), msg)
                for other in IDENTITIES:
                    if other != frm:
                        enqueue(other, msg)
            return self._send(200, {'ok': True, 'msg_id': msg_id, 'fanout': [i for i in IDENTITIES if i != frm]})

        if path == '/enroll':
            # one-time enrollment: exchange a single-use code for the identity's token.
            # This is how a machine gets its FIRST token securely (token never printed).
            code = data.get('code')
            if not code:
                return self._send(400, {'error': 'code required'})
            ident, token = consume_enroll(str(code))
            if not ident or not token:
                return self._send(401, {'error': 'invalid, used, or expired enrollment code'})
            return self._send(200, {'ok': True, 'identity': ident, 'token': token,
                                    'relay': 'qsb_leadership_relay'})

        if path == '/ack':
            ident = self._auth(data)
            mid = data.get('msg_id')
            if not ident or not mid:
                return self._send(400, {'error': 'identity/token + msg_id required'})
            with _LOCK:
                append_jsonl(os.path.join(COMMS, 'acks.jsonl'),
                             {'msg_id': mid, 'to': ident, 'ack_by_client': True, 'ts': now_iso()})
            return self._send(200, {'ok': True, 'acked': mid})

        return self._send(404, {'error': 'not found', 'path': path})


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('--host', default='0.0.0.0')
    ap.add_argument('--port', type=int, default=8855)
    a = ap.parse_args()
    _paths()
    if not load_tokens():
        print('FATAL: no leadership tokens in vault — run token generation first', file=sys.stderr)
        sys.exit(2)
    srv = ThreadingHTTPServer((a.host, a.port), Handler)
    print(f'qsb_leadership_relay listening on {a.host}:{a.port} — identities={IDENTITIES}')
    srv.serve_forever()


if __name__ == '__main__':
    main()
