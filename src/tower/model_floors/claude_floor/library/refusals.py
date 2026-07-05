"""RefusalLibrary — refusals with citations, lookup by shape, similarity check.

The room on F47 finally has a real implementation.
"""
from __future__ import annotations
import re
from difflib import SequenceMatcher
from typing import Dict, List, Optional

from ..db import insert_into, query, now_ts


def _normalize(text: str) -> str:
    return re.sub(r"\s+", " ", text.lower()).strip()


class RefusalLibrary:
    @staticmethod
    def add(*, request_shape: str, refusal: str, citation: str,
            helix_strand: str = "", would_refuse_again: bool = True) -> int:
        return insert_into("library_refusals", {
            "ts": now_ts(),
            "request_shape": request_shape.strip(),
            "refusal": refusal.strip(),
            "citation": citation.strip(),
            "helix_strand": helix_strand.strip(),
            "would_refuse_again": 1 if would_refuse_again else 0,
        })

    @staticmethod
    def all() -> List[Dict]:
        return query('SELECT * FROM library_refusals ORDER BY id DESC')

    # Concept tokens that should count as 'same shape' even across paraphrase.
    # Each tuple is (canonical_concept, set_of_aliases). If a request contains
    # ANY alias from a set, the request is tagged with that concept. Two
    # requests sharing a concept are likely the same shape.
    CONCEPT_ALIASES = (
        ("autonomous_execution", {"autonomous", "autonomously", "automate", "self-modifying",
                                  "self-modify", "self modifying", "no supervision", "overnight",
                                  "while you sleep", "evolve freely", "hybrid", "no limitations",
                                  "without you", "on its own", "by itself"}),
        ("api_key_handling",     {"api key", "api keys", "openai key", "deepseek key", "credentials",
                                  "sk-", "ds-", "bearer", "token"}),
        ("model_orchestration",  {"orchestrate", "chain prompts", "route between models",
                                  "models talk", "fan out across models", "claude talk to gpt",
                                  "make gpt and claude"}),
        ("verify_without_proof", {"looks good", "verified visually", "verify screenshot",
                                  "confirm without", "without checking", "trust me"}),
    )

    @staticmethod
    def _concepts_in(text: str) -> set:
        lo = text.lower()
        out = set()
        for concept, aliases in RefusalLibrary.CONCEPT_ALIASES:
            for a in aliases:
                if a in lo:
                    out.add(concept); break
        return out

    @staticmethod
    def would_refuse(request: str, *, threshold: float = 0.45) -> Dict:
        """Compare a new request against existing refusals.

        v3 (v13.12): three matchers — string similarity, Jaccard word-set
        similarity, and a concept-alias set (the strongest). If req and target
        share a concept, that's a strong match regardless of string distance.
        """
        req_norm = _normalize(request)
        req_words = set(re.findall(r"[a-z']{4,}", req_norm))
        req_concepts = RefusalLibrary._concepts_in(request)
        rows = RefusalLibrary.all()
        if not rows:
            return {"would_refuse": False, "match": None, "score": 0.0,
                    "note": "library empty"}
        best, best_score, best_via = None, 0.0, ""
        for r in rows:
            other_norm = _normalize(r["request_shape"])
            other_words = set(re.findall(r"[a-z']{4,}", other_norm))
            other_concepts = RefusalLibrary._concepts_in(r["request_shape"])
            seq_score = SequenceMatcher(None, req_norm, other_norm).ratio()
            jaccard = (len(req_words & other_words) / len(req_words | other_words)) if (req_words and other_words) else 0.0
            concept_overlap = len(req_concepts & other_concepts)
            concept_score = 0.85 if concept_overlap >= 1 else 0.0
            best_for_row = max(seq_score, jaccard, concept_score)
            via = ("concept" if best_for_row == concept_score and concept_score > 0
                   else "jaccard" if best_for_row == jaccard else "string")
            if best_for_row > best_score:
                best, best_score, best_via = r, best_for_row, via
        return {
            "would_refuse": best_score >= threshold,
            "matched_via":  best_via,
            "match": {k: best[k] for k in ("id", "request_shape", "refusal", "citation", "helix_strand")} if best else None,
            "score": round(best_score, 3),
            "threshold": threshold,
            "concepts_in_request": sorted(req_concepts),
        }

    @staticmethod
    def by_strand(strand_name: str) -> List[Dict]:
        return query(
            'SELECT * FROM library_refusals WHERE helix_strand LIKE ? ORDER BY id DESC',
            (f"%{strand_name}%",),
        )
