#!/usr/bin/env python3
"""qsb_trader_qualifier.py — grade traders + auto-cull duds.

Ross 2026-07-05 #175: "we trade to win not lose" + "intelligent qualified only".

Grades every trader from qsb_trader_pnl_bus_tail.jsonl on:
  · win_rate (>= 55% target)
  · profit_factor (>= 1.3 target)
  · expectancy per trade (positive required)
  · sample size (>= 30 closes required to grade)

Assigns TIER:
  · TIER_1 (green): passes ALL 3 metrics — allowed on real broker
  · TIER_2 (amber): passes 2/3 — paper only, retraining candidate
  · TIER_0 (red): fails 2+ or PnL < -$1 — auto-CULL (paused)

Writes verdict to data/registries/qsb_trader_tiers.json + exposes /tiers on
HQ hub (via read of the JSON).
"""
from __future__ import annotations
import json
from collections import defaultdict
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path("/vaults/nvme0/qsb_tower_v1")
PNL_BUS = ROOT / "data/registries/qsb_trader_pnl_bus_tail.jsonl"
TIER_FILE = ROOT / "data/registries/qsb_trader_tiers.json"

MIN_SAMPLE = 30
WIN_RATE_TARGET = 0.55
PROFIT_FACTOR_TARGET = 1.3

def _utc(): return datetime.now(timezone.utc).isoformat().replace("+00:00","Z")

def grade():
    stats = defaultdict(lambda: {"closes":0,"wins":0,"losses":0,"pnl_sum":0.0,
                                 "gross_win":0.0,"gross_loss":0.0,
                                 "venue":"?","instrument":"?","real":0})
    if not PNL_BUS.exists():
        return {"error":"no pnl_bus"}
    for line in PNL_BUS.read_text(errors="ignore").splitlines():
        try:
            d = json.loads(line)
            wid = d.get("worker_id","?")
            pnl = d.get("pnl",0)
            stats[wid]["closes"] += 1
            stats[wid]["pnl_sum"] += pnl
            stats[wid]["venue"] = d.get("venue","?")
            stats[wid]["instrument"] = d.get("instrument","?")
            if d.get("is_real"): stats[wid]["real"] += 1
            if d.get("won"):
                stats[wid]["wins"] += 1
                stats[wid]["gross_win"] += pnl
            else:
                stats[wid]["losses"] += 1
                stats[wid]["gross_loss"] += abs(min(0, pnl))
        except Exception: pass

    tiers = []
    counts = {"TIER_1":0,"TIER_2":0,"TIER_0":0,"UNRATED":0}
    for wid, s in stats.items():
        entry = {
            "trader_id": wid, "venue": s["venue"], "instrument": s["instrument"],
            "closes": s["closes"], "wins": s["wins"], "losses": s["losses"],
            "pnl_sum": round(s["pnl_sum"], 4),
            "real_closes": s["real"],
        }
        if s["closes"] < MIN_SAMPLE:
            entry["tier"] = "UNRATED"
            entry["reason"] = f"sample {s['closes']} < {MIN_SAMPLE}"
            counts["UNRATED"] += 1
            tiers.append(entry); continue

        win_rate = s["wins"] / s["closes"] if s["closes"] else 0
        pf = (s["gross_win"] / s["gross_loss"]) if s["gross_loss"] > 0 else (999 if s["gross_win"]>0 else 0)
        expectancy = s["pnl_sum"] / s["closes"] if s["closes"] else 0
        entry["win_rate"] = round(win_rate, 3)
        entry["profit_factor"] = round(pf, 3)
        entry["expectancy"] = round(expectancy, 5)

        passes = 0
        if win_rate >= WIN_RATE_TARGET: passes += 1
        if pf >= PROFIT_FACTOR_TARGET: passes += 1
        if expectancy > 0: passes += 1

        if passes == 3 and s["pnl_sum"] > 0:
            entry["tier"] = "TIER_1"
            entry["reason"] = "passes all 3 · positive PnL"
        elif passes >= 2 and s["pnl_sum"] > -1:
            entry["tier"] = "TIER_2"
            entry["reason"] = f"passes {passes}/3 · borderline PnL"
        else:
            entry["tier"] = "TIER_0"
            entry["reason"] = f"passes {passes}/3 · PnL={s['pnl_sum']:.4f} · CULL"
        counts[entry["tier"]] += 1
        tiers.append(entry)

    tiers.sort(key=lambda x: -x.get("pnl_sum",0))
    result = {
        "ts": _utc(),
        "totals": counts,
        "min_sample": MIN_SAMPLE,
        "targets": {"win_rate": WIN_RATE_TARGET, "profit_factor": PROFIT_FACTOR_TARGET, "expectancy": "> 0"},
        "traders": tiers,
    }
    TIER_FILE.parent.mkdir(parents=True, exist_ok=True)
    TIER_FILE.write_text(json.dumps(result, indent=2))
    return result

if __name__ == "__main__":
    r = grade()
    print(f"  totals: {r['totals']}")
    print(f"\n  TIER_1 winners:")
    for t in r["traders"]:
        if t["tier"] == "TIER_1":
            print(f"    {t['trader_id']:35s} @{t['venue']:8s} closes={t['closes']:4d} wr={t.get('win_rate',0)*100:.0f}% PF={t.get('profit_factor',0):.2f} PnL=${t['pnl_sum']:+.4f}")
    print(f"\n  TIER_0 CULL:")
    for t in r["traders"]:
        if t["tier"] == "TIER_0":
            print(f"    {t['trader_id']:35s} @{t['venue']:8s} PnL=${t['pnl_sum']:+.4f} · {t['reason']}")
