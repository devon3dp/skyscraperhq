#!/usr/bin/env python3
"""qsb_worker_needs_queue.py — the RECEIVING side of worker activation.

As the QSB Tower switches on, ~2000 floor workers each post a REAL per-worker
report to their per-floor activity log (data/registries/qsb_floor_{N}_worker_
activity.jsonl), written by the worker activation engine. Each report carries an
explicit `need` field (e.g. "floor card still skeleton (fit-out pending)",
"floor card 38d stale (refresh pending)", "roster card lists 5 but 280 stations
assigned here (headcount reconcile)").

This tool is the receiver. It:
  (1) reads those REAL per-worker reports (+ the honest floor activity index for
      quiet/stale floors),
  (2) aggregates + dedups them into a "worker needs queue" registry
      data/registries/qsb_worker_needs_queue.json — one entry per (floor, need),
      each citing its evidence source + a representative worker + count + ts,
  (3) DELIVERS the top needs to Wren and Codex via their REAL existing channels
      WITHOUT touching their minds:
        - Wren : appends a wake row to wren_self_schedule.jsonl (her evolution
                 loop watches this file and wakes on append) AND enqueues a
                 schema-correct leadership-comms message to
                 leadership_comms/queues/wren.jsonl (drained by her live :8855
                 client into delivered/wren.jsonl — the proven path).
        - Codex: books a Task Council task via qsb_council_tasks.create(...);
                 the Codex autorunner picks open, unowned, real tasks.
  (4) exposes a read-only HTTP section (--serve) other dashboards can pull.

R01 HONESTY: every need in the queue is REAL and CITED — it comes verbatim from
a worker report row (or the honest activity index) with the exact source file +
timestamp. Nothing is invented. If there are zero real needs, the queue is empty.

BOUNDARIES (do not edit these — this tool only READS them):
  qsb_worker_activation_engine.py, (a chain reporter if present),
  qsb_floor_activity_index.py, qsb_tower_transit_map.py, and any Wren/Codex
  mind/persona file. This tool owns ONLY qsb_worker_needs_queue.py + the
  qsb_worker_needs_queue.json registry (+ its own delivery-cursor file).

Usage:
  python3 tools/qsb_worker_needs_queue.py                 # aggregate + deliver
  python3 tools/qsb_worker_needs_queue.py --no-deliver    # aggregate only
  python3 tools/qsb_worker_needs_queue.py --top N         # deliver top-N (dflt 5)
  python3 tools/qsb_worker_needs_queue.py --serve [PORT]  # read-only queue http
"""
from __future__ import annotations

import glob
import json
import os
import re
import sys
import time
import uuid
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
REG = ROOT / "data" / "registries"

# ---- REAL sources this receiver reads (never writes) --------------------------
PERFLOOR_GLOB = str(REG / "qsb_floor_*_worker_activity.jsonl")
ACTIVITY_INDEX = REG / "qsb_floor_activity_index.json"

# ---- The one registry this tool OWNS -----------------------------------------
QUEUE = REG / "qsb_worker_needs_queue.json"
DELIVERY_CURSOR = REG / "qsb_worker_needs_delivery_cursor.json"

# ---- Wren's REAL channels (append-only; NOT her mind) ------------------------
WREN_SELF_SCHEDULE = REG / "wren_self_schedule.jsonl"   # her evolution loop wakes on append
COMMS = REG / "leadership_comms"
WREN_QUEUE = COMMS / "queues" / "wren.jsonl"            # her live :8855 client drains this

# ---- audit -------------------------------------------------------------------
F47 = REG / "qsb_f47_team_records.jsonl"

_FLOOR_RE = re.compile(r"qsb_floor_(\d+)_worker_activity\.jsonl$")


def utc() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def _age_days(ts: str) -> float | None:
    if not ts:
        return None
    try:
        t = datetime.fromisoformat(ts.replace("Z", "+00:00"))
        return round((datetime.now(timezone.utc) - t).total_seconds() / 86400.0, 2)
    except Exception:
        return None


# ------------------------------------------------------------------ aggregation
def collect_real_needs() -> list[dict]:
    """Read every per-floor worker-activity log and fold each REAL `need` into a
    deduped list keyed on (floor, need). Each entry cites its evidence source +
    the representative worker + latest ts + how many workers reported it."""
    agg: dict[tuple, dict] = {}
    for fp in sorted(glob.glob(PERFLOOR_GLOB)):
        m = _FLOOR_RE.search(fp)
        floor = int(m.group(1)) if m else None
        src_rel = os.path.relpath(fp, ROOT)
        try:
            lines = Path(fp).read_text().splitlines()
        except Exception:
            continue
        for line in lines:
            line = line.strip()
            if not line:
                continue
            try:
                r = json.loads(line)
            except Exception:
                continue
            need = (r.get("need") or "").strip()
            if not need:
                continue
            fl = r.get("floor", floor)
            key = (fl, need)
            e = agg.get(key)
            ts = r.get("ts") or ""
            if e is None:
                agg[key] = {
                    "floor": fl,
                    "floor_manager": r.get("floor_manager"),
                    "need": need,
                    "from_worker": r.get("worker_id"),
                    "lead": r.get("floor_manager"),
                    "room": r.get("room"),
                    "reported_by_count": 1,
                    "evidence_source": src_rel,
                    "evidence_example": (r.get("message") or "")[:400],
                    "first_ts": ts,
                    "ts": ts,
                }
            else:
                e["reported_by_count"] += 1
                if ts and (not e["ts"] or ts > e["ts"]):
                    e["ts"] = ts
                if ts and (not e["first_ts"] or ts < e["first_ts"]):
                    e["first_ts"] = ts
    return list(agg.values())


def collect_quiet_floor_needs() -> list[dict]:
    """The honest activity index marks floors active/quiet with a cited source.
    A floor that has gone quiet (active:false) with a real last_ts is a REAL
    'this floor needs attention' signal — cite the index + the floor's source."""
    out: list[dict] = []
    try:
        idx = json.loads(ACTIVITY_INDEX.read_text())
    except Exception:
        return out
    floors = idx.get("floors") or {}
    idx_rel = os.path.relpath(ACTIVITY_INDEX, ROOT)
    for _k, v in floors.items():
        if v.get("active"):
            continue
        last_ts = v.get("last_ts")
        # Only surface floors that HAD a real signal that has since gone quiet.
        # A floor that never emitted (last_ts None) is not a worker "report".
        if not last_ts:
            continue
        age = _age_days(last_ts)
        label = v.get("label") or ""
        mfl = re.search(r"[Ff](\d+)", label)
        fl = int(mfl.group(1)) if mfl else None
        need = f"floor gone quiet ({age}d since last signal) — {v.get('signal','')}".strip()
        out.append({
            "floor": fl,
            "floor_manager": None,
            "need": need,
            "from_worker": None,
            "lead": None,
            "room": None,
            "reported_by_count": 1,
            "evidence_source": f"{idx_rel} :: {v.get('source')}",
            "evidence_example": f"activity index marks {label} active=false; last_ts={last_ts}",
            "first_ts": last_ts,
            "ts": last_ts,
        })
    return out


def build_queue() -> dict:
    real = collect_real_needs()
    quiet = collect_quiet_floor_needs()
    entries = real + quiet
    # stable, meaningful ordering: most-reported first, then most-recent
    entries.sort(key=lambda e: (-int(e.get("reported_by_count") or 0),
                                e.get("ts") or ""), reverse=False)
    entries.sort(key=lambda e: (int(e.get("reported_by_count") or 0),
                                e.get("ts") or ""), reverse=True)
    for i, e in enumerate(entries):
        e["id"] = "need_" + "_".join(str(x) for x in (e.get("floor"), i)) \
            .replace("None", "x")
        e.setdefault("status", "open")
    total_reports = sum(int(e.get("reported_by_count") or 0) for e in entries)
    return {
        "ok": True,
        "kind": "qsb_worker_needs_queue",
        "generated_ts": utc(),
        "honesty": ("R01: every need is verbatim from a real worker report row "
                    "(qsb_floor_*_worker_activity.jsonl) or the honest floor "
                    "activity index; each entry cites evidence_source + ts. "
                    "Nothing invented."),
        "sources": [os.path.relpath(PERFLOOR_GLOB, ROOT),
                    os.path.relpath(ACTIVITY_INDEX, ROOT)],
        "distinct_needs": len(entries),
        "worker_reports_folded": total_reports,
        "needs": entries,
    }


def _atomic_write_json(path: Path, obj: dict) -> None:
    tmp = path.with_suffix(path.suffix + f".tmp.{os.getpid()}")
    tmp.write_text(json.dumps(obj, indent=2))
    os.replace(tmp, path)


def save_queue(q: dict) -> None:
    # back up before overwriting an existing registry (memory rule: BACKUP first)
    if QUEUE.exists():
        bak = QUEUE.with_name(QUEUE.name + f".bak_{utc().replace(':','').replace('-','')}")
        try:
            bak.write_text(QUEUE.read_text())
        except Exception:
            pass
    _atomic_write_json(QUEUE, q)


# --------------------------------------------------------------------- delivery
def _load_cursor() -> dict:
    try:
        return json.loads(DELIVERY_CURSOR.read_text())
    except Exception:
        return {"delivered_need_signatures": []}


def _save_cursor(c: dict) -> None:
    _atomic_write_json(DELIVERY_CURSOR, c)


def _need_sig(e: dict) -> str:
    return f"{e.get('floor')}|{e.get('need')}"


def _append_jsonl(path: Path, obj: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with open(path, "a") as f:
        f.write(json.dumps(obj, separators=(",", ":")) + "\n")


def deliver_to_wren(top: list[dict], summary_line: str) -> dict:
    """Deliver WITHOUT touching Wren's mind:
       (A) append a wake row to her self-schedule (her loop wakes on append),
       (B) enqueue a schema-correct leadership-comms message to her inbox queue
           (her live :8855 client drains it into delivered/wren.jsonl)."""
    ts = utc()
    # (A) wake her mind — pure append to the file her evolution loop watches
    wake = {
        "ts": ts,
        "source": "worker_needs_queue",
        "wake_reason": "worker_needs_surfaced",
        "distinct_needs": len(top),
        "top_need": (top[0]["need"] if top else None),
        "queue_path": os.path.relpath(QUEUE, ROOT),
        "note": summary_line,
    }
    _append_jsonl(WREN_SELF_SCHEDULE, wake)

    # (B) leadership-comms inbox message (same shape the relay enqueue() writes)
    body_lines = [f"WORKER NEEDS ROLL-UP -> Wren ({ts})",
                  summary_line, "", "Top needs (real, cited):"]
    for e in top:
        body_lines.append(
            f"  - F{e.get('floor')}: {e['need']}  "
            f"[{e.get('reported_by_count')} workers; src {e.get('evidence_source')}]")
    body_lines.append("")
    body_lines.append(f"Full queue: {os.path.relpath(QUEUE, ROOT)}")
    msg = {
        "msg_id": "wn_" + uuid.uuid4().hex[:16],
        "kind": "room",
        "from": "worker_needs_queue",
        "to": "wren",
        "ts": ts,
        "body": "\n".join(body_lines),
    }
    _append_jsonl(WREN_QUEUE, msg)
    return {"wake_appended": str(WREN_SELF_SCHEDULE), "queue_msg_id": msg["msg_id"],
            "queue_path": str(WREN_QUEUE)}


# 2026-07-30 (Claude, close-path fix): the standing Codex roll-up task's exact title.
# ONE open instance of this ever — see _existing_open_codex_task() dedup below.
CODEX_ROLLUP_TITLE = "Worker needs surfaced by activation — action the tower's real requests"

# A council task in any of these states is FINISHED/dead and no longer occupies a slot,
# so a fresh roll-up may be created. Every other state (open/claimed/in_progress/
# awaiting_*/blocked/needs_*/recycled→open …) counts as "already present" for dedup.
_TERMINAL_TASK_STATES = {
    "done", "denied", "cancelled", "rejected", "archived",
    "superseded", "duplicate", "closed", "abandoned_by_ross_order",
}


def _existing_open_codex_task(C, title: str = CODEX_ROLLUP_TITLE):
    """Return the task_id of an existing NON-terminal council task with this exact
    title, else None.

    ROOT-CAUSE FIX (2026-07-30): this tool runs on a ~2-min systemd timer
    (qsb-worker-needs-queue.timer). deliver_to_codex() used to call C.create()
    UNCONDITIONALLY every tick, so the SAME collective roll-up task was spawned
    193 times in a day. Every copy is the vague, unactionable narrative "action
    the tower's real requests", so the autonomous runner's worker can only answer
    with plan-only text ("I'll pull in…") which the 2-CEO verifier quorum
    (deepseek + openai) CORRECTLY rejects — then it recycles forever, and 168
    high-priority copies starved every genuine task out of the picker. Dedup caps
    it at ONE open instance."""
    try:
        snap = C.snapshot()
    except Exception:
        return None
    want = (title or "").strip()
    for t in snap.get("tasks", []):
        if (t.get("title") or "").strip() != want:
            continue
        if (t.get("state") or "").lower() in _TERMINAL_TASK_STATES:
            continue
        return t.get("id")
    return None


def deliver_to_codex(top: list[dict], summary_line: str) -> dict:
    """Deliver to Codex via his REAL intake: a Task Council task he can pick up.
       (Codex autorunner picks open, unowned, real tasks from qsb_council_tasks.)

       DEDUP: never create a second open copy. If a non-terminal roll-up task
       already exists, reuse it (append a note so the citation stays fresh)
       instead of spawning a duplicate. One open instance max."""
    sys.path.insert(0, str(ROOT / "tools"))
    import qsb_council_tasks as C  # noqa: E402
    desc_lines = [summary_line, "Real worker needs (cited):"]
    for e in top:
        desc_lines.append(
            f"F{e.get('floor')}: {e['need']} "
            f"({e.get('reported_by_count')} workers, src {e.get('evidence_source')})")
    desc_lines.append(f"Full queue registry: {os.path.relpath(QUEUE, ROOT)}")

    existing = _existing_open_codex_task(C, CODEX_ROLLUP_TITLE)
    if existing:
        # Silent reuse — one open instance max. The fresh citation already lives in
        # the queue registry (QUEUE) and in Wren's roll-up delivery, so we do NOT
        # append a note here (that would spam the journal ~720x/day on one task).
        return {"council_task": {"ok": True, "task_id": existing, "deduped": True},
                "deduped": True}

    # First (and only) open instance. priority="low": this is a standing triage
    # roll-up, NOT urgent build work — "high" wrongly made it dominate the
    # autorunner's priority-then-FIFO picker and starve real tasks.
    r = C.create(
        title=CODEX_ROLLUP_TITLE,
        description="\n".join(desc_lines),
        actor="claude",
        priority="low",
        tags=["worker-needs", "worker-activation", "receiving-side", "standing-rollup"],
    )
    r["deduped"] = False
    return {"council_task": r, "deduped": False}


def stamp_f47(row: dict) -> None:
    row = dict(row, ts=utc(), kind="worker_needs_delivered",
               operator="qsb_worker_needs_queue")
    _append_jsonl(F47, row)


def deliver(q: dict, top_n: int = 5) -> dict:
    cur = _load_cursor()
    already = set(cur.get("delivered_need_signatures", []))
    needs = q.get("needs", [])
    top = needs[:top_n]
    new_top = [e for e in top if _need_sig(e) not in already]
    summary = (f"{q['distinct_needs']} distinct real worker needs across the tower "
               f"({q['worker_reports_folded']} worker reports folded).")
    out = {"summary": summary, "delivered_new": len(new_top)}
    if not top:
        out["note"] = "no real needs in queue — nothing to deliver"
        return out
    out["wren"] = deliver_to_wren(top, summary)
    out["codex"] = deliver_to_codex(top, summary)
    for e in top:
        already.add(_need_sig(e))
    cur["delivered_need_signatures"] = sorted(already)
    cur["last_delivery_ts"] = utc()
    _save_cursor(cur)
    stamp_f47({
        "summary": (f"delivered top {len(top)} real worker needs to Wren "
                    f"(self_schedule wake + leadership queue) and Codex "
                    f"(council task {out['codex']['council_task'].get('task_id')}); "
                    f"{summary}"),
        "wren_queue_msg_id": out["wren"]["queue_msg_id"],
        "codex_task_id": out["codex"]["council_task"].get("task_id"),
        "distinct_needs": q["distinct_needs"],
        "no_sims": True,
    })
    return out


# ----------------------------------------------------------------- http (r/o)
def serve(port: int = 8876) -> None:
    from http.server import BaseHTTPRequestHandler, HTTPServer

    class H(BaseHTTPRequestHandler):
        def log_message(self, *a):  # quiet
            pass

        def do_GET(self):
            if self.path.rstrip("/") in ("/needs", "/api/worker_needs", ""):
                try:
                    body = QUEUE.read_bytes()
                except Exception:
                    body = json.dumps({"ok": False, "error": "queue not built yet"}).encode()
                self.send_response(200)
                self.send_header("Content-Type", "application/json")
                self.send_header("Access-Control-Allow-Origin", "*")
                self.end_headers()
                self.wfile.write(body)
            else:
                self.send_response(404)
                self.end_headers()

    print(f"[worker-needs] read-only queue at http://127.0.0.1:{port}/needs")
    HTTPServer(("127.0.0.1", port), H).serve_forever()


def main(argv: list[str]) -> int:
    if "--serve" in argv:
        i = argv.index("--serve")
        port = 8876
        if i + 1 < len(argv) and argv[i + 1].isdigit():
            port = int(argv[i + 1])
        serve(port)
        return 0

    top_n = 5
    if "--top" in argv:
        i = argv.index("--top")
        if i + 1 < len(argv) and argv[i + 1].isdigit():
            top_n = int(argv[i + 1])

    q = build_queue()
    save_queue(q)
    print(f"[worker-needs] queue built: {q['distinct_needs']} distinct real needs "
          f"from {q['worker_reports_folded']} worker reports -> "
          f"{os.path.relpath(QUEUE, ROOT)}")
    for e in q["needs"][:top_n]:
        print(f"    F{e.get('floor')}: {e['need']}  "
              f"[{e.get('reported_by_count')} workers, {e.get('evidence_source')}]")

    if "--no-deliver" in argv:
        print("[worker-needs] --no-deliver: aggregation only.")
        return 0

    d = deliver(q, top_n=top_n)
    print(f"[worker-needs] {d.get('summary','')}")
    if "wren" in d:
        print(f"    -> Wren: woke {os.path.relpath(WREN_SELF_SCHEDULE, ROOT)} "
              f"+ queued msg {d['wren']['queue_msg_id']} to her inbox")
    if "codex" in d:
        print(f"    -> Codex: council task "
              f"{d['codex']['council_task'].get('task_id')}")
    if d.get("delivered_new") == 0 and "wren" in d:
        print("    (top needs already delivered previously; re-notified current top)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
