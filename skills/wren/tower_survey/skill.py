"""tower_survey — Wren's whole-tower situational grounding (read-only).

Governor upgrade (2026-07-30). Gives Wren real per-floor state across ALL
~170 floors in one call so she can answer "what's the state of floor N / the
whole tower right now" from real data, never a guess (R01).

Sources (all real, all read-only):
  - data/registries/qsb_floor_activity_index.json  (per-floor active/idle, label,
      last activity age, signal — the authoritative live floor state)
  - floors/*/floor_card.json                         (per-floor card + skeleton/fit-out flag)
  - data/registries/qsb_council_tasks_snapshot.json  (board counts)
  - data/registries/qsb_worker_needs_queue.json      (unmet worker needs count)

Returns a compact tower-wide picture PLUS an optional deep-dive on one floor.
"""
import glob
import json
import re
from pathlib import Path

ROOT = Path(__file__).resolve().parents[3]
REG = ROOT / "data/registries"
FLOOR_INDEX = REG / "qsb_floor_activity_index.json"
BOARD_SNAP = REG / "qsb_council_tasks_snapshot.json"
NEEDS_Q = REG / "qsb_worker_needs_queue.json"

STALE_S = 3600          # a floor idle > 1h is "stale"
COLD_S = 24 * 3600      # idle > 24h is "cold"
SKELETON_MARK = re.compile(r"skeleton|fit.?out pending|fit_out_pending|\bstub\b", re.I)


def _load(p):
    try:
        return json.loads(p.read_text())
    except Exception:
        return None


def _floor_num(key: str):
    m = re.search(r"(\d+)", key or "")
    return int(m.group(1)) if m else None


def _card_for(n):
    """Find the floor_card.json for floor number n and flag if skeleton."""
    if n is None:
        return None
    hits = glob.glob(str(ROOT / f"floors/floor_{n:02d}_*/floor_card.json")) or \
        glob.glob(str(ROOT / f"floors/floor_{n}_*/floor_card.json"))
    if not hits:
        return None
    try:
        raw = Path(hits[0]).read_text()
        card = json.loads(raw)
    except Exception:
        return None
    # Prefer the explicit structured flag; fall back to text marker.
    skel = bool(card.get("skeleton")) if isinstance(card, dict) else False
    if not skel:
        skel = bool(SKELETON_MARK.search(raw))
    return {
        "path": str(Path(hits[0]).relative_to(ROOT)),
        "skeleton": skel,
        "staff_lead": card.get("staff_lead") if isinstance(card, dict) else None,
        "bytes": len(raw),
    }


def run(floor: int = None, list_stale: int = 12):
    idx = _load(FLOOR_INDEX)
    if not idx:
        return {"ok": False, "error": "floor_activity_index not readable"}
    floors = idx.get("floors", {})
    board = _load(BOARD_SNAP) or {}
    needs = _load(NEEDS_Q) or {}

    # Per-floor deep dive
    if floor is not None:
        key = f"floor_{floor}"
        fe = floors.get(key)
        if not fe:
            return {"ok": False, "error": f"floor {floor} not in activity index"}
        return {
            "ok": True,
            "floor": floor,
            "label": fe.get("label"),
            "active": fe.get("active"),
            "last_ts": fe.get("last_ts"),
            "age_s": fe.get("age_s"),
            "signal": fe.get("signal"),
            "source": fe.get("source"),
            "card": _card_for(floor),
            "honesty": "verbatim from qsb_floor_activity_index.json (R01)",
        }

    # Whole-tower survey
    active, idle, stale, cold, skeleton = [], [], [], [], []
    for k, v in floors.items():
        n = _floor_num(k)
        age = v.get("age_s") or 0
        label = v.get("label") or k
        row = {"floor": n, "label": label, "age_s": age, "signal": v.get("signal")}
        if v.get("active"):
            active.append(row)
        else:
            idle.append(row)
        if age >= COLD_S and n not in (0,):
            cold.append(row)
        elif age >= STALE_S:
            stale.append(row)
    # skeleton floor cards (fit-out pending, structured "skeleton": true)
    for k, v in floors.items():
        n = _floor_num(k)
        c = _card_for(n)
        if c and c.get("skeleton"):
            skeleton.append({"floor": n, "label": v.get("label"), "card": c["path"],
                             "staff_lead": c.get("staff_lead")})

    idle.sort(key=lambda r: -(r["age_s"] or 0))
    stale.sort(key=lambda r: -(r["age_s"] or 0))
    cold.sort(key=lambda r: -(r["age_s"] or 0))

    return {
        "ok": True,
        "generated_ts": idx.get("generated_ts"),
        "total_floors": idx.get("total_floors"),
        "active_floors": len(active),
        "idle_floors": len(idle),
        "stale_floors_gt_1h": len(stale),
        "cold_floors_gt_24h": len(cold),
        "skeleton_cards": len(skeleton),
        "board": {
            "open": board.get("open"), "in_progress": board.get("in_progress"),
            "blocked": board.get("blocked"), "done": board.get("done"),
        },
        "worker_needs_open": needs.get("distinct_needs"),
        "worker_reports_folded": needs.get("worker_reports_folded"),
        "cold_list": cold[:list_stale],
        "stale_list": stale[:list_stale],
        "skeleton_list": skeleton[:list_stale],
        "honesty": "every floor state verbatim from the live floor activity index (R01)",
    }


if __name__ == "__main__":
    print(json.dumps(run(), indent=2))
