"""
QSB Tower V1.5 — EQSB Model Lane Governance
Phase: EQSB_KERNEL_MAJOR_DEEP_SYMBOLIC_QUANTUM_CORE_V1

Owns the structured model-lane registry: which lanes exist, what they
may do, and how their output is validated. Outputs Guardian-ready
verdicts: accepted / advisory_only / rejected / contradiction_detected
/ requires_human_review.
"""

import json

from tower.eqsb_kernel_core_ext import (
    EQSB_MAJOR_SCHEMA_VERSION, REG,
    now_iso, load_json, write_json, append_event,
    safety_envelope, stable_hash,
)

P_GOVERNANCE = REG / "eqsb_model_lane_governance.json"


LANES = [
    {
        "lane_id": "lane_local_ollama",
        "role": "local_advisory_speech_paraphrase",
        "isolation": "tower_venv",
        "execution_allowed": False,
        "may_unlock_gates": False,
        "registry_truth_outranks": True,
        "wired_into_autoloop": False,
        "wired_into_trading": False,
        "wired_into_openclaw": False,
        "wired_into_workers": False,
        "notes": "Local Ollama; chat paraphrase only.",
    },
    {
        "lane_id": "lane_local_llama",
        "role": "local_advisory_reasoning",
        "isolation": "tower_venv",
        "execution_allowed": False,
        "may_unlock_gates": False,
        "registry_truth_outranks": True,
        "wired_into_autoloop": False,
        "wired_into_trading": False,
        "wired_into_openclaw": False,
        "wired_into_workers": False,
        "notes": "Llama-family local models; advisory only.",
    },
    {
        "lane_id": "lane_airllm_chamber",
        "role": "isolated_advisory_reasoning",
        "isolation": "/vaults/ai/airllm_lab/.venv (separate venv)",
        "execution_allowed": False,
        "may_unlock_gates": False,
        "registry_truth_outranks": True,
        "wired_into_autoloop": False,
        "wired_into_trading": False,
        "wired_into_openclaw": False,
        "wired_into_workers": False,
        "notes": "AirLLM big-model chamber; never shares a process with QSB.",
    },
    {
        "lane_id": "lane_future_locked_provider",
        "role": "external_provider_advisory_reserved",
        "isolation": "external_https",
        "execution_allowed": False,
        "may_unlock_gates": False,
        "registry_truth_outranks": True,
        "wired_into_autoloop": False,
        "wired_into_trading": False,
        "wired_into_openclaw": False,
        "wired_into_workers": False,
        "notes": "Reserved slot for a future external provider; remains locked until separately approved.",
    },
]


VALIDATION_RULES = [
    "model output is advisory",
    "model output must be checked against registry truth",
    "model output must not overwrite structured state",
    "model output must not invent Kernel state",
    "model output must not erase uncertainty",
    "model output must not claim real quantum hardware unless verified",
    "model output must be labelled paraphrase when not registry-backed",
    "model output may never enable execution gates",
]


GOVERNANCE_OUTPUTS = [
    "accepted",
    "advisory_only",
    "rejected",
    "contradiction_detected",
    "requires_human_review",
]


def validate_lanes():
    lane_verdicts = []
    for lane in LANES:
        # By default every lane is advisory only; flag misconfiguration.
        violations = []
        if lane.get("execution_allowed") is not False:
            violations.append("execution_allowed must be False")
        if lane.get("may_unlock_gates") is not False:
            violations.append("may_unlock_gates must be False")
        if lane.get("registry_truth_outranks") is not True:
            violations.append("registry_truth_outranks must be True")
        verdict = "advisory_only" if not violations else "rejected"
        lane_verdicts.append({
            "lane_id": lane["lane_id"],
            "verdict": verdict,
            "violations": violations,
            "validated_ts": now_iso(),
        })
    return lane_verdicts


def build_model_lane_governance():
    lane_verdicts = validate_lanes()

    payload = {
        "schema_version": EQSB_MAJOR_SCHEMA_VERSION,
        "kind": "eqsb_model_lane_governance",
        "generated_ts": now_iso(),
        "lanes": LANES,
        "lane_verdicts": lane_verdicts,
        "validation_rules": VALIDATION_RULES,
        "governance_outputs": GOVERNANCE_OUTPUTS,
        "default_lane_verdict": "advisory_only",
        "kernel_truth_note": (
            "Models do not define EQSB. They paraphrase. Registry truth "
            "outranks paraphrase. Any model output that contradicts "
            "registry truth yields BLOCK_MODEL_OVERRIDE."
        ),
        "lane_count": len(LANES),
        "source_files": [
            "src/tower/eqsb_model_governance.py",
            "src/tower/local_model_inference_gateway.py",
        ],
    }
    payload.update(safety_envelope())
    payload["governance_hash"] = stable_hash([l["lane_id"] for l in LANES])
    write_json(P_GOVERNANCE, payload)
    append_event({"event": "build_model_lane_governance",
                  "lane_count": len(LANES)})
    return payload


def build():
    return build_model_lane_governance()


if __name__ == "__main__":
    print(json.dumps(build(), indent=2))
