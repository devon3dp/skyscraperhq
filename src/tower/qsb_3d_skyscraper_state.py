"""
QSB 3D Skyscraper Live State Aggregator
Phase: QSB_3D_SKYSCRAPER_LIVE_REBUILD_V2

Single endpoint payload that the 3D V2 frontend can poll. Aggregates:
  - lift_scene_state          (9 lifts → animated cars)
  - worker_scene_state        (per-floor density → floor glow)
  - openclaw route            (current floor → orbital marker)
  - eqsb_cadence_state        (tick → cadence pulse)
  - floor41 pnl               (open trades → trading floor glow)
  - intercom packets          (recent flashes between floors)

Reads only. Stamps safety envelope on every payload.
"""

from datetime import datetime, timezone
from pathlib import Path
import json

ROOT = Path("/vaults/nvme0/qsb_tower_v1")
REG = ROOT / "data/registries"

PHASE = "QSB_3D_SKYSCRAPER_LIVE_REBUILD_V2"


def _now():
    return datetime.now(timezone.utc).isoformat()


def _safety():
    return {
        "execution_allowed": False,
        "active_local_only": True,
        "advisory_only": True,
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


def build():
    lifts = _load("qsb_lift_scene_state.json", {})
    workers = _load("qsb_worker_scene_state.json", {})
    route = _load("qsb_openclaw_route.json", {})
    cadence = _load("eqsb_cadence_state.json", {})
    pnl = _load("qsb_floor41_oanda_pnl.json", {})
    intercom = _load("qsb_floor_intercom_packets_latest.json", {})

    # Reduce per_floor → just what 3D needs
    per_floor = []
    for r in workers.get("per_floor", [])[:60]:
        per_floor.append({
            "floor": r.get("floor"),
            "total": r.get("total", 0),
            "ops": (r.get("classes") or {}).get("operational_worker", 0),
            "tr": ((r.get("classes") or {}).get("training_worker", 0)
                   + (r.get("classes") or {}).get("candidate_worker", 0)),
            "rest": (r.get("classes") or {}).get("resting_worker", 0),
        })

    # Map lifts → animation-ready records
    lift_records = []
    for L in lifts.get("lifts", [])[:9]:
        lift_records.append({
            "lift_id": L.get("lift_id"),
            "type": L.get("type"),
            "current_floor": L.get("current_floor"),
            "target_floor": L.get("target_floor"),
            "moving": L.get("moving", False),
            "is_idle": L.get("is_idle", True),
            "status": L.get("status", "online"),
            "serves_min": min([f for f in (
                _serves_to_numbers(L.get("serves") or []))], default=0),
            "serves_max": max([f for f in (
                _serves_to_numbers(L.get("serves") or []))], default=53),
        })

    # Intercom flashes: recent packets in transit
    flashes = []
    for p in (intercom.get("packets") or [])[-10:]:
        src = p.get("from_floor", "")
        dst = p.get("to_floor", "")
        flashes.append({
            "from_floor": _floor_num(src),
            "to_floor": _floor_num(dst),
            "lift": p.get("lift"),
            "kind": p.get("kind"),
            "ts": p.get("ts"),
        })

    payload = {
        "ok": True,
        "kind": "qsb_3d_skyscraper_state",
        "phase": PHASE,
        "generated_ts": _now(),
        "lifts": lift_records,
        "lift_count": len(lift_records),
        "per_floor": per_floor,
        "canonical_workers": workers.get("canonical_total", 0),
        "openclaw_current_floor": route.get("current_floor"),
        "openclaw_advanced_by": route.get("advanced_by"),
        "cadence_tick": cadence.get("tick_count", 0),
        "cadence_last_ts": cadence.get("last_tick_ts"),
        "trading_pnl": {
            "realized": pnl.get("realized_pnl_total"),
            "unrealized": pnl.get("unrealized_pnl_total"),
            "total": pnl.get("total_pnl"),
        },
        "intercom_flashes": flashes,
    }
    payload.update(_safety())
    p = REG / "qsb_3d_skyscraper_state.json"
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(json.dumps(payload, indent=2, default=str), encoding="utf-8")
    return payload


def _serves_to_numbers(serves):
    nums = []
    for s in serves or []:
        if not isinstance(s, str):
            continue
        if s == "ground":
            nums.append(0)
        elif s == "roof":
            nums.append(54)
        elif s.startswith("floor_"):
            try:
                nums.append(int(s.split("_")[1]))
            except Exception:
                pass
    return nums


def _floor_num(key):
    if not isinstance(key, str):
        return None
    if key.startswith("floor_"):
        try:
            return int(key.split("_")[1])
        except Exception:
            return None
    return None


def main():
    payload = build()
    print(json.dumps({
        "ok": True,
        "lifts": payload.get("lift_count"),
        "openclaw_floor": payload.get("openclaw_current_floor"),
        "cadence_tick": payload.get("cadence_tick"),
        "intercom_flashes": len(payload.get("intercom_flashes", [])),
    }, indent=2))


if __name__ == "__main__":
    main()
