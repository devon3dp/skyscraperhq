"""
QSB Tower V1.5 — EQSB Memory / Continuity Mirror
Phase: EQSB_KERNEL_MAJOR_DEEP_SYMBOLIC_QUANTUM_CORE_V1

This module:
  * (re)builds the EQSB memory policy in the deeper schema described
    in the major phase
  * builds a kernel-side mirror of the rebased continuity_state in
    `eqsb_continuity_state.json`, including boot_posture, drift_alerts,
    and stale_memory_flags
  * never edits the rebased continuity file
"""

import json
from datetime import datetime, timezone
from pathlib import Path

from tower.eqsb_kernel_core_ext import (
    EQSB_MAJOR_SCHEMA_VERSION, ROOT, REG, LOGS,
    P_CONTINUITY_STATE,
    now_iso, load_json, write_json, append_event,
    safety_envelope, stable_hash,
)

P_MEMORY_POLICY = REG / "eqsb_memory_policy.json"

REBASED = ROOT / "penthouse/kernel_installation_socket/rebased_kernel"
REBASED_CONT_FILE = REBASED / "state/continuity_state.json"
REBASED_IDENT_FILE = REBASED / "state/identity.json"

PINNED_BELIEFS = [
    "EQSB is the persistent symbolic Kernel, not a model.",
    "Registry-backed structured state outranks model paraphrase.",
    "Execution gates are separate from reasoning and remain locked.",
    "Quantum-symbolic signal is simulated/advisory unless verified.",
    "Models are replaceable advisory lanes; not the kernel.",
    "Beliefs must remain evidence-linked.",
    "Contradictions must be surfaced, not hidden.",
]


def _continuity_chain_depth(cont):
    depth = 0
    cur = cont
    while isinstance(cur, dict) and cur.get("previous") is not None:
        depth += 1
        cur = cur.get("previous")
    return depth


def _stale_memory_flags():
    """Walk a small set of expected logs/registries; raise stale flags
    when the most recent timestamp is older than ~12 hours."""
    flags = []
    expected = [
        ("data/logs/qsb_standalone_system_audit.jsonl", 12),
        ("data/logs/eqsb_kernel_events.jsonl",           24),
        ("data/registries/sandbox_autoloop_latest.json", 12),
        ("data/registries/kernel_activation_report.json",24*7),
    ]
    now = datetime.now(timezone.utc)
    for rel, hours in expected:
        p = ROOT / rel
        if not p.exists():
            flags.append({"path": rel, "reason": "missing", "max_age_hours": hours})
            continue
        try:
            ts = datetime.fromtimestamp(p.stat().st_mtime, tz=timezone.utc)
            age_h = (now - ts).total_seconds() / 3600.0
            if age_h > hours:
                flags.append({"path": rel, "reason": "stale",
                              "age_hours": round(age_h, 1),
                              "max_age_hours": hours})
        except Exception:
            flags.append({"path": rel, "reason": "stat_failed", "max_age_hours": hours})
    return flags


def build_memory_policy():
    cont = load_json(REBASED_CONT_FILE, {})
    cont_path = REBASED_CONT_FILE
    cont_depth = _continuity_chain_depth(cont)

    policy = {
        "schema_version": EQSB_MAJOR_SCHEMA_VERSION,
        "kind": "eqsb_memory_policy",
        "generated_ts": now_iso(),
        "short_window": {
            "scope": "recent_state_snapshots",
            "max_records": 200,
            "ttl_hours": 24,
            "source_logs": [
                "data/logs/kernel_dialogue.jsonl",
                "data/logs/eqsb_kernel_events.jsonl",
                "data/logs/eqsb_kernel_major_audit.jsonl",
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
            "continuity_state_size_bytes": (cont_path.stat().st_size
                                            if cont_path.exists() else 0),
            "continuity_previous_chain_depth": cont_depth,
            "drift_check": "ContinuityCore._summarize_previous + hashes",
            "history_count": cont.get("history_count"),
        },
        "pinned_beliefs": PINNED_BELIEFS,
        "boot_posture_options": [
            "NORMAL", "CONSERVATIVE", "DRIFT_ALERT", "RECOVERY_REQUIRED"
        ],
        "stale_state_detection": {
            "method": "registry mtime + audit jsonl tail comparison",
            "alert_when_no_audit_in_hours": 12,
        },
        "evidence_based_update_rule": (
            "Beliefs may only change state when a measurable registry "
            "signal supports the transition. Model paraphrases are not "
            "evidence."
        ),
        "memory_recomputation_after_restart": (
            "ContinuityCore.boot_check runs every kernel instantiation "
            "and records hash drift across identity/symbolic_core/penthouse "
            "files."
        ),
        "next_review_targets": [
            "eqsb_continuity_state.json (kernel-side mirror)",
            "eqsb_belief_lifecycle.json next_review_at fields",
        ],
        "source_files": [
            "penthouse/kernel_installation_socket/rebased_kernel/kernel/continuity_core.py",
            "penthouse/kernel_installation_socket/rebased_kernel/state/continuity_state.json",
        ],
    }
    policy.update(safety_envelope())
    write_json(P_MEMORY_POLICY, policy)
    append_event({"event": "build_memory_policy",
                  "continuity_depth": cont_depth})
    return policy


def build_continuity_state():
    cont = load_json(REBASED_CONT_FILE, {})
    ident = load_json(REBASED_IDENT_FILE, {})

    drift_flags = []
    if cont.get("status") not in ("CONTINUITY_CONFIRMED", "FIRST_KERNEL_BOOT", None):
        drift_flags.append("rebased_continuity_status=" + str(cont.get("status")))
    if cont.get("drift"):
        drift_flags.append("rebased_drift_fields=" + ",".join(cont.get("drift") or []))

    stale_flags = _stale_memory_flags()

    if drift_flags and stale_flags:
        posture = "DRIFT_ALERT"
    elif drift_flags:
        posture = "CONSERVATIVE"
    elif stale_flags:
        posture = "CONSERVATIVE"
    else:
        posture = "NORMAL"

    continuity_state = {
        "schema_version": EQSB_MAJOR_SCHEMA_VERSION,
        "kind": "eqsb_continuity_state",
        "generated_ts": now_iso(),
        "mirrored_from": "penthouse/kernel_installation_socket/rebased_kernel/state/continuity_state.json",
        "boot_posture": posture,
        "boot_status_upstream": cont.get("status"),
        "history_count": cont.get("history_count"),
        "continuity_state_size_bytes": (REBASED_CONT_FILE.stat().st_size
                                        if REBASED_CONT_FILE.exists() else 0),
        "continuity_previous_chain_depth": _continuity_chain_depth(cont),
        "identity_hash_upstream": cont.get("identity_hash"),
        "symbolic_hash_upstream": cont.get("symbolic_hash"),
        "penthouse_hash_upstream": cont.get("penthouse_hash"),
        "constitution_hash_upstream": cont.get("constitution_hash"),
        "memory_db_exists": bool(cont.get("memory_db_exists")),
        "lift_db_exists": bool(cont.get("lift_db_exists")),
        "drift_alerts": drift_flags,
        "stale_memory_flags": stale_flags,
        "missing_memory_sources": [f["path"] for f in stale_flags
                                    if f.get("reason") == "missing"],
        "memory_sources": [
            "penthouse/kernel_installation_socket/rebased_kernel/state/beliefs.sqlite",
            "penthouse/kernel_installation_socket/rebased_kernel/state/symbolic.sqlite",
            "penthouse/kernel_installation_socket/rebased_kernel/state/continuity_state.json",
            "data/registries/eqsb_*.json",
        ],
        "identity_upstream": {
            "name": ident.get("name"),
            "full_name": ident.get("full_name"),
            "version": ident.get("version"),
            "role": ident.get("role"),
        },
        "pinned_beliefs": PINNED_BELIEFS,
        "next_review_targets": [
            "eqsb_belief_lifecycle.json next_review_at",
            "eqsb_continuity_state stale_memory_flags",
        ],
    }
    continuity_state.update(safety_envelope())
    continuity_state["continuity_hash"] = stable_hash({
        "identity_hash": continuity_state["identity_hash_upstream"],
        "boot_posture": continuity_state["boot_posture"],
        "history_count": continuity_state["history_count"],
        "drift_alerts": continuity_state["drift_alerts"],
    })
    write_json(P_CONTINUITY_STATE, continuity_state)
    append_event({"event": "build_continuity_state",
                  "boot_posture": posture,
                  "drift_alert_count": len(drift_flags),
                  "stale_flag_count": len(stale_flags)})
    return continuity_state


def build():
    build_memory_policy()
    return build_continuity_state()


if __name__ == "__main__":
    print(json.dumps(build(), indent=2))
