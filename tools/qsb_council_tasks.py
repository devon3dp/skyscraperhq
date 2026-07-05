#!/usr/bin/env python3
"""qsb_council_tasks.py — Shared Council task engine.

Ross 2026-07-04: Claude needs a persistent shared task board readable by
every Council member (Wren, TP-Pip, Acer-Cass, HQ-Claude, Ross himself)
that survives sessions. TaskCreate is session-scoped.

Model:
  · Event log (append-only): data/registries/qsb_council_tasks.jsonl
    - {ts, event: created|claimed|updated|noted|blocked|unblocked|done|reopened,
       task_id, actor, ...}
  · Snapshot (derived, rewritten on every write):
    data/registries/qsb_council_tasks_snapshot.json
    - {tasks: [{id, title, description, created_by, created_at,
                owner, state, priority, notes[], subtasks[],
                started_at, completed_at, completed_by, tags[]}]}

State machine:
  open → claimed → in_progress → done
  any state → blocked → any state
  done → reopened → in_progress
"""
from __future__ import annotations
import argparse, json, os, sys, time, uuid
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path("/vaults/nvme0/qsb_tower_v1")
REG = ROOT / "data/registries"
LOG = REG / "qsb_council_tasks.jsonl"
SNAPSHOT = REG / "qsb_council_tasks_snapshot.json"


def utc() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds").replace("+00:00", "Z")


def _load_events() -> list[dict]:
    if not LOG.exists():
        return []
    events = []
    for line in LOG.read_text(errors="ignore").splitlines():
        line = line.strip()
        if not line:
            continue
        try:
            events.append(json.loads(line))
        except Exception:
            pass
    return events


def _append_event(event: dict) -> None:
    LOG.parent.mkdir(parents=True, exist_ok=True)
    with LOG.open("a") as fp:
        fp.write(json.dumps(event) + "\n")


def _rebuild_snapshot() -> dict:
    events = _load_events()
    tasks: dict[str, dict] = {}
    for e in events:
        tid = e.get("task_id")
        if not tid:
            continue
        t = tasks.setdefault(tid, {
            "id": tid, "created_at": e.get("ts"), "created_by": e.get("actor","?"),
            "title": "", "description": "", "owner": None, "state": "open",
            "priority": "normal", "notes": [], "subtasks": [], "tags": [],
            "started_at": None, "completed_at": None, "completed_by": None,
            "history": [],
        })
        ev = e.get("event")
        t["history"].append({"ts": e.get("ts"), "event": ev, "actor": e.get("actor","?"),
                             "text": e.get("text","")[:200] if e.get("text") else ""})
        if ev == "created":
            t["title"] = e.get("title", "")
            t["description"] = e.get("description", "")
            t["priority"] = e.get("priority", "normal")
            t["tags"] = e.get("tags", [])
            t["state"] = "open"
        elif ev == "claimed":
            t["owner"] = e.get("actor")
            t["state"] = "claimed"
            t["started_at"] = t.get("started_at") or e.get("ts")
        elif ev == "updated":
            for k in ("title", "description", "priority", "state", "owner"):
                if k in e:
                    t[k] = e[k]
            if e.get("state") == "in_progress" and not t.get("started_at"):
                t["started_at"] = e.get("ts")
        elif ev == "noted":
            t["notes"].append({"ts": e.get("ts"), "by": e.get("actor","?"),
                               "text": e.get("text", "")[:1000]})
        elif ev == "subtask_added":
            t["subtasks"].append({"text": e.get("text","")[:200], "done": False,
                                  "by": e.get("actor","?"), "ts": e.get("ts")})
        elif ev == "assigned":
            t["assignee"] = e.get("assignee")
            t["assigned_by"] = e.get("actor")
            t["state"] = "assigned"
            t["assigned_at"] = e.get("ts")
        elif ev == "acknowledged":
            t["acknowledged_by"] = e.get("actor")
            t["acknowledged_at"] = e.get("ts")
            t["state"] = "acknowledged"
            if e.get("text"):
                t["notes"].append({"ts": e.get("ts"), "by": e.get("actor"),
                                   "text": "ACK: " + e["text"][:500]})
        elif ev == "sandbox_passed":
            t["sandbox_passed_by"] = e.get("actor")
            t["sandbox_passed_at"] = e.get("ts")
            t["state"] = "awaiting_peer_signoff"
            if e.get("text"):
                t["notes"].append({"ts": e.get("ts"), "by": e.get("actor"),
                                   "text": "SANDBOX PASS: " + e["text"][:500]})
        elif ev == "peer_signoff":
            verdict = e.get("verdict", "approve")
            reviewer = e.get("actor")
            worker = t.get("owner") or t.get("acknowledged_by")
            if reviewer == worker:
                # rejected — no self-signoff
                t["notes"].append({"ts": e.get("ts"), "by": reviewer,
                                   "text": "SELF-SIGNOFF REJECTED (peer must be a different CEO)"})
            else:
                t["peer_signoff_by"] = reviewer
                t["peer_signoff_at"] = e.get("ts")
                t["peer_signoff_verdict"] = verdict
                if verdict == "approve":
                    t["state"] = "ready_to_ship"
                else:
                    t["state"] = "in_progress"
                if e.get("text"):
                    t["notes"].append({"ts": e.get("ts"), "by": reviewer,
                                       "text": f"PEER {verdict.upper()}: " + e["text"][:500]})
        elif ev == "subtask_ticked":
            idx = e.get("subtask_index", -1)
            if 0 <= idx < len(t["subtasks"]):
                t["subtasks"][idx]["done"] = True
                t["subtasks"][idx]["ticked_by"] = e.get("actor","?")
                t["subtasks"][idx]["ticked_at"] = e.get("ts")
        elif ev == "blocked":
            t["state"] = "blocked"
            if e.get("text"):
                t["notes"].append({"ts": e.get("ts"), "by": e.get("actor","?"),
                                   "text": "BLOCKED: " + e["text"][:500]})
        elif ev == "unblocked":
            t["state"] = "in_progress" if t.get("owner") else "open"
        elif ev == "done":
            t["state"] = "done"
            t["completed_at"] = e.get("ts")
            t["completed_by"] = e.get("actor","?")
        elif ev == "reopened":
            t["state"] = "in_progress" if t.get("owner") else "open"
            t["completed_at"] = None
            t["completed_by"] = None

    snap = {
        "ts": utc(),
        "total": len(tasks),
        "open": sum(1 for t in tasks.values() if t["state"] == "open"),
        "in_progress": sum(1 for t in tasks.values() if t["state"] in ("claimed", "in_progress")),
        "blocked": sum(1 for t in tasks.values() if t["state"] == "blocked"),
        "done": sum(1 for t in tasks.values() if t["state"] == "done"),
        "tasks": sorted(tasks.values(),
                        key=lambda t: (t["state"] == "done", t.get("created_at","")),
                        reverse=False),
    }
    # Race-safe: unique tmp filename per call so concurrent writers don't fight
    import os as _os
    tmp = SNAPSHOT.with_suffix(f".tmp.{_os.getpid()}.{id(snap)}")
    try:
        tmp.write_text(json.dumps(snap, indent=2))
        tmp.replace(SNAPSHOT)
    except FileNotFoundError:
        pass  # another thread already replaced — no harm
    return snap


# ─── public API (imported by hub) ────────────────────────────────
def snapshot() -> dict:
    return _rebuild_snapshot()


def create(title: str, description: str = "", actor: str = "hq_claude",
           priority: str = "normal", tags: list = None) -> dict:
    tid = "t_" + uuid.uuid4().hex[:10]
    _append_event({"ts": utc(), "event": "created", "task_id": tid, "actor": actor,
                   "title": title, "description": description,
                   "priority": priority, "tags": tags or []})
    return {"ok": True, "task_id": tid}


def claim(task_id: str, actor: str) -> dict:
    _append_event({"ts": utc(), "event": "claimed", "task_id": task_id, "actor": actor})
    return {"ok": True}


def update(task_id: str, actor: str, **fields) -> dict:
    ev = {"ts": utc(), "event": "updated", "task_id": task_id, "actor": actor}
    ev.update({k: v for k, v in fields.items() if k in
               ("title", "description", "priority", "state", "owner")})
    _append_event(ev)
    return {"ok": True}


def note(task_id: str, actor: str, text: str) -> dict:
    _append_event({"ts": utc(), "event": "noted", "task_id": task_id, "actor": actor,
                   "text": text})
    return {"ok": True}


def block(task_id: str, actor: str, reason: str) -> dict:
    _append_event({"ts": utc(), "event": "blocked", "task_id": task_id, "actor": actor,
                   "text": reason})
    return {"ok": True}


def unblock(task_id: str, actor: str) -> dict:
    _append_event({"ts": utc(), "event": "unblocked", "task_id": task_id, "actor": actor})
    return {"ok": True}


def done(task_id: str, actor: str, summary: str = "") -> dict:
    _append_event({"ts": utc(), "event": "done", "task_id": task_id, "actor": actor,
                   "text": summary})
    return {"ok": True}


def reopen(task_id: str, actor: str) -> dict:
    _append_event({"ts": utc(), "event": "reopened", "task_id": task_id, "actor": actor})
    return {"ok": True}


def add_subtask(task_id: str, actor: str, text: str) -> dict:
    _append_event({"ts": utc(), "event": "subtask_added", "task_id": task_id,
                   "actor": actor, "text": text})
    return {"ok": True}


def assign(task_id: str, actor: str, assignee: str) -> dict:
    """Ross (or any CEO) assigns a task to a specific member. Assignee
    must ack. Two roles: assigner + assignee."""
    _append_event({"ts": utc(), "event": "assigned", "task_id": task_id,
                   "actor": actor, "assignee": assignee})
    return {"ok": True}


def ack(task_id: str, actor: str, note_text: str = "") -> dict:
    """Assignee acknowledges an assigned task (I got it, I'm on it)."""
    _append_event({"ts": utc(), "event": "acknowledged", "task_id": task_id,
                   "actor": actor, "text": note_text})
    return {"ok": True}


def sandbox_pass(task_id: str, actor: str, evidence: str) -> dict:
    """Worker self-verifies in own sandbox. Task moves to
    awaiting_peer_signoff."""
    _append_event({"ts": utc(), "event": "sandbox_passed", "task_id": task_id,
                   "actor": actor, "text": evidence[:800]})
    return {"ok": True}


def peer_signoff(task_id: str, actor: str, verdict: str = "approve",
                 comment: str = "") -> dict:
    """A DIFFERENT CEO reviews the sandbox evidence + approves/rejects.
    Worker cannot peer-sign their own task (validated in HTTP layer)."""
    _append_event({"ts": utc(), "event": "peer_signoff", "task_id": task_id,
                   "actor": actor, "verdict": verdict,
                   "text": comment[:800]})
    return {"ok": True}


def tick_subtask(task_id: str, actor: str, subtask_index: int) -> dict:
    _append_event({"ts": utc(), "event": "subtask_ticked", "task_id": task_id,
                   "actor": actor, "subtask_index": subtask_index})
    return {"ok": True}


# ─── CLI for manual work + seeding ────────────────────────────────
def main():
    ap = argparse.ArgumentParser()
    sub = ap.add_subparsers(dest="cmd", required=True)
    p_snap = sub.add_parser("snapshot");
    p_create = sub.add_parser("create")
    p_create.add_argument("--title", required=True)
    p_create.add_argument("--description", default="")
    p_create.add_argument("--actor", default="hq_claude")
    p_create.add_argument("--priority", default="normal")
    p_create.add_argument("--tags", default="")
    p_claim = sub.add_parser("claim")
    p_claim.add_argument("--id", required=True); p_claim.add_argument("--actor", required=True)
    p_done = sub.add_parser("done")
    p_done.add_argument("--id", required=True); p_done.add_argument("--actor", required=True)
    p_done.add_argument("--summary", default="")
    p_note = sub.add_parser("note")
    p_note.add_argument("--id", required=True); p_note.add_argument("--actor", required=True)
    p_note.add_argument("--text", required=True)

    args = ap.parse_args()
    if args.cmd == "snapshot":
        print(json.dumps(snapshot(), indent=2))
    elif args.cmd == "create":
        r = create(args.title, args.description, args.actor, args.priority,
                   [t.strip() for t in args.tags.split(",") if t.strip()])
        print(json.dumps(r))
    elif args.cmd == "claim":
        print(json.dumps(claim(args.id, args.actor)))
    elif args.cmd == "done":
        print(json.dumps(done(args.id, args.actor, args.summary)))
    elif args.cmd == "note":
        print(json.dumps(note(args.id, args.actor, args.text)))


if __name__ == "__main__":
    main()
