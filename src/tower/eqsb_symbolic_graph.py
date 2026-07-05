"""
QSB Tower V1.5 — EQSB Symbolic Graph (Major Phase)
Phase: EQSB_KERNEL_MAJOR_DEEP_SYMBOLIC_QUANTUM_CORE_V1

Augments the V1 eqsb_symbolic_graph.json with explicit Kernel-level
node kinds and edges described in the major phase prompt. Existing V1
nodes (floors, workers, model lanes, lock_matrix) are preserved.
"""

import json
from datetime import datetime, timezone

from tower.eqsb_kernel_core_ext import (
    EQSB_MAJOR_SCHEMA_VERSION, REG,
    now_iso, load_json, write_json, append_event,
    safety_envelope, stable_hash,
)

P_GRAPH         = REG / "eqsb_symbolic_graph.json"
P_AXIOMS        = REG / "eqsb_axiom_registry.json"
P_BELIEFS       = REG / "eqsb_belief_lifecycle.json"
P_SYMBOLS       = REG / "eqsb_symbol_registry.json"
P_HYPOTHESES    = REG / "eqsb_hypothesis_state.json"
P_CONTRADICTIONS= REG / "eqsb_contradiction_report.json"
P_GOVERNANCE    = REG / "eqsb_model_lane_governance.json"


KERNEL_NODE_KINDS = [
    "kernel", "guardian", "axiom", "belief", "symbol",
    "memory", "registry", "model_lane",
    "entropy_signal", "quantum_signal",
    "contradiction", "hypothesis", "replay_event",
    "floor", "worker", "lock_matrix",
]

KERNEL_RELATIONS = [
    "kernel_owns_axiom",
    "guardian_validates_kernel_output",
    "axiom_supports_belief",
    "registry_supports_belief",
    "symbol_represents_entity",
    "contradiction_challenges_belief",
    "hypothesis_explains_signal",
    "entropy_raises_uncertainty",
    "model_lane_suggests_text",
    "kernel_validates_model_output",
    "memory_preserves_belief",
    "continuity_hash_links_state",
    "quantum_signal_weights_hypothesis",
    "collapse_selects_hypothesis",
    # V1 relations we preserve
    "floor_routes_to_floor",
    "lock_protects_execution_path",
    "model_lane_advises_kernel",
    "worker_assigned_to_floor",
]


def build_symbolic_graph():
    prev = load_json(P_GRAPH, {})
    axioms = load_json(P_AXIOMS, {})
    beliefs = load_json(P_BELIEFS, {})
    symbols = load_json(P_SYMBOLS, {})
    hypotheses = load_json(P_HYPOTHESES, {})
    contradictions = load_json(P_CONTRADICTIONS, {})
    gov = load_json(P_GOVERNANCE, {})

    # Kernel-level nodes — synthesized from the EQSB registries.
    nodes = []
    nodes.append({"id": "node_kernel_self", "kind": "kernel",
                  "label": "EQSB Kernel"})
    nodes.append({"id": "node_guardian", "kind": "guardian",
                  "label": "Guardian Envelope"})
    nodes.append({"id": "node_memory", "kind": "memory",
                  "label": "Memory / Continuity"})
    nodes.append({"id": "node_entropy_signal", "kind": "entropy_signal",
                  "label": "Entropy Signal"})
    nodes.append({"id": "node_quantum_signal", "kind": "quantum_signal",
                  "label": "Quantum-Symbolic Signal"})
    nodes.append({"id": "node_registry_truth", "kind": "registry",
                  "label": "Registry Truth"})
    nodes.append({"id": "node_model_paraphrase", "kind": "model_lane",
                  "label": "Model Paraphrase"})

    edges = []

    # kernel_owns_axiom
    for a in (axioms.get("axioms") or []):
        nid = "node_axiom_" + a.get("axiom_id", "x")
        nodes.append({"id": nid, "kind": "axiom",
                       "label": a.get("axiom_id"),
                       "category": a.get("category")})
        edges.append({"source": "node_kernel_self", "relation": "kernel_owns_axiom",
                       "target": nid})

    # axiom_supports_belief + registry_supports_belief
    for b in (beliefs.get("beliefs") or []):
        nid = "node_belief_" + b.get("belief_id", "x")
        nodes.append({"id": nid, "kind": "belief",
                       "label": b.get("belief_id"),
                       "state": b.get("state"),
                       "confidence": b.get("confidence")})
        for ax in (b.get("linked_axioms") or []):
            edges.append({"source": "node_axiom_" + ax,
                           "relation": "axiom_supports_belief",
                           "target": nid})
        if b.get("source_files") or b.get("source"):
            edges.append({"source": "node_registry_truth",
                           "relation": "registry_supports_belief",
                           "target": nid})
        # memory_preserves_belief
        edges.append({"source": "node_memory",
                       "relation": "memory_preserves_belief",
                       "target": nid})

    # symbol_represents_entity
    for s in (symbols.get("symbols") or []):
        nid = "node_symbol_" + s.get("symbol_id", "x")
        nodes.append({"id": nid, "kind": "symbol",
                       "label": s.get("symbol_id"),
                       "type": s.get("type"),
                       "confidence": s.get("confidence")})
        edges.append({"source": nid, "relation": "symbol_represents_entity",
                       "target": "node_kernel_self"})

    # hypothesis_explains_signal + quantum_signal_weights_hypothesis
    for h in (hypotheses.get("hypotheses") or []):
        hid = h.get("hypothesis_id") or h.get("id") or "h?"
        nid = "node_hypothesis_" + hid
        nodes.append({"id": nid, "kind": "hypothesis",
                       "label": h.get("title") or hid,
                       "severity": h.get("severity")})
        edges.append({"source": nid, "relation": "hypothesis_explains_signal",
                       "target": "node_entropy_signal"})
        edges.append({"source": "node_quantum_signal",
                       "relation": "quantum_signal_weights_hypothesis",
                       "target": nid})

    # contradiction_challenges_belief + entropy_raises_uncertainty
    for c in (contradictions.get("contradictions") or []):
        cid = c.get("contradiction_id") or c.get("id") or "c?"
        nid = "node_contradiction_" + cid
        nodes.append({"id": nid, "kind": "contradiction",
                       "label": c.get("title") or cid,
                       "severity": c.get("severity")})
        edges.append({"source": nid,
                       "relation": "entropy_raises_uncertainty",
                       "target": "node_entropy_signal"})
        for bid in (c.get("affected_beliefs") or []):
            edges.append({"source": nid,
                           "relation": "contradiction_challenges_belief",
                           "target": "node_belief_" + bid})

    # model_lane_suggests_text + kernel_validates_model_output + guardian
    for ln in (gov.get("lanes") or []):
        nid = "node_lane_" + (ln.get("lane_id") or "lane_x")
        nodes.append({"id": nid, "kind": "model_lane",
                       "label": ln.get("lane_id"),
                       "role": ln.get("role")})
        edges.append({"source": nid, "relation": "model_lane_suggests_text",
                       "target": "node_kernel_self"})
        edges.append({"source": "node_kernel_self",
                       "relation": "kernel_validates_model_output",
                       "target": nid})
        edges.append({"source": "node_guardian",
                       "relation": "guardian_validates_kernel_output",
                       "target": nid})

    # continuity_hash_links_state
    edges.append({"source": "node_kernel_self",
                   "relation": "continuity_hash_links_state",
                   "target": "node_memory"})

    # collapse_selects_hypothesis (use selected_hypothesis from quantum signal if available)
    quantum = load_json(REG / "eqsb_quantum_signal_state.json", {})
    sel = quantum.get("selected_hypothesis") or {}
    sel_id = sel.get("hypothesis_id")
    if sel_id:
        edges.append({"source": "node_quantum_signal",
                       "relation": "collapse_selects_hypothesis",
                       "target": "node_hypothesis_" + sel_id})

    # Preserve V1 nodes/edges (floors, workers, lock_matrix)
    v1_nodes = prev.get("nodes") or []
    v1_edges = prev.get("edges") or []
    # Avoid duplicating same id; carry over preserved kinds
    seen_ids = {n["id"] for n in nodes}
    for n in v1_nodes:
        nid = n.get("id")
        if nid and nid not in seen_ids and n.get("kind") in (
            "floor", "worker", "lock_matrix"
        ):
            nodes.append(n)
            seen_ids.add(nid)
    for e in v1_edges:
        if e.get("relation") in ("floor_routes_to_floor",
                                  "worker_assigned_to_floor",
                                  "lock_protects_execution_path",
                                  "model_lane_advises_kernel"):
            edges.append(e)

    node_kinds = sorted({n.get("kind") for n in nodes if n.get("kind")})
    relations_in_use = sorted({e.get("relation") for e in edges if e.get("relation")})

    orphan_symbols = []
    for n in nodes:
        if n.get("kind") == "symbol":
            sid = n.get("id")
            outgoing = any(e.get("source") == sid for e in edges)
            incoming = any(e.get("target") == sid for e in edges)
            if not (outgoing or incoming):
                orphan_symbols.append(sid)

    unsupported_beliefs = []
    contradicted_beliefs = []
    high_conf_beliefs = []
    for n in nodes:
        if n.get("kind") == "belief":
            bid = n.get("id")
            has_axiom_support = any(
                e.get("target") == bid and e.get("relation") == "axiom_supports_belief"
                for e in edges
            )
            has_contradiction = any(
                e.get("target") == bid and e.get("relation") == "contradiction_challenges_belief"
                for e in edges
            )
            if not has_axiom_support:
                unsupported_beliefs.append(bid)
            if has_contradiction:
                contradicted_beliefs.append(bid)
            if (n.get("confidence") or 0) >= 0.9:
                high_conf_beliefs.append(bid)

    payload = {
        "schema_version": EQSB_MAJOR_SCHEMA_VERSION,
        "kind": "eqsb_symbolic_graph",
        "generated_ts": now_iso(),
        "node_count": len(nodes),
        "edge_count": len(edges),
        "node_kinds": node_kinds,
        "relations_in_use": relations_in_use,
        "supported_node_kinds": KERNEL_NODE_KINDS,
        "supported_relations": KERNEL_RELATIONS,
        "orphan_symbols": orphan_symbols,
        "unsupported_beliefs": unsupported_beliefs,
        "contradicted_beliefs": contradicted_beliefs,
        "high_confidence_beliefs": high_conf_beliefs,
        "stale_symbols": [],
        "missing_expected_nodes": [],
        "nodes": nodes,
        "edges": edges,
    }
    payload.update(safety_envelope())
    payload["symbolic_graph_hash"] = stable_hash({
        "node_count": payload["node_count"],
        "edge_count": payload["edge_count"],
        "kinds": node_kinds,
        "relations": relations_in_use,
    })
    write_json(P_GRAPH, payload)
    append_event({"event": "build_symbolic_graph",
                  "node_count": payload["node_count"],
                  "edge_count": payload["edge_count"]})
    return payload


def build():
    return build_symbolic_graph()


if __name__ == "__main__":
    print(json.dumps(build(), indent=2))
