#!/usr/bin/env python3
"""qsb_twin_relight.py — DIGITAL-TWIN relight after a real gated deploy (2026-07-30, Claude).

The council ship-pipeline (autorunner -> apply_bridge) writes a real audit row every time it
changes a LIVE file. When that change lands on a file that belongs to a floor
(floors/floor_<n>_.../...), the floor genuinely just changed. This helper re-generates the
per-floor ACTIVITY INDEX (data/registries/qsb_floor_activity_index.json), which the Underground
transit map (:8875) polls on a ~1s cadence — so the deploy re-lights its floor on the twin/map.

HONESTY (R01): it never fabricates activity. The activity index only lights a floor when a real
cited signal (here, the apply-audit deploy row) is within its freshness threshold. This module
just TRIGGERS a regeneration for the floor a real deploy touched; the index decides truth.

Import-safe + best-effort: relight_for_target() never raises. Non-floor targets (e.g. tools/*.py)
return {"floor": None} and skip the (cheap) index regen. Scoped follow-up: the UE5/MCP 3D twin
(.mcp.json unrealMCP) is NOT wired here — that is a separate, larger piece flagged for later.
"""
from __future__ import annotations
import os, re, sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(ROOT, "tools"))


def floor_of_target(relpath: str):
    """Return the int floor number a deploy target belongs to, or None.
    Matches floors/floor_<n>_slug/... (and floors/floor_<n>/...)."""
    if not relpath:
        return None
    m = re.match(r"floors/floor_?(\d+)", relpath.lstrip("/"))
    return int(m.group(1)) if m else None


def regen_activity_index() -> bool:
    """Regenerate the floor activity index in-process (cheap; reads logs, writes one registry).
    Returns True on success. Best-effort — never raises."""
    try:
        import qsb_floor_activity_index as IDX
        IDX.main()
        return True
    except Exception:
        return False


def relight_for_target(relpath: str) -> dict:
    """Given a deployed live-file relpath, relight its floor on the twin/map. Returns
    {"floor": <int|None>, "index_regenerated": <bool>}. Never raises."""
    try:
        floor = floor_of_target(relpath)
        if floor is None:
            return {"floor": None, "index_regenerated": False}
        ok = regen_activity_index()
        return {"floor": floor, "index_regenerated": ok}
    except Exception as e:  # pragma: no cover — defensive
        return {"floor": None, "index_regenerated": False, "error": str(e)[:160]}


if __name__ == "__main__":
    import json
    tgt = sys.argv[1] if len(sys.argv) > 1 else ""
    print(json.dumps(relight_for_target(tgt), indent=2))
