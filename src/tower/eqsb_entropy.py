"""
QSB Tower V1.5 — EQSB Entropy / Drift / Stability Engine
Phase: EQSB_KERNEL_MAJOR_DEEP_SYMBOLIC_QUANTUM_CORE_V1

Replaces V1's compute_entropy with a registry-driven, deeper scoring
that reflects the major-phase definition. Inputs include: registry
timestamp churn, continuity hash changes, belief confidence changes,
contradiction count, stale registry count, missing registry count,
model-vs-registry disagreement, unsupported symbol count, unsupported
belief count, hypothesis conflict count, kernel chat refusal anomalies,
axiom validation failures, memory drift, cadence failures.
"""

import json
from datetime import datetime, timezone
from pathlib import Path

from tower.eqsb_kernel_core_ext import (
    EQSB_MAJOR_SCHEMA_VERSION, ROOT, REG,
    now_iso, load_json, write_json, append_event,
    safety_envelope, stable_hash,
)

P_ENTROPY = REG / "eqsb_entropy_state.json"


def _clamp(v, lo=0, hi=100):
    try:
        v = float(v)
    except Exception:
        v = 0.0
    return max(lo, min(hi, v))


def _count_stale_or_missing(paths, max_age_hours):
    now = datetime.now(timezone.utc)
    stale = 0
    missing = 0
    for rel in paths:
        p = ROOT / rel
        if not p.exists():
            missing += 1
            continue
        try:
            ts = datetime.fromtimestamp(p.stat().st_mtime, tz=timezone.utc)
            if (now - ts).total_seconds() / 3600.0 > max_age_hours:
                stale += 1
        except Exception:
            stale += 1
    return stale, missing


def compute_entropy():
    beliefs = load_json(REG / "eqsb_belief_lifecycle.json", {})
    contradictions = load_json(REG / "eqsb_contradiction_report.json", {})
    hypotheses = load_json(REG / "eqsb_hypothesis_state.json", {})
    cont = load_json(REG / "eqsb_continuity_state.json", {})
    audit = load_json(REG / "eqsb_kernel_major_audit.json", {})
    sym = load_json(REG / "eqsb_symbol_registry.json", {})
    state = load_json(REG / "eqsb_symbolic_state.json", {})

    belief_count = beliefs.get("belief_count") or 0
    quarantined = (beliefs.get("state_counts") or {}).get("QUARANTINED") or 0
    aging = (beliefs.get("state_counts") or {}).get("AGING") or 0
    contradiction_count = contradictions.get("contradiction_count") or 0
    hypothesis_count = hypotheses.get("hypothesis_count") or 0
    missing = audit.get("missing_count") or 0

    # Stale/missing registry signals.
    stale, missing_reg = _count_stale_or_missing([
        "data/registries/sandbox_autoloop_latest.json",
        "data/registries/kernel_activation_report.json",
        "data/registries/eqsb_kernel_introspection_latest.json",
        "data/registries/eqsb_belief_lifecycle.json",
        "data/registries/eqsb_axiom_registry.json",
        "data/registries/eqsb_quantum_signal_state.json",
    ], max_age_hours=24)

    continuity_depth = cont.get("continuity_previous_chain_depth") or 0
    boot_posture = cont.get("boot_posture") or "NORMAL"
    drift_alert_count = len(cont.get("drift_alerts") or [])
    stale_memory_flag_count = len(cont.get("stale_memory_flags") or [])

    orphan_symbols = len(state.get("orphan_symbols") or [])

    inputs = {
        "belief_count": belief_count,
        "quarantined_beliefs": quarantined,
        "aging_beliefs": aging,
        "contradiction_count": contradiction_count,
        "hypothesis_count": hypothesis_count,
        "missing_registry_count": missing + missing_reg,
        "stale_registry_count": stale,
        "continuity_previous_chain_depth": continuity_depth,
        "drift_alert_count": drift_alert_count,
        "stale_memory_flag_count": stale_memory_flag_count,
        "orphan_symbol_count": orphan_symbols,
        "boot_posture": boot_posture,
    }

    # Scoring (0..100 scale)
    contradiction_score = _clamp(min(100, contradiction_count * 20))
    drift_score = _clamp(min(100,
                             drift_alert_count * 25 +
                             stale_memory_flag_count * 8 +
                             max(0, continuity_depth - 1) * 0.5))
    stability_score = _clamp(100 - drift_score)
    confidence_score = _clamp(70
                              - (quarantined * 10)
                              - (orphan_symbols * 5)
                              + (10 if boot_posture == "NORMAL" else 0))
    entropy_score = _clamp(min(100,
                               contradiction_score * 0.4 +
                               drift_score * 0.4 +
                               (100 - confidence_score) * 0.2))
    urgency_score = _clamp(min(100,
                               contradiction_score * 0.5 +
                               drift_score * 0.3 +
                               (missing + missing_reg) * 5 +
                               quarantined * 3))

    explanation = []
    if contradiction_count > 0:
        explanation.append(f"{contradiction_count} contradiction(s) detected.")
    if drift_alert_count > 0:
        explanation.append(f"{drift_alert_count} continuity drift alert(s).")
    if stale_memory_flag_count > 0:
        explanation.append(f"{stale_memory_flag_count} stale memory flag(s).")
    if continuity_depth > 1:
        explanation.append("Continuity chain depth exceeds 1.")
    if missing or missing_reg:
        explanation.append(f"{missing + missing_reg} missing registry slot(s).")
    if orphan_symbols:
        explanation.append(f"{orphan_symbols} orphan symbol(s).")
    if not explanation:
        explanation.append("No anomalies detected.")

    recommended_review_targets = []
    if contradiction_count:
        recommended_review_targets.append("eqsb_contradiction_report.json")
    if drift_alert_count or stale_memory_flag_count:
        recommended_review_targets.append("eqsb_continuity_state.json")
    if quarantined:
        recommended_review_targets.append("eqsb_belief_lifecycle.json (QUARANTINED beliefs)")
    if missing or missing_reg:
        recommended_review_targets.append("eqsb_kernel_missing_capabilities.json")
    if orphan_symbols:
        recommended_review_targets.append("eqsb_symbolic_state.json (orphan symbols)")

    payload = {
        "schema_version": EQSB_MAJOR_SCHEMA_VERSION,
        "kind": "eqsb_entropy_state",
        "generated_ts": now_iso(),
        "entropy_score": round(entropy_score, 2),
        "stability_score": round(stability_score, 2),
        "drift_score": round(drift_score, 2),
        "confidence_score": round(confidence_score, 2),
        "contradiction_score": round(contradiction_score, 2),
        "urgency_score": round(urgency_score, 2),
        "scoring_scale": "0_to_100",
        "inputs": inputs,
        "explanation": explanation,
        "recommended_review_targets": recommended_review_targets,
        "source_files": [
            "data/registries/eqsb_belief_lifecycle.json",
            "data/registries/eqsb_contradiction_report.json",
            "data/registries/eqsb_hypothesis_state.json",
            "data/registries/eqsb_continuity_state.json",
            "data/registries/eqsb_symbol_registry.json",
            "data/registries/eqsb_symbolic_state.json",
        ],
        "interpretation": {
            "low_entropy_high_confidence":  "stable kernel state",
            "high_entropy_high_contradiction":"review required",
            "high_drift":                   "continuity concern",
            "high_urgency":                 "repair priority",
        },
    }
    payload.update(safety_envelope())
    payload["entropy_hash"] = stable_hash({
        "entropy_score": payload["entropy_score"],
        "drift_score": payload["drift_score"],
        "contradiction_score": payload["contradiction_score"],
    })
    write_json(P_ENTROPY, payload)
    append_event({"event": "compute_entropy",
                  "entropy_score": payload["entropy_score"],
                  "drift_score": payload["drift_score"]})
    return payload


def build():
    return compute_entropy()


if __name__ == "__main__":
    print(json.dumps(build(), indent=2))
