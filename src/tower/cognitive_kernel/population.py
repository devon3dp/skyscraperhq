"""Population — Tower-wide worker cap and headroom.

Reads the workforce registry for the current canonical worker count.
Adds pending child grants from family_tree to compute "effective"
population (current + pending births).

Cap is 5,000 right now; the kernel will refuse to propose new child
grants if effective >= CAP. The cap is upgradable later by operator.
"""

from __future__ import annotations
from typing import Dict, Optional, Any
import time

from . import write_registry, append_log, now, load, REG
from .family_tree import family_tree


POPULATION_CAP = 5000


def _read_current_worker_count() -> int:
    # Try several known workforce registries to be resilient
    candidates = [
        "qsb_workforce_v1.json",
        "qsb_worker_truth.json",
        "qsb_worker_scene_state.json",
        "qsb_workforce_v1_summary.json",
    ]
    for name in candidates:
        d = load(REG / name)
        if not isinstance(d, dict):
            continue
        for k in ("total_canonical", "total_workers",
                  "worker_count", "workers", "total"):
            v = d.get(k)
            if isinstance(v, int):
                return v
        # Some registries put it under counts/.../total
        counts = d.get("counts") or {}
        for k in ("total_canonical", "total_workers", "total"):
            v = counts.get(k)
            if isinstance(v, int):
                return v
    return 0


def _pending_births() -> int:
    snap = family_tree().snapshot()
    children = snap.get("children_sample") or []
    return sum(1 for c in children
               if c.get("status") in ("pending_birth", "confirmed_birth"))


def population_snapshot() -> Dict[str, Any]:
    current = _read_current_worker_count()
    pending = _pending_births()
    effective = current + pending
    headroom = max(0, POPULATION_CAP - effective)
    return {
        "ok": True,
        "kind": "cognitive_population_status",
        "generated_ts": now(),
        "policy": ("Cap = 5,000. Refuses new child grants once "
                    "effective_population >= cap. Operator can lift cap "
                    "by editing POPULATION_CAP."),
        "cap": POPULATION_CAP,
        "current_worker_count": current,
        "pending_births": pending,
        "effective_population": effective,
        "headroom": headroom,
        "at_cap": effective >= POPULATION_CAP,
        "near_cap": (effective >= POPULATION_CAP - 100
                      and effective < POPULATION_CAP),
    }


def has_headroom_for_grant(n: int = 1) -> bool:
    s = population_snapshot()
    ok = s["headroom"] >= n
    if not ok:
        append_log("population.jsonl", {
            "event": "grant_refused_at_cap",
            "requested": n, "headroom": s["headroom"],
            "effective": s["effective_population"], "cap": s["cap"],
        })
    return ok


def persist() -> Dict[str, Any]:
    snap = population_snapshot()
    write_registry("cognitive_population_status.json", snap)
    return snap
