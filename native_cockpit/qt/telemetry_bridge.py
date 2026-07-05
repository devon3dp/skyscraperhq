"""
QSB Native Cockpit V2 — Telemetry Bridge
Phase: QSB_NATIVE_COCKPIT_STANDALONE_SKYSCRAPER_PLATFORM_V2

Reads local QSB registries (no HTTP dependency by default). Falls back
to the local HTTP server if registries are missing.

Returns a unified scene snapshot the Qt scene engine consumes.

No secrets in logs. No external API calls.
"""

from pathlib import Path
import json
import urllib.request

ROOT = Path("/vaults/nvme0/qsb_tower_v1")
REG = ROOT / "data/registries"
HTTP_BASE = "http://127.0.0.1:8765"
TIMEOUT_SEC = 2.0


def _load_local(name, fallback=None):
    p = REG / name
    if not p.exists():
        return fallback if fallback is not None else {}
    try:
        return json.loads(p.read_text(encoding="utf-8"))
    except Exception:
        return fallback if fallback is not None else {}


def _fetch_http(path):
    try:
        with urllib.request.urlopen(HTTP_BASE + path, timeout=TIMEOUT_SEC) as r:
            return json.loads(r.read().decode("utf-8"))
    except Exception:
        return None


def http_available():
    try:
        with urllib.request.urlopen(HTTP_BASE + "/api/unified", timeout=1.0) as r:
            return r.status == 200
    except Exception:
        return False


def build_scene_snapshot():
    """Return a single dict consumed by the Qt scene engine.

    Source of truth is local registries; HTTP is fallback for fields
    that are computed live (e.g., trade lifecycle).
    """
    audit = _load_local("qsb_full_floor_audit.json")
    masterplan = _load_local("qsb_floor_occupancy_masterplan.json")
    workforce_new = _load_local("qsb_new_1000_workers_employed.json")
    workforce_canon = _load_local("qsb_worker_truth_contract.json")
    lifts = _load_local("qsb_lift_scene_state.json")
    workers_scene = _load_local("qsb_worker_scene_state.json")
    openclaw_route = _load_local("qsb_openclaw_route.json")
    openclaw_tickets = _load_local("qsb_openclaw_tickets.json")
    openclaw_full = _load_local("qsb_openclaw_full_floor_inspection.json")
    commerce_wing = _load_local("qsb_commerce_wing_masterplan.json")
    shop_opps = _load_local("qsb_online_shop_opportunity_map.json")
    etsy = _load_local("qsb_etsy_floor_manifest.json")
    pod = _load_local("qsb_print_on_demand_floor.json")
    pnl = _load_local("qsb_floor41_oanda_pnl.json")
    open_t = _load_local("qsb_floor41_oanda_open_trades.json")
    closed_t = _load_local("qsb_floor41_oanda_closed_trades.json")
    cadence = _load_local("eqsb_cadence_state.json")
    guardian = _load_local("eqsb_guardian_state.json")
    floor42 = _load_local("qsb_floor42_binance_interior.json")
    floor43 = _load_local("qsb_floor43_stocks_interior.json")
    penthouse_cmd = _load_local("qsb_penthouse_command_state.json")
    penthouse_gauges = _load_local("qsb_penthouse_gauges.json")
    hw = _load_local("qsb_hardware_floor_audit.json")

    # Verified totals
    canonical_total = (workforce_canon.get("total_canonical_workers") or 0)
    new_v2 = workforce_new.get("new_worker_count") or 0
    verified_total = canonical_total + new_v2

    # Workers by floor — merged from canonical + new
    per_floor = {}
    for rec in (workers_scene.get("per_floor") or []):
        per_floor[rec.get("floor")] = {
            "floor": rec.get("floor"),
            "canonical_total": rec.get("total", 0),
            "classes": rec.get("classes", {}),
            "new_v2_total": 0,
        }
    by_floor_new = workforce_new.get("by_floor") or {}
    for fkey, cnt in by_floor_new.items():
        try:
            f = int(fkey)
        except Exception:
            continue
        if f not in per_floor:
            per_floor[f] = {
                "floor": f, "canonical_total": 0,
                "classes": {}, "new_v2_total": 0
            }
        per_floor[f]["new_v2_total"] = cnt

    # Floor catalog from masterplan (one entry per floor 1-53)
    floor_catalog = []
    for plan in (masterplan.get("floors") or []):
        f = plan.get("floor")
        pf = per_floor.get(f, {})
        floor_catalog.append({
            "floor": f,
            "primary": plan.get("primary_label"),
            "secondary": plan.get("secondary_department"),
            "purpose": plan.get("purpose"),
            "rooms": plan.get("rooms") or [],
            "team_size": plan.get("team_size") or 0,
            "profit": bool(plan.get("profit")),
            "kernel": bool(plan.get("kernel")),
            "safety": bool(plan.get("safety")),
            "rest": bool(plan.get("rest")),
            "preserve_existing": bool(plan.get("preserve_existing")),
            "canonical_workers": pf.get("canonical_total", 0),
            "new_v2_workers": pf.get("new_v2_total", 0),
            "total_workers": pf.get("canonical_total", 0) + pf.get("new_v2_total", 0),
        })

    return {
        "ts": (cadence.get("last_tick_ts") or ""),
        "verified": {
            "canonical_workers_before": canonical_total,
            "new_v2_workers": new_v2,
            "verified_total_workers": verified_total,
            "commerce_wing_floors": len(commerce_wing.get("departments") or []),
            "shop_opportunities_mapped": shop_opps.get("opportunity_count") or 0,
            "openclaw_findings": openclaw_full.get("finding_count") or 0,
            "openclaw_tickets": openclaw_full.get("ticket_count") or 0,
            "floor_masterplan_entries": masterplan.get("floor_count") or 0,
        },
        "floors": floor_catalog,
        "lifts": (lifts.get("lifts") or [])[:9],
        "openclaw": {
            "current_floor": openclaw_route.get("current_floor"),
            "advanced_by": openclaw_route.get("advanced_by"),
            "is_random": openclaw_route.get("is_random"),
            "ticket_count": openclaw_tickets.get("ticket_count") or
                             len(openclaw_tickets.get("tickets") or []),
            "tickets": (openclaw_tickets.get("tickets") or [])[:6],
            "full_inspection_findings": openclaw_full.get("finding_count") or 0,
            "full_inspection_tickets": openclaw_full.get("ticket_count") or 0,
        },
        "commerce_wing": {
            "floors": commerce_wing.get("departments") or [],
            "manual_approval_gate": commerce_wing.get("manual_approval_gate"),
            "live_payments_enabled": False,
            "live_listings_publishing_enabled": False,
            "shop_opportunities": (shop_opps.get("opportunities") or [])[:15],
        },
        "etsy": {
            "ok": etsy.get("ok"),
            "floor": etsy.get("floor"),
            "rooms": etsy.get("rooms") or [],
            "worker_count": etsy.get("worker_count") or 0,
            "draft_only": etsy.get("draft_only", True),
            "publishing_enabled": False,
            "credentials_status": "masked",
        },
        "print_on_demand": {
            "ok": pod.get("ok"),
            "floor": pod.get("floor"),
            "rooms": pod.get("rooms") or [],
            "worker_count": pod.get("worker_count") or 0,
            "draft_only": True,
        },
        "trading": {
            "oanda_pnl": {
                "realized": pnl.get("realized_pnl_total"),
                "unrealized": pnl.get("unrealized_pnl_total"),
                "total": pnl.get("total_pnl"),
                "open_count": pnl.get("open_total"),
                "closed_count": pnl.get("closed_total"),
            },
            "open_trades_first_5": (open_t.get("open_trades") or [])[:5],
            "closed_trades_last_5": (closed_t.get("closed_trades") or [])[-5:],
            "floor42_binance": {
                "rooms": (floor42.get("rooms") or []),
                "worker_count": len(floor42.get("workers") or []),
                "mode": (floor42.get("policy") or {}).get("mode"),
            },
            "floor43_stocks": {
                "rooms": (floor43.get("rooms") or []),
                "worker_count": len(floor43.get("workers") or []),
                "mode": (floor43.get("policy") or {}).get("mode"),
            },
        },
        "penthouse": {
            "kernel_active": penthouse_cmd.get("kernel_active"),
            "cadence_tick": penthouse_cmd.get("cadence_tick"),
            "guardian_state": penthouse_cmd.get("guardian_state"),
            "locks_open": penthouse_cmd.get("locks_open"),
            "gauges": (penthouse_gauges.get("gauges") or [])[:12],
        },
        "hardware": {
            "cpu": hw.get("cpu_model") or hw.get("cpu"),
            "cpu_cores": hw.get("cpu_count") or hw.get("cpu cores/threads"),
            "memory_total": hw.get("memory_total_gb") or hw.get("ram_total"),
            "gpu": hw.get("gpu_summary") or hw.get("gpu"),
            "kernel_release": hw.get("kernel"),
        },
        "safety_locks": {
            "real_money_live_trading_enabled": False,
            "openclaw_real_tool_execution_enabled": False,
            "live_payments_enabled": False,
            "live_listings_publishing_enabled": False,
            "external_api_calls_enabled": False,
            "guardian_state": guardian.get("safety_state") or "OK",
        },
        "browser_dashboard_fallback_url":
            "http://127.0.0.1:8765/?v=next3d&floor=55",
    }


if __name__ == "__main__":
    import sys
    snap = build_scene_snapshot()
    print(json.dumps({
        "ok": True,
        "verified": snap["verified"],
        "floors": len(snap["floors"]),
        "lifts": len(snap["lifts"]),
        "openclaw_floor": snap["openclaw"]["current_floor"],
        "commerce_wing_floors": len(snap["commerce_wing"]["floors"]),
        "shop_opportunities": len(snap["commerce_wing"]["shop_opportunities"]),
        "real_money_live_trading_enabled":
            snap["safety_locks"]["real_money_live_trading_enabled"],
    }, indent=2))
