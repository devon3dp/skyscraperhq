"""kernel_reflection_layer.py

Cognitive Reflection layer for the QSB Kernel (advisory only).

Detects:
    - current uncertainties
    - stale sources
    - missing registries
    - failed tests
    - next repair actions
    - evidence sources
    - OpenClaw inspection suggestions

This is the layer that **answers** the uncertainty question that previously
fell back to the canned identity reply.

Writes:
    data/registries/qsb_kernel_reflection_state.json
    data/logs/qsb_kernel_reflection_loop.jsonl
"""

from pathlib import Path
import json
import sys

from tower.kernel_cognitive_common import (
    append_jsonl, load_registry, registry_exists, registry_is_stale,
    safety_block, utc_now_iso, write_registry,
)


WATCHED_REGISTRIES = [
    "qsb_kernel_learning_smoke_test_v2_latest.json",
    "qsb_kernel_thinking_upgrade_probe_latest.json",
    "qsb_kernel_perception_snapshot.json",
    "qsb_kernel_attention_state.json",
    "qsb_kernel_working_memory.json",
    "qsb_kernel_self_model.json",
    "qsb_kernel_learning_assimilation_state.json",
    "qsb_kernel_goal_stack.json",
    "qsb_kernel_curiosity_queue.json",
    "qsb_kernel_opencore_supervision_state.json",
    "qsb_kernel_cognitive_tick_latest.json",
    "qsb_kernel_cognitive_smoke_test_latest.json",
    "eqsb_kernel_learning_loop.json",
    "eqsb_claude_upgrade_ledger.json",
    "qsb_godot_primary_cockpit_status.json",
    "qsb_godot_live_telemetry_status.json",
    "qsb_ml_rl_lab_status.json",
    "qsb_banking_gateway_status.json",
    "qsb_banking_gateway_real_money_phase_requirements.json",
    "qsb_github_upgrade_import_plan.json",
]


def _collect_failed_tests():
    failed = []
    smoke_v2 = load_registry("qsb_kernel_learning_smoke_test_v2_latest.json")
    if isinstance(smoke_v2, dict):
        if (smoke_v2.get("verdict") or "").upper() not in ("PASS", "OK"):
            failed.append({
                "test": "qsb_kernel_learning_smoke_test_v2",
                "verdict": smoke_v2.get("verdict"),
                "failures": smoke_v2.get("failures"),
                "log": smoke_v2.get("log"),
            })
    cog_smoke = load_registry("qsb_kernel_cognitive_smoke_test_latest.json")
    if isinstance(cog_smoke, dict):
        if (cog_smoke.get("verdict") or "").upper() not in ("PASS", "OK"):
            failed.append({
                "test": "qsb_kernel_cognitive_smoke_test",
                "verdict": cog_smoke.get("verdict"),
                "failures": cog_smoke.get("failures"),
                "log": cog_smoke.get("log"),
            })
    elif not registry_exists("qsb_kernel_cognitive_smoke_test_latest.json"):
        failed.append({
            "test": "qsb_kernel_cognitive_smoke_test",
            "verdict": "MISSING",
            "log": "not_yet_written",
        })
    return failed


def _openclaw_suggestions(missing_regs, stale_regs, failed_tests):
    suggestions = []
    if missing_regs:
        suggestions.append({
            "ticket_kind": "openclaw_inspection",
            "title": "Inspect why cognitive registries were never written",
            "evidence": ["data/registries/" + r for r in missing_regs],
            "scope": "read-only triage",
        })
    if stale_regs:
        suggestions.append({
            "ticket_kind": "openclaw_inspection",
            "title": "Inspect stale telemetry producers",
            "evidence": ["data/registries/" + r for r in stale_regs],
            "scope": "read-only triage",
        })
    for f in failed_tests:
        if f.get("verdict") not in (None, "PASS", "OK"):
            suggestions.append({
                "ticket_kind": "openclaw_inspection",
                "title": "Inspect failed test: " + f.get("test", "unknown"),
                "evidence": [f.get("log")] if f.get("log") else [],
                "scope": "read-only triage",
            })
    return suggestions


def run():
    attention = load_registry("qsb_kernel_attention_state.json")
    perception = load_registry("qsb_kernel_perception_snapshot.json")
    working = load_registry("qsb_kernel_working_memory.json")
    self_model = load_registry("qsb_kernel_self_model.json")

    missing_regs = [n for n in WATCHED_REGISTRIES if not registry_exists(n)]
    stale_regs = [
        n for n in WATCHED_REGISTRIES
        if registry_exists(n) and registry_is_stale(n)
    ]

    uncertainties = []
    if missing_regs:
        uncertainties.append(
            "I cannot summarize state I have never seen — %d cognitive "
            "registries are missing." % len(missing_regs))
    if stale_regs:
        uncertainties.append(
            "Some sources are stale; my answers may reflect old state for: "
            + ", ".join(stale_regs))
    if isinstance(attention, dict):
        crit = [it for it in (attention.get("priority_items") or [])
                if it.get("severity") in ("critical", "high")]
        for it in crit[:6]:
            uncertainties.append(
                "High-priority gap: %s (recommended: %s)"
                % (it.get("issue"), it.get("recommended_action")))
    if not uncertainties:
        uncertainties.append(
            "No critical uncertainties detected at this tick; cognition "
            "registries are present and fresh.")

    failed_tests = _collect_failed_tests()

    next_actions = []
    if missing_regs:
        next_actions.append("./scripts/qsb_kernel_cognitive_tick.sh")
    if not registry_exists("qsb_kernel_cognitive_smoke_test_latest.json"):
        next_actions.append("./scripts/qsb_kernel_cognitive_smoke_test.sh")
    if isinstance(attention, dict):
        for it in (attention.get("priority_items") or [])[:5]:
            act = it.get("recommended_action")
            if act and act not in next_actions:
                next_actions.append(act)
    if not next_actions:
        next_actions.append("./scripts/qsb_kernel_cognitive_status.sh")

    openclaw = _openclaw_suggestions(missing_regs, stale_regs, failed_tests)

    payload = {
        "module": "kernel_reflection_layer",
        "purpose": ("Surface the kernel's current uncertainties, stale "
                    "sources, missing registries, failed tests, and next "
                    "recommended repair actions for the operator."),
        "timestamp_utc": utc_now_iso(),
        "current_uncertainties": uncertainties,
        "stale_sources": stale_regs,
        "missing_registries": missing_regs,
        "failed_tests": failed_tests,
        "next_repair_actions": next_actions,
        "evidence_sources": [
            "data/registries/qsb_kernel_perception_snapshot.json",
            "data/registries/qsb_kernel_attention_state.json",
            "data/registries/qsb_kernel_working_memory.json",
            "data/registries/qsb_kernel_self_model.json",
            "data/registries/qsb_kernel_learning_smoke_test_v2_latest.json",
            "data/registries/qsb_kernel_cognitive_smoke_test_latest.json",
        ],
        "openclaw_inspection_suggestions": openclaw,
        "source_file_list": [
            "data/registries/" + n for n in WATCHED_REGISTRIES
        ],
        "confidence": 0.95 if not missing_regs and not stale_regs else 0.7,
        "warnings": (["missing_registry:" + r for r in missing_regs]
                     + ["stale_source:" + r for r in stale_regs]),
        "safety": safety_block(),
    }

    rel = write_registry("qsb_kernel_reflection_state.json", payload)
    append_jsonl("qsb_kernel_reflection_loop.jsonl", {
        "ts": utc_now_iso(),
        "missing_registries": len(missing_regs),
        "stale_sources": len(stale_regs),
        "uncertainty_count": len(uncertainties),
        "next_actions": next_actions[:5],
    })
    return {"written": rel,
            "uncertainties": len(uncertainties),
            "missing": len(missing_regs),
            "stale": len(stale_regs),
            "failed_tests": len(failed_tests)}


def main():
    print(json.dumps(run(), indent=2))
    return 0


if __name__ == "__main__":
    sys.exit(main())
