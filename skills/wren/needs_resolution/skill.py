"""needs_resolution — Wren's CLOSE-THE-LOOP capability for real worker needs.

Wren already SURFACES worker needs (worker_needs_digest) and BOOKS tasks. This
skill tracks the *other half*: need -> resolution -> verified. For every OPEN
need in the honest queue it answers "is a real council task actually handling
this, and is it done?", and it lets Wren RESOLVE a need only when there is real
cited evidence.

Honesty (R01):
  - Every need is read verbatim from data/registries/qsb_worker_needs_queue.json
    (the honest queue; each need already carries evidence_source + ts).
  - Council tasks are read from the live snapshot; a need is only linked to a
    task when the task's OWN text names that floor AND shares a need keyword.
  - A need is NEVER marked resolved without a real task id that exists on the
    live board. Auto-resolve fires only for tasks in state=done. An explicit
    resolve against an active task is recorded as "dispatched" (loop opened,
    fix booked) — NOT as "resolved/verified".
  - Resolutions are written ONLY to Wren's own append-only registry
    data/registries/qsb_wren_needs_resolution.jsonl. No Codex-owned file is
    edited. The queue and the council board are read-only here.
"""
import json
import os
import re
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[3]
QUEUE = ROOT / "data/registries/qsb_worker_needs_queue.json"
SNAP = ROOT / "data/registries/qsb_council_tasks_snapshot.json"
RES = ROOT / "data/registries/qsb_wren_needs_resolution.jsonl"  # Wren's OWN file

ACTIVE = {"open", "claimed", "assigned", "in_progress", "awaiting_peer_signoff"}
DONE = {"done", "closed", "resolved", "completed"}
DEAD = {"cancelled", "canceled", "rejected"}

# keywords that carry the substance of a worker need
NEED_KW = {
    "skeleton", "fit-out", "fitout", "roster", "headcount", "reconcile",
    "stale", "refresh", "reception", "signal", "quiet", "card", "fit",
    "trading", "pnl", "oanda", "boardroom", "relay",
}


def _now():
    return datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")


def _floor_re(n: int):
    # word-boundary floor tokens only, so "f3" never matches inside "49"/"F350"
    return re.compile(r"(?:\bfloor[ _]0*%d\b|\bf0*%d\b)" % (n, n), re.IGNORECASE)


def _kws(txt: str):
    return {w for w in re.findall(r"[a-z][a-z\-]+", (txt or "").lower()) if w in NEED_KW}


def _load_needs():
    if not QUEUE.exists():
        return None, "worker_needs_queue not found"
    try:
        q = json.loads(QUEUE.read_text())
    except Exception as e:
        return None, f"bad queue json: {e}"
    return q, None


def _load_tasks():
    if not SNAP.exists():
        return [], None
    try:
        d = json.loads(SNAP.read_text())
    except Exception as e:
        return [], f"bad snapshot json: {e}"
    return d.get("tasks", []), None


def _task_blob(t):
    return ((t.get("title") or "") + " " + (t.get("description") or "")).strip()


def _match(need, tasks):
    """Best real council task addressing this need, or None.

    Score rewards: floor named in the TITLE, an explicit fit-out/skeleton task,
    and each shared need-keyword. Only tasks whose text actually names the
    need's floor AND shares a keyword can match — the generic collective
    "worker needs surfaced" task cannot masquerade as a per-floor fix.
    """
    n = need.get("floor")
    if n is None:
        return None
    fr = _floor_re(n)
    nkw = _kws(need.get("need", ""))
    best, best_score = None, 0
    for t in tasks:
        title = t.get("title") or ""
        blob = _task_blob(t)
        if not blob:
            continue
        if not fr.search(blob):
            continue
        shared = nkw & _kws(blob)
        if not shared:
            continue
        score = 2 * len(shared)
        if fr.search(title):
            score += 3
        low = blob.lower()
        if "skeleton_card" in low or "fit out floor card" in low or "fit-out" in low:
            score += 3
        # prefer a done task, then an active one, over a dead/generic one
        st = t.get("state")
        if st in DONE:
            score += 4
        elif st in ACTIVE:
            score += 1
        if score > best_score:
            best, best_score = t, score
    if not best:
        return None
    return {
        "task_id": best.get("id"),
        "task_state": best.get("state"),
        "task_title": (best.get("title") or _task_blob(best)[:70] or "(untitled)"),
        "match_score": best_score,
        "match_reason": f"task names floor {n} and shares need keywords {sorted(nkw & _kws(_task_blob(best)))}",
    }


def _resolutions():
    """Latest resolution row per need_id from Wren's own append-only file."""
    out = {}
    if not RES.exists():
        return out
    for line in RES.read_text().splitlines():
        line = line.strip()
        if not line:
            continue
        try:
            r = json.loads(line)
        except Exception:
            continue
        nid = r.get("need_id")
        if nid:
            out[nid] = r  # last write wins
    return out


def _find_task(task_id, tasks):
    for t in tasks:
        if t.get("id") == task_id:
            return t
    return None


def _append(row):
    RES.parent.mkdir(parents=True, exist_ok=True)
    with os.fdopen(os.open(str(RES), os.O_WRONLY | os.O_CREAT | os.O_APPEND, 0o644), "a") as f:
        f.write(json.dumps(row) + "\n")


# ---------------------------------------------------------------- digest ----
def _digest(n=20, floor=None):
    q, err = _load_needs()
    if err:
        return {"ok": False, "error": err}
    tasks, terr = _load_tasks()
    needs = [x for x in q.get("needs", []) if x.get("status", "open") == "open"]
    if floor is not None:
        needs = [x for x in needs if x.get("floor") == floor]
    res = _resolutions()
    rows, counts = [], {"open": 0, "in_progress": 0, "ready_to_resolve": 0,
                        "resolved_verified": 0, "resolved_dispatched": 0}
    ranked = sorted(needs, key=lambda x: -(x.get("reported_by_count") or 0))
    for x in ranked:
        nid = x.get("id")
        m = _match(x, tasks)
        prior = res.get(nid)
        if prior:
            kind = prior.get("evidence_kind")
            state = "resolved_verified" if kind == "council_task_done" else "resolved_dispatched"
        elif m and m["task_state"] in DONE:
            state = "ready_to_resolve"      # a done task addresses it — auto-resolve will close it
        elif m and m["task_state"] in ACTIVE:
            state = "in_progress"           # a real fix task is booked but not done
        else:
            state = "open"                  # nothing on the board addresses this need
        counts[state] = counts.get(state, 0) + 1
        rows.append({
            "need_id": nid,
            "floor": x.get("floor"),
            "source_floor_manager": x.get("floor_manager") or x.get("lead"),
            "room": x.get("room"),
            "need": x.get("need"),
            "reported_by_count": x.get("reported_by_count"),
            "evidence_source": x.get("evidence_source"),
            "council_task": m,
            "resolution_state": state,
            "resolution_evidence": (prior.get("evidence") if prior else None),
        })
    return {
        "ok": True,
        "action": "digest",
        "generated_ts": q.get("generated_ts"),
        "snapshot_err": terr,
        "open_needs_total": len(needs),
        "state_counts": counts,
        "loop_closed": counts["resolved_verified"] + counts["resolved_dispatched"],
        "loop_open": counts["open"] + counts["in_progress"] + counts["ready_to_resolve"],
        "needs": rows[:n],
        "resolution_registry": str(RES.relative_to(ROOT)),
        "honesty": "R01: needs verbatim from honest queue; a need links to a task only when the task text names its floor + shares a keyword; resolved rows cite a real live task id.",
    }


# --------------------------------------------------------------- resolve ----
def _resolve(need_id=None, task_id=None, floor=None, note=None):
    q, err = _load_needs()
    if err:
        return {"ok": False, "error": err}
    tasks, terr = _load_tasks()
    by_id = {x.get("id"): x for x in q.get("needs", [])}
    already = _resolutions()

    # ---- explicit path: resolve ONE need against ONE cited task ----
    if need_id:
        need = by_id.get(need_id)
        if not need:
            return {"ok": False, "error": f"no such need id on the honest queue: {need_id} (R01: cannot resolve a need that isn't real)"}
        if need_id in already:
            return {"ok": True, "action": "resolve", "skipped": True,
                    "reason": f"need {need_id} already has a resolution row",
                    "existing": already[need_id]}
        if not task_id:
            return {"ok": False, "error": "resolve needs a task_id to cite as evidence — a need is never resolved without a real cited task (R01)"}
        t = _find_task(task_id, tasks)
        if not t:
            return {"ok": False, "error": f"REFUSED: task {task_id} is not on the live council board — cannot cite as evidence (R01: no resolve without real evidence)"}
        st = t.get("state")
        if st in DEAD:
            return {"ok": False, "error": f"REFUSED: cited task {task_id} is {st} — a dead task is not a real fix (R01)"}
        verified = st in DONE
        # optional sanity: warn if the cited task doesn't obviously address this floor
        addresses = bool(_floor_re(need.get("floor")).search(_task_blob(t)))
        row = {
            "ts": _now(),
            "need_id": need_id,
            "floor": need.get("floor"),
            "need": need.get("need"),
            "source_floor_manager": need.get("floor_manager") or need.get("lead"),
            "resolution": "resolved" if verified else "dispatched",
            "evidence_kind": "council_task_done" if verified else "council_task_dispatched",
            "evidence": {
                "task_id": task_id,
                "task_state": st,
                "task_title": (t.get("title") or _task_blob(t)[:70] or "(untitled)"),
                "task_names_this_floor": addresses,
            },
            "note": (note or "")[:500],
            "marked_by": "wren:needs_resolution_skill",
            "honesty": "cited task verified present on live board; 'resolved' only when task state is done, else 'dispatched' (fix booked, loop opened, not yet verified).",
        }
        _append(row)
        return {"ok": True, "action": "resolve", "mode": "explicit", "wrote": row,
                "resolution_registry": str(RES.relative_to(ROOT))}

    # ---- auto path: close every open need whose best matching task is DONE ----
    needs = [x for x in q.get("needs", []) if x.get("status", "open") == "open"]
    if floor is not None:
        needs = [x for x in needs if x.get("floor") == floor]
    resolved, scanned = [], 0
    for x in needs:
        nid = x.get("id")
        scanned += 1
        if nid in already:
            continue
        m = _match(x, tasks)
        if not m or m["task_state"] not in DONE:
            continue  # only a DONE task auto-closes a need
        row = {
            "ts": _now(),
            "need_id": nid,
            "floor": x.get("floor"),
            "need": x.get("need"),
            "source_floor_manager": x.get("floor_manager") or x.get("lead"),
            "resolution": "resolved",
            "evidence_kind": "council_task_done",
            "evidence": {
                "task_id": m["task_id"],
                "task_state": m["task_state"],
                "task_title": m["task_title"],
                "match_score": m["match_score"],
                "match_reason": m["match_reason"],
            },
            "note": "auto-resolved: a council task addressing this floor reached done",
            "marked_by": "wren:needs_resolution_skill(auto)",
            "honesty": "auto-close fires only for a matching task in state=done.",
        }
        _append(row)
        resolved.append(row)
    return {
        "ok": True,
        "action": "resolve",
        "mode": "auto",
        "scanned_open_needs": scanned,
        "resolved_now": len(resolved),
        "resolved": resolved,
        "note": ("no open need has a verified-done council task yet — loop stays open, honestly"
                 if not resolved else f"closed {len(resolved)} need(s) with real done-task evidence"),
        "resolution_registry": str(RES.relative_to(ROOT)),
    }


def run(action: str = "digest", n: int = 20, floor: int = None,
        need_id: str = None, task_id: str = None, note: str = None):
    if action == "resolve":
        return _resolve(need_id=need_id, task_id=task_id, floor=floor, note=note)
    return _digest(n=n, floor=floor)


if __name__ == "__main__":
    import sys
    kw = {}
    for a in sys.argv[1:]:
        if "=" in a:
            k, v = a.split("=", 1)
            if v.isdigit():
                v = int(v)
            kw[k] = v
    print(json.dumps(run(**kw), indent=2, default=str))
