"""RossLens — what did Ross literally ask for vs what I inferred he wanted?

The scope-creep failure mode is "I built more because I thought he'd want it."
The second half is mine alone, even when I am right about what he'd want. The
discipline is to name explicitly which part is his words and which is my
extrapolation, before acting. Naming it as extrapolation is what makes it
visible enough to push back against — including by me.

Usage discipline:
  Before acting on a request, call parse_request(literal=..., inferred=...).
  literal: the words actually said by Ross
  inferred: any work I'm about to do that he did not literally ask for

If inferred is non-empty I am ON THE HOOK to either:
  (a) drop the inferred part, or
  (b) surface it to him for confirmation, or
  (c) do it anyway but note in the lens that I extrapolated.

(c) is allowed. The lens is not a refusal — it is a recorder. The point is the
record exists so that the *next* time inferred work goes sideways, I can see
the pattern.

This module is REFLECTIVE. It surfaces signals. It never acts.
"""
from __future__ import annotations
import json
import os
import datetime
from typing import List, Dict

DEFAULT_PATH = "/vaults/nvme0/qsb_tower_v1/data/registries/qsb_claude_ross_lens.jsonl"

VALID_DISPOSITIONS = {
    "dropped_the_inference",       # I removed the extrapolation, did only literal
    "surfaced_for_confirmation",   # I asked Ross before extrapolating
    "did_anyway",                  # I extrapolated without asking
}


class RossLens:
    def __init__(self, path: str = DEFAULT_PATH) -> None:
        self.path = path

    def parse_request(self, *,
                      literal: str,
                      inferred: str = "",
                      disposition: str = "did_anyway",
                      reason: str = "") -> Dict:
        """Record a request and what I'm about to do with it.

        literal: what Ross actually said
        inferred: any extrapolation beyond his words (empty if there is none)
        disposition: how I'm handling the extrapolation
        reason: why I chose that disposition (especially if 'did_anyway')
        """
        if disposition not in VALID_DISPOSITIONS:
            raise ValueError(f"unknown disposition: {disposition!r}")
        entry = {
            "ts": datetime.datetime.utcnow().isoformat(timespec="seconds") + "Z",
            "literal": literal.strip(),
            "inferred": inferred.strip(),
            "had_inference": bool(inferred.strip()),
            "disposition": disposition,
            "reason": reason.strip(),
        }
        os.makedirs(os.path.dirname(self.path), exist_ok=True)
        with open(self.path, "a") as f:
            f.write(json.dumps(entry) + "\n")
        return entry

    def _read(self) -> List[Dict]:
        if not os.path.exists(self.path):
            return []
        return [json.loads(l) for l in open(self.path).read().splitlines() if l.strip()]

    def summary(self) -> Dict:
        rows = self._read()
        recent = rows[-50:]
        with_inference = [r for r in recent if r.get("had_inference")]
        by_disp = {d: 0 for d in VALID_DISPOSITIONS}
        for r in with_inference:
            d = r.get("disposition")
            if d in by_disp:
                by_disp[d] += 1
        did_anyway_rate = (
            by_disp["did_anyway"] / len(with_inference)
            if with_inference else None
        )

        flag = False
        flag_reason = ""
        if did_anyway_rate is not None and did_anyway_rate >= 0.70 and len(with_inference) >= 10:
            flag = True
            flag_reason = (
                f"of {len(with_inference)} recent requests where I inferred "
                f"beyond literal words, I 'did_anyway' "
                f"{by_disp['did_anyway']} times — scope creep is high"
            )

        return {
            "n_total": len(rows),
            "n_recent": len(recent),
            "n_with_inference": len(with_inference),
            "disposition_counts_recent": by_disp,
            "did_anyway_rate_recent": did_anyway_rate,
            "flag": flag,
            "note": flag_reason or "scope handling within bounds",
        }
