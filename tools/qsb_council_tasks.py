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
            # Ross 2026-07-05 #166: reset clocks so SLA doesn't count old stale time
            t["started_at"] = e.get("ts")
            t["claimed_at"] = e.get("ts") if t.get("owner") else None
            t["assigned_at"] = None
            t["sandbox_passed_by"] = None
            t["sandbox_passed_at"] = None
            t["peer_signoff_by"] = None
            t["peer_signoff_at"] = None
            t["peer_signoff_verdict"] = None

    # 2026-07-18: fold in Governance V2 tasks (ADD not TAKE) so the board reflects real V2 work
    for _tid, _t in _load_gov2_tasks().items():
        tasks[_tid] = _t

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


_WORKER_CEOS = {"hq_claude", "tp_pip", "acer_cass"}
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


def propose(title: str, description: str = "", actor: str = "hq_claude",
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
ACTIVE_CAP = 3

# CEO identities the cap applies to. Ross himself is NOT capped (safety gate).
# Future CEOs: add their actor id here.
CAPPED_CEOS = {"hq_claude", "tp_pip", "acer_cass", "wren"}

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
    "claimed", "in_progress", "assigned", "acknowledged",
    "awaiting_peer_signoff", "ready_to_ship", "blocked",
    "needs_partner", "needs_proof", "needs_second_verifier",
    "needs_verification", "blocked_waiting_for_peer",
    "blocked_waiting_for_verifier", "needs_ross_chatgpt_verifier_review",
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
    return {"ok": True}


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
                         detector: str = "hq_claude", evidence: str = "",
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


def claim(task_id: str, actor: str) -> dict:
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


def sandbox_pass(task_id: str, actor: str, evidence: str) -> dict:
    """Worker self-verifies in own sandbox. Task moves to
    awaiting_peer_signoff."""
    _append_event({"ts": utc(), "event": "sandbox_passed", "task_id": task_id,
                   "actor": actor, "text": evidence[:800]})
    return {"ok": True}


def peer_signoff(task_id: str, actor: str, verdict: str = "approve",
                 comment: str = "") -> dict:
    """A DIFFERENT CEO reviews the sandbox evidence + approves/rejects.
    Ross 2026-07-06 rule: the taker (proposer OR claimer) CANNOT sign off own task.
    Only the OTHER 3 CEOs from {wren, hq_claude, tp_pip, acer_cass} may signoff."""
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
