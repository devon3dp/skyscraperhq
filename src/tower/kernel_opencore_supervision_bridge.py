"""kernel_opencore_supervision_bridge.py

Cognitive OpenClaw / OpenCore supervision bridge for the QSB Kernel
(advisory only).

OpenClaw execution is LOCKED. This bridge does not invoke OpenClaw. It only
summarizes what OpenClaw *would be asked to inspect* based on current
registries, and surfaces any OpenClaw-related ticket registries already on
disk.

Writes:
    data/registries/qsb_kernel_opencore_supervision_state.json
    data/logs/qsb_kernel_opencore_supervision.jsonl
"""

from pathlib import Path
import json
import sys

from tower.kernel_cognitive_common import (
    LOGS, REG, append_jsonl, load_registry, registry_exists,
    safety_block, utc_now_iso, write_registry,
)


OPENCLAW_REGISTRY_CANDIDATES = [
    "openclaw_tickets.json",
    "openclaw_status.json",
    "openclaw_findings.json",
    "qsb_openclaw_supervisor_status.json",
    "qsb_openclaw_ticket_queue.json",
]


def _collect_openclaw_registries():
    found = {}
    for n in OPENCLAW_REGISTRY_CANDIDATES:
        if registry_exists(n):
            data = load_registry(n)
            found[n] = data
    return found


def run():
    reflection = load_registry("qsb_kernel_reflection_state.json")
    attention = load_registry("qsb_kernel_attention_state.json")
    found = _collect_openclaw_registries()

    open_tickets = []
    for name, data in found.items():
        if isinstance(data, dict):
            for t in (data.get("tickets") or data.get("open_tickets") or []):
                if isinstance(t, dict):
                    open_tickets.append({
                        "from": name,
                        "id": t.get("id") or t.get("ticket_id"),
                        "kind": t.get("kind") or t.get("type"),
                        "title": t.get("title") or t.get("summary"),
                        "status": t.get("status") or "open",
                    })
        elif isinstance(data, list):
            for t in data:
                if isinstance(t, dict):
                    open_tickets.append({
                        "from": name,
                        "id": t.get("id") or t.get("ticket_id"),
                        "kind": t.get("kind") or t.get("type"),
                        "title": t.get("title") or t.get("summary"),
                        "status": t.get("status") or "open",
                    })

    suggested_inspections = []
    if isinstance(reflection, dict):
        for s in (reflection.get("openclaw_inspection_suggestions") or []):
            suggested_inspections.append(s)
    if isinstance(attention, dict):
        for it in (attention.get("priority_items") or []):
            if it.get("severity") in ("critical", "high"):
                suggested_inspections.append({
                    "ticket_kind": "openclaw_inspection",
                    "title": "Triage: " + str(it.get("issue")),
                    "evidence": [it.get("evidence_source")],
                    "scope": "read-only triage",
                })

    payload = {
        "module": "kernel_opencore_supervision_bridge",
        "purpose": ("Summarize what OpenClaw / OpenCore supervision should "
                    "inspect next. Never invokes OpenClaw; the execution "
                    "gate openclaw_execution_enabled is locked false."),
        "timestamp_utc": utc_now_iso(),
        "openclaw_execution_enabled": False,
        "openclaw_real_tool_execution_enabled": False,
        "recruitment_openclaw_execution_enabled": False,
        "openclaw_registries_found": list(found.keys()),
        "open_tickets": open_tickets,
        "open_ticket_count": len(open_tickets),
        "suggested_inspections": suggested_inspections,
        "suggested_inspection_count": len(suggested_inspections),
        "source_file_list": [
            "data/registries/qsb_kernel_reflection_state.json",
            "data/registries/qsb_kernel_attention_state.json",
        ] + ["data/registries/" + n for n in OPENCLAW_REGISTRY_CANDIDATES],
        "confidence": 0.85,
        "warnings": ["openclaw_registries_absent"] if not found else [],
        "safety": safety_block(),
    }

    rel = write_registry("qsb_kernel_opencore_supervision_state.json",
                          payload)
    append_jsonl("qsb_kernel_opencore_supervision.jsonl", {
        "ts": utc_now_iso(),
        "open_ticket_count": len(open_tickets),
        "suggested_inspection_count": len(suggested_inspections),
        "openclaw_execution_enabled": False,
    })
    return {"written": rel,
            "open_ticket_count": len(open_tickets),
            "suggested_inspection_count": len(suggested_inspections)}


def main():
    print(json.dumps(run(), indent=2))
    return 0


if __name__ == "__main__":
    sys.exit(main())
