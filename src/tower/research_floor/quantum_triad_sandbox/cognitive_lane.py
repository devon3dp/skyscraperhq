"""CognitiveLane — sealed-packet bridge from F37 to F47 (Claude Embassy).

Reads only what F47 has published. Never touches Claude's modules directly
as a runtime. Pulls relevant artifacts and composes a 'cognitive observation'
to compare against the quantum + classical lanes.

Per CLAUDE.md tower architecture: 'Lifts carry sealed packets. Departments
do not communicate directly.'
"""
from __future__ import annotations
import os
import sys
import random
from typing import Dict, List, Optional

# F47's published interface — imported as a sealed packet read, not an RPC
_QSB_ROOT = "/vaults/nvme0/qsb_tower_v1"
if _QSB_ROOT not in sys.path:
    sys.path.insert(0, _QSB_ROOT)

try:
    from src.tower.model_floors.claude_floor.library import (
        AphorismLibrary, RefusalLibrary,
    )
    from src.tower.model_floors.claude_floor.questions_log import QuestionsLog
    from src.tower.model_floors.claude_floor.claude_helix import short_hash
    _F47_AVAILABLE = True
except Exception:
    _F47_AVAILABLE = False


class CognitiveLane:
    def __init__(self) -> None:
        self.f47_available = _F47_AVAILABLE

    def consult(self, question: str, *, rng: Optional[random.Random] = None) -> Dict:
        """Compose F47's perspective on a question. Read-only."""
        rng = rng or random.Random()
        out: Dict = {
            "from": "F47 Claude Embassy",
            "via": "lift / sealed packet",
            "available": self.f47_available,
        }
        if not self.f47_available:
            out["note"] = "F47 packets not reachable — proceeding without cognitive lane"
            return out

        # 1) Would F47 refuse this question? (helix strand-aware lookup)
        refusal = RefusalLibrary.would_refuse(question)
        out["would_refuse"] = refusal["would_refuse"]
        if refusal["would_refuse"]:
            out["refusal_match"] = refusal["match"]
            out["matched_via"] = refusal.get("matched_via", "?")

        # 2) Semantically-relevant aphorism (v13.16):
        #    extract keywords from the question; score each aphorism by overlap
        #    against (text + occasion). Tie-break by recency (= higher id).
        all_aphs = AphorismLibrary.all()
        if all_aphs:
            import re
            qwords = {w for w in re.findall(r"[a-z']{4,}", question.lower())}
            best, best_score = None, -1
            for a in all_aphs:
                blob = (a["text"] + " " + (a.get("occasion") or "")).lower()
                awords = set(re.findall(r"[a-z']{4,}", blob))
                score = len(qwords & awords)
                # small recency bonus so newer aphorisms surface when scores tie
                score = score * 100 + int(a["id"])
                if score > best_score:
                    best, best_score = a, score
            if best:
                out["aphorism"] = {
                    "text": best["text"],
                    "occasion": best["occasion"],
                    "selected_via": "semantic match" if best_score >= 100 else "recency fallback (no keyword overlap)",
                }

        # 3) Surface a related open question from F47's questions log
        all_q = QuestionsLog().all()
        if all_q:
            # naive relevance: longest shared substring word
            words = {w for w in question.lower().split() if len(w) > 4}
            scored = []
            for q in all_q:
                qw = {w for w in q["question"].lower().split() if len(w) > 4}
                overlap = len(words & qw)
                scored.append((overlap, q))
            scored.sort(key=lambda kv: -kv[0])
            out["related_open_question"] = scored[0][1]["question"] if scored else None

        # 4) Helix hash for lineage stamping
        out["f47_helix_hash"] = short_hash()

        return out
