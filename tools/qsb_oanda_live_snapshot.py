#!/usr/bin/env python3
"""qsb_oanda_live_snapshot.py — write a LIVE OANDA account snapshot for the dash.

Queries the practice account (balance, NAV, unrealized P/L, open counts) and
writes data/registries/qsb_oanda_live.json. Run on a short timer so the dash
shows real-time results (NAV moving) between realized closes. READ-ONLY.
"""
import json, sys, time
from pathlib import Path
ROOT = Path("/vaults/nvme0/qsb_tower_v1")
sys.path.insert(0, str(ROOT / "src"))
OUT = ROOT / "data/registries/qsb_oanda_live.json"


def snap():
    from tower_ops.oanda_practice_trading import account
    a = account() or {}
    if not a.get("ok"):
        return {"ok": False, "reason": a.get("reason", a.get("status", "?")),
                "ts": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())}
    def f(x):
        try:
            return round(float(x), 2)
        except Exception:
            return None
    return {"ok": True, "ts": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
            "balance": f(a.get("balance")), "NAV": f(a.get("NAV")),
            "unrealized_pl": f(a.get("unrealized_pl")),
            "realized_pl_today": f(a.get("realized_pl_today")),
            "margin_used": f(a.get("margin_used")),
            "margin_available": f(a.get("margin_available")),
            "open_trades": a.get("open_trade_count"),
            "open_positions": a.get("open_position_count"),
            "currency": a.get("currency")}


if __name__ == "__main__":
    r = snap()
    OUT.write_text(json.dumps(r, indent=1))
    print(json.dumps(r))
