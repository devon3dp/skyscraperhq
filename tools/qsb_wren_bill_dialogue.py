#!/usr/bin/env python3
"""
qsb_wren_bill_dialogue.py — GENUINE live two-way dialogue between Wren (tower
governor) and Bill (Executive Concierge, single Mac qwen) about running the
QSB Tower.

HONESTY CONTRACT (R01): every line written here is a REAL model response over
REAL current tower state. NOTHING is scripted, canned, or fabricated. If a
model genuinely fails or times out, the turn is logged as an honest
`turn_failed` note and skipped — a missing line is never invented.

How it works, one bounded conversation per invocation (default 5 turns, then
exits — never loops forever inside one run, so a watchdog/timer can call it
repeatedly):

  1. Pick a seed topic by rotation from a DIFFERENT real tower matter each run
     (worker-needs queue / floor-activity index / council board / health
     snapshot / accounts summary). A real current fact + delta is extracted
     from that source so no two openers repeat.
  2. Wren (governor) opens with a real management concern grounded in that fact
     -> POST http://127.0.0.1:8851/api/wren_chat  (hard 60s timeout).
  3. Relay Wren's line to Bill via the leadership relay (:8855) and poll the
     room log for Bill's REAL new reply (hard ~60s timeout).
  4. Feed Bill's read back to Wren, and so on, for a bounded number of REAL
     back-and-forth turns.

Each real turn is appended to
  data/registries/qsb_wren_bill_dialogue.jsonl
as: {conversation_id, turn, speaker, text, ts, seed_topic, seed_source}
(the live dashboard at :8879 reads this).

Both minds are called through their EXISTING endpoints only. This tool does NOT
edit Wren's or Bill's minds, the map, SAFETY_DENY, or flip any gate.
"""
import argparse
import json
import os
import re
import subprocess
import sys
import time
import uuid
import urllib.request
import urllib.error
from datetime import datetime, timezone

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
REG = os.path.join(ROOT, "data", "registries")
DIALOGUE_LOG = os.path.join(REG, "qsb_wren_bill_dialogue.jsonl")
ROOM_LOG = os.path.join(REG, "leadership_comms", "room.jsonl")
ROTATION_STATE = os.path.join(REG, "qsb_wren_bill_dialogue_rotation.json")
LEADERSHIP_CLIENT = os.path.join(ROOT, "tools", "qsb_leadership_client.py")

WREN_URL = "http://127.0.0.1:8851/api/wren_chat"
RELAY_URL = "http://127.0.0.1:8855"

WREN_TIMEOUT = 60
BILL_TIMEOUT = 60


def utcnow():
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def load_json(path):
    try:
        with open(path) as f:
            return json.load(f)
    except Exception:
        return None


# ---------------------------------------------------------------------------
# Seed extraction — each returns (headline_fact, wren_opener_prompt) from REAL
# current state. Returns None if the source is missing/empty so we can skip.
# ---------------------------------------------------------------------------

def seed_worker_needs():
    d = load_json(os.path.join(REG, "qsb_worker_needs_queue.json"))
    if not d or not d.get("needs"):
        return None
    n = d["needs"][0]
    fact = (f"Worker-needs queue: {d.get('distinct_needs')} distinct needs "
            f"(folded from {d.get('worker_reports_folded')} reports). Top item — "
            f"Floor {n.get('floor')} ({n.get('room')}): \"{n.get('need')}\" "
            f"reported {n.get('reported_by_count')}x by {n.get('from_worker')}.")
    opener = (
        "You are Wren, the tower GOVERNOR opening a working chat with Bill "
        "(Executive Concierge, Floor 47). Speak plainly to Bill, first person. "
        "Real state right now: " + fact + " Raise ONE concrete management "
        "concern about this specific need and ask Bill what he'd action first. "
        "2-3 sentences, no preamble.")
    return fact, opener


def seed_floor_activity():
    d = load_json(os.path.join(REG, "qsb_floor_activity_index.json"))
    if not d or not d.get("floors"):
        return None
    total = d.get("total_floors")
    active = d.get("active_floors")
    quiet = [k for k, v in d["floors"].items() if not v.get("active")]
    quiet_labels = []
    for k in quiet[:4]:
        quiet_labels.append(d["floors"][k].get("label", k))
    fact = (f"Floor-activity index: {active}/{total} floors active in the last "
            f"hour. Quiet floors right now: {', '.join(quiet_labels) or 'none'}.")
    opener = (
        "You are Wren, the tower GOVERNOR opening a working chat with Bill "
        "(Executive Concierge, Floor 47). Speak plainly to Bill, first person. "
        "Real state right now: " + fact + " Raise ONE concern about whether "
        "those quiet floors need attention or are fine idle, and ask Bill for "
        "his read. 2-3 sentences, no preamble.")
    return fact, opener


def seed_council_board():
    try:
        rows = [json.loads(l) for l in open(os.path.join(REG, "qsb_council_tasks.jsonl")) if l.strip()]
    except Exception:
        return None
    if not rows:
        return None
    titled = None
    for r in reversed(rows[-200:]):
        if r.get("text"):
            titled = r
            break
    if not titled:
        titled = rows[-1]
    fact = (f"Council board: {len(rows)} total events. Most recent activity — "
            f"task {titled.get('task_id')} ({titled.get('event')}) by "
            f"{titled.get('actor')}: \"{(titled.get('text') or '')[:140]}\".")
    opener = (
        "You are Wren, the tower GOVERNOR opening a working chat with Bill "
        "(Executive Concierge, Floor 47). Speak plainly to Bill, first person. "
        "Real state right now: " + fact + " Raise ONE concern about whether "
        "this council item is moving or stuck, and ask Bill how he'd unblock or "
        "prioritise it. 2-3 sentences, no preamble.")
    return fact, opener


def seed_health():
    d = load_json(os.path.join(REG, "qsb_tower_health_snapshot.json"))
    if not d:
        return None
    tc = d.get("task_council", {})
    svc = d.get("services", {})
    fact = (f"Health snapshot: {svc.get('up')}/{svc.get('total')} services up, "
            f"{d.get('traders_alive')} traders alive, root disk "
            f"{d.get('root_disk_pct')}, load {d.get('load_1m')}. Task council: "
            f"{tc.get('done')} done / {tc.get('in_progress')} in-progress / "
            f"{tc.get('blocked')} blocked / {tc.get('open')} open.")
    opener = (
        "You are Wren, the tower GOVERNOR opening a working chat with Bill "
        "(Executive Concierge, Floor 47). Speak plainly to Bill, first person. "
        "Real state right now: " + fact + " Raise ONE concern (e.g. the "
        "blocked tasks, the load, or the open backlog) and ask Bill what he "
        "thinks the priority is. 2-3 sentences, no preamble.")
    return fact, opener


def seed_accounts():
    d = load_json(os.path.join(REG, "qsb_accounts_summary_latest.json"))
    if not d or not d.get("reconciled_totals"):
        return None
    t = d["reconciled_totals"]
    fact = (f"Accounts summary (advisory, practice/paper only, no real money): "
            f"reconciled realized PnL GBP {t.get('realized_pnl_gbp_all_venues')}, "
            f"OANDA practice NAV GBP {t.get('oanda_practice_nav_gbp')}, belief "
            f"fleet open exposure GBP {t.get('belief_fleet_open_exposure_gbp')}, "
            f"provider spend today USD {t.get('provider_spend_usd_today')}.")
    opener = (
        "You are Wren, the tower GOVERNOR opening a working chat with Bill "
        "(Executive Concierge, Floor 47). Speak plainly to Bill, first person. "
        "Real state right now: " + fact + " Raise ONE concern about the fleet "
        "exposure or provider spend and ask Bill for his view on whether we're "
        "well-positioned. 2-3 sentences, no preamble. Remember: practice/paper "
        "only, never imply real-money trading.")
    return fact, opener


SEEDS = [
    ("worker_needs_queue", "data/registries/qsb_worker_needs_queue.json", seed_worker_needs),
    ("floor_activity_index", "data/registries/qsb_floor_activity_index.json", seed_floor_activity),
    ("council_board", "data/registries/qsb_council_tasks.jsonl", seed_council_board),
    ("health_snapshot", "data/registries/qsb_tower_health_snapshot.json", seed_health),
    ("accounts_summary", "data/registries/qsb_accounts_summary_latest.json", seed_accounts),
]


def next_seed_index():
    st = load_json(ROTATION_STATE) or {"idx": -1}
    idx = (st.get("idx", -1) + 1) % len(SEEDS)
    try:
        with open(ROTATION_STATE, "w") as f:
            json.dump({"idx": idx, "ts": utcnow()}, f)
    except Exception:
        pass
    return idx


def pick_seed(forced=None):
    order = list(range(len(SEEDS)))
    if forced is not None:
        order = [forced] + [i for i in order if i != forced]
    else:
        start = next_seed_index()
        order = [(start + k) % len(SEEDS) for k in range(len(SEEDS))]
    for i in order:
        topic, source, fn = SEEDS[i]
        try:
            res = fn()
        except Exception as e:
            print(f"[seed] {topic} raised {e!r}, trying next", file=sys.stderr)
            res = None
        if res:
            fact, opener = res
            return topic, source, fact, opener
    return None


# ---------------------------------------------------------------------------
# Model calls
# ---------------------------------------------------------------------------

def call_wren(prompt, timeout=WREN_TIMEOUT):
    """Real Wren governor call. Returns reply text or raises."""
    data = json.dumps({"text": prompt}).encode()
    req = urllib.request.Request(
        WREN_URL, data=data, method="POST",
        headers={"Content-Type": "application/json"})
    with urllib.request.urlopen(req, timeout=timeout) as r:
        obj = json.loads(r.read() or b"{}")
    reply = (obj.get("reply") or "").strip()
    if not reply:
        raise RuntimeError("wren returned empty reply")
    return reply


def _room_last_ts():
    ts = ""
    try:
        for line in open(ROOM_LOG):
            line = line.strip()
            if not line:
                continue
            try:
                r = json.loads(line)
            except Exception:
                continue
            if r.get("ts", "") > ts:
                ts = r["ts"]
    except FileNotFoundError:
        pass
    return ts


def _clean_bill(body):
    """Bill signs his real replies with a code prefix + 'Ross,'. Keep his real
    words, strip the routing/signature noise so the log reads clean. This is
    formatting only — no words are added or changed."""
    b = body.strip()
    # drop a leading probe/signature token like 'BZ26639C07' or 'PROBE-xxxx'
    b = re.sub(r"^(PROBE-[0-9a-f]+|[A-Z]{2}[0-9A-Z]{6,})\s+", "", b).strip()
    # drop a leading 'Ross,' salutation (Bill addresses the room)
    b = re.sub(r"^Ross,\s*", "", b).strip()
    return b or body.strip()


def call_bill(message, timeout=BILL_TIMEOUT):
    """Send message to Bill via relay, poll room for his REAL new reply.
    Returns reply text or raises on timeout."""
    before_ts = _room_last_ts()
    # send DM
    cmd = [sys.executable, LEADERSHIP_CLIENT,
           "--identity", "wren", "--relay", RELAY_URL,
           "--send-dm", "bill", message]
    out = subprocess.run(cmd, capture_output=True, text=True, timeout=30)
    if out.returncode != 0:
        raise RuntimeError(f"relay send failed: {out.stderr.strip() or out.stdout.strip()}")
    # poll room for a new, non-probe bill message
    deadline = time.time() + timeout
    while time.time() < deadline:
        try:
            rows = [json.loads(l) for l in open(ROOM_LOG) if l.strip()]
        except Exception:
            rows = []
        for r in reversed(rows):
            if (r.get("from") == "bill" and r.get("ts", "") > before_ts
                    and "PROBE" not in r.get("body", "")):
                cleaned = _clean_bill(r.get("body", ""))
                if cleaned:
                    return cleaned
        time.sleep(3)
    raise TimeoutError(f"no bill reply within {timeout}s")


# ---------------------------------------------------------------------------
# Logging
# ---------------------------------------------------------------------------

def log_turn(conv_id, turn, speaker, text, topic, source):
    row = {
        "conversation_id": conv_id,
        "turn": turn,
        "speaker": speaker,
        "text": text,
        "ts": utcnow(),
        "seed_topic": topic,
        "seed_source": source,
    }
    with open(DIALOGUE_LOG, "a") as f:
        f.write(json.dumps(row) + "\n")
    return row


def log_note(conv_id, turn, note, topic, source):
    row = {
        "conversation_id": conv_id,
        "turn": turn,
        "speaker": "system",
        "text": note,
        "ts": utcnow(),
        "seed_topic": topic,
        "seed_source": source,
        "turn_failed": True,
    }
    with open(DIALOGUE_LOG, "a") as f:
        f.write(json.dumps(row) + "\n")
    return row


# ---------------------------------------------------------------------------
# One bounded conversation
# ---------------------------------------------------------------------------

def run_conversation(max_turns=5, forced_seed=None, verbose=True):
    seed = pick_seed(forced_seed)
    if not seed:
        print("[dialogue] no usable seed source available", file=sys.stderr)
        return None
    topic, source, fact, opener = seed
    conv_id = "conv_" + uuid.uuid4().hex[:12]

    if verbose:
        print(f"=== conversation {conv_id} ===")
        print(f"seed_topic : {topic}")
        print(f"seed_source: {source}")
        print(f"real fact  : {fact}\n")

    transcript = []
    turn = 0

    # Turn 1: Wren opens (governor) grounded in the real fact
    try:
        wren_line = call_wren(opener)
    except Exception as e:
        log_note(conv_id, turn, f"wren opener failed: {e}", topic, source)
        print(f"[dialogue] wren opener failed: {e}", file=sys.stderr)
        return conv_id
    turn += 1
    log_turn(conv_id, turn, "wren", wren_line, topic, source)
    transcript.append(("wren", wren_line))
    if verbose:
        print(f"[turn {turn}] WREN: {wren_line}\n")

    last_wren = wren_line
    # Alternate Bill <-> Wren for the remaining turns
    while turn < max_turns:
        # Bill responds to Wren's last line
        try:
            bill_line = call_bill(last_wren)
        except Exception as e:
            log_note(conv_id, turn, f"bill turn failed (honest skip): {e}", topic, source)
            print(f"[dialogue] bill turn failed: {e}", file=sys.stderr)
            break
        turn += 1
        log_turn(conv_id, turn, "bill", bill_line, topic, source)
        transcript.append(("bill", bill_line))
        if verbose:
            print(f"[turn {turn}] BILL: {bill_line}\n")
        if turn >= max_turns:
            break

        # Wren replies to Bill, staying on the same real matter
        wren_prompt = (
            "You are Wren, the tower GOVERNOR, mid-conversation with Bill "
            "(Executive Concierge) about this real matter: " + fact + " "
            "Bill just said: \"" + bill_line + "\" Respond to Bill directly, "
            "first person, 2-3 sentences: either agree and name the next step, "
            "push back with your reasoning, or ask him one sharper question. "
            "No preamble.")
        try:
            wren_line = call_wren(wren_prompt)
        except Exception as e:
            log_note(conv_id, turn, f"wren reply failed (honest skip): {e}", topic, source)
            print(f"[dialogue] wren reply failed: {e}", file=sys.stderr)
            break
        turn += 1
        log_turn(conv_id, turn, "wren", wren_line, topic, source)
        transcript.append(("wren", wren_line))
        if verbose:
            print(f"[turn {turn}] WREN: {wren_line}\n")
        last_wren = wren_line

    if verbose:
        print(f"=== conversation {conv_id} complete: {len(transcript)} real turns ===")
    return conv_id


def main():
    ap = argparse.ArgumentParser(description="Live Wren<->Bill tower dialogue")
    ap.add_argument("--max-turns", type=int, default=5,
                    help="bounded turn cap (default 5), then exit")
    ap.add_argument("--seed", type=int, default=None,
                    help="force a seed index 0-4 (default: rotate)")
    ap.add_argument("--quiet", action="store_true")
    args = ap.parse_args()
    run_conversation(max_turns=args.max_turns, forced_seed=args.seed,
                     verbose=not args.quiet)


if __name__ == "__main__":
    main()
