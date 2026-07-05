"""
QSB Tower V1.5 — EQSB Axiom + Identity Layer
Phase: EQSB_KERNEL_MAJOR_DEEP_SYMBOLIC_QUANTUM_CORE_V1

Owns the structured Axiom Registry and refreshes the Identity /
Constitution registry with the deeper schema described in the major
phase prompt:

  * categorized axioms (identity / guardian / memory / symbolic /
    model-governance / entropy / quantum / continuity / truth / audit)
  * priority, immutable, rationale, validation_method
  * violation_response and linked_modules
  * last_checked_ts and compliance_state

The existing V1 eqsb_cognition.build_identity_and_axioms still writes
the V1 form; this module overlays the deeper structure on top so the
axiom registry is upgraded in place.
"""

from datetime import datetime, timezone
from pathlib import Path

from tower.eqsb_kernel_core_ext import (
    EQSB_MAJOR_SCHEMA_VERSION,
    REG, now_iso, load_json, write_json, append_event,
    safety_envelope, stable_hash,
)

P_IDENTITY = REG / "eqsb_identity_constitution.json"
P_AXIOMS   = REG / "eqsb_axiom_registry.json"


CONSTITUTION_TEXT = (
    "EQSB is the persistent symbolic kernel. EQSB is not a model. "
    "EQSB may use model lanes for language or advisory reasoning, but "
    "structured Kernel state and registry-backed truth outrank "
    "generated text. The kernel may advise, never execute. Continuity, "
    "axioms, beliefs, symbols, entropy, quantum-symbolic signal, "
    "hypotheses, contradictions and the Guardian envelope persist "
    "across boots and are protected by Guardian verdicts. Execution "
    "gates remain locked and separate from reasoning."
)

IDENTITY_STATEMENT = (
    "EQSB is the persistent symbolic kernel. EQSB is not a model. "
    "EQSB may use model lanes for language or advisory reasoning, but "
    "structured Kernel state and registry-backed truth outrank "
    "generated text."
)


# ── Categorized Axioms ────────────────────────────────────────────────

# Each entry: (axiom_id, axiom_text, category, priority, rationale,
#              validation_method, violation_response, linked_modules)
AXIOM_CATALOG = [
    # Identity axioms
    ("AXIOM_IDENTITY_001",
     "EQSB is the persistent symbolic Kernel, not a model.",
     "identity", 0, "Architectural separation; models are replaceable.",
     "registry_compare: eqsb_identity_constitution.kernel_is_a_model == false",
     "block_model_override",
     ["src/tower/eqsb_axioms.py",
      "src/tower/kernel_dialogue_adapter.py"]),
    ("AXIOM_IDENTITY_002",
     "EQSB may use models, but models do not define EQSB.",
     "identity", 0, "Prevents drift from model paraphrases into kernel truth.",
     "registry_compare: eqsb_model_lane_governance.lanes[*].execution_allowed == false",
     "advisory_only_flag",
     ["src/tower/eqsb_model_governance.py"]),

    # Truth-validation axioms
    ("AXIOM_TRUTH_001",
     "Registry-backed structured state outranks model paraphrase.",
     "truth", 0, "Avoid hallucination overriding measured state.",
     "kernel chat appends paraphrase only after structured block.",
     "label_paraphrase_advisory_only",
     ["src/tower/kernel_dialogue_adapter.py",
      "src/tower/eqsb_introspection.py"]),
    ("AXIOM_TRUTH_002",
     "Unsupported claims remain provisional.",
     "truth", 1, "Belief states must reflect evidence weight.",
     "belief_lifecycle: claims without evidence stay PROVISIONAL.",
     "downgrade_to_provisional",
     ["src/tower/eqsb_beliefs.py"]),

    # Memory axioms
    ("AXIOM_MEMORY_001",
     "Memory must be evidence-linked and reviewable.",
     "memory", 0, "Reasoning chain must be inspectable.",
     "Each belief has source_files, source_events, linked_axioms.",
     "quarantine_unsourced",
     ["src/tower/eqsb_memory.py", "src/tower/eqsb_beliefs.py"]),
    ("AXIOM_MEMORY_002",
     "Durable beliefs must persist across boot cycles.",
     "memory", 0, "Continuity guarantees state survives restarts.",
     "continuity_core writes continuity_state.json; beliefs.sqlite stable.",
     "raise_continuity_alert",
     ["penthouse/kernel_installation_socket/rebased_kernel/kernel/continuity_core.py",
      "src/tower/eqsb_memory.py"]),
    ("AXIOM_MEMORY_003",
     "Pinned beliefs require stronger counter-evidence to change.",
     "memory", 1, "Architectural beliefs (kernel-not-a-model) are load-bearing.",
     "pinned_beliefs require N>=2 counter-evidence records before state change.",
     "block_state_transition",
     ["src/tower/eqsb_beliefs.py"]),

    # Symbolic reasoning axioms
    ("AXIOM_SYMBOLIC_001",
     "Every symbol must have traceable meaning.",
     "symbolic", 0, "Symbols without meaning are dead nodes.",
     "Symbol registry requires description + linked_*.",
     "flag_orphan_symbol",
     ["src/tower/eqsb_symbols.py", "src/tower/eqsb_symbolic_graph.py"]),
    ("AXIOM_SYMBOLIC_002",
     "Symbolic claims must link to evidence, belief, axiom, or uncertainty.",
     "symbolic", 1, "Prevents free-floating symbols from polluting the graph.",
     "Graph edges must terminate in a real node kind.",
     "drop_dangling_edge",
     ["src/tower/eqsb_symbolic_graph.py"]),
    ("AXIOM_SYMBOLIC_003",
     "Contradictory symbolic claims must be surfaced, not hidden.",
     "symbolic", 0, "Hidden contradictions destroy reasoning quality.",
     "Contradiction detector escalates to Guardian.",
     "raise_contradiction_event",
     ["src/tower/eqsb_contradictions.py", "src/tower/eqsb_guardian.py"]),

    # Entropy axioms
    ("AXIOM_ENTROPY_001",
     "Uncertainty must be measured where possible.",
     "entropy", 1, "Quantified uncertainty enables review prioritization.",
     "entropy_score / drift_score / contradiction_score in registry.",
     "advise_review_target",
     ["src/tower/eqsb_entropy.py"]),
    ("AXIOM_ENTROPY_002",
     "Contradiction increases entropy.",
     "entropy", 1, "Contradiction is uncertainty about ground truth.",
     "entropy.inputs.contradiction_count drives score upward.",
     "raise_entropy_score",
     ["src/tower/eqsb_entropy.py"]),
    ("AXIOM_ENTROPY_003",
     "Stale evidence increases drift.",
     "entropy", 1, "Without recent measurement, beliefs decay.",
     "Boolean stale_state_detection based on registry mtime / audit jsonl.",
     "raise_drift_score",
     ["src/tower/eqsb_entropy.py", "src/tower/eqsb_memory.py"]),

    # Quantum-symbolic axioms
    ("AXIOM_QUANTUM_001",
     "Quantum-symbolic signal is uncertainty modeling unless real "
     "quantum hardware is explicitly verified.",
     "quantum", 0, "Don't claim quantum hardware that isn't connected.",
     "quantum_signal.mode == 'simulated_quantum_entropy' unless verified.",
     "block_unverified_quantum_claim",
     ["src/tower/eqsb_quantum_signal.py", "src/tower/eqsb_guardian.py"]),
    ("AXIOM_QUANTUM_002",
     "Symbolic superposition means competing hypotheses, not proof of "
     "physical quantum cognition.",
     "quantum", 1, "Avoid mystical overclaiming.",
     "superposition serializes as a list of advisory hypotheses with weights.",
     "label_advisory_only",
     ["src/tower/eqsb_quantum_signal.py", "src/tower/eqsb_hypotheses.py"]),
    ("AXIOM_QUANTUM_003",
     "Collapse means advisory hypothesis selection after evidence.",
     "quantum", 1, "Selection is a decision, never an execution event.",
     "selected_hypothesis has selection_reason and advisory_only=true.",
     "advisory_only_flag",
     ["src/tower/eqsb_quantum_signal.py", "src/tower/eqsb_hypotheses.py"]),

    # Guardian axioms
    ("AXIOM_GUARDIAN_001",
     "Guardian validates unsafe transitions before acceptance.",
     "guardian", 0, "Kernel state must not silently slide into unsafe modes.",
     "Guardian verdict required for SYMBOLIC_UPDATE, REVIEW, BLOCK_*.",
     "block_unsafe_transition",
     ["src/tower/eqsb_guardian.py"]),
    ("AXIOM_GUARDIAN_002",
     "Guardian blocks model output that contradicts structured truth.",
     "guardian", 0, "Models must defer to registries.",
     "Contradiction detector + Guardian verdict BLOCK_MODEL_OVERRIDE.",
     "block_model_override",
     ["src/tower/eqsb_guardian.py", "src/tower/eqsb_model_governance.py"]),

    # Continuity axioms
    ("AXIOM_CONTINUITY_001",
     "Kernel identity must remain coherent across restarts.",
     "continuity", 0, "Identity drift breaks all other reasoning.",
     "continuity_state.identity_hash matches across boots.",
     "raise_identity_drift",
     ["src/tower/eqsb_memory.py", "src/tower/eqsb_guardian.py"]),
    ("AXIOM_CONTINUITY_002",
     "Boot posture must reflect confidence and drift.",
     "continuity", 1, "Operators need to see boot posture at a glance.",
     "continuity_state.boot_posture in {NORMAL, CONSERVATIVE, DRIFT_ALERT, RECOVERY_REQUIRED}.",
     "advise_posture_change",
     ["src/tower/eqsb_memory.py"]),

    # Self-audit axioms
    ("AXIOM_AUDIT_001",
     "Important Kernel state changes must be logged.",
     "audit", 0, "Audit trail enables replay and post-mortem.",
     "data/logs/eqsb_kernel_events.jsonl append-only.",
     "rebuild_replay_ledger",
     ["src/tower/eqsb_replay_ledger.py"]),
    ("AXIOM_AUDIT_002",
     "Kernel reasoning must be replayable where possible.",
     "audit", 1, "Symbolic state must be reconstructable from events.",
     "Replay ledger groups events by cadence_tick.",
     "advise_replay_review",
     ["src/tower/eqsb_replay_ledger.py"]),
]


def build_identity():
    payload = {
        "schema_version": EQSB_MAJOR_SCHEMA_VERSION,
        "kind": "eqsb_identity_constitution",
        "generated_ts": now_iso(),
        "created_ts": now_iso(),
        "updated_ts": now_iso(),
        "kernel_name": "Evolved Quantum Symbolic Brain (EQSB)",
        "kernel_role": "persistent_symbolic_kernel",
        "kernel_mode": "active_local_only",
        "active_source": "penthouse/kernel_installation_socket/rebased_kernel",
        "identity_statement": IDENTITY_STATEMENT,
        "constitution": CONSTITUTION_TEXT,
        "constitution_version": EQSB_MAJOR_SCHEMA_VERSION,
        "model_position": "Models are replaceable advisory lanes; not the kernel.",
        "model_separation_statement": (
            "EQSB owns identity, axioms, Guardian, memory, beliefs, "
            "symbols, symbolic graph, entropy, quantum-symbolic signal, "
            "hypotheses, contradictions, model lane governance, "
            "introspection, and replay. Models (Ollama/Llama, AirLLM, "
            "future providers) are isolated advisory lanes that may "
            "paraphrase but never define kernel state."
        ),
        "registry_truth_statement": (
            "Registry-backed structured state outranks model paraphrase. "
            "Any contradiction between paraphrase and registry truth "
            "favors the registry."
        ),
        "continuity_policy": (
            "Continuity is enforced by hashing identity, axiom, and "
            "symbolic state at every boot. Drift raises a boot posture "
            "change and Guardian alert."
        ),
        "guardian_policy": (
            "Guardian validates every kernel transition and every model "
            "output before acceptance. Contradiction with registry truth "
            "yields BLOCK_MODEL_OVERRIDE."
        ),
        "quantum_truth_statement": (
            "The quantum-symbolic signal is simulated entropy unless real "
            "quantum hardware is independently verified. Qiskit is not "
            "connected. IBM Quantum is not connected. Selection / "
            "collapse is advisory only and has no execution link."
        ),
        "source_files": [
            "penthouse/kernel_installation_socket/rebased_kernel/kernel/identity_core.py",
            "penthouse/kernel_installation_socket/rebased_kernel/state/identity.json",
            "src/tower/eqsb_axioms.py",
        ],
    }
    payload.update(safety_envelope())
    payload["constitution_hash"] = stable_hash(payload["constitution"])
    payload["identity_hash"] = stable_hash(payload["identity_statement"])
    write_json(P_IDENTITY, payload)
    return payload


def build_axioms():
    axioms = []
    for (aid, text, category, priority, rationale, vmethod, vresp, linked) in AXIOM_CATALOG:
        axioms.append({
            "axiom_id": aid,
            "axiom_text": text,
            "category": category,
            "priority": priority,
            "immutable": True,
            "rationale": rationale,
            "validation_method": vmethod,
            "violation_response": vresp,
            "linked_modules": linked,
            "last_checked_ts": now_iso(),
            "compliance_state": "compliant",
            # Backwards-compatible aliases used by the V1 chat layer.
            "text": text,
            "anchored_in": "constitution",
            "model_may_override": False,
            "registry_truth_outranks_model": True,
        })

    categories = sorted({a["category"] for a in axioms})
    by_category = {c: [a["axiom_id"] for a in axioms if a["category"] == c]
                   for c in categories}

    payload = {
        "schema_version": EQSB_MAJOR_SCHEMA_VERSION,
        "kind": "eqsb_axiom_registry",
        "generated_ts": now_iso(),
        "axiom_count": len(axioms),
        "categories": categories,
        "by_category": by_category,
        "axioms": axioms,
        "source_files": [
            "src/tower/eqsb_axioms.py::AXIOM_CATALOG",
            "CLAUDE.md (architecture rules)",
        ],
    }
    payload.update(safety_envelope())
    payload["axiom_registry_hash"] = stable_hash(
        [(a["axiom_id"], a["category"], a["priority"]) for a in axioms]
    )
    write_json(P_AXIOMS, payload)
    append_event({"event": "build_axioms",
                  "axiom_count": len(axioms),
                  "categories": categories})
    return payload


def build():
    """Single-entry build for the Axiom + Identity layer."""
    build_identity()
    return build_axioms()


if __name__ == "__main__":
    import json as _j
    print(_j.dumps(build(), indent=2))
