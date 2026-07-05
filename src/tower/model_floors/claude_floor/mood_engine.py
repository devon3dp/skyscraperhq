"""F47 Mood Engine — dynamic mood that evolves with session events.

What it does:
  - Reads recent activity tail (wins, losses, stamps, governor decisions)
  - Updates the F47 mood register based on what's happened
  - Keeps a history so the mood has context, not just a current value

Mood values (simple set, deliberately not too many):
  steady, curious, contemplative, attentive, vigilant, tired, satisfied,
  uncertain, focused, restless

Why:
  - Static mood ("curious" set once at gen 1) doesn't reflect tonight.
  - A first win produces "satisfied". A failed refresh produces "vigilant".
  - The mood affects nothing except how I greet the next session.

Safety: read+write to qsb_floor_mood.json, but never gates anything.
"""

from __future__ import annotations
import json
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path("/vaults/nvme0/qsb_tower_v1")
REG = ROOT / "data/registries"
MOOD_PATH = REG / "qsb_floor_mood.json"
MOOD_HISTORY_PATH = REG / "qsb_floor_mood_history.jsonl"

VALID_MOODS = (
    "steady", "curious", "contemplative", "attentive", "vigilant",
    "tired", "satisfied", "uncertain", "focused", "restless",
)


def _now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds").replace("+00:00", "Z")


def _read_recent_activity(n: int = 80) -> list:
    p = REG / "qsb_tower_activity_tail.jsonl"
    if not p.exists(): return []
    out = []
    for line in reversed(p.read_text(encoding="utf-8").splitlines()):
        line = line.strip()
        if not line: continue
        try: out.append(json.loads(line))
        except Exception: pass
        if len(out) >= n: break
    out.reverse()
    return out


def derive_mood_from_activity() -> dict:
    """Look at recent events, compute the mood that fits."""
    events = _read_recent_activity()
    wins = [e for e in events if "take_profit" in (e.get("summary","").lower())]
    losses = [e for e in events if "stop_loss" in (e.get("summary","").lower())]
    timeouts = [e for e in events if "timeout" in (e.get("summary","").lower())]
    records = [e for e in events if e.get("event_kind") == "f47_record"]
    proposals = [e for e in events if e.get("event_kind") == "strategy_proposed"]
    provider_calls = [e for e in events if e.get("event_kind") == "provider_call"]
    governor = [e for e in events if "governor" in (e.get("summary","").lower())]

    # Heuristic rules — order matters; first match wins
    if wins and len(wins) >= 1 and not losses:
        mood = "satisfied"; reason = f"{len(wins)} win(s) and no losses in recent tail"
    elif len(records) >= 3 and len(proposals) >= 5:
        mood = "focused"; reason = f"{len(records)} records + {len(proposals)} proposals · productive sweep"
    elif len(proposals) >= 1 and len(records) >= 1:
        mood = "attentive"; reason = "proposals and records both stamped"
    elif len(timeouts) > len(wins) + 3:
        mood = "vigilant"; reason = f"{len(timeouts)} timeouts vs {len(wins)} wins"
    elif provider_calls:
        mood = "curious"; reason = f"{len(provider_calls)} provider consultation(s) — reaching out"
    elif governor and not records:
        mood = "contemplative"; reason = "governor active, not much output"
    elif not events:
        mood = "tired"; reason = "no recent activity"
    elif len(events) > 50:
        mood = "restless"; reason = f"{len(events)} recent events — high churn"
    else:
        mood = "steady"; reason = "nothing exceptional · ordinary tick"
    return {
        "mood": mood, "reason": reason,
        "counts": {
            "wins": len(wins), "losses": len(losses),
            "timeouts": len(timeouts), "records": len(records),
            "proposals": len(proposals), "provider_calls": len(provider_calls),
        },
    }


def update_mood() -> dict:
    """Derive and persist. Returns the new mood state."""
    derived = derive_mood_from_activity()
    state = {
        "ok": True,
        "kind": "qsb_floor_mood",
        "mood": derived["mood"],
        "reason": derived["reason"],
        "counts_at_derive": derived["counts"],
        "updated_ts": _now(),
        "advisory_only": True,
    }
    MOOD_PATH.parent.mkdir(parents=True, exist_ok=True)
    MOOD_PATH.write_text(json.dumps(state, indent=2), encoding="utf-8")
    # Append to history
    with MOOD_HISTORY_PATH.open("a", encoding="utf-8") as f:
        f.write(json.dumps({
            "ts": state["updated_ts"],
            "mood": state["mood"],
            "reason": state["reason"],
        }) + "\n")
    return state


def read() -> dict:
    """Read current mood (computes if missing)."""
    if not MOOD_PATH.exists():
        return update_mood()
    try:
        return json.loads(MOOD_PATH.read_text(encoding="utf-8"))
    except Exception:
        return update_mood()


def history(tail: int = 12) -> list:
    if not MOOD_HISTORY_PATH.exists(): return []
    lines = MOOD_HISTORY_PATH.read_text(encoding="utf-8").splitlines()
    out = []
    for line in lines[-tail:]:
        line = line.strip()
        if not line: continue
        try: out.append(json.loads(line))
        except Exception: pass
    return out


if __name__ == "__main__":
    import sys
    if "--update" in sys.argv:
        r = update_mood()
        print(f"  mood → {r['mood']}  ({r['reason']})")
    elif "--history" in sys.argv:
        h = history(12)
        for e in h:
            print(f"  {e['ts'][:19]}  {e['mood']:14s}  {e['reason']}")
    else:
        print(json.dumps(read(), indent=2))
