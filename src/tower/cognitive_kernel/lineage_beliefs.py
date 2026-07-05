"""LineageBeliefs — Per-lineage performance computation.

Reads family_tree + worker_pnl. For each parent that has any
descendants, computes:
  · descendants_count
  · descendants_total_pnl
  · descendants_avg_win_rate
  · descendants_outperform_tower_pct  (delta vs tower avg PnL per trader)

Writes the top performers as beliefs the Uncertainty layer can cite.
Beliefs decay normally; reflection can then say things like:
  "Lineage of demo_worker_A is outperforming the tower by 23%
   (confidence 0.74)."
"""

from __future__ import annotations
from dataclasses import dataclass, field, asdict
from typing import Dict, List, Optional, Any
import time

from . import write_registry, append_log, now
from .family_tree import family_tree
from .worker_pnl import worker_pnl
from .uncertainty import uncertainty
from .long_term_memory import long_term_memory


@dataclass
class LineageReading:
    ancestor_id: str
    descendants_count: int
    descendants_total_pnl: float
    descendants_avg_win_rate: Optional[float]
    descendants_outperform_tower_pct: Optional[float]
    notes: List[str] = field(default_factory=list)


def _tower_avg_pnl_per_trader(snap: Dict[str, Any]) -> Optional[float]:
    n = snap.get("worker_count") or 0
    total = snap.get("total_realized_pnl_practice") or 0
    if not n: return None
    # Exclude 'unassigned' bucket if present
    sample = snap.get("rows_sample") or []
    real_rows = [r for r in sample if r.get("worker_id") != "unassigned"]
    real_n = len(real_rows) or n
    if not real_n: return None
    return total / real_n


class LineageBeliefs:

    def compute(self) -> List[LineageReading]:
        ft = family_tree()
        ft.load_from_snapshot()
        pnl = worker_pnl(); pnl.refresh()
        snap = pnl.snapshot()
        rows_by_wid = {r["worker_id"]: r for r in (snap.get("rows_sample") or [])}
        tower_avg = _tower_avg_pnl_per_trader(snap)

        # Find every ancestor (a worker with at least one descendant)
        all_parents = set()
        for e in ft.snapshot().get("children_sample") or []:
            pid = e.get("parent_id")
            if pid:
                all_parents.add(pid)

        readings: List[LineageReading] = []
        for anc in all_parents:
            descendants = ft.descendants_of(anc)
            if not descendants: continue
            total_pnl = 0.0
            wr_acc = 0.0
            wr_n = 0
            for did in descendants:
                r = rows_by_wid.get(did)
                if not r: continue
                total_pnl += float(r.get("realized_pnl") or 0)
                wr = r.get("win_rate")
                if isinstance(wr, (int, float)):
                    wr_acc += float(wr); wr_n += 1
            avg_wr = (wr_acc / wr_n) if wr_n else None
            outperf = None
            if tower_avg and descendants:
                lineage_avg = total_pnl / len(descendants)
                if tower_avg != 0:
                    outperf = (lineage_avg - tower_avg) / abs(tower_avg) * 100.0
            r_obj = LineageReading(
                ancestor_id=anc,
                descendants_count=len(descendants),
                descendants_total_pnl=round(total_pnl, 2),
                descendants_avg_win_rate=(round(avg_wr, 3)
                                              if avg_wr is not None else None),
                descendants_outperform_tower_pct=(round(outperf, 1)
                                                     if outperf is not None else None),
            )
            if r_obj.descendants_outperform_tower_pct is not None \
               and r_obj.descendants_outperform_tower_pct >= 10:
                r_obj.notes.append("strong_lineage")
            readings.append(r_obj)
            # Stamp belief
            uncertainty().assert_(
                key=f"lineage_perf:{anc}",
                statement=(f"Lineage of {anc}: {len(descendants)} "
                            f"descendants; total PnL ${total_pnl:.2f}; "
                            f"outperforming tower by "
                            f"{outperf:.1f}%"
                            if outperf is not None else
                            f"Lineage of {anc}: {len(descendants)} descendants"),
                confidence=0.7 if (outperf is not None and abs(outperf) > 5) else 0.5,
                source="lineage_beliefs",
                half_life_seconds=3 * 86400,
                tags=["lineage", anc],
            )
            long_term_memory().record_episode(
                kind="lineage_reading",
                summary=(f"Lineage {anc}: {len(descendants)} descendants, "
                          f"total PnL ${total_pnl:.2f}, vs tower "
                          f"{(outperf or 0):+.1f}%"),
                tags=["lineage"],
                payload=asdict(r_obj),
            )

        append_log("lineage_beliefs.jsonl", {
            "event": "compute",
            "lineage_count": len(readings),
            "tower_avg_pnl_per_trader": tower_avg,
        })
        return readings

    def persist(self) -> Dict[str, Any]:
        readings = self.compute()
        snap = {
            "ok": True,
            "kind": "cognitive_lineage_beliefs",
            "generated_ts": now(),
            "policy": "Per-lineage performance read-only beliefs. Decay normally.",
            "lineage_count": len(readings),
            "best_lineages": sorted(
                [asdict(r) for r in readings],
                key=lambda r: -(r["descendants_outperform_tower_pct"] or 0),
            )[:10],
            "worst_lineages": sorted(
                [asdict(r) for r in readings],
                key=lambda r: (r["descendants_outperform_tower_pct"] or 0),
            )[:10],
        }
        write_registry("cognitive_lineage_beliefs.json", snap)
        return snap


_LB: Optional[LineageBeliefs] = None


def lineage_beliefs() -> LineageBeliefs:
    global _LB
    if _LB is None:
        _LB = LineageBeliefs()
    return _LB
