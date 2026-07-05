"""CausalPhaseModel — Layer · How Claude phases cause downstream effects.

Each Claude phase (recorded in eqsb_phase_history.jsonl) tends to
produce a *kind* of downstream effect:
  - registry additions
  - new topic handlers
  - new floors brought online
  - guardian-related changes
  - kernel-chat behavior changes

This module builds a coarse causal graph:

    phase_kind  →  observed_effect_kind  →  count, last_seen_ts

And uses it to predict, for the most recent phase, what kinds of
downstream effects to expect to see in the next N hours. If those
effects don't appear, it files a curiosity item ("did phase X actually
land its expected effect?").
"""

from __future__ import annotations
from dataclasses import dataclass, field, asdict
from typing import Dict, List, Optional, Tuple
import json
import time

from . import append_log, write_registry, now, ROOT, REG, load, COG_LOG
from .curiosity import curiosity
from .long_term_memory import long_term_memory


@dataclass
class CausalLink:
    phase_kind: str
    effect_kind: str
    count: int = 0
    last_seen_ts: float = 0.0
    confidence: float = 0.5


PHASE_HISTORY_PATH = ROOT / "data/logs/eqsb_phase_history.jsonl"


class CausalPhaseModel:
    def __init__(self):
        self._links: Dict[Tuple[str, str], CausalLink] = {}
        self._last_predictions: List[dict] = []

    # ── ingestion ──────────────────────────────────────────────────
    def ingest_phase_history(self, tail_lines: int = 200) -> int:
        """Walk recent phase history and build causal links."""
        if not PHASE_HISTORY_PATH.exists():
            return 0
        try:
            with PHASE_HISTORY_PATH.open("r", encoding="utf-8") as f:
                lines = f.readlines()[-tail_lines:]
        except Exception:
            return 0
        added = 0
        for line in lines:
            try:
                rec = json.loads(line)
            except Exception:
                continue
            phase_kind = self._phase_kind_of(rec)
            effects = rec.get("effects") or rec.get("effect_kinds") or []
            if isinstance(effects, str):
                effects = [effects]
            if not isinstance(effects, list):
                continue
            for ek in effects:
                if not isinstance(ek, str):
                    continue
                key = (phase_kind, ek)
                link = self._links.get(key) or CausalLink(
                    phase_kind=phase_kind, effect_kind=ek,
                )
                link.count += 1
                link.last_seen_ts = time.time()
                link.confidence = min(0.95, 0.4 + 0.05 * link.count)
                self._links[key] = link
                added += 1
        append_log("causal_phase_model.jsonl",
                   {"event": "ingest", "links_added_or_updated": added})
        return added

    @staticmethod
    def _phase_kind_of(rec: dict) -> str:
        p = (rec.get("phase") or rec.get("title") or "").lower()
        if "kernel" in p: return "kernel_change"
        if "godot" in p:  return "cockpit_change"
        if "trading" in p or "oanda" in p or "binance" in p: return "trading_change"
        if "openclaw" in p: return "routing_change"
        if "ml" in p or "rl" in p: return "ml_lab_change"
        if "dashboard" in p: return "dashboard_change"
        if "worker" in p: return "worker_change"
        return "other_change"

    # ── prediction ─────────────────────────────────────────────────
    def predict_for_latest_phase(self) -> List[dict]:
        last = load(REG / "eqsb_last_claude_change_summary.json")
        if not isinstance(last, dict):
            return []
        phase_kind = self._phase_kind_of(last)
        # Pick the most-likely effect kinds for this phase kind
        candidates = [l for l in self._links.values()
                      if l.phase_kind == phase_kind]
        candidates.sort(key=lambda l: -l.count)
        preds = [{"effect_kind": l.effect_kind,
                  "support_count": l.count,
                  "confidence": l.confidence}
                 for l in candidates[:5]]
        self._last_predictions = preds
        if preds:
            long_term_memory().record_episode(
                kind="causal_prediction_filed",
                summary=(f"Phase '{last.get('phase')}' (kind={phase_kind}) "
                         f"predicted to produce: "
                         f"{[p['effect_kind'] for p in preds]}"),
                tags=["causal"],
                payload={"phase": last.get("phase"),
                         "phase_kind": phase_kind,
                         "predictions": preds},
            )
            # File curiosity: did the predicted effects actually appear?
            for p in preds[:3]:
                curiosity().add(
                    question=(f"verify predicted effect '{p['effect_kind']}' "
                              f"appeared after phase '{last.get('phase')}'"),
                    source="causal_phase_model",
                    priority=0.5,
                )
        return preds

    def persist(self) -> None:
        write_registry("cognitive_causal_phase_model.json", {
            "ok": True, "kind": "cognitive_causal_phase_model",
            "generated_ts": now(),
            "link_count": len(self._links),
            "top_links": [asdict(l) for l in
                           sorted(self._links.values(),
                                  key=lambda l: -l.count)[:30]],
            "last_predictions": self._last_predictions,
        })


_CAUSAL: Optional[CausalPhaseModel] = None


def causal_phase_model() -> CausalPhaseModel:
    global _CAUSAL
    if _CAUSAL is None:
        _CAUSAL = CausalPhaseModel()
    return _CAUSAL
