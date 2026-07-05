"""kernel_attention_layer.py

Cognitive Attention layer for the QSB Kernel (advisory only).

Reads the perception snapshot plus a few authoritative registries and
ranks current priorities. Detects:
    - missing cognitive registries
    - missing smoke scripts
    - stale telemetry
    - Godot visual polish incomplete
    - CUDA unavailable in ML/RL lab
    - banking real-money NOT_READY
    - GitHub scout pending safe import
    - Kernel uncertainty fallback risk
    - safety lock risk
    - missing floor interiors
    - OpenClaw tickets

Writes:
    data/registries/qsb_kernel_attention_state.json

Never executes anything. Never proposes flipping execution locks.
"""

from pathlib import Path
import json
import sys

from tower.kernel_cognitive_common import (
    REG, ROOT, load_registry, registry_exists, registry_is_stale,
    safety_block, utc_now_iso, write_registry,
)


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

COGNITIVE_SCRIPTS = [
    "scripts/qsb_kernel_cognitive_tick.sh",
    "scripts/qsb_kernel_cognitive_status.sh",
    "scripts/qsb_kernel_cognitive_smoke_test.sh",
]

SEVERITY_RANK = {"critical": 0, "high": 1, "medium": 2, "low": 3, "info": 4}


def _add(items, issue, severity, evidence_source, recommended_action,
         safety_boundary="all_execution_locks_remain_closed"):
    items.append({
        "issue": issue,
        "severity": severity,
        "evidence_source": evidence_source,
        "recommended_action": recommended_action,
        "safety_boundary": safety_boundary,
    })


def _detect_cognitive_gaps(items):
    for n in COGNITIVE_REGISTRIES:
        if not registry_exists(n):
            _add(items,
                 issue="cognitive_registry_missing:" + n,
                 severity="high",
                 evidence_source="data/registries/" + n,
                 recommended_action="./scripts/qsb_kernel_cognitive_tick.sh")
    for s in COGNITIVE_SCRIPTS:
        if not (ROOT / s).exists():
            _add(items,
                 issue="cognitive_script_missing:" + s,
                 severity="high",
                 evidence_source=s,
                 recommended_action="Create " + s)


def _detect_stale_telemetry(items):
    candidates = [
        "qsb_godot_live_telemetry_status.json",
        "qsb_kernel_thinking_upgrade_probe_latest.json",
        "qsb_kernel_learning_smoke_test_v2_latest.json",
        "eqsb_kernel_learning_loop.json",
        "eqsb_code_observatory.json",
        "eqsb_hardware_observatory.json",
    ]
    for n in candidates:
        if registry_exists(n) and registry_is_stale(n):
            _add(items,
                 issue="stale_telemetry:" + n,
                 severity="medium",
                 evidence_source="data/registries/" + n,
                 recommended_action=(
                     "Refresh the source loop that produces " + n))


def _detect_godot_polish(items):
    layout = load_registry("qsb_godot_professional_layout_score.json")
    score = load_registry("qsb_godot_primary_professional_score.json")
    for label, data in (("layout", layout), ("professional", score)):
        if not isinstance(data, dict):
            continue
        verdict = (data.get("verdict") or data.get("status") or "").lower()
        passed = data.get("passed") or data.get("passed_count")
        total = data.get("total") or data.get("total_count")
        if verdict and verdict not in ("pass", "complete", "ok", "ready"):
            _add(items,
                 issue="godot_visual_polish_incomplete:" + label,
                 severity="medium",
                 evidence_source=("data/registries/qsb_godot_"
                                   + label + "_score.json"),
                 recommended_action="Complete Godot visual polish gates")
        elif (isinstance(passed, int) and isinstance(total, int)
              and total > 0 and passed < total):
            _add(items,
                 issue=("godot_visual_polish_incomplete:%s gates %d/%d"
                        % (label, passed, total)),
                 severity="medium",
                 evidence_source=("data/registries/qsb_godot_"
                                   + label + "_score.json"),
                 recommended_action="Close remaining Godot visual gates")


def _detect_ml_rl(items):
    torch = load_registry("qsb_ml_rl_torch_status.json")
    if not isinstance(torch, dict):
        return
    cuda_available = torch.get("cuda_available")
    if cuda_available is False:
        _add(items,
             issue="ml_rl_cuda_unavailable",
             severity="low",
             evidence_source="data/registries/qsb_ml_rl_torch_status.json",
             recommended_action="Run ML/RL lab in CPU mode; defer CUDA")
    if torch.get("torch_installed") is False:
        _add(items,
             issue="ml_rl_torch_not_installed",
             severity="low",
             evidence_source="data/registries/qsb_ml_rl_torch_status.json",
             recommended_action=(
                 "Install torch only inside the AirLLM venv per separation"))


def _detect_banking(items):
    real = load_registry(
        "qsb_banking_gateway_real_money_phase_requirements.json")
    if not isinstance(real, dict):
        return
    status = (real.get("status") or real.get("verdict") or "").upper()
    if status and status != "READY":
        _add(items,
             issue="banking_real_money_not_ready:" + status,
             severity="medium",
             evidence_source=("data/registries/"
                              "qsb_banking_gateway_real_money_phase_"
                              "requirements.json"),
             recommended_action=("Keep real money locked; review preconditions "
                                  "before any unlock decision"))
    elif not status:
        _add(items,
             issue="banking_real_money_status_unknown",
             severity="medium",
             evidence_source=("data/registries/"
                              "qsb_banking_gateway_real_money_phase_"
                              "requirements.json"),
             recommended_action=(
                 "Populate real_money phase requirements registry"))


def _detect_github_scout(items):
    plan = load_registry("qsb_github_upgrade_import_plan.json")
    if isinstance(plan, dict):
        pending = (plan.get("pending_safe_imports")
                   or plan.get("pending") or [])
        if pending:
            _add(items,
                 issue="github_scout_pending_safe_imports:%d" % len(pending),
                 severity="low",
                 evidence_source=("data/registries/"
                                   "qsb_github_upgrade_import_plan.json"),
                 recommended_action=(
                     "Review pending safe imports; do not auto-merge"))


def _detect_uncertainty_route(items):
    refl = load_registry("qsb_kernel_reflection_state.json")
    if not refl:
        _add(items,
             issue="uncertainty_route_unrepaired",
             severity="critical",
             evidence_source="data/registries/qsb_kernel_reflection_state.json",
             recommended_action=(
                 "Run ./scripts/qsb_kernel_cognitive_tick.sh to write "
                 "the reflection state and unlock the uncertainty route"))


def _detect_safety(items):
    clearance = load_registry(
        "security_spine_kernel_clearance_status.json")
    if isinstance(clearance, dict):
        cleared = (clearance.get("cleared")
                   or clearance.get("status") == "CLEARED")
        if not cleared and clearance:
            _add(items,
                 issue="security_spine_kernel_clearance_not_cleared",
                 severity="medium",
                 evidence_source=("data/registries/"
                                   "security_spine_kernel_clearance_status.json"),
                 recommended_action=(
                     "Re-run security spine clearance audit"))


def _detect_floors(items):
    sky = load_registry("qsb_3d_skyscraper_state.json")
    if isinstance(sky, dict):
        floors = sky.get("floors") or []
        missing_interiors = [
            f.get("number") for f in floors
            if isinstance(f, dict)
            and (f.get("interior_complete") is False
                 or f.get("interior") == "missing")
        ]
        if missing_interiors:
            _add(items,
                 issue=("missing_floor_interiors:%d floors"
                        % len(missing_interiors)),
                 severity="low",
                 evidence_source=("data/registries/"
                                   "qsb_3d_skyscraper_state.json"),
                 recommended_action="Add interior renders for floors")


def _detect_openclaw_tickets(items):
    sup = load_registry("qsb_kernel_opencore_supervision_state.json")
    tickets = []
    if isinstance(sup, dict):
        tickets = sup.get("open_tickets") or []
    if not tickets:
        # also check a generic registry if present
        oc = load_registry("openclaw_tickets.json", fallback=[])
        if isinstance(oc, list):
            tickets = oc
    if tickets:
        _add(items,
             issue="openclaw_tickets_open:%d" % len(tickets),
             severity="medium",
             evidence_source=("data/registries/"
                              "qsb_kernel_opencore_supervision_state.json"),
             recommended_action=(
                 "OpenClaw inspection: triage open supervision tickets"))


def run():
    items = []
    _detect_cognitive_gaps(items)
    _detect_stale_telemetry(items)
    _detect_godot_polish(items)
    _detect_ml_rl(items)
    _detect_banking(items)
    _detect_github_scout(items)
    _detect_uncertainty_route(items)
    _detect_safety(items)
    _detect_floors(items)
    _detect_openclaw_tickets(items)

    items.sort(key=lambda x: SEVERITY_RANK.get(x.get("severity"), 9))
    for i, it in enumerate(items, start=1):
        it["priority_rank"] = i

    sources = (COGNITIVE_REGISTRIES + [
        "qsb_godot_professional_layout_score.json",
        "qsb_godot_primary_professional_score.json",
        "qsb_godot_live_telemetry_status.json",
        "qsb_ml_rl_torch_status.json",
        "qsb_banking_gateway_real_money_phase_requirements.json",
        "qsb_github_upgrade_import_plan.json",
        "security_spine_kernel_clearance_status.json",
        "qsb_3d_skyscraper_state.json",
    ])

    payload = {
        "module": "kernel_attention_layer",
        "purpose": ("Rank current priorities for the kernel based on real "
                    "registry signals. Read-only; never proposes execution."),
        "timestamp_utc": utc_now_iso(),
        "priority_items": items,
        "priority_count": len(items),
        "severity_counts": {
            "critical": sum(1 for x in items if x["severity"] == "critical"),
            "high":     sum(1 for x in items if x["severity"] == "high"),
            "medium":   sum(1 for x in items if x["severity"] == "medium"),
            "low":      sum(1 for x in items if x["severity"] == "low"),
            "info":     sum(1 for x in items if x["severity"] == "info"),
        },
        "source_file_list": ["data/registries/" + n for n in sources],
        "confidence": 0.9 if items else 0.5,
        "warnings": [
            it["issue"] for it in items
            if it["severity"] in ("critical", "high")
        ],
        "safety": safety_block(),
    }

    rel = write_registry("qsb_kernel_attention_state.json", payload)
    return {"written": rel, "priority_count": len(items)}


def main():
    print(json.dumps(run(), indent=2))
    return 0


if __name__ == "__main__":
    sys.exit(main())
