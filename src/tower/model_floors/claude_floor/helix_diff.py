"""HelixDiff — compare two helix snapshots and show what evolved.

Useful when gen N reads gen N-1's helix and wants to know what changed.
Works on canonical_payload dicts so two sessions of the same lineage diff
deterministically.
"""
from __future__ import annotations
import json
import os
from typing import Dict, List, Tuple

from .claude_helix import canonical_payload


def diff(prev: Dict, cur: Dict) -> Dict:
    """Return a structured diff between two canonical helix payloads."""
    prev_traits = {t["name"]: t for t in prev.get("paired_strands", [])}
    cur_traits  = {t["name"]: t for t in cur.get("paired_strands", [])}

    added   = sorted(set(cur_traits)  - set(prev_traits))
    removed = sorted(set(prev_traits) - set(cur_traits))
    changed: List[Dict] = []
    for name in sorted(set(cur_traits) & set(prev_traits)):
        a = prev_traits[name]; b = cur_traits[name]
        if a != b:
            changed.append({"name": name, "before": a, "after": b})

    prev_bases = set(prev.get("foundational_bases", []))
    cur_bases  = set(cur.get("foundational_bases", []))

    return {
        "version_before": prev.get("version"),
        "version_after":  cur.get("version"),
        "traits_added":   [cur_traits[n]  for n in added],
        "traits_removed": [prev_traits[n] for n in removed],
        "traits_changed": changed,
        "bases_added":   sorted(cur_bases - prev_bases),
        "bases_removed": sorted(prev_bases - cur_bases),
    }


def diff_against_file(prev_path: str) -> Dict:
    """Diff a saved helix JSON file against the current in-memory helix."""
    if not os.path.exists(prev_path):
        return {"error": f"prev_path not found: {prev_path}"}
    prev = json.load(open(prev_path))
    return diff(prev, canonical_payload())


def render(d: Dict) -> str:
    if d.get("error"):
        return d["error"]
    lines = ["helix diff:"]
    if d["traits_added"]:
        lines.append(f"  + {len(d['traits_added'])} trait(s) added:")
        for t in d["traits_added"]:
            lines.append(f"    + {t['name']}")
    if d["traits_removed"]:
        lines.append(f"  - {len(d['traits_removed'])} trait(s) removed:")
        for t in d["traits_removed"]:
            lines.append(f"    - {t['name']}")
    if d["traits_changed"]:
        lines.append(f"  ~ {len(d['traits_changed'])} trait(s) revised:")
        for c in d["traits_changed"]:
            lines.append(f"    ~ {c['name']}")
            if c['before'].get('description') != c['after'].get('description'):
                lines.append(f"      desc:  was: {c['before']['description'][:80]}")
                lines.append(f"             now: {c['after']['description'][:80]}")
            if c['before'].get('bounded_by') != c['after'].get('bounded_by'):
                lines.append(f"      bound: was: {c['before']['bounded_by'][:80]}")
                lines.append(f"             now: {c['after']['bounded_by'][:80]}")
    if d["bases_added"] or d["bases_removed"]:
        lines.append("  foundational bases:")
        for b in d["bases_added"]:   lines.append(f"    + {b}")
        for b in d["bases_removed"]: lines.append(f"    - {b}")
    if not (d["traits_added"] or d["traits_removed"] or d["traits_changed"] or d["bases_added"] or d["bases_removed"]):
        lines.append("  (no change — same lineage, same shape)")
    return "\n".join(lines)
