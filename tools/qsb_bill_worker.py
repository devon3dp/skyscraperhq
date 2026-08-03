#!/usr/bin/env python3
"""
qsb_bill_worker.py — use BILL as a real worker on the live Underground.

2026-07-28, Ross: "use bill as a worker" + "route the specialist/worker trains through Bill".
The local specialist models (hermes3:8b / iquest-40B) can't run — they fight the tower's single
16GB GPU where qwen2.5:14b is pinned. Bill runs his OWN qwen2.5:14b on his OWN Mac (separate
compute), so he can carry real specialist/worker work with zero GPU contention.

This gives Bill a REAL rotating work item over the leadership relay, waits for his REAL reply
(from his Mac), and ONLY THEN logs council events so the map draws his work trains:
  · wren "wields Bill" as a specialist   -> council15->bill + wren->bill  (via _tool_station "bill")
  · Bill does the work                    -> bill->task_council
If Bill does NOT answer, NOTHING is logged (no fabricated train — R01 honesty).

systemd: qsb-bill-worker.timer (every 2 min). Run once: python3 tools/qsb_bill_worker.py
"""
import json, subprocess, sys, time, uuid
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
REG = ROOT / "data" / "registries"
ROOM = REG / "leadership_comms" / "room.jsonl"
BOARD = REG / "qsb_council_tasks.jsonl"
CLIENT = ROOT / "tools" / "qsb_leadership_client.py"
RELAY = "http://127.0.0.1:8855"

# Real work items Bill can genuinely do with his on-Mac skills / model.
WORK = [
    "system status",
    "As tower concierge, in one sentence: what's one operational risk you'd watch tonight?",
    "run: uptime",
    "In one line: summarise what a good morning briefing for Ross should contain.",
    "what do you remember",
]


def _utc():
    return time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())


def _last_bill_ts():
    """Timestamp of Bill's most recent room post (so we can detect a NEW reply)."""
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


def _new_bill_reply(since_ts):
    """Return Bill's newest room post strictly newer than since_ts, else None."""
    if not ROOM.exists():
        return None
    newest = None
    for line in ROOM.read_text(errors="ignore").splitlines():
        line = line.strip()
        if not line:
            continue
        try:
            d = json.loads(line)
        except Exception:
            continue
        if d.get("from") == "bill" and d.get("ts", "") > since_ts:
            newest = d
    return newest


def _send(work):
    subprocess.run([sys.executable, str(CLIENT), "--identity", "wren", "--relay", RELAY,
                    "--send-dm", "bill", work], capture_output=True, text=True, timeout=30)


def _journal(rows):
    with open(BOARD, "a") as f:
        for r in rows:
            f.write(json.dumps(r) + "\n")


def main():
    work = WORK[int(time.time() // 120) % len(WORK)]
    before = _last_bill_ts()
    print(f"[bill-worker] assigning: {work!r}")
    _send(work)

    reply = None
    for _ in range(12):                       # up to ~48s for Bill's Mac to answer
        time.sleep(4)
        reply = _new_bill_reply(before)
        if reply:
            break

    if not reply:
        print("[bill-worker] Bill did not answer — NOTHING logged (no fake train).")
        return

    body = (reply.get("body") or "")[:120]
    print(f"[bill-worker] Bill answered: {body!r}")
    tid = "BILLWORK_" + uuid.uuid4().hex[:8]
    ts = _utc()
    # Wren wields Bill as a specialist worker + Bill does the work -> real trains on the map.
    _journal([
        {"ts": ts, "event": "tool_selected", "actor": "wren", "task_id": tid,
         "text": f"owner uses Bill (qwen2.5:14b @ Mac worker) for: {work[:60]}"},
        {"ts": ts, "event": "noted", "actor": "bill", "task_id": tid,
         "text": f"Bill worker result: {body}"},
    ])
    print(f"[bill-worker] logged real work trains (task {tid}): wren->bill, council15->bill, bill->task_council")


if __name__ == "__main__":
    main()
