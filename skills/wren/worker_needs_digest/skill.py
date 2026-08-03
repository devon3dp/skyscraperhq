"""worker_needs_digest — surfaces the real worker-needs queue for Wren to act on.

Read-only. Sorts distinct needs by how many workers reported them (impact)
so Wren can prioritise the loudest real needs across the tower.
"""
import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[3]
QUEUE = ROOT / "data/registries/qsb_worker_needs_queue.json"


def run(n: int = 8, floor: int = None):
    if not QUEUE.exists():
        return {"ok": False, "error": "worker_needs_queue not found"}
    try:
        q = json.loads(QUEUE.read_text())
    except Exception as e:
        return {"ok": False, "error": f"bad queue json: {e}"}
    needs = q.get("needs", [])
    if floor is not None:
        needs = [x for x in needs if x.get("floor") == floor]
    # rank by reported_by_count desc (impact), stable on floor
    ranked = sorted(needs, key=lambda x: -(x.get("reported_by_count") or 0))
    top = []
    for x in ranked[:n]:
        top.append({
            "floor": x.get("floor"),
            "lead": x.get("lead") or x.get("floor_manager"),
            "room": x.get("room"),
            "need": x.get("need"),
            "reported_by_count": x.get("reported_by_count"),
            "from_worker": x.get("from_worker"),
            "evidence_source": x.get("evidence_source"),
        })
    return {
        "ok": True,
        "generated_ts": q.get("generated_ts"),
        "distinct_needs_total": q.get("distinct_needs"),
        "worker_reports_folded": q.get("worker_reports_folded"),
        "returned": len(top),
        "top_needs": top,
        "honesty": "every need verbatim from a real worker report row (R01)",
    }


if __name__ == "__main__":
    print(json.dumps(run(), indent=2))
