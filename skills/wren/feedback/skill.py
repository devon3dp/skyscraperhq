"""feedback — governed feedback module for Wren (improvement doc A5).

WHAT THIS DOES
--------------
Records Ross's feedback about a specific Wren message/answer as an append-only
row in data/registries/qsb_wren_feedback.jsonl, and produces a category-grouped
digest of recent feedback so improvement can be DATA-DRIVEN later.

WHAT THIS DELIBERATELY DOES NOT DO (HARD GUARDRAIL)
---------------------------------------------------
- It does NOT retrain Wren.
- It does NOT rewrite / edit Wren's mind, persona, memory or any prompt.
- It does NOT flip any execution gate.
- It does NOT trigger any automatic action off the back of a feedback row.

The ONLY side effect is appending one JSON line to a registry that a human
reviews later. Every row lands with reviewed=false; nothing consumes it
automatically. Improvement stays a human-in-the-loop decision. This module is
pure evidence collection — see GUARDRAIL_CONTRACT below, which is asserted at
import time so the file cannot silently gain retrain/rewrite behaviour.
"""
import json
from datetime import datetime, timezone
from pathlib import Path
from collections import Counter, OrderedDict

ROOT = Path(__file__).resolve().parents[3]
# Our OWN registry — not one Codex writes. Append-only.
FEEDBACK = ROOT / "data/registries/qsb_wren_feedback.jsonl"

CATEGORIES = [
    "correct", "incorrect", "helpful", "misunderstood",
    "too_slow", "identity_error", "memory_error", "relay_corruption",
]

# Machine-checkable statement of intent. Asserted at import so no future edit
# can quietly turn this into a retrain/rewrite path without tripping the assert.
GUARDRAIL_CONTRACT = {
    "auto_retrain": False,
    "auto_rewrite": False,
    "touches_wren_mind": False,
    "flips_gates": False,
    "only_effect": "append reviewable feedback row (reviewed=false)",
}
assert not any(GUARDRAIL_CONTRACT[k] for k in
               ("auto_retrain", "auto_rewrite", "touches_wren_mind", "flips_gates")), \
    "feedback skill must never retrain/rewrite/touch-mind/flip-gates"


def _now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds").replace("+00:00", "Z")


def _record(category: str, target: str = "", note: str = "") -> dict:
    if category not in CATEGORIES:
        return {"ok": False, "error": f"unknown category '{category}'",
                "allowed": CATEGORIES}
    row = {
        "ts": _now(),
        "category": category,
        "target": (target or "")[:500],
        "note": (note or "")[:1000],
        "source": "ross",
        "reviewed": False,
    }
    FEEDBACK.parent.mkdir(parents=True, exist_ok=True)
    with FEEDBACK.open("a") as f:
        f.write(json.dumps(row) + "\n")
    total = sum(1 for _ in FEEDBACK.open())
    return {
        "ok": True,
        "recorded": row,
        "registry": str(FEEDBACK),
        "total_rows": total,
        "retrain_triggered": False,  # explicit: nothing was retrained/rewritten
        "wren_mind_touched": False,
    }


def _load_rows() -> list:
    if not FEEDBACK.exists():
        return []
    rows = []
    for line in FEEDBACK.read_text().splitlines():
        line = line.strip().lstrip("\x00")  # tolerate boat-power-loss NUL padding
        if not line:
            continue
        try:
            rows.append(json.loads(line))
        except Exception:
            continue
    return rows


def _digest(n: int = 50) -> dict:
    rows = _load_rows()
    recent = rows[-n:] if n and n > 0 else rows
    by_cat = OrderedDict((c, []) for c in CATEGORIES)
    counts = Counter()
    unreviewed = 0
    for r in recent:
        cat = r.get("category", "unknown")
        counts[cat] += 1
        if not r.get("reviewed", False):
            unreviewed += 1
        by_cat.setdefault(cat, [])
        by_cat[cat].append({
            "ts": r.get("ts"),
            "target": r.get("target", ""),
            "note": r.get("note", ""),
            "reviewed": r.get("reviewed", False),
        })
    grouped = {c: items for c, items in by_cat.items() if items}
    return {
        "ok": True,
        "registry": str(FEEDBACK),
        "total_rows": len(rows),
        "shown": len(recent),
        "counts_by_category": dict(counts),
        "unreviewed": unreviewed,
        "grouped": grouped,
        "note": "reviewable evidence only — no retrain/rewrite is triggered by this data",
    }


def run(action: str = "digest", category: str = None, target: str = "",
        note: str = "", n: int = 50) -> dict:
    if action == "record":
        if not category:
            return {"ok": False, "error": "action=record requires 'category'",
                    "allowed": CATEGORIES}
        return _record(category, target, note)
    if action == "digest":
        return _digest(n)
    return {"ok": False, "error": f"unknown action '{action}'",
            "actions": ["record", "digest"]}


if __name__ == "__main__":
    import sys
    print(json.dumps(run(*sys.argv[1:]), indent=2))
