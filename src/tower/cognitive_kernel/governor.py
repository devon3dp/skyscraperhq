"""Kernel Governor — runtime self-regulation layer.

Watches pressure across the tower (open trade count, recent activity rate,
process load) and decides whether a given subsystem should fire on the next
tick. Every decision is stamped to qsb_tower_activity_tail.jsonl so we can
see WHY the kernel chose to skip / throttle / proceed.

The governor does NOT change subsystem behavior — it just decides whether
each subsystem is allowed to run. Subsystems opt in by calling:

    from tower.cognitive_kernel.governor import should_run
    ok, reason = should_run("auto_close")
    if not ok:
        print(f"governor declined: {reason}")
        return

Pressure inputs (all soft):
    - open_trade_count         (high = back off cohort + synthesis)
    - recent_activity_rate     (events/min from activity tail)
    - last_run_age_seconds     (per subsystem; prevents runaway calls)
    - current_kernel_mode      (some subsystems disabled in SLEEP / MEDITATE)

Safety: governor is advisory; subsystems can ignore it (they don't). It
never flips an execution gate. It only sets a 'yes / no / wait' bit.
"""

from __future__ import annotations
import json
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

ROOT = Path("/vaults/nvme0/qsb_tower_v1")
REG = ROOT / "data/registries"
STATE_PATH = REG / "qsb_kernel_governor_state.json"
ACTIVITY_TAIL = REG / "qsb_tower_activity_tail.jsonl"

# Per-subsystem cooldown floors (seconds). The governor will refuse to run
# the same subsystem twice within this window even if everything else is OK.
COOLDOWN_SECONDS = {
    "auto_close":        45,
    "synthesis":         120,
    "cohort_train":      90,
    "kernel_introspect": 300,
    "audit_event":       0,    # always allowed
}

# Pressure thresholds (soft caps).
OPEN_TRADE_HIGH_PRESSURE = 30     # above this, throttle synthesis + cohort
ACTIVITY_RATE_HIGH_PRESSURE = 60  # events/min above this = busy tower


def _now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds").replace("+00:00", "Z")


def _load(rel: str, fallback=None):
    p = REG / rel
    if not p.exists():
        return fallback if fallback is not None else {}
    try:
        return json.loads(p.read_text(encoding="utf-8"))
    except Exception:
        return fallback if fallback is not None else {}


def _load_state() -> dict:
    return _load(STATE_PATH.name, {"last_run_ts": {}, "last_decisions": []})


def _save_state(state: dict) -> None:
    STATE_PATH.parent.mkdir(parents=True, exist_ok=True)
    STATE_PATH.write_text(json.dumps(state, indent=2), encoding="utf-8")


def _stamp_activity(summary: str, payload: dict) -> None:
    """Append a governor decision event to the activity tail."""
    ACTIVITY_TAIL.parent.mkdir(parents=True, exist_ok=True)
    ev = {
        "ts": _now(),
        "event_kind": "audit_event",
        "summary": summary,
        "payload": payload,
        "floor": "F55",   # governor lives in the penthouse with the kernel
    }
    with ACTIVITY_TAIL.open("a", encoding="utf-8") as f:
        f.write(json.dumps(ev) + "\n")


# ── pressure measurement ────────────────────────────────────────────────


def _open_trade_count() -> int:
    lc = _load("qsb_floor41_oanda_trade_lifecycle.json")
    return len(lc.get("open_trades", [])) if isinstance(lc, dict) else 0


def _activity_rate_per_min() -> float:
    """Count events in the last 60s in the activity tail."""
    if not ACTIVITY_TAIL.exists():
        return 0.0
    cutoff = time.time() - 60.0
    n = 0
    try:
        with ACTIVITY_TAIL.open("r", encoding="utf-8") as f:
            # Cheap tail — read last ~120 lines max
            lines = f.readlines()[-200:]
        for line in lines:
            line = line.strip()
            if not line: continue
            try:
                ev = json.loads(line)
            except Exception:
                continue
            ts = ev.get("ts", "")
            if not ts: continue
            try:
                ev_t = datetime.fromisoformat(ts.replace("Z", "+00:00")).timestamp()
            except Exception:
                continue
            if ev_t >= cutoff:
                n += 1
    except Exception:
        return 0.0
    return float(n)


def _current_mode() -> str:
    s = _load("qsb_kernel_mode_state.json")
    return (s.get("current_mode") if isinstance(s, dict) else None) or "WAKE"


def _mode_allows(subsystem: str, mode: str) -> tuple[bool, str]:
    """Mode-gating: some subsystems are off in some modes."""
    # Default-on. Spell out the exceptions.
    if mode == "SLEEP":
        if subsystem in ("synthesis", "cohort_train", "kernel_introspect"):
            return False, f"mode={mode} forbids compute-heavy subsystems"
    if mode == "MEDITATE":
        if subsystem == "cohort_train":
            return False, f"mode={mode} disables active worker training (kernel introspecting)"
    if mode == "DREAM":
        # In DREAM mode we permit synthesis without contradiction-check
        # (handled inside the sandbox), but disable cohort_train.
        if subsystem == "cohort_train":
            return False, f"mode={mode} disables real placement (exploration only)"
    if mode == "EVOLVE":
        # In EVOLVE we WANT introspection + synthesis to fire often.
        return True, "ok"
    return True, "ok"


def measure_pressure() -> dict:
    """Snapshot pressure inputs for the next decision."""
    return {
        "open_trade_count": _open_trade_count(),
        "activity_rate_per_min": _activity_rate_per_min(),
        "current_mode": _current_mode(),
        "ts": _now(),
    }


# ── decision ────────────────────────────────────────────────────────────


def should_run(subsystem: str) -> tuple[bool, str]:
    """Should `subsystem` fire on this tick? Returns (yes/no, reason).

    Records the decision in qsb_kernel_governor_state.json and stamps it
    to the activity tail.
    """
    state = _load_state()
    pressure = measure_pressure()
    mode = pressure["current_mode"]

    # Mode gate first
    mode_ok, mode_reason = _mode_allows(subsystem, mode)
    if not mode_ok:
        _record(state, subsystem, False, mode_reason, pressure)
        return False, mode_reason

    # Cooldown gate
    last_ts = state.get("last_run_ts", {}).get(subsystem)
    if last_ts:
        try:
            last_t = datetime.fromisoformat(last_ts.replace("Z", "+00:00")).timestamp()
            age = time.time() - last_t
            cd = COOLDOWN_SECONDS.get(subsystem, 30)
            if age < cd:
                reason = f"cooldown: last_run {int(age)}s ago, floor {cd}s"
                _record(state, subsystem, False, reason, pressure)
                return False, reason
        except Exception:
            pass

    # Pressure gates per-subsystem
    if subsystem in ("synthesis", "cohort_train"):
        if pressure["open_trade_count"] >= OPEN_TRADE_HIGH_PRESSURE:
            reason = (
                f"open_trade_count={pressure['open_trade_count']} >= "
                f"high_pressure {OPEN_TRADE_HIGH_PRESSURE}"
            )
            _record(state, subsystem, False, reason, pressure)
            return False, reason
        if pressure["activity_rate_per_min"] >= ACTIVITY_RATE_HIGH_PRESSURE:
            reason = (
                f"activity_rate={pressure['activity_rate_per_min']:.0f}/min "
                f">= high_pressure {ACTIVITY_RATE_HIGH_PRESSURE}/min"
            )
            _record(state, subsystem, False, reason, pressure)
            return False, reason

    # All checks passed
    _record(state, subsystem, True, f"ok in mode={mode}", pressure)
    state["last_run_ts"][subsystem] = pressure["ts"]
    _save_state(state)
    return True, f"ok in mode={mode}"


def _record(state: dict, subsystem: str, allowed: bool,
              reason: str, pressure: dict) -> None:
    decision = {
        "ts": pressure["ts"],
        "subsystem": subsystem,
        "allowed": allowed,
        "reason": reason,
        "mode": pressure["current_mode"],
        "open_trade_count": pressure["open_trade_count"],
        "activity_rate_per_min": pressure["activity_rate_per_min"],
    }
    state.setdefault("last_decisions", [])
    state["last_decisions"].append(decision)
    state["last_decisions"] = state["last_decisions"][-80:]
    _save_state(state)
    _stamp_activity(
        summary=f"governor · {'ALLOW' if allowed else 'DENY'} {subsystem} · {reason}",
        payload=decision,
    )


def status() -> dict:
    state = _load_state()
    pressure = measure_pressure()
    return {
        "ok": True,
        "kind": "qsb_kernel_governor_status",
        "generated_ts": _now(),
        "current_pressure": pressure,
        "cooldowns_seconds": COOLDOWN_SECONDS,
        "thresholds": {
            "open_trade_high_pressure": OPEN_TRADE_HIGH_PRESSURE,
            "activity_rate_high_pressure_per_min": ACTIVITY_RATE_HIGH_PRESSURE,
        },
        "last_run_ts": state.get("last_run_ts", {}),
        "last_decisions_tail": state.get("last_decisions", [])[-12:],
    }


if __name__ == "__main__":
    import argparse
    ap = argparse.ArgumentParser()
    ap.add_argument("--ask", help="ask whether subsystem can run now")
    ap.add_argument("--status", action="store_true")
    args = ap.parse_args()
    if args.status or not args.ask:
        s = status()
        p = s["current_pressure"]
        print(f"  mode:                 {p['current_mode']}")
        print(f"  open_trade_count:     {p['open_trade_count']}")
        print(f"  activity_rate/min:    {p['activity_rate_per_min']:.0f}")
        print(f"  last decisions:")
        for d in s["last_decisions_tail"]:
            mark = "✓" if d["allowed"] else "✗"
            print(f"    {mark} {d['ts'][:19]}  {d['subsystem']:18s}  {d['reason']}")
    else:
        ok, reason = should_run(args.ask)
        print(f"  {args.ask}: {'ALLOW' if ok else 'DENY'} · {reason}")
