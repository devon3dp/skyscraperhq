"""delegate_task — Wren's first-class DELEGATION action (R01 honest, gate-respecting).

Governor upgrade (2026-07-30). Wren could already CREATE council tasks; she could
already MESSAGE a peer. This makes DELEGATION a single first-class act: pick the
right worker (by real load + who is online), hand a real task to them with a named
VERIFIER, notify them over the leadership relay, and log the whole handoff to a
ledger so she can follow it up.

It is deliberately WIP-CAP RESPECTING. Assigning a task holds a work-in-flight slot,
so before it lands an assignment on the board it runs the council's own cap_check
(GATE 17 per-CEO cap + the global WIP ceiling). If there is capacity the task is
truly assigned (state=assigned, assignee set) and the worker is pinged. If the
council is saturated it does NOT force work onto a jammed board — it records a
PENDING delegation (earmarked to the chosen worker, citing the real gate) that
governor_act will promote the moment a slot frees. Either way the handoff is
honestly logged. It never flips a gate and never bypasses the cap.

Worker routing (real signals, nothing invented):
  · explicit assignee wins (tp / asa / bill / tp_pip / acer_cass)
  · otherwise auto-pick the least-loaded eligible worker CEO, preferring one that
    is online right now (leadership relay heartbeat)
  · verifier = a different signoff-CEO (a task's owner must not verify their own work)

Ledger: data/registries/qsb_wren_delegations.jsonl (append-only).
Audit:  data/registries/qsb_f47_team_records.jsonl (governor_delegation row).
"""
import json
import subprocess
import sys
import time
import uuid
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[3]
REG = ROOT / "data/registries"
PRESENCE = REG / "leadership_comms/presence.json"
DELEG = REG / "qsb_wren_delegations.jsonl"
F47 = REG / "qsb_f47_team_records.jsonl"

# canonical worker-CEO actor  ->  leadership-relay identity
ACTOR_ALIAS = {
    "tp": "tp_pip", "tp_pip": "tp_pip",
    "asa": "acer_cass", "acer_cass": "acer_cass", "acer": "acer_cass",
    "bill": "bill",
}
RELAY_ID = {"tp_pip": "tp", "acer_cass": "asa", "bill": "bill"}
# who is eligible to be handed backlog work (Wren governs, she does not self-assign backlog)
ELIGIBLE_WORKERS = ("tp_pip", "acer_cass")
SIGNOFF_CEOS = ("wren", "tp_pip", "acer_cass", "bill")
ONLINE_WINDOW_S = 90


def _now():
    return datetime.now(timezone.utc).isoformat(timespec="seconds").replace("+00:00", "Z")


def _load(p):
    try:
        return json.loads(Path(p).read_text())
    except Exception:
        return None


def _ct():
    sys.path.insert(0, str(ROOT / "tools"))
    import qsb_council_tasks as CT  # type: ignore
    return CT


def _online():
    pres = _load(PRESENCE) or {}
    now = time.time()
    out = {}
    for ident, rec in pres.items():
        hb = rec.get("last_heartbeat_epoch") or 0
        age = now - hb if hb else None
        out[ident] = bool(hb) and age is not None and age < ONLINE_WINDOW_S \
            and str(rec.get("status", "")).lower() != "offline"
    return out


def _pick_assignee(CT, online):
    """Least-loaded eligible worker CEO, preferring one online now."""
    scored = []
    for actor in ELIGIBLE_WORKERS:
        load = len(CT.active_tasks_for(actor))
        rid = RELAY_ID.get(actor)
        is_on = online.get(rid, False)
        # sort key: online first (0), then by load, then stable
        scored.append(((0 if is_on else 1, load), actor, load, is_on))
    scored.sort(key=lambda x: x[0])
    best = scored[0]
    return best[1], {"picked_by": "least-loaded-online", "load": best[2],
                     "online": best[3],
                     "candidates": [{"actor": a, "load": l, "online": o}
                                    for (_, a, l, o) in scored]}


def _pick_verifier(assignee, online):
    """A different signoff-CEO to verify (owner can't verify own work). Prefer online."""
    cands = [c for c in SIGNOFF_CEOS if c != assignee and c != "wren"] or \
            [c for c in SIGNOFF_CEOS if c != assignee]
    # prefer online
    cands.sort(key=lambda a: 0 if online.get(RELAY_ID.get(a, a), False) else 1)
    return cands[0] if cands else "wren"


def _notify(relay_id, text):
    """Best-effort leadership-relay DM using Wren's existing proven client. Honest result."""
    if not relay_id:
        return {"sent": False, "reason": "assignee has no relay identity (not tp/asa/bill)"}
    try:
        r = subprocess.run(
            ["python3", str(ROOT / "tools/qsb_leadership_client.py"),
             "--identity", "wren", "--once", "--send-dm", relay_id, text],
            capture_output=True, text=True, timeout=45, cwd=str(ROOT))
        out = [l for l in (r.stdout or "").splitlines() if l.strip()]
        last = out[-1] if out else ((r.stderr or "").strip()[:160] or "no output")
        ok = r.returncode == 0
        return {"sent": ok, "detail": last[:200]}
    except Exception as e:
        return {"sent": False, "reason": str(e)[:200]}


def run(title: str = "", description: str = "", task_id: str = "",
        assignee: str = "", verifier: str = "", priority: str = "normal",
        reason: str = "", notify: bool = True, tags=None):
    CT = _ct()
    online = _online()

    # 1) resolve assignee (explicit alias or auto by load)
    if assignee:
        a = ACTOR_ALIAS.get(assignee.lower().strip())
        if not a:
            return {"ok": False, "error": f"unknown assignee '{assignee}' — use one of "
                    f"{sorted(set(ACTOR_ALIAS))}"}
        pick_meta = {"picked_by": "explicit"}
        assignee_actor = a
    else:
        assignee_actor, pick_meta = _pick_assignee(CT, online)

    # 2) resolve verifier
    verifier_actor = ACTOR_ALIAS.get((verifier or "").lower().strip(), verifier.lower().strip()) \
        if verifier else _pick_verifier(assignee_actor, online)
    if verifier_actor == assignee_actor:
        verifier_actor = _pick_verifier(assignee_actor, online)

    # 3) resolve or create the task
    snap = CT.snapshot()
    board = {t.get("id"): t for t in snap.get("tasks", [])}
    if task_id:
        if task_id not in board:
            return {"ok": False, "error": f"task_id {task_id} not on the council board"}
        t = board[task_id]
        title = t.get("title") or title
        created = False
    else:
        title = (title or "").strip()
        if len(title) < 6:
            return {"ok": False, "error": "title required (min 6 chars) OR pass an existing task_id"}
        # de-dupe against open/in-progress board
        key = title.lower()[:50]
        for tid, t in board.items():
            if t.get("state") in ("done", "cancelled", "dropped"):
                continue
            body = ((t.get("title") or "") + " " + (t.get("description") or "")).lower()
            if key and key in body:
                task_id = tid
                title = t.get("title") or title
                created = False
                break
        else:
            r = CT.create(title, description[:1500], actor="wren",
                          priority=(priority if priority in ("normal", "high", "low") else "normal"),
                          tags=(tags or ["governor", "delegation", "wren"]))
            task_id = r.get("task_id")
            created = True

    # 4) WIP-cap gate — does the assignee have capacity to actually take this now?
    cap = CT.cap_check(assignee_actor, task_id)
    delegation_id = "dg_" + uuid.uuid4().hex[:10]

    if cap.get("ok"):
        # land a real assignment on the board (state=assigned, assignee set)
        CT._append_event({"ts": _now(), "event": "assigned", "task_id": task_id,
                          "actor": "wren", "assignee": assignee_actor,
                          "verifier": verifier_actor,
                          "note": (reason or f"Wren delegated to {assignee_actor}")[:300]})
        status = "assigned"
        handoff = (f"[Wren → {assignee_actor}] You are assigned council task {task_id}: "
                   f"\"{title[:90]}\". Verifier: {verifier_actor}. "
                   f"{('Why you: ' + reason) if reason else ''}".strip())
    else:
        # council saturated / assignee at cap — DO NOT force. Earmark as pending.
        status = "pending_capacity"
        handoff = (f"[Wren → {assignee_actor}] Earmarked for you: council task {task_id} "
                   f"\"{title[:80]}\" (verifier {verifier_actor}). "
                   f"Held pending capacity — {cap.get('error', 'wip_cap')}. Claim it when a slot frees.")

    # 5) notify over the relay (best-effort, honestly recorded)
    notify_result = {"sent": False, "reason": "notify disabled"}
    if notify:
        notify_result = _notify(RELAY_ID.get(assignee_actor), handoff)

    # 6) ledger + F47 audit
    rec = {
        "ts": _now(), "delegation_id": delegation_id, "task_id": task_id,
        "title": title[:120], "assignee": assignee_actor, "verifier": verifier_actor,
        "priority": priority, "reason": (reason or "")[:300], "status": status,
        "task_created": created, "assignee_pick": pick_meta,
        "cap_check": {"ok": cap.get("ok"), "reason": cap.get("error"),
                      "global_active": cap.get("global_active_count"),
                      "global_cap": cap.get("global_cap"),
                      "active_count": cap.get("active_count")},
        "notified": notify_result,
        "by": "wren",
    }
    try:
        DELEG.parent.mkdir(parents=True, exist_ok=True)
        with DELEG.open("a") as f:
            f.write(json.dumps(rec) + "\n")
    except Exception as e:
        return {"ok": False, "error": f"failed to write delegation ledger: {e}", "record": rec}
    try:
        with F47.open("a") as f:
            f.write(json.dumps({"ts": _now(), "kind": "governor_delegation", "by": "wren",
                                "delegation_id": delegation_id, "task_id": task_id,
                                "assignee": assignee_actor, "verifier": verifier_actor,
                                "status": status, "title": title[:120]}) + "\n")
    except Exception:
        pass

    return {
        "ok": True,
        "delegation_id": delegation_id,
        "task_id": task_id,
        "title": title[:120],
        "assignee": assignee_actor,
        "verifier": verifier_actor,
        "status": status,
        "task_created": created,
        "assignee_pick": pick_meta,
        "wip_gate": ("capacity_ok — assignment landed on the board"
                     if cap.get("ok") else
                     f"gate_respected — {cap.get('error')} — earmarked pending, nothing forced"),
        "notify": notify_result,
        "summary": handoff,
        "honesty": "real council task, real cap_check, real ledger row. No gate flipped, no cap bypassed (R01).",
    }


if __name__ == "__main__":
    import argparse
    ap = argparse.ArgumentParser()
    ap.add_argument("--selftest", action="store_true",
                    help="prove the assign-lands-on-board mechanics against an ISOLATED temp council log (no live pollution)")
    ap.add_argument("--title", default="")
    ap.add_argument("--task-id", default="")
    ap.add_argument("--assignee", default="")
    ap.add_argument("--no-notify", action="store_true")
    a = ap.parse_args()
    if a.selftest:
        # Isolated proof: point the council LOG at a temp file, create + assign, show state.
        import tempfile
        CT = _ct()
        tmp = Path(tempfile.mkdtemp()) / "council.jsonl"
        CT.LOG = tmp  # process-local redirect; live board untouched
        r = CT.create("SELFTEST delegate mechanics proof", actor="wren")
        tid = r["task_id"]
        CT._append_event({"ts": _now(), "event": "assigned", "task_id": tid,
                          "actor": "wren", "assignee": "tp_pip", "verifier": "acer_cass"})
        snap = CT.snapshot()
        t = {x["id"]: x for x in snap["tasks"]}[tid]
        print(json.dumps({"selftest": True, "temp_log": str(tmp), "task_id": tid,
                          "state": t.get("state"), "assignee": t.get("assignee"),
                          "assigned_by": t.get("assigned_by"),
                          "PASS": t.get("state") == "assigned" and t.get("assignee") == "tp_pip"},
                         indent=2))
    else:
        print(json.dumps(run(title=a.title, task_id=a.task_id, assignee=a.assignee,
                              notify=not a.no_notify), indent=2, default=str))
