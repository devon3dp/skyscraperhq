"""Pro Operations Cockpit V4 — aggregated state for the dashboard."""

from datetime import datetime, timezone
from .safety_contract import stamp_safe


def _now(): return datetime.now(timezone.utc).isoformat()


def pro_state():
    """Single snapshot for the Pro Dashboard top status bar + side rails."""
    from . import (worker_status, manager_status, overseer_status,
                    maintenance_status, security_status, it_status,
                    research_status, accounts_status, quantum_status,
                    models_status, lifts_status, training_status,
                    audit_status)
    from .oanda_practice_trading import account as oa_account, practice_preflight
    from .openclaw_practice import status as oc_status
    ws = worker_status(); ms = manager_status(); os_ = overseer_status()
    return stamp_safe({
        "ok": True, "ts": _now(),
        "phase":            "QSB_TOWER_OPERATIONS_V4",
        "dashboard_version":"QSB_TOWER_V1.4_PRO_OPERATIONS_COCKPIT",
        "renderer_version": "QSB_SKYSCRAPER_RENDERER_V4_PRO",
        "headline": "PRO OPERATIONS COCKPIT · OANDA PRACTICE ENABLED · LIVE REAL MONEY OFF · ALL REAL EXECUTION LOCKS CLOSED",
        "tower_summary": {
            "workers":  ws.get("total_workers"),
            "managers": ms.get("total_managers"),
            "overseers":os_.get("total_overseers"),
            "lifts":    9,
        },
        "department_health": {
            "maintenance":  maintenance_status().get("overall_status"),
            "security":     security_status().get("overall_status"),
            "it":           it_status().get("overall_status"),
            "research":     research_status().get("overall_status"),
            "accounts":     accounts_status().get("overall_status"),
            "quantum":      quantum_status().get("overall_status"),
            "training":     training_status().get("overall_status"),
            "models":       "live",
        },
        "oanda_practice": {
            "credentials_present": bool(oa_account().get("ok")),
            "account_label":       oa_account().get("label"),
            "balance":             oa_account().get("balance"),
            "NAV":                 oa_account().get("NAV"),
            "open_trade_count":    oa_account().get("open_trade_count"),
            "open_position_count": oa_account().get("open_position_count"),
            "preflight_ok":        practice_preflight().get("ok"),
            "execution_mode":      "PRACTICE_ONLY",
            "live_trading_enabled":         False,
            "real_order_execution_enabled": False,
            "oanda_practice_order_execution_enabled": True,
        },
        "openclaw": {
            "practice_mode_enabled":   True,
            "real_execution_enabled":  False,
            "proposal_count":          oc_status().get("proposal_count"),
        },
        "audit": {
            "overall_score":   audit_status().get("overall_score"),
            "overall_status":  audit_status().get("overall_status"),
            "critical_count":  audit_status().get("critical_count"),
        },
        "modes": ["3D Tower", "Operations", "Trading", "Workers", "OpenClaw",
                   "Models", "Accounts", "Audit", "Training", "Security",
                   "Maintenance", "AI Center"],
    })


def renderer_v4_state():
    from .tower_tick import live_state
    from .oanda_practice_trading import account as oa_account
    s = live_state()
    s["dashboard_version"] = "QSB_TOWER_V1.4_PRO_OPERATIONS_COCKPIT"
    s["renderer_version"]  = "QSB_SKYSCRAPER_RENDERER_V4_PRO"
    s["oanda_practice_trading_enabled"] = bool(oa_account().get("ok"))
    return stamp_safe(s)


def renderer_v4_options():
    return stamp_safe({
        "ok": True, "ts": _now(),
        "renderer_version": "QSB_SKYSCRAPER_RENDERER_V4_PRO",
        "options": [
            "show_worker_ids", "show_worker_names", "show_worker_roles",
            "show_managers", "show_overseers", "show_accountants",
            "show_lifts", "show_packets", "show_openclaw_routes",
            "show_model_routes", "show_trading_streams", "show_account_streams",
            "show_alerts_only", "show_practice_trading_only",
            "show_department_colors", "show_live_floor_status",
            "cinematic_camera", "auto_tour", "focus_floor",
            "explode_floor_view", "pause_animation", "performance_mode",
        ],
    })


# ── Lightweight wrapper endpoints ───────────────────────────────────
def floors_live():
    from . import worker_directory
    d = worker_directory()
    by_floor = {}
    for w in (d.get("directory") or []):
        fid = w.get("floor_id"); by_floor.setdefault(fid, 0); by_floor[fid] += 1
    return stamp_safe({"ok": True, "ts": _now(),
                        "occupancy_by_floor": by_floor,
                        "alive_floor_count": len([k for k, v in by_floor.items() if v > 0])})


def floors_activity():
    from .tower_tick import live_state
    return live_state()


def workers_live():
    from . import worker_directory
    return worker_directory()


def workers_routes():
    from . import workers_by_floor_dir
    return stamp_safe({"ok": True, "ts": _now(),
                        "note": "Workers do not autonomously dispatch. Route mapping is observation-only.",
                        "execution_allowed": False})


def packets_live():
    from .tower_tick import live_state
    s = live_state()
    return stamp_safe({"ok": True, "ts": _now(),
                        "tick_count": (s.get("tick_state") or {}).get("tick_count", 0),
                        "advisory_packet_types": [
                            "worker_report","manager_report","overseer_report",
                            "accounting_report","maintenance_alert","security_alert",
                            "IT_route","OpenClaw_practice_proposal","OANDA_practice_order",
                            "trading_telemetry","model_lane","AirLLM_advisory",
                            "kernel_chat","audit_report",
                        ]})


def events_live():
    from pathlib import Path
    import json
    ROOT = Path("/vaults/nvme0/qsb_tower_v1")
    files = sorted((ROOT / "logs/tower_ops").glob("*.jsonl"))[-5:]
    rows = []
    for f in files:
        try:
            lines = f.read_text(encoding="utf-8").splitlines()[-10:]
            for line in lines:
                try: rows.append({"source": f.name, **json.loads(line)})
                except Exception: pass
        except Exception: pass
    rows.sort(key=lambda r: r.get("ts", ""), reverse=True)
    return stamp_safe({"ok": True, "ts": _now(), "events": rows[:50]})


def departments_live():
    from . import (maintenance_status, security_status, it_status,
                    research_status, accounts_status, quantum_status,
                    training_status)
    return stamp_safe({"ok": True, "ts": _now(),
                        "departments": {
                            "maintenance":  maintenance_status().get("overall_status"),
                            "security":     security_status().get("overall_status"),
                            "it":           it_status().get("overall_status"),
                            "research":     research_status().get("overall_status"),
                            "accounts":     accounts_status().get("overall_status"),
                            "quantum":      quantum_status().get("overall_status"),
                            "training":     training_status().get("overall_status"),
                        }})


def accounts_live():
    from .oanda_practice_trading import account as oa, practice_ledger
    return stamp_safe({"ok": True, "ts": _now(),
                        "oanda_practice": oa(),
                        "practice_ledger": practice_ledger(),
                        "binance_account": "not_configured_v4",
                        "stocks_account":  "not_configured_v4"})


def oanda_practice_summary():
    from .oanda_practice_trading import (account as oa, open_trades,
                                          open_positions, transactions, practice_ledger,
                                          practice_preflight)
    ac = oa()
    return stamp_safe({
        "ok": True, "ts": _now(),
        "label": "OANDA_PRACTICE_SUMMARY",
        "account": ac,
        "open_trades":     (open_trades().get("trades") or [])[:10],
        "open_positions":  (open_positions().get("positions") or [])[:10],
        "recent_transactions": (transactions(10).get("transactions") or [])[:10],
        "practice_ledger_entry_count": len(practice_ledger().get("entries") or []),
        "preflight_ok": practice_preflight().get("ok"),
        "execution_mode": "PRACTICE_ONLY",
        "live_trading_enabled":         False,
        "real_order_execution_enabled": False,
        "oanda_practice_order_execution_enabled": True,
    })


def kernel_live():
    from . import kernel_chat_diagnostics, speech_status, models_lanes
    return stamp_safe({"ok": True, "ts": _now(),
                        "chat":   kernel_chat_diagnostics(),
                        "speech": speech_status(),
                        "model_lanes_top": (models_lanes().get("lanes") or [])[:3]})


def models_live():
    from . import models_lanes
    return models_lanes()
