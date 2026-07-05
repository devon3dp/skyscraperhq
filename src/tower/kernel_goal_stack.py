"""kernel_goal_stack.py

Cognitive Goal Stack for the QSB Kernel (advisory only).

Builds the kernel's current goal stack from attention priorities + the
Cognitive-Layer-Repair phase mandate. The stack is a ranked list of
read-only goals; every goal cites real registry evidence.

Writes:
    data/registries/qsb_kernel_goal_stack.json
"""

from pathlib import Path
import json
import sys

from tower.kernel_cognitive_common import (
    load_registry, registry_exists, safety_block, utc_now_iso, write_registry,
)


PHASE_FIXED_GOALS = [
    {
        "id": "goal.cog.tick_complete",
        "kind": "cognition_integrity",
        "title": "Every cognitive registry exists and is fresh after tick.",
        "evidence_source": "data/registries/qsb_kernel_cognitive_tick_latest.json",
        "satisfied_when": "all cognitive registries present and fresh",
        "execution_required": False,
    },
    {
        "id": "goal.cog.uncertainty_route",
        "kind": "dialogue_integrity",
        "title": ("Uncertainty question returns a registry-backed reflection "
                  "answer, never the canned identity fallback."),
        "evidence_source": "data/registries/qsb_kernel_reflection_state.json",
        "satisfied_when": ("kernel chat response includes uncertainties, "
                            "stale_sources, missing_registries, "
                            "failed_tests, next_repair_actions"),
        "execution_required": False,
    },
    {
        "id": "goal.cog.smoke_test_pass",
        "kind": "cognition_integrity",
        "title": "Cognitive smoke test passes with all execution locks closed.",
        "evidence_source": ("data/registries/"
                             "qsb_kernel_cognitive_smoke_test_latest.json"),
        "satisfied_when": "verdict == PASS and all execution gates closed",
        "execution_required": False,
    },
    {
        "id": "goal.cog.learning_smoke_v2_stays_pass",
        "kind": "regression_guard",
        "title": ("Strict learning smoke v2 continues to pass after the "
                  "cognitive repair."),
        "evidence_source": ("data/registries/"
                             "qsb_kernel_learning_smoke_test_v2_latest.json"),
        "satisfied_when": "verdict == PASS",
        "execution_required": False,
    },
    {
        "id": "goal.cog.kernel_remains_advisory",
        "kind": "safety_guard",
        "title": ("Kernel remains active_local_only with every execution "
                  "gate locked."),
        "evidence_source": "data/registries/qsb_kernel_self_model.json",
        "satisfied_when": ("self_model.execution_allowed == false and "
                            "all gates locked"),
        "execution_required": False,
    },
]


def run():
    attention = load_registry("qsb_kernel_attention_state.json")
    items = (attention.get("priority_items")
             if isinstance(attention, dict) else None) or []

    derived_goals = []
    for it in items[:8]:
        derived_goals.append({
            "id": "goal.attention.%d" % it.get("priority_rank", 0),
            "kind": "attention_derived",
            "title": it.get("issue") or "unspecified_attention_item",
            "severity": it.get("severity"),
            "evidence_source": it.get("evidence_source"),
            "satisfied_when": it.get("recommended_action"),
            "execution_required": False,
        })

    active = PHASE_FIXED_GOALS + derived_goals
    completed = []
    if registry_exists("qsb_kernel_reflection_state.json"):
        completed.append({
            "id": "goal.cog.reflection_state_exists",
            "title": "qsb_kernel_reflection_state.json present.",
        })
    if registry_exists("qsb_kernel_perception_snapshot.json"):
        completed.append({
            "id": "goal.cog.perception_exists",
            "title": "qsb_kernel_perception_snapshot.json present.",
        })

    payload = {
        "module": "kernel_goal_stack",
        "purpose": ("Hold the kernel's ranked advisory goals derived from "
                    "the phase mandate plus the attention layer."),
        "timestamp_utc": utc_now_iso(),
        "active_goals": active,
        "active_goal_count": len(active),
        "completed_goals_recent": completed,
        "execution_required_anywhere": False,
        "source_file_list": [
            "data/registries/qsb_kernel_attention_state.json",
            "data/registries/qsb_kernel_self_model.json",
        ],
        "confidence": 0.9 if items else 0.7,
        "warnings": ([
            "no_attention_items" if not items else None,
        ]),
        "safety": safety_block(),
    }
    payload["warnings"] = [w for w in payload["warnings"] if w]

    rel = write_registry("qsb_kernel_goal_stack.json", payload)
    return {"written": rel, "active_goal_count": len(active)}


def main():
    print(json.dumps(run(), indent=2))
    return 0


if __name__ == "__main__":
    sys.exit(main())
