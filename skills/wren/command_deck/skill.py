"""command_deck — Wren's DEEP governor eyes (read-only, R01 honest).

Governor upgrade (2026-07-30). Wren's existing eyes (tower_health / tower_survey /
governor_scan) tell her which FLOORS are active and what NEEDS doing. They did NOT
tell her the numbers a governor actually manages by: how loaded each worker is, how
full the whole council is against the WIP ceiling, how big the backlog really is,
who is stuck, and whether her own delegations landed. This skill surfaces exactly
those command-and-control numbers from real registries — nothing invented.

It reports:
  · per-CEO load        — active in-flight tasks per capped CEO vs the per-CEO cap
  · global WIP          — total concurrent in-flight vs GLOBAL_WIP_CAP + free slots
  · backlog             — open + unowned-open counts (the real depth of the queue)
  · completion          — done vs live (the throughput reality)
  · state histogram     — the whole board by state
  · blocked / stuck     — blocked tasks + stale claims holding WIP slots
  · CEO presence        — who is online now (leadership relay heartbeats)
  · delegation outcomes — Wren's own handoffs and where each one landed

Everything is derived live from qsb_council_tasks + the leadership presence file +
Wren's delegation ledger. Read-only: it writes nothing.
"""
import json
import sys
import time
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[3]
REG = ROOT / "data/registries"
PRESENCE = REG / "leadership_comms/presence.json"
DELEG = REG / "qsb_wren_delegations.jsonl"

CAPPED_CEOS = ("tp_pip", "acer_cass", "wren")
ONLINE_WINDOW_S = 90


def _load(p):
    try:
        return json.loads(Path(p).read_text())
    except Exception:
        return None


def _ct():
    sys.path.insert(0, str(ROOT / "tools"))
    import qsb_council_tasks as CT  # type: ignore
    return CT


def _presence():
    pres = _load(PRESENCE) or {}
    now = time.time()
    out = {}
    for ident, rec in pres.items():
        hb = rec.get("last_heartbeat_epoch") or 0
        age = now - hb if hb else None
        explicit_off = str(rec.get("status", "")).lower() == "offline"
        online = bool(hb) and age is not None and age < ONLINE_WINDOW_S and not explicit_off
        out[ident] = {
            "online": online,
            "heartbeat_age_s": round(age, 1) if age is not None else None,
            "addr": rec.get("reachable_addr"),
        }
    return out


def _deleg_outcomes(board_by_id):
    """Read Wren's delegation ledger and resolve where each handoff landed now."""
    if not DELEG.exists():
        return {"total": 0, "records": [], "by_status": {}, "note": "no delegations logged yet"}
    recs = []
    for line in DELEG.read_text(errors="ignore").splitlines():
        line = line.strip()
        if not line:
            continue
        try:
            recs.append(json.loads(line))
        except Exception:
            pass
    by_status = {}
    resolved = []
    for r in recs[-40:]:
        tid = r.get("task_id")
        live = board_by_id.get(tid) or {}
        cur_state = live.get("state") or "unknown"
        landed = r.get("status")  # assigned | pending_capacity at delegation time
        # outcome now: did the delegated task move forward / complete?
        if cur_state in ("done", "closed"):
            outcome = "done"
        elif cur_state in ("claimed", "in_progress", "assigned", "acknowledged",
                           "awaiting_verification", "awaiting_peer_signoff"):
            outcome = "in_flight"
        elif cur_state in ("open", "pending_admission"):
            outcome = "waiting"
        else:
            outcome = cur_state
        by_status[outcome] = by_status.get(outcome, 0) + 1
        resolved.append({
            "delegation_id": r.get("delegation_id"), "task_id": tid,
            "assignee": r.get("assignee"), "verifier": r.get("verifier"),
            "delegated_status": landed, "current_state": cur_state,
            "outcome": outcome, "title": (r.get("title") or "")[:70],
            "ts": r.get("ts"),
        })
    return {"total": len(recs), "by_outcome": by_status, "records": resolved[-12:]}


def run():
    CT = _ct()
    snap = CT.snapshot()
    tasks = snap.get("tasks", [])
    board_by_id = {t.get("id"): t for t in tasks}

    # state histogram
    hist = {}
    for t in tasks:
        s = (t.get("state") or "?").lower()
        hist[s] = hist.get(s, 0) + 1

    # per-CEO load
    per_ceo = {}
    for ceo in CAPPED_CEOS:
        held = CT.active_tasks_for(ceo)
        per_ceo[ceo] = {
            "active": len(held),
            "cap": CT.ACTIVE_CAP,
            "at_cap": len(held) >= CT.ACTIVE_CAP,
            "task_ids": [t.get("id") for t in held],
        }

    # global WIP
    gwip = CT.global_active_count()
    global_wip = {
        "in_flight": gwip,
        "cap": CT.GLOBAL_WIP_CAP,
        "free_slots": max(0, CT.GLOBAL_WIP_CAP - gwip),
        "saturated": gwip >= CT.GLOBAL_WIP_CAP,
    }

    # backlog depth
    open_tasks = [t for t in tasks if (t.get("state") or "").lower() in ("open", "pending_admission")]
    unowned_open = [t for t in open_tasks
                    if not (t.get("owner") or t.get("assignee"))
                    and (t.get("state") or "").lower() == "open"]
    pri = {"high": 0, "normal": 1, "low": 2}
    top_backlog = sorted(unowned_open, key=lambda t: pri.get((t.get("priority") or "normal"), 1))[:8]

    # completion / throughput reality
    done = hist.get("done", 0) + hist.get("closed", 0)
    dead = sum(hist.get(s, 0) for s in ("dropped", "cancelled", "denied", "superseded", "archived", "duplicate"))
    live_total = len(tasks) - dead
    completion_pct = round(100.0 * done / live_total, 1) if live_total else 0.0

    # blocked + stuck
    blocked = [{"id": t.get("id"), "title": (t.get("title") or "")[:70], "owner": t.get("owner")}
               for t in tasks if (t.get("state") or "").lower() == "blocked"]
    try:
        stale = CT.find_stale_claims()
    except Exception:
        stale = []

    presence = _presence()
    delegations = _deleg_outcomes(board_by_id)

    # a governor's one-line read of the room
    briefing = (
        f"WIP {gwip}/{CT.GLOBAL_WIP_CAP} ({global_wip['free_slots']} free) · "
        f"backlog {len(open_tasks)} open ({len(unowned_open)} unowned) · "
        f"done {done}/{live_total} ({completion_pct}%) · "
        f"blocked {len(blocked)} · stale {len(stale)} · "
        f"CEOs online: {sorted(i for i, v in presence.items() if v['online']) or 'none'}"
    )
    # honest headline recommendation for the governor
    if global_wip["saturated"]:
        rec = ("Council is SATURATED at the WIP ceiling — do NOT start/delegate new "
               "in-flight work. Drive existing in-flight tasks to done, unblock the "
               f"{len(blocked)} blocked, and reap {len(stale)} stale claims to free slots. "
               "Delegation of new work should QUEUE until a slot frees.")
    elif global_wip["free_slots"] and unowned_open:
        rec = (f"{global_wip['free_slots']} WIP slot(s) free and {len(unowned_open)} unowned "
               "open tasks waiting — assign the highest-priority ones to the least-loaded "
               "online worker (delegate_task / governor_act).")
    else:
        rec = "Capacity available; queue is shallow. Hold or top up from governor_scan findings."

    return {
        "ok": True,
        "generated_ts": datetime.now(timezone.utc).isoformat(timespec="seconds").replace("+00:00", "Z"),
        "briefing": briefing,
        "recommendation": rec,
        "global_wip": global_wip,
        "per_ceo_load": per_ceo,
        "backlog": {
            "open_total": len(open_tasks),
            "unowned_open": len(unowned_open),
            "top_unowned_by_priority": [
                {"id": t.get("id"), "priority": t.get("priority") or "normal",
                 "title": (t.get("title") or "")[:80]} for t in top_backlog
            ],
        },
        "throughput": {"done": done, "live_total": live_total, "completion_pct": completion_pct,
                       "dead_or_dropped": dead},
        "state_histogram": dict(sorted(hist.items(), key=lambda kv: -kv[1])),
        "blocked": blocked,
        "stale_claims": stale,
        "ceo_presence": presence,
        "delegation_outcomes": delegations,
        "honesty": "every number derived live from qsb_council_tasks + leadership presence + Wren's delegation ledger (R01). Read-only.",
    }


if __name__ == "__main__":
    print(json.dumps(run(), indent=2, default=str))
