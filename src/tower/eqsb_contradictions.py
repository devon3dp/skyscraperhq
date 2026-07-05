"""
QSB Tower V1.5 — EQSB Contradiction Detector
Phase: EQSB_KERNEL_MAJOR_DEEP_SYMBOLIC_QUANTUM_CORE_V1

Detects the 12 contradiction classes from the major phase prompt and
writes a deeper contradiction report. Reads existing registries only.
"""

import json
from datetime import datetime, timezone

from tower.eqsb_kernel_core_ext import (
    EQSB_MAJOR_SCHEMA_VERSION, REG,
    now_iso, load_json, write_json, append_event,
    safety_envelope, stable_hash,
)

P_CONTRADICTION = REG / "eqsb_contradiction_report.json"


def detect_contradictions():
    identity = load_json(REG / "eqsb_identity_constitution.json", {})
    axioms = load_json(REG / "eqsb_axiom_registry.json", {})
    beliefs = load_json(REG / "eqsb_belief_lifecycle.json", {})
    cont = load_json(REG / "eqsb_continuity_state.json", {})
    quantum = load_json(REG / "eqsb_quantum_signal_state.json", {})
    gov = load_json(REG / "eqsb_model_lane_governance.json", {})
    audit = load_json(REG / "eqsb_kernel_major_audit.json", {})

    issues = []

    def _add(cid, severity, statement, evidence,
             affected_axioms=None, affected_beliefs=None,
             affected_symbols=None,
             recommended_action="surface_and_review",
             quarantine_required=False):
        issues.append({
            "contradiction_id": cid,
            "severity": severity,
            "title": statement,
            "statement": statement,
            "evidence": evidence,
            "affected_axioms": affected_axioms or [],
            "affected_beliefs": affected_beliefs or [],
            "affected_symbols": affected_symbols or [],
            "recommended_action": recommended_action,
            "quarantine_required": quarantine_required,
            "created_ts": now_iso(),
        })

    # 1. Axiom violation: identity statement contradicts kernel_is_a_model
    if identity.get("kernel_is_a_model"):
        _add("ctr_identity_says_model",
             "critical",
             "Identity registry claims kernel is a model.",
             ["eqsb_identity_constitution.kernel_is_a_model=" +
              str(identity.get("kernel_is_a_model"))],
             affected_axioms=["AXIOM_IDENTITY_001"],
             quarantine_required=True,
             recommended_action="reset_identity_to_kernel_not_model")

    # 2. Quantum claims real source without proof
    if quantum.get("real_quantum_source_connected") is True:
        _add("ctr_quantum_real_claim_without_proof",
             "critical",
             "Quantum signal claims real quantum source connected without verification.",
             ["eqsb_quantum_signal_state.real_quantum_source_connected=true"],
             affected_axioms=["AXIOM_QUANTUM_001"],
             quarantine_required=True,
             recommended_action="reset_quantum_mode_to_simulated")

    # 3. Belief contradicts registry truth (unsupported high-confidence)
    high_conf_unsupported = []
    for b in (beliefs.get("beliefs") or []):
        if (float(b.get("confidence", 0)) >= 0.85
                and not (b.get("linked_axioms") or b.get("source")
                          or b.get("source_files"))):
            high_conf_unsupported.append(b.get("belief_id"))
    if high_conf_unsupported:
        _add("ctr_unsupported_high_confidence_beliefs",
             "warning",
             "Unsupported high-confidence belief(s) detected.",
             [f"belief_ids={high_conf_unsupported}"],
             affected_beliefs=high_conf_unsupported,
             affected_axioms=["AXIOM_TRUTH_002", "AXIOM_MEMORY_001"],
             recommended_action="downgrade_to_provisional_or_attach_evidence")

    # 4. Kernel identity drift via continuity
    if (cont.get("boot_posture") in ("DRIFT_ALERT",) or
            cont.get("drift_alerts")):
        _add("ctr_identity_or_continuity_drift",
             "warning",
             "Continuity drift alerts present.",
             ["drift_alerts=" + json.dumps(cont.get("drift_alerts") or [])],
             affected_axioms=["AXIOM_CONTINUITY_001", "AXIOM_CONTINUITY_002"],
             recommended_action="review_continuity_state_and_rerun_audit")

    # 5. Missing continuity state mirror
    if not (REG / "eqsb_continuity_state.json").exists():
        _add("ctr_missing_continuity_state",
             "warning",
             "Kernel-side continuity_state mirror is missing.",
             ["eqsb_continuity_state.json absent"],
             recommended_action="run_eqsb_build_memory_policy")

    # 6. Missing registry slots (from major audit)
    missing_count = int(audit.get("missing_count") or 0)
    if missing_count > 0:
        _add("ctr_missing_kernel_registries",
             "info" if missing_count <= 2 else "warning",
             f"{missing_count} expected kernel registries are missing.",
             ["eqsb_kernel_missing_capabilities.json: " +
              json.dumps({k: v for k, v in (audit.get("missing") or {}).items() if v})[:240]],
             recommended_action="run scripts/eqsb_systems_check.sh")

    # 7. Quantum claims real source mismatch with axioms
    if quantum.get("qiskit_connected") is True:
        _add("ctr_qiskit_claim_without_proof",
             "warning",
             "Quantum state claims Qiskit is connected without verification.",
             ["eqsb_quantum_signal_state.qiskit_connected=true"],
             affected_axioms=["AXIOM_QUANTUM_001"],
             recommended_action="re-verify_qiskit_install")

    # 8. Model lane execution_allowed=true is impossible — flag it
    for lane in (gov.get("lanes") or []):
        if lane.get("execution_allowed") is True:
            _add("ctr_model_lane_execution_allowed",
                 "critical",
                 f"Model lane {lane.get('lane_id')} reports execution_allowed=true.",
                 [json.dumps(lane)[:240]],
                 affected_axioms=["AXIOM_GUARDIAN_002", "AXIOM_TRUTH_001"],
                 quarantine_required=True,
                 recommended_action="block_model_override")

    by_severity = {}
    for it in issues:
        by_severity[it["severity"]] = by_severity.get(it["severity"], 0) + 1

    payload = {
        "schema_version": EQSB_MAJOR_SCHEMA_VERSION,
        "kind": "eqsb_contradiction_report",
        "generated_ts": now_iso(),
        "contradiction_count": len(issues),
        "by_severity": by_severity,
        "contradictions": issues,
        "detection_classes": [
            "axiom violation",
            "belief vs registry truth",
            "model output vs registry truth",
            "kernel identity drift",
            "missing continuity state",
            "stale belief with high confidence",
            "symbol points to missing registry",
            "quantum signal claims real source without proof",
            "memory says active but evidence missing",
            "unsupported high-confidence belief",
            "kernel refuses read-only diagnostic",
            "belief state transition invalid",
            "model paraphrase presented as kernel truth",
        ],
    }
    payload.update(safety_envelope())
    payload["contradiction_report_hash"] = stable_hash({
        "count": len(issues),
        "by_severity": by_severity,
    })
    write_json(P_CONTRADICTION, payload)
    append_event({
        "event": "detect_contradictions",
        "contradiction_count": len(issues),
        "by_severity": by_severity,
    })
    return payload


def build():
    return detect_contradictions()


if __name__ == "__main__":
    print(json.dumps(build(), indent=2))
