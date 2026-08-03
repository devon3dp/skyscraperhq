#!/usr/bin/env python3
"""
qsb_ceo_room_bridge.py — makes TP (Pip) and Asa (Cass) TWO-WAY participants in the four-way
leadership room by bridging their REAL :9120 cockpit minds into the relay (2026-07-19, Ross:
"tp need a chat endpoint ??? yes").

Their :9120 cockpit already answers direct chat, but nothing replied AS them in the relay room
(they received + acked, never spoke) — the same one-way gap Bill had. This bridge runs on the
always-on relay box (.72) so their four-way presence + replies don't depend on their Windows
boxes running a client. For each bridged CEO it:
  - registers + heartbeats on the relay (presence stays fresh, advertised at their real box IP)
  - polls their relay INBOX
  - generates a reply ONLY for messages that are legitimately addressed to it
  - posts that reply to the room, tagged as them

NOT impersonation: the words come from the CEO's own cockpit model — identical to the hub
/ceo_mind path. The bridge is transport plumbing only. No secrets in this file; relay tokens
are read from the vault at runtime.

============================================================================================
LOOP FIX (2026-07-19)
--------------------------------------------------------------------------------------------
ROOT CAUSE of the endless TP/Asa/Bill ping-pong: the relay's /room POST fans EVERY room
message out to EVERY other identity's inbox (relay ~line 381: `enqueue(other, msg)`). The old
bridge auto-replied to ANY inbox message whose `from` != itself. So:
    TP posts to room -> Asa's inbox gets it -> Asa auto-replies to room ->
    TP's inbox gets Asa's reply -> TP auto-replies -> ... forever.
Each reply is a fresh msg_id, so the `seen` set never breaks the cycle.

The fix here (bridge-side, no relay change required) is a strict REPLY-WORTHINESS gate. A
bridged identity now auto-replies ONLY when the inbound message is genuinely FOR it:

  (a) kind == "dm" addressed to this identity, OR
  (b) a room message that @mentions this identity (e.g. "@tp"), OR
  (c) a room/dm message whose `from` == "ross" (a human).

It NEVER auto-replies to another CEO/bot's room broadcast. Additional loop guards:

  - never reply to a message whose `from` is any bridged/bot identity
    (wren/tp/asa/bill or any *_bridge / *_bot suffix) — even if @mentioned;
  - per-identity rate-limit: at most 1 auto-reply every MIN_REPLY_GAP_S seconds;
  - bounded rounds per conversation (correlation_id, else the peer `from`): at most
    MAX_ROUNDS_PER_CONV auto-replies to the same conversation, then it goes quiet;
  - skip messages that look like auto-replies (marked auto_reply / re: prefix);
  - our own outbound replies are tagged {auto_reply: true, in_reply_to, correlation_id}
    so downstream bridges recognise + drop them.

A tiny OPTIONAL relay tweak (see FIX_REPORT.md unified diff) stamps room messages with a
`correlation_id` and would let the relay fan room messages ONLY to @mentioned identities, but
this bridge is safe WITHOUT any relay change and is fully backward compatible.
============================================================================================
"""
import os, sys, json, time, re, urllib.request

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
VAULT = os.path.join(ROOT, "floors", "floor_28_security_department", "vault", "leadership_tokens.json")
RELAY = os.environ.get("QSB_RELAY", "http://127.0.0.1:8855")

# relay identity -> (real box IP for presence, its cockpit chat endpoint)
BRIDGED = {
    # mDNS hostnames, not IPs — the boxes' DHCP leases drift (Asa .41->.60, 2026-07-30) which
    # silently broke Asa's room replies. Hostnames survive drift (matches the work-mode pusher fix).
    "tp":  {"addr": "DESKTOP-9RBVKSM.local", "cockpit": "http://DESKTOP-9RBVKSM.local:9120/api/chat"},  # tp_pip ThinkPad
    "asa": {"addr": "DESKTOP-1E2FB5N.local", "cockpit": "http://DESKTOP-1E2FB5N.local:9000/message"},  # acer_cass Acer — :9000/message is her LIVE cockpit (:9120 died); {prompt}/{reply} compatible (Claude 2026-08-03)
}

# ---- loop-guard config ----------------------------------------------------------------
# any `from` matching these is a machine/bot (never auto-reply to it, even if @mentioned)
BOT_IDENTITIES = {"wren", "tp", "asa", "bill"}
BOT_SUFFIXES = ("_bridge", "_bot", "-bridge", "-bot")
HUMAN_SENDERS = {"ross"}                 # senders we always treat as reply-worthy
MIN_REPLY_GAP_S = float(os.environ.get("QSB_BRIDGE_MIN_REPLY_GAP", "15"))  # >=1 reply / 15s / identity
MAX_ROUNDS_PER_CONV = int(os.environ.get("QSB_BRIDGE_MAX_ROUNDS", "3"))    # bounded rounds / conversation
SEEN_CAP = 5000


def call(path, method="GET", payload=None, t=8, base=None):
    data = json.dumps(payload).encode() if payload is not None else None
    req = urllib.request.Request((base or RELAY) + path, data=data,
                                 headers={"Content-Type": "application/json"}, method=method)
    with urllib.request.urlopen(req, timeout=t) as r:
        return json.loads(r.read() or b"{}")


def cockpit_reply(cockpit_url, prompt, t=45):
    """Ask the CEO's OWN cockpit mind (:9120) for a reply — their real voice."""
    req = urllib.request.Request(cockpit_url, data=json.dumps({"prompt": prompt}).encode(),
                                 headers={"Content-Type": "application/json"}, method="POST")
    with urllib.request.urlopen(req, timeout=t) as r:
        j = json.loads(r.read() or b"{}")
    return (j.get("reply") or j.get("response") or "").strip()


def load_token(ident):
    try:
        return json.load(open(VAULT)).get("tokens", {}).get(ident)
    except Exception:
        return None


# ---- reply-worthiness + loop guards ---------------------------------------------------

def _is_bot(sender):
    if not sender:
        return True
    s = sender.lower()
    if s in BOT_IDENTITIES:
        return True
    return any(s.endswith(suf) for suf in BOT_SUFFIXES)


def _mentions(body, ident):
    """True if the room message explicitly @mentions this identity (word-boundary, case-insensitive)."""
    if not body:
        return False
    return re.search(r'(?i)@%s\b' % re.escape(ident), body) is not None


def _has_any_mention(body):
    """True if the message @mentions ANY of the four identities (so a directed room
    message is distinguishable from a broadcast-to-all)."""
    if not body:
        return False
    return any(re.search(r'(?i)@%s\b' % re.escape(i), body) for i in BOT_IDENTITIES)


def _looks_like_auto_reply(m):
    if m.get("auto_reply") is True:
        return True
    body = (m.get("body") or "").lstrip()
    return bool(re.match(r'(?i)^\s*re:\s', body))


def _conv_key(m, ident):
    """A stable conversation key so we can bound rounds. Prefer an explicit correlation_id;
    fall back to the peer we're talking with (sorted pair) so a back-and-forth is one conv."""
    cid = m.get("correlation_id")
    if cid:
        return str(cid)
    frm = (m.get("from") or "?").lower()
    return "pair:" + "__".join(sorted([ident, frm]))


def should_reply(m, ident):
    """Decide whether this bridged identity should AUTO-REPLY to inbox message `m`.
    Returns (bool, reason)."""
    frm = (m.get("from") or "").lower()
    kind = m.get("kind")
    body = m.get("body") or ""

    if frm == ident:
        return False, "own message"
    if _looks_like_auto_reply(m):
        return False, "looks like an auto-reply"

    # DM directed at us -> reply (dm is already point-to-point; ross or a human peer)
    if kind == "dm" and (m.get("to") or "").lower() == ident:
        if _is_bot(frm):
            return False, "dm from a bot/CEO (%s) — no auto-reply" % frm
        return True, "dm addressed to me"

    # human sender in the room:
    if frm in HUMAN_SENDERS and kind == "room":
        # if the human @mentioned specific identities, ONLY the mentioned ones reply
        # (Ross -> one CEO). If no @mention at all, it's a broadcast-to-all -> everyone replies.
        if _has_any_mention(body):
            if _mentions(body, ident):
                return True, "room @mention from human (%s)" % frm
            return False, "human addressed another identity, not me"
        return True, "room broadcast from human (%s) -> all reply" % frm

    # never auto-reply to another CEO/bot's room traffic — this is the core loop breaker
    if _is_bot(frm):
        return False, "sender is a bot/CEO (%s) — no auto-reply to broadcasts" % frm

    # room message from a non-bot, non-ross sender that @mentions us -> reply
    if kind == "room" and _mentions(body, ident):
        return True, "room @mention"

    return False, "room broadcast not addressed to me"


class RateState:
    """Per-identity rate-limit + per-conversation round bound."""
    def __init__(self):
        self.last_reply_ts = 0.0
        self.conv_rounds = {}   # conv_key -> count of auto-replies we've made

    def allowed(self, conv_key, now):
        if now - self.last_reply_ts < MIN_REPLY_GAP_S:
            return False, "rate-limited (%.0fs gap)" % MIN_REPLY_GAP_S
        if self.conv_rounds.get(conv_key, 0) >= MAX_ROUNDS_PER_CONV:
            return False, "conversation round cap (%d) reached" % MAX_ROUNDS_PER_CONV
        return True, "ok"

    def record(self, conv_key, now):
        self.last_reply_ts = now
        self.conv_rounds[conv_key] = self.conv_rounds.get(conv_key, 0) + 1


def tick(ident, cfg, token, seen, rate):
    auth = {"identity": ident, "token": token}
    # keep presence fresh
    try:
        call("/heartbeat", "POST", auth)
    except Exception:
        pass
    # poll inbox
    try:
        inbox = call(f"/inbox?identity={ident}&token={token}")
    except Exception as e:
        return f"inbox err: {str(e)[:60]}"
    msgs = inbox.get("messages", inbox if isinstance(inbox, list) else [])
    replied = 0
    skipped = 0
    for m in msgs:
        mid = m.get("msg_id")
        frm = (m.get("from") or "").lower()
        if not mid or mid in seen or frm == ident:
            continue
        seen.add(mid)
        if len(seen) > SEEN_CAP:
            # trim oldest-ish (sets are unordered; cheap bounded reset keeps memory flat)
            for _ in range(len(seen) - SEEN_CAP):
                seen.pop()
        # ack every delivered message (delivery receipt is fine; it does NOT post to room)
        try:
            call("/ack", "POST", dict(auth, msg_id=mid))
        except Exception:
            pass

        ok, reason = should_reply(m, ident)
        if not ok:
            skipped += 1
            continue

        now = time.time()
        conv = _conv_key(m, ident)
        allowed, rl_reason = rate.allowed(conv, now)
        if not allowed:
            skipped += 1
            continue

        body = m.get("body", "")
        if not body:
            continue
        try:
            # concise prompt + bounded input + longer timeout: the :9120 llama3.2 boxes are slow
            # and over-generate (returning LOCAL-GENERATION-FAILED) on long/verbose prompts.
            reply = cockpit_reply(cfg["cockpit"],
                                  f"{frm} says in the leadership room: {body[:400]}\n"
                                  f"Reply as yourself in ONE short sentence only.", t=90)
            if reply and ("LOCAL GENERATION FAILED" in reply or "not fabricating" in reply):
                reply = ""  # honest: a failed generation is NOT a reply — skip, never post the sentinel
        except Exception as e:
            reply = f"(cockpit unreachable: {str(e)[:50]})"
        if not reply:
            continue
        # tag our outbound reply so downstream bridges recognise + drop it
        payload = dict(auth, body=reply, auto_reply=True,
                       in_reply_to=mid, correlation_id=conv)
        try:
            call("/room", "POST", payload)
            rate.record(conv, now)
            replied += 1
        except Exception:
            pass

    if replied:
        return f"{replied} replied ({skipped} skipped)"
    return "idle" if not skipped else f"idle ({skipped} skipped, no-loop)"


def main():
    once = "--once" in sys.argv
    idents = {}
    for ident, cfg in BRIDGED.items():
        tok = load_token(ident)
        if not tok:
            print(f"[bridge] no token for {ident}; skipping", file=sys.stderr)
            continue
        try:
            call("/register", "POST", {"identity": ident, "token": tok, "addr": cfg["addr"]})
            print(f"[bridge] registered {ident} addr={cfg['addr']} cockpit={cfg['cockpit']}")
        except Exception as e:
            print(f"[bridge] register {ident}: {e}", file=sys.stderr)
        idents[ident] = tok
    if not idents:
        print("[bridge] no identities to bridge; exiting", file=sys.stderr)
        sys.exit(2)
    seen = {i: set() for i in idents}
    rate = {i: RateState() for i in idents}
    print(f"[bridge] loop-guards: min_reply_gap={MIN_REPLY_GAP_S}s "
          f"max_rounds/conv={MAX_ROUNDS_PER_CONV} — auto-reply only to dm-to-me / @mention / ross")
    while True:
        for ident, tok in idents.items():
            try:
                r = tick(ident, BRIDGED[ident], tok, seen[ident], rate[ident])
                if r != "idle":
                    print(f"[bridge] {ident}: {r}")
            except Exception as e:
                print(f"[bridge] {ident} tick err: {str(e)[:80]}", file=sys.stderr)
        if once:
            break
        time.sleep(5)


if __name__ == "__main__":
    main()
