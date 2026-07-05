"""UpgradeAssimilation — Layer · Make Claude's commits reflect inward.

When a Claude phase lands new modules / topic handlers / registries, the
Kernel previously had to be told. This module *notices* recent commits
by polling:

  - eqsb_last_claude_change_summary.json
  - eqsb_claude_changes.jsonl  (full history)

And then:

  1. Adds new topics to SelfModel's known_topics set
  2. Adds new registries to SelfModel's known_registries set
  3. Files curiosity items if a phase introduced terms the topic table
     hasn't yet adopted ("kernel_chat_should_now_answer_what_X_is")
  4. Increments the "phases_assimilated" count
"""

from __future__ import annotations
from dataclasses import dataclass, field, asdict
from pathlib import Path
from typing import Dict, List, Optional, Set
import json
import time
import re

from . import append_log, write_registry, now, load, REG, ROOT
from .self_model import self_model
from .curiosity import curiosity
from .long_term_memory import long_term_memory


@dataclass
class AssimilationRecord:
    phase: str
    seen_ts: float
    new_topics: List[str] = field(default_factory=list)
    new_registries: List[str] = field(default_factory=list)
    new_curiosity_items: List[str] = field(default_factory=list)


class UpgradeAssimilator:
    def __init__(self):
        self._assimilated_phases: Set[str] = set()
        self._records: List[AssimilationRecord] = []

    def assimilate_once(self) -> Optional[AssimilationRecord]:
        last = load(REG / "eqsb_last_claude_change_summary.json")
        if not isinstance(last, dict):
            return None
        phase = last.get("phase")
        if not phase or phase in self._assimilated_phases:
            return None

        sm = self_model()
        cur = curiosity()
        before_topics = set(sm.known_topics)
        before_regs = set(sm.known_registries)
        sm.discover_topics_from_dialogue_adapter()
        sm.discover_registries_from_disk()
        new_topics = sorted(sm.known_topics - before_topics)
        new_regs = sorted(sm.known_registries - before_regs)

        # File a curiosity item if the phase introduced terms not in the topic table
        intro_terms = self._extract_terms_from_summary(last)
        missing_terms = [t for t in intro_terms if t not in sm.known_topics]
        new_cur = []
        for t in missing_terms[:8]:
            cur.add(
                question=f"add topic handler for new phase term: {t}",
                source="upgrade_assimilation",
                priority=0.55,
            )
            new_cur.append(t)

        rec = AssimilationRecord(
            phase=phase, seen_ts=time.time(),
            new_topics=new_topics, new_registries=new_regs,
            new_curiosity_items=new_cur,
        )
        self._records.append(rec)
        self._assimilated_phases.add(phase)
        long_term_memory().record_episode(
            kind="claude_phase_assimilated",
            summary=f"Assimilated phase: {phase} (+{len(new_topics)} topics, +{len(new_regs)} registries)",
            tags=["upgrade_assimilation"],
            payload=asdict(rec),
        )
        append_log("upgrade_assimilation.jsonl", asdict(rec))
        return rec

    @staticmethod
    def _extract_terms_from_summary(summary: dict) -> List[str]:
        """Yank candidate term names out of a phase summary."""
        text_bits: List[str] = []
        for k in ("title", "description", "phase"):
            v = summary.get(k)
            if isinstance(v, str):
                text_bits.append(v)
        files = summary.get("files_changed") or summary.get("files") or []
        if isinstance(files, list):
            for f in files:
                if isinstance(f, str):
                    text_bits.append(Path(f).stem)
        all_text = " ".join(text_bits).lower()
        # Heuristic: identifier-like words 4+ chars, not common verbs
        STOP = {"phase", "files", "change", "kernel", "update", "build", "fix",
                "add", "the", "and", "for", "with", "from", "into", "this",
                "module", "registry", "summary", "title", "description"}
        out: List[str] = []
        for m in re.findall(r"[a-z][a-z0-9_]{3,}", all_text):
            if m in STOP:
                continue
            if m not in out:
                out.append(m)
            if len(out) >= 25:
                break
        return out

    def persist(self) -> None:
        write_registry("cognitive_upgrade_assimilation.json", {
            "ok": True, "kind": "cognitive_upgrade_assimilation",
            "generated_ts": now(),
            "assimilated_phase_count": len(self._assimilated_phases),
            "assimilated_phases": sorted(self._assimilated_phases),
            "recent_records": [asdict(r) for r in self._records[-15:]],
        })


_ASSIMILATOR: Optional[UpgradeAssimilator] = None


def upgrade_assimilator() -> UpgradeAssimilator:
    global _ASSIMILATOR
    if _ASSIMILATOR is None:
        _ASSIMILATOR = UpgradeAssimilator()
    return _ASSIMILATOR
