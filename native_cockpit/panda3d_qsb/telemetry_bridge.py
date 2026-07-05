"""Panda3D fallback telemetry bridge — reads local QSB registries.

Shares the same JSON shape as the Qt fallback's bridge but lives in
the .venv_3d so Panda3D can import its own deps.
"""
from pathlib import Path
import json

ROOT = Path("/vaults/nvme0/qsb_tower_v1")
REG = ROOT / "data/registries"


def _load(name, fallback=None):
    p = REG / name
    if not p.exists():
        return fallback if fallback is not None else {}
    try:
        return json.loads(p.read_text(encoding="utf-8"))
    except Exception:
        return fallback if fallback is not None else {}


def build_scene_snapshot():
    master = _load("qsb_floor_occupancy_masterplan.json")
    new_workers = _load("qsb_new_1000_workers_employed.json")
    canon = _load("qsb_worker_truth_contract.json")
    lifts = _load("qsb_lift_scene_state.json")
    route = _load("qsb_openclaw_route.json")
    tickets = _load("qsb_openclaw_tickets.json")
    workers_scene = _load("qsb_worker_scene_state.json")
    pnl = _load("qsb_floor41_oanda_pnl.json")
    commerce = _load("qsb_commerce_wing_masterplan.json")

    per_floor_density = {}
    for r in (workers_scene.get("per_floor") or []):
        per_floor_density[r.get("floor")] = r.get("total", 0)
    new_by_floor = new_workers.get("by_floor") or {}

    floors = []
    for plan in (master.get("floors") or []):
        f = plan.get("floor")
        canonical = per_floor_density.get(f, 0)
        new_v2 = int(new_by_floor.get(str(f), 0))
        floors.append({
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
            "canonical_workers": canonical,
            "new_v2_workers": new_v2,
            "total_workers": canonical + new_v2,
        })

    canon_total = canon.get("total_canonical_workers") or 0
    new_total = new_workers.get("new_worker_count") or 0
    return {
        "ts": route.get("ts"),
        "verified": {
            "canonical_workers_before": canon_total,
            "new_v2_workers": new_total,
            "verified_total_workers": canon_total + new_total,
        },
        "floors": floors,
        "lifts": (lifts.get("lifts") or [])[:9],
        "openclaw": {
            "current_floor": route.get("current_floor"),
            "ticket_count": tickets.get("ticket_count")
                             or len(tickets.get("tickets") or []),
        },
        "trading": {
            "oanda_pnl": {
                "realized": pnl.get("realized_pnl_total"),
                "unrealized": pnl.get("unrealized_pnl_total"),
                "total": pnl.get("total_pnl"),
            },
        },
        "commerce_wing": {
            "floors": commerce.get("departments") or [],
        },
        "safety_locks": {
            "real_money_live_trading_enabled": False,
            "openclaw_real_tool_execution_enabled": False,
            "live_payments_enabled": False,
            "live_listings_publishing_enabled": False,
        },
    }


if __name__ == "__main__":
    snap = build_scene_snapshot()
    print(json.dumps({
        "verified": snap["verified"],
        "floors": len(snap["floors"]),
        "lifts": len(snap["lifts"]),
        "openclaw_floor": snap["openclaw"]["current_floor"],
    }, indent=2))
