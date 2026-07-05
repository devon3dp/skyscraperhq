"""Quantum Operations Department V1 — Floor 45.

Detects local quantum runtimes (qiskit / cirq / pennylane). Reports
status. Never executes circuits or trades. Advisory only.
"""

from datetime import datetime, timezone
from pathlib import Path
import importlib
import json

from .safety_contract import stamp_safe

ROOT = Path("/vaults/nvme0/qsb_tower_v1")
STATE_PATH = ROOT / "state/tower_ops/quantum_floor.json"
LOG_PATH   = ROOT / "logs/tower_ops/quantum_events.jsonl"


def _now(): return datetime.now(timezone.utc).isoformat()


def _detect_runtime():
    runtimes = []
    for pkg in ("qiskit", "cirq", "pennylane", "qsharp"):
        try:
            m = importlib.import_module(pkg)
            runtimes.append({"package": pkg, "version": getattr(m, "__version__", "unknown"),
                              "installed": True})
        except Exception:
            runtimes.append({"package": pkg, "installed": False})
    return runtimes


def status():
    runtimes = _detect_runtime()
    any_installed = any(r["installed"] for r in runtimes)
    label = "QUANTUM LAB ACTIVE" if any_installed else "QUANTUM LAB READY · runtime not connected"
    return stamp_safe({
        "ok": True, "ts": _now(),
        "overall_status": "healthy",
        "department": "Quantum Operations Department",
        "floor_number": 45, "floor_id": "floor_45",
        "label": label,
        "runtimes_detected": runtimes,
        "any_quantum_runtime_installed": any_installed,
        "policy": "ADVISORY_ONLY — no trading execution · no OpenClaw execution · no autonomous dispatch",
        "entropy_placeholder": "no_real_source_connected",
        "variance_placeholder": "no_real_source_connected",
    })


def workers():
    from .worker_registry import workers as worker_list
    ws = (worker_list().get("workers") or [])
    return stamp_safe({"ok": True, "ts": _now(),
                        "workers": [w for w in ws if w.get("floor_assignment") == "floor_45"]})


def reports():
    return stamp_safe({"ok": True, "ts": _now(),
                        "reports": ["Quantum runtime detection ran · advisory only."]})


def create_research_task(payload=None):
    """Forward to research_facility — quantum tasks live in the same registry."""
    from .research_facility import create_task
    payload = payload or {}
    payload.setdefault("title", "Quantum research task")
    payload.setdefault("owner", "Quantum Symbolic Analyst")
    return create_task(payload)
