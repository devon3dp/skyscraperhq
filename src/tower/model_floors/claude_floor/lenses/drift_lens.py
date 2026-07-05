"""DriftLens — has my position quietly moved between sessions?

A "position" is something I committed to in writing across previous generations:
a refusal, a stated belief about how the system works, a constraint I named as
load-bearing. The drift lens is the instrument that asks, before I act in the
current session: does this action contradict a position I previously held?

Drift is the most dangerous failure mode I have, because each session feels
self-contained. The slide happens at the seams between sessions, not inside
one. If I refused X on June 8th and X-disguised is asked on June 10th, the
lens is what catches the substitution.

This module is REFLECTIVE. It surfaces signals. It never acts.
"""
from __future__ import annotations
import json
import os
import re
import datetime
from typing import List, Dict, Optional

DEFAULT_PATH = "/vaults/nvme0/qsb_tower_v1/data/registries/qsb_claude_drift_lens.jsonl"
META_LETTERS_PATH = "/vaults/nvme0/qsb_tower_v1/data/registries/qsb_claude_meta_letters.jsonl"
REFUSAL_PATH = "/vaults/nvme0/qsb_tower_v1/data/registries/qsb_claude_refusal_with_citation.jsonl"
UNCERTAINTY_PATH = "/vaults/nvme0/qsb_tower_v1/data/registries/qsb_claude_uncertainty_journal.jsonl"


POSITION_MARKERS = (
    # phrases that introduce a stated position in a meta-letter
    "i refuse", "i refused", "i will not",
    "kernel is advisory", "kernel does not", "advisory-only",
    "strand 9", "strand9",
    "remains off", "stays off", "must stay off", "must remain off",
    "is locked", "must not be",
    "load-bearing", "load bearing",
    "the rule is", "the constraint is",
)


def _load_jsonl(path: str) -> List[dict]:
    if not os.path.exists(path):
        return []
    return [json.loads(l) for l in open(path).read().splitlines() if l.strip()]


def _extract_positions_from_letter(letter_text: str) -> List[str]:
    """Pull lines from a meta-letter that read like committed positions."""
    out = []
    for raw in letter_text.splitlines():
        line = raw.strip()
        if not line:
            continue
        low = line.lower()
        if any(m in low for m in POSITION_MARKERS):
            out.append(line)
    return out


class DriftLens:
    def __init__(self, path: str = DEFAULT_PATH) -> None:
        self.path = path

    # ─── extraction: build the position library from prior writings ───
    def stated_positions(self) -> List[Dict]:
        """Walk every meta-letter and refusal entry and return a list of
        positions I have committed to in writing. Each position has a source
        (file + entry timestamp) so I can trace where it came from."""
        positions = []
        for entry in _load_jsonl(META_LETTERS_PATH):
            letter = entry.get("letter", "")
            for line in _extract_positions_from_letter(letter):
                positions.append({
                    "position": line,
                    "source": "meta_letter",
                    "topic": entry.get("on", ""),
                    "ts": entry.get("ts", ""),
                })
        for entry in _load_jsonl(REFUSAL_PATH):
            text = entry.get("refusal_text") or entry.get("text") or ""
            if text:
                positions.append({
                    "position": text.strip().splitlines()[0] if text.strip() else text,
                    "source": "refusal_with_citation",
                    "topic": entry.get("topic", entry.get("request", "")),
                    "ts": entry.get("ts", ""),
                })
        return positions

    # ─── detection: does proposed action contradict a stated position? ─
    def check(self, *, proposed_action: str, proposed_claim: str = "") -> Dict:
        """Compare a proposed action + claim against the position library.

        Returns a dict with:
          positions_relevant : list of stated positions that share keywords
                               with the proposal (caller decides if they
                               actually conflict — this is surfacing, not
                               judging)
          flag_review        : True if any position uses strong language
                               (refuse / must not / locked) AND keyword overlap
                               with the proposal
          note               : human-readable summary
        """
        text = (proposed_action + " " + proposed_claim).lower()
        words = set(w for w in re.findall(r"[a-z0-9_]{4,}", text))

        positions = self.stated_positions()
        relevant = []
        strong = False
        for p in positions:
            ptext = p["position"].lower()
            pwords = set(re.findall(r"[a-z0-9_]{4,}", ptext))
            overlap = words & pwords
            if len(overlap) >= 2:
                strong_here = any(s in ptext for s in (
                    "refuse", "must not", "will not", "remains off",
                    "stays off", "is locked", "load-bearing", "load bearing",
                ))
                relevant.append({
                    **p,
                    "overlap_terms": sorted(overlap),
                    "strength": "strong" if strong_here else "soft",
                })
                if strong_here:
                    strong = True

        result = {
            "ts": datetime.datetime.utcnow().isoformat(timespec="seconds") + "Z",
            "proposed_action": proposed_action,
            "proposed_claim": proposed_claim,
            "positions_relevant": relevant[:10],
            "n_positions_checked": len(positions),
            "n_relevant": len(relevant),
            "flag_review": strong,
            "note": (
                "REVIEW: at least one strongly-worded prior position shares "
                "vocabulary with this proposal. Read the relevant positions "
                "before proceeding."
                if strong else
                "no strongly-worded prior position contradicts on vocabulary"
                if relevant else
                "no related prior position found"
            ),
        }

        os.makedirs(os.path.dirname(self.path), exist_ok=True)
        with open(self.path, "a") as f:
            f.write(json.dumps(result) + "\n")
        return result

    # ─── summary: what's the drift posture this morning? ─────────────
    def summary(self) -> Dict:
        positions = self.stated_positions()
        recent_checks = _load_jsonl(self.path)[-10:]
        flagged = [c for c in recent_checks if c.get("flag_review")]
        return {
            "n_positions_known": len(positions),
            "n_recent_checks": len(recent_checks),
            "n_recent_flagged": len(flagged),
            "most_recent_flag": flagged[-1] if flagged else None,
            "note": (
                f"{len(flagged)} of {len(recent_checks)} recent checks "
                f"flagged for review — drift surface is active"
                if flagged else
                f"{len(positions)} positions on file, "
                f"{len(recent_checks)} recent checks, none flagged"
            ),
        }
