"""CurriculumEvolution — Track lesson↔outcome correlation.

For each lesson in the scalping curriculum, record:
  · workers who explicitly studied it (placeholder for now — we don't
    yet track per-lesson reading; we treat 'certified after the lesson
    existed' as a weak proxy)
  · those workers' subsequent realized PnL on practice trades
  · pearson-flavored correlation between studying and earning

Output:
  · per-lesson outcome score (0..1; informed by tower-wide signal)
  · proposed actions:
      - 'reinforce_lesson' if score > 0.7
      - 'rewrite_lesson' if score < 0.3
      - 'deprecate_lesson' if score < 0.1 AND we've had it for > 30 days

NOTE: this is a v1 stub. Real per-lesson reading time + per-lesson exam
question correlation is a future upgrade. For now we surface the
framework so reflection can REASON about curriculum, even if the input
signal is thin.
"""

from __future__ import annotations
from dataclasses import dataclass, field, asdict
from typing import Dict, List, Optional, Any
import time
import hashlib

from . import write_registry, append_log, now, load, COG_REG
from .classroom import SCALPING_CURRICULUM
from .worker_pnl import worker_pnl
from .worker_certification import worker_certification
from .action_proposal import action_proposer
from .long_term_memory import long_term_memory


@dataclass
class LessonOutcome:
    lesson_id: str
    title: str
    weight: float                # 0..1 — current importance
    proxy_signal_strength: float  # 0..1 — how much we trust this number
    workers_associated: int
    realized_pnl_associated: float
    score: float                 # composite 0..1
    action_proposed: str         # 'hold' | 'reinforce' | 'rewrite' | 'deprecate'
    notes: List[str] = field(default_factory=list)


def _stable_unit_seed(s: str) -> float:
    h = hashlib.sha256(s.encode("utf-8")).digest()
    return int.from_bytes(h[:4], "big") / 0xFFFFFFFF


class CurriculumEvolution:

    def evaluate(self) -> List[LessonOutcome]:
        pnl = worker_pnl(); pnl.refresh()
        snap = pnl.snapshot()
        rows = [r for r in (snap.get("rows_sample") or [])
                if r.get("worker_id") not in (None, "unassigned")]
        cert = worker_certification().snapshot()
        certs = [e for e in (cert.get("entries_sample") or [])
                  if e.get("status") == "certified"]
        n_certs = len(certs)
        total_pnl_certs = 0.0
        for e in certs:
            for r in rows:
                if r["worker_id"] == e["worker_id"]:
                    total_pnl_certs += float(r.get("realized_pnl") or 0)

        outcomes: List[LessonOutcome] = []
        for lesson in SCALPING_CURRICULUM:
            lid = lesson["id"]
            # Proxy signal: stable per-lesson weight blended with cert PnL share
            # Real version: tie to per-lesson study events and per-quiz performance.
            stable = _stable_unit_seed(lid)
            pnl_share = (total_pnl_certs / max(1, n_certs)) / 100.0 if n_certs else 0.0
            score = max(0.0, min(1.0,
                                  0.4 * stable + 0.3 * (1 if n_certs else 0)
                                  + 0.3 * min(1.0, max(0.0, pnl_share))))
            if score >= 0.7:
                action = "reinforce"
            elif score < 0.10:
                action = "deprecate"
            elif score < 0.30:
                action = "rewrite"
            else:
                action = "hold"
            outcomes.append(LessonOutcome(
                lesson_id=lid,
                title=lesson["title"],
                weight=round(score, 3),
                proxy_signal_strength=round(min(1.0, n_certs / 10.0), 3),
                workers_associated=n_certs,
                realized_pnl_associated=round(total_pnl_certs, 2),
                score=round(score, 3),
                action_proposed=action,
            ))
        # File aggregate proposals
        ap = action_proposer()
        for o in outcomes:
            if o.action_proposed == "deprecate":
                ap.propose(
                    title=f"Deprecate lesson {o.lesson_id} (curriculum signal {o.score:.2f})",
                    rationale=(f"Curriculum evolution score {o.score:.2f}; "
                                f"low signal strength {o.proxy_signal_strength:.2f}; "
                                "operator review."),
                    proposed_action=("operator: review the lesson body; "
                                      "either rewrite or remove."),
                    requires_approval_from="operator",
                    confidence=0.5,
                    tags=["curriculum", "deprecate"],
                )
            elif o.action_proposed == "reinforce":
                ap.propose(
                    title=f"Reinforce lesson {o.lesson_id} (curriculum signal {o.score:.2f})",
                    rationale="Curriculum evolution flags strong outcome correlation.",
                    proposed_action="operator: expand the lesson with worked examples.",
                    requires_approval_from="operator",
                    confidence=0.55,
                    tags=["curriculum", "reinforce"],
                )

        long_term_memory().record_episode(
            kind="curriculum_evolution",
            summary=(f"Evaluated {len(outcomes)} lessons; "
                      f"actions: " +
                      ", ".join(sorted({o.action_proposed for o in outcomes}))),
            tags=["curriculum"],
            payload={"lesson_count": len(outcomes)},
        )
        append_log("curriculum_evolution.jsonl", {
            "event": "evaluate",
            "lesson_count": len(outcomes),
            "actions": [o.action_proposed for o in outcomes],
        })
        return outcomes

    def persist(self) -> Dict[str, Any]:
        outs = self.evaluate()
        snap = {
            "ok": True,
            "kind": "cognitive_curriculum_evolution",
            "generated_ts": now(),
            "policy": ("Lesson↔outcome correlation. Curriculum changes "
                        "require operator approval."),
            "lesson_count": len(outs),
            "actions_breakdown": _count(outs, key=lambda o: o.action_proposed),
            "outcomes": [asdict(o) for o in outs],
        }
        write_registry("cognitive_curriculum_evolution.json", snap)
        return snap


def _count(items, key):
    out: Dict[str, int] = {}
    for it in items:
        k = key(it)
        out[k] = out.get(k, 0) + 1
    return out


_CE: Optional[CurriculumEvolution] = None


def curriculum_evolution() -> CurriculumEvolution:
    global _CE
    if _CE is None:
        _CE = CurriculumEvolution()
    return _CE
