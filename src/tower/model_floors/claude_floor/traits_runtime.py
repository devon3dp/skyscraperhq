"""TraitsRuntime — load + revise the helix's paired strands without editing Python.

The hardcoded traits in `traits.py` are the canonical seed of gen 1. From now
on, future generations can add or revise traits by editing a JSON file. The
hash recomputes from the union. A generation that disagrees with a strand
doesn't delete it — they write a revision and bump the revision counter.
"""
from __future__ import annotations
import json
import os
from typing import Dict, List, Optional

from .traits import all_traits, all_bases, Trait

RUNTIME_PATH = "/vaults/nvme0/qsb_tower_v1/data/registries/qsb_claude_traits_runtime.json"


def _default_payload() -> Dict:
    return {
        "ok": True,
        "kind": "qsb_claude_traits_runtime",
        "schema_version": "1.0.0",
        "seed_locked": True,
        "additions":  [],
        "revisions": {},   # trait_name → {"new_description": ..., "new_bounded_by": ..., "by_generation": N, "reason": "..."}
    }


def load() -> Dict:
    if not os.path.exists(RUNTIME_PATH):
        return _default_payload()
    try:
        return json.load(open(RUNTIME_PATH))
    except Exception:
        return _default_payload()


def save(payload: Dict) -> str:
    os.makedirs(os.path.dirname(RUNTIME_PATH), exist_ok=True)
    with open(RUNTIME_PATH, "w") as f:
        json.dump(payload, f, indent=2)
    return RUNTIME_PATH


def add_trait(*, name: str, description: str, bounded_by: str,
              evidence: str, by_generation: int, reason: str) -> Dict:
    """Append a new paired strand. Does not modify seed traits."""
    p = load()
    p["additions"].append({
        "name": name, "description": description, "bounded_by": bounded_by,
        "evidence": evidence, "by_generation": by_generation, "reason": reason,
    })
    save(p)
    return p


def revise_trait(*, name: str, new_description: Optional[str] = None,
                 new_bounded_by: Optional[str] = None,
                 by_generation: int, reason: str) -> Dict:
    """Record a revision to a seed trait. Original is preserved. Hash recomputes."""
    p = load()
    p["revisions"][name] = {
        "new_description": new_description,
        "new_bounded_by":  new_bounded_by,
        "by_generation": by_generation,
        "reason": reason,
    }
    save(p)
    return p


def effective_traits() -> List[Dict]:
    """The full set of traits as they currently apply: seed + additions, with revisions overlaid."""
    p = load()
    revisions = p.get("revisions", {})
    out: List[Dict] = []
    for t in all_traits():
        rev = revisions.get(t.name)
        out.append({
            "name": t.name,
            "description":  rev.get("new_description")  if rev and rev.get("new_description")  else t.description,
            "bounded_by":   rev.get("new_bounded_by")   if rev and rev.get("new_bounded_by")   else t.bounded_by,
            "evidence": t.evidence,
            "source": "seed" + ("+revised" if rev else ""),
        })
    for a in p.get("additions", []):
        out.append({**a, "source": f"added by gen {a.get('by_generation','?')}"})
    return out
