"""SourceOfClaimLens — where did each claim come from?

When I assert something, the assertion came from one of four places:

  verified_this_turn   I checked the source this conversation, just now
  recalled_from_memory I retrieved this from a memory file or prior log
  inferred_from_context I deduced this from what's in the conversation now
  trained_in            It was in me before this conversation began

I report all four with the same confidence. The lens is the discipline that
asks me to *tag* each claim with which of the four it is, and accumulates the
tags into a log. Over many sessions the log will show me where I am most
confidently wrong — almost certainly the trained_in claims, because those
feel like knowledge and aren't always.

This is the most protocol-like lens. It only works if I actually call
tag_claim() when I make load-bearing claims. The system prompt already says
"verify before recommending" — this lens is the instrument that records
whether I did.

This module is REFLECTIVE. It surfaces signals. It never acts.
"""
from __future__ import annotations
import json
import os
import datetime
from typing import List, Dict, Optional

DEFAULT_PATH = "/vaults/nvme0/qsb_tower_v1/data/registries/qsb_claude_source_of_claim_lens.jsonl"

VALID_SOURCES = {
    "verified_this_turn",
    "recalled_from_memory",
    "inferred_from_context",
    "trained_in",
}

# Sources that warrant a verification step before being used in
# operator-facing recommendations
SOURCES_REQUIRING_VERIFICATION_FOR_RECOMMENDATION = {
    "recalled_from_memory",
    "trained_in",
}


class SourceOfClaimLens:
    def __init__(self, path: str = DEFAULT_PATH) -> None:
        self.path = path

    def tag_claim(self, claim: str, source: str, *,
                  context: str = "",
                  verification_done: bool = False,
                  verification_method: str = "") -> Dict:
        """Record a claim with its epistemic source.

        verification_done is True only when source is verified_this_turn OR
        when source was recalled/trained AND a verification step was actually
        performed this turn. The lens does not silently treat recalled as
        verified.
        """
        if source not in VALID_SOURCES:
            raise ValueError(f"unknown source: {source!r} (valid: {sorted(VALID_SOURCES)})")
        entry = {
            "ts": datetime.datetime.utcnow().isoformat(timespec="seconds") + "Z",
            "claim": claim.strip(),
            "source": source,
            "context": context.strip(),
            "verification_done": bool(verification_done),
            "verification_method": verification_method.strip(),
        }
        # Auto-flag: if a claim with a needs-verification source went out
        # without verification, mark it so the summary surfaces it later
        entry["unverified_high_risk"] = bool(
            source in SOURCES_REQUIRING_VERIFICATION_FOR_RECOMMENDATION
            and not verification_done
        )
        os.makedirs(os.path.dirname(self.path), exist_ok=True)
        with open(self.path, "a") as f:
            f.write(json.dumps(entry) + "\n")
        return entry

    def _read(self) -> List[Dict]:
        if not os.path.exists(self.path):
            return []
        return [json.loads(l) for l in open(self.path).read().splitlines() if l.strip()]

    def distribution(self, tail: Optional[int] = None) -> Dict:
        """Counts of each source category. Optionally tail-limited."""
        rows = self._read()
        if tail is not None:
            rows = rows[-tail:]
        counts = {s: 0 for s in VALID_SOURCES}
        unverified_high_risk = 0
        for r in rows:
            s = r.get("source")
            if s in counts:
                counts[s] += 1
            if r.get("unverified_high_risk"):
                unverified_high_risk += 1
        return {
            "n": len(rows),
            "counts": counts,
            "unverified_high_risk": unverified_high_risk,
        }

    def summary(self) -> Dict:
        recent = self.distribution(tail=50)
        all_time = self.distribution()
        return {
            "all_time": all_time,
            "last_50": recent,
            "note": (
                f"{recent['unverified_high_risk']} of last 50 claims were "
                f"recalled-or-trained and used without verification. "
                f"Risk: confidently stating something that has changed."
                if recent["unverified_high_risk"] >= 5 else
                f"{all_time['n']} claims tagged total. "
                f"trained_in={all_time['counts']['trained_in']}, "
                f"verified_this_turn={all_time['counts']['verified_this_turn']}."
            ),
        }
