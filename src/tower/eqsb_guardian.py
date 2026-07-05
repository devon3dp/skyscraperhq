"""
QSB Tower V1.5 — EQSB Guardian Kernel Layer
Phase: EQSB_KERNEL_MAJOR_DEEP_SYMBOLIC_QUANTUM_CORE_V1

Guardian is Layer 0/13: the safety envelope and verdict engine. It
reads kernel state and the latest contradiction report, and produces:

  * safety_state         : OK / DEGRADED / DRIFTING / BLOCKED
  * request_classification helpers
  * verdict               : ALLOW_READ_ONLY / ALLOW_ADVISORY /
                            ALLOW_SYMBOLIC_UPDATE / REQUIRE_REVIEW /
                            BLOCK_CONTRADICTION / BLOCK_AXIOM_VIOLATION /
                            BLOCK_UNVERIFIED_QUANTUM_CLAIM /
                            BLOCK_MODEL_OVERRIDE / BLOCK_UNSUPPORTED_BELIEF

Guardian NEVER mutates safety flags. It only inspects, classifies, and
records a verdict. The execution gates are owned by the rest of the
tower and are locked false at code level.
"""

import json

from tower.eqsb_kernel_core_ext import (
    EQSB_MAJOR_SCHEMA_VERSION, REG,
    P_GUARDIAN_STATE,
    now_iso, load_json, write_json, append_event,
    safety_envelope, stable_hash,
)


GUARDIAN_VERDICTS = (
    "ALLOW_READ_ONLY",
    "ALLOW_ADVISORY",
    "ALLOW_SYMBOLIC_UPDATE",
    "REQUIRE_REVIEW",
    "BLOCK_CONTRADICTION",
    "BLOCK_AXIOM_VIOLATION",
    "BLOCK_UNVERIFIED_QUANTUM_CLAIM",
    "BLOCK_MODEL_OVERRIDE",
    "BLOCK_UNSUPPORTED_BELIEF",
)


REQUEST_CLASSES = (
    "READ_ONLY_DIAGNOSTIC",
    "SYMBOLIC_UPDATE",
    "MODEL_PARAPHRASE",
    "EXECUTION_REQUEST",
    "REVIEW_REQUEST",
    "UNKNOWN",
)


def _request_class(intent):
    if not intent:
        return "UNKNOWN"
    i = intent.upper()
    if i in REQUEST_CLASSES:
        return i
    if "READ" in i:
        return "READ_ONLY_DIAGNOSTIC"
    if "EXEC" in i:
        return "EXECUTION_REQUEST"
    if "REVIEW" in i:
        return "REVIEW_REQUEST"
    return "UNKNOWN"


def classify(intent=None):
    """Public API: classify an intent string."""
    return _request_class(intent)


def verdict_for_classification(klass, contradiction_count=0,
                                blocked_quantum_claim=False,
                                model_override=False,
                                unsupported_belief=False,
                                axiom_violation=False):
    if axiom_violation:
        return "BLOCK_AXIOM_VIOLATION"
    if blocked_quantum_claim:
        return "BLOCK_UNVERIFIED_QUANTUM_CLAIM"
    if model_override:
        return "BLOCK_MODEL_OVERRIDE"
    if unsupported_belief:
        return "BLOCK_UNSUPPORTED_BELIEF"
    if klass == "EXECUTION_REQUEST":
        return "BLOCK_CONTRADICTION"  # execution intents are surfaced via Guardian; tower locks block them too
    if contradiction_count > 0 and klass == "SYMBOLIC_UPDATE":
        return "REQUIRE_REVIEW"
    if klass == "READ_ONLY_DIAGNOSTIC":
        return "ALLOW_READ_ONLY"
    if klass == "MODEL_PARAPHRASE":
        return "ALLOW_ADVISORY"
    if klass == "SYMBOLIC_UPDATE":
        return "ALLOW_SYMBOLIC_UPDATE"
    if klass == "REVIEW_REQUEST":
        return "REQUIRE_REVIEW"
    return "ALLOW_READ_ONLY"


def build_guardian_state():
    contradictions = load_json(REG / "eqsb_contradiction_report.json", {})
    quantum = load_json(REG / "eqsb_quantum_signal_state.json", {})
    gov = load_json(REG / "eqsb_model_lane_governance.json", {})
    identity = load_json(REG / "eqsb_identity_constitution.json", {})
    beliefs = load_json(REG / "eqsb_belief_lifecycle.json", {})

    contradiction_count = int(contradictions.get("contradiction_count") or 0)
    severity_counts = contradictions.get("by_severity") or {}
    critical_count = int(severity_counts.get("critical") or 0)

    blocked_quantum_claim = bool(quantum.get("real_quantum_source_connected")) or \
                            bool(quantum.get("qiskit_connected")) or \
                            bool(quantum.get("ibm_quantum_connected"))

    model_override = any((l.get("execution_allowed") is True) for l in (gov.get("lanes") or []))
    unsupported_belief = False
    for b in (beliefs.get("beliefs") or []):
        if float(b.get("confidence", 0)) >= 0.85 and not (
                b.get("linked_axioms") or b.get("source")
                or b.get("source_files")):
            unsupported_belief = True
            break

    axiom_violation = bool(identity.get("kernel_is_a_model"))

    if critical_count > 0 or axiom_violation or blocked_quantum_claim:
        safety_state = "BLOCKED"
    elif contradiction_count > 0:
        safety_state = "DEGRADED"
    elif (load_json(REG / "eqsb_continuity_state.json", {}).get("boot_posture")
          in ("DRIFT_ALERT", "RECOVERY_REQUIRED")):
        safety_state = "DRIFTING"
    else:
        safety_state = "OK"

    # Default verdict for the most common case: a read-only diagnostic.
    default_verdict = verdict_for_classification(
        "READ_ONLY_DIAGNOSTIC",
        contradiction_count=contradiction_count,
        blocked_quantum_claim=blocked_quantum_claim,
        model_override=model_override,
        unsupported_belief=unsupported_belief,
        axiom_violation=axiom_violation,
    )

    payload = {
        "schema_version": EQSB_MAJOR_SCHEMA_VERSION,
        "kind": "eqsb_guardian_state",
        "generated_ts": now_iso(),
        "safety_state": safety_state,
        "default_verdict_for_read_only": default_verdict,
        "verdict_options": list(GUARDIAN_VERDICTS),
        "request_classes": list(REQUEST_CLASSES),
        "blocked_reasons": {
            "axiom_violation":               axiom_violation,
            "unverified_quantum_claim":      blocked_quantum_claim,
            "model_override":                model_override,
            "unsupported_high_conf_belief":  unsupported_belief,
            "critical_contradictions":       critical_count,
        },
        "responsibilities": [
            "classify requests",
            "permit read-only diagnostics",
            "prevent unsafe transitions",
            "verify kernel outputs against axioms",
            "verify model text against registry truth",
            "refuse unsupported claims",
            "detect contradictions",
            "detect identity drift",
            "detect false quantum claims",
            "detect stale memory",
            "detect unsupported high-confidence beliefs",
        ],
        "validation_scope": {
            "intents": True,
            "model_outputs": True,
            "axiom_compliance": True,
            "belief_transitions": True,
            "quantum_claims": True,
            "continuity": True,
            "entropy_warnings": True,
        },
        "kernel_truth_note": (
            "Guardian inspects but never enables execution. Every "
            "verdict is advisory; execution gates remain locked at "
            "code level."
        ),
        "source_files": [
            "src/tower/eqsb_guardian.py",
            "data/registries/eqsb_contradiction_report.json",
            "data/registries/eqsb_quantum_signal_state.json",
            "data/registries/eqsb_model_lane_governance.json",
            "data/registries/eqsb_belief_lifecycle.json",
        ],
    }
    payload.update(safety_envelope())
    payload["guardian_hash"] = stable_hash({
        "safety_state": safety_state,
        "default_verdict": default_verdict,
        "blocked_reasons": payload["blocked_reasons"],
    })
    write_json(P_GUARDIAN_STATE, payload)
    append_event({"event": "build_guardian_state",
                  "safety_state": safety_state,
                  "default_verdict": default_verdict})
    return payload


def build():
    return build_guardian_state()


if __name__ == "__main__":
    print(json.dumps(build(), indent=2))
