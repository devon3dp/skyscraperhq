"""kernel_perception_layer.py

Cognitive Perception layer for the QSB Kernel (advisory only).

Reads existing registries/logs across Core, Godot, ML/RL, Banking, GitHub
scout, Workers/Floors, and Safety. Summarizes what the kernel currently
perceives without inventing values.

Writes:
    data/registries/qsb_kernel_perception_snapshot.json

Never executes anything, never calls external providers, never exposes
secrets.
"""

from pathlib import Path
import json
import sys

from tower.kernel_cognitive_common import (
    REG, ROOT, classify_sources, load_registry,
    safety_block, utc_now_iso, write_registry,
)


CORE_SOURCES = [
    "qsb_kernel_learning_smoke_test_v2_latest.json",
    "qsb_kernel_thinking_upgrade_probe_latest.json",
    "eqsb_claude_upgrade_ledger.json",
    "eqsb_kernel_learning_loop.json",
    "eqsb_code_observatory.json",
    "eqsb_hardware_observatory.json",
]

GODOT_SOURCES = [
    "qsb_cockpit_primary_engine_policy.json",
    "qsb_godot_primary_cockpit_status.json",
    "qsb_godot_primary_professional_score.json",
    "qsb_godot_professional_layout_score.json",
    "qsb_godot_live_telemetry_status.json",
    "qsb_godot_project_status.json",
    "qsb_godot_visual_score.json",
    "qsb_3d_engine_status.json",
]

ML_RL_SOURCES = [
    "qsb_ml_rl_lab_status.json",
    "qsb_ml_rl_runtime_mode.json",
    "qsb_ml_rl_torch_status.json",
    "qsb_ml_rl_package_install_status.json",
]

BANKING_SOURCES = [
    "qsb_banking_gateway_status.json",
    "qsb_banking_gateway_kill_switches.json",
    "qsb_banking_gateway_real_money_phase_requirements.json",
]

GITHUB_SOURCES = [
    "qsb_github_upgrade_candidates.json",
    "qsb_github_upgrade_import_plan.json",
    "qsb_github_upgrade_risk_matrix.json",
]

WORKER_SOURCES = [
    "qsb_3d_skyscraper_state.json",
    "recruitment_workers.json",
    "worker_training_assignments.json",
    "qsb_worker_skill_matrix.json",
]

SAFETY_SOURCES = [
    "qsb_banking_gateway_kill_switches.json",
    "security_spine_kernel_clearance_status.json",
    "kernel_activation_gate_status.json",
    "kernel_activation_report.json",
]


def _summarize_category(label, names):
    fresh, stale, missing = classify_sources(names)
    samples = {}
    for n in fresh[:6]:
        d = load_registry(n)
        if isinstance(d, dict):
            samples[n] = {
                k: d.get(k)
                for k in ("status", "verdict", "version", "schema_version",
                          "generated_ts", "timestamp_utc", "ts", "phase",
                          "passes", "failures", "warnings", "execution_allowed",
                          "advisory_only", "active_local_only")
                if k in d
            }
        elif isinstance(d, list):
            samples[n] = {"length": len(d)}
    return {
        "category": label,
        "present_fresh_count": len(fresh),
        "present_stale_count": len(stale),
        "missing_count": len(missing),
        "present_fresh": fresh,
        "present_stale": stale,
        "missing": missing,
        "samples": samples,
    }


def run():
    categories = {
        "core": _summarize_category("core", CORE_SOURCES),
        "godot": _summarize_category("godot", GODOT_SOURCES),
        "ml_rl": _summarize_category("ml_rl", ML_RL_SOURCES),
        "banking": _summarize_category("banking", BANKING_SOURCES),
        "github_scout": _summarize_category("github_scout", GITHUB_SOURCES),
        "workers_floors": _summarize_category("workers_floors", WORKER_SOURCES),
        "safety": _summarize_category("safety", SAFETY_SOURCES),
    }

    all_sources = (CORE_SOURCES + GODOT_SOURCES + ML_RL_SOURCES
                   + BANKING_SOURCES + GITHUB_SOURCES + WORKER_SOURCES
                   + SAFETY_SOURCES)
    fresh_all, stale_all, missing_all = classify_sources(all_sources)

    # Confidence = fraction of categories whose primary inputs are present
    # and fresh. Honest, not boosted.
    total = max(1, len(all_sources))
    confidence = round(len(fresh_all) / total, 3)

    payload = {
        "module": "kernel_perception_layer",
        "purpose": ("Perceive current kernel/tower state across registries "
                    "and logs. Read-only summary; never proposes execution."),
        "timestamp_utc": utc_now_iso(),
        "categories": categories,
        "fresh_sources": fresh_all,
        "stale_sources": stale_all,
        "missing_sources": missing_all,
        "source_file_list": [
            "data/registries/" + n for n in all_sources
        ],
        "confidence": confidence,
        "warnings": [
            ("stale_source:" + s) for s in stale_all
        ] + [
            ("missing_source:" + s) for s in missing_all
        ],
        "safety": safety_block(),
    }

    rel = write_registry("qsb_kernel_perception_snapshot.json", payload)
    return {"written": rel, "confidence": confidence,
            "missing_count": len(missing_all),
            "stale_count": len(stale_all),
            "fresh_count": len(fresh_all)}


def main():
    result = run()
    print(json.dumps(result, indent=2))
    return 0


if __name__ == "__main__":
    sys.exit(main())
