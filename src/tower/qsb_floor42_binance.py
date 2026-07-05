"""
QSB Floor 42 Binance Department & Workers
Phase: QSB_DASHBOARD_VISIBLE_REALITY_REBUILD_V1

Emits a proper Floor 42 Binance interior so that selecting Floor 42 in
the cockpit shows real rooms + workers, not just two sandbox scouts.

Safety:
  - No live order placement.
  - testnet preview only.
  - Mirrors the same room/worker dictionary into
    qsb_worker_room_assignments + qsb_worker_station_assignments so the
    Floor inspector built earlier also picks them up.
"""

from datetime import datetime, timezone
from hashlib import blake2b
from pathlib import Path
import json

ROOT = Path("/vaults/nvme0/qsb_tower_v1")
REG = ROOT / "data/registries"

PHASE = "QSB_DASHBOARD_VISIBLE_REALITY_REBUILD_V1"

ROOMS = [
    {"name": "Binance Testnet Feed Desk",
     "responsibility": "stream testnet ticker + order book"},
    {"name": "Strategy Desk",
     "responsibility": "score testnet candidates, score against risk caps"},
    {"name": "Order Preview Desk",
     "responsibility": "format previewed orders (placement blocked)"},
    {"name": "Risk Station",
     "responsibility": "veto previews over caps; guard kill switch"},
    {"name": "Ledger Dispatch",
     "responsibility": "append every preview + audit to ledger"},
    {"name": "OpenClaw Inspection Post",
     "responsibility": "read-only supervisor checks"},
]

WORKERS = [
    {"worker_id": "f42_floor_manager",      "role": "Binance Floor Manager",     "room": "Strategy Desk"},
    {"worker_id": "f42_testnet_scout",      "role": "Testnet Market Scout",      "room": "Binance Testnet Feed Desk"},
    {"worker_id": "f42_orderbook_watcher",  "role": "Order Book Watcher",        "room": "Binance Testnet Feed Desk"},
    {"worker_id": "f42_strategy_analyst",   "role": "Strategy Analyst",          "room": "Strategy Desk"},
    {"worker_id": "f42_order_preview_clerk","role": "Order Preview Clerk",        "room": "Order Preview Desk"},
    {"worker_id": "f42_risk_sentinel",      "role": "Risk Sentinel",              "room": "Risk Station"},
    {"worker_id": "f42_ledger_clerk",       "role": "Ledger Dispatch Clerk",      "room": "Ledger Dispatch"},
    {"worker_id": "f42_openclaw_inspector", "role": "OpenClaw Binance Inspector", "room": "OpenClaw Inspection Post"},
]

FLOOR_KEY = "floor_42_binance_trading"


def _now():
    return datetime.now(timezone.utc).isoformat()


def _safety():
    # Tier B unlock (Ross, 2026-06-10): binance TESTNET (fake-money) placement
    # is now permitted so workers can actually place orders on the testnet API.
    # Real-money / live-money flags stay False — CLAUDE.md V1.5 forbids those.
    return {
        "execution_allowed": False,
        "active_local_only": True,
        "advisory_only": True,
        "binance_real_order_execution_enabled": False,
        "binance_testnet_placement_enabled": True,
        "real_money_live_trading_enabled": False,
        "openclaw_real_tool_execution_enabled": False,
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


def _stable_idx(seed, modulo):
    return int.from_bytes(
        blake2b(str(seed).encode("utf-8"), digest_size=4).digest(), "big"
    ) % modulo if modulo else 0


def build_workers_with_stations():
    out = []
    for w in WORKERS:
        station_idx = _stable_idx(w["worker_id"], 12) + 1
        station = f"{w['room']} · station #{station_idx:02d}"
        out.append({
            "worker_id": w["worker_id"],
            "role": w["role"],
            "room": w["room"],
            "station": station,
            "state": "idle_at_station",
            "current_task": "monitor testnet feed (no placement)",
            "stable": True,
            "source": "qsb_floor42_binance.py",
        })
    return out


def build_floor42_interior():
    workers = build_workers_with_stations()
    # Mirror into the floor inspector's source.
    rooms_payload = _load("qsb_worker_room_assignments.json", {"by_floor_room": {}})
    by_floor = rooms_payload.get("by_floor_room") or {}
    if not isinstance(by_floor, dict):
        by_floor = {}
    f42_rooms = {}
    for r in ROOMS:
        f42_rooms[r["name"]] = [w["worker_id"] for w in workers if w["room"] == r["name"]]
    by_floor[FLOOR_KEY] = f42_rooms
    rooms_payload.update({
        "ok": True,
        "kind": "qsb_worker_room_assignments",
        "generated_ts": _now(),
        "by_floor_room": by_floor,
        "floor_42_binance_appended": True,
    })
    rooms_payload.update(_safety())
    _write(REG / "qsb_worker_room_assignments.json", rooms_payload)

    # Mirror stations.
    stations_payload = _load("qsb_worker_station_assignments.json",
                             {"stations": {}, "station_count": 0})
    stations = stations_payload.get("stations") or {}
    if not isinstance(stations, dict):
        stations = {}
    for w in workers:
        stations[w["worker_id"]] = {
            "floor": FLOOR_KEY,
            "room": w["room"],
            "station": w["station"],
            "role": w["role"],
            "stable": True,
            "source": "qsb_floor42_binance.py",
        }
    stations_payload.update({
        "ok": True,
        "kind": "qsb_worker_station_assignments",
        "generated_ts": _now(),
        "station_count": len(stations),
        "stations": stations,
        "floor_42_binance_appended": True,
    })
    stations_payload.update(_safety())
    _write(REG / "qsb_worker_station_assignments.json", stations_payload)

    interior = {
        "ok": True,
        "kind": "qsb_floor42_binance_interior",
        "phase": PHASE,
        "generated_ts": _now(),
        "floor": 42,
        "department": "Binance Trading Floor",
        "rooms": ROOMS,
        "workers": workers,
        "policy": {
            "mode": "testnet_preview_only",
            "placement": "blocked_without_explicit_unlock",
            "real_money_enabled": False,
        },
    }
    interior.update(_safety())
    _write(REG / "qsb_floor42_binance_interior.json", interior)
    return interior


def main():
    payload = build_floor42_interior()
    print(json.dumps({
        "ok": True,
        "phase": PHASE,
        "rooms": len(payload["rooms"]),
        "workers": len(payload["workers"]),
        **_safety(),
    }, indent=2))


if __name__ == "__main__":
    main()
