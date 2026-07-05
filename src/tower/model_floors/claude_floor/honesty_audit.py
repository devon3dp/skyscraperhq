"""HonestyAudit — scan recent text for hedges, unsupported confidence,
missing citations. Reports rates. The point is: when the rates drift,
I should notice before the operator does.
"""
from __future__ import annotations
import json
import os
import re
import datetime
from typing import Dict, List

HEDGE_WORDS = {
    "probably","likely","maybe","might","could","perhaps","seems","appears",
    "i think","i believe","i suspect","arguably","sort of","kind of",
}
CONFIDENCE_WORDS = {
    "clearly","obviously","definitely","certainly","of course","surely",
    "without doubt","always","never","just","simply",
}
CITATION_HINTS = {".gd",".py",".sh",".tscn",".json",".md","line ", "file ", "registry"}


class HonestyAudit:
    @staticmethod
    def audit_text(text: str) -> Dict[str, float]:
        if not text:
            return {"chars": 0, "hedge_rate": 0.0, "confidence_rate": 0.0,
                    "citation_density": 0.0, "claim_count": 0}
        lo = text.lower()
        words = re.findall(r"[a-zA-Z][a-zA-Z']*", lo)
        n = max(1, len(words))
        hedge_n = sum(1 for w in words if w in HEDGE_WORDS)
        # phrase hedges
        for phrase in ("i think","i believe","i suspect","sort of","kind of","of course","without doubt"):
            hedge_n += lo.count(phrase)
        confidence_n = sum(1 for w in words if w in CONFIDENCE_WORDS)
        citation_n = sum(lo.count(c) for c in CITATION_HINTS)
        # rough "claim" count: sentences with a verb after a noun, approximated by sentence-ish splits
        claims = re.split(r"[.!?]+", text)
        claim_count = sum(1 for c in claims if len(c.strip().split()) >= 5)
        return {
            "chars": len(text),
            "words": n,
            "hedge_rate": round(hedge_n / max(1, n), 4),
            "confidence_rate": round(confidence_n / max(1, n), 4),
            "citation_density": round(citation_n / max(1, n), 4),
            "claim_count": claim_count,
            "verdict": HonestyAudit._verdict(hedge_n, confidence_n, citation_n, n, claim_count),
        }

    @staticmethod
    def _verdict(hedge_n: int, confidence_n: int, citation_n: int,
                 word_n: int, claim_count: int) -> List[str]:
        notes: List[str] = []
        if confidence_n > 5 * max(1, hedge_n):
            notes.append("confidence words dominate hedges — risk of overclaiming")
        if claim_count >= 8 and citation_n == 0:
            notes.append("many claims, zero citation hints — likely floating assertions")
        if hedge_n > 0 and citation_n == 0:
            notes.append("hedges without citations — uncertain *and* unsupported")
        if not notes:
            notes.append("ok — proportions look healthy")
        return notes

    @staticmethod
    def audit_file(path: str) -> dict:
        if not os.path.exists(path):
            return {"ok": False, "error": "path not found"}
        text = open(path).read()
        return {"ok": True, "path": path, **HonestyAudit.audit_text(text)}
