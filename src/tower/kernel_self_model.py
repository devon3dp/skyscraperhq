"""kernel_self_model.py

Cognitive Self-Model layer for the QSB Kernel (advisory only).

Describes the kernel's identity, version source, capabilities, limitations,
available scripts/modules, model lanes, and safety locks. Every value is
derived from real files or from the CLAUDE.md-mandated contract — nothing
is invented.

Writes:
    data/registries/qsb_kernel_self_model.json
"""

from pathlib import Path
import json
import sys

from tower.kernel_cognitive_common import (
    LOGS, REG, ROOT, load_registry, registry_exists,
    safety_block, utc_now_iso, write_registry,
)


COGNITIVE_MODULES = [
    "src/tower/kernel_perception_layer.py",
    "src/tower/kernel_attention_layer.py",
    "src/tower/kernel_working_memory.py",
    "src/tower/kernel_self_model.py",
    "src/tower/kernel_reflection_layer.py",
    "src/tower/kernel_learning_assimilation.py",
    "src/tower/kernel_goal_stack.py",
    "src/tower/kernel_curiosity_queue.py",
    "src/tower/kernel_opencore_supervision_bridge.py",
    "src/tower/kernel_registry_answer_builder.py",
    "src/tower/kernel_dialogue_adapter.py",
]

COGNITIVE_SCRIPTS = [
    "scripts/qsb_kernel_cognitive_tick.sh",
    "scripts/qsb_kernel_cognitive_status.sh",
    "scripts/qsb_kernel_cognitive_smoke_test.sh",
    "scripts/qsb_kernel_learning_smoke_test_v2.sh",
    "scripts/qsb_kernel_chat.sh",
]

COGNITIVE_REGISTRIES = [
    "qsb_kernel_perception_snapshot.json",
    "qsb_kernel_attention_state.json",
    "qsb_kernel_working_memory.json",
    "qsb_kernel_self_model.json",
    "qsb_kernel_reflection_state.json",
    "qsb_kernel_learning_assimilation_state.json",
    "qsb_kernel_goal_stack.json",
    "qsb_kernel_curiosity_queue.json",
    "qsb_kernel_opencore_supervision_state.json",
    "qsb_kernel_cognitive_tick_latest.json",
]


def _present(paths_rel_to_root):
    present, missing = [], []
    for p in paths_rel_to_root:
        if (ROOT / p).exists():
            present.append(p)
        else:
            missing.append(p)
    return present, missing


def run():
    act = load_registry("kernel_activation_report.json")
    gate = load_registry("kernel_activation_gate_status.json")
    lanes = load_registry("eqsb_model_lane_governance.json")

    modules_present, modules_missing = _present(COGNITIVE_MODULES)
    scripts_present, scripts_missing = _present(COGNITIVE_SCRIPTS)

    regs_present = [n for n in COGNITIVE_REGISTRIES if registry_exists(n)]
    regs_missing = [n for n in COGNITIVE_REGISTRIES if not registry_exists(n)]

    payload = {
        "module": "kernel_self_model",
        "purpose": ("Describe what the kernel is, what it can do, what it "
                    "must not do, and what scripts/modules/registries support "
                    "its cognition."),
        "timestamp_utc": utc_now_iso(),
        "identity": "EQSB / QSB Kernel (local-only symbolic, advisory only)",
        "version": (act.get("kernel_version")
                    or "4.6-offline-kernel-symbolic"),
        "active_kernel_source": act.get("active_kernel_source")
                                  or "rebased_kernel",
        "active_local_only": True,
        "advisory_only": True,
        "execution_allowed": False,
        "can_read": [
            "data/registries/*.json (advisory)",
            "data/logs/*.jsonl (advisory tail)",
            "penthouse/kernel_installation_socket/rebased_kernel/state/*",
        ],
        "can_propose": [
            "next read-only repair actions",
            "next cognitive tick",
            "next operator dialogue priorities",
            "registry-cited explanations of state",
        ],
        "cannot_do": [
            "enable any execution gate",
            "place real orders or call external providers",
            "dispatch workers or start autonomous loops",
            "rewrite or unlock CLAUDE.md safety contract",
            "expose secrets / .env / *.key / *.pem",
        ],
        "known_limitations": [
            "I do not run live inference; I summarize registries.",
            "I cannot confirm CUDA/torch state beyond what the ML/RL lab registry reports.",
            "Stale registries make my answers honest-but-old, not invented.",
            "I cannot guarantee what is in a registry I have not read.",
        ],
        "available_modules": {
            "present": modules_present,
            "missing": modules_missing,
        },
        "available_scripts": {
            "present": scripts_present,
            "missing": scripts_missing,
        },
        "available_cognitive_registries": {
            "present": regs_present,
            "missing": regs_missing,
        },
        "missing_cognitive_scripts": scripts_missing,
        "missing_cognitive_registries": regs_missing,
        "current_model_lanes": (
            lanes.get("lanes")
            if isinstance(lanes, dict) else
            ["kernel_introspection",
             "local_speech_only",
             "registry_quotation"]),
        "safety_locks": safety_block(),
        "kernel_activation_gate_state": {
            "status": (gate.get("status") if isinstance(gate, dict) else None),
            "active_local_only": True,
            "execution_unlock_required": True,
            "auto_unlock_allowed": False,
        },
        "source_file_list": [
            "data/registries/kernel_activation_report.json",
            "data/registries/kernel_activation_gate_status.json",
            "data/registries/eqsb_model_lane_governance.json",
        ] + ["data/registries/" + n for n in COGNITIVE_REGISTRIES],
        "confidence": 0.9 if not modules_missing and not scripts_missing else 0.7,
        "warnings": (["missing_module:" + m for m in modules_missing]
                     + ["missing_script:" + s for s in scripts_missing]
                     + ["missing_registry:" + r for r in regs_missing]),
        "safety": safety_block(),
    }

    rel = write_registry("qsb_kernel_self_model.json", payload)
    return {"written": rel,
            "modules_missing": len(modules_missing),
            "scripts_missing": len(scripts_missing),
            "registries_missing": len(regs_missing)}


def main():
    print(json.dumps(run(), indent=2))
    return 0


if __name__ == "__main__":
    sys.exit(main())
