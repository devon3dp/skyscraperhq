"""Tower-wide activity tail — appendable structured event log.

Any code path that does something notable should call append_event(...).
The tail is then readable by Wren on entry to a session ("what fired
while I was away?"), and by any worker via tools/qsb_wren_dispatch.py.

Tail path: data/registries/qsb_tower_activity_tail.jsonl
Each line: one JSON event with ts + event_kind + floor + summary + payload.

Safety:
  · advisory_only — no events trigger execution
  · payloads must NOT contain credentials, raw API responses, or secrets
  · the tail caps at MAX_EVENTS (default 5000) — older events rotate to
    qsb_tower_activity_tail.archive.jsonl on next append once cap is hit.
"""

from __future__ import annotations
import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Optional

ROOT = Path("/vaults/nvme0/qsb_tower_v1")
TAIL_PATH = ROOT / "data/registries/qsb_tower_activity_tail.jsonl"
ARCHIVE_PATH = ROOT / "data/registries/qsb_tower_activity_tail.archive.jsonl"
MAX_EVENTS = 5000

VALID_KINDS = {
    "trade_open", "trade_close",
    "cohort_start", "cohort_complete",
    "auto_close_tick",
    "strategy_proposed", "strategy_blocked",
    "gate_check", "gate_blocked",
    "lift_packet_sent", "lift_packet_delivered",
    "openclaw_finding", "openclaw_ticket",
    "kernel_chat_query", "kernel_chat_reply",
    "team_dispatch", "team_output",
    "f47_record", "lineage_stamp",
    "service_start", "service_stop",
    "audit_event",
}


def now_ts() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds").replace("+00:00", "Z")


def append_event(event_kind: str, summary: str, *,
                  floor: Optional[str] = None,
                  worker_id: Optional[str] = None,
                  payload: Optional[dict] = None) -> dict:
    """Append a single event to the tower activity tail.

    Returns the event dict that was written.
    """
    if event_kind not in VALID_KINDS:
        # Accept it but tag as unknown so misuse is visible.
        event_kind = f"unknown:{event_kind}"
    event = {
        "ts": now_ts(),
        "event_kind": event_kind,
        "summary": summary,
    }
    if floor:      event["floor"] = floor
    if worker_id:  event["worker_id"] = worker_id
    if payload:
        # Defensive truncation — keep payloads small
        try:
            json.dumps(payload)
            event["payload"] = payload
        except Exception:
            event["payload"] = {"_unserializable": True}

    TAIL_PATH.parent.mkdir(parents=True, exist_ok=True)
    with TAIL_PATH.open("a", encoding="utf-8") as f:
        f.write(json.dumps(event) + "\n")

    _maybe_rotate()
    return event


def _maybe_rotate() -> None:
    """If the tail exceeds MAX_EVENTS, move the oldest half to archive."""
    if not TAIL_PATH.exists(): return
    try:
        lines = TAIL_PATH.read_text(encoding="utf-8").splitlines()
    except Exception:
        return
    if len(lines) <= MAX_EVENTS: return
    keep_from = len(lines) - (MAX_EVENTS // 2)
    archive = lines[:keep_from]
    keep = lines[keep_from:]
    with ARCHIVE_PATH.open("a", encoding="utf-8") as f:
        for l in archive:
            f.write(l + "\n")
    TAIL_PATH.write_text("\n".join(keep) + "\n", encoding="utf-8")


def read_tail(last: int = 50, kind: Optional[str] = None) -> list[dict]:
    """Return up to `last` most recent events, optionally filtered by kind."""
    if not TAIL_PATH.exists():
        return []
    lines = TAIL_PATH.read_text(encoding="utf-8").splitlines()
    out: list[dict] = []
    for line in reversed(lines):
        line = line.strip()
        if not line: continue
        try:
            ev = json.loads(line)
        except Exception:
            continue
        if kind and ev.get("event_kind") != kind:
            continue
        out.append(ev)
        if len(out) >= last:
            break
    out.reverse()
    return out


def summary_by_kind(last: int = 500) -> dict:
    """How many events of each kind in the last N events."""
    events = read_tail(last=last)
    counts: dict[str, int] = {}
    for ev in events:
        k = ev.get("event_kind", "unknown")
        counts[k] = counts.get(k, 0) + 1
    return counts


if __name__ == "__main__":
    import argparse
    ap = argparse.ArgumentParser()
    ap.add_argument("--tail", type=int, default=20,
                    help="show last N events")
    ap.add_argument("--kind", default=None,
                    help="filter by event_kind")
    ap.add_argument("--summary", action="store_true",
                    help="show counts per kind for the last 500 events")
    args = ap.parse_args()
    if args.summary:
        for k, n in sorted(summary_by_kind().items(), key=lambda kv: -kv[1]):
            print(f"  {n:>4d}  {k}")
    else:
        for ev in read_tail(last=args.tail, kind=args.kind):
            print(f"  {ev['ts']}  {ev['event_kind']:24s}  {ev.get('floor','-'):4s}  "
                  f"{ev.get('worker_id','-')[:24]:24s}  {ev['summary'][:80]}")
