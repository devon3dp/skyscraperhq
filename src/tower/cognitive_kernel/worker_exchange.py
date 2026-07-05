"""WorkerKnowledgeExchange — Layer · Cognitive view of worker state.

The Kernel does NOT speak to workers directly (no inter-floor RPC).
This module is a *digest* of the worker scene state registry plus any
voice-narration events, used to surface:

  - which floors have stale workers
  - which workers were recently briefed (and what was briefed)
  - aggregate hum/idle pressure across floors

It writes a "worker exchange" snapshot into working memory so reasoning
and proposals can reference it.
"""

from __future__ import annotations
from dataclasses import dataclass, field, asdict
from typing import Dict, List, Optional
import time

from . import append_log, write_registry, now, load, REG
from .working_memory import blackboard
from .uncertainty import uncertainty


@dataclass
class FloorWorkerDigest:
    floor: str
    worker_count: int
    active_count: int
    idle_count: int
    last_brief_ts: Optional[float] = None
    notes: List[str] = field(default_factory=list)


class WorkerKnowledgeExchange:
    def __init__(self):
        self._last_digest: Dict[str, FloorWorkerDigest] = {}

    def digest(self) -> Dict[str, FloorWorkerDigest]:
        scene = load(REG / "qsb_worker_scene_state.json")
        if not isinstance(scene, dict):
            return {}
        floors = scene.get("floors") or scene.get("floor_summary") or {}
        out: Dict[str, FloorWorkerDigest] = {}
        if isinstance(floors, dict):
            for fname, fdata in floors.items():
                if not isinstance(fdata, dict):
                    continue
                wc = int(fdata.get("worker_count", fdata.get("workers", 0) or 0))
                active = int(fdata.get("active_count", fdata.get("active", 0) or 0))
                idle = int(fdata.get("idle_count", max(0, wc - active)))
                notes: List[str] = []
                if wc and active == 0:
                    notes.append("floor_all_idle")
                if wc == 0:
                    notes.append("floor_vacant")
                out[str(fname)] = FloorWorkerDigest(
                    floor=str(fname), worker_count=wc,
                    active_count=active, idle_count=idle,
                    notes=notes,
                )
        elif isinstance(floors, list):
            for fdata in floors:
                if not isinstance(fdata, dict):
                    continue
                fname = str(fdata.get("floor", fdata.get("name", "?")))
                wc = int(fdata.get("worker_count", fdata.get("workers", 0) or 0))
                active = int(fdata.get("active_count", fdata.get("active", 0) or 0))
                idle = int(fdata.get("idle_count", max(0, wc - active)))
                notes: List[str] = []
                if wc and active == 0:
                    notes.append("floor_all_idle")
                if wc == 0:
                    notes.append("floor_vacant")
                out[fname] = FloorWorkerDigest(
                    floor=fname, worker_count=wc,
                    active_count=active, idle_count=idle,
                    notes=notes,
                )

        # Aggregate metrics
        total = sum(d.worker_count for d in out.values())
        active_total = sum(d.active_count for d in out.values())
        idle_total = sum(d.idle_count for d in out.values())
        idle_ratio = (idle_total / total) if total else 0.0

        # Mirror into working memory
        blackboard().write(
            key="worker_exchange_digest",
            value={"floor_count": len(out),
                   "worker_total": total,
                   "active_total": active_total,
                   "idle_total": idle_total,
                   "idle_ratio": round(idle_ratio, 3)},
            source="qsb_worker_scene_state.json",
            priority=0.45,
            ttl_seconds=900,
            tags=["workers", "scene"],
        )
        uncertainty().assert_(
            key="worker_idle_ratio",
            statement=f"Tower idle ratio ~{idle_ratio:.2f} across {len(out)} floors ({active_total}/{total} active).",
            confidence=0.7,
            source="worker_exchange",
            half_life_seconds=600.0,
            tags=["workers"],
        )

        self._last_digest = out
        append_log("worker_exchange.jsonl", {
            "event": "digest", "floor_count": len(out),
            "worker_total": total, "idle_ratio": round(idle_ratio, 3),
        })
        return out

    def persist(self) -> None:
        write_registry("cognitive_worker_exchange.json", {
            "ok": True, "kind": "cognitive_worker_exchange",
            "generated_ts": now(),
            "policy": "Read-only digest. Kernel does not direct workers; the orchestrator/operator does.",
            "floor_count": len(self._last_digest),
            "digest": {k: asdict(v) for k, v in self._last_digest.items()},
        })


_WORKER_EX: Optional[WorkerKnowledgeExchange] = None


def worker_exchange() -> WorkerKnowledgeExchange:
    global _WORKER_EX
    if _WORKER_EX is None:
        _WORKER_EX = WorkerKnowledgeExchange()
    return _WORKER_EX
