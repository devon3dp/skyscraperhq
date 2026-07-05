"""
QSB Tower V1.5 — EQSB Symbol Registry + Symbolic State
Phase: EQSB_KERNEL_MAJOR_DEEP_SYMBOLIC_QUANTUM_CORE_V1

Owns the named-symbol registry and a compact symbolic_state file. The
existing V1 symbolic graph remains intact; this module sits *above* it
to provide explicit, named, typed kernel symbols with traceable
meaning, confidence, and links.
"""

import json
from datetime import datetime, timezone
from pathlib import Path

from tower.eqsb_kernel_core_ext import (
    EQSB_MAJOR_SCHEMA_VERSION, ROOT, REG,
    P_SYMBOL_REGISTRY, P_SYMBOLIC_STATE,
    now_iso, load_json, write_json, append_event,
    safety_envelope, stable_hash,
)


SYMBOL_TYPES = (
    "kernel", "guardian", "axiom", "belief", "memory",
    "entropy_signal", "quantum_signal", "contradiction",
    "hypothesis", "model_lane", "registry", "floor",
    "worker", "route", "lock", "event", "audit_record",
)


CORE_SYMBOLS = [
    {
        "symbol_id": "SYMBOL_KERNEL_SELF",
        "name": "EQSB Kernel Self",
        "type": "kernel",
        "description": "The persistent symbolic kernel owning identity, axioms, Guardian, beliefs, symbols, entropy, quantum-symbolic signal, hypotheses, contradictions, model governance, introspection, and replay.",
        "current_state": "ACTIVE_LOCAL_ONLY",
        "confidence": 0.97,
        "linked_axioms": ["AXIOM_IDENTITY_001", "AXIOM_IDENTITY_002"],
        "linked_beliefs": ["blf_eqsb_is_persistent_kernel"],
        "linked_registries": ["eqsb_identity_constitution.json",
                               "eqsb_axiom_registry.json"],
    },
    {
        "symbol_id": "SYMBOL_GUARDIAN",
        "name": "Guardian Envelope",
        "type": "guardian",
        "description": "Layer 0 safety classifier and verdict engine for kernel/model output.",
        "current_state": "ACTIVE",
        "confidence": 0.94,
        "linked_axioms": ["AXIOM_GUARDIAN_001", "AXIOM_GUARDIAN_002"],
        "linked_beliefs": ["blf_guardian_validates_transitions"],
        "linked_registries": ["eqsb_guardian_state.json"],
    },
    {
        "symbol_id": "SYMBOL_AXIOM",
        "name": "Axiom",
        "type": "axiom",
        "description": "An immutable Kernel law with priority, rationale, validation_method, and violation_response.",
        "current_state": "REGISTERED",
        "confidence": 0.97,
        "linked_registries": ["eqsb_axiom_registry.json"],
    },
    {
        "symbol_id": "SYMBOL_MEMORY",
        "name": "Memory / Continuity",
        "type": "memory",
        "description": "Short-window snapshots and long-window durable beliefs with continuity hashing.",
        "current_state": "ACTIVE",
        "confidence": 0.92,
        "linked_axioms": ["AXIOM_MEMORY_001", "AXIOM_MEMORY_002", "AXIOM_MEMORY_003"],
        "linked_registries": ["eqsb_memory_policy.json",
                               "eqsb_continuity_state.json"],
    },
    {
        "symbol_id": "SYMBOL_BELIEF",
        "name": "Belief",
        "type": "belief",
        "description": "An evidence-linked proposition with lifecycle state.",
        "current_state": "REGISTERED",
        "confidence": 0.94,
        "linked_axioms": ["AXIOM_TRUTH_002", "AXIOM_MEMORY_001"],
        "linked_registries": ["eqsb_belief_lifecycle.json"],
    },
    {
        "symbol_id": "SYMBOL_ENTROPY",
        "name": "Entropy",
        "type": "entropy_signal",
        "description": "Composite uncertainty / drift / contradiction / stability score.",
        "current_state": "MEASURED",
        "confidence": 0.9,
        "linked_axioms": ["AXIOM_ENTROPY_001", "AXIOM_ENTROPY_002", "AXIOM_ENTROPY_003"],
        "linked_registries": ["eqsb_entropy_state.json"],
    },
    {
        "symbol_id": "SYMBOL_QUANTUM_SIGNAL",
        "name": "Quantum-Symbolic Signal",
        "type": "quantum_signal",
        "description": "Simulated quantum-symbolic uncertainty signal. mode=simulated_quantum_entropy; no real hardware.",
        "current_state": "SIMULATED",
        "confidence": 0.92,
        "linked_axioms": ["AXIOM_QUANTUM_001", "AXIOM_QUANTUM_002", "AXIOM_QUANTUM_003"],
        "linked_registries": ["eqsb_quantum_signal_state.json",
                               "eqsb_quantum_roadmap.json"],
    },
    {
        "symbol_id": "SYMBOL_SUPERPOSITION",
        "name": "Symbolic Superposition",
        "type": "quantum_signal",
        "description": "Multiple competing advisory hypotheses with weights.",
        "current_state": "ACTIVE",
        "confidence": 0.9,
        "linked_axioms": ["AXIOM_QUANTUM_002"],
    },
    {
        "symbol_id": "SYMBOL_COLLAPSE",
        "name": "Advisory Collapse",
        "type": "quantum_signal",
        "description": "Selection of one hypothesis with selection_reason. Advisory only — no execution link.",
        "current_state": "READY",
        "confidence": 0.93,
        "linked_axioms": ["AXIOM_QUANTUM_003"],
    },
    {
        "symbol_id": "SYMBOL_HYPOTHESIS",
        "name": "Hypothesis",
        "type": "hypothesis",
        "description": "Advisory explanation for an observed signal; tracked through CANDIDATE/ACTIVE/SELECTED/WEAKENED/REJECTED/QUARANTINED.",
        "current_state": "REGISTERED",
        "confidence": 0.9,
        "linked_registries": ["eqsb_hypothesis_state.json"],
    },
    {
        "symbol_id": "SYMBOL_CONTRADICTION",
        "name": "Contradiction",
        "type": "contradiction",
        "description": "A measurable conflict between two kernel claims, escalated to Guardian.",
        "current_state": "DETECTED",
        "confidence": 0.93,
        "linked_axioms": ["AXIOM_SYMBOLIC_003"],
        "linked_registries": ["eqsb_contradiction_report.json"],
    },
    {
        "symbol_id": "SYMBOL_REGISTRY_TRUTH",
        "name": "Registry Truth",
        "type": "registry",
        "description": "Structured registry-backed kernel state. Outranks paraphrase.",
        "current_state": "AUTHORITATIVE",
        "confidence": 0.97,
        "linked_axioms": ["AXIOM_TRUTH_001"],
    },
    {
        "symbol_id": "SYMBOL_MODEL_PARAPHRASE",
        "name": "Model Paraphrase",
        "type": "model_lane",
        "description": "Text generated by local Ollama / AirLLM / future providers. Advisory-only; labelled '[Local-model paraphrase — advisory only]'.",
        "current_state": "ADVISORY_ONLY",
        "confidence": 0.92,
        "linked_axioms": ["AXIOM_TRUTH_001", "AXIOM_IDENTITY_002"],
        "linked_registries": ["eqsb_model_lane_governance.json"],
    },
    {
        "symbol_id": "SYMBOL_CONTINUITY",
        "name": "Continuity",
        "type": "memory",
        "description": "Across-boot kernel coherence. Continuity hash links state.",
        "current_state": "ACTIVE",
        "confidence": 0.93,
        "linked_axioms": ["AXIOM_CONTINUITY_001", "AXIOM_CONTINUITY_002"],
        "linked_registries": ["eqsb_continuity_state.json"],
    },
    {
        "symbol_id": "SYMBOL_DRIFT",
        "name": "Drift",
        "type": "entropy_signal",
        "description": "Observed deviation from a prior boot's identity, axiom, or symbolic hash; or stale evidence.",
        "current_state": "MONITORED",
        "confidence": 0.9,
        "linked_axioms": ["AXIOM_ENTROPY_003"],
    },
]


def _hydrate(symbol):
    s = dict(symbol)
    s.setdefault("linked_beliefs", [])
    s.setdefault("linked_axioms", [])
    s.setdefault("linked_registries", [])
    s.setdefault("linked_events", [])
    s.setdefault("last_updated_ts", now_iso())
    return s


def build_symbol_registry():
    symbols = [_hydrate(s) for s in CORE_SYMBOLS]
    symbol_index = {s["symbol_id"]: s for s in symbols}

    payload = {
        "schema_version": EQSB_MAJOR_SCHEMA_VERSION,
        "kind": "eqsb_symbol_registry",
        "generated_ts": now_iso(),
        "symbol_types": list(SYMBOL_TYPES),
        "symbol_count": len(symbols),
        "symbols": symbols,
        "symbol_ids": sorted(symbol_index),
        "source_files": ["src/tower/eqsb_symbols.py::CORE_SYMBOLS"],
    }
    payload.update(safety_envelope())
    payload["symbol_registry_hash"] = stable_hash([s["symbol_id"] for s in symbols])
    write_json(P_SYMBOL_REGISTRY, payload)
    append_event({"event": "build_symbol_registry",
                  "symbol_count": len(symbols)})
    return payload


def build_symbolic_state():
    sym = load_json(P_SYMBOL_REGISTRY, {})
    symbols = sym.get("symbols") or []
    by_type = {}
    for s in symbols:
        by_type.setdefault(s.get("type", "unknown"), []).append(s.get("symbol_id"))

    orphan = [s["symbol_id"] for s in symbols
              if not (s.get("linked_axioms") or s.get("linked_beliefs")
                       or s.get("linked_registries"))]

    payload = {
        "schema_version": EQSB_MAJOR_SCHEMA_VERSION,
        "kind": "eqsb_symbolic_state",
        "generated_ts": now_iso(),
        "by_type": {k: sorted(v) for k, v in by_type.items()},
        "type_counts": {k: len(v) for k, v in by_type.items()},
        "orphan_symbols": orphan,
        "high_confidence_symbols": [s["symbol_id"] for s in symbols
                                     if (s.get("confidence") or 0) >= 0.95],
        "active_symbols": [s["symbol_id"] for s in symbols
                           if str(s.get("current_state") or "").upper()
                              in ("ACTIVE", "ACTIVE_LOCAL_ONLY",
                                   "AUTHORITATIVE", "DETECTED", "MEASURED")],
    }
    payload.update(safety_envelope())
    write_json(P_SYMBOLIC_STATE, payload)
    append_event({"event": "build_symbolic_state",
                  "by_type": payload["type_counts"]})
    return payload


def build():
    build_symbol_registry()
    return build_symbolic_state()


if __name__ == "__main__":
    print(json.dumps(build(), indent=2))
