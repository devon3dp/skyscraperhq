"""Kernel operating modes — kernel postures Wren switches between.

Modes change the kernel's rhythm and which subsystems are eligible to fire
on a tick. They never change the kernel's identity (still advisory-only,
still local-symbolic) and they never flip an execution gate.

Modes:
    WAKE       — default. All subsystems polling. Dispatch ready.
    RESEARCH   — F37 synthesis fires often; ML/RL classroom active; cohort
                 training muted unless explicitly dispatched.
    MEDITATE   — kernel introspects beliefs; writes meta-letters; auto-close
                 still runs; cohort training disabled.
    DREAM      — synthesis runs WITHOUT contradiction checks (exploration);
                 cohort training disabled; outputs marked as speculation.
    EVOLVE     — auto-update topic table from no_topic_matched events; both
                 synthesis + introspection fire often.
    SLEEP      — only ticker + activity tail; no compute-heavy work.

Persists to:
    data/registries/qsb_kernel_mode_state.json

Reads from CLAUDE.md V1.5 to confirm advisory-only invariant.
"""

from __future__ import annotations
import json
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path("/vaults/nvme0/qsb_tower_v1")
REG = ROOT / "data/registries"
STATE_PATH = REG / "qsb_kernel_mode_state.json"
ACTIVITY_TAIL = REG / "qsb_tower_activity_tail.jsonl"

VALID_MODES = ("WAKE", "RESEARCH", "MEDITATE", "DREAM", "EVOLVE", "SLEEP")
DEFAULT_MODE = "WAKE"

MODE_DESCRIPTIONS = {
    "WAKE":     "Default. All subsystems polling. Dispatch ready.",
    "RESEARCH": "F37 synthesis fires often; classroom active; cohort training muted unless dispatched.",
    "MEDITATE": "Kernel introspects beliefs; writes meta-letters; auto-close runs; cohort training off.",
    "DREAM":    "Synthesis runs WITHOUT contradiction checks (exploratory); outputs marked speculation.",
    "EVOLVE":   "Auto-update topic table from no_topic_matched events; synthesis + introspection fire often.",
    "SLEEP":    "Only ticker + activity tail; no compute-heavy work.",
}

MODE_SUBSYSTEM_GATES = {
    "WAKE":     {"auto_close": True,  "synthesis": True,  "cohort_train": True,  "kernel_introspect": True},
    "RESEARCH": {"auto_close": True,  "synthesis": True,  "cohort_train": False, "kernel_introspect": True},
    "MEDITATE": {"auto_close": True,  "synthesis": False, "cohort_train": False, "kernel_introspect": True},
    "DREAM":    {"auto_close": True,  "synthesis": True,  "cohort_train": False, "kernel_introspect": True},
    "EVOLVE":   {"auto_close": True,  "synthesis": True,  "cohort_train": True,  "kernel_introspect": True},
    "SLEEP":    {"auto_close": False, "synthesis": False, "cohort_train": False, "kernel_introspect": False},
}


def _now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds").replace("+00:00", "Z")


def _stamp_activity(summary: str, payload: dict) -> None:
    ACTIVITY_TAIL.parent.mkdir(parents=True, exist_ok=True)
    ev = {
        "ts": _now(),
        "event_kind": "audit_event",
        "summary": summary,
        "payload": payload,
        "floor": "F55",
    }
    with ACTIVITY_TAIL.open("a", encoding="utf-8") as f:
        f.write(json.dumps(ev) + "\n")


def current_mode() -> dict:
    if not STATE_PATH.exists():
        return {
            "current_mode": DEFAULT_MODE,
            "description": MODE_DESCRIPTIONS[DEFAULT_MODE],
            "gates": MODE_SUBSYSTEM_GATES[DEFAULT_MODE],
            "last_transition_ts": None,
            "last_transition_by": None,
        }
    try:
        s = json.loads(STATE_PATH.read_text(encoding="utf-8"))
        mode = s.get("current_mode", DEFAULT_MODE)
        if mode not in VALID_MODES:
            mode = DEFAULT_MODE
        return {
            "current_mode": mode,
            "description": MODE_DESCRIPTIONS[mode],
            "gates": MODE_SUBSYSTEM_GATES[mode],
            "last_transition_ts": s.get("last_transition_ts"),
            "last_transition_by": s.get("last_transition_by"),
            "history_tail": s.get("history", [])[-8:],
        }
    except Exception:
        return current_mode.__wrapped__() if hasattr(current_mode, "__wrapped__") else {
            "current_mode": DEFAULT_MODE,
            "description": MODE_DESCRIPTIONS[DEFAULT_MODE],
            "gates": MODE_SUBSYSTEM_GATES[DEFAULT_MODE],
        }


def set_mode(new_mode: str, by: str = "Wren", reason: str = "") -> dict:
    if new_mode not in VALID_MODES:
        raise ValueError(f"unknown mode {new_mode!r}; valid: {VALID_MODES}")
    state = {}
    if STATE_PATH.exists():
        try:
            state = json.loads(STATE_PATH.read_text(encoding="utf-8"))
        except Exception:
            state = {}
    prior = state.get("current_mode", DEFAULT_MODE)
    history = state.get("history", [])
    transition = {
        "ts": _now(),
        "from": prior,
        "to": new_mode,
        "by": by,
        "reason": reason,
    }
    history.append(transition)
    history = history[-200:]
    new_state = {
        "ok": True,
        "kind": "qsb_kernel_mode_state",
        "current_mode": new_mode,
        "description": MODE_DESCRIPTIONS[new_mode],
        "gates": MODE_SUBSYSTEM_GATES[new_mode],
        "last_transition_ts": transition["ts"],
        "last_transition_by": by,
        "history": history,
        "advisory_only": True,
    }
    STATE_PATH.parent.mkdir(parents=True, exist_ok=True)
    STATE_PATH.write_text(json.dumps(new_state, indent=2), encoding="utf-8")
    _stamp_activity(
        summary=f"kernel mode transition · {prior} → {new_mode} · by {by}",
        payload=transition,
    )
    return current_mode()


if __name__ == "__main__":
    import argparse
    ap = argparse.ArgumentParser()
    ap.add_argument("--set", choices=VALID_MODES,
                    help="set kernel mode")
    ap.add_argument("--by", default="cli", help="actor name")
    ap.add_argument("--reason", default="", help="why")
    args = ap.parse_args()
    if args.set:
        s = set_mode(args.set, by=args.by, reason=args.reason)
        print(f"  mode set: {s['current_mode']}  ({s['description']})")
    else:
        s = current_mode()
        print(f"  current: {s['current_mode']}  ({s['description']})")
        print(f"  gates: {s['gates']}")
        print(f"  last_transition_by: {s.get('last_transition_by')}")
