"""governor_scan — Wren's management DETECTION engine (read-only).

Governor upgrade (2026-07-30). Turns the raw tower state into a ranked list of
concrete management FINDINGS Wren should act on — each with a suggested council
task title so she can create real work with wren_create_council_task.

It does NOT create tasks itself (read-only); it hands Wren a prioritised agenda
so her model reasons over real findings and decides what to dispatch. It also
de-dupes against the CURRENT open council board so she doesn't create a task
that already exists.

Finding kinds (all from real registries, R01):
  cold_floor        — a floor idle > 24h (needs a wake / check)
  skeleton_card     — a floor card still skeleton / fit-out pending (needs fit-out)
  loud_worker_need  — a real worker need reported by many workers (needs actioning)
  blocked_task      — a council task stuck blocked (needs unblocking)
  stale_in_progress — a task claimed but idle a long time (SLA drift)
"""
import glob
import json
import re
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[3]
REG = ROOT / "data/registries"
FLOOR_INDEX = REG / "qsb_floor_activity_index.json"
BOARD_SNAP = REG / "qsb_council_tasks_snapshot.json"
NEEDS_Q = REG / "qsb_worker_needs_queue.json"

COLD_S = 24 * 3600
SKELETON_MARK = re.compile(r"skeleton|fit.?out pending|fit_out_pending|\bstub\b", re.I)
STALE_INPROGRESS_S = 6 * 3600


def _load(p):
    try:
        return json.loads(p.read_text())
    except Exception:
        return None


def _num(k):
    m = re.search(r"(\d+)", k or "")
    return int(m.group(1)) if m else None


def _age_iso(ts):
    try:
        t = datetime.fromisoformat(str(ts).replace("Z", "+00:00"))
        return (datetime.now(timezone.utc) - t).total_seconds()
    except Exception:
        return None


def _open_titles(board):
    """Set of lowercased open/in_progress task titles+descriptions for de-dupe."""
    corpus = []
    for t in (board.get("tasks") or []):
        if t.get("state") in ("done", "cancelled"):
            continue
        corpus.append(((t.get("title") or "") + " " + (t.get("description") or "")).lower())
    return corpus


def _already_covered(corpus, *keys):
    keys = [k.lower() for k in keys if k]
    for c in corpus:
        if all(k in c for k in keys):
            return True
    return False


def run(max_findings: int = 10):
    idx = _load(FLOOR_INDEX) or {}
    board = _load(BOARD_SNAP) or {}
    needs = _load(NEEDS_Q) or {}
    floors = idx.get("floors", {})
    corpus = _open_titles(board)
    findings = []

    # 1) cold floors (idle > 24h) — skip lobby floor 0
    cold = []
    for k, v in floors.items():
        n = _num(k)
        if n in (0, None):
            continue
        if not v.get("active") and (v.get("age_s") or 0) >= COLD_S:
            cold.append((n, v.get("label") or k, v.get("age_s")))
    cold.sort(key=lambda r: -(r[2] or 0))
    for n, label, age in cold[:4]:
        title = f"Wake + health-check {label} (idle {int(age/3600)}h)"
        findings.append({
            "kind": "cold_floor", "floor": n, "priority": "normal",
            "detail": f"{label} has had no worker activity for {int(age/3600)}h.",
            "suggested_task_title": title,
            "already_on_board": _already_covered(corpus, label, "idle"),
        })

    # 2) skeleton / fit-out-pending floor cards
    skel = []
    for k, v in floors.items():
        n = _num(k)
        if n in (None,):
            continue
        hits = glob.glob(str(ROOT / f"floors/floor_{n:02d}_*/floor_card.json")) or \
            glob.glob(str(ROOT / f"floors/floor_{n}_*/floor_card.json"))
        if not hits:
            continue
        try:
            raw = Path(hits[0]).read_text()
            card = json.loads(raw)
        except Exception:
            continue
        is_skel = bool(card.get("skeleton")) if isinstance(card, dict) else bool(SKELETON_MARK.search(raw))
        if is_skel:
            skel.append((n, v.get("label") or k, str(Path(hits[0]).relative_to(ROOT))))
    for n, label, path in skel[:4]:
        title = f"Fit out floor card for {label} (card still skeleton)"
        findings.append({
            "kind": "skeleton_card", "floor": n, "priority": "normal",
            "detail": f"{label}'s floor card is still skeleton/fit-out-pending ({path}).",
            "suggested_task_title": title,
            "already_on_board": _already_covered(corpus, label, "card"),
        })

    # 3) loudest unmet worker needs
    ranked_needs = sorted(needs.get("needs", []),
                          key=lambda x: -(x.get("reported_by_count") or 0))
    for x in ranked_needs[:4]:
        fl = x.get("floor")
        need = (x.get("need") or "").strip()
        cnt = x.get("reported_by_count") or 0
        if not need:
            continue
        title = f"Action worker need on F{fl}: {need[:70]} ({cnt} workers)"
        findings.append({
            "kind": "loud_worker_need", "floor": fl,
            "priority": "high" if cnt >= 50 else "normal",
            "detail": f"{cnt} workers on F{fl} report: {need[:180]}",
            "suggested_task_title": title,
            "already_on_board": _already_covered(corpus, need[:40]),
        })

    # 4) blocked council tasks
    for t in (board.get("tasks") or []):
        if t.get("state") == "blocked":
            title = f"Unblock council task {t.get('id')}: {(t.get('title') or '')[:60]}"
            findings.append({
                "kind": "blocked_task", "task_id": t.get("id"), "priority": "high",
                "detail": f"Task {t.get('id')} is blocked; owner={t.get('owner')}.",
                "suggested_task_title": title, "already_on_board": True,
            })

    # 5) stale in-progress (SLA drift)
    for t in (board.get("tasks") or []):
        if t.get("state") in ("claimed", "in_progress"):
            started = t.get("started_at") or t.get("claimed_at") or t.get("created_at")
            age = _age_iso(started)
            if age and age >= STALE_INPROGRESS_S:
                findings.append({
                    "kind": "stale_in_progress", "task_id": t.get("id"),
                    "priority": "normal",
                    "detail": f"Task {t.get('id')} held by {t.get('owner')} for {int(age/3600)}h with no completion.",
                    "suggested_task_title": f"Chase/reassign stalled task {t.get('id')} (held {int(age/3600)}h)",
                    "already_on_board": True,
                })

    # rank: not-yet-on-board first, then high priority
    pri = {"high": 0, "normal": 1, "low": 2}
    findings.sort(key=lambda f: (f.get("already_on_board", False),
                                 pri.get(f.get("priority"), 1)))
    fresh = [f for f in findings if not f.get("already_on_board")]

    return {
        "ok": True,
        "generated_ts": idx.get("generated_ts"),
        "total_findings": len(findings),
        "new_actionable_findings": len(fresh),
        "findings": findings[:max_findings],
        "guidance": ("Pick the top NEW findings (already_on_board=false) and create a real "
                     "council task for each with wren_create_council_task using the "
                     "suggested_task_title. Skip anything already_on_board=true."),
        "honesty": "every finding derived from a real registry row (R01)",
    }


if __name__ == "__main__":
    print(json.dumps(run(), indent=2))
