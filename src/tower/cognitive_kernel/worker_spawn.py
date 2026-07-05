"""WorkerSpawn — Promote pending_birth children into the workforce registry.

The Kernel writes lineage edges into cognitive_family_tree.json. A child
with status='pending_birth' is a promise — the Kernel says "this worker
exists now in our lineage records". But the actual workforce registry
(qsb_workforce_v1.json or whatever the canonical sheet is) is OUTSIDE
the cognitive namespace.

This module reads pending_birth children and writes a workforce-spawn
roster. The actual workforce-registry mutation is conservative: we
write to a NEW registry qsb_workforce_pending_births.json so the
operator can review every spawn before it's committed to the canonical
registry. (The canonical workforce registry is treated as
operator-owned; we do not edit it from cognition.)

Each pending birth carries:
  · child_id (from family_tree)
  · parent_id, grant_id, inherited_gene
  · spawn_status: pending_birth → roster_written → operator_committed
  · operator_decision_at: timestamp once operator commits or declines
"""

from __future__ import annotations
from dataclasses import dataclass, field, asdict
from typing import Dict, List, Optional, Any
import json
import time

from . import REG, write_registry, append_log, now
from .family_tree import family_tree


PENDING_ROSTER_REGISTRY = "qsb_workforce_pending_births.json"


@dataclass
class PendingBirth:
    child_id: str
    parent_id: str
    grant_id: str
    inherited_gene: Optional[Dict[str, Any]]
    spawn_status: str       # pending_birth | roster_written | operator_committed | operator_declined
    family_tree_status: str
    granted_ts: float
    proposed_workforce_role: str
    proposed_floor_assignment: str
    notes: List[str] = field(default_factory=list)


def _role_for_gene(gene: Optional[Dict[str, Any]]) -> str:
    if not gene: return "general_apprentice"
    style = (gene.get("style") or "").lower()
    if style == "scalp": return "scalper_apprentice"
    if style == "trend": return "trend_apprentice"
    if style == "mean_revert": return "mean_revert_apprentice"
    return "general_apprentice"


def _floor_for_gene(gene: Optional[Dict[str, Any]]) -> str:
    # Default to Floor 25 recruitment for classroom-first lifecycle.
    if not gene: return "floor_25_worker_recruitment"
    fam = (gene.get("family") or "").lower()
    if fam.startswith("fx") or fam == "metals":
        return "floor_25_worker_recruitment"   # graduates to Floor 41 after cert
    return "floor_25_worker_recruitment"


class WorkerSpawn:

    def __init__(self):
        # Track which children we've already written to the roster so we
        # don't re-emit them every tick.
        self._written: Dict[str, PendingBirth] = {}

    def collect_pending(self) -> List[PendingBirth]:
        ft = family_tree()
        ft.load_from_snapshot()
        snap = ft.snapshot()
        out: List[PendingBirth] = []
        for e in snap.get("children_sample") or []:
            cid = e.get("child_id")
            if not cid: continue
            ft_status = e.get("status", "pending_birth")
            # Only newly-pending OR newly-confirmed births
            if ft_status not in ("pending_birth", "confirmed_birth"):
                continue
            if cid in self._written:
                continue
            pb = PendingBirth(
                child_id=cid,
                parent_id=e.get("parent_id", "?"),
                grant_id=e.get("grant_id", "?"),
                inherited_gene=e.get("inherited_gene"),
                spawn_status="pending_birth",
                family_tree_status=ft_status,
                granted_ts=float(e.get("granted_ts") or 0),
                proposed_workforce_role=_role_for_gene(e.get("inherited_gene")),
                proposed_floor_assignment=_floor_for_gene(e.get("inherited_gene")),
                notes=[],
            )
            self._written[cid] = pb
            out.append(pb)
        return out

    def write_roster(self) -> Dict[str, Any]:
        pendings = list(self._written.values())
        # Read the existing roster registry so operator-committed decisions
        # are preserved across spawn rounds.
        path = REG / PENDING_ROSTER_REGISTRY
        existing: Dict[str, Any] = {}
        if path.exists():
            try:
                existing = json.loads(path.read_text(encoding="utf-8"))
            except Exception:
                existing = {}
        # Merge: keep existing operator decisions
        prev_rows = {r.get("child_id"): r for r in
                      (existing.get("pending_births") or [])
                      if isinstance(r, dict)}
        merged: List[Dict[str, Any]] = []
        for pb in pendings:
            prior = prev_rows.get(pb.child_id)
            row = asdict(pb)
            if prior:
                # Preserve operator decisions made out-of-band
                for k in ("spawn_status", "operator_decision_at", "notes"):
                    if k in prior:
                        row[k] = prior[k]
            merged.append(row)
        # Also include any prior rows the Kernel does NOT currently see
        # (e.g., family_tree was wiped but operator wants to keep history)
        cur_ids = {pb.child_id for pb in pendings}
        for cid, prior in prev_rows.items():
            if cid not in cur_ids:
                merged.append(prior)
        payload = {
            "ok": True,
            "kind": "qsb_workforce_pending_births",
            "generated_ts": now(),
            "policy": (
                "Pending-birth roster. Kernel writes the candidate spawn "
                "list. Operator commits each one into the canonical "
                "workforce registry via qsb_spawn.py CLI."
            ),
            "pending_count": len(merged),
            "pending_births": merged,
        }
        path.write_text(json.dumps(payload, indent=2), encoding="utf-8")
        append_log("worker_spawn.jsonl", {
            "event": "write_roster",
            "pending_count": len(merged),
        })
        return payload

    def snapshot(self) -> Dict[str, Any]:
        return {
            "ok": True,
            "kind": "cognitive_worker_spawn_state",
            "generated_ts": now(),
            "policy": "Mirrors qsb_workforce_pending_births.json for chat / dashboard.",
            "pending_count": len(self._written),
            "pending_births": [asdict(pb) for pb in self._written.values()],
        }

    def persist(self) -> Dict[str, Any]:
        snap = self.snapshot()
        write_registry("cognitive_worker_spawn_state.json", snap)
        return snap


_SPAWN: Optional[WorkerSpawn] = None


def worker_spawn() -> WorkerSpawn:
    global _SPAWN
    if _SPAWN is None:
        _SPAWN = WorkerSpawn()
    return _SPAWN
