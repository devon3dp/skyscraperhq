"""V2.0 autonomous OANDA practice — operator-controlled auto-mode with caps.

This module ONLY wraps the existing oanda_practice_trading guardrails.
auto_practice_allowed defaults to False. Real-money trading remains hard-off
regardless of every flag here.
"""

from datetime import datetime, timezone
from pathlib import Path
import json

from .safety_contract import stamp_safe


ROOT = Path("/vaults/nvme0/qsb_tower_v1")
STATE_PATH = ROOT / "state/tower_ops/autonomous_oanda_practice.json"
LOG_PATH = ROOT / "logs/tower_ops/autonomous_oanda_practice.jsonl"


# V2.0 autonomy caps — applied IN ADDITION to the V1.5 guardrails.
AUTONOMY_CAPS = {
    "max_units_per_trade": 100,
    "max_open_trades": 3,
    "max_trades_per_hour": 3,
    "max_daily_practice_loss": 200,
    "max_spread_pips": 2.0,
    "manager_approved_required": True,
    "risk_approved_required": True,
    "accounts_approved_required": True,
    "kill_switch_required_false": True,
}


def _now(): return datetime.now(timezone.utc).isoformat()


def _ensure():
    STATE_PATH.parent.mkdir(parents=True, exist_ok=True)
    LOG_PATH.parent.mkdir(parents=True, exist_ok=True)
    if not STATE_PATH.exists():
        STATE_PATH.write_text(json.dumps({
            "auto_practice_allowed": False,
            "manual_confirm_required": True,
            "kill_switch": False,
            "last_change_ts": _now(),
        }, indent=2))


def _load():
    _ensure()
    try: return json.loads(STATE_PATH.read_text())
    except Exception: return {"auto_practice_allowed": False,
                                "manual_confirm_required": True,
                                "kill_switch": False}


def _save(d):
    d["last_change_ts"] = _now()
    STATE_PATH.write_text(json.dumps(d, indent=2))


def _log(rec):
    _ensure()
    with LOG_PATH.open("a", encoding="utf-8") as f:
        f.write(json.dumps({**rec, "ts": _now()}) + "\n")


def status():
    s = _load()
    return stamp_safe({
        "ok": True, "ts": _now(),
        "label": "AUTONOMOUS_OANDA_PRACTICE_STATUS",
        "OANDA_ENV": "practice",
        "auto_practice_allowed": bool(s.get("auto_practice_allowed")),
        "manual_confirm_required": bool(s.get("manual_confirm_required", True)),
        "kill_switch": bool(s.get("kill_switch", False)),
        "caps": AUTONOMY_CAPS,
        "real_order_execution_enabled": False,
        "binance_order_execution_enabled": False,
        "stock_order_execution_enabled": False,
        "openclaw_execution_enabled": False,
        "live_trading_enabled": False,
        "execution_allowed": False,
    })


def enable_auto_practice(payload):
    payload = payload or {}
    confirm = payload.get("confirm") == "I_UNDERSTAND_OANDA_PRACTICE_ONLY"
    if not confirm:
        return {"ok": False, "error": "explicit_confirmation_required",
                "required_confirm_token": "I_UNDERSTAND_OANDA_PRACTICE_ONLY"}
    s = _load()
    s["auto_practice_allowed"] = True
    s["manual_confirm_required"] = bool(payload.get("manual_confirm_required", False))
    _save(s)
    _log({"event": "enable_auto_practice", "by": payload.get("by") or "operator"})
    return stamp_safe({"ok": True, **status(), "execution_allowed": False})


def pause_auto_practice(payload=None):
    s = _load(); s["auto_practice_allowed"] = False; _save(s)
    _log({"event": "pause_auto_practice"})
    return stamp_safe({"ok": True, **status(), "execution_allowed": False})


def emergency_stop(payload=None):
    s = _load()
    s["kill_switch"] = True
    s["auto_practice_allowed"] = False
    _save(s)
    _log({"event": "emergency_stop"})
    # Also trip the V1.5 oanda practice kill_switch
    try:
        from .oanda_practice_trading import kill_switch as _ks
        _ks({"action": "engage"})
    except Exception:
        pass
    return stamp_safe({"ok": True, "ts": _now(),
                        "label": "AUTONOMOUS_OANDA_PRACTICE_EMERGENCY_STOP",
                        "kill_switch": True,
                        "auto_practice_allowed": False,
                        "execution_allowed": False})


def close_all_practice_trades(payload=None):
    closed = []; failed = []
    try:
        from .oanda_practice_trading import open_trades, close_practice_trade
        trades = (open_trades().get("trades") or [])
        for t in trades:
            tid = t.get("id") or t.get("trade_id")
            if not tid: continue
            r = close_practice_trade({"trade_id": tid,
                                       "confirm": "I_UNDERSTAND_OANDA_PRACTICE_ONLY"})
            if r.get("ok"): closed.append(tid)
            else: failed.append({"trade_id": tid, "reason": r.get("error") or r.get("reason")})
    except Exception as e:
        return {"ok": False, "error": str(e)[:200]}
    _log({"event": "close_all_practice_trades",
           "closed_count": len(closed), "failed_count": len(failed)})
    return stamp_safe({"ok": True, "ts": _now(),
                        "label": "CLOSE_ALL_OANDA_PRACTICE_TRADES",
                        "closed_trade_ids": closed,
                        "failed_trades": failed,
                        "execution_allowed": False})
