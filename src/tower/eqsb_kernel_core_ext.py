"""
QSB Tower V1.5 — EQSB Kernel Core Extensions (Major Deep Phase)
Phase: EQSB_KERNEL_MAJOR_DEEP_SYMBOLIC_QUANTUM_CORE_V1

Shared utilities and central orchestrator for the deep EQSB Kernel
upgrade. This module does NOT replace src/tower/eqsb_cognition.py — it
extends it with:

  * an explicit Kernel architecture layer registry
  * a deep audit registry (separate from the V1 deep_kernel_audit)
  * a Guardian state and Guardian verdict envelope
  * a cadence/heartbeat state
  * a continuity_state registry (kernel-side mirror of the rebased
    continuity state)
  * a symbol registry and richer symbolic graph metadata
  * a replay/audit ledger
  * a kernel self-audit verdict
  * a central `build_all_eqsb_layers()` orchestrator used by the
    systems-check scripts

Hard contracts:
  * No external HTTP calls. No model calls. No installs.
  * Every payload stamps active_local_only=true, advisory_only=true,
    execution_allowed=false, plus the full lock matrix.
  * Reads existing registries; writes only the listed EQSB JSON/logs.
"""

from datetime import datetime, timezone
from pathlib import Path
import hashlib
import json
import os
import sys

ROOT = Path("/vaults/nvme0/qsb_tower_v1")
REG = ROOT / "data/registries"
LOGS = ROOT / "data/logs"

EQSB_MAJOR_SCHEMA_VERSION = "eqsb_major_v1.0"

# ── Major-phase registry paths ──────────────────────────────────────────
P_ARCH_LAYERS         = REG / "eqsb_kernel_architecture_layers.json"
P_MAJOR_AUDIT         = REG / "eqsb_kernel_major_audit.json"
P_EXISTING_CAPS       = REG / "eqsb_kernel_existing_capabilities.json"
P_MISSING_CAPS        = REG / "eqsb_kernel_missing_capabilities.json"
P_UPGRADE_PLAN        = REG / "eqsb_kernel_upgrade_plan.json"
P_GUARDIAN_STATE      = REG / "eqsb_guardian_state.json"
P_CADENCE_STATE       = REG / "eqsb_cadence_state.json"
P_CONTINUITY_STATE    = REG / "eqsb_continuity_state.json"
P_SYMBOL_REGISTRY     = REG / "eqsb_symbol_registry.json"
P_SYMBOLIC_STATE      = REG / "eqsb_symbolic_state.json"
P_REPLAY_LEDGER       = REG / "eqsb_replay_audit_ledger.json"
P_SELF_AUDIT          = REG / "eqsb_kernel_self_audit.json"
P_MAJOR_INTROSPECTION = REG / "eqsb_kernel_introspection_latest.json"

# Major-phase logs
L_MAJOR_AUDIT  = LOGS / "eqsb_kernel_major_audit.jsonl"
L_KERNEL_EVENTS = LOGS / "eqsb_kernel_events.jsonl"


# ── Time / IO helpers ──────────────────────────────────────────────────

def now_iso():
    return datetime.now(timezone.utc).isoformat()


def safety_envelope(extra=None):
    """Stamp every payload with the locked-false execution matrix."""
    env = {
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
        "model_inference_enabled": False,
        "autonomous_workers_enabled": False,
        "maintenance_auto_repair_enabled": False,
        "web_access_autonomous_enabled": False,
    }
    if extra:
        env.update(extra)
    return env


def load_json(path, fallback=None):
    try:
        return json.loads(Path(path).read_text(encoding="utf-8"))
    except Exception:
        return fallback if fallback is not None else {}


def write_json(path, payload):
    p = Path(path)
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(json.dumps(payload, indent=2, default=str), encoding="utf-8")


def append_event(record, log_path=L_KERNEL_EVENTS):
    log_path.parent.mkdir(parents=True, exist_ok=True)
    record = dict(record)
    record.setdefault("ts", now_iso())
    record.setdefault("execution_allowed", False)
    record.setdefault("advisory_only", True)
    with log_path.open("a", encoding="utf-8") as f:
        f.write(json.dumps(record, default=str) + "\n")


def stable_hash(payload):
    """Return a short, stable hex hash for a JSON-encodable payload."""
    blob = json.dumps(payload, sort_keys=True, default=str).encode("utf-8")
    return hashlib.sha256(blob).hexdigest()[:16]


# ── Kernel architecture layer registry ─────────────────────────────────

ARCHITECTURE_LAYERS = [
    {
        "level": 0,
        "name": "Kernel Safety Envelope",
        "responsibilities": [
            "classify requests",
            "permit read-only diagnostics",
            "prevent unsafe transitions",
            "verify kernel outputs against axioms",
            "detect contradictions",
            "detect identity drift",
            "refuse unverified quantum claims",
            "refuse unsupported high-confidence beliefs",
        ],
        "outputs": [
            "safety_state", "request_classification",
            "allowed_kernel_operation", "blocked_reason",
            "advisory_only", "guardian_verdict",
        ],
        "registry": "eqsb_guardian_state.json",
        "module": "src/tower/eqsb_guardian.py",
    },
    {
        "level": 1,
        "name": "Identity / Constitution",
        "responsibilities": [
            "kernel name, role, mode",
            "active source",
            "constitution version",
            "model-separation statement",
            "registry-truth statement",
            "quantum-truth statement",
        ],
        "registry": "eqsb_identity_constitution.json",
        "module": "src/tower/eqsb_axioms.py",
    },
    {
        "level": 2,
        "name": "Axiom System",
        "responsibilities": [
            "identity axioms",
            "guardian axioms",
            "memory axioms",
            "symbolic reasoning axioms",
            "model-governance axioms",
            "entropy axioms",
            "quantum-symbolic axioms",
            "continuity axioms",
            "truth-validation axioms",
            "self-audit axioms",
        ],
        "registry": "eqsb_axiom_registry.json",
        "module": "src/tower/eqsb_axioms.py",
    },
    {
        "level": 3,
        "name": "Cadence / Heartbeat",
        "responsibilities": [
            "read state",
            "validate axioms",
            "update memory",
            "update beliefs",
            "compute entropy",
            "detect contradictions",
            "generate hypotheses",
            "compute quantum-symbolic signal",
            "select advisory hypothesis",
            "update introspection",
            "write replay ledger",
        ],
        "registry": "eqsb_cadence_state.json",
        "module": "src/tower/eqsb_cadence.py",
    },
    {
        "level": 4,
        "name": "Memory / Continuity System",
        "responsibilities": [
            "short_window_state",
            "long_window_state",
            "pinned_beliefs",
            "boot_posture",
            "continuity_hash",
            "drift_alerts",
            "stale_memory_flags",
        ],
        "registries": [
            "eqsb_memory_policy.json",
            "eqsb_continuity_state.json",
        ],
        "module": "src/tower/eqsb_memory.py",
    },
    {
        "level": 5,
        "name": "Belief Lifecycle Engine",
        "responsibilities": [
            "PROVISIONAL/ACTIVE/STRENGTHENED/AGING/DEPRECATED/RETIRED/QUARANTINED",
            "evidence and counter-evidence tracking",
            "linked axioms / symbols / modules",
            "next_review scheduling",
        ],
        "registry": "eqsb_belief_lifecycle.json",
        "module": "src/tower/eqsb_beliefs.py",
    },
    {
        "level": 6,
        "name": "Symbol Registry",
        "responsibilities": [
            "all named symbols (kernel, guardian, axiom, belief, memory,"
            " entropy_signal, quantum_signal, contradiction, hypothesis,"
            " model_lane, registry, floor, worker, route, lock, event,"
            " audit_record)",
        ],
        "registries": [
            "eqsb_symbol_registry.json",
            "eqsb_symbolic_state.json",
        ],
        "module": "src/tower/eqsb_symbols.py",
    },
    {
        "level": 7,
        "name": "Symbolic Graph",
        "responsibilities": [
            "kernel/guardian/axiom/belief/symbol nodes",
            "edges: kernel_owns_axiom, axiom_supports_belief,"
            " contradiction_challenges_belief, hypothesis_explains_signal,"
            " collapse_selects_hypothesis, quantum_signal_weights_hypothesis,"
            " continuity_hash_links_state",
        ],
        "registry": "eqsb_symbolic_graph.json",
        "module": "src/tower/eqsb_symbolic_graph.py",
    },
    {
        "level": 8,
        "name": "Entropy / Drift / Stability Engine",
        "responsibilities": [
            "entropy_score / stability_score / drift_score",
            "confidence_score / contradiction_score / urgency_score",
            "registry churn / continuity drift / belief change pressure",
            "recommended_review_targets",
        ],
        "registry": "eqsb_entropy_state.json",
        "module": "src/tower/eqsb_entropy.py",
    },
    {
        "level": 9,
        "name": "Quantum-Symbolic Signal Engine",
        "responsibilities": [
            "mode=simulated_quantum_entropy (no real hardware)",
            "symbolic superposition / measurement / collapse / decoherence",
            "advisory_only, no execution link",
        ],
        "registries": [
            "eqsb_quantum_signal_state.json",
            "eqsb_quantum_roadmap.json",
        ],
        "module": "src/tower/eqsb_quantum_signal.py",
    },
    {
        "level": 10,
        "name": "Hypothesis Engine",
        "responsibilities": [
            "competing hypotheses",
            "evidence / counter-evidence",
            "selection / collapse with reason",
            "advisory_only",
        ],
        "registry": "eqsb_hypothesis_state.json",
        "module": "src/tower/eqsb_hypotheses.py",
    },
    {
        "level": 11,
        "name": "Contradiction Detector",
        "responsibilities": [
            "axiom violation",
            "belief vs registry truth",
            "model vs registry truth",
            "kernel identity drift",
            "missing continuity",
            "unsupported high-confidence belief",
            "quantum claims without proof",
        ],
        "registry": "eqsb_contradiction_report.json",
        "module": "src/tower/eqsb_contradictions.py",
    },
    {
        "level": 12,
        "name": "Model Lane Governance",
        "responsibilities": [
            "local_ollama / local_llama / airllm_advisory lanes",
            "advisory_only enforcement",
            "registry-truth outranks paraphrase",
            "no quantum-hardware claims without proof",
        ],
        "registry": "eqsb_model_lane_governance.json",
        "module": "src/tower/eqsb_model_governance.py",
    },
    {
        "level": 13,
        "name": "Guardian Kernel Layer",
        "responsibilities": [
            "intent validation",
            "model output validation",
            "axiom compliance",
            "belief transition validation",
            "quantum claim validation",
            "continuity validation",
            "entropy alerting",
        ],
        "registry": "eqsb_guardian_state.json",
        "module": "src/tower/eqsb_guardian.py",
    },
    {
        "level": 14,
        "name": "Kernel Introspection Engine",
        "responsibilities": [
            "structured registry-backed answers for every kernel chat topic",
            "identity, constitution, axioms, Guardian, cadence, memory,"
            " continuity, beliefs, symbols, graph, entropy, quantum, "
            " hypotheses, contradictions, model_lanes, replay ledger",
        ],
        "registry": "eqsb_kernel_introspection_latest.json",
        "module": "src/tower/eqsb_introspection.py",
    },
    {
        "level": 15,
        "name": "Replay / Audit Ledger",
        "responsibilities": [
            "record kernel questions, cadence ticks, memory updates,"
            " belief / symbol / entropy / quantum / hypothesis updates,"
            " contradiction detection, Guardian verdicts, model governance"
            " decisions, repair suggestions",
        ],
        "registry": "eqsb_replay_audit_ledger.json",
        "log": "data/logs/eqsb_kernel_events.jsonl",
        "module": "src/tower/eqsb_replay_ledger.py",
    },
]


def build_architecture_layers():
    payload = {
        "schema_version": EQSB_MAJOR_SCHEMA_VERSION,
        "generated_ts": now_iso(),
        "kind": "eqsb_kernel_architecture_layers",
        "phase": "EQSB_KERNEL_MAJOR_DEEP_SYMBOLIC_QUANTUM_CORE_V1",
        "layer_count": len(ARCHITECTURE_LAYERS),
        "layers": ARCHITECTURE_LAYERS,
        "kernel_is_a_model": False,
        "kernel_is_persistent_symbolic_brain": True,
        "registry_truth_outranks_model_paraphrase": True,
    }
    payload.update(safety_envelope())
    write_json(P_ARCH_LAYERS, payload)
    append_event({"event": "build_architecture_layers",
                  "layer_count": len(ARCHITECTURE_LAYERS)})
    return payload


# ── Major-phase audit ──────────────────────────────────────────────────

def _registry_present(name):
    return (REG / name).exists()


def major_audit():
    """Audit the existing kernel against the EQSB major phase requirements.

    Reads only. Produces:
      - eqsb_kernel_major_audit.json
      - eqsb_kernel_existing_capabilities.json
      - eqsb_kernel_missing_capabilities.json
      - eqsb_kernel_upgrade_plan.json
      - data/logs/eqsb_kernel_major_audit.jsonl
    """
    rebased_kernel = ROOT / "penthouse/kernel_installation_socket/rebased_kernel"
    rebased_state  = rebased_kernel / "state"

    existing = {
        "rebased_kernel_present": rebased_kernel.exists(),
        "rebased_kernel_core_present": (rebased_kernel / "kernel/kernel_core.py").exists(),
        "identity_core_present":       (rebased_kernel / "kernel/identity_core.py").exists(),
        "axiom_core_present":          (rebased_kernel / "kernel/axiom_core.py").exists(),
        "symbolic_core_present":       (rebased_kernel / "kernel/symbolic_core.py").exists(),
        "belief_core_present":         (rebased_kernel / "kernel/belief_core.py").exists(),
        "continuity_core_present":     (rebased_kernel / "kernel/continuity_core.py").exists(),
        "beliefs_sqlite_present":      (rebased_state / "beliefs.sqlite").exists(),
        "symbolic_sqlite_present":     (rebased_state / "symbolic.sqlite").exists(),
        "continuity_state_present":    (rebased_state / "continuity_state.json").exists(),
        "identity_state_present":      (rebased_state / "identity.json").exists(),
        "eqsb_cognition_module":       (ROOT / "src/tower/eqsb_cognition.py").exists(),
        "kernel_dialogue_adapter":     (ROOT / "src/tower/kernel_dialogue_adapter.py").exists(),
        "dormant_kernel_adapter":      (ROOT / "src/tower/dormant_kernel_adapter.py").exists(),

        "registry_identity_constitution":  _registry_present("eqsb_identity_constitution.json"),
        "registry_axiom_registry":         _registry_present("eqsb_axiom_registry.json"),
        "registry_memory_policy":          _registry_present("eqsb_memory_policy.json"),
        "registry_belief_lifecycle":       _registry_present("eqsb_belief_lifecycle.json"),
        "registry_symbolic_graph":         _registry_present("eqsb_symbolic_graph.json"),
        "registry_entropy_state":          _registry_present("eqsb_entropy_state.json"),
        "registry_quantum_signal_state":   _registry_present("eqsb_quantum_signal_state.json"),
        "registry_hypothesis_state":       _registry_present("eqsb_hypothesis_state.json"),
        "registry_contradiction_report":   _registry_present("eqsb_contradiction_report.json"),
        "registry_model_lane_governance":  _registry_present("eqsb_model_lane_governance.json"),
        "registry_introspection_latest":   _registry_present("eqsb_kernel_introspection_latest.json"),
    }

    # What the major phase explicitly REQUIRES that didn't exist as deep
    # standalone modules / registries before.
    expected_after_major_phase = {
        "kernel_architecture_layers":    P_ARCH_LAYERS.name,
        "kernel_major_audit":            P_MAJOR_AUDIT.name,
        "kernel_existing_capabilities":  P_EXISTING_CAPS.name,
        "kernel_missing_capabilities":   P_MISSING_CAPS.name,
        "kernel_upgrade_plan":           P_UPGRADE_PLAN.name,
        "guardian_state":                P_GUARDIAN_STATE.name,
        "cadence_state":                 P_CADENCE_STATE.name,
        "continuity_state":              P_CONTINUITY_STATE.name,
        "symbol_registry":               P_SYMBOL_REGISTRY.name,
        "symbolic_state":                P_SYMBOLIC_STATE.name,
        "replay_audit_ledger":           P_REPLAY_LEDGER.name,
        "kernel_self_audit":             P_SELF_AUDIT.name,
    }
    missing = {k: (not _registry_present(v))
               for k, v in expected_after_major_phase.items()}

    # Concrete audit answers to the 20 audit questions.
    cont = load_json(rebased_state / "continuity_state.json", {})
    audit_answers = {
        "1_current_kernel_class":            "QSBKernelCore (rebased_kernel.kernel.kernel_core)",
        "2_active_kernel_source":            "penthouse/kernel_installation_socket/rebased_kernel (active_local_only)",
        "3_status_returns":                  "{kernel, continuity, axioms, symbolic_core, beliefs}",
        "4_analyze_returns":                 "{axiom_check, symbolic_result}",
        "5_kernel_chat_structured_truth":    "data/registries/eqsb_*.json + rebased_kernel.status()",
        "6_kernel_chat_model_paraphrase":    "[Local-model paraphrase — advisory only] block, appended after kernel block",
        "7_symbolic_logic_existing":         "symbolic_core.SymbolicLogicCore + symbolic.sqlite + eqsb_cognition.build_symbolic_graph",
        "8_axioms_existing":                 "axiom_core.AXIOMS (10) + eqsb_axiom_registry.json (10)",
        "9_guardian_logic_existing":         "Partial: kernel_dialogue_adapter.safety_check + LOCKED_FALSE flags. Missing: structured Guardian envelope/verdict registry.",
        "10_memory_continuity_existing":     "continuity_core.boot_check + beliefs.sqlite + eqsb_memory_policy.json. Missing: explicit eqsb_continuity_state mirror.",
        "11_belief_lifecycle_existing":      "belief_core + eqsb_belief_lifecycle.json (PROVISIONAL/ACTIVE/STRENGTHENED/AGING/DEPRECATED/RETIRED/QUARANTINED)",
        "12_entropy_logic_existing":         "eqsb_cognition.compute_entropy + eqsb_entropy_state.json",
        "13_quantum_logic_existing":         "eqsb_cognition.compute_quantum_signal (mode=simulated_quantum_entropy). No real hardware.",
        "14_contradiction_detection_existing":"eqsb_cognition.detect_contradictions + eqsb_contradiction_report.json",
        "15_hypothesis_generation_existing": "eqsb_cognition.build_hypotheses + eqsb_hypothesis_state.json",
        "16_model_lane_governance_existing": "eqsb_cognition.build_model_lane_governance + eqsb_model_lane_governance.json",
        "17_replay_audit_ledger_existing":   "data/logs/eqsb_kernel_events.jsonl + kernel_dialogue.jsonl. Missing: structured replay registry.",
        "18_missing_for_true_eqsb":          [k for k, v in missing.items() if v],
        "19_safe_now":                       [
            "kernel_architecture_layers registry",
            "guardian_state envelope",
            "cadence_state heartbeat",
            "continuity_state mirror",
            "symbol_registry + symbolic_state",
            "replay_audit_ledger summary",
            "kernel_self_audit verdict",
        ],
        "20_deferred":                       [
            "Qiskit installation",
            "IBM Quantum credentials",
            "real quantum hardware connection",
            "execution-gate unlocks (always deferred)",
        ],
        "continuity_state_history_count":    cont.get("history_count"),
        "continuity_state_status":           cont.get("status"),
    }

    major = {
        "schema_version": EQSB_MAJOR_SCHEMA_VERSION,
        "generated_ts": now_iso(),
        "kind": "eqsb_kernel_major_audit",
        "phase": "EQSB_KERNEL_MAJOR_DEEP_SYMBOLIC_QUANTUM_CORE_V1",
        "audit_answers": audit_answers,
        "existing": existing,
        "missing": missing,
        "missing_count": sum(1 for v in missing.values() if v),
    }
    major.update(safety_envelope())
    write_json(P_MAJOR_AUDIT, major)

    write_json(P_EXISTING_CAPS, {
        "schema_version": EQSB_MAJOR_SCHEMA_VERSION,
        "generated_ts": now_iso(),
        "kind": "eqsb_kernel_existing_capabilities",
        **safety_envelope(),
        "capabilities_present": [k for k, v in existing.items() if v is True],
        "capabilities_absent": [k for k, v in existing.items() if v is False],
    })

    write_json(P_MISSING_CAPS, {
        "schema_version": EQSB_MAJOR_SCHEMA_VERSION,
        "generated_ts": now_iso(),
        "kind": "eqsb_kernel_missing_capabilities",
        **safety_envelope(),
        "missing": missing,
        "what_to_build_next": [
            k for k, v in missing.items() if v
        ],
    })

    write_json(P_UPGRADE_PLAN, {
        "schema_version": EQSB_MAJOR_SCHEMA_VERSION,
        "generated_ts": now_iso(),
        "kind": "eqsb_kernel_upgrade_plan",
        **safety_envelope(),
        "ordered_steps": [
            "build_architecture_layers",
            "build_axioms_and_constitution",
            "build_guardian_state",
            "build_memory_and_continuity_state",
            "update_beliefs_lifecycle",
            "build_symbol_registry",
            "build_symbolic_graph",
            "compute_entropy",
            "compute_quantum_signal (simulated only)",
            "generate_hypotheses",
            "detect_contradictions",
            "validate_model_lanes",
            "cadence_tick",
            "build_introspection",
            "build_replay_ledger",
            "kernel_self_audit",
        ],
        "do_not_do": [
            "install Qiskit or contact IBM Quantum",
            "promote local kernel to executing logic",
            "enable any execution gate",
            "unlock OpenClaw execution",
            "enable live trading or autonomous dispatch",
        ],
    })

    append_event({"event": "major_audit",
                  "missing_count": major["missing_count"]},
                 log_path=L_MAJOR_AUDIT)
    append_event({"event": "major_audit",
                  "missing_count": major["missing_count"]})
    return major


# ── Central orchestrator ───────────────────────────────────────────────

def build_kernel_self_audit():
    """Write a compact kernel self-audit verdict registry that summarises
    the major-phase build outcome. Reads the other major-phase registries
    and writes eqsb_kernel_self_audit.json."""
    audit = load_json(P_MAJOR_AUDIT, {})
    guardian = load_json(P_GUARDIAN_STATE, {})
    entropy = load_json(REG / "eqsb_entropy_state.json", {})
    contradictions = load_json(REG / "eqsb_contradiction_report.json", {})
    cont = load_json(P_CONTINUITY_STATE, {})
    introspection = load_json(P_MAJOR_INTROSPECTION, {})

    verdict = "kernel_healthy"
    reasons = []
    if guardian.get("safety_state") in ("BLOCKED",):
        verdict = "kernel_blocked"
        reasons.append("guardian.safety_state=BLOCKED")
    elif guardian.get("safety_state") in ("DEGRADED", "DRIFTING"):
        verdict = "kernel_advisory_review"
        reasons.append("guardian.safety_state=" + str(guardian.get("safety_state")))
    if (contradictions.get("by_severity") or {}).get("critical"):
        verdict = "kernel_blocked"
        reasons.append("critical_contradictions_present")
    if (entropy.get("urgency_score") or 0) >= 80:
        verdict = "kernel_advisory_review"
        reasons.append("high_urgency_score")
    if not reasons:
        reasons.append("no contradictions, no Guardian blocks, entropy nominal")

    payload = {
        "schema_version": EQSB_MAJOR_SCHEMA_VERSION,
        "kind": "eqsb_kernel_self_audit",
        "generated_ts": now_iso(),
        "verdict": verdict,
        "verdict_reasons": reasons,
        "missing_registry_count": audit.get("missing_count"),
        "guardian_safety_state": guardian.get("safety_state"),
        "entropy_score": entropy.get("entropy_score"),
        "drift_score": entropy.get("drift_score"),
        "contradiction_count": contradictions.get("contradiction_count"),
        "continuity_boot_posture": cont.get("boot_posture"),
        "introspection_hash": introspection.get("introspection_hash"),
        "layer_count": len(ARCHITECTURE_LAYERS),
        "kernel_truth_note": (
            "EQSB self-audit is advisory only. Even a healthy verdict "
            "does not unlock execution gates — they remain locked at code "
            "level."
        ),
        "next_actions": [
            "review repair_suggestions in eqsb_replay_audit_ledger.json",
            "verify Guardian default verdict for read-only diagnostics",
            "watch quantum_signal.mode stays simulated_quantum_entropy",
        ],
    }
    payload.update(safety_envelope())
    payload["self_audit_hash"] = stable_hash({
        "verdict": verdict,
        "reasons": reasons,
        "entropy_score": payload["entropy_score"],
        "contradiction_count": payload["contradiction_count"],
    })
    write_json(P_SELF_AUDIT, payload)
    append_event({"event": "build_kernel_self_audit",
                  "verdict": verdict,
                  "reasons": reasons})
    return payload


def build_all_eqsb_layers():
    """Run every EQSB layer in dependency order and return a compact map of
    layer name → registry path. Each subsystem module owns its own writer.

    Safe to invoke from any script. Never executes external code, never
    flips execution gates, never installs anything.
    """
    out = {"ts": now_iso(), "phase": "EQSB_KERNEL_MAJOR_DEEP_SYMBOLIC_QUANTUM_CORE_V1",
           "results": {}}

    # Always run the V1 cognition's `build_all_layers` first so the V1
    # registries are present and current. The major-phase modules read
    # them.
    try:
        from tower.eqsb_cognition import build_all_layers as _v1_build
        _v1_build()
        out["results"]["v1_eqsb_cognition_build_all_layers"] = "ok"
    except Exception as exc:  # pragma: no cover - defensive
        out["results"]["v1_eqsb_cognition_build_all_layers"] = "error: " + str(exc)[:200]

    out["results"]["architecture_layers"] = str(build_architecture_layers().get("kind"))

    # Each major-phase module exposes a `build()` function that returns the
    # registry payload. Wired here in order; each call is a thin wrapper.
    from tower.eqsb_axioms import build as build_axioms
    out["results"]["axioms"] = build_axioms()["kind"]

    from tower.eqsb_memory import build as build_memory
    out["results"]["memory"] = build_memory()["kind"]

    from tower.eqsb_beliefs import build as build_beliefs
    out["results"]["beliefs"] = build_beliefs()["kind"]

    from tower.eqsb_symbols import build as build_symbols
    out["results"]["symbols"] = build_symbols()["kind"]

    from tower.eqsb_symbolic_graph import build as build_graph
    out["results"]["symbolic_graph"] = build_graph()["kind"]

    from tower.eqsb_entropy import build as build_entropy
    out["results"]["entropy"] = build_entropy()["kind"]

    from tower.eqsb_quantum_signal import build as build_quantum
    out["results"]["quantum_signal"] = build_quantum()["kind"]

    from tower.eqsb_hypotheses import build as build_hypotheses
    out["results"]["hypotheses"] = build_hypotheses()["kind"]

    from tower.eqsb_contradictions import build as build_contradictions
    out["results"]["contradictions"] = build_contradictions()["kind"]

    from tower.eqsb_model_governance import build as build_governance
    out["results"]["model_governance"] = build_governance()["kind"]

    from tower.eqsb_guardian import build as build_guardian
    out["results"]["guardian"] = build_guardian()["kind"]

    from tower.eqsb_cadence import build as build_cadence
    out["results"]["cadence"] = build_cadence()["kind"]

    from tower.eqsb_replay_ledger import build as build_ledger
    out["results"]["replay_ledger"] = build_ledger()["kind"]

    from tower.eqsb_introspection import build as build_introspection
    out["results"]["introspection"] = build_introspection()["kind"]

    # Write kernel self-audit verdict first so the final audit sees it.
    out["results"]["kernel_self_audit"] = build_kernel_self_audit()["kind"]
    # Then re-run the major audit so missing_count reflects post-build state.
    major_audit()

    out.update(safety_envelope())
    return out


def main():
    cmd = (sys.argv[1] if len(sys.argv) > 1 else "all").lower()
    if cmd == "audit":
        print(json.dumps(major_audit(), indent=2))
    elif cmd == "architecture":
        print(json.dumps(build_architecture_layers(), indent=2))
    elif cmd == "all":
        major_audit()
        print(json.dumps(build_all_eqsb_layers(), indent=2))
    else:
        print(json.dumps({"ok": False, "error": "unknown_command",
                          "valid": ["audit", "architecture", "all"]},
                         indent=2))
        raise SystemExit(2)


if __name__ == "__main__":
    main()
