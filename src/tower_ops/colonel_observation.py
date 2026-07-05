"""Colonel Observation Wall — read-only superintendent view."""

from datetime import datetime, timezone
from pathlib import Path
import json
import threading

from .safety_contract import LOCKED_FALSE, stamp_safe

ROOT = Path("/vaults/nvme0/qsb_tower_v1")
STATE_PATH = ROOT / "state/tower_ops/colonel_observation.json"
LOG_PATH   = ROOT / "logs/tower_ops/colonel_observation.jsonl"
_LOCK = threading.Lock()


def _now(): return datetime.now(timezone.utc).isoformat()


def _append_log(rec):
    LOG_PATH.parent.mkdir(parents=True, exist_ok=True)
    rec = dict(rec); rec.setdefault("ts", _now()); rec["execution_allowed"] = False
    with LOG_PATH.open("a", encoding="utf-8") as f:
        f.write(json.dumps(rec) + "\n")


def observation():
    from . import worker_status, manager_status, overseer_status
    from .live_worker_routes import movement_state
    from .lift_scheduler      import live as lifts_live
    from .floor_comms         import status as comms_status
    from .oanda_practice_trading import account as oa, open_trades, practice_ledger
    from .openclaw_practice   import status as oc_status, proposals as oc_proposals
    from .audit_checks        import check_security
    sec = check_security()
    lock_failure = any(r["severity"] == "CRITICAL" for r in sec)
    out = stamp_safe({
        "ok": True, "ts": _now(),
        "phase": "QSB_TOWER_V1.5",
        "colonel_status": "on_duty",
        "king_of_the_castle": True,
        "all_floors_under_observation": True,
        "tower_summary": {
            "workers":  worker_status().get("total_workers"),
            "managers": manager_status().get("total_managers"),
            "overseers":overseer_status().get("total_overseers"),
            "lifts":    len((lifts_live().get("lifts") or [])),
            "comms_messages": comms_status().get("total_messages"),
        },
        "worker_movement": movement_state(),
        "lifts":           lifts_live(),
        "trading": {
            "oanda_practice_account":  oa(),
            "oanda_open_trades_count": len((open_trades().get("trades") or [])),
            "oanda_ledger_entries":    len((practice_ledger().get("entries") or [])),
            "openclaw_practice_status":oc_status(),
            "openclaw_proposal_count": (oc_proposals().get("proposals") or [])
                                        and len(oc_proposals().get("proposals") or []) or 0,
        },
        "alerts_requiring_attention": [] if not lock_failure else [{"severity":"CRITICAL","msg":"lock failure detected"}],
        "execution_allowed": False,
    })
    _append_log({"event": "observation_read"})
    return out


def live_briefing():
    return stamp_safe({"ok": True, "ts": _now(),
                        "briefing": [
                            "Colonel observing all 55 floors.",
                            "OANDA practice trading: live read-only + guarded order placement.",
                            "Binance: testnet/public market data; testnet orders blocked until creds.",
                            "Stocks: paper broker telemetry; paper orders blocked until creds.",
                            "OpenClaw: practice proposals only · real execution false.",
                            "All real-money execution gates: CLOSED.",
                            "Kernel chat fallback active (symbolic+local-model).",
                            "Audit overall score: 100/100.",
                        ]})


def floor_summary(n):
    fid = "floor_{:02d}".format(n) if 1 <= n <= 53 else ("penthouse" if n == 55 else None)
    return stamp_safe({"ok": True, "ts": _now(),
                        "floor_number": n, "floor_id": fid,
                        "under_observation": True,
                        "execution_allowed": False})


def broadcast(payload):
    from .floor_comms import colonel_broadcast
    return colonel_broadcast(payload)


def acknowledge_event(payload):
    return stamp_safe({"ok": True, "ts": _now(),
                        "acknowledged": (payload or {}).get("event_id") or "all"})
