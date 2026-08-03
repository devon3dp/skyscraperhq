#!/usr/bin/env python3
"""qsb_teach_from_history.py — teach the belief-driven traders from their REAL
broker history (Ross 2026-07-27: "teach the traders more... how to win, they
have a good history of data now").

Mechanism (uses the tower's OWN learning math — no invented logic):
  For each belief_state_<worker>__<INSTRUMENT>.json whose INSTRUMENT has real
  OANDA fills, seed a neutral strategy_fitness and replay every real fill in
  chronological order through belief_updater_math.update_on_trade_closed().
  The brain's win_rate (EWMA) + expectancy (running mean) + n_trades then match
  broker reality. regime.* is preserved (that's live-tick state, not P/L).

Result: losers (JP225 0/9) collapse below the act-gate; proven-positive-
expectancy engines (EUR_USD, USD_JPY) are recognised.

--apply writes the files; default is dry-run (report only). Reversible via the
cognitive.bak_* snapshot.
"""
import json, sys, glob, os
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parent))
from belief_updater_math import update_on_trade_closed, confidence_to_act  # noqa

ROOT = Path(__file__).resolve().parent.parent
HIST = ROOT / "data/registries/qsb_oanda_history.jsonl"
COG = ROOT / "data/registries/cognitive"

def load_fills():
    """instrument -> chronologically-sorted list of (pnl, won)."""
    rows = {}
    for line in HIST.open():
        try:
            d = json.loads(line)
        except Exception:
            continue
        ins = d.get("instrument")
        pl = d.get("pl", d.get("realizedPL"))
        ts = d.get("time", d.get("ts", ""))
        if not ins or pl in (None, ""):
            continue
        try:
            pl = float(pl)
        except Exception:
            continue
        rows.setdefault(ins, []).append((ts, pl))
    out = {}
    for ins, lst in rows.items():
        lst.sort(key=lambda x: x[0])  # chronological
        out[ins] = [(pl, pl > 0) for _, pl in lst]
    return out

def teach(apply=False):
    fills = load_fills()
    report = []
    for path in sorted(glob.glob(str(COG / "belief_state_*.json"))):
        base = os.path.basename(path)[len("belief_state_"):-len(".json")]
        if "__" not in base:
            continue
        worker, instrument = base.split("__", 1)
        seq = fills.get(instrument)
        if not seq:
            continue  # no real history for this instrument -> leave untouched
        try:
            belief = json.loads(Path(path).read_text())
        except Exception:
            continue
        sf = belief.setdefault("strategy_fitness", {})
        before_wr = sf.get("win_rate")
        before_exp = sf.get("expectancy")
        before_n = sf.get("n_trades")
        act_before, _ = confidence_to_act(belief) if all(
            k in sf for k in ("win_rate", "expectancy", "n_trades")) and "regime" in belief else (None, "")
        # seed neutral prior, then replay reality
        sf["win_rate"], sf["expectancy"], sf["n_trades"] = 0.5, 0.0, 0
        for pnl, won in seq:
            belief = update_on_trade_closed(belief, pnl, won)
        belief.setdefault("regime", {}).setdefault("regime_confidence", 1.0)
        act_after, why = confidence_to_act(belief)
        rec = {
            "worker": worker, "instrument": instrument, "n_fills": len(seq),
            "before": {"win_rate": before_wr, "expectancy": before_exp, "n": before_n, "act": act_before},
            "after": {"win_rate": round(sf["win_rate"], 4),
                      "expectancy": round(sf["expectancy"], 4),
                      "n": sf["n_trades"], "act": act_after, "why": why},
        }
        report.append(rec)
        if apply:
            Path(path).write_text(json.dumps(belief, indent=2))
    return report

def main():
    apply = "--apply" in sys.argv
    report = teach(apply=apply)
    report.sort(key=lambda r: r["after"]["expectancy"])
    mode = "APPLIED" if apply else "DRY-RUN"
    print(f"=== TEACH FROM HISTORY ({mode}) — {len(report)} traders taught from real fills ===")
    print(f"{'instrument':13} {'n':>4} {'win_rate':>9} {'exp/trade':>10}  act?  reason")
    flipped_off, kept_on = [], []
    for r in report:
        a = r["after"]
        flag = "TRADE" if a["act"] else "REFUSE"
        print(f"  {r['instrument']:13} {a['n']:>4} {a['win_rate']:>8.1%} £{a['expectancy']:>8.3f}  {flag:6} {a['why']}")
        (kept_on if a["act"] else flipped_off).append(r["instrument"])
    print(f"\nREFUSE (taught to stop): {', '.join(sorted(set(flipped_off))) or 'none'}")
    print(f"TRADE  (kept/allowed):   {', '.join(sorted(set(kept_on))) or 'none'}")

if __name__ == "__main__":
    main()
