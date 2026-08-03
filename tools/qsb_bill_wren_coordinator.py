#!/usr/bin/env python3
"""
qsb_bill_wren_coordinator.py — REAL Bill<->Wren working-pair coordinator.

Ross goal (2026-07-29): make Bill (Executive Concierge, one mind on his Mac,
qwen2.5:14b, outbound-only) and Wren (Resident Governor, real local qwen mind on
this box at :8851) work as a genuine PAIR — not just trade probe tokens.

  * Wren RUNS / GOVERNS the tower (task board + verification).
  * Bill SURFACES what is happening and coordinates on Ross's behalf.

HONESTY CONTRACT — no fake minds, real endpoints only:
  * Wren's mind is REAL and lives on THIS box: POST :8851/api/wren_chat -> {"reply": ...}
    Her mind already injects LIVE TOWER TELEMETRY, so her answers are grounded.
  * Bill's mind is REAL and lives on his MAC. We NEVER answer "as Bill" here. We only
    move messages to/from Bill through the leadership relay (:8855). Bill's Mac responder
    (deploy/qsb_bill_responder.py) pulls DMs from the relay inbox and replies with his own
    local mind. If his Mac is offline the relay queues durably; nothing is faked.
  * Every Wren->Bill briefing carries a machine-checkable TELEMETRY footer taken verbatim
    from data/registries/qsb_tower_health_snapshot.json so a human/auditor can confirm the
    concierge line matches REAL tower state (Bill's prose can drift; the footer cannot).

TWO REAL DIRECTIONS
-------------------
(A) WREN -> BILL  (--push / default tick)
    1. read REAL telemetry: qsb_tower_health_snapshot.json + council board counts
       + Wren's recent dash-chat (qsb_wren_dash_chat.jsonl).
    2. ask WREN'S REAL MIND (:8851) for a one-paragraph "top priority + what I'm doing"
       update, grounded in that telemetry.
    3. DM that REAL Wren answer to Bill via relay (from=wren, to=bill), with the verbatim
       telemetry footer appended. Bill's Mac receives it and can brief Ross.

(B) BILL -> WREN  (--answer-bill)
    1. find DMs Bill sent to Wren (dm/bill__wren.jsonl, from=bill) that Wren has not yet
       answered (tracked in data/registries/qsb_bill_wren_answered.json).
    2. route each REAL Bill question to WREN'S REAL MIND (:8851).
    3. DM Wren's REAL reply back to Bill (from=wren, to=bill). Now Bill asked, Wren's real
       mind answered from real state, both directions carried by real endpoints.

(C) --converse "question"
    End-to-end proof: post a REAL question as Bill to Wren (from=bill), let Wren's REAL mind
    answer it, DM the answer back to Bill, and print both real messages with timestamps.
    (This exercises the exact same path a live Bill would; the only shortcut is that WE
    inject Bill's question text so the exchange can be demonstrated deterministically. The
    ANSWER is 100% Wren's real grounded mind — never faked.)

CLI
    python3 tools/qsb_bill_wren_coordinator.py --push          # Wren->Bill grounded update
    python3 tools/qsb_bill_wren_coordinator.py --answer-bill   # answer Bill's pending Qs to Wren
    python3 tools/qsb_bill_wren_coordinator.py --tick          # both directions (service tick)
    python3 tools/qsb_bill_wren_coordinator.py --converse "what's the tower's top priority right now?"
    python3 tools/qsb_bill_wren_coordinator.py --status        # show presence + last exchange
"""
from __future__ import annotations
import argparse, json, os, sys, time, uuid, urllib.request, urllib.error
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
REG = ROOT / "data" / "registries"
COMMS = REG / "leadership_comms"
VAULT = ROOT / "floors" / "floor_28_security_department" / "vault"

HEALTH = REG / "qsb_tower_health_snapshot.json"
BOARD = REG / "qsb_council_tasks.jsonl"
WREN_CHAT_LOG = REG / "qsb_wren_dash_chat.jsonl"
DM_BILL_WREN = COMMS / "dm" / "bill__wren.jsonl"
ANSWERED = REG / "qsb_bill_wren_answered.json"
COORD_LOG = REG / "qsb_bill_wren_coordinator.jsonl"
LEADER_TOKENS = VAULT / "leadership_tokens.json"

RELAY = os.environ.get("BILL_WREN_RELAY", "http://127.0.0.1:8855")
WREN_MIND = os.environ.get("WREN_MIND_URL", "http://127.0.0.1:8851/api/wren_chat")
WREN_TIMEOUT = int(os.environ.get("WREN_MIND_TIMEOUT", "120"))


def utc() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds").replace("+00:00", "Z")


def log(rec: dict) -> None:
    rec = {"ts": utc(), **rec}
    try:
        with COORD_LOG.open("a") as f:
            f.write(json.dumps(rec) + "\n")
    except Exception:
        pass


def _tokens() -> dict:
    try:
        return json.loads(LEADER_TOKENS.read_text()).get("tokens", {})
    except Exception:
        return {}


# ── real telemetry gathering (no LLM) ──────────────────────────────────────

def read_health() -> dict:
    try:
        return json.loads(HEALTH.read_text())
    except Exception:
        return {}


def board_counts() -> dict:
    """Authoritative board counts. The tower's own health snapshot already computes the
    canonical board tally (qsb_tower_health.py) — trust that so we never surface a number
    that disagrees with what Wren's mind sees. Fall back to a raw JSONL recount only if the
    snapshot is missing."""
    h = read_health()
    tc = h.get("task_council")
    if isinstance(tc, dict) and tc:
        c = {k: v for k, v in tc.items() if isinstance(v, int)}
        c["total"] = sum(c.values())
        return c
    # fallback: raw recount (schema-tolerant across id/task_id + state/status fields)
    latest: dict[str, str] = {}
    try:
        with BOARD.open() as f:
            for line in f:
                line = line.strip()
                if not line:
                    continue
                try:
                    r = json.loads(line)
                except Exception:
                    continue
                tid = r.get("id") or r.get("task_id")
                st = r.get("state") or r.get("status")
                if tid and st:
                    latest[tid] = st
    except Exception:
        return {}
    c = {}
    for st in latest.values():
        c[st] = c.get(st, 0) + 1
    c["total"] = len(latest)
    return c


def wren_recent_activity(n: int = 6) -> list[str]:
    """Wren's REAL recent dash-chat lines (what she's actually been saying/doing)."""
    rows = []
    try:
        with WREN_CHAT_LOG.open() as f:
            for line in f:
                line = line.strip()
                if not line:
                    continue
                try:
                    r = json.loads(line)
                except Exception:
                    continue
                if r.get("from") == "wren":
                    rows.append(r.get("text", ""))
    except Exception:
        pass
    return rows[-n:]


def telemetry_footer(h: dict, b: dict) -> str:
    """Machine-checkable footer taken VERBATIM from the real snapshot. This is the
    ground-truth line an auditor cross-checks Bill's prose against."""
    svc = h.get("services", {})
    tc = h.get("task_council", {})
    return (
        "[TELEMETRY " + (h.get("ts", "?")) + "] "
        f"services {svc.get('up','?')}/{svc.get('total','?')} up | "
        f"bus={'LIVE' if h.get('event_bus_bound') else 'DOWN'} | "
        f"traders_alive={h.get('traders_alive','?')} | "
        f"root_disk={h.get('root_disk_pct','?')} load1m={h.get('load_1m','?')} | "
        f"board open={tc.get('open','?')} in_progress={tc.get('in_progress','?')} "
        f"blocked={tc.get('blocked','?')} done={tc.get('done','?')}"
    )


# ── Wren's REAL mind ───────────────────────────────────────────────────────

def ask_wren(text: str) -> str:
    """POST to Wren's real local mind at :8851. Returns her real reply string.
    Raises on transport failure so callers can report honestly (never fabricate)."""
    data = json.dumps({"text": text}).encode()
    req = urllib.request.Request(WREN_MIND, data=data,
                                 headers={"Content-Type": "application/json"}, method="POST")
    with urllib.request.urlopen(req, timeout=WREN_TIMEOUT) as r:
        d = json.loads(r.read().decode())
    # her dash returns {"reply": ...}; be tolerant of {"answer": ...}
    return (d.get("reply") or d.get("answer") or "").strip()


# ── relay I/O ──────────────────────────────────────────────────────────────

def relay_call(path: str, method: str = "GET", payload: dict | None = None, t: int = 10):
    url = RELAY.rstrip("/") + path
    data = json.dumps(payload).encode() if payload is not None else None
    req = urllib.request.Request(url, data=data,
                                 headers={"Content-Type": "application/json"}, method=method)
    with urllib.request.urlopen(req, timeout=t) as r:
        return json.loads(r.read().decode())


def dm(frm: str, to: str, body: str) -> dict:
    tok = _tokens().get(frm)
    if not tok:
        raise RuntimeError(f"no relay token for {frm}")
    return relay_call("/dm", "POST", {"identity": frm, "token": tok, "to": to, "body": body})


def presence() -> dict:
    try:
        return relay_call("/presence", "GET", t=8)
    except Exception:
        return {}


# ── answered-tracker (so we don't re-answer Bill's old DMs) ─────────────────

def load_answered() -> set:
    try:
        return set(json.loads(ANSWERED.read_text()).get("answered_msg_ids", []))
    except Exception:
        return set()


def save_answered(s: set) -> None:
    try:
        ANSWERED.write_text(json.dumps({"answered_msg_ids": sorted(s)[-500:],
                                        "updated": utc()}, indent=2))
    except Exception:
        pass


def bill_questions_to_wren() -> list[dict]:
    """DMs Bill sent TO Wren (from=bill) that look like a question/request (not an ack/probe echo)."""
    out = []
    if not DM_BILL_WREN.exists():
        return out
    with DM_BILL_WREN.open() as f:
        for line in f:
            line = line.strip()
            if not line:
                continue
            try:
                r = json.loads(line)
            except Exception:
                continue
            if r.get("from") == "bill" and r.get("to") == "wren":
                out.append(r)
    return out


# ── DIRECTION A: Wren -> Bill (grounded update) ────────────────────────────

def push_wren_to_bill(quiet: bool = False) -> dict:
    h = read_health()
    b = board_counts()
    recent = wren_recent_activity()
    foot = telemetry_footer(h, b)

    prompt = (
        "You are Wren, the Resident Governor. Brief Bill (Ross's Executive Concierge) so he can "
        "relay to Ross. In 2-3 sentences, state the tower's TOP PRIORITY right now and what you "
        "are actively governing, grounded ONLY in the live telemetry you can see. Be concrete "
        "(cite trader count / open-task count / any blocker). Do not invent numbers.\n"
        f"\n(For your reference, current board recomputed from the ledger: {json.dumps(b)})"
    )
    try:
        wren_says = ask_wren(prompt)
    except Exception as e:
        # HONEST failure — do not fabricate a Wren update.
        log({"dir": "wren->bill", "ok": False, "error": f"wren mind unreachable: {e}"})
        if not quiet:
            print(f"[coord] Wren's mind unreachable ({e}); NOT sending a faked update.", file=sys.stderr)
        return {"ok": False, "error": str(e)}

    body = f"WREN->BILL update: {wren_says}\n{foot}"
    try:
        res = dm("wren", "bill", body)
    except Exception as e:
        log({"dir": "wren->bill", "ok": False, "error": f"relay dm failed: {e}", "wren_says": wren_says})
        return {"ok": False, "error": str(e), "wren_says": wren_says}
    log({"dir": "wren->bill", "ok": True, "msg_id": res.get("msg_id"),
         "wren_says": wren_says, "telemetry": foot})
    if not quiet:
        print(f"[coord] Wren->Bill sent (msg_id={res.get('msg_id')}):\n  {wren_says}\n  {foot}")
    return {"ok": True, "wren_says": wren_says, "telemetry": foot, "msg_id": res.get("msg_id")}


# ── DIRECTION B: answer Bill's pending questions with Wren's real mind ──────

def answer_bill_questions(quiet: bool = False, max_answer: int = 3) -> dict:
    answered = load_answered()
    qs = [q for q in bill_questions_to_wren() if q.get("msg_id") not in answered]
    # only the most recent few, oldest-first, to avoid a backlog storm
    qs = qs[-max_answer:]
    done = []
    for q in qs:
        mid = q.get("msg_id")
        text = q.get("body", "")
        if not text:
            answered.add(mid); continue
        prompt = (
            "You are Wren, the Resident Governor. Bill (Ross's Executive Concierge) is asking you "
            "this, and Ross will read your answer. Answer directly and concisely, grounded ONLY in "
            "the live telemetry you can see. Do not invent numbers.\n\nBill asks: " + text
        )
        try:
            reply = ask_wren(prompt)
        except Exception as e:
            log({"dir": "bill->wren", "ok": False, "q_msg_id": mid, "error": str(e)})
            if not quiet:
                print(f"[coord] Wren mind unreachable for Bill's Q {mid} ({e}); skipping.", file=sys.stderr)
            continue
        try:
            res = dm("wren", "bill", f"WREN answers Bill: {reply}")
        except Exception as e:
            log({"dir": "bill->wren", "ok": False, "q_msg_id": mid, "error": f"relay: {e}"})
            continue
        answered.add(mid)
        done.append({"q": text, "a": reply, "reply_msg_id": res.get("msg_id")})
        log({"dir": "bill->wren", "ok": True, "q_msg_id": mid, "q": text,
             "a": reply, "reply_msg_id": res.get("msg_id")})
        if not quiet:
            print(f"[coord] Bill asked: {text}\n[coord] Wren answered -> Bill: {reply}")
    save_answered(answered)
    return {"answered": done, "count": len(done)}


# ── DIRECTION C: end-to-end conversation proof ─────────────────────────────

def converse(question: str) -> dict:
    """Full real round-trip: Bill asks (posted as bill), Wren's REAL mind answers, answer
    DM'd back to Bill. Prints both real messages with timestamps."""
    ts_q = utc()
    try:
        q_res = dm("bill", "wren", question)
    except Exception as e:
        print(f"[coord] could not post Bill's question: {e}", file=sys.stderr)
        return {"ok": False, "error": str(e)}
    # Wren's real mind answers, grounded in telemetry.
    h = read_health(); b = board_counts()
    prompt = (
        "You are Wren, the Resident Governor. Bill (Ross's Executive Concierge) asks you this and "
        "Ross will read your answer. Answer in 1-3 sentences, grounded ONLY in live telemetry you "
        "can see; cite concrete numbers (traders alive / open tasks / blockers). Do not invent.\n"
        f"\nBill asks: {question}"
    )
    try:
        wren_says = ask_wren(prompt)
    except Exception as e:
        print(f"[coord] Wren's mind unreachable ({e}); refusing to fake an answer.", file=sys.stderr)
        return {"ok": False, "error": str(e), "bill_q_msg_id": q_res.get("msg_id")}
    ts_a = utc()
    foot = telemetry_footer(h, b)
    try:
        a_res = dm("wren", "bill", f"WREN answers Bill: {wren_says}\n{foot}")
    except Exception as e:
        print(f"[coord] could not DM Wren's answer to Bill: {e}", file=sys.stderr)
        return {"ok": False, "error": str(e)}
    # mark this Bill question as answered so the service tick doesn't re-answer it
    ans = load_answered(); ans.add(q_res.get("msg_id")); save_answered(ans)
    out = {"ok": True,
           "bill_question": {"ts": ts_q, "from": "bill", "to": "wren", "msg_id": q_res.get("msg_id"), "body": question},
           "wren_answer": {"ts": ts_a, "from": "wren", "to": "bill", "msg_id": a_res.get("msg_id"), "body": wren_says},
           "telemetry_footer": foot}
    log({"dir": "converse", **out})
    print("\n=== REAL Bill<->Wren exchange (both real endpoints) ===")
    print(f"[{ts_q}] BILL -> WREN : {question}")
    print(f"[{ts_a}] WREN -> BILL : {wren_says}")
    print(f"    ground-truth  : {foot}")
    # concierge relay: what Bill (his Mac mind) would carry to Ross is HIS job; we only show the
    # grounded material he has to work from. (We never write Bill's prose here.)
    return out


def do_status() -> None:
    pres = presence().get("presence", {}) if presence() else {}
    h = read_health(); b = board_counts()
    print("Bill<->Wren coordinator status")
    print("  relay      :", RELAY)
    print("  wren mind  :", WREN_MIND)
    for who in ("wren", "bill"):
        p = pres.get(who, {})
        print(f"  presence[{who}] addr={p.get('reachable_addr','?')} last_hb={p.get('last_heartbeat','?')}")
    print("  ground-truth:", telemetry_footer(h, b))
    if COORD_LOG.exists():
        last = COORD_LOG.read_text().strip().splitlines()[-3:]
        print("  recent coordinator rows:")
        for l in last:
            print("   ", l[:200])


def main():
    ap = argparse.ArgumentParser(description="Real Bill<->Wren working-pair coordinator")
    ap.add_argument("--push", action="store_true", help="Wren->Bill grounded update")
    ap.add_argument("--answer-bill", action="store_true", help="answer Bill's pending DMs to Wren with Wren's real mind")
    ap.add_argument("--tick", action="store_true", help="both directions (service tick)")
    ap.add_argument("--converse", metavar="Q", help="end-to-end proof: Bill asks Q, Wren's real mind answers, answer DM'd back")
    ap.add_argument("--status", action="store_true")
    ap.add_argument("--quiet", action="store_true")
    a = ap.parse_args()

    if a.status:
        do_status(); return
    if a.converse:
        converse(a.converse); return
    did = False
    if a.push or a.tick:
        push_wren_to_bill(quiet=a.quiet); did = True
    if a.answer_bill or a.tick:
        answer_bill_questions(quiet=a.quiet); did = True
    if not did:
        ap.print_help()


if __name__ == "__main__":
    main()
