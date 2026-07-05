"""kernel_curiosity_queue.py

Cognitive Curiosity Queue for the QSB Kernel (advisory only).

Generates the kernel's current list of read-only questions/inspections it
would like to run next. Drawn from missing registries, stale telemetry,
and GitHub scout candidates. Every entry is read-only.

Writes:
    data/registries/qsb_kernel_curiosity_queue.json
"""

from pathlib import Path
import json
import sys

from tower.kernel_cognitive_common import (
    load_registry, registry_exists, registry_is_stale,
    safety_block, utc_now_iso, write_registry,
)


CURIOSITY_WATCHLIST = [
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
    "qsb_godot_live_telemetry_status.json",
    "qsb_ml_rl_lab_status.json",
    "qsb_banking_gateway_status.json",
]


def run():
    queue = []

    for n in CURIOSITY_WATCHLIST:
        if not registry_exists(n):
            queue.append({
                "kind": "inspect_missing_registry",
                "subject": n,
                "question": ("Why has %s not been written this cycle?"
                              % n),
                "evidence_source": "data/registries/" + n,
                "execution_required": False,
            })

    for n in CURIOSITY_WATCHLIST:
        if registry_exists(n) and registry_is_stale(n):
            queue.append({
                "kind": "inspect_stale_registry",
                "subject": n,
                "question": ("Why is %s stale? Which producer loop is "
                              "blocked or paused?" % n),
                "evidence_source": "data/registries/" + n,
                "execution_required": False,
            })

    github = load_registry("qsb_github_upgrade_candidates.json")
    if isinstance(github, dict):
        candidates = github.get("candidates") or []
        for cand in candidates[:6]:
            queue.append({
                "kind": "github_scout_review",
                "subject": (cand.get("repo")
                             or cand.get("name") or "candidate"),
                "question": ("Should this GitHub candidate be safely "
                              "imported? %s"
                              % (cand.get("summary") or "")),
                "evidence_source": ("data/registries/"
                                     "qsb_github_upgrade_candidates.json"),
                "execution_required": False,
            })

    reflection = load_registry("qsb_kernel_reflection_state.json")
    if isinstance(reflection, dict):
        for f in (reflection.get("failed_tests") or [])[:5]:
            queue.append({
                "kind": "inspect_failed_test",
                "subject": f.get("test"),
                "question": ("Why did %s report %s? Read its log."
                              % (f.get("test"), f.get("verdict"))),
                "evidence_source": f.get("log") or "data/logs/",
                "execution_required": False,
            })

    if not queue:
        queue.append({
            "kind": "monitor_steady_state",
            "subject": "kernel_cognition",
            "question": ("Nothing missing or stale; continue periodic "
                          "cognitive ticks."),
            "evidence_source": "data/registries/qsb_kernel_attention_state.json",
            "execution_required": False,
        })

    payload = {
        "module": "kernel_curiosity_queue",
        "purpose": ("List read-only inspections the kernel would like to "
                    "run next, prioritized by missing/stale evidence."),
        "timestamp_utc": utc_now_iso(),
        "queue": queue,
        "queue_length": len(queue),
        "source_file_list": [
            "data/registries/" + n for n in CURIOSITY_WATCHLIST
        ] + ["data/registries/qsb_github_upgrade_candidates.json",
             "data/registries/qsb_kernel_reflection_state.json"],
        "confidence": 0.9 if queue else 0.5,
        "warnings": [],
        "safety": safety_block(),
    }

    rel = write_registry("qsb_kernel_curiosity_queue.json", payload)
    return {"written": rel, "queue_length": len(queue)}


def main():
    print(json.dumps(run(), indent=2))
    return 0


if __name__ == "__main__":
    sys.exit(main())
