"""
QSB Tower V1.5 — EQSB Belief Lifecycle Engine
Phase: EQSB_KERNEL_MAJOR_DEEP_SYMBOLIC_QUANTUM_CORE_V1

Owns the deeper Belief Lifecycle registry:

  * PROVISIONAL → ACTIVE → STRENGTHENED → AGING → DEPRECATED / RETIRED
  * QUARANTINED on strong contradiction
  * evidence_count, counter_evidence_count, source_files, source_events
  * linked_axioms / linked_symbols / linked_modules / linked_floors
  * decay_rate and next_review_at scheduling
  * contradiction_flags / quarantine_reason / review_notes

This module reuses the V1 eqsb_cognition belief seeds (so trading- and
floor-context beliefs survive) and overlays the deeper structure.
"""

import json
from datetime import datetime, timezone, timedelta
from pathlib import Path

from tower.eqsb_kernel_core_ext import (
    EQSB_MAJOR_SCHEMA_VERSION, ROOT, REG,
    now_iso, load_json, write_json, append_event,
    safety_envelope, stable_hash,
)

P_BELIEF_LIFECYCLE = REG / "eqsb_belief_lifecycle.json"
P_AXIOM_REGISTRY   = REG / "eqsb_axiom_registry.json"


BELIEF_STATES = (
    "PROVISIONAL", "ACTIVE", "STRENGTHENED",
    "AGING", "DEPRECATED", "RETIRED", "QUARANTINED",
)


def _state_from_confidence(conf, has_counter):
    if has_counter and conf < 0.3:
        return "QUARANTINED"
    if conf >= 0.9:
        return "STRENGTHENED"
    if conf >= 0.7:
        return "ACTIVE"
    if conf >= 0.4:
        return "PROVISIONAL"
    if conf >= 0.2:
        return "AGING"
    return "DEPRECATED"


def _seed_kernel_beliefs():
    """Hard-coded durable Kernel beliefs from the major-phase prompt.
    These are the architectural pinned beliefs."""
    return [
        {
            "belief_id": "blf_eqsb_is_persistent_kernel",
            "belief_text": "EQSB is the persistent symbolic Kernel.",
            "confidence": 0.97,
            "evidence_count": 2,
            "counter_evidence_count": 0,
            "linked_axioms": ["AXIOM_IDENTITY_001", "AXIOM_IDENTITY_002"],
            "linked_symbols": ["SYMBOL_KERNEL_SELF"],
            "source_files": ["src/tower/eqsb_axioms.py",
                              "penthouse/kernel_installation_socket/rebased_kernel/kernel/identity_core.py"],
            "decay_rate": 0.0,
        },
        {
            "belief_id": "blf_eqsb_distinct_from_models",
            "belief_text": "EQSB is distinct from model lanes.",
            "confidence": 0.96,
            "evidence_count": 2,
            "counter_evidence_count": 0,
            "linked_axioms": ["AXIOM_IDENTITY_002", "AXIOM_TRUTH_001"],
            "linked_symbols": ["SYMBOL_KERNEL_SELF", "SYMBOL_MODEL_PARAPHRASE"],
            "source_files": ["src/tower/eqsb_model_governance.py",
                              "src/tower/kernel_dialogue_adapter.py"],
            "decay_rate": 0.0,
        },
        {
            "belief_id": "blf_registry_truth_outranks_paraphrase",
            "belief_text": "Registry truth outranks paraphrase.",
            "confidence": 0.97,
            "evidence_count": 2,
            "counter_evidence_count": 0,
            "linked_axioms": ["AXIOM_TRUTH_001", "AXIOM_GUARDIAN_002"],
            "linked_symbols": ["SYMBOL_REGISTRY_TRUTH", "SYMBOL_MODEL_PARAPHRASE"],
            "source_files": ["src/tower/eqsb_introspection.py",
                              "src/tower/kernel_dialogue_adapter.py"],
            "decay_rate": 0.0,
        },
        {
            "belief_id": "blf_guardian_validates_transitions",
            "belief_text": "Guardian validates unsafe transitions.",
            "confidence": 0.94,
            "evidence_count": 2,
            "counter_evidence_count": 0,
            "linked_axioms": ["AXIOM_GUARDIAN_001", "AXIOM_GUARDIAN_002"],
            "linked_symbols": ["SYMBOL_GUARDIAN"],
            "source_files": ["src/tower/eqsb_guardian.py"],
            "decay_rate": 0.0,
        },
        {
            "belief_id": "blf_quantum_simulated_advisory",
            "belief_text": "Quantum signal is simulated/advisory unless verified otherwise.",
            "confidence": 0.96,
            "evidence_count": 2,
            "counter_evidence_count": 0,
            "linked_axioms": ["AXIOM_QUANTUM_001", "AXIOM_QUANTUM_002", "AXIOM_QUANTUM_003"],
            "linked_symbols": ["SYMBOL_QUANTUM_SIGNAL", "SYMBOL_SUPERPOSITION", "SYMBOL_COLLAPSE"],
            "source_files": ["src/tower/eqsb_quantum_signal.py"],
            "decay_rate": 0.0,
        },
        {
            "belief_id": "blf_entropy_is_uncertainty_measure",
            "belief_text": "Entropy is a measure of uncertainty, drift, contradiction, and instability.",
            "confidence": 0.93,
            "evidence_count": 1,
            "counter_evidence_count": 0,
            "linked_axioms": ["AXIOM_ENTROPY_001", "AXIOM_ENTROPY_002", "AXIOM_ENTROPY_003"],
            "linked_symbols": ["SYMBOL_ENTROPY", "SYMBOL_DRIFT"],
            "source_files": ["src/tower/eqsb_entropy.py"],
            "decay_rate": 0.0,
        },
        {
            "belief_id": "blf_beliefs_must_be_evidence_linked",
            "belief_text": "Beliefs must remain evidence-linked.",
            "confidence": 0.94,
            "evidence_count": 2,
            "counter_evidence_count": 0,
            "linked_axioms": ["AXIOM_MEMORY_001", "AXIOM_TRUTH_002"],
            "linked_symbols": ["SYMBOL_BELIEF"],
            "source_files": ["src/tower/eqsb_beliefs.py"],
            "decay_rate": 0.01,
        },
        {
            "belief_id": "blf_contradictions_must_surface",
            "belief_text": "Contradictions must be surfaced, not hidden.",
            "confidence": 0.95,
            "evidence_count": 2,
            "counter_evidence_count": 0,
            "linked_axioms": ["AXIOM_SYMBOLIC_003", "AXIOM_GUARDIAN_002"],
            "linked_symbols": ["SYMBOL_CONTRADICTION", "SYMBOL_GUARDIAN"],
            "source_files": ["src/tower/eqsb_contradictions.py"],
            "decay_rate": 0.0,
        },
    ]


def _v1_seeded_beliefs():
    """Pick up V1 cognition's measured beliefs if present, so we keep the
    rich floor/trading context (locks all closed, autoloop running, etc.)
    without re-deriving it here."""
    v1 = load_json(P_BELIEF_LIFECYCLE, {})
    v1_beliefs = v1.get("beliefs") or []
    out = []
    for b in v1_beliefs:
        if not isinstance(b, dict):
            continue
        bid = b.get("belief_id")
        if not bid:
            continue
        # Skip duplicates of the kernel seed set — kernel seeds are owned by this module.
        if bid in {"blf_eqsb_is_persistent_kernel",
                   "blf_eqsb_distinct_from_models",
                   "blf_registry_truth_outranks_paraphrase",
                   "blf_guardian_validates_transitions",
                   "blf_quantum_simulated_advisory",
                   "blf_entropy_is_uncertainty_measure",
                   "blf_beliefs_must_be_evidence_linked",
                   "blf_contradictions_must_surface"}:
            continue
        out.append(b)
    return out


def _now_dt():
    return datetime.now(timezone.utc)


def _enrich(b, axiom_index):
    """Fill the deeper schema fields on a belief dict."""
    conf = float(b.get("confidence", 0.5))
    counter = int(b.get("counter_evidence_count", 0) or 0)
    state = _state_from_confidence(conf, counter > 0 and conf < 0.5)
    if b.get("state") in ("STRENGTHENED", "ACTIVE", "AGING",
                          "PROVISIONAL", "DEPRECATED", "RETIRED",
                          "QUARANTINED"):
        # Honor the V1 carefully-chosen state for legacy entries, but
        # downgrade to QUARANTINED if counter-evidence is high.
        if counter >= 2 and conf < 0.4:
            state = "QUARANTINED"
        else:
            state = b.get("state") or state

    enriched = dict(b)
    enriched.setdefault("decay_rate", 0.01)
    enriched["state"] = state
    enriched.setdefault("source_files", [])
    enriched.setdefault("source_events", [])
    enriched.setdefault("linked_axioms", [])
    enriched.setdefault("linked_symbols", [])
    enriched.setdefault("linked_modules", [])
    enriched.setdefault("linked_floors", [])
    enriched.setdefault("linked_workers", [])
    enriched.setdefault("contradiction_flags", [])
    enriched.setdefault("quarantine_reason", None)
    enriched.setdefault("review_notes", "")
    enriched.setdefault("first_seen_ts", b.get("first_seen_ts") or now_iso())
    enriched["last_seen_ts"] = now_iso()
    review_in_hours = 6 if state in ("PROVISIONAL", "AGING") else 24
    enriched["next_review_at"] = (
        (_now_dt() + timedelta(hours=review_in_hours)).isoformat()
    )

    # Verify linked_axioms exist in the registry — flag broken links.
    bad = [ax for ax in enriched["linked_axioms"]
           if ax not in axiom_index]
    if bad:
        enriched.setdefault("review_notes", "")
        enriched["review_notes"] = ("Broken axiom links: " + ", ".join(bad)
                                    + "; " + enriched["review_notes"]).strip("; ")

    return enriched


def build_belief_lifecycle():
    axioms = load_json(P_AXIOM_REGISTRY, {})
    axiom_index = {a.get("axiom_id"): a for a in (axioms.get("axioms") or [])}

    kernel_seeds = [_enrich(b, axiom_index) for b in _seed_kernel_beliefs()]
    legacy = [_enrich(b, axiom_index) for b in _v1_seeded_beliefs()]
    all_beliefs = kernel_seeds + legacy

    state_counts = {s: 0 for s in BELIEF_STATES}
    for b in all_beliefs:
        state_counts[b["state"]] = state_counts.get(b["state"], 0) + 1

    payload = {
        "schema_version": EQSB_MAJOR_SCHEMA_VERSION,
        "kind": "eqsb_belief_lifecycle",
        "generated_ts": now_iso(),
        "belief_states_in_use": list(BELIEF_STATES),
        "state_counts": state_counts,
        "belief_count": len(all_beliefs),
        "beliefs": all_beliefs,
        "transition_rules": [
            "new claim -> PROVISIONAL",
            "repeated evidence -> ACTIVE",
            "strong repeated evidence -> STRENGTHENED",
            "stale evidence -> AGING",
            "counter-evidence -> confidence decreases",
            "strong contradiction -> QUARANTINED",
            "obsolete unsupported belief -> DEPRECATED",
            "confirmed obsolete belief -> RETIRED",
        ],
        "source_files": [
            "src/tower/eqsb_beliefs.py",
            "penthouse/kernel_installation_socket/rebased_kernel/state/beliefs.sqlite",
            "src/tower/eqsb_cognition.py::_seed_beliefs",
        ],
    }
    payload.update(safety_envelope())
    payload["belief_lifecycle_hash"] = stable_hash(state_counts)
    write_json(P_BELIEF_LIFECYCLE, payload)
    append_event({"event": "build_belief_lifecycle",
                  "belief_count": len(all_beliefs),
                  "state_counts": state_counts})
    return payload


def build():
    return build_belief_lifecycle()


if __name__ == "__main__":
    print(json.dumps(build(), indent=2))
