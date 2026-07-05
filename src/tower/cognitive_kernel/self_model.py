"""SelfModel — Layer 5 · What the Kernel knows about itself.

Tracks:
  - capabilities: topics it can answer, registries it can read
  - dependencies: registries/services it needs
  - known gaps: things that fall through (fed by IdentityGate logs)
  - last_upgrade_ts + last_upgrade_phase
  - uncertainties: per-belief confidence (from Uncertainty tracker)
"""

from __future__ import annotations
from pathlib import Path
from typing import Dict, List, Optional, Set
import json
import time

from . import COG_REG, COG_LOG, ROOT, REG, write_registry, append_log, load


class SelfModel:
    def __init__(self):
        # Topics the topic table knows
        self.known_topics: Set[str] = set()
        # Registry paths the cognition has been observed reading
        self.known_registries: Set[str] = set()
        # Topics that triggered the safety-net (gaps)
        self.known_gaps: List[str] = []
        # Last Claude upgrade we noticed
        self.last_upgrade_phase: Optional[str] = None
        self.last_upgrade_ts: Optional[str] = None
        # Cross-reference to the uncertainty tracker
        self.uncertainty_summary: Dict[str, float] = {}

    # ── discovery ──────────────────────────────────────────────────
    def discover_topics_from_dialogue_adapter(self) -> int:
        """Walk kernel_dialogue_adapter.py to count topic names."""
        p = ROOT / "src/tower/kernel_dialogue_adapter.py"
        if not p.exists():
            return 0
        topics = set()
        try:
            text = p.read_text(encoding="utf-8")
            import re
            for m in re.findall(r'\("([a-z_0-9]+)",\s*\(', text):
                topics.add(m)
        except Exception:
            pass
        self.known_topics |= topics
        return len(topics)

    def discover_registries_from_disk(self) -> int:
        """Scan data/registries for all qsb_*.json + eqsb_*.json."""
        count = 0
        try:
            for p in REG.glob("qsb_*.json"):
                self.known_registries.add(str(p.relative_to(ROOT)))
                count += 1
            for p in REG.glob("eqsb_*.json"):
                self.known_registries.add(str(p.relative_to(ROOT)))
                count += 1
        except Exception:
            pass
        return count

    def absorb_gap_log(self) -> int:
        """Read the identity-gate safety-net log and track gaps."""
        p = COG_LOG / "identity_gate_safetynet.jsonl"
        gaps_added = 0
        if not p.exists():
            return 0
        try:
            with p.open("r", encoding="utf-8") as f:
                for line in f.readlines()[-200:]:
                    rec = json.loads(line)
                    intent = rec.get("intent", "?")
                    if intent not in self.known_gaps:
                        self.known_gaps.append(intent)
                        gaps_added += 1
        except Exception:
            pass
        return gaps_added

    def absorb_last_claude_change(self) -> None:
        """Read eqsb_last_claude_change_summary.json."""
        d = load(REG / "eqsb_last_claude_change_summary.json")
        if isinstance(d, dict):
            self.last_upgrade_phase = d.get("phase")
            self.last_upgrade_ts = d.get("generated_ts")

    # ── output ─────────────────────────────────────────────────────
    def snapshot(self) -> dict:
        return {
            "ok": True,
            "kind": "cognitive_self_model",
            "generated_ts": time.strftime("%Y-%m-%dT%H:%M:%S+00:00", time.gmtime()),
            "topic_count": len(self.known_topics),
            "topics_known": sorted(self.known_topics),
            "registry_count": len(self.known_registries),
            "registries_known_sample": sorted(self.known_registries)[:30],
            "gap_count": len(self.known_gaps),
            "known_gaps": self.known_gaps[:30],
            "last_upgrade_phase": self.last_upgrade_phase,
            "last_upgrade_ts": self.last_upgrade_ts,
            "uncertainty_summary": self.uncertainty_summary,
            "honest_self_assessment": {
                "i_can": [
                    "answer topic-table questions from registries",
                    "cite source paths in my answers",
                    "log safety-net misses for later upgrade",
                    "refuse execution intents",
                ],
                "i_cannot": [
                    "execute trades or any action",
                    "modify my own code",
                    "unlock safety gates",
                    "guarantee correctness without registry citation",
                ],
                "i_am_uncertain_about": [
                    "questions outside the topic table",
                    "registries that have not been refreshed recently",
                    "future Claude phase outcomes",
                ],
            },
        }

    def refresh_all(self) -> dict:
        self.discover_topics_from_dialogue_adapter()
        self.discover_registries_from_disk()
        self.absorb_gap_log()
        self.absorb_last_claude_change()
        snap = self.snapshot()
        write_registry("cognitive_self_model.json", snap)
        return snap


_SELF_MODEL: Optional[SelfModel] = None


def self_model() -> SelfModel:
    global _SELF_MODEL
    if _SELF_MODEL is None:
        _SELF_MODEL = SelfModel()
    return _SELF_MODEL
