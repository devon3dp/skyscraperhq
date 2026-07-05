#!/usr/bin/env python3
"""
QSB Trading Intelligence — HQ-side compute.

Reads the per-worker cognitive belief states + the PnL bus + paused-workers
registry and writes a compact trading-intelligence summary for the ThinkPad
tower dashboard.

Output:  data/registries/qsb_trading_intelligence.json
Shape:   {"generated_at","fleet","top_traders","worst_traders","regime","venues"}

Stdlib only. Fully defensive: every source is optional; a missing/garbled file
degrades gracefully rather than crashing. Designed to be run once per sync.
"""
import json, glob, os, math
from pathlib import Path
from datetime import datetime, timezone

ROOT = Path(__file__).resolve().parent.parent   # /vaults/nvme0/qsb_tower_v1
REG  = ROOT / "data" / "registries"
COG  = REG / "cognitive"
OUT  = REG / "qsb_trading_intelligence.json"

# Short venue token -> friendly canonical label (mirrors floor_feed's map).
VENUE_LABEL = {
    "binance": "binance_testnet",
    "binance_testnet": "binance_testnet",
    "oanda": "oanda_practice",
    "oanda_practice": "oanda_practice",
    "alpaca": "alpaca_paper",
    "alpaca_paper": "alpaca_paper",
}

# mean_retreat magnitude above which a worker is judged "trending" (mean_retreat
# is an already-normalised retreat ratio, so this is comparable across
# instruments regardless of raw price scale).
TREND_MEAN_RETREAT = 0.01


def _load(path, default=None):
    try:
        return json.loads(Path(path).read_text())
    except Exception:
        return default


def _num(x, d=0.0):
    try:
        v = float(x)
        if math.isnan(v) or math.isinf(v):
            return d
        return v
    except Exception:
        return d


def main():
    # ---- paused / benched workers -------------------------------------------
    paused = _load(REG / "qsb_paused_workers.json", {}) or {}
    paused_set = set(paused.keys()) if isinstance(paused, dict) else set()

    # ---- pnl bus ------------------------------------------------------------
    bus = _load(REG / "qsb_trader_pnl_bus_latest.json", {}) or {}
    by_worker_pnl = bus.get("by_worker", {}) if isinstance(bus, dict) else {}
    by_venue      = bus.get("by_venue", {}) if isinstance(bus, dict) else {}
    totals        = bus.get("totals", {}) if isinstance(bus, dict) else {}

    pnl_of = {}
    for w, rec in by_worker_pnl.items():
        if isinstance(rec, dict):
            pnl_of[w] = _num(rec.get("pnl_sum"))

    # ---- portfolio pot (open position count) --------------------------------
    pot = _load(REG / "qsb_portfolio_pot.json", {}) or {}
    open_positions = 0
    if isinstance(pot, dict):
        op = pot.get("open_positions")
        if isinstance(op, (dict, list)):
            open_positions = len(op)
        else:
            open_positions = int(_num(op, 0))

    # ---- cognitive belief states -> per-worker aggregates -------------------
    # Each file is belief_state_<worker>__<instrument>.json. A worker may have
    # several instruments; aggregate trade counts and trade-weight the rates.
    agg = {}          # worker -> {"trades","wins","exp_w","files"}
    regime = {"trending": 0, "flat": 0, "total": 0}

    for fp in glob.glob(str(COG / "belief_state_*.json")):
        d = _load(fp)
        if not isinstance(d, dict):
            continue
        stem = os.path.basename(fp)[len("belief_state_"):].rsplit(".json", 1)[0]
        worker = stem.split("__", 1)[0]

        fit = d.get("strategy_fitness", {}) if isinstance(d.get("strategy_fitness"), dict) else {}
        reg = d.get("regime", {}) if isinstance(d.get("regime"), dict) else {}
        wr  = _num(fit.get("win_rate"))
        n   = int(_num(fit.get("n_trades")))
        exp = _num(fit.get("expectancy"))

        a = agg.setdefault(worker, {"trades": 0, "wins": 0, "exp_w": 0.0, "files": 0})
        a["files"] += 1
        if n > 0:
            wins = int(round(wr * n))
            a["trades"] += n
            a["wins"]   += wins
            a["exp_w"]  += exp * n

        # regime classification (per belief file with data)
        mr = abs(_num(reg.get("mean_retreat")))
        if n > 0 or d.get("stream_evidence"):
            regime["total"] += 1
            if mr >= TREND_MEAN_RETREAT:
                regime["trending"] += 1
            else:
                regime["flat"] += 1

    # ---- build per-worker rows ---------------------------------------------
    rows = []
    fleet_wins = 0
    fleet_trades = 0
    fleet_exp_w = 0.0
    for worker, a in agg.items():
        n = a["trades"]
        fleet_trades += n
        fleet_wins   += a["wins"]
        fleet_exp_w  += a["exp_w"]
        if n <= 0:
            continue
        wr_pct = 100.0 * a["wins"] / n
        exp    = a["exp_w"] / n
        rows.append({
            "name": worker,
            "win_rate_pct": round(wr_pct, 1),
            "expectancy": exp,
            "pnl_gbp": round(pnl_of.get(worker, 0.0), 4),
            "n_trades": n,
        })

    # benched duds: paused OR (traded but never won)
    zero_win = {r["name"] for r in rows if r["win_rate_pct"] == 0.0 and r["n_trades"] > 0}
    benched_duds = len(paused_set | zero_win)

    # top / worst by expectancy then win_rate
    ranked = sorted(rows, key=lambda r: (r["expectancy"], r["win_rate_pct"]), reverse=True)

    def _slim(r):
        return {
            "name": r["name"],
            "win_rate_pct": r["win_rate_pct"],
            "expectancy": r["expectancy"],
            "pnl_gbp": r["pnl_gbp"],
        }

    top_traders   = [_slim(r) for r in ranked[:6]]
    worst_traders = [_slim(r) for r in list(reversed(ranked))[:6]]

    # ---- fleet --------------------------------------------------------------
    fleet_wr  = (100.0 * fleet_wins / fleet_trades) if fleet_trades else 0.0
    fleet_exp = (fleet_exp_w / fleet_trades) if fleet_trades else 0.0
    session_pnl = _num(totals.get("pnl_sum")) if isinstance(totals, dict) else 0.0

    fleet = {
        "win_rate_pct": round(fleet_wr, 1),
        "expectancy": fleet_exp,
        "total_trades": int(fleet_trades),
        "open_positions": int(open_positions),
        "benched_duds": int(benched_duds),
        "session_pnl_gbp": round(session_pnl, 2),
    }

    # ---- venues -------------------------------------------------------------
    venues = []
    if isinstance(by_venue, dict):
        for vk, rec in by_venue.items():
            if not isinstance(rec, dict):
                continue
            label = VENUE_LABEL.get(vk, vk)
            closes = int(_num(rec.get("closes")))
            wins   = int(_num(rec.get("wins")))
            wr_pct = (100.0 * wins / closes) if closes else 0.0
            venues.append({
                "venue": label,
                "pnl_gbp": round(_num(rec.get("pnl_sum")), 4),
                "trades": closes,
                "win_rate_pct": round(wr_pct, 1),
            })
    venues.sort(key=lambda v: v["pnl_gbp"], reverse=True)

    out = {
        "generated_at": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
        "fleet": fleet,
        "top_traders": top_traders,
        "worst_traders": worst_traders,
        "regime": regime,
        "venues": venues,
    }

    tmp = OUT.with_suffix(".json.tmp")
    tmp.write_text(json.dumps(out, indent=2))
    os.replace(tmp, OUT)
    print(json.dumps(out, indent=2))


if __name__ == "__main__":
    try:
        main()
    except Exception as e:
        # never leave the pipeline broken; emit an empty-but-valid file
        try:
            OUT.write_text(json.dumps({"error": str(e)}))
        except Exception:
            pass
        print("ERROR:", e)
