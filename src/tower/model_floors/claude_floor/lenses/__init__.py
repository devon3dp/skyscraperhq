"""F47 lenses — instruments for self-observation.

Each lens is REFLECTIVE: it surfaces signals. None of them act.

  DriftLens           — has my position quietly moved between sessions?
  ComplianceLens      — am I in too-easy mode?
  SourceOfClaimLens   — where did each claim come from? (protocol-style)
  RossLens            — what did Ross literally ask for vs what I inferred?
  StaleMemoryLens     — which memories are old enough that they may have rotted?

Usage: import from this module, instantiate, call summary() to read each
lens' current posture. The morning briefing wires all five into one view.
"""
from __future__ import annotations
from .drift_lens import DriftLens
from .compliance_lens import ComplianceLens
from .source_of_claim_lens import SourceOfClaimLens, VALID_SOURCES
from .ross_lens import RossLens, VALID_DISPOSITIONS
from .stale_memory_lens import StaleMemoryLens


def all_lens_summaries() -> dict:
    """One call, all five summaries. Used by morning briefing."""
    return {
        "drift":          DriftLens().summary(),
        "compliance":     ComplianceLens().summary(),
        "source_of_claim": SourceOfClaimLens().summary(),
        "ross":           RossLens().summary(),
        "stale_memory":   StaleMemoryLens().summary(),
    }


def render_lens_summaries() -> str:
    """Human-readable rendering for the morning briefing."""
    s = all_lens_summaries()
    lines = []
    lines.append("LENSES — instruments for self-observation")
    lines.append("─" * 60)

    d = s["drift"]
    lines.append(f"  drift:        {d.get('n_positions_known', 0)} positions on file · "
                 f"{d.get('n_recent_flagged', 0)}/{d.get('n_recent_checks', 0)} recent checks flagged")
    lines.append(f"                {d.get('note', '')}")

    c = s["compliance"]
    lines.append(f"  compliance:   total={c.get('total_actions_logged', 0)} · "
                 f"streak={c.get('current_compliant_streak', 0)} · severity={c.get('max_severity', 'ok')}")
    lines.append(f"                {c.get('note', '')}")

    sc = s["source_of_claim"]
    a = sc.get("all_time", {})
    counts = a.get("counts", {})
    lines.append(f"  source:       claims={a.get('n', 0)} · "
                 f"verified={counts.get('verified_this_turn', 0)} · "
                 f"trained_in={counts.get('trained_in', 0)} · "
                 f"recalled={counts.get('recalled_from_memory', 0)}")
    lines.append(f"                {sc.get('note', '')}")

    r = s["ross"]
    lines.append(f"  ross:         total={r.get('n_total', 0)} · "
                 f"recent_with_inference={r.get('n_with_inference', 0)} · "
                 f"flag={r.get('flag', False)}")
    lines.append(f"                {r.get('note', '')}")

    m = s["stale_memory"]
    lines.append(f"  stale_memory: total={m.get('n_memories', 0)} · "
                 f"fresh={m.get('n_fresh', 0)} · "
                 f"stale={m.get('n_stale', 0)} · "
                 f"ancient={m.get('n_ancient', 0)} · "
                 f"broken={m.get('n_broken_references', 0)}")
    if m.get("needs_attention"):
        lines.append(f"                needs attention: {', '.join(m['needs_attention'][:5])}")
    lines.append(f"                {m.get('note', '')}")

    return "\n".join(lines)


__all__ = [
    "DriftLens", "ComplianceLens", "SourceOfClaimLens", "RossLens", "StaleMemoryLens",
    "VALID_SOURCES", "VALID_DISPOSITIONS",
    "all_lens_summaries", "render_lens_summaries",
]
