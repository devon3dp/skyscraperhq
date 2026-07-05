"""
QSB Tower V1.5 — EQSB Replay / Audit Ledger
Phase: EQSB_KERNEL_MAJOR_DEEP_SYMBOLIC_QUANTUM_CORE_V1

Builds a compact, registry-form summary of the rolling event log in
data/logs/eqsb_kernel_events.jsonl plus
data/logs/eqsb_kernel_major_audit.jsonl. The detail lives in the
JSONL; the ledger is a query-friendly snapshot.
"""

import json
from datetime import datetime, timezone
from pathlib import Path

from tower.eqsb_kernel_core_ext import (
    EQSB_MAJOR_SCHEMA_VERSION, ROOT, REG, LOGS,
    P_REPLAY_LEDGER,
    L_KERNEL_EVENTS, L_MAJOR_AUDIT,
    now_iso, load_json, write_json, append_event,
    safety_envelope, stable_hash,
)


def _tail(path, limit=200):
    if not path.exists():
        return []
    out = []
    try:
        with path.open("r", encoding="utf-8") as f:
            for line in f:
                line = line.strip()
                if not line:
                    continue
                try:
                    out.append(json.loads(line))
                except Exception:
                    pass
    except Exception:
        return []
    return out[-limit:]


EVENT_KINDS = [
    "kernel question",
    "registry snapshot reference",
    "axiom validation",
    "cadence tick",
    "memory update",
    "belief update",
    "symbol update",
    "entropy update",
    "quantum signal update",
    "hypothesis update",
    "contradiction detection",
    "guardian verdict",
    "model governance decision",
    "introspection build",
    "repair suggestion",
]


def build_replay_ledger():
    events = _tail(L_KERNEL_EVENTS, limit=400)
    audit_events = _tail(L_MAJOR_AUDIT, limit=120)

    by_event = {}
    for e in events:
        ev = str(e.get("event") or "unknown")
        by_event[ev] = by_event.get(ev, 0) + 1

    last_per_event = {}
    for e in events:
        ev = str(e.get("event") or "unknown")
        ts = e.get("ts")
        prev = last_per_event.get(ev)
        if ts and (not prev or ts > prev.get("ts", "")):
            last_per_event[ev] = {"ts": ts, "summary": {k: v for k, v in e.items()
                                                          if k in ("event", "ts",
                                                                    "entropy_score",
                                                                    "drift_score",
                                                                    "contradiction_count",
                                                                    "lane_count",
                                                                    "tick_count",
                                                                    "belief_count",
                                                                    "missing_count",
                                                                    "node_count",
                                                                    "edge_count",
                                                                    "selected",
                                                                    "default_verdict",
                                                                    "safety_state")}}

    repair_suggestions = []
    contradictions = load_json(REG / "eqsb_contradiction_report.json", {})
    for c in (contradictions.get("contradictions") or []):
        if c.get("severity") in ("warning", "critical"):
            repair_suggestions.append({
                "contradiction_id": c.get("contradiction_id"),
                "severity": c.get("severity"),
                "action": c.get("recommended_action"),
                "title": c.get("title"),
            })

    payload = {
        "schema_version": EQSB_MAJOR_SCHEMA_VERSION,
        "kind": "eqsb_replay_audit_ledger",
        "generated_ts": now_iso(),
        "event_kinds_supported": EVENT_KINDS,
        "event_log_path": str(L_KERNEL_EVENTS.relative_to(ROOT)),
        "audit_log_path": str(L_MAJOR_AUDIT.relative_to(ROOT)),
        "event_count_total": len(events),
        "audit_event_count_total": len(audit_events),
        "events_by_kind": by_event,
        "last_per_event": last_per_event,
        "recent_events_tail": events[-15:],
        "recent_audit_tail": audit_events[-15:],
        "repair_suggestions": repair_suggestions,
        "replay_note": (
            "Replay is reconstructable by re-running each builder in the "
            "cadence loop order. Important kernel state transitions are "
            "always appended to data/logs/eqsb_kernel_events.jsonl."
        ),
    }
    payload.update(safety_envelope())
    payload["replay_ledger_hash"] = stable_hash({
        "event_count": payload["event_count_total"],
        "by_kind": by_event,
    })
    write_json(P_REPLAY_LEDGER, payload)
    append_event({"event": "build_replay_ledger",
                  "event_count_total": len(events)})
    return payload


def build():
    return build_replay_ledger()


if __name__ == "__main__":
    print(json.dumps(build(), indent=2))
