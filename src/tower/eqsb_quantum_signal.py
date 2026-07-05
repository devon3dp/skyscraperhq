"""
QSB Tower V1.5 — EQSB Quantum-Symbolic Signal Engine
Phase: EQSB_KERNEL_MAJOR_DEEP_SYMBOLIC_QUANTUM_CORE_V1

Quantum-symbolic concepts (used here as advisory uncertainty modeling):
  * symbolic superposition = multiple competing hypotheses
  * amplitude               = hypothesis weight / confidence
  * measurement             = evidence check
  * collapse                = selected advisory hypothesis
  * decoherence             = contradiction / stale evidence reducing confidence
  * entanglement            = strong symbolic correlation between nodes
  * uncertainty             = entropy-driven ambiguity

This module is brutally truthful:

  * mode = simulated_quantum_entropy
  * real_quantum_source_connected = False
  * qiskit_connected              = False
  * ibm_quantum_connected         = False
  * quantum_hardware_active       = False
  * advisory_only                 = True

No external service calls. No installs. Nothing here can ever drive
execution.
"""

import hashlib
import importlib
import json
from datetime import datetime, timezone
from pathlib import Path

from tower.eqsb_kernel_core_ext import (
    EQSB_MAJOR_SCHEMA_VERSION, ROOT, REG,
    now_iso, load_json, write_json, append_event,
    safety_envelope, stable_hash,
)

P_QUANTUM       = REG / "eqsb_quantum_signal_state.json"
P_QUANTUM_ROAD  = REG / "eqsb_quantum_roadmap.json"


def _entropy_seed():
    """Build a deterministic seed from a registry-state snapshot. Never
    contacts external services. Never uses os.urandom."""
    sample_paths = [
        REG / "eqsb_belief_lifecycle.json",
        REG / "eqsb_contradiction_report.json",
        REG / "eqsb_entropy_state.json",
        REG / "eqsb_continuity_state.json",
    ]
    h = hashlib.sha256()
    for p in sample_paths:
        if p.exists():
            try:
                h.update(p.read_bytes())
            except Exception:
                pass
    h.update(now_iso().encode("utf-8"))
    return "sha256:" + h.hexdigest()[:24]


def _qiskit_present():
    """Honest local probe. Does not import or instantiate Qiskit. Just
    reports whether it could be imported from this venv."""
    try:
        spec = importlib.util.find_spec("qiskit")
        return spec is not None
    except Exception:
        return False


def _hypotheses_for_superposition():
    """Build advisory hypotheses from kernel state — not from a model."""
    hypotheses = load_json(REG / "eqsb_hypothesis_state.json", {})
    candidates = []
    for h in (hypotheses.get("hypotheses") or [])[:8]:
        candidates.append({
            "label": h.get("title") or h.get("statement") or "hypothesis",
            "hypothesis_id": h.get("hypothesis_id") or h.get("id"),
            "weight": float(h.get("confidence", 0.5)),
            "advisory_only": True,
        })

    if not candidates:
        candidates = [
            {"label": "Kernel state is stable.",
             "hypothesis_id": "hyp_kernel_stable",
             "weight": 0.55, "advisory_only": True},
            {"label": "Some beliefs need review.",
             "hypothesis_id": "hyp_beliefs_need_review",
             "weight": 0.5, "advisory_only": True},
            {"label": "Entropy is rising due to stale state.",
             "hypothesis_id": "hyp_entropy_rising_stale",
             "weight": 0.45, "advisory_only": True},
            {"label": "A missing registry weakens continuity.",
             "hypothesis_id": "hyp_missing_registry_weakens_continuity",
             "weight": 0.4, "advisory_only": True},
            {"label": "Quantum signal is simulated and advisory.",
             "hypothesis_id": "hyp_quantum_simulated_advisory",
             "weight": 0.8, "advisory_only": True},
        ]
    # Normalize weights
    total = sum(c["weight"] for c in candidates) or 1.0
    for c in candidates:
        c["normalized_weight"] = round(c["weight"] / total, 4)
    return candidates


def _select_hypothesis(candidates):
    """Symbolic collapse: pick the highest weight; record collapse reason."""
    if not candidates:
        return None, "no_candidates"
    chosen = max(candidates, key=lambda c: c.get("normalized_weight", 0))
    reason = ("highest normalized weight after registry-evidence measurement; "
              "collapse is advisory only and has no execution link")
    return chosen, reason


def compute_quantum_signal():
    candidates = _hypotheses_for_superposition()
    selected, collapse_reason = _select_hypothesis(candidates)

    entropy = load_json(REG / "eqsb_entropy_state.json", {})
    contradictions = load_json(REG / "eqsb_contradiction_report.json", {})

    # decoherence_factors: things eroding confidence in the selected hypothesis
    decoherence_factors = []
    if (contradictions.get("contradiction_count") or 0) > 0:
        decoherence_factors.append("contradictions present")
    if (entropy.get("drift_score") or 0) > 50:
        decoherence_factors.append("high drift score")
    if (entropy.get("urgency_score") or 0) > 60:
        decoherence_factors.append("high urgency score")
    if not decoherence_factors:
        decoherence_factors.append("none observed")

    entangled_symbols = [
        ["SYMBOL_KERNEL_SELF", "SYMBOL_GUARDIAN"],
        ["SYMBOL_AXIOM", "SYMBOL_BELIEF"],
        ["SYMBOL_BELIEF", "SYMBOL_CONTRADICTION"],
        ["SYMBOL_QUANTUM_SIGNAL", "SYMBOL_HYPOTHESIS"],
        ["SYMBOL_ENTROPY", "SYMBOL_DRIFT"],
    ]

    qiskit_available = _qiskit_present()

    payload = {
        "schema_version": EQSB_MAJOR_SCHEMA_VERSION,
        "kind": "eqsb_quantum_signal_state",
        "generated_ts": now_iso(),
        "mode": "simulated_quantum_entropy",
        "real_quantum_source_connected": False,
        "qiskit_connected": False,
        "qiskit_importable_in_venv": qiskit_available,
        "ibm_quantum_connected": False,
        "quantum_hardware_active": False,
        "advisory_only": True,
        "no_external_quantum_calls": True,
        "no_quantum_trading_decisions": True,
        "execution_link": False,
        "entropy_seed_source": _entropy_seed(),
        "superposition_hypotheses": candidates,
        "selected_hypothesis": selected,
        "collapse_reason": collapse_reason,
        "decoherence_factors": decoherence_factors,
        "entangled_symbols": entangled_symbols,
        "confidence_distribution": [c["normalized_weight"] for c in candidates],
        "uncertainty_score": round(1.0 - (selected or {}).get("normalized_weight", 0), 4),
        "last_measurement_ts": now_iso(),
        "kernel_truth_note": (
            "This signal is symbolic uncertainty modeling. EQSB never "
            "claims real quantum hardware unless verified. Collapse is "
            "advisory and has no execution link."
        ),
    }
    payload.update(safety_envelope())
    payload["quantum_signal_hash"] = stable_hash({
        "selected": (selected or {}).get("hypothesis_id"),
        "mode": payload["mode"],
        "uncertainty_score": payload["uncertainty_score"],
    })
    write_json(P_QUANTUM, payload)
    append_event({
        "event": "compute_quantum_signal",
        "mode": payload["mode"],
        "selected": (selected or {}).get("hypothesis_id"),
        "uncertainty_score": payload["uncertainty_score"],
    })
    return payload


def build_quantum_roadmap():
    payload = {
        "schema_version": EQSB_MAJOR_SCHEMA_VERSION,
        "kind": "eqsb_quantum_roadmap",
        "generated_ts": now_iso(),
        "stages": [
            {"stage": 1, "name": "local simulated entropy",
             "status": "active"},
            {"stage": 2, "name": "Qiskit simulator (only if installed safely later)",
             "status": "deferred"},
            {"stage": 3, "name": "IBM Quantum entropy tap (only with explicit credentials and approval later)",
             "status": "deferred"},
            {"stage": 4, "name": "quantum entropy audit trail",
             "status": "deferred"},
            {"stage": 5, "name": "quantum-symbolic hypothesis weighting",
             "status": "active (simulated)"},
            {"stage": 6, "name": "quantum signal visualization",
             "status": "active (dashboard meter)"},
            {"stage": 7, "name": "execution linkage",
             "status": "permanently_locked",
             "note": "Never unlocked without a separate explicit gate."},
        ],
        "current_stage": 1,
        "execution_linkage": False,
    }
    payload.update(safety_envelope())
    write_json(P_QUANTUM_ROAD, payload)
    return payload


def build():
    build_quantum_roadmap()
    return compute_quantum_signal()


if __name__ == "__main__":
    print(json.dumps(build(), indent=2))
