#!/usr/bin/env python3
"""qsb_take_profit_sweep.py — bank big unrealized winners automatically.

Ross 2026-07-27: "add an automatic take-profit sweep so big unrealized winners
get banked instead of sitting." Lesson learned: the JP225 short sat at +£5,580
unrealized for days and could have evaporated; banking it flipped the realized
book from -£1,635 to +£4,020.

WHAT IT DOES (every run): reads live OANDA open trades; for any trade whose
unrealized P/L is >= take_profit_gbp it BANKS it (direct practice close), and
(if stop_loss_gbp is set) cuts any trade bleeding past it. Small scalp positions
(a few £) are LEFT to the belief fleet's own exit logic — the thresholds are set
well above scalp scope so the sweep only touches big, unmanaged winners/losers.

SAFE: PRACTICE_ONLY, respects the OANDA kill-switch (close_practice_trade does),
only ever CLOSES (never opens), and obeys its own gate file. Every bank is
audited. Real-money stays locked.
"""
import sys, json, time
from pathlib import Path
ROOT = Path("/vaults/nvme0/qsb_tower_v1")
sys.path.insert(0, str(ROOT / "src"))
GATE = ROOT / "data/registries/qsb_take_profit_sweep_gate.json"
AUDIT = ROOT / "data/registries/qsb_take_profit_sweep_audit.jsonl"

DEFAULT_GATE = {"enabled": True, "take_profit_gbp": 25.0, "stop_loss_gbp": -20.0,
                "comment": "bank winners >= take_profit_gbp; cut losers <= stop_loss_gbp (null disables). Scalp-sized positions left to the fleet."}


def _gate():
    try:
        g = json.loads(GATE.read_text())
    except Exception:
        g = dict(DEFAULT_GATE)
        GATE.write_text(json.dumps(g, indent=1))
    return g


def _now():
    return time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())


def sweep():
    g = _gate()
    if not g.get("enabled", True):
        return {"ok": True, "skipped": "gate_disabled"}
    tp = g.get("take_profit_gbp", 25.0)
    sl = g.get("stop_loss_gbp", None)
    import tower_ops.oanda_practice_trading as O
    O._load_oanda_env()
    trades = (O.open_trades() or {}).get("trades") or []
    banked, cut = [], []
    for t in trades:
        tid = str(t.get("id"))
        try:
            upl = float(t.get("unrealizedPL"))
        except Exception:
            continue
        inst = t.get("instrument")
        if tp is not None and upl >= tp:
            action, bucket = "take_profit", banked
        elif sl is not None and upl <= sl:
            action, bucket = "stop_loss", cut
        else:
            continue
        r = O.close_practice_trade({"trade_id": tid})
        if r.get("ok"):
            fill = (r.get("oanda_response") or {}).get("orderFillTransaction") or {}
            realized = fill.get("pl")
            rec = {"ts": _now(), "action": action, "trade_id": tid,
                   "instrument": inst, "unrealized_at_close": round(upl, 2),
                   "realized": realized}
            bucket.append(rec)
            with open(AUDIT, "a") as f:
                f.write(json.dumps(rec) + "\n")
        else:
            # kill-switch or error — stop trying this run
            if r.get("blocked"):
                return {"ok": False, "blocked": r.get("reason"), "banked": banked, "cut": cut}
    total = round(sum(float(b["realized"] or 0) for b in banked) +
                  sum(float(c["realized"] or 0) for c in cut), 2)
    return {"ok": True, "ts": _now(), "banked": len(banked), "cut": len(cut),
            "realized_gbp": total, "take_profit_gbp": tp, "stop_loss_gbp": sl,
            "detail": banked + cut}


if __name__ == "__main__":
    print(json.dumps(sweep(), indent=1))
