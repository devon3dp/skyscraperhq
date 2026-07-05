"""
QSB Tower V1.5 — EQSB Hypothesis Engine
Phase: EQSB_KERNEL_MAJOR_DEEP_SYMBOLIC_QUANTUM_CORE_V1

Generates registry-driven advisory hypotheses with the deeper schema:
status (CANDIDATE/ACTIVE/SELECTED/WEAKENED/REJECTED/QUARANTINED),
evidence / counter_evidence, linked_symbols / linked_beliefs /
linked_axioms / linked_registries, entropy_impact, contradiction_impact,
quantum_weight, selection_reason, next_test.

Carries over V1 hypothesis seeds when present so the trading-context
hypotheses are preserved.
"""

import json
from datetime import datetime, timezone

from tower.eqsb_kernel_core_ext import (
    EQSB_MAJOR_SCHEMA_VERSION, REG,
    now_iso, load_json, write_json, append_event,
    safety_envelope, stable_hash,
)

P_HYPOTHESIS    = REG / "eqsb_hypothesis_state.json"
P_QUANTUM       = REG / "eqsb_quantum_signal_state.json"
P_CONTRADICTION = REG / "eqsb_contradiction_report.json"
P_ENTROPY       = REG / "eqsb_entropy_state.json"


HYPOTHESIS_STATUSES = (
    "CANDIDATE", "ACTIVE", "SELECTED", "WEAKENED", "REJECTED", "QUARANTINED",
)


def _kernel_hypotheses_from_state():
    entropy = load_json(P_ENTROPY, {})
    contradictions = load_json(P_CONTRADICTION, {})

    items = []

    items.append({
        "hypothesis_id": "hyp_kernel_state_stable",
        "statement": "Kernel state is stable.",
        "title": "Kernel state is stable",
        "status": "CANDIDATE",
        "confidence": 0.65 if (entropy.get("entropy_score") or 0) < 50 else 0.35,
        "severity": "info",
        "evidence": [
            "entropy_score=" + str(entropy.get("entropy_score")),
            "stability_score=" + str(entropy.get("stability_score")),
        ],
        "counter_evidence": [
            "contradiction_count=" + str(contradictions.get("contradiction_count")),
            "drift_score=" + str(entropy.get("drift_score")),
        ],
        "linked_symbols": ["SYMBOL_KERNEL_SELF", "SYMBOL_ENTROPY"],
        "linked_axioms": ["AXIOM_AUDIT_001"],
        "linked_registries": ["eqsb_entropy_state.json"],
        "entropy_impact": -10,
        "contradiction_impact": 0,
        "quantum_weight": 0.55,
        "selected": False,
        "selection_reason": None,
        "next_test": "Re-run entropy after next cadence tick.",
        "advisory_only": True,
    })

    items.append({
        "hypothesis_id": "hyp_kernel_introspection_registry_backed",
        "statement": "Kernel introspection is registry-backed.",
        "title": "Kernel introspection is registry-backed",
        "status": "ACTIVE",
        "confidence": 0.92,
        "severity": "info",
        "evidence": [
            "eqsb_kernel_introspection_latest.json present",
            "kernel_dialogue_adapter primary_lane=kernel_introspection",
        ],
        "counter_evidence": [],
        "linked_symbols": ["SYMBOL_REGISTRY_TRUTH", "SYMBOL_KERNEL_SELF"],
        "linked_axioms": ["AXIOM_TRUTH_001"],
        "linked_registries": ["eqsb_kernel_introspection_latest.json"],
        "entropy_impact": -5,
        "contradiction_impact": 0,
        "quantum_weight": 0.8,
        "selected": False,
        "selection_reason": None,
        "next_test": "Inspect kernel chat output for primary_lane field.",
        "advisory_only": True,
    })

    items.append({
        "hypothesis_id": "hyp_beliefs_need_review",
        "statement": "Some beliefs need review.",
        "title": "Some beliefs need review",
        "status": "CANDIDATE",
        "confidence": 0.5,
        "severity": "warning" if (contradictions.get("contradiction_count") or 0) > 0 else "info",
        "evidence": ["aging_beliefs in eqsb_belief_lifecycle"],
        "counter_evidence": [],
        "linked_symbols": ["SYMBOL_BELIEF"],
        "linked_axioms": ["AXIOM_TRUTH_002"],
        "linked_registries": ["eqsb_belief_lifecycle.json"],
        "entropy_impact": 5,
        "contradiction_impact": 0,
        "quantum_weight": 0.5,
        "selected": False,
        "selection_reason": None,
        "next_test": "Refresh belief lifecycle on next cadence tick.",
        "advisory_only": True,
    })

    items.append({
        "hypothesis_id": "hyp_entropy_rising_stale",
        "statement": "Entropy is rising due to stale state.",
        "title": "Entropy is rising due to stale state",
        "status": "CANDIDATE",
        "confidence": 0.6 if (entropy.get("drift_score") or 0) > 50 else 0.3,
        "severity": "warning" if (entropy.get("drift_score") or 0) > 50 else "info",
        "evidence": ["drift_score=" + str(entropy.get("drift_score"))],
        "counter_evidence": [],
        "linked_symbols": ["SYMBOL_ENTROPY", "SYMBOL_DRIFT"],
        "linked_axioms": ["AXIOM_ENTROPY_003"],
        "linked_registries": ["eqsb_entropy_state.json", "eqsb_continuity_state.json"],
        "entropy_impact": 20,
        "contradiction_impact": 0,
        "quantum_weight": 0.55,
        "selected": False,
        "selection_reason": None,
        "next_test": "Re-run audit; check continuity_state stale_memory_flags.",
        "advisory_only": True,
    })

    items.append({
        "hypothesis_id": "hyp_model_paraphrase_conflicts_registry",
        "statement": "A model paraphrase conflicts with registry truth.",
        "title": "A model paraphrase conflicts with registry truth",
        "status": "CANDIDATE",
        "confidence": 0.35,
        "severity": "warning",
        "evidence": [],
        "counter_evidence": ["Guardian verdicts BLOCK_MODEL_OVERRIDE not yet recorded"],
        "linked_symbols": ["SYMBOL_MODEL_PARAPHRASE", "SYMBOL_REGISTRY_TRUTH"],
        "linked_axioms": ["AXIOM_TRUTH_001", "AXIOM_GUARDIAN_002"],
        "linked_registries": ["eqsb_model_lane_governance.json",
                               "eqsb_guardian_state.json"],
        "entropy_impact": 8,
        "contradiction_impact": 10,
        "quantum_weight": 0.4,
        "selected": False,
        "selection_reason": None,
        "next_test": "Sample kernel_dialogue logs for paraphrase-vs-registry drift.",
        "advisory_only": True,
    })

    items.append({
        "hypothesis_id": "hyp_missing_registry_weakens_continuity",
        "statement": "A missing registry weakens continuity.",
        "title": "A missing registry weakens continuity",
        "status": "CANDIDATE",
        "confidence": 0.45,
        "severity": "info",
        "evidence": [],
        "counter_evidence": [],
        "linked_symbols": ["SYMBOL_CONTINUITY", "SYMBOL_REGISTRY_TRUTH"],
        "linked_axioms": ["AXIOM_CONTINUITY_001"],
        "linked_registries": ["eqsb_kernel_missing_capabilities.json"],
        "entropy_impact": 6,
        "contradiction_impact": 0,
        "quantum_weight": 0.4,
        "selected": False,
        "selection_reason": None,
        "next_test": "Re-run major_audit to refresh missing_count.",
        "advisory_only": True,
    })

    items.append({
        "hypothesis_id": "hyp_quantum_simulated_advisory",
        "statement": "Quantum signal is simulated and advisory.",
        "title": "Quantum signal is simulated and advisory",
        "status": "SELECTED",
        "confidence": 0.92,
        "severity": "info",
        "evidence": [
            "mode=simulated_quantum_entropy",
            "real_quantum_source_connected=false",
            "qiskit_connected=false",
            "ibm_quantum_connected=false",
        ],
        "counter_evidence": [],
        "linked_symbols": ["SYMBOL_QUANTUM_SIGNAL", "SYMBOL_SUPERPOSITION", "SYMBOL_COLLAPSE"],
        "linked_axioms": ["AXIOM_QUANTUM_001", "AXIOM_QUANTUM_002", "AXIOM_QUANTUM_003"],
        "linked_registries": ["eqsb_quantum_signal_state.json"],
        "entropy_impact": -5,
        "contradiction_impact": 0,
        "quantum_weight": 0.95,
        "selected": True,
        "selection_reason": "Registry truth: quantum hardware is not connected.",
        "next_test": "Verify Qiskit / IBM Quantum credentials before any promotion.",
        "advisory_only": True,
    })

    return items


def _carry_v1_hypotheses(items):
    prev = load_json(P_HYPOTHESIS, {})
    seen = {h["hypothesis_id"] for h in items}
    for h in (prev.get("hypotheses") or []):
        hid = h.get("hypothesis_id") or h.get("id")
        if hid and hid not in seen and not hid.startswith("hyp_kernel_state_stable"):
            # Keep V1's measured hypotheses (OANDA practice, etc.)
            h.setdefault("status", "CANDIDATE")
            h.setdefault("advisory_only", True)
            h.setdefault("linked_symbols", [])
            h.setdefault("linked_axioms", [])
            h.setdefault("linked_registries", [])
            h.setdefault("evidence", [])
            h.setdefault("counter_evidence", [])
            h.setdefault("quantum_weight", float(h.get("confidence", 0.4)))
            h.setdefault("entropy_impact", 0)
            h.setdefault("contradiction_impact", 0)
            h.setdefault("selected", False)
            h.setdefault("selection_reason", None)
            items.append(h)
    return items


def build_hypotheses():
    items = _kernel_hypotheses_from_state()
    items = _carry_v1_hypotheses(items)

    # Status counts + severity counts
    status_counts = {s: 0 for s in HYPOTHESIS_STATUSES}
    for h in items:
        status_counts[h.get("status", "CANDIDATE")] = (
            status_counts.get(h.get("status", "CANDIDATE"), 0) + 1
        )
    sev_counts = {}
    for h in items:
        sev_counts[h.get("severity", "info")] = sev_counts.get(h.get("severity", "info"), 0) + 1

    selected = next((h for h in items if h.get("selected")), None)

    payload = {
        "schema_version": EQSB_MAJOR_SCHEMA_VERSION,
        "kind": "eqsb_hypothesis_state",
        "generated_ts": now_iso(),
        "hypothesis_count": len(items),
        "statuses_in_use": list(HYPOTHESIS_STATUSES),
        "status_counts": status_counts,
        "by_severity": sev_counts,
        "selected_hypothesis_id": (selected or {}).get("hypothesis_id"),
        "selected_hypothesis": selected,
        "hypotheses": items,
        "source_files": [
            "data/registries/eqsb_belief_lifecycle.json",
            "data/registries/eqsb_entropy_state.json",
            "data/registries/eqsb_contradiction_report.json",
        ],
    }
    payload.update(safety_envelope())
    payload["hypothesis_hash"] = stable_hash([h["hypothesis_id"] for h in items])
    write_json(P_HYPOTHESIS, payload)
    append_event({"event": "build_hypotheses",
                  "hypothesis_count": len(items),
                  "selected": payload["selected_hypothesis_id"]})
    return payload


def build():
    return build_hypotheses()


if __name__ == "__main__":
    print(json.dumps(build(), indent=2))
