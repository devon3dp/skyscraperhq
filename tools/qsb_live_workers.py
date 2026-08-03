#!/usr/bin/env python3
"""
qsb_live_workers.py — CONTINUOUS live-worker daemon (Bill + TP + Asa) for the Underground.

2026-07-28, Ross: "couple mins too long — needs to be much quicker". Instead of a 2-min timer,
this runs as a daemon and fires ALL THREE real workers IN PARALLEL every cycle, logging a fresh
train the instant each one replies. New trains land every ~10-15s (as fast as the real models
on the three separate boxes answer) — a genuine live stream.

HONEST (R01): a train is logged ONLY after a real reply. Cockpit-error sentinels / no answer =
no train. Each worker is on its own machine, so this never touches the tower's pinned GPU.

systemd: qsb-live-workers.service (Type=simple, Restart=always). Run: python3 tools/qsb_live_workers.py
"""
import json, time, uuid, threading, subprocess, sys, urllib.request
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "tools"))
try:
    import qsb_knowledge as KB          # the tower's learning layer
except Exception:
    KB = None
REG = ROOT / "data" / "registries"
PRESENCE = REG / "leadership_comms" / "presence.json"
ROOM = REG / "leadership_comms" / "room.jsonl"
BOARD = REG / "qsb_council_tasks.jsonl"
CLIENT = ROOT / "tools" / "qsb_leadership_client.py"
RELAY = "http://127.0.0.1:8855"
CYCLE_SLEEP = 6          # seconds between cycles (the models are the real pacing)

WORK = [
    "TRADING CHECK: in ONE sentence, name one risk in the trader fleet's open positions right now.",
    "In ONE line, one concrete way the council could work faster.",
    "TRADING CHECK: in ONE sentence, one thing to watch on the OANDA/PnL side tonight.",
    "In ONE sentence, one signal that a background worker has silently died.",
    "In ONE line, one thing worth checking on the tower tonight.",
    "TRADING CHECK: in ONE line, one way the trading floors could reduce duplicated trades.",
]

_lock = threading.Lock()


def _utc():
    return time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())


def _journal(rows):
    with _lock, open(BOARD, "a") as f:
        for r in rows:
            f.write(json.dumps(r) + "\n")


def _kind_for(work):
    w = (work or "").lower()
    if "risk" in w:
        return "risk"
    if "died" in w or "silently" in w:
        return "insight"
    if "reduce" in w or "faster" in w or "duplicated" in w:
        return "insight"
    return "note"


def _log_trains(disp, station, work, reply):
    tid = ("BILLWORK_" if station == "bill" else "CEOWORK_") + uuid.uuid4().hex[:8]
    ts = _utc()
    _journal([
        {"ts": ts, "event": "tool_selected", "actor": "wren", "task_id": tid,
         "text": f"owner uses {disp} worker for: {work[:48]}"},
        {"ts": ts, "event": "noted", "actor": station, "task_id": tid,
         "text": f"{disp} worker [{work[:40]}]: {reply[:100]}"},
    ])
    # LEARN: a real reply lands here -> record it as a deduped knowledge entry (honest source).
    if KB:
        try:
            row = KB.add(reply, source=station, kind=_kind_for(work))
            tag = f"NEW learning {row['id']} [{row['topic']}]" if row else "dup/junk (seen bumped)"
            print(f"[live-workers] {disp} knowledge: {tag}", flush=True)
        except Exception as e:
            print(f"[live-workers] {disp} knowledge add failed: {str(e)[:60]}", flush=True)
    print(f"[live-workers] {disp} -> train ({tid}): {reply[:55]!r}", flush=True)


def _cockpit_ip(pres_key, fallback):
    try:
        p = json.loads(PRESENCE.read_text())
        return (p.get(pres_key, {}) or {}).get("reachable_addr") or fallback
    except Exception:
        return fallback


def _bad(reply):
    r = (reply or "").lower()
    return (not reply) or r.startswith(("(cockpit", "local generation failed")) or "unreachable" in r


def _augment(work):
    """Prepend a few relevant prior learnings so the worker builds on them (recall path).

    Reward-loop closure (2026-07-29): prefer REPUTATION-REWEIGHTED recall so the
    worker builds on the HIGHER-TRUST prior first (per-source reputation from real
    council outcomes + KB on-topic/reaffirm, via qsb_worker_reputation). Falls back
    to flat KB recall if that module isn't importable — never breaks the live path."""
    if not KB:
        return work
    recall = ""
    try:
        import qsb_worker_reputation as REP  # reward at point of recall
        recall = REP.recall_context_reweighted(work, k=3)
    except Exception:
        try:
            recall = KB.recall_context(work, k=3)
        except Exception:
            recall = ""
    return f"{recall}\n\n{work}" if recall else work


def do_cockpit(pres_key, station, fallback, disp, work):
    ip = _cockpit_ip(pres_key, fallback)
    prompt = _augment(work)
    # 2026-07-29: Asa/TP boxes ride an iPad hotspot with variable latency; a single 45s
    # attempt drops ~1-in-3 cycles to a slow local-model generation. One quick health-gated
    # retry converts those slow-but-alive cycles into real trains instead of wasting them.
    # (Tower-side dispatcher change only — does NOT touch the CEO's box/mind.)
    reply = ""
    for attempt in (1, 2):
        try:
            req = urllib.request.Request(f"http://{ip}:9120/api/chat",
                                         data=json.dumps({"prompt": prompt}).encode(),
                                         headers={"Content-Type": "application/json"}, method="POST")
            with urllib.request.urlopen(req, timeout=45) as r:
                d = json.loads(r.read() or b"{}")
            reply = (d.get("reply") or d.get("response") or "").strip()
            break
        except Exception as e:
            if attempt == 1:
                # Only retry if the cockpit is actually alive (health 200) — a real
                # unreachable box fails the health check fast and we skip the retry.
                try:
                    hreq = urllib.request.Request(f"http://{ip}:9120/health")
                    with urllib.request.urlopen(hreq, timeout=6) as hr:
                        hr.read()
                    continue  # alive but slow — give it one more real attempt
                except Exception:
                    pass
            print(f"[live-workers] {disp} @ {ip} unreachable ({str(e)[:40]}) — no train", flush=True)
            return
    if _bad(reply):
        print(f"[live-workers] {disp} no real answer — no train", flush=True)
        return
    _log_trains(disp, station, work, reply)


def _last_bill_ts():
    if not ROOM.exists():
        return ""
    last = ""
    for line in ROOM.read_text(errors="ignore").splitlines():
        line = line.strip()
        if not line:
            continue
        try:
            d = json.loads(line)
        except Exception:
            continue
        if d.get("from") == "bill":
            last = d.get("ts", "")
    return last


def do_bill(work):
    before = _last_bill_ts()
    # Bill runs on ONE Mac (slower than the TP/Asa boxes) — keep his prompt SHORT (skip the
    # recall augmentation) so his single qwen isn't swamped/timing out. (2026-07-29 fix)
    #
    # 2026-07-30 (Ross: "he only gets the same questions"): drive Bill's prompt from a LIVE,
    # ROTATING, DELTA-AWARE tower topic instead of the fixed WORK item — so each cycle he's
    # asked about a DIFFERENT real thing (a real floor / metric / recent event / what changed).
    # He is a concierge, not a generic worker; the shared WORK list is what made him loop.
    prompt = work
    try:
        import qsb_bill_topics as TOPICS
        prompt, _t = TOPICS.worker_prompt()
    except Exception as e:
        print(f"[live-workers] Bill topic gen failed ({str(e)[:50]}) — falling back to WORK item", flush=True)
    try:
        subprocess.run([sys.executable, str(CLIENT), "--identity", "wren", "--relay", RELAY,
                        "--send-dm", "bill", prompt], capture_output=True, text=True, timeout=25)
    except Exception as e:
        print(f"[live-workers] Bill send failed ({str(e)[:40]})", flush=True)
        return
    for _ in range(10):                      # up to ~40s for Bill's Mac
        time.sleep(4)
        if not ROOM.exists():
            continue
        newest = None
        for line in ROOM.read_text(errors="ignore").splitlines():
            line = line.strip()
            if not line:
                continue
            try:
                d = json.loads(line)
            except Exception:
                continue
            if d.get("from") == "bill" and d.get("ts", "") > before:
                newest = d
        if newest and not _bad(newest.get("body")):
            _log_trains("Bill", "bill", work, newest.get("body", ""))
            return
    print("[live-workers] Bill no answer this cycle — no train", flush=True)


def main():
    # 2026-07-29: Bill is the CONCIERGE on a SINGLE Mac — the ~6s fast cadence wedged his one
    # qwen (repeatedly). He's driven at a concierge pace by qsb-bill-concierge / the Bill<->Wren
    # coordinator (every 10-30min) instead. TP/Asa are on their own boxes and keep the fast pace.
    # BILL_EVERY: only ping Bill once every N fast-cycles so his Mac stays healthy.
    print("[live-workers] continuous daemon start — TP + Asa fast; Bill throttled (concierge Mac)", flush=True)
    import os as _os
    BILL_EVERY = int(_os.environ.get("BILL_EVERY_CYCLES", "40"))   # ~40*6s = every ~4min at most
    i = 0
    while True:
        work = WORK[i % len(WORK)]
        i += 1
        threads = [
            threading.Thread(target=do_cockpit, args=("tp", "tp_pip", "192.168.1.91", "TP-Pip", work)),
            threading.Thread(target=do_cockpit, args=("asa", "acer_cass", "192.168.1.41", "Asa", work)),
        ]
        if BILL_EVERY > 0 and i % BILL_EVERY == 0:
            threads.append(threading.Thread(target=do_bill, args=(work,)))
        for t in threads:
            t.start()
        for t in threads:
            # allow for the one health-gated retry inside do_cockpit (2x45s) without
            # wedging the whole loop; threads are daemon-like and the next cycle proceeds.
            t.join(timeout=100)
        time.sleep(CYCLE_SLEEP)


if __name__ == "__main__":
    main()
