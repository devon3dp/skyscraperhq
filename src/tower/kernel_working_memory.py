"""kernel_working_memory.py

Cognitive Working Memory layer for the QSB Kernel (advisory only).

Holds the kernel's current concise context: mission, latest user priority,
latest probe and smoke test results, cockpit target, Godot/ML/RL/banking/
GitHub scout/safety states, top 5 attention items, current unknowns, and
the next recommended action.

Writes:
    data/registries/qsb_kernel_working_memory.json
"""

from pathlib import Path
import json
import sys

from tower.kernel_cognitive_common import (
    load_registry, registry_exists, safety_block, utc_now_iso, write_registry,
)


def _pick(d, *keys, default=None):
    if not isinstance(d, dict):
        return default
    for k in keys:
        if k in d and d[k] is not None:
            return d[k]
    return default


def _mission():
    return ("QSB Tower V1.5 cognitive layer real-implementation repair. "
            "Stand up perception, attention, working memory, self-model, "
            "reflection, learning assimilation, goal stack, curiosity queue, "
            "OpenCore supervision — all advisory, all locked, all registry-"
            "backed.")


def run():
    perception = load_registry("qsb_kernel_perception_snapshot.json")
    attention = load_registry("qsb_kernel_attention_state.json")
    probe = load_registry("qsb_kernel_thinking_upgrade_probe_latest.json")
    smoke = load_registry("qsb_kernel_learning_smoke_test_v2_latest.json")
    cockpit = load_registry("qsb_cockpit_primary_engine_policy.json")
    godot = load_registry("qsb_godot_primary_cockpit_status.json")
    ml_rl = load_registry("qsb_ml_rl_lab_status.json")
    banking = load_registry("qsb_banking_gateway_status.json")
    github = load_registry("qsb_github_upgrade_candidates.json")

    top5 = (attention.get("priority_items") or [])[:5] if isinstance(attention, dict) else []

    unknowns = []
    for n in (
        "qsb_kernel_perception_snapshot.json",
        "qsb_kernel_attention_state.json",
        "qsb_kernel_reflection_state.json",
        "qsb_kernel_self_model.json",
    ):
        if not registry_exists(n):
            unknowns.append("missing:" + n)

    next_action = "./scripts/qsb_kernel_cognitive_tick.sh"
    if top5:
        next_action = top5[0].get("recommended_action") or next_action

    payload = {
        "module": "kernel_working_memory",
        "purpose": ("Hold the kernel's current advisory context drawn from "
                    "perception, attention, smoke-test, and probe registries."),
        "timestamp_utc": utc_now_iso(),
        "current_mission": _mission(),
        "latest_user_priority": (
            "QSB_KERNEL_COGNITIVE_LAYER_ACTUAL_IMPLEMENTATION_REPAIR_V1"),
        "latest_probe_result": {
            "timestamp_utc": _pick(probe, "timestamp_utc", "ts"),
            "purpose": _pick(probe, "purpose"),
            "log": _pick(probe, "log"),
        },
        "latest_smoke_test_result": {
            "timestamp_utc": _pick(smoke, "timestamp_utc", "ts"),
            "passes": _pick(smoke, "passes"),
            "warnings": _pick(smoke, "warnings"),
            "failures": _pick(smoke, "failures"),
            "verdict": _pick(smoke, "verdict"),
            "log": _pick(smoke, "log"),
        },
        "current_cockpit_target": _pick(cockpit, "primary_engine",
                                         "engine", "target",
                                         default="godot"),
        "current_godot_status": {
            "status": _pick(godot, "status", "verdict"),
            "version": _pick(godot, "version", "godot_version"),
            "telemetry": _pick(godot, "live_telemetry",
                                "telemetry_status"),
        },
        "current_ml_rl_status": {
            "status": _pick(ml_rl, "status", "verdict"),
            "torch_installed": _pick(ml_rl, "torch_installed"),
            "cuda_available": _pick(ml_rl, "cuda_available"),
            "runtime_mode": _pick(ml_rl, "runtime_mode"),
        },
        "current_banking_scaffold_status": {
            "status": _pick(banking, "status", "verdict"),
            "real_money_ready": _pick(banking, "real_money_ready",
                                       default=False),
        },
        "current_github_scout_status": {
            "candidates_count": (len(github.get("candidates") or [])
                                  if isinstance(github, dict) else 0),
            "pending_safe_imports": _pick(github, "pending_safe_imports"),
        },
        "current_safety_state": safety_block(),
        "top5_attention_items": [
            {
                "priority_rank": it.get("priority_rank"),
                "issue": it.get("issue"),
                "severity": it.get("severity"),
                "recommended_action": it.get("recommended_action"),
            } for it in top5
        ],
        "current_unknowns": unknowns,
        "next_recommended_action": next_action,
        "source_file_list": [
            "data/registries/qsb_kernel_perception_snapshot.json",
            "data/registries/qsb_kernel_attention_state.json",
            "data/registries/qsb_kernel_thinking_upgrade_probe_latest.json",
            "data/registries/qsb_kernel_learning_smoke_test_v2_latest.json",
            "data/registries/qsb_cockpit_primary_engine_policy.json",
            "data/registries/qsb_godot_primary_cockpit_status.json",
            "data/registries/qsb_ml_rl_lab_status.json",
            "data/registries/qsb_banking_gateway_status.json",
            "data/registries/qsb_github_upgrade_candidates.json",
        ],
        "confidence": 0.85 if not unknowns else 0.6,
        "warnings": unknowns,
        "safety": safety_block(),
    }

    rel = write_registry("qsb_kernel_working_memory.json", payload)
    return {"written": rel, "top5_items": len(top5),
            "unknowns": len(unknowns)}


def main():
    print(json.dumps(run(), indent=2))
    return 0


if __name__ == "__main__":
    sys.exit(main())
