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
from datetime import datetime, timezone, timedelta
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


def _load_gov2_tasks() -> dict:
    """2026-07-18: fold Governance V2 task events into the board so the :8852 dashboard shows
    the real V2 tasks + completions, not only legacy V1. ADD not TAKE."""
    gov2 = LOG.parent / "qsb_gov2_task_events.jsonl"
    if not gov2.exists():
        return {}
    STATE = {
        "TASK_CREATED": "open", "TASK_ADMITTED": "open",
        "TASK_OWNER_ASSIGNED": "in_progress", "TASK_PARTNER_ASSIGNED": "in_progress",
        "WORK_PACKAGE_ASSIGNED": "in_progress", "WORK_STARTED": "in_progress",
        "PROGRESS_UPDATE": "in_progress", "EVIDENCE_ADDED": "in_progress",
        "VERIFICATION_REQUESTED": "awaiting_peer_signoff", "CORRECTION_REQUIRED": "in_progress",
        "TASK_VERIFIED": "in_progress", "AWAITING_ROSS": "awaiting_peer_signoff",
        "TASK_COMPLETED": "done", "TASK_REPORTED": "done", "TASK_ARCHIVED": "done",
        "TASK_BLOCKED": "blocked", "TASK_PAUSED": "blocked",
        "TASK_CANCEL_REQUESTED": "blocked", "TASK_CANCELLED": "cancelled",
    }
    tasks: dict[str, dict] = {}
    for line in gov2.read_text(errors="ignore").splitlines():
        line = line.strip()
        if not line:
            continue
        try:
            e = json.loads(line)
        except Exception:
            continue
        tid = e.get("TASK_ID")
        if not tid:
            continue
        t = tasks.setdefault(tid, {
            "id": tid, "created_at": e.get("TIMESTAMP"), "created_by": e.get("ACTOR", "?"),
            "title": tid, "description": "", "owner": None, "state": "open", "priority": "normal",
            "notes": [], "subtasks": [], "tags": ["governance_v2"], "started_at": None,
            "completed_at": None, "completed_by": None, "history": [], "source": "gov2"})
        et = e.get("EVENT_TYPE", "")
        t["history"].append({"ts": e.get("TIMESTAMP"), "event": et, "actor": e.get("ACTOR", "?"),
                             "text": (e.get("SUMMARY") or "")[:200]})
        if et in STATE:
            t["state"] = STATE[et]
        if et == "TASK_OWNER_ASSIGNED":
            t["owner"] = e.get("ACTOR")
        if et == "TASK_COMPLETED":
            t["completed_at"] = e.get("TIMESTAMP"); t["completed_by"] = e.get("ACTOR")
        if e.get("SUMMARY"):
            t["description"] = (e.get("SUMMARY") or "")[:200]
    return tasks


# 2026-07-29 councilbottleneck fix: qsb_live_workers.py + the liveness daemons append worker-PING
# events (ids CEOWORK_*/BILLWORK_*/LIVE_*/UG_*) to the SAME board file so the Underground transit
# map can animate live trains from them. They are NOT real council tasks, yet they were rebuilt AS
# tasks and made up ~63% of snapshot() (648/785), burying the real backlog. This read-side filter
# excludes those ids from the council TASK VIEW only — the raw JSONL is untouched (append-only, zero
# data loss) so the transit map still reads every row. Reversible: delete the prefixes below.
_NON_COUNCIL_TID_PREFIXES = ("CEOWORK_", "BILLWORK_", "TPWORK_", "ASAWORK_", "LIVE_", "UG_", "ORACLE_")


def _is_council_task_id(tid: str) -> bool:
    return not str(tid or "").startswith(_NON_COUNCIL_TID_PREFIXES)


# ─── ACTIVE-BOARD CAP (Claude 2026-07-30, Ross request) ──────────────────────
# Ross: the OPEN backlog ballooned to ~800; the tower can only productively evolve
# a focused ~20 at once. This is a DIFFERENT ceiling from the per-CEO cap (3) and
# the GLOBAL_WIP_CAP (12, owned in-flight only): it bounds the ENTIRE active board
# = open + in-flight tasks the picker considers. When the board is at the cap, a
# NEWLY-created task does NOT bloat open — it lands in the RESERVE (state=reserved,
# via a `parked` event) instead. Nothing is lost; promote-on-drain (refill_board)
# brings the highest-priority reserved task back to open as the board drains.
# Env-configurable. Reserved/dropped are NOT counted as active board.
ACTIVE_BOARD_CAP = int(os.environ.get("COUNCIL_ACTIVE_BOARD_CAP", "20"))
# States that occupy the active board (mirror the autorunner picker: open + the
# in-flight/stalled states it re-picks). 'reserved', 'blocked', and all terminal
# states are OFF-board. blocked waits on an external condition and is off-picker.
ACTIVE_BOARD_STATES = {
    "open", "claimed", "in_progress", "assigned", "acknowledged",
    "awaiting_peer_signoff", "awaiting_verification", "ready_to_ship",
    "needs_rework", "needs_partner", "needs_proof", "needs_second_verifier",
    "needs_verification",
}
_PRIO_RANK = {"high": 0, "normal": 1, "med": 1, "medium": 1, "low": 2}


def _rebuild_snapshot() -> dict:
    events = _load_events()
    tasks: dict[str, dict] = {}
    for e in events:
        tid = e.get("task_id")
        if not tid:
            continue
        # skip worker-ping / liveness trains — they belong to the transit map, not the task board
        if not _is_council_task_id(tid):
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
            # 2026-07-19 FIX C1: preserve build context through the snapshot (was silently dropped,
            # so run_backlog always got empty context and every "build on top" came out standalone).
            t["target_file"] = e.get("target_file", "")
            t["context_files"] = e.get("context_files", [])
            t["ceo_rationale"] = e.get("ceo_rationale", "")
            # 2026-08-03 PHASE-2 INTAKE GATE (Claude): an implementation intake missing the
            # research minimum (affected component + evidence + definition-of-done) is admitted
            # to state 'needs_research' — OFF the active board, OFF every CEO slot, OFF GATE18
            # work states — so a vague/narrative task can never generate implementation activity.
            # Complete intakes still land 'open'. Reversible: without intake_state the task is
            # 'open' exactly as before. Enrich → open via a normal `updated` state event.
            if e.get("intake_state"):
                t["state"] = e.get("intake_state")
            else:
                t["state"] = "open"
            if e.get("missing_fields"):
                t["missing_fields"] = e.get("missing_fields")
                if "needs_research" not in (t.get("tags") or []):
                    t["tags"] = list(t.get("tags") or []) + ["needs_research"]
            if e.get("dedup_key"):
                t["dedup_key"] = e.get("dedup_key")
        elif ev == "proposed":
            t["title"] = e.get("title", "")
            t["description"] = e.get("description", "")
            t["priority"] = e.get("priority", "normal")
            t["tags"] = e.get("tags", [])
            t["state"] = "pending_admission"
            t["proposer"] = e.get("actor")
            t["admission_votes"] = []
        elif ev == "admission_voted":
            votes = t.get("admission_votes") or []
            voter = e.get("actor","?")
            verdict = e.get("verdict","approve")
            # dedupe: keep latest vote per voter
            votes = [v for v in votes if v.get("by") != voter]
            votes.append({"by": voter, "verdict": verdict, "reason": e.get("reason",""), "ts": e.get("ts")})
            t["admission_votes"] = votes
            # Tally: skip proposer votes; ≥2 approve → open, ≥2 reject → denied
            proposer = t.get("proposer")
            valid = [v for v in votes if v["by"] != proposer]
            approves = sum(1 for v in valid if v["verdict"] == "approve")
            rejects = sum(1 for v in valid if v["verdict"] == "reject")
            if t.get("state") == "pending_admission":
                if approves >= 2:
                    t["state"] = "open"
                    t["admitted_at"] = e.get("ts")
                elif rejects >= 2:
                    t["state"] = "denied"
                    t["denied_at"] = e.get("ts")
        elif ev == "claimed":
            t["owner"] = e.get("actor")
            t["state"] = "claimed"
            t["started_at"] = t.get("started_at") or e.get("ts")
        elif ev == "updated":
            # Permit audited repair of build metadata after intake. These fields
            # were previously preserved only on `created`, trapping old tasks
            # without a deployable target forever.
            for k in ("title", "description", "priority", "state", "owner",
                      "target_file", "context_files", "ceo_rationale"):
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
        elif ev == "awaiting_verification":
            # 2026-07-19 FIX F1: this event had NO handler — 91+ events were silently ignored,
            # freezing task state. Now it advances the task and is timestamped for the reaper.
            t["state"] = "awaiting_verification"
            t["awaiting_verification_at"] = e.get("ts")
            if e.get("text"):
                t["notes"].append({"ts": e.get("ts"), "by": e.get("actor", "?"),
                                   "text": "AWAITING VERIFICATION: " + e["text"][:500]})
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
            # PHASE-6 (Claude 2026-08-03): surface the structured accountability fields so a
            # blocked task honestly reports its dependency / owner / retry posture on the board.
            for _k in ("blocking_dependency", "responsible_component", "last_attempt",
                       "retry_count", "next_attempt_after", "required_resolution"):
                if e.get(_k) not in (None, ""):
                    t[_k] = e.get(_k)
            if e.get("text"):
                t["notes"].append({"ts": e.get("ts"), "by": e.get("actor","?"),
                                   "text": "BLOCKED: " + e["text"][:500]})
        elif ev == "unblocked":
            t["state"] = "in_progress" if t.get("owner") else "open"
        elif ev == "done":
            t["state"] = "done"
            t["completed_at"] = e.get("ts")
            t["completed_by"] = e.get("actor","?")
            # 2026-07-30 CLOSE-THE-LOOP (Claude): a real completion carries a verifiable proof_path
            # (the live file that actually changed) + its sha. The autorunner only emits these when
            # apply_bridge made a real, gated, NON-tests file change; a narration-only "done" carries
            # none, so an empty proof_path is now an honest signal that no live change shipped.
            if e.get("proof_path"):
                t["proof_path"] = e.get("proof_path")
            if e.get("proof_sha"):
                t["proof_sha"] = e.get("proof_sha")
            if "applied" in e:
                t["applied"] = e.get("applied")
        elif ev in ("dropped", "resolved", "superseded"):
            # 2026-07-30: duplicate/recycler tasks closed as SUPERSEDED (NOT completed) during
            # backlog dedup. Terminal so they leave the open pool, but kept distinct from 'done'
            # so a supersede is never miscounted as real work delivered (R01 honest).
            t["state"] = "dropped"
            t["completed_at"] = e.get("ts")
            t["completed_by"] = e.get("actor", "?")
            if e.get("reason"):
                t["notes"].append({"ts": e.get("ts"), "by": e.get("actor", "?"),
                                   "text": "DROPPED (superseded, not done): " + str(e["reason"])[:300]})
        elif ev == "parked":
            # 2026-07-30 ACTIVE-BOARD CAP (Claude): a task moved to the RESERVE. Honest —
            # NOT done, NOT dropped, NOT deleted: it is deferred out of the active board so
            # the picker works a focused ~20 while the rest queue in reserve. `promote`
            # brings it back to open. owner is cleared (a reserved task holds no WIP slot).
            t["state"] = "reserved"
            t["owner"] = None
            t["parked_at"] = e.get("ts")
            t["parked_by"] = e.get("actor", "?")
            if e.get("reason") or e.get("text"):
                t["notes"].append({"ts": e.get("ts"), "by": e.get("actor", "?"),
                                   "text": "PARKED to reserve (deferred, not done): "
                                           + str(e.get("reason") or e.get("text"))[:300]})
        elif ev == "promoted":
            # 2026-07-30 PROMOTE-ON-DRAIN (Claude): a reserved task returns to the active
            # board as OPEN (owner cleared, re-pickable) when the board drops below the cap.
            t["state"] = "open"
            t["owner"] = None
            t["promoted_at"] = e.get("ts")
            if e.get("text"):
                t["notes"].append({"ts": e.get("ts"), "by": e.get("actor", "?"),
                                   "text": "PROMOTED from reserve → active board: " + e["text"][:300]})
        elif ev == "reopened":
            t["state"] = "in_progress" if t.get("owner") else "open"
            t["completed_at"] = None
            t["completed_by"] = None
            # Ross 2026-07-05 #166: reset clocks so SLA doesn't count old stale time
            t["started_at"] = e.get("ts")
            t["claimed_at"] = e.get("ts") if t.get("owner") else None
            t["assigned_at"] = None
            t["sandbox_passed_by"] = None
            t["sandbox_passed_at"] = None
            t["peer_signoff_by"] = None
            t["peer_signoff_at"] = None
            t["peer_signoff_verdict"] = None
        elif ev == "recycled":
            # 2026-07-20 Ross: "there should be no blocked tasks — they go back into the task pool to
            # be fixed; blocked only creates a bottleneck". A failed/exhausted task is NOT dead-ended;
            # it returns to the POOL as OPEN (owner cleared) so the autorunner re-picks and retries it
            # with the accumulated correction context. `retry_after` (set by the runner with exponential
            # backoff) keeps a genuinely-stuck task from thrashing — it re-enters, just not instantly.
            t["owner"] = None
            t["state"] = "open"
            t["completed_at"] = None; t["completed_by"] = None
            t["started_at"] = None; t["claimed_at"] = None; t["assigned_at"] = None
            t["sandbox_passed_by"] = None; t["sandbox_passed_at"] = None
            t["peer_signoff_by"] = None; t["peer_signoff_at"] = None; t["peer_signoff_verdict"] = None
            t["rework_rounds"] = int(t.get("rework_rounds", 0)) + 1
            t["retry_after"] = e.get("retry_after")   # ISO ts; picker skips until then
            if e.get("text"):
                t["notes"].append({"ts": e.get("ts"), "by": e.get("actor", "?"),
                                   "text": f"RECYCLED to pool (round {t['rework_rounds']}): " + e["text"][:400]})

    # 2026-07-18: fold in Governance V2 tasks (ADD not TAKE). Only add gov2 tasks NOT already on the
    # V1 board — the V1 board carries the full lifecycle (claimed/peer_signoff/done) and is authoritative
    # for shared IDs, so gov2's partial record must not overwrite a completed V1 task.
    for _tid, _t in _load_gov2_tasks().items():
        if _tid not in tasks:
            tasks[_tid] = _t

    # 2026-08-03 (Claude): active_board is the WORKING board (what the picker works),
    # which is capped. A burst can transiently leave open tasks un-parked, making a raw
    # count spike past the cap (the dash then showed e.g. 54). Report the capped working
    # board honestly = in-flight (un-parkable) + open up to the remaining cap, and surface
    # the true raw count + the un-parked open backlog as separate fields (nothing hidden).
    _open_ct = sum(1 for t in tasks.values() if (t.get("state") or "").lower() == "open")
    _inflight_ct = sum(1 for t in tasks.values()
                       if (t.get("state") or "").lower() in ACTIVE_BOARD_STATES
                       and (t.get("state") or "").lower() != "open")
    _active_raw = _open_ct + _inflight_ct
    _active_board = _inflight_ct + min(_open_ct, max(0, ACTIVE_BOARD_CAP - _inflight_ct))

    snap = {
        "ts": utc(),
        "total": len(tasks),
        "open": sum(1 for t in tasks.values() if t["state"] == "open"),
        "in_progress": sum(1 for t in tasks.values() if t["state"] in ("claimed", "in_progress")),
        "blocked": sum(1 for t in tasks.values() if t["state"] == "blocked"),
        "done": sum(1 for t in tasks.values() if t["state"] == "done"),
        # 2026-07-30 ACTIVE-BOARD CAP (Claude): active_board = tasks the picker works
        # (in-flight + open up to cap); reserved = the parked backlog; dropped = junk.
        "active_board": _active_board,
        "active_board_raw": _active_raw,
        "active_board_overflow": max(0, _active_raw - _active_board),
        "reserved": sum(1 for t in tasks.values() if t["state"] == "reserved"),
        "dropped": sum(1 for t in tasks.values() if t["state"] == "dropped"),
        # 2026-08-03 PHASE-2 (Claude): intakes held for clarification — visible + separately
        # counted, NOT part of active_board (so a narrative flood cannot masquerade as work).
        "needs_research": sum(1 for t in tasks.values() if t["state"] == "needs_research"),
        "active_board_cap": ACTIVE_BOARD_CAP,
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


# ─── active-board helpers (Claude 2026-07-30) ────────────────────────────────
def active_board_tasks(snap: dict = None) -> list:
    snap = snap or _rebuild_snapshot()
    return [t for t in snap.get("tasks", [])
            if (t.get("state") or "").lower() in ACTIVE_BOARD_STATES]


def active_board_count(snap: dict = None) -> int:
    return len(active_board_tasks(snap=snap))


def reserved_tasks(snap: dict = None) -> list:
    snap = snap or _rebuild_snapshot()
    return [t for t in snap.get("tasks", []) if (t.get("state") or "").lower() == "reserved"]


def park(task_id: str, actor: str = "board_cap", reason: str = "") -> dict:
    """Move a task to the RESERVE (deferred, NOT done, NOT dropped). Reversible via promote()."""
    _append_event({"ts": utc(), "event": "parked", "task_id": task_id,
                   "actor": actor, "reason": reason[:400]})
    return {"ok": True, "state": "reserved"}


def promote(task_id: str, actor: str = "board_refill", note: str = "") -> dict:
    """Bring a reserved task back to the active board as OPEN (promote-on-drain)."""
    _append_event({"ts": utc(), "event": "promoted", "task_id": task_id,
                   "actor": actor, "text": note[:400]})
    return {"ok": True, "state": "open"}


def refill_board(actor: str = "board_refill", cap: int = None, max_promote: int = None) -> dict:
    """PROMOTE-ON-DRAIN: while the active board is below the cap, promote the highest
    -priority (then oldest) reserved task back to open. Called after a task drains
    (done/dropped/park) so the tower always works a focused ~cap, self-refilling from
    reserve. Non-destructive: only appends `promoted` events."""
    cap = ACTIVE_BOARD_CAP if cap is None else cap
    snap = _rebuild_snapshot()
    board = active_board_count(snap=snap)
    slots = cap - board
    if slots <= 0:
        return {"promoted": 0, "board": board, "cap": cap, "reason": "board at/over cap"}
    reserve = reserved_tasks(snap=snap)
    reserve.sort(key=lambda t: (_PRIO_RANK.get((t.get("priority") or "normal").lower(), 1),
                                t.get("created_at", "")))
    if max_promote is not None:
        slots = min(slots, max_promote)
    promoted = []
    for t in reserve[:slots]:
        promote(t["id"], actor=actor, note=f"board drained to {board}/{cap} — refilled from reserve")
        promoted.append(t["id"])
        board += 1
    return {"promoted": len(promoted), "task_ids": promoted, "board": board, "cap": cap}


# ─── PHASE-2 · deterministic dedup + intake completeness (Claude 2026-08-03) ──
# Baseline defect (proven): 375 duplicate-title groups (1,343 tasks; one title ×193);
# vague/narrative tasks flood the open board faster than they can ever be verified.
# create() had NO dedup and NO intake gate — every intake became a fresh active task.
# These two gates are deterministic (no fuzzy similarity, no external model) and
# reversible (env kill-switches COUNCIL_DEDUP / COUNCIL_INTAKE_GATE, default on).
import re as _re

INTAKE_GATE_ENABLED = os.environ.get("COUNCIL_INTAKE_GATE", "1") not in ("0", "false", "False")
DEDUP_ENABLED = os.environ.get("COUNCIL_DEDUP", "1") not in ("0", "false", "False")

# Terminal states are NOT dedup targets — a finished/dropped task does not block a
# genuine NEW raise of the same need (it may have regressed).
_TERMINAL_STATES_FOR_DEDUP = {
    "done", "dropped", "cancelled", "denied", "superseded", "closed",
    "archived", "rejected", "duplicate",
}
_DEDUP_STOPWORDS = {
    "the", "a", "an", "and", "or", "for", "to", "of", "in", "on", "with", "is",
    "are", "be", "task", "please", "we", "need", "should", "make", "get", "this",
    "that", "it", "its", "into", "from", "so", "our", "your", "their",
}


def _extract_components(text: str) -> set:
    """Structured 'affected surface' from real fields — floors, py/service/registry
    files, ports. This is the anchor that makes dedup about the AFFECTED COMPONENT,
    not title-similarity alone."""
    tl = (text or "").lower()
    comps = set()
    for n in _re.findall(r'floor[_ ]?(\d{1,3})', tl):
        comps.add(f"floor_{int(n)}")
    comps |= {f for f in _re.findall(r'\b([a-z0-9_]+\.py)\b', tl)}
    comps |= {s for s in _re.findall(r'\b([a-z0-9_.-]+\.service)\b', tl)}
    comps |= {f for f in _re.findall(r'\b([a-z0-9_]+\.(?:json|jsonl|md|html|js|css|sh|txt|yaml|yml))\b', tl)}
    comps |= {f"port:{p}" for p in _re.findall(r':(\d{4,5})\b', tl)}
    return comps


def _goal_tokens(title: str) -> frozenset:
    """Normalised significant tokens of the GOAL (title). Deterministic set —
    equality, not similarity."""
    toks = _re.findall(r'[a-z0-9]{3,}', (title or "").lower())
    return frozenset(t for t in toks if t not in _DEDUP_STOPWORDS)


def _dedup_key(title: str, description: str = "", tags: list = None) -> str:
    """Canonical dedup key from REAL fields: affected-component set (title+desc+tags)
    + goal-token set (title). Two intakes collide ONLY when both the affected surface
    AND the goal signature match — different component or different goal => new task
    admitted (genuinely different scope)."""
    surface = " ".join([title or "", description or "", " ".join(tags or [])])
    comps = _extract_components(surface)
    goal = _goal_tokens(title)
    return "C:" + ",".join(sorted(comps)) + "|G:" + ",".join(sorted(goal))


def _find_open_dup(key: str, snap: dict = None):
    """Return an existing NON-terminal task whose dedup key equals `key`, else None.
    Scans open/active/reserved/needs_research/blocked — never terminal tasks."""
    snap = snap or _rebuild_snapshot()
    for t in snap.get("tasks", []):
        if (t.get("state") or "").lower() in _TERMINAL_STATES_FOR_DEDUP:
            continue
        tkey = t.get("dedup_key") or _dedup_key(t.get("title", ""),
                                                t.get("description", ""), t.get("tags"))
        if tkey == key:
            return t
    return None


# Intake completeness — an implementation intake needs a research minimum before it
# can occupy the active implementation board: an AFFECTED component, EVIDENCE of the
# need, and a DEFINITION OF DONE. owner/partner/verifier are enforced downstream at
# assignment/verification by the EXISTING GATE 17 / GATE 18 / peer_signoff — not
# crammed into create() (they are unknowable at intake).
_EVIDENCE_MARKERS = ("evidence:", "proof:", "repro", "observed", "traceback", "error:",
                     "error ", "log:", "logs ", "because", "symptom", "baseline",
                     "measured", "found ", "stack trace", "failing", "returns ", "throws")
_DOD_MARKERS = ("dod:", "definition of done", "done when", "acceptance", "success:",
                "expected:", "must ", "should ", "so that", "verify that", "pass ",
                "green", "target:")
_AFFECTED_MARKERS = ("affected:", "file:", "files:", "component:", "service:", "floor",
                     "target:", "module:", "path:", "endpoint", "registry")


def _has_marker(text: str, markers) -> bool:
    return any(m in text for m in markers)


def _intake_assess(title: str, description: str = "", tags: list = None):
    """Return (complete, missing[]). Complete = has affected component + evidence +
    definition-of-done. Deterministic keyword/structure test, no model."""
    text = ((title or "") + "\n" + (description or "")).lower()
    comps = _extract_components((title or "") + " " + (description or "") + " " + " ".join(tags or []))
    has_affected = bool(comps) or _has_marker(text, _AFFECTED_MARKERS)
    has_evidence = _has_marker(text, _EVIDENCE_MARKERS)
    has_dod = _has_marker(text, _DOD_MARKERS)
    missing = []
    if not has_affected:
        missing.append("affected_component")
    if not has_evidence:
        missing.append("evidence")
    if not has_dod:
        missing.append("definition_of_done")
    return (len(missing) == 0), missing


def create(title: str, description: str = "", actor: str = "wren",
           priority: str = "normal", tags: list = None) -> dict:
    tags = tags or []
    key = _dedup_key(title, description, tags)

    # (1) DETERMINISTIC DEDUP — before minting a task, link to any existing NON-terminal
    # task with the same structured key. Do NOT create a second active implementation
    # task; append an audit note to the existing one and return linked_to.
    if DEDUP_ENABLED:
        dup = _find_open_dup(key)
        if dup is not None:
            _append_event({"ts": utc(), "event": "noted", "task_id": dup["id"],
                           "actor": "dedup",
                           "text": (f"INTAKE LINKED (deterministic dedup, key={key}): a new "
                                    f"intake by {actor} — '{(title or '')[:120]}' — matches this "
                                    f"existing task's affected-component + goal signature. No "
                                    f"second active task created.")})
            return {"ok": True, "task_id": dup["id"], "linked_to": dup["id"],
                    "deduped": True, "state": dup.get("state"), "dedup_key": key}

    # (2) INTAKE COMPLETENESS — an incomplete implementation intake enters needs_research
    # (off the active board) instead of the active implementation board.
    complete, missing = (True, [])
    if INTAKE_GATE_ENABLED:
        complete, missing = _intake_assess(title, description, tags)

    tid = "t_" + uuid.uuid4().hex[:10]
    ev = {"ts": utc(), "event": "created", "task_id": tid, "actor": actor,
          "title": title, "description": description,
          "priority": priority, "tags": tags, "dedup_key": key}
    if not complete:
        ev["intake_state"] = "needs_research"
        ev["missing_fields"] = missing
    _append_event(ev)

    if not complete:
        # needs_research is OFF the active board already — no park needed.
        return {"ok": True, "task_id": tid, "state": "needs_research",
                "needs_research": True, "missing": missing, "dedup_key": key,
                "cap": ACTIVE_BOARD_CAP}

    # (3) ACTIVE-BOARD CAP: a complete NEW task overflows into the RESERVE when the board
    # is already full instead of bloating `open`. Nothing lost — promote-on-drain surfaces
    # it later. Source-agnostic choke against any generator re-flooding the open board.
    board = active_board_count()  # counts the just-created open task
    if board > ACTIVE_BOARD_CAP:
        park(tid, actor="board_cap",
             reason=(f"active board at cap ({board-1}≥{ACTIVE_BOARD_CAP}) when created by "
                     f"{actor} — auto-parked to reserve; promote-on-drain will surface it"))
        return {"ok": True, "task_id": tid, "state": "reserved", "parked": True,
                "active_board": board - 1, "cap": ACTIVE_BOARD_CAP, "dedup_key": key}
    return {"ok": True, "task_id": tid, "state": "open", "parked": False,
            "active_board": board, "cap": ACTIVE_BOARD_CAP, "dedup_key": key}


def enforce_board_cap(actor: str = "board_cap_enforcer", cap: int = None,
                      dry_run: bool = False) -> dict:
    """PIN THE ACTIVE BOARD TO THE CAP — the missing inverse of refill_board().
    create() parks its OWN overflow, but tasks also re-enter the active board via
    recycled / reopened / unblocked / promoted events that never checked the cap
    (this is why the live board reached 39 > 20). This trims the overflow the same
    non-destructive way create() does: it PARKS the excess to reserve (reversible,
    separately counted, promote-on-drain restores). It ONLY parks UNOWNED `open`
    tasks (lowest priority, newest first) — never an owned/in-flight task mid-work,
    which is already bounded by the per-CEO (3) and global-WIP (12) caps."""
    cap = ACTIVE_BOARD_CAP if cap is None else cap
    snap = _rebuild_snapshot()
    board = active_board_tasks(snap=snap)
    if len(board) <= cap:
        return {"parked": 0, "board": len(board), "cap": cap, "dry_run": dry_run}
    parkable = [t for t in board
                if (t.get("state") or "").lower() == "open"
                and not (t.get("owner") or t.get("assignee"))]
    # Park worst-first: lowest priority (highest rank), then newest created.
    parkable.sort(key=lambda t: (_PRIO_RANK.get((t.get("priority") or "normal").lower(), 1),
                                 t.get("created_at", "")), reverse=True)
    need = len(board) - cap
    parked = []
    for t in parkable[:need]:
        if not dry_run:
            park(t["id"], actor=actor,
                 reason=(f"active board over cap ({len(board)}>{cap}) — trimmed unowned "
                         f"open overflow to reserve (re-entry via recycle/reopen/unblock "
                         f"bypassed the create-time cap)"))
        parked.append(t["id"])
    return {"parked": len(parked), "task_ids": parked,
            "board_before": len(board), "board_after": len(board) - (0 if dry_run else len(parked)),
            "cap": cap, "dry_run": dry_run,
            "note": ("only unowned open tasks parked; owned in-flight left alone. "
                     "reversible via refill_board/promote.")}


# 2026-07-27 Ross: "there should not be one [hq_claude], he resigned." Claude HQ
# is RETIRED (caged specialist under Wren, NON_CEO). Current leadership roster =
# Wren, TP(tp_pip), Asa(acer_cass), Bill. hq_claude removed from all CEO sets and
# BLOCKED from casting signoffs (see peer_signoff).
SIGNOFF_CEOS = {"wren", "tp_pip", "acer_cass", "bill"}   # who may verify/sign off
RETIRED_ACTORS = {"hq_claude", "claude", "claude_specialist"}  # NEVER a CEO
_WORKER_CEOS = {"tp_pip", "acer_cass"}                   # who does backlog tasks
_AGREE_WINDOW_SEC = 30 * 60


def submission_agree(actor: str, target_actor: str, note: str = "") -> dict:
    """Ross 2026-07-07: before a CEO can propose(), TWO OTHER worker CEOs must
    agree in advance. Each other-CEO calls this once to give their agree ticket
    naming the target proposer. Tickets expire after _AGREE_WINDOW_SEC."""
    _append_event({"ts": utc(), "event": "submission_agree_ticket",
                   "actor": actor, "target": target_actor, "note": note[:400]})
    return {"ok": True}


def _count_recent_agrees_for(target_actor: str) -> tuple:
    """Return (unique_agreers, latest_ts). Only OTHER worker CEOs within window."""
    import time as _t
    now = _t.time()
    unique = set()
    latest = ""
    try:
        with open(LOG) as f:
            for line in f:
                try: o = json.loads(line)
                except Exception: continue
                if o.get("event") != "submission_agree_ticket": continue
                if o.get("target") != target_actor: continue
                by = o.get("actor")
                if by == target_actor: continue
                if by not in _WORKER_CEOS: continue
                ts = o.get("ts", "")
                try:
                    import datetime as _dt
                    ev_t = _dt.datetime.fromisoformat(ts.replace("Z","+00:00")).timestamp()
                    if now - ev_t > _AGREE_WINDOW_SEC: continue
                except Exception: pass
                unique.add(by)
                if ts > latest: latest = ts
    except FileNotFoundError:
        pass
    return unique, latest


def propose(title: str, description: str = "", actor: str = "wren",
            priority: str = "normal", tags: list = None,
            bypass_pre_agree: bool = False) -> dict:
    """Ross #217: any CEO submits a proposal. Enters pending_admission.
    Needs ≥2 approvals from OTHER CEOs before promoted to open.

    Ross 2026-07-07 PRE-SUBMISSION GATE: worker-CEO proposer (hq_claude,
    tp_pip, acer_cass) must have ≥2 unique OTHER worker-CEO submission_agree
    tickets within the last 30 minutes before propose() succeeds.
    bypass_pre_agree=True allowed only when Ross gives explicit permission
    or when actor is 'ross_knechtel' or 'wren'."""
    if actor in _WORKER_CEOS and not bypass_pre_agree:
        agreers, latest = _count_recent_agrees_for(actor)
        if len(agreers) < 2:
            return {"ok": False,
                    "error": "pre_submission_agree_gate",
                    "detail": f"{actor} has {len(agreers)}/2 required OTHER-CEO submission_agree tickets in last {_AGREE_WINDOW_SEC//60}min. Have: {sorted(agreers) or '[]'}. Need agrees from the OTHER TWO worker CEOs before propose().",
                    "rule": "Ross 2026-07-07 · two_ceos_agree_before_submission",
                    "agreers": sorted(agreers)}
    tid = "t_" + uuid.uuid4().hex[:10]
    _append_event({"ts": utc(), "event": "proposed", "task_id": tid, "actor": actor,
                   "title": title, "description": description,
                   "priority": priority, "tags": tags or [],
                   "bypass_pre_agree": bool(bypass_pre_agree)})
    return {"ok": True, "task_id": tid, "state": "pending_admission"}


def admission_vote(task_id: str, actor: str, verdict: str, reason: str = "") -> dict:
    """Ross #217: any CEO (other than proposer) votes approve/reject on a proposal.
    After ≥2 approvals → promoted to 'open'. After ≥2 rejects → 'denied'."""
    _append_event({"ts": utc(), "event": "admission_voted", "task_id": task_id,
                   "actor": actor, "verdict": verdict, "reason": reason})
    return {"ok": True}


# ─── GATE 17 · Max 3 active tasks per CEO (Ross 2026-07-10) ──────────
# "No CEO may hold more than 3 active tasks at one time." Before claim(),
# go_in_progress (update state=in_progress), or assignment, count the actor's
# active/held tasks; if >=3 refuse with state=blocked_task_cap, log a
# task_cap_blocked event, and show the 3 blocking tasks. Helpers get no slots
# and cannot be used to dodge the cap. Ross may override, but only if the
# override is logged.
#
# 2026-07-30 WIP-CAP (Claude, "finish before starting"): the council was
# sprawling across hundreds of open/claimed tasks and finishing ~6% (F04 saw
# ~1.4%). The per-CEO cap below was aspirational for the AUTORUNNER path (it
# journals `claimed` directly and never called cap_check — wren was measured at
# 9 active vs cap 3). Two knobs make the cap real and add a whole-council ceiling:
#   · ACTIVE_CAP        — per-CEO in-flight cap (env COUNCIL_PER_CEO_CAP, default 3)
#   · GLOBAL_WIP_CAP    — total concurrent in-flight across ALL owners/engines
#                         (env COUNCIL_GLOBAL_WIP_CAP, default 12) so the council
#                         cannot sprawl even if every per-CEO cap individually passes.
# Both are env-configurable (like COUNCIL_MAX_CORRECTIONS). A logged Ross
# task_cap_override (target actor, or "*" for the global cap) still bypasses.
ACTIVE_CAP = int(os.environ.get("COUNCIL_PER_CEO_CAP", "3"))
GLOBAL_WIP_CAP = int(os.environ.get("COUNCIL_GLOBAL_WIP_CAP", "12"))
# A claimed/in_progress task whose last event is older than this is a STALE claim
# holding a WIP slot forever (F04 found ~40h-old ones). reap_stale_claims() recycles
# them back to the OPEN pool (owner cleared) via the existing `recycled` event so the
# slot frees for real work. Never fake-completes — a reaped task is re-openable work.
STALE_CLAIM_HOURS = float(os.environ.get("COUNCIL_STALE_CLAIM_HOURS", "2"))
STALE_REAP_BACKOFF_MIN = int(os.environ.get("COUNCIL_STALE_REAP_BACKOFF_MIN", "10"))

# CEO identities the cap applies to. Ross himself is NOT capped (safety gate).
# Future CEOs: add their actor id here.
CAPPED_CEOS = {"tp_pip", "acer_cass", "wren", "bill", "codex"}

# Helpers / Council-of-15 tools / gene-pool providers get NO task slots and may
# not be used to park a task to bypass the cap.
HELPER_ACTORS = {
    "hermes", "hermes_fast", "hermes_smart", "iquest", "iquest_coder",
    "qwen", "deepseek", "deepseek_coder", "deepseek-coder", "openai",
    "gene_pool", "brain_router",
}

# A task in any of these states is "active / held" by its owner|assignee and
# counts toward the cap. Union of Ross's 2026-07-10 list + the engine's own
# in-flight state names.
CAP_ACTIVE_STATES = {
    # 2026-07-19 FIX S4: "blocked" REMOVED — a blocked task waits on external conditions and
    # must NOT hold the owner's cap slot (blocked tasks were clogging the 3/CEO cap and starving
    # all new work). "awaiting_verification" ADDED so in-flight verification counts.
    "claimed", "in_progress", "assigned", "acknowledged",
    "awaiting_peer_signoff", "awaiting_verification", "ready_to_ship",
    "needs_partner", "needs_proof", "needs_second_verifier", "needs_rework",
    "needs_verification", "needs_ross_chatgpt_verifier_review",
}

# States that do NOT count (finished / dead / not-yet-claimed).
CAP_INACTIVE_STATES = {
    "open", "pending_admission", "denied", "done", "closed", "cancelled",
    "rejected", "archived", "superseded", "duplicate",
    "abandoned_by_ross_order",
}


def _held_by(task: dict, actor: str) -> bool:
    return task.get("owner") == actor or task.get("assignee") == actor


def active_tasks_for(actor: str, exclude_id: str = None) -> list:
    """Active/held tasks for a CEO, per GATE 17 (excludes exclude_id so a
    re-claim / progress of an already-held task is not double-counted)."""
    snap = _rebuild_snapshot()
    out = []
    for t in snap.get("tasks", []):
        if exclude_id and t.get("id") == exclude_id:
            continue
        if not _held_by(t, actor):
            continue
        if (t.get("state") or "").lower() in CAP_ACTIVE_STATES:
            out.append(t)
    return out


def global_active_tasks(exclude_id: str = None, snap: dict = None) -> list:
    """Every task in a CAP_ACTIVE state, including unowned signoff work.

    Unowned awaiting-signoff tasks still consume verifier and board capacity. The
    old owner-only filter let such tasks sit outside the global ceiling.
    """
    snap = snap or _rebuild_snapshot()
    out = []
    for t in snap.get("tasks", []):
        if exclude_id and t.get("id") == exclude_id:
            continue
        if (t.get("state") or "").lower() in CAP_ACTIVE_STATES:
            out.append(t)
    return out


def global_active_count(exclude_id: str = None, snap: dict = None) -> int:
    return len(global_active_tasks(exclude_id=exclude_id, snap=snap))


def _has_cap_override(actor: str, window_sec: int = 60 * 60) -> bool:
    """True if Ross logged a task_cap_override for this actor (or '*') within
    the window. GATE 17 bypass is allowed ONLY when logged."""
    import time as _t, datetime as _dt
    now = _t.time()
    try:
        with open(LOG) as f:
            for line in f:
                try:
                    o = json.loads(line)
                except Exception:
                    continue
                if o.get("event") != "task_cap_override":
                    continue
                if o.get("target") not in (actor, "*"):
                    continue
                ts = o.get("ts", "")
                try:
                    ev_t = _dt.datetime.fromisoformat(ts.replace("Z", "+00:00")).timestamp()
                    if now - ev_t > window_sec:
                        continue
                except Exception:
                    pass
                return True
    except FileNotFoundError:
        pass
    return False


def ross_cap_override(target_actor: str, reason: str = "") -> dict:
    """Ross-only: log an override letting target_actor exceed the cap for the
    next hour. Without this logged event the cap cannot be bypassed."""
    _append_event({"ts": utc(), "event": "task_cap_override",
                   "actor": "ross_knechtel", "target": target_actor,
                   "text": reason[:400]})
    return {"ok": True}


def cap_check(actor: str, this_task_id: str = None) -> dict:
    """GATE 17. {"ok": True} if actor may take another task, else a refusal
    dict (and a task_cap_blocked event is logged). Helpers are refused a slot
    outright; Ross is never capped."""
    a = (actor or "").lower()
    if a in ("ross", "ross_knechtel"):
        return {"ok": True}
    if a in HELPER_ACTORS:
        _append_event({"ts": utc(), "event": "task_cap_blocked",
                       "actor": actor, "task_id": this_task_id,
                       "reason": "helpers_have_no_task_slots"})
        return {"ok": False, "state": "blocked_task_cap",
                "error": "helpers_have_no_task_slots",
                "detail": (f"{actor} is a helper/tool/provider, not a CEO. "
                           "Helpers get no task slots and cannot be used to "
                           "bypass the cap."),
                "rule": "Ross 2026-07-10 · GATE 17"}
    held = active_tasks_for(actor, exclude_id=this_task_id)
    if len(held) >= ACTIVE_CAP and not _has_cap_override(actor):
        blocking = [{"id": t["id"], "title": t.get("title", "")[:80],
                     "state": t.get("state")} for t in held]
        _append_event({"ts": utc(), "event": "task_cap_blocked",
                       "actor": actor, "task_id": this_task_id,
                       "reason": "blocked_task_cap",
                       "active_count": len(held),
                       "blocking_task_ids": [t["id"] for t in held]})
        return {"ok": False, "state": "blocked_task_cap",
                "error": "blocked_task_cap",
                "detail": (f"CEO {actor} already has {len(held)} active tasks "
                           f"(cap {ACTIVE_CAP}). Finish, hand off, close "
                           "properly, or request Ross cleanup before claiming "
                           "more."),
                "active_count": len(held),
                "allowed_count": ACTIVE_CAP,
                "blocking_tasks": blocking,
                "rule": "Ross 2026-07-10 · GATE 17 · max_three_active_tasks_per_ceo"}
    # 2026-07-30 WIP-CAP · GLOBAL ceiling. Even if this CEO is under their per-CEO
    # cap, refuse if the WHOLE council is already at GLOBAL_WIP_CAP concurrent
    # in-flight tasks — finish before starting more. Ross "*" override bypasses.
    gcount = global_active_count(exclude_id=this_task_id)
    if gcount >= GLOBAL_WIP_CAP and not _has_cap_override(actor) and not _has_cap_override("*"):
        _append_event({"ts": utc(), "event": "task_cap_blocked",
                       "actor": actor, "task_id": this_task_id,
                       "reason": "blocked_global_wip",
                       "global_active_count": gcount,
                       "global_cap": GLOBAL_WIP_CAP})
        return {"ok": False, "state": "blocked_global_wip",
                "error": "blocked_global_wip",
                "detail": (f"Council already has {gcount} tasks in flight "
                           f"(global WIP cap {GLOBAL_WIP_CAP}). Finish/verify open "
                           "work before claiming more — this throttles NEW claims, "
                           "it does not stop work in progress."),
                "global_active_count": gcount,
                "global_cap": GLOBAL_WIP_CAP,
                "rule": "Ross 2026-07-30 · WIP-CAP · global_concurrent_wip_ceiling"}
    return {"ok": True}


# ─── WIP-CAP · stale-claim reaper (Claude 2026-07-30) ────────────────
# A task stuck in claimed/in_progress with no state change for > STALE_CLAIM_HOURS
# is holding a WIP slot forever (F04 found ~40h-old ones). This recycles it back to
# the OPEN pool via the EXISTING `recycled` event (owner cleared, state=open, a small
# retry_after backoff so it doesn't instantly re-thrash). It NEVER marks a task done
# and NEVER invents a terminal state — a reaped task is real work returned to the pool.
_REAP_STATES = {"claimed", "in_progress"}


def _last_event_ts(task: dict) -> str:
    h = task.get("history") or []
    if h:
        return h[-1].get("ts") or task.get("started_at") or task.get("created_at")
    return task.get("started_at") or task.get("created_at")


def _age_hours(ts: str):
    try:
        t = datetime.fromisoformat((ts or "").replace("Z", "+00:00"))
        return (datetime.now(timezone.utc) - t).total_seconds() / 3600.0
    except Exception:
        return None


def find_stale_claims(hours: float = None, snap: dict = None) -> list:
    """List tasks in claimed/in_progress whose last event is older than `hours`
    (default STALE_CLAIM_HOURS). Read-only — nothing is written."""
    hours = STALE_CLAIM_HOURS if hours is None else hours
    snap = snap or _rebuild_snapshot()
    out = []
    for t in snap.get("tasks", []):
        if (t.get("state") or "").lower() not in _REAP_STATES:
            continue
        if not t.get("owner"):
            continue
        age = _age_hours(_last_event_ts(t))
        if age is not None and age > hours:
            out.append({"id": t["id"], "owner": t.get("owner"),
                        "state": t.get("state"), "age_hours": round(age, 1),
                        "title": (t.get("title") or "")[:70]})
    return out


def reap_stale_claims(hours: float = None, dry_run: bool = False,
                      actor: str = "stale_reaper") -> dict:
    """Recycle stale claimed/in_progress tasks back to the OPEN pool so they stop
    holding a WIP slot. Uses the existing `recycled` event (no new terminal state,
    no fake completion). Returns {reaped, dry_run, hours, tasks[]}."""
    hours = STALE_CLAIM_HOURS if hours is None else hours
    stale = find_stale_claims(hours=hours)
    if not dry_run:
        retry_after = (datetime.now(timezone.utc)
                       + timedelta(minutes=STALE_REAP_BACKOFF_MIN)
                       ).strftime("%Y-%m-%dT%H:%M:%SZ")
        for s in stale:
            _append_event({"ts": utc(), "event": "recycled", "task_id": s["id"],
                           "actor": actor, "retry_after": retry_after,
                           "text": (f"stale-reaped: no state change for {s['age_hours']}h "
                                    f"(> {hours}h WIP-cap threshold) — back to pool, "
                                    f"owner {s['owner']} slot freed")})
    return {"reaped": len(stale), "dry_run": dry_run, "hours": hours, "tasks": stale}


# ─── GATE 18 · Task-driven work only (Ross 2026-07-10) ──────────────
# "If a CEO/worker/helper is not directly responding to Ross in chat, they must
# be task-driven." Before any non-chat work (code edit, dashboard edit, service
# change, file write, install, hardware action, repair), require a valid
# task_id in a work-allowing state with an owner and a partner (unless a logged
# Ross emergency override). Helpers need a parent task_id. Read-only work is
# allowed only under an audit/smoke_test task. Refusal state = blocked_no_task.
GATE18_WORK_STATES = {
    "claimed", "in_progress", "assigned", "acknowledged",
    "needs_partner", "needs_proof", "needs_second_verifier",
    "awaiting_peer_signoff",
}
GATE18_READONLY_CLASSES = {"audit", "smoke_test", "read_only", "report"}


def _get_task(task_id: str):
    for t in _rebuild_snapshot().get("tasks", []):
        if t.get("id") == task_id:
            return t
    return None


def _task_partner(task: dict):
    """A second distinct CEO attached to the task = the partner."""
    owner = task.get("owner")
    for cand in (task.get("assignee"), task.get("partner"),
                 task.get("peer_signoff_by"), task.get("acknowledged_by")):
        if cand and cand != owner:
            return cand
    return None


def _has_work_override(actor: str, window_sec: int = 60 * 60) -> bool:
    """True if Ross logged a gate18_work_override (emergency) for actor/'*'."""
    import time as _t, datetime as _dt
    now = _t.time()
    try:
        with open(LOG) as f:
            for line in f:
                try:
                    o = json.loads(line)
                except Exception:
                    continue
                if o.get("event") != "gate18_work_override":
                    continue
                if o.get("target") not in (actor, "*"):
                    continue
                ts = o.get("ts", "")
                try:
                    ev_t = _dt.datetime.fromisoformat(ts.replace("Z", "+00:00")).timestamp()
                    if now - ev_t > window_sec:
                        continue
                except Exception:
                    pass
                return True
    except FileNotFoundError:
        pass
    return False


def ross_work_override(target_actor: str, reason: str = "") -> dict:
    """Ross-only: log an emergency override letting target_actor work without
    the full task envelope for the next hour (GATE 18 bypass — must be logged)."""
    _append_event({"ts": utc(), "event": "gate18_work_override",
                   "actor": "ross_knechtel", "target": target_actor,
                   "text": reason[:400]})
    return {"ok": True}


def work_authorization(actor: str, task_id: str = None, task_class: str = None,
                       readonly: bool = False, is_helper: bool = False,
                       parent_task_id: str = None,
                       require_partner: bool = True) -> dict:
    """GATE 18. {"ok": True} if this work action is properly task-driven, else
    a refusal dict (state=blocked_no_task). Ross-direct chat is a separate
    allowed mode handled by the caller; this enforces the task envelope for
    NON-chat work."""
    a = (actor or "").lower()
    # Emergency: logged Ross override lets the actor proceed.
    if _has_work_override(actor) or a in ("ross", "ross_knechtel"):
        return {"ok": True, "mode": "ross_override_or_direct"}

    # Helpers do not start independent work — they must ride a parent task.
    if is_helper:
        if not parent_task_id:
            return {"ok": False, "state": "blocked_no_task",
                    "error": "helper_no_parent_task",
                    "detail": (f"{actor} is a helper/toolbox resource and may "
                               "only work under a CEO/task parent_task_id."),
                    "rule": "Ross 2026-07-10 · GATE 18"}
        task_id = parent_task_id

    if not task_id:
        return {"ok": False, "state": "blocked_no_task",
                "error": "no_task_id",
                "detail": ("No task_id. If not working directly with Ross, work "
                           "must be attached to a Task Council task. Intake one "
                           "first."),
                "rule": "Ross 2026-07-10 · GATE 18 · task_driven_work_only"}

    task = _get_task(task_id)
    if not task:
        return {"ok": False, "state": "blocked_no_task",
                "error": "unknown_task",
                "detail": f"task_id {task_id} not found in the council.",
                "rule": "Ross 2026-07-10 · GATE 18"}

    # Read-only work is allowed only under an audit / smoke_test class.
    if readonly:
        if (task_class or "").lower() in GATE18_READONLY_CLASSES:
            return {"ok": True, "mode": "readonly_audit", "task_id": task_id}
        return {"ok": False, "state": "blocked_no_task",
                "error": "readonly_requires_audit_class",
                "detail": ("read-only work is allowed only when the task_class "
                           "is audit or smoke_test."),
                "rule": "Ross 2026-07-10 · GATE 18"}

    state = (task.get("state") or "").lower()
    if state not in GATE18_WORK_STATES:
        return {"ok": False, "state": "blocked_no_task",
                "error": "state_disallows_work",
                "detail": (f"task {task_id} is in state '{state}', which does "
                           "not allow active work. Claim/intake it first."),
                "rule": "Ross 2026-07-10 · GATE 18"}

    if not (task.get("owner") or task.get("assignee")):
        return {"ok": False, "state": "blocked_no_task",
                "error": "no_owner",
                "detail": f"task {task_id} has no owner; claim it before working.",
                "rule": "Ross 2026-07-10 · GATE 18"}

    if require_partner and not _task_partner(task):
        return {"ok": False, "state": "blocked_no_task",
                "error": "no_partner",
                "detail": (f"task {task_id} has no partner CEO. Assign a partner "
                           "or get a logged Ross emergency override."),
                "rule": "Ross 2026-07-10 · GATE 18"}

    return {"ok": True, "mode": "task_driven", "task_id": task_id,
            "owner": task.get("owner"), "partner": _task_partner(task)}


# ─── GATE 19 · Team liveness watch + recovery (Ross 2026-07-10 · R108) ───
# Every CEO/runtime/service must be watched. If a node goes stale/unreachable/
# offline it must NOT be ignored or treated as agreement — the others create a
# recovery task. Before any two-CEO or verification work, the required nodes'
# heartbeats are checked; any not-ONLINE node => blocked_node_offline.
LIVENESS_STATES = {"ONLINE", "STALE", "UNREACHABLE", "OFFLINE", "IDENTITY_MISMATCH",
                   "HQ_HOSTED_ONLY", "PHYSICAL_INDEPENDENCE_UNPROVEN",
                   "RECOVERY_IN_PROGRESS", "RECOVERED"}
HEARTBEAT_STALE_SEC = 10 * 60  # 10 minutes for active work


def classify_liveness(probe: dict) -> str:
    """Classify a node from a probe dict. Keys: host_down, reachable,
    identity, expected_id, last_heartbeat_ts (epoch secs). Offline/stale is
    NEVER 'ONLINE' — silence is not agreement."""
    if probe.get("host_down"):
        return "OFFLINE"
    if not probe.get("reachable"):
        return "UNREACHABLE"
    exp, got = probe.get("expected_id"), probe.get("identity")
    if exp and got and exp != got:
        return "IDENTITY_MISMATCH"
    hb = probe.get("last_heartbeat_ts")
    if hb is not None:
        import time as _t
        if (_t.time() - hb) > HEARTBEAT_STALE_SEC:
            return "STALE"
    return "ONLINE"


def liveness_gate(node_states: dict) -> dict:
    """GATE 19. node_states = {name: liveness_state}. If EVERY required node is
    ONLINE -> ok. Otherwise blocked_node_offline naming the bad nodes (so an
    offline partner/verifier can never be silently treated as approval)."""
    bad = {n: s for n, s in (node_states or {}).items() if s != "ONLINE"}
    if bad:
        return {"ok": False, "state": "blocked_node_offline", "offline_nodes": bad,
                "detail": ("required node(s) not ONLINE — cannot proceed with a "
                           "two-CEO/verification task. A recovery task is required; "
                           "silence is NOT agreement."),
                "rule": "Ross 2026-07-10 · GATE 19 · R108_team_liveness_watch"}
    return {"ok": True}


def create_recovery_task(node_name: str, last_url: str = "", last_heartbeat: str = "",
                         detector: str = "wren", evidence: str = "",
                         state: str = "UNREACHABLE") -> dict:
    """Create the Task Council recovery task for an offline/stale node."""
    desc = (f"node/service: {node_name}\nlast_url: {last_url}\n"
            f"last_heartbeat: {last_heartbeat}\ndetected_by: {detector}\n"
            f"liveness: {state}\nevidence: {evidence[:600]}\n"
            "safe recovery steps: read-only check first (port/process/logs/"
            "systemd/network/disk/token/host); restart ONLY if known safe. "
            "NOT allowed without Ross: wipe/reflash/delete/rotate-secrets/change-"
            "identity/overwrite-memory/bypass-council/force-close.\n"
            "Wren observability role: verify the outage facts only (cannot replace "
            "the missing CEO).")
    return create(title=f"Recover offline node/service: {node_name}",
                  description=desc, actor=detector,
                  tags=["recovery", "team_liveness", "R108", f"node:{node_name}"])


# ─── PHASE-3 · physical-CEO liveness + surrogate gate (Claude 2026-08-03) ─────
# claim()/assign() previously did NO liveness or identity check: an OFFLINE
# principal or a surrogate/retired identity could still take a task (silence !=
# agreement). This gate delegates to the Task-Council-side real-liveness module
# (tools/qsb_council_liveness.py) which probes each principal's GENUINE host +
# local runtime (Asa on :9000, fixing the federation :9120 false-negative) and
# refuses + logs an offline principal or a CEO-impersonating identity. Specialists
# (codex/hermes/iquest) and benign non-CEO actors still claim non-leadership work.
# Reversible: env COUNCIL_LIVENESS_GATE=0 disables it; an import failure fails OPEN
# (logged) so a bug here can never wedge the task engine.
LIVENESS_GATE_ENABLED = os.environ.get("COUNCIL_LIVENESS_GATE", "1") not in ("0", "false", "False", "no")


def _liveness_verdict(actor: str, task_id: str = None, kind: str = "claim"):
    """Return None to allow (gate off / import failed), else a verdict dict.
    On refusal, appends a {kind}_rejected audit event so every rejection lands
    in the append-only DB."""
    if not LIVENESS_GATE_ENABLED:
        return None
    try:
        import sys as _sys
        _sys.path.insert(0, str(ROOT / "tools"))
        import qsb_council_liveness as _LV
    except Exception as e:
        _append_event({"ts": utc(), "event": "liveness_gate_skipped",
                       "task_id": task_id, "actor": actor,
                       "reason": f"import_error: {str(e)[:160]}"})
        return None
    v = _LV.claim_verdict(actor)
    if not v.get("ok"):
        _append_event({"ts": utc(), "event": f"{kind}_rejected", "task_id": task_id,
                       "actor": actor, "reason": v.get("error"),
                       "klass": v.get("klass"), "liveness": v.get("liveness"),
                       "detail": (v.get("detail") or "")[:300],
                       "rule": v.get("rule")})
    return v


def claim(task_id: str, actor: str) -> dict:
    # PHASE-3: offline principal / surrogate identity refused + logged (before GATE 17).
    lv = _liveness_verdict(actor, task_id, kind="claim")
    if lv is not None and not lv.get("ok"):
        return lv
    gate = cap_check(actor, this_task_id=task_id)  # GATE 17
    if not gate.get("ok"):
        return gate
    _append_event({"ts": utc(), "event": "claimed", "task_id": task_id, "actor": actor})
    return {"ok": True}


def update(task_id: str, actor: str, **fields) -> dict:
    # GATE 17: go_in_progress is a cap-gated transition. cap_check excludes
    # this_task_id, so progressing an already-held task never wrongly blocks;
    # it only blocks when this would be a NEW 4th active task for the owner.
    if fields.get("state") == "in_progress":
        owner = fields.get("owner") or actor
        gate = cap_check(owner, this_task_id=task_id)
        if not gate.get("ok"):
            return gate
    ev = {"ts": utc(), "event": "updated", "task_id": task_id, "actor": actor}
    ev.update({k: v for k, v in fields.items() if k in
               ("title", "description", "priority", "state", "owner",
                "target_file", "context_files", "ceo_rationale")})
    _append_event(ev)
    return {"ok": True}


def note(task_id: str, actor: str, text: str) -> dict:
    _append_event({"ts": utc(), "event": "noted", "task_id": task_id, "actor": actor,
                   "text": text})
    return {"ok": True}


def block(task_id: str, actor: str, reason: str,
          blocking_dependency: str = "", responsible_component: str = "",
          required_resolution: str = "", retry_count: int = None,
          next_attempt_after: str = "") -> dict:
    """Record a BLOCKED task with the STRUCTURED accountability fields Phase-6 requires so a
    blocked task is never a silent dead-end: what it is blocked ON (blocking_dependency), WHO
    owns unblocking it (responsible_component), the LAST attempt (auto: the task's last-activity
    ts), the NEXT permitted attempt (next_attempt_after), the RETRY COUNT (auto: rework_rounds
    when not supplied), and the REQUIRED RESOLUTION. Backward compatible — the legacy 3-arg
    block(task_id, actor, reason) still works; the structured fields then default to best-effort
    values derived from the live task, so even old callers record accountability."""
    t = _get_task(task_id) or {}
    ev = {"ts": utc(), "event": "blocked", "task_id": task_id, "actor": actor,
          "text": reason,
          "blocking_dependency": blocking_dependency or "",
          "responsible_component": responsible_component or (t.get("owner") or "unassigned"),
          "last_attempt": (_last_event_ts(t) if t else utc()),
          "retry_count": (retry_count if retry_count is not None
                          else int(t.get("rework_rounds", 0) or 0)),
          "next_attempt_after": next_attempt_after or "",
          "required_resolution": required_resolution or ""}
    _append_event(ev)
    return {"ok": True, "blocked": True,
            **{k: ev[k] for k in ("blocking_dependency", "responsible_component",
                                  "last_attempt", "retry_count", "next_attempt_after",
                                  "required_resolution")}}


def unblock(task_id: str, actor: str) -> dict:
    _append_event({"ts": utc(), "event": "unblocked", "task_id": task_id, "actor": actor})
    return {"ok": True}


# ─── PHASE-5 · COMPLETION PROOF GATE on done() (Claude 2026-08-03) ────────────
# Baseline defect (proven): of 33 'done' tasks only 3 carried any proof/verifier —
# `done` was a RECORD, not verified completion. The done() verb (called by the
# boardroom-hub /done endpoint and the CLI) appended a `done` event unconditionally:
# no independent verifier, no proof reference. A worker/dashboard could self-close a
# task with an empty summary and it became state=done. (The autorunner path is
# separately gated — it only journals `done` after apply-bridge quorum + two
# independent no-self-verify peer_signoffs + a real proof_path/sha; this closes the
# UNGATED verb backdoor to match.)
#
# GATE: done() now REFUSES to mark a task done unless it carries reproducible
# completion evidence — BOTH of:
#   (1) an INDEPENDENT VERIFIER (an approving peer_signoff, or an explicit `verifier`
#       arg) that is NOT the builder/owner and NOT the done-caller; builder
#       self-verify alone is REJECTED, AND
#   (2) a PROOF REFERENCE that is present and FRESH — a proof_path that exists on
#       disk (and whose sha256 matches proof_sha when one is supplied), OR an
#       applied code-apply audit row for this task, OR a sandbox_passed test-evidence
#       event in the task history.
# On refusal the task is NOT silently completed: a `done_rejected` audit event is
# appended (append-only, greppable) and the task is moved to awaiting_verification
# (held for correction), and done() returns ok=False with a refusal code.
#
# Reversible + safe: env kill-switch COUNCIL_PROOF_GATE (default ON). Any
# exception/lookup failure inside the gate FAILS OPEN (logs proof_gate_error and
# lets the completion through) so a bug here can never wedge the engine.
# History is untouched: the 33 legacy `done` events already in the log reduce
# exactly as before — the gate only governs NEW done() calls going forward.
PROOF_GATE_ENABLED = os.environ.get("COUNCIL_PROOF_GATE", "1") not in ("0", "false", "False", "no")


def _sha256_file(path: Path):
    import hashlib
    try:
        h = hashlib.sha256()
        with open(path, "rb") as fp:
            for chunk in iter(lambda: fp.read(65536), b""):
                h.update(chunk)
        return h.hexdigest()
    except Exception:
        return None


def _approving_verifiers(task: dict) -> set:
    """CEO ids that cast an approving peer_signoff on this task. Reads the
    append-only LOG (which preserves the `verdict` field — the reduced `history`
    entries strip it), so a SELF-signoff by the builder is still detected as a
    verifier (and then rejected as non-independent), not misread as no verifier."""
    tid = (task or {}).get("id")
    out = set()
    if tid:
        try:
            with open(LOG) as fp:
                for line in fp:
                    if tid not in line:
                        continue
                    try:
                        o = json.loads(line)
                    except Exception:
                        continue
                    if (o.get("task_id") == tid and o.get("event") == "peer_signoff"
                            and o.get("verdict") == "approve"):
                        a = o.get("actor")
                        if a:
                            out.add(a)
        except FileNotFoundError:
            pass
    # honour the reduced field too (belt-and-braces)
    if task and task.get("peer_signoff_by") and task.get("peer_signoff_verdict") == "approve":
        out.add(task["peer_signoff_by"])
    return out


def _has_sandbox_test_evidence(task: dict) -> bool:
    """A sandbox_passed event carrying non-trivial evidence text = test evidence."""
    for h in (task or {}).get("history") or []:
        if h.get("event") == "sandbox_passed" and len((h.get("text") or "").strip()) >= 40:
            return True
    return False


def _code_apply_audit_row(task_id: str):
    """Latest applied=True code-apply audit row referencing this task_id, else None.
    This immutable row (sha_before/sha_after) is the real proof a live change shipped."""
    audit = REG / "qsb_code_apply_audit.jsonl"
    if not audit.exists():
        return None
    row = None
    try:
        with open(audit) as fp:
            for line in fp:
                line = line.strip()
                if not line or task_id not in line:
                    continue
                try:
                    o = json.loads(line)
                except Exception:
                    continue
                if o.get("task_id") == task_id and o.get("applied"):
                    row = o  # keep last (latest)
    except Exception:
        return None
    return row


def _completion_evidence(task_id: str, actor: str, proof_path: str,
                         proof_sha: str, verifier: str) -> tuple:
    """Return (ok, code, detail, meta). ok=True only when the task carries an
    INDEPENDENT verifier AND a FRESH proof reference. Deterministic, no model."""
    task = _get_task(task_id)
    owner = (task or {}).get("owner") or (task or {}).get("acknowledged_by")
    builders = {b for b in (owner, actor) if b}

    # (1) INDEPENDENT VERIFIER — approving peer_signoff or explicit verifier arg,
    # by someone who is NOT the builder/owner and NOT the done-caller.
    verifiers = _approving_verifiers(task)
    if verifier:
        verifiers = verifiers | {verifier}
    independent = {v for v in verifiers if v and v not in builders}
    if not verifiers:
        return (False, "done_refused_no_verifier",
                (f"task {task_id} has no approving independent verifier. A completion "
                 "needs a peer_signoff/approve (or explicit verifier) from a CEO other "
                 f"than the builder/owner {sorted(builders) or '[?]'}. Builder self-"
                 "verification alone is rejected."),
                {"verifiers": sorted(verifiers), "builders": sorted(builders)})
    if not independent:
        return (False, "done_refused_self_verify",
                (f"the only verifier(s) {sorted(verifiers)} are the builder/owner/"
                 f"done-caller {sorted(builders)}. Builder self-verification alone is "
                 "rejected — a DIFFERENT CEO must sign off."),
                {"verifiers": sorted(verifiers), "builders": sorted(builders)})

    # (2) PROOF REFERENCE — present + fresh. An explicitly-supplied proof_path MUST
    # be fresh (exists on disk; sha matches when proof_sha given) — a stale/missing
    # path blocks. If no proof_path, fall back to an applied audit row / test evidence.
    if proof_path:
        p = (ROOT / proof_path) if not os.path.isabs(proof_path) else Path(proof_path)
        if not p.exists():
            return (False, "done_refused_stale_proof",
                    (f"proof_path '{proof_path}' does not exist on disk — the proof is "
                     "missing/stale. Completion blocked."),
                    {"proof_path": proof_path, "independent_verifier": sorted(independent)})
        if proof_sha:
            actual = _sha256_file(p)
            if actual != proof_sha:
                return (False, "done_refused_stale_proof",
                        (f"proof_path '{proof_path}' sha256 {(actual or 'None')[:16]} does "
                         f"NOT match declared proof_sha {proof_sha[:16]} — the proof is "
                         "stale (the file changed since it was verified). Blocked."),
                        {"proof_path": proof_path, "actual_sha": actual,
                         "declared_sha": proof_sha, "independent_verifier": sorted(independent)})
        return (True, "ok", "fresh proof_path" + ("+sha" if proof_sha else ""),
                {"proof_kind": "proof_path", "proof_path": proof_path,
                 "independent_verifier": sorted(independent)})

    row = _code_apply_audit_row(task_id)
    if row is not None:
        return (True, "ok", "applied code-apply audit row",
                {"proof_kind": "code_apply_audit", "proposal_id": row.get("proposal_id"),
                 "target": row.get("target"), "independent_verifier": sorted(independent)})

    if _has_sandbox_test_evidence(task):
        return (True, "ok", "sandbox test evidence",
                {"proof_kind": "sandbox_test_evidence",
                 "independent_verifier": sorted(independent)})

    return (False, "done_refused_no_proof",
            (f"task {task_id} has an independent verifier {sorted(independent)} but NO "
             "proof reference (no proof_path, no applied code-apply audit row, no "
             "sandbox test evidence). A record of 'done' is not proof of completion."),
            {"independent_verifier": sorted(independent)})


def done(task_id: str, actor: str, summary: str = "",
         proof_path: str = "", proof_sha: str = "", verifier: str = "") -> dict:
    # PHASE-5 COMPLETION PROOF GATE: a task can only BECOME done when it carries an
    # independent verifier + a fresh proof reference. proof_path/proof_sha optional
    # (an applied audit row or sandbox test-evidence can supply the proof); the
    # autonomous loop supplies proof_path/sha directly. Fail-open on any error.
    if PROOF_GATE_ENABLED:
        try:
            ev_ok, code, detail, meta = _completion_evidence(
                task_id, actor, proof_path, proof_sha, verifier)
        except Exception as e:
            ev_ok = True
            _append_event({"ts": utc(), "event": "proof_gate_error", "task_id": task_id,
                           "actor": actor,
                           "reason": f"{type(e).__name__}:{str(e)[:180]}",
                           "note": "completion proof gate errored — FAILED OPEN (completion allowed)"})
        if not ev_ok:
            # NOT a silent completion: log the refusal + hold for verification.
            _append_event({"ts": utc(), "event": "done_rejected", "task_id": task_id,
                           "actor": actor, "reason": code, "detail": detail[:400],
                           "rule": "Phase-5 · completion_proof_gate", **meta})
            if _get_task(task_id) is not None:
                _append_event({"ts": utc(), "event": "awaiting_verification",
                               "task_id": task_id, "actor": "proof_gate",
                               "text": f"DONE REFUSED ({code}): {detail}"[:500]})
            return {"ok": False, "error": code, "detail": detail,
                    "state": "awaiting_verification",
                    "rule": "Phase-5 · completion_proof_gate", **meta}

    ev = {"ts": utc(), "event": "done", "task_id": task_id, "actor": actor, "text": summary}
    if proof_path:
        ev["proof_path"] = proof_path
    if proof_sha:
        ev["proof_sha"] = proof_sha
    if verifier:
        ev["verifier"] = verifier
    _append_event(ev)
    # PROMOTE-ON-DRAIN: a completion just freed a board slot — pull the highest-priority
    # reserved task back to open so the board self-refills toward the cap.
    try:
        refill_board(actor="promote_on_drain")
    except Exception:
        pass
    return {"ok": True}


# ─── REOPEN TRANSITION GUARD · Phase-1 truth model (Claude 2026-08-03) ─────────
# Baseline defect (proven): one task was reopened 197× — 2,283 `reopened` events
# across 84 tasks, 8 tasks past 100 reopens — because the watcher / sla_watcher
# re-`reopen()` any SLA-breached or unfinished task every scan, and reopen() was an
# UNCONDITIONAL append (no state check, no bound). A task could be resurrected from a
# terminal state and recycled endlessly. This guard makes reopen a CHECKED transition
# without adding any parallel state field and without touching history:
#   (a) TERMINAL task (done/dropped/cancelled/denied/superseded/closed/archived) may
#       be reopened ONLY with an explicit non-empty reason — no silent resurrection.
#   (b) BOUNDED CAP: after REOPEN_CAP prior reopens the reopen is REFUSED (logged, not
#       applied); the task stops in place for review instead of looping forever.
#   (c) NO-OP: reopening a task already state=open changes nothing → rejected + logged.
# Every refusal appends a timestamped `reopen_rejected` audit event (history preserved,
# log stays append-only). A legal reopen still writes the same `reopened` event as before
# (plus an optional reason), so downstream reduction is unchanged.
#
# N = 5 justification (evidence-driven, 2026-08-03 log of 52,953 events):
#   reopen-count distribution over the 84 ever-reopened tasks —
#     >=2:61  >=3:49  >=5:38  >=10:29  >=20:23  >=50:13  >=100:8  (max 197).
#   Healthy rework/SLA-release tails off by ~3-4; every task past 5 is a runaway
#   loop (the top 8 sit at 118-197). 5 sits just above the correction ceiling
#   (COUNCIL_MAX_CORRECTIONS=3) to allow genuine rework + a couple of SLA releases,
#   yet cleanly severs the pathological loop. Env-overridable for tuning.
REOPEN_CAP = int(os.environ.get("COUNCIL_REOPEN_CAP", "5"))
_TERMINAL_STATES_FOR_REOPEN = {
    "done", "dropped", "cancelled", "denied", "superseded", "closed", "archived",
}


def _count_reopens(task_id: str) -> int:
    """How many `reopened` events already exist for this task (append-only log)."""
    n = 0
    try:
        with open(LOG) as f:
            for line in f:
                try:
                    o = json.loads(line)
                except Exception:
                    continue
                if o.get("task_id") == task_id and o.get("event") == "reopened":
                    n += 1
    except FileNotFoundError:
        pass
    return n


def reopen(task_id: str, actor: str, reason: str = "") -> dict:
    """Reopen a task — now a GUARDED transition (was an unconditional append).
    Backward compatible: existing callers pass (task_id, actor) positionally; the
    new optional `reason` is required only to reopen a TERMINAL task."""
    task = _get_task(task_id)
    state = ((task or {}).get("state") or "").lower()
    prior = _count_reopens(task_id)
    reason_clean = (reason or "").strip()

    # (c) NO-OP — already open, nothing to reopen.
    if task is not None and state == "open":
        _append_event({"ts": utc(), "event": "reopen_rejected", "task_id": task_id,
                       "actor": actor, "reason": "noop_already_open",
                       "prior_state": state, "prior_reopens": prior})
        return {"ok": False, "error": "reopen_noop",
                "detail": f"task {task_id} is already open; reopen is a no-op.",
                "state": state, "reopen_count": prior}

    # (a) TERMINAL requires an explicit logged reason — no silent resurrection.
    if state in _TERMINAL_STATES_FOR_REOPEN and not reason_clean:
        _append_event({"ts": utc(), "event": "reopen_rejected", "task_id": task_id,
                       "actor": actor, "reason": "terminal_requires_explicit_reason",
                       "prior_state": state, "prior_reopens": prior})
        return {"ok": False, "error": "terminal_reopen_needs_reason",
                "detail": (f"task {task_id} is terminal (state='{state}'); reopening a "
                           "completed/dropped task requires an explicit reason so a "
                           "finished task is never silently resurrected."),
                "state": state, "reopen_count": prior,
                "rule": "Phase-1 truth model · terminal_reopen_needs_reason"}

    # (b) BOUNDED CAP — refuse (log, do not apply) once the reopen ceiling is hit.
    if prior >= REOPEN_CAP:
        _append_event({"ts": utc(), "event": "reopen_rejected", "task_id": task_id,
                       "actor": actor, "reason": "reopen_cap_exceeded",
                       "prior_state": state, "prior_reopens": prior, "cap": REOPEN_CAP})
        return {"ok": False, "error": "reopen_cap_exceeded",
                "detail": (f"task {task_id} has already been reopened {prior} times "
                           f"(cap {REOPEN_CAP}); refusing further reopen. It stays in "
                           f"state '{state}' for review instead of looping."),
                "state": state, "reopen_count": prior, "cap": REOPEN_CAP,
                "rule": "Phase-1 truth model · bounded_reopen_cap"}

    ev = {"ts": utc(), "event": "reopened", "task_id": task_id, "actor": actor}
    if reason_clean:
        ev["reason"] = reason_clean[:400]
    _append_event(ev)
    return {"ok": True, "reopen_count": prior + 1, "cap": REOPEN_CAP}


def add_subtask(task_id: str, actor: str, text: str) -> dict:
    _append_event({"ts": utc(), "event": "subtask_added", "task_id": task_id,
                   "actor": actor, "text": text})
    return {"ok": True}


def assign(task_id: str, actor: str, assignee: str) -> dict:
    """Ross (or any CEO) assigns a task to a specific member. Assignee
    must ack. Two roles: assigner + assignee."""
    # PHASE-3: the ASSIGNEE (who will hold/work it) must be an online physical CEO
    # or a legitimate non-CEO worker; an offline/surrogate assignee is refused + logged.
    lv = _liveness_verdict(assignee, task_id, kind="assign")
    if lv is not None and not lv.get("ok"):
        return {**lv, "assignee": assignee}
    gate = cap_check(assignee, this_task_id=task_id)  # GATE 17 — assignee holds it
    if not gate.get("ok"):
        return {**gate, "assignee": assignee}
    _append_event({"ts": utc(), "event": "assigned", "task_id": task_id,
                   "actor": actor, "assignee": assignee})
    return {"ok": True}


def ack(task_id: str, actor: str, note_text: str = "") -> dict:
    """Assignee acknowledges an assigned task (I got it, I'm on it)."""
    _append_event({"ts": utc(), "event": "acknowledged", "task_id": task_id,
                   "actor": actor, "text": note_text})
    return {"ok": True}


# 2026-07-27 Ross "#1 harden the sandbox" — the sandbox used to accept ANY non-empty
# text as a pass, so plan-only intention-text ("I will retrieve/extract…") and
# cross-task-contaminated output (a TOUR3D prompt bleeding into an OANDA task) sailed
# through to the peer-verify gate. This gate rejects the two clear failure modes so
# the worker must submit a REAL deliverable before the task advances.
_PLAN_MARKERS = ("i will ", "i plan to", "i'm going to", "i am going to", "i would ",
                 "my approach", "steps:", "first, i", "then i will", "i intend to",
                 "here's my plan", "here is my plan", "i'm currently booted", "i will retrieve",
                 "i will load", "i will extract", "i'm uncertain")


def _artifact_quality_gate(task_id: str, evidence: str) -> tuple[bool, str]:
    import re
    e = (evidence or "").strip()
    if len(e) < 60:
        return False, "artifact too short/empty — not a real deliverable"
    el = e.lower()
    plan_hits = [m for m in _PLAN_MARKERS if m in el]
    if len(plan_hits) >= 2:
        return False, (f"reads like a PLAN, not a deliverable ({len(plan_hits)} intention-phrases e.g. "
                       f"'{plan_hits[0].strip()}'). Do the work and submit the ACTUAL result, not what you intend to do.")
    # cross-task contamination: a '#TAG' / '[TAG]' or foreign task id referenced up front
    task = _get_task(task_id) or {}
    title = (task.get("title") or "")
    foreign_tags = set(re.findall(r'#([A-Za-z0-9_]{3,})', e)) | set(re.findall(r'\[([A-Z0-9_]{4,})\]', e))
    title_tokens = set(re.findall(r'[A-Za-z0-9]{4,}', title.upper()))
    off_topic = {t for t in foreign_tags if t.upper() not in title_tokens and not t.upper().startswith(tuple(title_tokens or {"~"}))}
    if off_topic and ("to address the #" in el or "task pulled" in el):
        return False, (f"cross-task CONTAMINATION — evidence references unrelated task tag(s) {sorted(off_topic)} "
                       f"not in this task's title. Submit output for THIS task only.")
    return True, "ok"


def sandbox_pass(task_id: str, actor: str, evidence: str) -> dict:
    """Worker self-verifies in own sandbox. Task moves to awaiting_peer_signoff.
    2026-07-27: gated — plan-only / contaminated artifacts are refused (stay in_progress)."""
    ok, reason = _artifact_quality_gate(task_id, evidence)
    if not ok:
        _append_event({"ts": utc(), "event": "sandbox_rejected", "task_id": task_id,
                       "actor": "sandbox_gate", "text": f"REFUSED sandbox-pass by {actor}: {reason}"})
        return {"ok": False, "error": "sandbox_quality_gate", "reason": reason}
    _append_event({"ts": utc(), "event": "sandbox_passed", "task_id": task_id,
                   "actor": actor, "text": evidence[:800]})
    return {"ok": True}


def peer_signoff(task_id: str, actor: str, verdict: str = "approve",
                 comment: str = "") -> dict:
    """A DIFFERENT CEO reviews the sandbox evidence + approves/rejects.
    Ross 2026-07-06 rule: the taker (proposer OR claimer) CANNOT sign off own task.
    Only current-roster CEOs {wren, tp_pip, acer_cass, bill} may signoff.
    2026-07-27 Ross: hq_claude RESIGNED — a retired identity can NEVER sign off."""
    if actor in RETIRED_ACTORS:
        return {"ok": False, "error": "retired_actor_cannot_signoff",
                "detail": f"'{actor}' is retired (Claude HQ resigned; Claude is a caged specialist, not a CEO). "
                          f"Signoff must come from a current CEO: {sorted(SIGNOFF_CEOS)}.",
                "rule": "project_leadership_comms_pipeline_2026-07-17 · Claude HQ retired"}
    if actor not in SIGNOFF_CEOS:
        return {"ok": False, "error": "not_a_current_ceo",
                "detail": f"'{actor}' is not on the current signoff roster {sorted(SIGNOFF_CEOS)}."}
    proposer, claimer = None, None
    try:
        with open(LOG) as f:
            for line in f:
                try: o = json.loads(line)
                except Exception: continue
                if o.get("task_id") != task_id: continue
                if o.get("event") == "proposed": proposer = o.get("actor")
                elif o.get("event") == "claimed": claimer = o.get("actor")
    except Exception:
        pass
    self_actor = claimer or proposer
    if self_actor and actor == self_actor:
        return {"ok": False,
                "error": "taker_cannot_signoff_own_task",
                "detail": f"task {task_id} was taken by {self_actor}; peer_signoff must come from one of the OTHER 3 CEOs.",
                "rule": "Ross 2026-07-06 · feedback_taker_cannot_signoff_2026-07-06"}
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
    p_create.add_argument("--actor", default="wren")
    p_create.add_argument("--priority", default="normal")
    p_create.add_argument("--tags", default="")
    p_claim = sub.add_parser("claim")
    p_claim.add_argument("--id", required=True); p_claim.add_argument("--actor", required=True)
    p_done = sub.add_parser("done")
    p_done.add_argument("--id", required=True); p_done.add_argument("--actor", required=True)
    p_done.add_argument("--summary", default="")
    p_done.add_argument("--proof-path", default="")
    p_done.add_argument("--proof-sha", default="")
    p_done.add_argument("--verifier", default="")
    p_note = sub.add_parser("note")
    p_note.add_argument("--id", required=True); p_note.add_argument("--actor", required=True)
    p_note.add_argument("--text", required=True)
    # WIP-CAP ops (2026-07-30)
    p_gw = sub.add_parser("global-wip")     # show global + per-CEO WIP vs caps
    p_stale = sub.add_parser("stale")       # list stale claims (read-only)
    p_stale.add_argument("--hours", type=float, default=None)
    p_reap = sub.add_parser("reap-stale")   # recycle stale claims back to pool
    p_reap.add_argument("--hours", type=float, default=None)
    p_reap.add_argument("--dry-run", action="store_true")
    p_cap = sub.add_parser("cap-check")     # dry-run the claim gate for an actor
    p_cap.add_argument("--actor", required=True)
    # ACTIVE-BOARD CAP ops (2026-07-30)
    p_board = sub.add_parser("board")       # show active board vs cap + reserve/dropped
    p_park = sub.add_parser("park")
    p_park.add_argument("--id", required=True); p_park.add_argument("--actor", default="board_cap")
    p_park.add_argument("--reason", default="")
    p_promote = sub.add_parser("promote")
    p_promote.add_argument("--id", required=True); p_promote.add_argument("--actor", default="board_refill")
    p_refill = sub.add_parser("refill-board")  # promote-on-drain until board hits cap
    p_refill.add_argument("--cap", type=int, default=None)
    # PHASE-2 (2026-08-03): pin the board to cap (inverse of refill), + intake diagnostics
    p_enf = sub.add_parser("enforce-board")   # park unowned-open overflow down to cap
    p_enf.add_argument("--cap", type=int, default=None)
    p_enf.add_argument("--dry-run", action="store_true")
    p_dk = sub.add_parser("dedup-key")        # print the dedup key for a title/desc
    p_dk.add_argument("--title", required=True); p_dk.add_argument("--description", default="")
    p_dk.add_argument("--tags", default="")
    p_ic = sub.add_parser("intake-check")     # print completeness verdict for a title/desc
    p_ic.add_argument("--title", required=True); p_ic.add_argument("--description", default="")
    p_ic.add_argument("--tags", default="")

    args = ap.parse_args()
    if args.cmd == "snapshot":
        print(json.dumps(snapshot(), indent=2))
    elif args.cmd == "global-wip":
        snap = _rebuild_snapshot()
        from collections import Counter
        by = Counter()
        for t in global_active_tasks(snap=snap):
            by[t.get("owner") or t.get("assignee")] += 1
        print(json.dumps({
            "global_active": global_active_count(snap=snap),
            "global_cap": GLOBAL_WIP_CAP,
            "per_ceo_cap": ACTIVE_CAP,
            "per_owner": dict(by),
            "stale_claim_hours": STALE_CLAIM_HOURS,
        }, indent=2))
    elif args.cmd == "stale":
        print(json.dumps(find_stale_claims(hours=args.hours), indent=2))
    elif args.cmd == "reap-stale":
        print(json.dumps(reap_stale_claims(hours=args.hours, dry_run=args.dry_run), indent=2))
    elif args.cmd == "cap-check":
        print(json.dumps(cap_check(args.actor), indent=2))
    elif args.cmd == "board":
        snap = _rebuild_snapshot()
        print(json.dumps({
            "active_board": snap.get("active_board"),
            "active_board_cap": snap.get("active_board_cap"),
            "open": snap.get("open"),
            "in_flight": snap.get("in_progress"),
            "reserved": snap.get("reserved"),
            "dropped": snap.get("dropped"),
            "done": snap.get("done"),
            "blocked": snap.get("blocked"),
            "total": snap.get("total"),
        }, indent=2))
    elif args.cmd == "park":
        print(json.dumps(park(args.id, args.actor, args.reason)))
    elif args.cmd == "promote":
        print(json.dumps(promote(args.id, args.actor)))
    elif args.cmd == "refill-board":
        print(json.dumps(refill_board(cap=args.cap)))
    elif args.cmd == "enforce-board":
        print(json.dumps(enforce_board_cap(cap=args.cap, dry_run=args.dry_run), indent=2))
    elif args.cmd == "dedup-key":
        tg = [t.strip() for t in args.tags.split(",") if t.strip()]
        print(_dedup_key(args.title, args.description, tg))
    elif args.cmd == "intake-check":
        tg = [t.strip() for t in args.tags.split(",") if t.strip()]
        ok, missing = _intake_assess(args.title, args.description, tg)
        print(json.dumps({"complete": ok, "missing": missing,
                          "would_state": "open" if ok else "needs_research"}, indent=2))
    elif args.cmd == "create":
        r = create(args.title, args.description, args.actor, args.priority,
                   [t.strip() for t in args.tags.split(",") if t.strip()])
        print(json.dumps(r))
    elif args.cmd == "claim":
        print(json.dumps(claim(args.id, args.actor)))
    elif args.cmd == "done":
        print(json.dumps(done(args.id, args.actor, args.summary,
                              proof_path=args.proof_path, proof_sha=args.proof_sha,
                              verifier=args.verifier)))
    elif args.cmd == "note":
        print(json.dumps(note(args.id, args.actor, args.text)))


if __name__ == "__main__":
    main()
