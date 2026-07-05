"""
QSB Floor 43 Stocks Department — Phase
QSB_FLOOR_41_42_43_INTERCOM_AND_FLOOR_43_VISIBLE_V1

Mirrors the Floor 42 Binance pattern. Reads existing stock_floor_*
registries and emits:
  - qsb_floor43_stocks_interior.json
  - merges 6 rooms + 8 workers into qsb_worker_room_assignments
  - merges stations into qsb_worker_station_assignments

Safety:
  - stocks_paper_preview_only
  - placement blocked without explicit unlock instruction
  - no real money order placement
"""

from datetime import datetime, timezone
from hashlib import blake2b
from pathlib import Path
import json

ROOT = Path("/vaults/nvme0/qsb_tower_v1")
REG = ROOT / "data/registries"

PHASE = "QSB_FLOOR_41_42_43_INTERCOM_AND_FLOOR_43_VISIBLE_V1"
FLOOR_KEY = "floor_43_stock_exchange"

ROOMS = [
    {"name": "Stock Market Feed Desk",
     "responsibility": "stream equity quotes + bars from data provider"},
    {"name": "Sector Watch Desk",
     "responsibility": "score sector breadth, leadership, momentum"},
    {"name": "Paper Order Desk",
     "responsibility": "format paper orders (live placement blocked)"},
    {"name": "Risk Station",
     "responsibility": "veto orders over caps; kill switch"},
    {"name": "Ledger Dispatch",
     "responsibility": "append every paper order + audit to ledger"},
    {"name": "Compliance Desk",
     "responsibility": "regulatory checks + KYC/AML labels"},
    {"name": "OpenClaw Inspection Post",
     "responsibility": "read-only supervisor checks"},
]

WORKERS = [
    {"worker_id": "f43_floor_manager",     "role": "Stocks Floor Manager",       "room": "Sector Watch Desk"},
    {"worker_id": "f43_market_scout",      "role": "Equity Market Scout",        "room": "Stock Market Feed Desk"},
    {"worker_id": "f43_sector_analyst",    "role": "Sector Breadth Analyst",     "room": "Sector Watch Desk"},
    {"worker_id": "f43_paper_order_clerk", "role": "Paper Order Clerk",          "room": "Paper Order Desk"},
    {"worker_id": "f43_risk_sentinel",     "role": "Risk Sentinel",              "room": "Risk Station"},
    {"worker_id": "f43_ledger_clerk",      "role": "Ledger Dispatch Clerk",      "room": "Ledger Dispatch"},
    {"worker_id": "f43_compliance_clerk",  "role": "Compliance Clerk",           "room": "Compliance Desk"},
    {"worker_id": "f43_openclaw_inspector","role": "OpenClaw Stocks Inspector",  "room": "OpenClaw Inspection Post"},
]


def _now():
    return datetime.now(timezone.utc).isoformat()


def _safety():
    # V17 — paper unlock reflected if qsb_alpaca_paper_unlock.json present
    unlock_p = REG / "qsb_alpaca_paper_unlock.json"
    paper_unlocked = False
    if unlock_p.exists():
        try:
            u = json.loads(unlock_p.read_text(encoding="utf-8"))
            paper_unlocked = bool(u.get("authorized_by"))
        except Exception:
            pass
    return {
        "execution_allowed": False,
        "active_local_only": True,
        "advisory_only": True,
        "stocks_paper_preview_only": not paper_unlocked,
        "stocks_paper_order_placement_enabled": paper_unlocked,
        "real_order_placement_enabled": False,   # live still locked
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
        idx = _stable_idx(w["worker_id"], 12) + 1
        out.append({
            "worker_id": w["worker_id"],
            "role": w["role"],
            "room": w["room"],
            "station": f"{w['room']} · station #{idx:02d}",
            "state": "idle_at_station",
            "current_task": "monitor stocks paper feed (no placement)",
            "stable": True,
            "source": "qsb_floor43_stocks.py",
        })
    return out


def build_interior():
    workers = build_workers_with_stations()

    # Mirror rooms.
    rooms_payload = _load("qsb_worker_room_assignments.json",
                          {"by_floor_room": {}})
    by_floor = rooms_payload.get("by_floor_room") or {}
    if not isinstance(by_floor, dict):
        by_floor = {}
    f43_rooms = {}
    for r in ROOMS:
        f43_rooms[r["name"]] = [w["worker_id"] for w in workers
                                  if w["room"] == r["name"]]
    by_floor[FLOOR_KEY] = f43_rooms
    rooms_payload.update({
        "ok": True,
        "kind": "qsb_worker_room_assignments",
        "generated_ts": _now(),
        "by_floor_room": by_floor,
        "floor_43_stocks_appended": True,
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
            "source": "qsb_floor43_stocks.py",
        }
    stations_payload.update({
        "ok": True,
        "kind": "qsb_worker_station_assignments",
        "generated_ts": _now(),
        "station_count": len(stations),
        "stations": stations,
        "floor_43_stocks_appended": True,
    })
    stations_payload.update(_safety())
    _write(REG / "qsb_worker_station_assignments.json", stations_payload)

    # Pull in existing stock floor telemetry so the panel has live numbers.
    status = _load("stock_floor_status.json", {})
    strategy = _load("stock_paper_strategy_latest.json", {})
    snap = _load("stock_market_snapshot_latest.json", {})

    interior = {
        "ok": True,
        "kind": "qsb_floor43_stocks_interior",
        "phase": PHASE,
        "generated_ts": _now(),
        "floor": 43,
        "department": "Stock Exchange Floor",
        "rooms": ROOMS,
        "workers": workers,
        "policy": {
            "mode": "paper_preview_only",
            "placement": "blocked_without_explicit_unlock",
            "real_money_enabled": False,
        },
        "telemetry": {
            "status_ts": status.get("status_ts"),
            "provider": status.get("provider"),
            "environment": status.get("environment"),
            "market_status": strategy.get("market_status"),
            "default_symbols": strategy.get("default_symbols"),
            "snapshot_ts": snap.get("snapshot_ts"),
            "quotes": (snap.get("quotes") or [])[:8],
            "credentials_state": status.get("credentials") or {},
        },
    }
    interior.update(_safety())
    _write(REG / "qsb_floor43_stocks_interior.json", interior)
    return interior


def main():
    payload = build_interior()
    print(json.dumps({
        "ok": True,
        "phase": PHASE,
        "rooms": len(payload["rooms"]),
        "workers": len(payload["workers"]),
        **_safety(),
    }, indent=2))


if __name__ == "__main__":
    main()
