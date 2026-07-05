"""
QSB Trading Floor Room Assignments — Phase
QSB_RENDER_VISIBLE_WORKERS_AND_LIFTS_FIX_V1

The existing qsb_worker_room_assignments registry covers only admin
floors {30, 36, 38, 44, 45, 47, 49, 52}. Trading floors 41 (OANDA), 42
(Binance), 43 (Stocks) have legacy sandbox workers but no rooms —
which is why clicking those floors shows "no live worker assignments
registered."

This module:
  - takes the legacy sandbox workers (from /api/unified) that belong
    on floors 41/42/43,
  - assigns them DETERMINISTICALLY to rooms via hash(worker_id),
  - merges into qsb_worker_room_assignments.by_floor_room without
    overwriting existing admin-floor rooms,
  - emits qsb_trading_floor_station_assignments.json as the per-floor
    station record.

Stable assignment: room = ROOMS[trading_floor][hash(wid) % len(rooms)].
"""

from datetime import datetime, timezone
from hashlib import blake2b
from pathlib import Path
import json

ROOT = Path("/vaults/nvme0/qsb_tower_v1")
REG = ROOT / "data/registries"
LOGS = ROOT / "data/logs"

PHASE = "QSB_RENDER_VISIBLE_WORKERS_AND_LIFTS_FIX_V1"

# Sandbox seed workers we know belong to trading floors. We also accept
# any worker whose floor/home_floor/floor_id matches 41/42/43.
TRADING_FLOORS = {
    41: "floor_41_oanda_practice",
    42: "floor_42_binance_trading",
    43: "floor_43_stock_exchange",
}

ROOMS_BY_FLOOR = {
    41: ["Quote Desk", "Practice Order Desk", "Risk Review Desk", "Audit Bench"],
    42: ["Testnet Desk", "Order Preview Desk", "Risk Review Desk", "Compliance Desk"],
    43: ["Paper Order Desk", "Sector Watch Desk", "Risk Review Desk", "Compliance Desk"],
}

ROLE_BY_HINT = {
    "scout": "market_scout",
    "executor": "order_handler",
    "risk": "risk_reviewer",
    "audit": "auditor",
    "compliance": "compliance_officer",
    "ledger": "ledger_clerk",
}


def _now():
    return datetime.now(timezone.utc).isoformat()


def _safety():
    return {
        "execution_allowed": False,
        "active_local_only": True,
        "advisory_only": True,
        "read_only": True,
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


def _stable_idx(wid, modulo):
    h = blake2b(wid.encode("utf-8"), digest_size=4).digest()
    return int.from_bytes(h, "big") % modulo


def _floor_of(w):
    if not isinstance(w, dict):
        return None
    raw = (
        w.get("floor")
        or w.get("floor_id")
        or w.get("home_floor")
        or w.get("current_floor")
    )
    if raw is None:
        return None
    try:
        return int(raw)
    except Exception:
        s = str(raw)
        for n in (41, 42, 43):
            if str(n) in s or f"floor_{n}" in s:
                return n
        return None


def _legacy_workers():
    """Pull legacy seed workers from /api/unified-equivalent in-process."""
    try:
        from dashboard import server as _s  # not imported, just for hint
    except Exception:
        pass
    # Easiest path: read the live telemetry workers list.
    workers = []
    try:
        from tower.qsb_dashboard_live_telemetry import build_live_telemetry
        tel = build_live_telemetry()
        workers = tel.get("workers") or []
    except Exception:
        workers = []
    # Add legacy sandbox seeds from qsb_unified or canonical files too.
    for name in ("qsb_canonical_workers.json", "qsb_worker_truth_contract.json"):
        d = _load(name, {})
        ws = d.get("workers") or d.get("canonical_workers") or []
        if isinstance(ws, list):
            workers.extend(ws)
    return workers


def build():
    rooms_payload = _load("qsb_worker_room_assignments.json", {})
    by_floor_room = rooms_payload.get("by_floor_room") or {}
    if not isinstance(by_floor_room, dict):
        by_floor_room = {}

    workers = _legacy_workers()
    seen = set()
    trading_assignments = {41: {}, 42: {}, 43: {}}
    stations = {}

    for w in workers:
        if not isinstance(w, dict):
            continue
        wid = w.get("worker_id") or w.get("id")
        if not wid or wid in seen:
            continue
        floor = _floor_of(w)
        if floor not in TRADING_FLOORS:
            continue
        seen.add(wid)
        rooms = ROOMS_BY_FLOOR[floor]
        room = rooms[_stable_idx(wid, len(rooms))]
        trading_assignments[floor].setdefault(room, []).append(wid)
        # Assign a stable station id.
        station_idx = (_stable_idx(wid, 12) + 1)
        stations[wid] = {
            "floor": TRADING_FLOORS[floor],
            "room": room,
            "station": f"{room} · station #{station_idx:02d}",
            "role": _role_for(w),
            "stable": True,
            "source": "qsb_trading_floor_room_assignments.py",
        }

    # Materialize and merge into by_floor_room.
    for f, rooms in trading_assignments.items():
        key = TRADING_FLOORS[f]
        existing = by_floor_room.get(key, {})
        if not isinstance(existing, dict):
            existing = {}
        for room, wids in rooms.items():
            merged = list(dict.fromkeys((existing.get(room) or []) + wids))
            existing[room] = merged
        by_floor_room[key] = existing

    rooms_payload.update({
        "ok": True,
        "kind": "qsb_worker_room_assignments",
        "generated_ts": _now(),
        "by_floor_room": by_floor_room,
        "trading_floors_appended": True,
        "trading_floors_count": {
            str(f): sum(len(v) for v in rooms.values())
            for f, rooms in trading_assignments.items()
        },
    })
    rooms_payload.update(_safety())
    _write(REG / "qsb_worker_room_assignments.json", rooms_payload)

    # Stations: merge into qsb_worker_station_assignments stations dict
    # without trampling V1 admin-floor assignments.
    stations_payload = _load("qsb_worker_station_assignments.json", {})
    existing_stations = stations_payload.get("stations") or {}
    if not isinstance(existing_stations, dict):
        existing_stations = {}
    for wid, rec in stations.items():
        if wid not in existing_stations:
            existing_stations[wid] = rec
    stations_payload.update({
        "ok": True,
        "kind": "qsb_worker_station_assignments",
        "generated_ts": _now(),
        "station_count": len(existing_stations),
        "stations": existing_stations,
        "trading_floors_appended": True,
    })
    stations_payload.update(_safety())
    _write(REG / "qsb_worker_station_assignments.json", stations_payload)

    out = {
        "ok": True,
        "kind": "qsb_trading_floor_room_assignments",
        "phase": PHASE,
        "generated_ts": _now(),
        "trading_assignments_count": {
            str(f): sum(len(v) for v in rooms.values())
            for f, rooms in trading_assignments.items()
        },
        "total_stations_assigned": len(stations),
    }
    out.update(_safety())
    _write(REG / "qsb_trading_floor_station_assignments.json", out)
    return out


def _role_for(w):
    name = (w.get("name") or w.get("display_name") or "").lower()
    wid = (w.get("worker_id") or w.get("id") or "").lower()
    role_text = (w.get("role") or "").lower()
    bag = f"{name} {wid} {role_text}"
    for hint, role in ROLE_BY_HINT.items():
        if hint in bag:
            return role
    return "trading_floor_operator"


def main():
    payload = build()
    print(json.dumps(payload, indent=2, default=str))


if __name__ == "__main__":
    main()
