"""council_board_digest — lets Wren see & drive the Task Council board.

Read-only. Ranks active tasks by SLA-breach then age so Wren can prioritise
what's stuck. Creating/claiming/closing tasks stays in qsb_council_tasks.py.
"""
import json
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[3]
SNAP = ROOT / "data/registries/qsb_council_tasks_snapshot.json"
ACTIVE = {"open", "claimed", "assigned", "in_progress", "awaiting_peer_signoff"}


def _age_min(ts: str):
    try:
        t = datetime.fromisoformat((ts or "").replace("Z", "+00:00"))
        return round((datetime.now(timezone.utc) - t).total_seconds() / 60.0)
    except Exception:
        return None


def _sla_breach(task) -> bool:
    for note in (task.get("notes") or []):
        if "SLA-BREACH" in (note.get("text") or ""):
            return True
    return False


def run(n: int = 10, state: str = None):
    if not SNAP.exists():
        return {"ok": False, "error": "council snapshot not found"}
    try:
        d = json.loads(SNAP.read_text())
    except Exception as e:
        return {"ok": False, "error": f"bad snapshot json: {e}"}
    tasks = d.get("tasks", [])
    if state:
        pool = [t for t in tasks if t.get("state") == state]
    else:
        pool = [t for t in tasks if t.get("state") in ACTIVE]
    # rank: SLA breaches first, then oldest
    def keyf(t):
        return (0 if _sla_breach(t) else 1, -(_age_min(t.get("created_at")) or 0))
    ranked = sorted(pool, key=keyf)
    out = []
    for t in ranked[:n]:
        out.append({
            "id": t.get("id"),
            "title": t.get("title") or t.get("description", "")[:70] or "(untitled)",
            "owner": t.get("owner"),
            "state": t.get("state"),
            "priority": t.get("priority"),
            "age_min": _age_min(t.get("created_at")),
            "sla_breach": _sla_breach(t),
        })
    return {
        "ok": True,
        "snapshot_ts": d.get("ts"),
        "totals": {k: d.get(k) for k in ("total", "open", "in_progress", "blocked", "done")},
        "active_shown": len(out),
        "top_active": out,
        "act_via": "tools/qsb_council_tasks.py (create/claim/note/done)",
    }


if __name__ == "__main__":
    print(json.dumps(run(), indent=2))
