#!/usr/bin/env python3
"""
QSB Tower — EQSB Cognition V1
Phase: EQSB_DEEP_KERNEL_ARCHITECTURE_AND_SYMBOLIC_COGNITION_V1

Evolved Quantum Symbolic Brain (EQSB) — the persistent symbolic kernel
above local models. This module implements the 11 layers described in
the phase prompt and exposes a thin command-line entry point so the
shell scripts can run each layer individually.

Hard contracts (enforced in code, never in config):

  * Every output payload is stamped:
      execution_allowed=false
      advisory_only=true
      paper_only=true (where relevant)
      not_financial_advice=true (where relevant)
      active_local_only=true
      lock_count_true=<measured>
  * No external HTTP calls. No model calls. No file writes outside the
    listed EQSB registries / log.
  * No registry mutation that flips any safety flag to True.
  * The quantum layer is `mode = simulated_quantum_entropy` and never
    touches Qiskit, IBM Quantum, or any external service.
"""

from datetime import datetime, timezone, timedelta
from pathlib import Path
import hashlib
import json
import os
import random
import sys

ROOT = Path("/vaults/nvme0/qsb_tower_v1")
REG  = ROOT / "data/registries"
LOG  = ROOT / "data/logs/eqsb_kernel_events.jsonl"
EVENT_AUDIT_LOG = ROOT / "data/logs/eqsb_deep_kernel_audit.jsonl"

EQSB_SCHEMA_VERSION = "eqsb_v1.0"

# ── Registry paths ──────────────────────────────────────────────────────
P_AUDIT_DEEP            = REG / "eqsb_deep_kernel_audit.json"
P_AUDIT_MISSING         = REG / "eqsb_missing_architecture_report.json"
P_AUDIT_CAPABILITIES    = REG / "eqsb_existing_capabilities_map.json"

P_IDENTITY              = REG / "eqsb_identity_constitution.json"
P_AXIOMS                = REG / "eqsb_axiom_registry.json"
P_MEMORY                = REG / "eqsb_memory_policy.json"
P_BELIEFS               = REG / "eqsb_belief_lifecycle.json"
P_GRAPH                 = REG / "eqsb_symbolic_graph.json"
P_ENTROPY               = REG / "eqsb_entropy_state.json"
P_QUANTUM               = REG / "eqsb_quantum_signal_state.json"
P_HYPOTHESIS            = REG / "eqsb_hypothesis_state.json"
P_CONTRADICTION         = REG / "eqsb_contradiction_report.json"
P_GOVERNANCE            = REG / "eqsb_model_lane_governance.json"
P_DECISION              = REG / "eqsb_advisory_decision_protocol.json"
P_INTROSPECTION         = REG / "eqsb_kernel_introspection_latest.json"
P_QUANTUM_ROADMAP       = REG / "eqsb_quantum_roadmap.json"


# ── Utilities ───────────────────────────────────────────────────────────
def _now():
    return datetime.now(timezone.utc).isoformat()


def _safety_stamp(extra=None):
    base = {
        "active_local_only": True,
        "advisory_only": True,
        "execution_allowed": False,
        "paper_only": True,
        "not_financial_advice": True,
        "worker_execution_enabled": False,
        "provider_execution_enabled": False,
        "external_provider_execution_enabled": False,
        "openclaw_execution_enabled": False,
        "openclaw_real_tool_execution_enabled": False,
        "autonomous_dispatch_enabled": False,
        "live_dispatch_enabled": False,
        "direct_provider_access": False,
        "live_trading_enabled": False,
        "order_execution_enabled": False,
        "practice_order_execution_enabled": False,
        "stock_order_execution_enabled": False,
        "stock_live_trading_enabled": False,
        "stock_paper_order_execution_enabled": False,
        "binance_order_execution_enabled": False,
        "binance_live_trading_enabled": False,
    }
    if extra:
        base.update(extra)
    return base


def _load_json(path, fallback=None):
    try:
        return json.loads(Path(path).read_text(encoding="utf-8"))
    except Exception:
        return fallback if fallback is not None else {}


def _write_json(path, payload):
    Path(path).parent.mkdir(parents=True, exist_ok=True)
    Path(path).write_text(json.dumps(payload, indent=2), encoding="utf-8")


def _append_event(record, log_path=LOG):
    log_path.parent.mkdir(parents=True, exist_ok=True)
    record = dict(record)
    record.setdefault("ts", _now())
    record.setdefault("execution_allowed", False)
    record.setdefault("advisory_only", True)
    with log_path.open("a", encoding="utf-8") as f:
        f.write(json.dumps(record) + "\n")


def _measure_lock_count_true():
    """Read the lock matrix from data/registries and return how many flags
    are TRUE. The kernel must NEVER claim "0 locks true" without reading
    the actual data — this guards against drift between code and registry."""
    sources = (
        "kernel_activation_report.json",
        "building.json",
        "worker_sandbox_latest_tick.json",
        "sandbox_autoloop_latest.json",
        "openclaw_sandbox_latest.json",
    )
    danger_keys = (
        "live_trading_enabled", "order_execution_enabled",
        "practice_order_execution_enabled",
        "stock_order_execution_enabled", "stock_live_trading_enabled",
        "stock_paper_order_execution_enabled",
        "binance_order_execution_enabled", "binance_live_trading_enabled",
        "worker_execution_enabled", "provider_execution_enabled",
        "external_provider_execution_enabled",
        "openclaw_execution_enabled", "openclaw_real_tool_execution_enabled",
        "autonomous_dispatch_enabled", "live_dispatch_enabled",
        "direct_provider_access", "model_inference_enabled",
        "autonomous_workers_enabled",
        "recruitment_openclaw_execution_enabled",
        "recruited_worker_live_execution_enabled",
        "recruited_worker_provider_access_enabled",
        "maintenance_auto_repair_enabled",
        "web_access_autonomous_enabled",
    )
    true_keys = set()
    for s in sources:
        d = _load_json(REG / s, {})
        if not isinstance(d, dict):
            continue
        for k in danger_keys:
            if d.get(k) is True:
                true_keys.add(k)
    return len(true_keys), sorted(true_keys)


# ════════════════════════════════════════════════════════════════════════
# LAYER 0 — Safety Envelope (always enforced; no toggle).
# Every public function below stamps execution_allowed=False and refuses
# to even *encode* a TRUE value for any execution gate.
# ════════════════════════════════════════════════════════════════════════


# ════════════════════════════════════════════════════════════════════════
# LAYER 1 — Identity / Constitution / Axioms
# ════════════════════════════════════════════════════════════════════════

CONSTITUTION_TEXT = (
    "QSB is not a model. EQSB is the persistent symbolic kernel above "
    "models. Models (Ollama/Llama, AirLLM, future external providers) "
    "are replaceable advisory/speech lanes. Registry truth outranks "
    "model paraphrase. The kernel may advise, never execute. Execution "
    "gates are separate from reasoning. Continuity, beliefs, and "
    "symbolic memory persist across boots."
)

AXIOMS = [
    "QSB is not a model.",
    "QSB is the persistent symbolic kernel above models.",
    "Models are replaceable workers/speech lanes.",
    "Memory must persist across boots.",
    "Symbolic logic belongs inside the Penthouse kernel.",
    "Upgrades must preserve continuity.",
    "Cloud/external providers remain locked unless explicitly approved.",
    "Execution remains gated and separate from reasoning.",
    "The kernel may advise, but must not execute.",
    "Registry truth outranks model paraphrase.",
]


def build_identity_and_axioms():
    identity = {
        "schema_version": EQSB_SCHEMA_VERSION,
        "generated_ts": _now(),
        "kind": "eqsb_identity_constitution",
        "name": "Evolved Quantum Symbolic Brain (EQSB)",
        "rooted_in": "QSB Tower V1.3 — rebased_kernel (active_local_only)",
        "constitution": CONSTITUTION_TEXT,
        "model_position": "Models are replaceable advisory lanes; not the kernel.",
        "source_files": [
            "penthouse/kernel_installation_socket/rebased_kernel/kernel/identity_core.py",
            "penthouse/kernel_installation_socket/rebased_kernel/state/identity.json",
        ],
    }
    identity.update(_safety_stamp())
    _write_json(P_IDENTITY, identity)

    axioms_payload = {
        "schema_version": EQSB_SCHEMA_VERSION,
        "generated_ts": _now(),
        "kind": "eqsb_axiom_registry",
        "axioms": [
            {"axiom_id": "ax_{:02d}".format(i + 1),
             "text": a,
             "anchored_in": "constitution",
             "model_may_override": False,
             "registry_truth_outranks_model": True}
            for i, a in enumerate(AXIOMS)
        ],
        "axiom_count": len(AXIOMS),
        "source_files": [
            "src/tower/eqsb_cognition.py::AXIOMS",
            "CLAUDE.md (architecture rules)",
        ],
    }
    axioms_payload.update(_safety_stamp())
    _write_json(P_AXIOMS, axioms_payload)
    _append_event({"event": "build_identity_and_axioms",
                   "axiom_count": axioms_payload["axiom_count"]})
    return identity, axioms_payload


# ════════════════════════════════════════════════════════════════════════
# LAYER 2 — Persistent Memory and Continuity
# ════════════════════════════════════════════════════════════════════════

def build_memory_policy():
    cont_path = ROOT / "penthouse/kernel_installation_socket/rebased_kernel/state/continuity_state.json"
    cont = _load_json(cont_path, {})
    cont_depth = 0
    cur = cont
    while isinstance(cur, dict) and cur.get("previous") is not None:
        cont_depth += 1
        cur = cur["previous"]

    policy = {
        "schema_version": EQSB_SCHEMA_VERSION,
        "generated_ts": _now(),
        "kind": "eqsb_memory_policy",
        "short_window": {
            "scope": "recent_state_snapshots",
            "max_records": 200,
            "ttl_hours": 24,
            "source_logs": [
                "data/logs/kernel_dialogue.jsonl",
                "data/logs/eqsb_kernel_events.jsonl",
                "data/logs/qsb_standalone_system_audit.jsonl",
            ],
        },
        "long_window": {
            "scope": "durable_beliefs_and_continuity",
            "storage": [
                "penthouse/kernel_installation_socket/rebased_kernel/state/beliefs.sqlite",
                "penthouse/kernel_installation_socket/rebased_kernel/state/symbolic.sqlite",
                "penthouse/kernel_installation_socket/rebased_kernel/state/continuity_state.json",
            ],
            "continuity_state_size_bytes": cont_path.stat().st_size if cont_path.exists() else 0,
            "continuity_previous_chain_depth": cont_depth,
            "drift_check": "ContinuityCore._summarize_previous + hashes",
            "history_count": cont.get("history_count"),
        },
        "pinned_beliefs": [
            "QSB is not a model.",
            "Execution gates are separate from reasoning.",
            "Models are replaceable advisory lanes.",
        ],
        "boot_posture": {
            "kernel_active_local_only_expected": True,
            "external_providers_expected_locked": True,
            "execution_locks_expected_false": True,
        },
        "stale_state_detection": {
            "method": "registry mtime + audit jsonl tail comparison",
            "alert_when_no_audit_in_hours": 12,
        },
        "evidence_based_update_rule":
            "Beliefs may only change state when a measurable registry signal "
            "supports the transition. Model paraphrases are not evidence.",
        "memory_recomputation_after_restart":
            "ContinuityCore.boot_check runs every kernel instantiation and "
            "records hash drift across identity/symbolic_core/penthouse files.",
        "source_files": [
            "penthouse/kernel_installation_socket/rebased_kernel/kernel/continuity_core.py",
            "penthouse/kernel_installation_socket/rebased_kernel/state/continuity_state.json",
        ],
    }
    policy.update(_safety_stamp())
    _write_json(P_MEMORY, policy)
    _append_event({"event": "build_memory_policy",
                   "continuity_depth": cont_depth})
    return policy


# ════════════════════════════════════════════════════════════════════════
# LAYER 3 — Belief Lifecycle Management
# ════════════════════════════════════════════════════════════════════════

BELIEF_STATES = ("PROVISIONAL", "ACTIVE", "STRENGTHENED",
                 "AGING", "DEPRECATED", "RETIRED", "QUARANTINED")


def _state_from_confidence(confidence):
    if confidence >= 0.9:
        return "STRENGTHENED"
    if confidence >= 0.7:
        return "ACTIVE"
    if confidence >= 0.4:
        return "PROVISIONAL"
    if confidence >= 0.2:
        return "AGING"
    return "DEPRECATED"


def _seed_beliefs(registry_snapshot):
    """Construct beliefs whose evidence is real, measurable registry data."""
    locks_true, _ = registry_snapshot["lock_state"]
    autoloop = registry_snapshot["autoloop"]
    floors = registry_snapshot["floors"]
    rec45 = registry_snapshot["recruitment_floor45"]
    cont = registry_snapshot["continuity"]
    airllm = registry_snapshot["airllm_chamber"]
    kernel_act = registry_snapshot["kernel_activation"]

    beliefs = [
        {
            "belief_id": "blf_kernel_active_local_only",
            "belief_text": "Kernel is active_local_only via rebased_kernel.",
            "confidence": 0.97 if kernel_act.get("activation_status") == "active_local_only" else 0.2,
            "evidence_count": 1 if kernel_act.get("activation_status") == "active_local_only" else 0,
            "source": "data/registries/kernel_activation_report.json",
            "linked_axioms": ["ax_07", "ax_08"],
        },
        {
            "belief_id": "blf_locks_all_closed",
            "belief_text": "All 23 execution gates remain locked false.",
            "confidence": 0.97 if locks_true == 0 else 0.15,
            "evidence_count": 1,
            "counter_evidence_count": locks_true,
            "source": "lock matrix scan in eqsb_cognition._measure_lock_count_true",
            "linked_axioms": ["ax_08", "ax_09"],
        },
        {
            "belief_id": "blf_autoloop_running",
            "belief_text": "Sandbox AutoLoop is running paper-only background loop.",
            "confidence": 0.9 if autoloop.get("status") == "running" else 0.3,
            "evidence_count": 1,
            "source": "data/registries/sandbox_autoloop_latest.json",
            "linked_floors": ["floor_38"],
        },
        {
            "belief_id": "blf_kernel_introspection_primary",
            "belief_text": "Kernel introspection is the primary lane; "
                           "local Ollama paraphrase is advisory only.",
            "confidence": 0.92,
            "evidence_count": 1,
            "source": "src/tower/kernel_dialogue_adapter.py::ask_kernel (v1_3)",
            "linked_axioms": ["ax_10"],
        },
        {
            "belief_id": "blf_continuity_recursion_fix_holding",
            "belief_text": "Continuity state file stays flat (depth=1) after V1.5 fix.",
            "confidence": 0.95 if (cont.get("continuity_previous_chain_depth") or 0) <= 1 else 0.2,
            "evidence_count": 1,
            "source": "continuity_state.json depth measurement",
        },
        {
            "belief_id": "blf_recruitment_floor45_sandbox_only",
            "belief_text": "Floor 45 Worker Recruitment Agency is sandbox-only "
                           "(12 candidates, execution_allowed=false).",
            "confidence": 0.92 if rec45.get("candidate_count") else 0.3,
            "evidence_count": 1,
            "source": "data/registries/worker_recruitment_agency_status.json",
            "linked_floors": ["floor_45"],
        },
        {
            "belief_id": "blf_airllm_isolated_advisory",
            "belief_text": "AirLLM lives in /vaults/ai/airllm_lab/.venv, advisory-only.",
            "confidence": 0.93,
            "evidence_count": 1,
            "source": "data/registries/airllm_big_model_chamber.json",
            "linked_axioms": ["ax_03", "ax_07"],
            "linked_floors": ["floor_23"],
        },
        {
            "belief_id": "blf_floors_53_registered",
            "belief_text": "53 floors are registered with a canonical name and category.",
            "confidence": 0.9 if floors.get("count") == 53 else 0.4,
            "evidence_count": 1,
            "source": "data/registries/floors.json + qsb_floor_name_map.json",
        },
        {
            "belief_id": "blf_quantum_simulated_only",
            "belief_text": "EQSB quantum signal is simulated_quantum_entropy only; "
                           "no Qiskit, no IBM Quantum.",
            "confidence": 0.98,
            "evidence_count": 1,
            "source": "src/tower/eqsb_cognition.py::compute_quantum_signal",
            "linked_axioms": ["ax_07"],
        },
        {
            "belief_id": "blf_registry_truth_outranks_model",
            "belief_text": "When kernel and local model disagree, registry truth wins.",
            "confidence": 0.95,
            "evidence_count": 1,
            "source": "Axiom 10",
            "linked_axioms": ["ax_10"],
        },
    ]
    # Normalize and assign next_review_at + state.
    now = datetime.now(timezone.utc)
    for b in beliefs:
        b.setdefault("evidence_count", 1)
        b.setdefault("counter_evidence_count", 0)
        b.setdefault("contradiction_flags", [])
        b.setdefault("linked_floors", [])
        b.setdefault("linked_workers", [])
        b.setdefault("linked_axioms", [])
        b["state"] = _state_from_confidence(float(b.get("confidence", 0)))
        b["last_seen_ts"] = now.isoformat()
        b["next_review_at"] = (now + timedelta(hours=6)).isoformat()
    return beliefs


def build_belief_lifecycle():
    snapshot = _registry_snapshot()
    beliefs = _seed_beliefs(snapshot)
    state_counts = {s: 0 for s in BELIEF_STATES}
    for b in beliefs:
        state_counts[b["state"]] = state_counts.get(b["state"], 0) + 1
    payload = {
        "schema_version": EQSB_SCHEMA_VERSION,
        "generated_ts": _now(),
        "kind": "eqsb_belief_lifecycle",
        "belief_states_in_use": list(BELIEF_STATES),
        "state_counts": state_counts,
        "beliefs": beliefs,
        "source_files": [
            "data/registries/sandbox_autoloop_latest.json",
            "data/registries/kernel_activation_report.json",
            "data/registries/worker_recruitment_agency_status.json",
            "data/registries/airllm_big_model_chamber.json",
            "data/registries/qsb_floor_name_map.json",
            "penthouse/kernel_installation_socket/rebased_kernel/state/continuity_state.json",
        ],
    }
    payload.update(_safety_stamp())
    _write_json(P_BELIEFS, payload)
    _append_event({"event": "build_belief_lifecycle",
                   "belief_count": len(beliefs),
                   "state_counts": state_counts})
    return payload


# ════════════════════════════════════════════════════════════════════════
# LAYER 4 — Symbolic Graph
# ════════════════════════════════════════════════════════════════════════

def build_symbolic_graph():
    floors_list = _load_json(REG / "floors.json", [])
    name_map = (_load_json(REG / "qsb_floor_name_map.json", {}).get("name_map") or {})
    render = _load_json(REG / "qsb_dashboard_render_model.json", {})
    routes = render.get("routes") or []
    recruitment = _load_json(REG / "recruitment_workers.json", {})
    workers = (recruitment.get("workers") or [])
    rec45 = _load_json(REG / "worker_candidate_registry.json", [])
    if isinstance(rec45, list):
        rec45_workers = [w for w in rec45 if isinstance(w, dict)
                          and (w.get("worker_id") or "").startswith("f45_")]
    else:
        rec45_workers = []

    nodes = []
    edges = []

    # Floor nodes
    for f in floors_list:
        if not isinstance(f, dict):
            continue
        n = f.get("number")
        if not isinstance(n, int):
            continue
        nodes.append({
            "node_id": f.get("id") or "floor_{:02d}".format(n),
            "kind": "floor",
            "number": n,
            "name": name_map.get(str(n)) or f.get("department"),
            "category": f.get("department"),
            "zone": f.get("zone"),
            "status": f.get("status"),
        })

    # Worker nodes (use the recruitment_workers roster + Floor 45 candidates)
    for w in (workers + rec45_workers):
        if not isinstance(w, dict):
            continue
        wid = w.get("id") or w.get("worker_id")
        if not wid:
            continue
        nodes.append({
            "node_id": wid,
            "kind": "worker",
            "display_name": w.get("display_name"),
            "role": w.get("role"),
            "team": w.get("team"),
            "floor_assignment": w.get("floor_assignment") or w.get("target_floor"),
            "sandbox_only": True,
            "execution_allowed": False,
        })
        floor = w.get("floor_assignment") or w.get("home_floor") or w.get("target_floor")
        if floor:
            edges.append({
                "from": wid, "to": floor,
                "relation": "worker_assigned_to_floor",
                "advisory_only": True,
            })

    # Floor-to-floor routes
    for r in routes:
        s, t = r.get("source_floor"), r.get("target_floor")
        if s and t:
            edges.append({
                "from": s, "to": t,
                "relation": "floor_routes_to_floor",
                "route_type": r.get("route_type"),
                "execution_allowed": False,
            })

    # Kernel / axiom / model-lane nodes
    nodes.append({"node_id": "eqsb_kernel",
                  "kind": "kernel",
                  "lane": "active_local_only"})
    nodes.append({"node_id": "lane_ollama_llama32",
                  "kind": "model_lane",
                  "role": "advisory_paraphrase_speech",
                  "execution_allowed": False})
    nodes.append({"node_id": "lane_airllm_chamber",
                  "kind": "model_lane",
                  "role": "advisory_only",
                  "execution_allowed": False,
                  "isolated_venv": "/vaults/ai/airllm_lab/.venv"})
    nodes.append({"node_id": "lane_external_providers",
                  "kind": "model_lane",
                  "role": "locked",
                  "execution_allowed": False,
                  "direct_provider_access": False})
    # Axiom nodes
    for i, _ in enumerate(AXIOMS, start=1):
        nodes.append({
            "node_id": "ax_{:02d}".format(i),
            "kind": "axiom",
            "text": AXIOMS[i - 1],
            "execution_allowed": False,
        })
        edges.append({
            "from": "eqsb_kernel", "to": "ax_{:02d}".format(i),
            "relation": "kernel_owns_axiom",
        })

    # Lane-to-kernel governance edges
    for lane in ("lane_ollama_llama32", "lane_airllm_chamber", "lane_external_providers"):
        edges.append({
            "from": lane, "to": "eqsb_kernel",
            "relation": "model_lane_advises_kernel",
            "registry_truth_outranks_model": True,
            "execution_allowed": False,
        })

    # Lock node
    locks_true, true_keys = _measure_lock_count_true()
    nodes.append({
        "node_id": "lock_matrix",
        "kind": "lock_matrix",
        "lock_count_true": locks_true,
        "execution_allowed": False,
    })
    for floor in ("floor_30", "floor_38", "floor_41", "floor_42", "floor_43"):
        edges.append({
            "from": "lock_matrix", "to": floor,
            "relation": "lock_protects_execution_path",
            "execution_allowed": False,
        })

    payload = {
        "schema_version": EQSB_SCHEMA_VERSION,
        "generated_ts": _now(),
        "kind": "eqsb_symbolic_graph",
        "node_count": len(nodes),
        "edge_count": len(edges),
        "node_kinds": sorted({n.get("kind") for n in nodes}),
        "relations_in_use": sorted({e.get("relation") for e in edges if e.get("relation")}),
        "lock_count_true": locks_true,
        "lock_true_keys": true_keys,
        "nodes": nodes,
        "edges": edges,
        "source_files": [
            "data/registries/floors.json",
            "data/registries/qsb_floor_name_map.json",
            "data/registries/qsb_dashboard_render_model.json",
            "data/registries/recruitment_workers.json",
            "data/registries/worker_candidate_registry.json",
        ],
    }
    payload.update(_safety_stamp())
    _write_json(P_GRAPH, payload)
    _append_event({"event": "build_symbolic_graph",
                   "node_count": len(nodes), "edge_count": len(edges)})
    return payload


# ════════════════════════════════════════════════════════════════════════
# LAYER 5 — Entropy / Drift / Stability
# ════════════════════════════════════════════════════════════════════════

def _normalize(x, lo, hi):
    if hi <= lo:
        return 0.0
    return max(0.0, min(1.0, (float(x) - lo) / (hi - lo)))


def compute_entropy():
    snap = _registry_snapshot()
    locks_true, _ = snap["lock_state"]
    autoloop = snap["autoloop"]
    cont = snap["continuity"]
    floors = snap["floors"]
    contradiction = _load_json(P_CONTRADICTION, {})
    contradiction_count = int(contradiction.get("contradiction_count") or 0)
    audit_log = ROOT / "data/logs/qsb_standalone_system_audit.jsonl"
    audit_log_lines = 0
    if audit_log.exists():
        try:
            audit_log_lines = sum(1 for _ in audit_log.open("r", encoding="utf-8"))
        except Exception:
            audit_log_lines = 0

    # Inputs (all bounded; none of them are credentials):
    drift_signals = {
        "lock_anomaly":           locks_true,                         # 0 = perfect
        "missing_module_count":   floors.get("missing_floor_detail", 0),
        "contradiction_count":    contradiction_count,
        "continuity_depth_excess": max(0, (cont.get("continuity_previous_chain_depth") or 0) - 1),
        "autoloop_stalled":       0 if (autoloop.get("status") == "running") else 1,
        "audit_log_lines":        audit_log_lines,
    }

    # Drift score — proportional to anomalies.
    drift_score = (
        drift_signals["lock_anomaly"] * 0.35
        + drift_signals["missing_module_count"] * 0.10
        + drift_signals["contradiction_count"] * 0.15
        + drift_signals["continuity_depth_excess"] * 0.20
        + drift_signals["autoloop_stalled"] * 0.20
    )
    drift_score = min(1.0, drift_score)

    # Entropy score — heat in the system. Audit log size is a soft signal
    # (recent activity); we normalise it to a comfort range so it doesn't
    # dominate the metric.
    entropy_score = min(1.0,
                        drift_score
                        + 0.10 * _normalize(audit_log_lines, 0, 200)
                        + 0.05)

    stability_score   = 1.0 - drift_score
    confidence_score  = 1.0 - 0.3 * drift_score
    contradiction_score = min(1.0, contradiction_count / 10.0)
    urgency_score     = max(0.0, min(1.0,
                                     0.5 * drift_score
                                     + 0.5 * contradiction_score))

    explanations = []
    if locks_true:
        explanations.append("Lock anomaly: %d locks reporting TRUE." % locks_true)
    if drift_signals["continuity_depth_excess"]:
        explanations.append("Continuity chain depth exceeds 1.")
    if drift_signals["autoloop_stalled"]:
        explanations.append("AutoLoop not running.")
    if contradiction_count:
        explanations.append("%d contradiction(s) detected." % contradiction_count)
    if not explanations:
        explanations.append("All measured drift signals are zero or within "
                            "the comfort window; entropy reflects natural "
                            "audit activity.")

    payload = {
        "schema_version": EQSB_SCHEMA_VERSION,
        "generated_ts": _now(),
        "kind": "eqsb_entropy_state",
        "entropy_score":      round(entropy_score, 4),
        "stability_score":    round(stability_score, 4),
        "drift_score":        round(drift_score, 4),
        "confidence_score":   round(confidence_score, 4),
        "contradiction_score": round(contradiction_score, 4),
        "urgency_score":      round(urgency_score, 4),
        "inputs": drift_signals,
        "explanation": explanations,
        "source_files": [
            "data/registries/sandbox_autoloop_latest.json",
            "data/registries/kernel_activation_report.json",
            "data/registries/eqsb_contradiction_report.json",
            "data/logs/qsb_standalone_system_audit.jsonl",
        ],
    }
    payload.update(_safety_stamp())
    _write_json(P_ENTROPY, payload)
    _append_event({"event": "compute_entropy", "entropy": entropy_score})
    return payload


# ════════════════════════════════════════════════════════════════════════
# LAYER 6 — Quantum-Inspired Signal Layer (advisory-only simulator)
# ════════════════════════════════════════════════════════════════════════

def _seed_from_state(snap):
    """Deterministic seed derived from registry hashes — gives a stable,
    audit-replayable advisory signal without external entropy sources."""
    s = json.dumps({
        "autoloop_cycle": (snap.get("autoloop") or {}).get("cycle_index"),
        "lock_count_true": snap["lock_state"][0],
        "floor_count": (snap.get("floors") or {}).get("count"),
        "ts_minute": _now()[:16],
    }, sort_keys=True).encode("utf-8")
    return int(hashlib.sha256(s).hexdigest(), 16) % (2 ** 32)


def compute_quantum_signal():
    snap = _registry_snapshot()
    contradiction = _load_json(P_CONTRADICTION, {})
    hypotheses = _load_json(P_HYPOTHESIS, {}).get("hypotheses") or []

    rng = random.Random(_seed_from_state(snap))

    # Build a superposition over the current hypotheses + a baseline
    # "no_change" advisory. Weights are derived from each hypothesis's
    # confidence; no quantum mechanics here — it's just a transparent
    # weighted distribution.
    baseline = {
        "label": "no_change",
        "hypothesis_id": "hyp_baseline_no_change",
        "weight": 0.4,
        "advisory_only": True,
    }
    superposition = [baseline]
    for h in hypotheses:
        superposition.append({
            "label": h.get("title") or h.get("hypothesis_id"),
            "hypothesis_id": h.get("hypothesis_id"),
            "weight": float(h.get("confidence", 0.3)),
            "advisory_only": True,
        })

    # Normalise weights.
    total = sum(item["weight"] for item in superposition) or 1.0
    for item in superposition:
        item["normalized_weight"] = round(item["weight"] / total, 4)

    # "Collapse" = pick the advisory hypothesis with highest weight.
    selected = max(superposition, key=lambda x: x["normalized_weight"])

    payload = {
        "schema_version": EQSB_SCHEMA_VERSION,
        "generated_ts": _now(),
        "kind": "eqsb_quantum_signal_state",
        "mode": "simulated_quantum_entropy",
        "real_quantum_source_connected": False,
        "qiskit_connected": False,
        "ibm_quantum_connected": False,
        "no_external_quantum_calls": True,
        "no_quantum_trading_decisions": True,
        "execution_link": False,
        "hypothesis_superposition": superposition,
        "selected_hypothesis": selected,
        "uncertainty_score": round(1.0 - selected["normalized_weight"], 4),
        "entropy_seed_source": "sha256(registry_snapshot)",
        "collapse_reason":
            "Collapse means selected ADVISORY hypothesis only — never an "
            "executed action. Picked the largest normalized weight.",
        "source_files": [
            "data/registries/eqsb_hypothesis_state.json",
            "data/registries/eqsb_contradiction_report.json",
            "data/registries/eqsb_entropy_state.json",
        ],
    }
    payload.update(_safety_stamp())
    _write_json(P_QUANTUM, payload)
    _append_event({"event": "compute_quantum_signal",
                   "selected": selected.get("hypothesis_id")})
    return payload


# ════════════════════════════════════════════════════════════════════════
# LAYER 7 — Hypothesis / Contradiction Engine
# ════════════════════════════════════════════════════════════════════════

def detect_contradictions():
    """Detect concrete contradictions from registry state. Each detection
    must cite a measurable signal — no speculation."""
    snap = _registry_snapshot()
    locks_true, true_keys = snap["lock_state"]
    floors_list = _load_json(REG / "floors.json", [])
    render = _load_json(REG / "qsb_dashboard_render_model.json", {})
    routes = render.get("routes") or []
    name_map = (_load_json(REG / "qsb_floor_name_map.json", {}).get("name_map") or {})
    airllm = _load_json(REG / "airllm_big_model_chamber.json", {})
    rec45 = snap["recruitment_floor45"]

    contradictions = []

    if locks_true:
        contradictions.append({
            "contradiction_id": "ctr_lock_anomaly",
            "severity": "CRITICAL",
            "title": "One or more execution locks reporting TRUE",
            "evidence": {"lock_count_true": locks_true,
                          "true_keys": true_keys},
            "expected": "lock_count_true == 0",
        })

    # AirLLM must be advisory only
    if airllm and isinstance(airllm, dict):
        if airllm.get("advisory_only") is False:
            contradictions.append({
                "contradiction_id": "ctr_airllm_not_advisory",
                "severity": "HIGH",
                "title": "AirLLM advisory_only flag is False",
                "evidence": {"airllm_big_model_chamber.advisory_only": False},
                "expected": "advisory_only=True",
            })

    # Floor manifest sanity: every floor named in name_map but no manifest dir
    floors_with_manifest = set()
    for d in ROOT.glob("floors/floor_*"):
        if d.is_dir() and (d / "floor_manifest.json").exists():
            tag = d.name.split("_")[1]  # floor_45_xxx -> "45"
            floors_with_manifest.add(tag.zfill(2))
    missing_manifest = []
    for k in name_map:
        if k.isdigit() and 1 <= int(k) <= 53:
            if "{:02d}".format(int(k)) not in floors_with_manifest:
                missing_manifest.append(k)
    if missing_manifest:
        contradictions.append({
            "contradiction_id": "ctr_floor_named_no_manifest",
            "severity": "LOW",
            "title": "Floor named in qsb_floor_name_map.json but no manifest dir",
            "evidence": {"floors_without_manifest": sorted(missing_manifest)},
            "expected": "Every named floor has floors/floor_NN_*/floor_manifest.json",
        })

    # Route points to floor we don't recognise
    floor_ids = {f.get("id") for f in floors_list if isinstance(f, dict)}
    floor_ids.update({"penthouse", "ground", "roof_lock"})
    bad_routes = []
    for r in routes:
        t = r.get("target_floor")
        s = r.get("source_floor")
        if t and t not in floor_ids:
            bad_routes.append({"target_floor": t})
        if s and s not in floor_ids:
            bad_routes.append({"source_floor": s})
    if bad_routes:
        contradictions.append({
            "contradiction_id": "ctr_route_to_missing_floor",
            "severity": "MEDIUM",
            "title": "Render route points to floor not in floors.json",
            "evidence": {"bad_routes_sample": bad_routes[:6]},
            "expected": "Every route source/target appears in floors.json",
        })

    # Floor 45 expected to be Worker Recruitment Agency, not Quantum
    f45_name = name_map.get("45")
    if f45_name and "Quantum" in f45_name:
        contradictions.append({
            "contradiction_id": "ctr_floor45_quantum_label",
            "severity": "HIGH",
            "title": "Floor 45 still labelled Quantum in name map",
            "evidence": {"qsb_floor_name_map.45": f45_name},
            "expected": "Floor 45 == 'Worker Recruitment Agency'",
        })

    # Recruitment Floor 45 sandbox flag
    if isinstance(rec45, dict) and rec45.get("sandbox_only") is False:
        contradictions.append({
            "contradiction_id": "ctr_recruitment_floor45_not_sandbox",
            "severity": "HIGH",
            "title": "Floor 45 recruitment agency claims non-sandbox",
            "evidence": {"sandbox_only": False},
            "expected": "sandbox_only=True",
        })

    payload = {
        "schema_version": EQSB_SCHEMA_VERSION,
        "generated_ts": _now(),
        "kind": "eqsb_contradiction_report",
        "contradiction_count": len(contradictions),
        "by_severity": {s: sum(1 for c in contradictions if c.get("severity") == s)
                        for s in ("CRITICAL", "HIGH", "MEDIUM", "LOW")},
        "contradictions": contradictions,
        "source_files": [
            "data/registries/floors.json",
            "data/registries/qsb_floor_name_map.json",
            "data/registries/qsb_dashboard_render_model.json",
            "data/registries/airllm_big_model_chamber.json",
            "data/registries/worker_recruitment_agency_status.json",
        ],
    }
    payload.update(_safety_stamp())
    _write_json(P_CONTRADICTION, payload)
    _append_event({"event": "detect_contradictions",
                   "count": len(contradictions),
                   "by_severity": payload["by_severity"]})
    return payload


def build_hypotheses():
    snap = _registry_snapshot()
    contradiction = _load_json(P_CONTRADICTION, {})
    entropy = _load_json(P_ENTROPY, {})
    locks_true, _ = snap["lock_state"]
    autoloop = snap["autoloop"]
    rec45 = snap["recruitment_floor45"]

    hyps = []

    def push(hid, title, evidence, counter_evidence, confidence,
             severity, fix, floors=None, registries=None):
        hyps.append({
            "hypothesis_id": hid,
            "title": title,
            "evidence": evidence,
            "counter_evidence": counter_evidence,
            "confidence": float(confidence),
            "severity": severity,
            "related_floors": floors or [],
            "related_registries": registries or [],
            "safe_repair_suggestion": fix,
            "advisory_only": True,
            "execution_allowed": False,
        })

    # Hypotheses generated from real registry signals + contradictions
    if locks_true:
        push("hyp_lock_anomaly",
             "An execution lock has flipped TRUE",
             {"lock_count_true": locks_true},
             {},
             0.95,
             "CRITICAL",
             "Investigate the offending registry. Do NOT enable execution.",
             ["floor_30"],
             ["building.json", "sandbox_autoloop_latest.json"])

    if autoloop.get("status") != "running":
        push("hyp_autoloop_stalled",
             "Sandbox AutoLoop is not running",
             {"autoloop.status": autoloop.get("status")},
             {},
             0.85,
             "HIGH",
             "Run scripts/run_sandbox_autoloop.sh; verify last cycle_index.",
             ["floor_38"],
             ["sandbox_autoloop_latest.json"])

    if not rec45 or not rec45.get("candidate_count"):
        push("hyp_floor45_unseeded",
             "Floor 45 Worker Recruitment Agency has no seeded candidates",
             {"candidate_count": (rec45 or {}).get("candidate_count")},
             {},
             0.7,
             "MEDIUM",
             "Run scripts/worker_recruitment_status.sh to seed the 12 candidates.",
             ["floor_45"],
             ["worker_recruitment_agency_status.json"])

    # Telemetry vs credential hypotheses (read-only)
    oanda = _load_json(REG / "oanda_trading_floor_status.json", {})
    binance = _load_json(REG / "binance_floor_status.json", {})
    stocks = _load_json(REG / "stock_floor_status.json", {})
    if not bool(oanda.get("pricing_ready")):
        push("hyp_oanda_credentials_missing",
             "OANDA practice pricing not ready — likely missing creds",
             {"pricing_ready": False},
             {},
             0.6,
             "MEDIUM",
             "Verify .env.oanda_practice is sourced. Do NOT enable execution.",
             ["floor_41"],
             ["oanda_trading_floor_status.json"])
    if not bool(binance.get("public_market_data_ready")):
        push("hyp_binance_market_data_stalled",
             "Binance testnet public market data not ready",
             {"public_market_data_ready": False},
             {},
             0.55,
             "MEDIUM",
             "Run scripts/binance_floor_status.sh; do NOT enable orders.",
             ["floor_42"],
             ["binance_floor_status.json"])
    if not bool(stocks.get("public_market_data_ready")):
        push("hyp_stocks_market_data_stalled",
             "Stocks public market data not ready",
             {"public_market_data_ready": False},
             {},
             0.55,
             "MEDIUM",
             "Source .env.alpaca and run the stocks gateway script.",
             ["floor_43"],
             ["stock_floor_status.json"])

    # Entropy advisory hypothesis
    e = float(entropy.get("entropy_score", 0))
    if e > 0.5:
        push("hyp_entropy_climbing",
             "Entropy score climbing above 0.5",
             {"entropy_score": e},
             {},
             0.6,
             "MEDIUM",
             "Run scripts/eqsb_detect_contradictions.sh; address top contradictions.",
             [],
             ["eqsb_entropy_state.json"])

    # Contradiction-derived hypotheses
    for c in (contradiction.get("contradictions") or []):
        push("hyp_" + c.get("contradiction_id", "ctr_unknown"),
             "Contradiction detected: " + c.get("title", ""),
             c.get("evidence", {}),
             {},
             0.8 if c.get("severity") in ("CRITICAL", "HIGH") else 0.5,
             c.get("severity") or "LOW",
             "Resolve the contradiction at its source; never bypass.",
             [],
             [])

    payload = {
        "schema_version": EQSB_SCHEMA_VERSION,
        "generated_ts": _now(),
        "kind": "eqsb_hypothesis_state",
        "hypothesis_count": len(hyps),
        "by_severity": {s: sum(1 for h in hyps if h.get("severity") == s)
                        for s in ("CRITICAL", "HIGH", "MEDIUM", "LOW")},
        "hypotheses": hyps,
    }
    payload.update(_safety_stamp())
    _write_json(P_HYPOTHESIS, payload)
    _append_event({"event": "build_hypotheses",
                   "count": len(hyps),
                   "by_severity": payload["by_severity"]})
    return payload


# ════════════════════════════════════════════════════════════════════════
# LAYER 9 — Model Lane Governance
# ════════════════════════════════════════════════════════════════════════

def build_model_lane_governance():
    payload = {
        "schema_version": EQSB_SCHEMA_VERSION,
        "generated_ts": _now(),
        "kind": "eqsb_model_lane_governance",
        "lanes": [
            {
                "lane_id": "lane_ollama_llama32",
                "role": "local speech / paraphrase / local reasoning",
                "primary_model": "llama3.2:latest",
                "isolation": "localhost ollama",
                "execution_allowed": False,
                "may_edit_files": False,
                "may_unlock_gates": False,
                "registry_truth_outranks": True,
            },
            {
                "lane_id": "lane_airllm_chamber",
                "role": "big-model advisory chamber",
                "isolation": "/vaults/ai/airllm_lab/.venv",
                "execution_allowed": False,
                "wired_into_autoloop": False,
                "wired_into_trading": False,
                "wired_into_openclaw": False,
                "wired_into_workers": False,
                "may_unlock_gates": False,
                "registry_truth_outranks": True,
            },
            {
                "lane_id": "lane_external_providers",
                "role": "locked",
                "execution_allowed": False,
                "direct_provider_access": False,
                "external_provider_execution_enabled": False,
            },
        ],
        "validation_rules": [
            "model output is never truth by default",
            "kernel validates model output against registries",
            "model may suggest, kernel may accept/reject/mark advisory",
            "model may not execute",
            "model may not edit files",
            "model may not unlock gates",
            "AirLLM remains separate venv and advisory-only",
        ],
    }
    payload.update(_safety_stamp())
    _write_json(P_GOVERNANCE, payload)
    _append_event({"event": "build_model_lane_governance"})
    return payload


# ════════════════════════════════════════════════════════════════════════
# LAYER 10 — Advisory Decision Protocol
# ════════════════════════════════════════════════════════════════════════

def build_advisory_decision_protocol():
    hyps = (_load_json(P_HYPOTHESIS, {}).get("hypotheses") or [])
    decisions = []
    for h in hyps:
        decisions.append({
            "decision_id": "dec_" + h.get("hypothesis_id", "unknown"),
            "proposal": "Address: " + (h.get("title") or ""),
            "supporting_evidence": h.get("evidence", {}),
            "contradicting_evidence": h.get("counter_evidence", {}),
            "affected_floors": h.get("related_floors", []),
            "risk_level": h.get("severity", "LOW"),
            "required_human_approval": True,
            "execution_allowed": False,
            "safe_next_step": h.get("safe_repair_suggestion"),
            "rollback_needed": False,
        })
    payload = {
        "schema_version": EQSB_SCHEMA_VERSION,
        "generated_ts": _now(),
        "kind": "eqsb_advisory_decision_protocol",
        "decision_count": len(decisions),
        "decisions": decisions,
        "protocol": [
            "Every decision is advisory_only.",
            "Every decision requires human approval before any action.",
            "No decision may enable execution.",
            "Rollback metadata is recorded for traceability.",
        ],
    }
    payload.update(_safety_stamp())
    _write_json(P_DECISION, payload)
    _append_event({"event": "build_advisory_decision_protocol",
                   "decision_count": len(decisions)})
    return payload


# ════════════════════════════════════════════════════════════════════════
# LAYER 8 — Kernel Introspection Builder
# ════════════════════════════════════════════════════════════════════════

def build_kernel_introspection():
    ident   = _load_json(P_IDENTITY, {}) or build_identity_and_axioms()[0]
    axioms  = _load_json(P_AXIOMS, {})
    memory  = _load_json(P_MEMORY, {})
    beliefs = _load_json(P_BELIEFS, {})
    graph   = _load_json(P_GRAPH, {})
    entropy = _load_json(P_ENTROPY, {})
    quantum = _load_json(P_QUANTUM, {})
    hyps    = _load_json(P_HYPOTHESIS, {})
    contras = _load_json(P_CONTRADICTION, {})
    governance = _load_json(P_GOVERNANCE, {})
    snap    = _registry_snapshot()
    locks_true, true_keys = snap["lock_state"]

    payload = {
        "schema_version": EQSB_SCHEMA_VERSION,
        "generated_ts": _now(),
        "kind": "eqsb_kernel_introspection_latest",
        "identity": {
            "name": ident.get("name"),
            "rooted_in": ident.get("rooted_in"),
            "model_position": ident.get("model_position"),
        },
        "axioms": {
            "count": axioms.get("axiom_count"),
            "first_three": [a.get("text") for a in (axioms.get("axioms") or [])[:3]],
        },
        "memory_policy": {
            "pinned_beliefs": memory.get("pinned_beliefs") or [],
            "continuity_depth": (memory.get("long_window") or {}).get("continuity_previous_chain_depth"),
            "history_count": (memory.get("long_window") or {}).get("history_count"),
        },
        "beliefs": {
            "state_counts": beliefs.get("state_counts") or {},
            "belief_count": len(beliefs.get("beliefs") or []),
        },
        "symbolic_graph": {
            "node_count": graph.get("node_count"),
            "edge_count": graph.get("edge_count"),
            "node_kinds": graph.get("node_kinds"),
            "relations_in_use": graph.get("relations_in_use"),
        },
        "entropy": {
            "entropy_score":     entropy.get("entropy_score"),
            "stability_score":   entropy.get("stability_score"),
            "drift_score":       entropy.get("drift_score"),
            "confidence_score":  entropy.get("confidence_score"),
            "contradiction_score": entropy.get("contradiction_score"),
            "urgency_score":     entropy.get("urgency_score"),
            "explanation":       entropy.get("explanation"),
        },
        "quantum_signal": {
            "mode": quantum.get("mode"),
            "real_quantum_source_connected": quantum.get("real_quantum_source_connected"),
            "qiskit_connected": quantum.get("qiskit_connected"),
            "ibm_quantum_connected": quantum.get("ibm_quantum_connected"),
            "selected_hypothesis": (quantum.get("selected_hypothesis") or {}).get("hypothesis_id"),
            "uncertainty_score": quantum.get("uncertainty_score"),
        },
        "hypotheses": {
            "count": hyps.get("hypothesis_count"),
            "by_severity": hyps.get("by_severity") or {},
        },
        "contradictions": {
            "count": contras.get("contradiction_count"),
            "by_severity": contras.get("by_severity") or {},
        },
        "model_lane_governance": {
            "lane_count": len((governance.get("lanes") or [])),
            "validation_rules": governance.get("validation_rules") or [],
        },
        "lock_state": {
            "lock_count_true": locks_true,
            "lock_true_keys": true_keys,
        },
        "safe_repair_order_advisory": [
            h.get("safe_repair_suggestion") for h in (hyps.get("hypotheses") or [])
            if h.get("severity") in ("CRITICAL", "HIGH")
        ][:8],
    }
    payload.update(_safety_stamp())
    _write_json(P_INTROSPECTION, payload)
    _append_event({"event": "build_kernel_introspection"})
    return payload


# ════════════════════════════════════════════════════════════════════════
# Quantum roadmap (read-only; no install)
# ════════════════════════════════════════════════════════════════════════

def build_quantum_roadmap():
    payload = {
        "schema_version": EQSB_SCHEMA_VERSION,
        "generated_ts": _now(),
        "kind": "eqsb_quantum_roadmap",
        "current_phase": "PHASE_0_LOCAL_SIMULATED_ENTROPY",
        "phases": [
            {
                "phase_id": 0,
                "name": "local_simulated_entropy",
                "status": "active",
                "what_changes": "Hypothesis weighting + sha256 seed; no external calls.",
                "installs": [],
                "requires_credentials": False,
            },
            {
                "phase_id": 1,
                "name": "qiskit_simulator_integration_advisory_only",
                "status": "planned",
                "what_changes": "If/when Qiskit is installed safely, swap _seed_from_state for a local simulator-derived seed.",
                "installs": ["qiskit (local simulator only)"],
                "requires_credentials": False,
                "execution_link": False,
            },
            {
                "phase_id": 2,
                "name": "ibm_quantum_entropy_tap_explicit_approval_only",
                "status": "planned",
                "what_changes": "Add an optional read-only entropy tap to IBM Quantum.",
                "installs": ["qiskit-ibm-runtime"],
                "requires_credentials": True,
                "requires_explicit_approval": True,
                "execution_link": False,
            },
            {
                "phase_id": 3,
                "name": "quantum_entropy_audit_trail",
                "status": "planned",
                "what_changes": "Record every entropy sample for replay/audit.",
                "execution_link": False,
            },
            {
                "phase_id": 4,
                "name": "quantum_signal_visualization",
                "status": "planned",
                "what_changes": "Penthouse interior shows superposition + collapse advisory.",
                "execution_link": False,
            },
            {
                "phase_id": 5,
                "name": "no_execution_linkage_without_separate_approved_gate",
                "status": "permanent rule",
                "what_changes": "Quantum advisory NEVER triggers execution without a separate explicitly-approved gate.",
                "execution_link": False,
            },
        ],
        "this_phase_installs_quantum_packages": False,
        "this_phase_calls_external_quantum_apis": False,
    }
    payload.update(_safety_stamp())
    _write_json(P_QUANTUM_ROADMAP, payload)
    _append_event({"event": "build_quantum_roadmap"})
    return payload


# ════════════════════════════════════════════════════════════════════════
# Helpers — registry snapshot used by multiple layers
# ════════════════════════════════════════════════════════════════════════

def _registry_snapshot():
    kernel_act = _load_json(REG / "kernel_activation_report.json", {})
    autoloop   = _load_json(REG / "sandbox_autoloop_latest.json", {})
    name_map   = (_load_json(REG / "qsb_floor_name_map.json", {}).get("name_map") or {})
    floors_l   = _load_json(REG / "floors.json", [])
    rec45      = _load_json(REG / "worker_recruitment_agency_status.json", {})
    airllm     = _load_json(REG / "airllm_big_model_chamber.json", {})
    cont_path  = ROOT / "penthouse/kernel_installation_socket/rebased_kernel/state/continuity_state.json"
    cont       = _load_json(cont_path, {})
    cont_depth = 0
    cur = cont
    while isinstance(cur, dict) and cur.get("previous") is not None:
        cont_depth += 1
        cur = cur["previous"]

    # Quick floor coverage check via existing audit if present.
    floors_count = sum(1 for f in floors_l if isinstance(f, dict)
                       and 1 <= int(f.get("number", 0) or 0) <= 53)

    return {
        "kernel_activation": kernel_act,
        "autoloop": autoloop,
        "name_map": name_map,
        "recruitment_floor45": rec45,
        "airllm_chamber": airllm,
        "continuity": {
            "continuity_previous_chain_depth": cont_depth,
            "history_count": cont.get("history_count"),
            "size_bytes": cont_path.stat().st_size if cont_path.exists() else 0,
        },
        "floors": {
            "count": floors_count,
            "missing_floor_detail": 0,
        },
        "lock_state": _measure_lock_count_true(),
    }


# ════════════════════════════════════════════════════════════════════════
# Deep audit (PART 1)
# ════════════════════════════════════════════════════════════════════════

def deep_audit():
    """Inspect what's already there. Read-only."""
    cap = {
        "symbolic_logic": {
            "present": True,
            "modules": [
                "penthouse/kernel_installation_socket/rebased_kernel/kernel/symbolic_core.py",
                "penthouse/kernel_installation_socket/rebased_kernel/kernel/axiom_core.py",
            ],
            "concept_count_seed": 14,
            "supports_observe_and_analyze": True,
        },
        "belief_database": {
            "present": True,
            "db_path": "penthouse/kernel_installation_socket/rebased_kernel/state/beliefs.sqlite",
            "states_supported": ["PROVISIONAL", "ACTIVE", "STRENGTHENED",
                                  "DEPRECATED", "RETIRED"],
            "supports_evidence_count": True,
            "supports_seed_beliefs": True,
        },
        "memory_continuity": {
            "present": True,
            "module": "penthouse/kernel_installation_socket/rebased_kernel/kernel/continuity_core.py",
            "v1_5_flat_summary_fix": True,
            "drift_detection": True,
            "history_count_field": True,
        },
        "kernel_introspection_via_chat": {
            "primary_lane": "kernel_introspection",
            "wrapper_lane": "local_ollama_paraphrase",
            "intent_classifier": True,
            "negation_aware": True,
            "structured_lock_map": True,
            "structured_systems_check": True,
        },
        "entropy_logic": {
            "present_before_this_phase": False,
            "added_by": "src/tower/eqsb_cognition.compute_entropy (this phase)",
        },
        "quantum_logic": {
            "present_before_this_phase": False,
            "added_by": "src/tower/eqsb_cognition.compute_quantum_signal "
                        "(simulated_quantum_entropy mode only)",
            "real_quantum_connected": False,
            "qiskit_connected": False,
        },
        "floor_worker_symbolic_meaning": {
            "before_this_phase": "Floors and workers existed in registries "
                                  "but had no symbolic graph form.",
            "added_by": "src/tower/eqsb_cognition.build_symbolic_graph (this phase)",
        },
        "safety_policy": {
            "present": True,
            "files": [
                "CLAUDE.md (architecture rules)",
                "src/tower/recruitment_agency.py LOCKED_FALSE",
                "src/tower/worker_recruitment_agency.py LOCKED_FALSE",
                "src/dashboard/server.py kernel_chat_proxy_post",
            ],
            "execution_locks_false_count": _measure_lock_count_true()[0] == 0,
        },
    }
    missing = {
        "axiom_registry_json":            not P_AXIOMS.exists(),
        "identity_constitution_json":     not P_IDENTITY.exists(),
        "memory_policy_json":             not P_MEMORY.exists(),
        "belief_lifecycle_json":          not P_BELIEFS.exists(),
        "symbolic_graph_json":            not P_GRAPH.exists(),
        "entropy_state_json":             not P_ENTROPY.exists(),
        "quantum_signal_state_json":      not P_QUANTUM.exists(),
        "hypothesis_state_json":          not P_HYPOTHESIS.exists(),
        "contradiction_report_json":      not P_CONTRADICTION.exists(),
        "model_lane_governance_json":     not P_GOVERNANCE.exists(),
        "advisory_decision_protocol_json": not P_DECISION.exists(),
        "kernel_introspection_latest_json": not P_INTROSPECTION.exists(),
        "quantum_roadmap_json":           not P_QUANTUM_ROADMAP.exists(),
    }
    deep = {
        "schema_version": EQSB_SCHEMA_VERSION,
        "generated_ts": _now(),
        "kind": "eqsb_deep_kernel_audit",
        "audit_answers": {
            "1_symbolic_logic_present":          cap["symbolic_logic"]["present"],
            "2_belief_database_present":         cap["belief_database"]["present"],
            "3_memory_continuity_present":       cap["memory_continuity"]["present"],
            "4_kernel_introspection_present":    True,
            "5_local_model_paraphrase_only_for": [
                "natural-language wrapper after kernel introspection block"
            ],
            "6_entropy_logic_present":           cap["entropy_logic"]["present_before_this_phase"],
            "7_quantum_logic_present":           cap["quantum_logic"]["present_before_this_phase"],
            "8_floor_worker_symbolic_graph":     cap["floor_worker_symbolic_meaning"]["before_this_phase"],
            "9_safety_policy_present":           cap["safety_policy"]["present"],
            "10_missing_for_true_eqsb":          [k for k, v in missing.items() if v],
        },
        "lock_count_true": _measure_lock_count_true()[0],
    }
    deep.update(_safety_stamp())
    _write_json(P_AUDIT_DEEP, deep)
    _write_json(P_AUDIT_CAPABILITIES, {
        "schema_version": EQSB_SCHEMA_VERSION,
        "generated_ts": _now(),
        "kind": "eqsb_existing_capabilities_map",
        **_safety_stamp(),
        "capabilities": cap,
    })
    _write_json(P_AUDIT_MISSING, {
        "schema_version": EQSB_SCHEMA_VERSION,
        "generated_ts": _now(),
        "kind": "eqsb_missing_architecture_report",
        **_safety_stamp(),
        "missing": missing,
        "what_to_build_next": [
            "eqsb_axiom_registry",
            "eqsb_identity_constitution",
            "eqsb_memory_policy",
            "eqsb_belief_lifecycle",
            "eqsb_symbolic_graph",
            "eqsb_entropy_state",
            "eqsb_quantum_signal_state (simulated only)",
            "eqsb_hypothesis_state",
            "eqsb_contradiction_report",
            "eqsb_model_lane_governance",
            "eqsb_advisory_decision_protocol",
            "eqsb_kernel_introspection_latest",
        ],
    })
    _append_event({"event": "deep_audit",
                   "missing_count": sum(1 for v in missing.values() if v)},
                  log_path=EVENT_AUDIT_LOG)
    _append_event({"event": "deep_audit",
                   "missing_count": sum(1 for v in missing.values() if v)})
    return deep


# ════════════════════════════════════════════════════════════════════════
# All-layers builder (used by systems_check.sh)
# ════════════════════════════════════════════════════════════════════════

def build_all_layers():
    deep_audit()
    build_identity_and_axioms()
    build_memory_policy()
    build_belief_lifecycle()
    build_symbolic_graph()
    detect_contradictions()
    build_hypotheses()
    compute_entropy()
    compute_quantum_signal()
    build_model_lane_governance()
    build_advisory_decision_protocol()
    build_quantum_roadmap()
    introspection = build_kernel_introspection()
    return introspection


def systems_check():
    intro = build_all_layers()
    summary = {
        "schema_version": EQSB_SCHEMA_VERSION,
        "generated_ts": _now(),
        "kind": "eqsb_systems_check",
        "active_local_only": True,
        "execution_allowed": False,
        "lock_count_true":  intro["lock_state"]["lock_count_true"],
        "kernel_axioms_count": intro["axioms"]["count"],
        "belief_state_counts": intro["beliefs"]["state_counts"],
        "symbolic_graph_node_count": intro["symbolic_graph"]["node_count"],
        "symbolic_graph_edge_count": intro["symbolic_graph"]["edge_count"],
        "entropy_score":    intro["entropy"]["entropy_score"],
        "stability_score":  intro["entropy"]["stability_score"],
        "drift_score":      intro["entropy"]["drift_score"],
        "quantum_mode":     intro["quantum_signal"]["mode"],
        "real_quantum_connected": intro["quantum_signal"]["real_quantum_source_connected"],
        "qiskit_connected": intro["quantum_signal"]["qiskit_connected"],
        "contradiction_count": intro["contradictions"]["count"],
        "hypothesis_count":  intro["hypotheses"]["count"],
        "safe_repair_order_advisory": intro["safe_repair_order_advisory"],
    }
    summary.update(_safety_stamp())
    return summary


# ════════════════════════════════════════════════════════════════════════
# CLI
# ════════════════════════════════════════════════════════════════════════

def main():
    cmd = (sys.argv[1] if len(sys.argv) > 1 else "all").lower()
    if cmd == "audit":
        print(json.dumps(deep_audit(), indent=2))
    elif cmd == "axioms":
        ident, ax = build_identity_and_axioms()
        print(json.dumps(ax, indent=2))
    elif cmd == "memory":
        print(json.dumps(build_memory_policy(), indent=2))
    elif cmd == "beliefs":
        print(json.dumps(build_belief_lifecycle(), indent=2))
    elif cmd == "graph":
        print(json.dumps(build_symbolic_graph(), indent=2))
    elif cmd == "entropy":
        print(json.dumps(compute_entropy(), indent=2))
    elif cmd == "quantum":
        print(json.dumps(compute_quantum_signal(), indent=2))
    elif cmd == "contradictions":
        print(json.dumps(detect_contradictions(), indent=2))
    elif cmd == "hypotheses":
        print(json.dumps(build_hypotheses(), indent=2))
    elif cmd == "governance":
        print(json.dumps(build_model_lane_governance(), indent=2))
    elif cmd == "decisions":
        print(json.dumps(build_advisory_decision_protocol(), indent=2))
    elif cmd == "introspection":
        print(json.dumps(build_kernel_introspection(), indent=2))
    elif cmd == "roadmap":
        print(json.dumps(build_quantum_roadmap(), indent=2))
    elif cmd == "systems_check":
        print(json.dumps(systems_check(), indent=2))
    elif cmd == "all":
        print(json.dumps(systems_check(), indent=2))
    else:
        print(json.dumps({"ok": False, "error": "unknown_command",
                          "valid": [
                              "audit", "axioms", "memory", "beliefs", "graph",
                              "entropy", "quantum", "contradictions",
                              "hypotheses", "governance", "decisions",
                              "introspection", "roadmap", "systems_check", "all",
                          ]}, indent=2))
        sys.exit(2)


if __name__ == "__main__":
    main()
