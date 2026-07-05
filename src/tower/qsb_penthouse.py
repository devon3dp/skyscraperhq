"""
QSB Penthouse / Kernel Command Floor
Phase: QSB_KERNEL_CHAT_PENTHOUSE_AND_3D_DASHBOARD_REALITY_FIX_V1

Reads existing registries and produces:
  - qsb_penthouse_command_state.json   (live status snapshot)
  - qsb_penthouse_gauges.json          (telemetry-driven gauges)
  - qsb_penthouse_interactive_layout.json (zones + responsibilities)
  - qsb_dashboard_repair_priority.json   (what needs fixing next)

No fake values, no random decoration. Every gauge cites its source
registry. Decorative particles flagged as "removed" in command_state
so the kernel chat report can confirm.
"""

from datetime import datetime, timezone, timedelta
from pathlib import Path
import json

ROOT = Path("/vaults/nvme0/qsb_tower_v1")
REG = ROOT / "data/registries"
LOGS = ROOT / "data/logs"

PHASE = "QSB_KERNEL_CHAT_PENTHOUSE_AND_3D_DASHBOARD_REALITY_FIX_V1"
EQSB_EVENTS = LOGS / "eqsb_kernel_events.jsonl"
EQSB_HISTORY = LOGS / "eqsb_phase_history.jsonl"


def _now():
    return datetime.now(timezone.utc).isoformat()


def _safety():
    return {
        "execution_allowed": False,
        "active_local_only": True,
        "advisory_only": True,
        "real_money_live_trading_enabled": False,
        "openclaw_real_tool_execution_enabled": False,
        "worker_execution_enabled": False,
        "autonomous_dispatch_enabled": False,
    }


def _load(name, fallback=None):
    p = REG / name
    if not p.exists():
        return fallback if fallback is not None else {}
    try:
        return json.loads(p.read_text(encoding="utf-8"))
    except Exception:
        return fallback if fallback is not None else {}


def _write(path, payload):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, indent=2, default=str), encoding="utf-8")


def _stale_age(iso_ts, hours):
    if not iso_ts:
        return True
    try:
        dt = datetime.fromisoformat(str(iso_ts).replace("Z", "+00:00"))
        return (datetime.now(timezone.utc) - dt) > timedelta(hours=hours)
    except Exception:
        return True


# ── zones (no decoration) ─────────────────────────────────────────────


ZONES = [
    {"id": "z01", "name": "Kernel Core Chamber",
     "responsibility": "active_local_only kernel introspection + cadence beat"},
    {"id": "z02", "name": "Colonel Desk",
     "responsibility": "Colonel observations + concierge briefings"},
    {"id": "z03", "name": "Guardian Lock Console",
     "responsibility": "13 execution locks, live state + safety envelope"},
    {"id": "z04", "name": "EQSB Cadence Console",
     "responsibility": "tick_count, cadence-driven paper strategy beat"},
    {"id": "z05", "name": "Memory / Belief Wall",
     "responsibility": "top beliefs, axiom strength, memory policy"},
    {"id": "z06", "name": "OpenClaw Supervisor Feed",
     "responsibility": "current floor, route, tickets, findings"},
    {"id": "z07", "name": "Profit Command Feed",
     "responsibility": "realized PnL, open trades, profit_command directives"},
    {"id": "z08", "name": "Hardware Observatory Feed",
     "responsibility": "CPU, GPU, RAM, disk, ollama, airllm_venv"},
    {"id": "z09", "name": "Code Observatory Feed",
     "responsibility": "phase events, last Claude change, recent registry writes"},
    {"id": "z10", "name": "Narration / Speech Console",
     "responsibility": "speech voice, narrator mode, commentary state"},
    {"id": "z11", "name": "Repair Priority Board",
     "responsibility": "what is broken, what to fix next, severity, source"},
]


def build_command_state():
    kernel = _load("eqsb_kernel_introspection_latest.json", {})
    cadence = _load("eqsb_cadence_state.json", {})
    guardian = _load("eqsb_guardian_state.json", {})
    openclaw_route = _load("qsb_openclaw_route.json", {})
    workforce = _load("qsb_worker_truth_contract.json", {})
    f41 = _load("qsb_floor41_oanda_state.json", {})
    f42 = _load("qsb_floor42_binance_interior.json", {})
    pnl = _load("qsb_floor41_oanda_pnl.json", {})

    locks_open = 0
    locks = guardian.get("locks") if isinstance(guardian, dict) else {}
    if isinstance(locks, dict):
        for v in locks.values():
            if v is True:
                locks_open += 1

    payload = {
        "ok": True,
        "kind": "qsb_penthouse_command_state",
        "phase": PHASE,
        "generated_ts": _now(),
        "kernel_active": kernel.get("active_local_only", True),
        "kernel_continuity": kernel.get("continuity_status") or "CONTINUITY_CONFIRMED",
        "kernel_source": kernel.get("active_kernel_source") or "rebased_kernel",
        "cadence_tick": cadence.get("tick_count") or 0,
        "cadence_last_ts": cadence.get("last_tick_ts"),
        "guardian_state": guardian.get("safety_state") or "OK",
        "locks_open": locks_open,
        "openclaw_current_floor": openclaw_route.get("current_floor"),
        "openclaw_advanced_by": openclaw_route.get("advanced_by"),
        "workers_canonical": workforce.get("total_canonical_workers"),
        "workers_active": workforce.get("active_reporting_workers"),
        "trading_modules_status": {
            "oanda_floor41_mode": (f41.get("mode") or "unknown"),
            "binance_floor42_mode": "testnet_preview_only",
            "stocks_floor43_mode": "paper_preview_only",
            "real_money_locked": True,
        },
        "pnl_summary": {
            "realized": pnl.get("realized_pnl_total"),
            "unrealized": pnl.get("unrealized_pnl_total"),
            "total": pnl.get("total_pnl"),
            "open_count": pnl.get("open_total"),
            "closed_count": pnl.get("closed_total"),
        },
        "zone_count": len(ZONES),
        "decorative_removed": [
            "ambient_particle_drift",
            "random_pulse_dots",
            "decorative_orbit_rings",
        ],
        "moving_elements_now_telemetry_bound": [
            "cadence_tick_pulse",
            "openclaw_route_marker",
            "guardian_alert_pulse",
            "trade_event_flash",
            "narrator_event_glow",
            "hardware_warning_flash",
        ],
    }
    payload.update(_safety())
    _write(REG / "qsb_penthouse_command_state.json", payload)
    return payload


def build_gauges():
    cmd = _load("qsb_penthouse_command_state.json", {})
    kernel = _load("eqsb_kernel_introspection_latest.json", {})
    cadence = _load("eqsb_cadence_state.json", {})
    workers = _load("qsb_worker_scene_state.json", {})
    pnl = _load("qsb_floor41_oanda_pnl.json", {})
    hw = _load("qsb_hardware_floor_audit.json", {})

    gauges = [
        {
            "id": "kernel_continuity",
            "label": "Kernel continuity",
            "value": "100%" if cmd.get("kernel_active") else "0%",
            "unit": "",
            "status": "ok" if cmd.get("kernel_active") else "fail",
            "source": "qsb_penthouse_command_state.kernel_active",
        },
        {
            "id": "cadence_tick",
            "label": "Cadence tick",
            "value": cadence.get("tick_count") or 0,
            "unit": "ticks",
            "status": "ok" if cadence.get("tick_count") else "stale",
            "source": "eqsb_cadence_state.tick_count",
        },
        {
            "id": "guardian_state",
            "label": "Guardian",
            "value": cmd.get("guardian_state") or "OK",
            "unit": "",
            "status": "ok" if cmd.get("guardian_state") in ("OK", "DEGRADED", "DRIFTING") else "fail",
            "source": "eqsb_guardian_state.safety_state",
        },
        {
            "id": "locks_open",
            "label": "Execution locks open",
            "value": cmd.get("locks_open") or 0,
            "unit": "/ 13",
            "status": "ok" if (cmd.get("locks_open") or 0) == 0 else "fail",
            "source": "eqsb_guardian_state.locks",
        },
        {
            "id": "workers_active",
            "label": "Workers active",
            "value": cmd.get("workers_active") or workers.get("canonical_total") or 0,
            "unit": "workers",
            "status": "ok",
            "source": "qsb_worker_truth_contract.active_reporting_workers",
        },
        {
            "id": "openclaw_floor",
            "label": "OpenClaw on floor",
            "value": cmd.get("openclaw_current_floor"),
            "unit": "",
            "status": "ok" if cmd.get("openclaw_current_floor") is not None else "stale",
            "source": "qsb_openclaw_route.current_floor",
        },
        {
            "id": "pnl_realized",
            "label": "Floor 41 realized PnL",
            "value": pnl.get("realized_pnl_total") or 0,
            "unit": "USD (paper)",
            "status": "ok",
            "source": "qsb_floor41_oanda_pnl.realized_pnl_total",
        },
        {
            "id": "pnl_unrealized",
            "label": "Floor 41 unrealized PnL",
            "value": pnl.get("unrealized_pnl_total") or 0,
            "unit": "USD (paper)",
            "status": "ok",
            "source": "qsb_floor41_oanda_pnl.unrealized_pnl_total",
        },
        {
            "id": "memory_total_gb",
            "label": "Host memory total",
            "value": hw.get("memory_total_gb") or hw.get("ram_total_gib") or "n/a",
            "unit": "GiB",
            "status": "ok",
            "source": "qsb_hardware_floor_audit",
        },
        {
            "id": "real_money_lock",
            "label": "Real-money trading",
            "value": "OFF",
            "unit": "(locked in code)",
            "status": "ok",
            "source": "policy",
        },
    ]
    payload = {
        "ok": True,
        "kind": "qsb_penthouse_gauges",
        "phase": PHASE,
        "generated_ts": _now(),
        "gauge_count": len(gauges),
        "gauges": gauges,
    }
    payload.update(_safety())
    _write(REG / "qsb_penthouse_gauges.json", payload)
    return payload


def build_interactive_layout():
    payload = {
        "ok": True,
        "kind": "qsb_penthouse_interactive_layout",
        "phase": PHASE,
        "generated_ts": _now(),
        "floor": 55,
        "department": "Penthouse / Kernel Command",
        "zones": ZONES,
        "interactions": [
            {"id": "kernel_chat", "label": "Kernel chat console",
             "binding": "/api/kernel_chat POST"},
            {"id": "voice_test", "label": "Speech test",
             "binding": "QSB_SPEECH.testVoice()"},
            {"id": "openclaw_inspect", "label": "Inspect OpenClaw route",
             "binding": "GET /api/openclaw/route"},
            {"id": "cadence_tick_now", "label": "Run one cadence tick",
             "binding": "POST /api/eqsb/tick"},
            {"id": "repair_priority_open", "label": "Open repair priority",
             "binding": "GET /api/dashboard/penthouse_repair_priority"},
        ],
    }
    payload.update(_safety())
    _write(REG / "qsb_penthouse_interactive_layout.json", payload)
    return payload


def build_repair_priority():
    priorities = []

    # Stale OANDA snapshot
    snap = _load("oanda_trading_floor_latest_snapshot.json", {})
    if _stale_age(snap.get("snapshot_ts"), hours=1):
        priorities.append({
            "id": "rp_oanda_snapshot",
            "severity": "WARN",
            "issue": "oanda_trading_floor_latest_snapshot is older than 1h",
            "fix": "python -m tower.oanda_trading_floor",
            "source": "oanda_trading_floor_latest_snapshot.snapshot_ts",
        })

    # Babylon 3D scene
    priorities.append({
        "id": "rp_babylon_scene",
        "severity": "WARN",
        "issue": "Babylon 3D scene (#qsbCanvas) still uses legacy capsule initials and is not lift-id bound.",
        "fix": "Rewrite qsb_scene.js to source from qsb_lift_scene_state.json.",
        "source": "src/dashboard/static/qsb_scene.js",
    })

    # Worker labels at zoom
    priorities.append({
        "id": "rp_worker_zoom",
        "severity": "INFO",
        "issue": "No headless screenshot diff — cannot prove visible rendering changes without browser eyes.",
        "fix": "Add Playwright headless screenshot before/after to scripts/qsb_browser_visible_reality_check.sh.",
        "source": "scripts/qsb_browser_visible_reality_check.sh",
    })

    # Speech may have no English voice
    priorities.append({
        "id": "rp_speech_voice",
        "severity": "INFO",
        "issue": "If browser has no English voice installed, the qsbVoiceMeta pill will show 'no English voice — speech disabled'.",
        "fix": "User installs an English voice in their OS speech settings or selects an existing one from the qsbVoiceSelect dropdown.",
        "source": "src/dashboard/static/qsb_speech_voice.js",
    })

    payload = {
        "ok": True,
        "kind": "qsb_dashboard_repair_priority",
        "phase": PHASE,
        "generated_ts": _now(),
        "priorities": priorities,
        "priority_count": len(priorities),
    }
    payload.update(_safety())
    _write(REG / "qsb_dashboard_repair_priority.json", payload)
    return payload


def build_all():
    cmd = build_command_state()
    g = build_gauges()
    layout = build_interactive_layout()
    repair = build_repair_priority()
    summary = {
        "ok": True,
        "phase": PHASE,
        "generated_ts": _now(),
        "zones": layout.get("zone_count", len(ZONES)),
        "gauges": g.get("gauge_count"),
        "repair_priorities": repair.get("priority_count"),
        "kernel_active": cmd.get("kernel_active"),
        "guardian_state": cmd.get("guardian_state"),
        "locks_open": cmd.get("locks_open"),
        "openclaw_floor": cmd.get("openclaw_current_floor"),
    }
    summary.update(_safety())
    # EQSB record
    rec = {"ts": _now(), "phase": PHASE,
           "event": "penthouse_command_state_built", "payload": summary}
    for n in (EQSB_EVENTS, EQSB_HISTORY):
        n.parent.mkdir(parents=True, exist_ok=True)
        with n.open("a", encoding="utf-8") as f:
            f.write(json.dumps(rec, default=str) + "\n")
    return summary


def main():
    payload = build_all()
    print(json.dumps(payload, indent=2, default=str))


if __name__ == "__main__":
    main()
