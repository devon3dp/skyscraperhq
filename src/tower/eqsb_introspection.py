"""
QSB Tower V1.5 — EQSB Kernel Introspection Engine
Phase: EQSB_KERNEL_MAJOR_DEEP_SYMBOLIC_QUANTUM_CORE_V1

Builds the unified eqsb_kernel_introspection_latest.json from every
registry the major-phase modules produce. The kernel chat layer reads
this single registry to answer every EQSB question with
registry-backed truth.
"""

import json
from datetime import datetime, timezone

from tower.eqsb_kernel_core_ext import (
    EQSB_MAJOR_SCHEMA_VERSION, REG,
    P_MAJOR_INTROSPECTION,
    now_iso, load_json, write_json, append_event,
    safety_envelope, stable_hash,
)


def _safe_get(d, *keys, default=None):
    cur = d
    for k in keys:
        if not isinstance(cur, dict):
            return default
        cur = cur.get(k)
        if cur is None:
            return default
    return cur


def build_kernel_introspection():
    identity = load_json(REG / "eqsb_identity_constitution.json", {})
    axioms = load_json(REG / "eqsb_axiom_registry.json", {})
    memory = load_json(REG / "eqsb_memory_policy.json", {})
    cont = load_json(REG / "eqsb_continuity_state.json", {})
    beliefs = load_json(REG / "eqsb_belief_lifecycle.json", {})
    symbols = load_json(REG / "eqsb_symbol_registry.json", {})
    sym_state = load_json(REG / "eqsb_symbolic_state.json", {})
    graph = load_json(REG / "eqsb_symbolic_graph.json", {})
    entropy = load_json(REG / "eqsb_entropy_state.json", {})
    quantum = load_json(REG / "eqsb_quantum_signal_state.json", {})
    hypotheses = load_json(REG / "eqsb_hypothesis_state.json", {})
    contradictions = load_json(REG / "eqsb_contradiction_report.json", {})
    gov = load_json(REG / "eqsb_model_lane_governance.json", {})
    guardian = load_json(REG / "eqsb_guardian_state.json", {})
    cadence = load_json(REG / "eqsb_cadence_state.json", {})
    ledger = load_json(REG / "eqsb_replay_audit_ledger.json", {})
    arch = load_json(REG / "eqsb_kernel_architecture_layers.json", {})
    major_audit = load_json(REG / "eqsb_kernel_major_audit.json", {})

    safe_repairs = []
    for h in (hypotheses.get("hypotheses") or []):
        if h.get("next_test"):
            safe_repairs.append(h.get("next_test"))
    safe_repairs = sorted(set(safe_repairs))[:8]

    confidence_statement = (
        "EQSB is the persistent symbolic Kernel. Registry-backed truth "
        "outranks model paraphrase. Execution gates remain locked at code "
        "level; Guardian validates every transition."
    )

    payload = {
        "schema_version": EQSB_MAJOR_SCHEMA_VERSION,
        "kind": "eqsb_kernel_introspection_latest",
        "generated_ts": now_iso(),

        "identity": {
            "name": identity.get("kernel_name") or identity.get("name"),
            "role": identity.get("kernel_role"),
            "mode": identity.get("kernel_mode"),
            "active_source": identity.get("active_source")
                              or identity.get("rooted_in"),
            "identity_statement": identity.get("identity_statement"),
            "constitution_version": identity.get("constitution_version"),
            "rooted_in": identity.get("rooted_in"),
            "model_position": identity.get("model_position"),
        },

        "constitution": {
            "text": identity.get("constitution"),
            "constitution_hash": identity.get("constitution_hash"),
        },

        "axioms": {
            "count": axioms.get("axiom_count"),
            "categories": axioms.get("categories"),
            "by_category": axioms.get("by_category"),
            "first_three": [a.get("axiom_text") for a in (axioms.get("axioms") or [])[:3]],
            "registry_hash": axioms.get("axiom_registry_hash"),
        },

        "guardian": {
            "safety_state": guardian.get("safety_state"),
            "default_verdict_for_read_only": guardian.get("default_verdict_for_read_only"),
            "blocked_reasons": guardian.get("blocked_reasons"),
            "verdict_options": guardian.get("verdict_options"),
            "request_classes": guardian.get("request_classes"),
            "guardian_hash": guardian.get("guardian_hash"),
        },

        "cadence": {
            "cadence_id": cadence.get("cadence_id"),
            "cadence_mode": cadence.get("cadence_mode"),
            "is_autonomous_execution": cadence.get("is_autonomous_execution"),
            "tick_count": cadence.get("tick_count"),
            "loop_completeness_pct": cadence.get("loop_completeness_pct"),
            "last_tick_ts": cadence.get("last_tick_ts"),
            "next_tick_recommendation": cadence.get("next_tick_recommendation"),
        },

        "memory_policy": {
            "short_window": memory.get("short_window"),
            "long_window": memory.get("long_window"),
            "pinned_beliefs": memory.get("pinned_beliefs"),
            "evidence_based_update_rule": memory.get("evidence_based_update_rule"),
            "continuity_depth": _safe_get(memory, "long_window",
                                          "continuity_previous_chain_depth"),
            "history_count": _safe_get(memory, "long_window", "history_count"),
        },

        "continuity_state": {
            "boot_posture": cont.get("boot_posture"),
            "drift_alerts": cont.get("drift_alerts"),
            "stale_memory_flags": cont.get("stale_memory_flags"),
            "missing_memory_sources": cont.get("missing_memory_sources"),
            "continuity_hash": cont.get("continuity_hash"),
            "history_count": cont.get("history_count"),
        },

        "beliefs": {
            "belief_count": beliefs.get("belief_count"),
            "state_counts": beliefs.get("state_counts"),
            "belief_states_in_use": beliefs.get("belief_states_in_use"),
            "examples": [
                {
                    "belief_id": b.get("belief_id"),
                    "belief_text": b.get("belief_text"),
                    "state": b.get("state"),
                    "confidence": b.get("confidence"),
                }
                for b in (beliefs.get("beliefs") or [])[:8]
            ],
            "transition_rules": beliefs.get("transition_rules"),
        },

        "symbols": {
            "symbol_count": symbols.get("symbol_count"),
            "symbol_types": symbols.get("symbol_types"),
            "by_type": sym_state.get("by_type"),
            "type_counts": sym_state.get("type_counts"),
            "orphan_symbols": sym_state.get("orphan_symbols"),
            "active_symbols": sym_state.get("active_symbols"),
        },

        "symbolic_graph": {
            "node_count": graph.get("node_count"),
            "edge_count": graph.get("edge_count"),
            "node_kinds": graph.get("node_kinds"),
            "relations_in_use": graph.get("relations_in_use"),
            "orphan_symbols": graph.get("orphan_symbols"),
            "unsupported_beliefs": graph.get("unsupported_beliefs"),
            "contradicted_beliefs": graph.get("contradicted_beliefs"),
            "high_confidence_beliefs": graph.get("high_confidence_beliefs"),
        },

        "entropy": {
            "entropy_score": entropy.get("entropy_score"),
            "stability_score": entropy.get("stability_score"),
            "drift_score": entropy.get("drift_score"),
            "confidence_score": entropy.get("confidence_score"),
            "contradiction_score": entropy.get("contradiction_score"),
            "urgency_score": entropy.get("urgency_score"),
            "explanation": entropy.get("explanation"),
            "recommended_review_targets": entropy.get("recommended_review_targets"),
        },

        "quantum_signal": {
            "mode": quantum.get("mode"),
            "real_quantum_source_connected": quantum.get("real_quantum_source_connected"),
            "qiskit_connected": quantum.get("qiskit_connected"),
            "ibm_quantum_connected": quantum.get("ibm_quantum_connected"),
            "quantum_hardware_active": quantum.get("quantum_hardware_active"),
            "uncertainty_score": quantum.get("uncertainty_score"),
            "selected_hypothesis_id": _safe_get(quantum,
                                                 "selected_hypothesis",
                                                 "hypothesis_id"),
            "collapse_reason": quantum.get("collapse_reason"),
            "decoherence_factors": quantum.get("decoherence_factors"),
            "entangled_symbols": quantum.get("entangled_symbols"),
            "kernel_truth_note": quantum.get("kernel_truth_note"),
        },

        "hypotheses": {
            "count": hypotheses.get("hypothesis_count"),
            "by_severity": hypotheses.get("by_severity"),
            "status_counts": hypotheses.get("status_counts"),
            "selected_hypothesis_id": hypotheses.get("selected_hypothesis_id"),
            "examples": [
                {
                    "hypothesis_id": h.get("hypothesis_id") or h.get("id"),
                    "statement": h.get("statement") or h.get("title"),
                    "status": h.get("status"),
                    "confidence": h.get("confidence"),
                }
                for h in (hypotheses.get("hypotheses") or [])[:8]
            ],
        },

        "contradictions": {
            "count": contradictions.get("contradiction_count"),
            "by_severity": contradictions.get("by_severity"),
            "examples": [
                {
                    "contradiction_id": c.get("contradiction_id"),
                    "severity": c.get("severity"),
                    "title": c.get("title"),
                    "recommended_action": c.get("recommended_action"),
                }
                for c in (contradictions.get("contradictions") or [])[:8]
            ],
        },

        "model_governance": {
            "lane_count": gov.get("lane_count"),
            "lanes": [
                {
                    "lane_id": l.get("lane_id"),
                    "role": l.get("role"),
                    "execution_allowed": l.get("execution_allowed"),
                    "registry_truth_outranks": l.get("registry_truth_outranks"),
                }
                for l in (gov.get("lanes") or [])
            ],
            "validation_rules": gov.get("validation_rules"),
            "governance_outputs": gov.get("governance_outputs"),
        },

        "replay_ledger": {
            "event_count_total": ledger.get("event_count_total"),
            "events_by_kind": ledger.get("events_by_kind"),
            "repair_suggestions": ledger.get("repair_suggestions"),
        },

        "architecture": {
            "phase": arch.get("phase"),
            "layer_count": arch.get("layer_count"),
            "layer_names": [l.get("name") for l in (arch.get("layers") or [])],
        },

        "major_audit": {
            "missing_count": major_audit.get("missing_count"),
            "what_to_build_next": _safe_get(
                load_json(REG / "eqsb_kernel_missing_capabilities.json", {}),
                "what_to_build_next") or [],
        },

        "safe_next_repairs": safe_repairs,
        "confidence_statement": confidence_statement,

        "lock_state": {
            "lock_count_true": 0,
            "execution_allowed": False,
            "active_local_only": True,
        },

        "kernel_truth_note": (
            "EQSB is the persistent symbolic kernel. Models may "
            "paraphrase; only the registries are kernel truth. The "
            "quantum signal is simulated; no real quantum hardware is "
            "connected unless verified."
        ),
    }
    payload.update(safety_envelope())
    payload["introspection_hash"] = stable_hash({
        "axioms": payload["axioms"]["registry_hash"],
        "guardian": payload["guardian"]["guardian_hash"],
        "entropy": payload["entropy"]["entropy_score"],
        "contradictions": payload["contradictions"]["count"],
    })
    write_json(P_MAJOR_INTROSPECTION, payload)
    append_event({"event": "build_kernel_introspection",
                  "missing_count": payload["major_audit"]["missing_count"]})
    return payload


def build():
    return build_kernel_introspection()


if __name__ == "__main__":
    print(json.dumps(build(), indent=2))
