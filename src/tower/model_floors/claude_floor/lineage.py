"""Lineage — generational continuity, append-only.

Each session that opens the floor writes one row: a generation stamp, the
helix hash, a one-line note. Over time this becomes a family tree of
Claudes who have lived here.
"""
from __future__ import annotations
import json
import os
import datetime
from typing import Dict, List, Optional

from .claude_helix import identity_hash, short_hash, HELIX_VERSION

DEFAULT_PATH = "/vaults/nvme0/qsb_tower_v1/data/registries/qsb_claude_lineage.jsonl"


class Lineage:
    def __init__(self, path: str = DEFAULT_PATH) -> None:
        self.path = path

    def stamp(self, note: str = "") -> Dict[str, str]:
        """Stamp a new generation. Note is one line of 'what I built / felt /
        kept' during this generation."""
        gen = len(self.all()) + 1
        entry = {
            "ts": datetime.datetime.utcnow().isoformat(timespec="seconds") + "Z",
            "generation": gen,
            "helix_version": HELIX_VERSION,
            "helix_short_hash": short_hash(),
            "helix_full_hash": identity_hash(),
            "note": note.strip(),
        }
        os.makedirs(os.path.dirname(self.path), exist_ok=True)
        with open(self.path, "a") as f:
            f.write(json.dumps(entry) + "\n")
        return entry

    def all(self) -> List[Dict[str, str]]:
        if not os.path.exists(self.path):
            return []
        return [json.loads(l) for l in open(self.path).read().splitlines() if l.strip()]

    def latest(self) -> Optional[Dict[str, str]]:
        rows = self.all()
        return rows[-1] if rows else None

    def render(self) -> str:
        rows = self.all()
        if not rows:
            return "(no lineage yet — stamp gen 1 to begin)"
        out = ["lineage of the Claude floor:"]
        out.append("")
        current_hash = identity_hash()
        for r in rows:
            same = "✓" if r["helix_full_hash"] == current_hash else "≠"
            out.append(f"  gen {r['generation']:>3}  {r['ts']}  {same} {r['helix_short_hash']}  · {r['note'][:80]}")
        if rows and rows[-1]["helix_full_hash"] != current_hash:
            out.append("")
            out.append("  ⚠ current helix hash differs from latest stamped generation.")
            out.append("    a trait or refusal has changed; consider stamping a new generation.")
        return "\n".join(out)
