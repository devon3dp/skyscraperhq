#!/usr/bin/env python3
"""qsb_pot_broker_reconcile.py — keep the portfolio pot in sync with OANDA broker truth.

WHY: positions close two ways — (1) the trader calls _close_position (now releases
the pot via release-on-close), and (2) OANDA auto-closes on the broker-side
stop/take-profit the trader set at open. Path (2) never notifies the trader, so
those positions linger in the pot as ORPHANS and clog the currency caps
(ccy_cap_USD jammed the winners repeatedly). This job removes any oanda_practice
pot position whose id is NOT in the broker's live open-trade set.

SAFE: data-only. It sends ZERO broker orders — it only deletes stale pot entries
for positions the broker already reports as closed. Non-OANDA venues (alpaca /
binance) are left untouched (this tool can only verify OANDA truth).

Run once (cron/timer) or --loop. --dry-run prints without writing.
"""
import json, subprocess, re, sys, time, argparse
from pathlib import Path

ROOT = Path("/vaults/nvme0/qsb_tower_v1")
POT = ROOT / "data/registries/qsb_portfolio_pot.json"
AUDIT = ROOT / "data/registries/qsb_pot_broker_reconcile_audit.jsonl"


def broker_open_ids() -> set:
    out = subprocess.run(["python3", str(ROOT / "tools/qsb_oanda.py"), "open"],
                         capture_output=True, text=True, timeout=40).stdout
    return set(re.findall(r"id=(\S+)", out))


def reconcile_once(dry=False) -> dict:
    try:
        bids = broker_open_ids()
    except Exception as e:
        return {"ok": False, "error": str(e)[:80]}
    if not bids:
        # never trust an empty broker read (transient API error) — refuse to wipe the pot
        return {"ok": False, "error": "broker returned no open ids — skipping (safety)"}
    pot = json.loads(POT.read_text())
    op = pot.get("open_positions", {})
    orphans = [(pid, p.get("instrument"), float(p.get("notional_gbp", 0)))
               for pid, p in op.items()
               if p.get("venue") == "oanda_practice" and pid not in bids]
    freed = round(sum(n for _, _, n in orphans), 2)
    if orphans and not dry:
        for pid, _, _ in orphans:
            op.pop(pid, None)
        pot["committed_gbp"] = round(sum(float(p.get("notional_gbp", 0)) for p in op.values()), 2)
        # Rebuild by_venue from the SURVIVING positions on every reconcile. The old
        # code only recomputed committed_gbp and left by_venue untouched, so each
        # orphan removal leaked its notional into by_venue permanently (drifted to
        # +£19k on oanda_practice by 2026-07-30). Recomputing here is self-healing:
        # it also corrects any pre-existing drift on the next tick. (2026-07-30 fix)
        by_venue = {}
        for p in op.values():
            ven = p.get("venue", "?")
            by_venue[ven] = round(by_venue.get(ven, 0.0) + float(p.get("notional_gbp", 0) or 0), 2)
        pot["by_venue"] = by_venue
        pot["released_count"] = pot.get("released_count", 0) + len(orphans)
        POT.write_text(json.dumps(pot, indent=1))
        try:
            with open(AUDIT, "a") as f:
                f.write(json.dumps({"ts": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
                                    "removed": len(orphans), "freed_gbp": freed,
                                    "ids": [pid for pid, _, _ in orphans]}) + "\n")
        except Exception:
            pass
    return {"ok": True, "orphans_removed": len(orphans), "freed_gbp": freed,
            "broker_open": len(bids), "pot_open_after": len(op),
            "detail": [f"{i}:{ins}:£{n:.0f}" for i, ins, n in orphans]}


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--dry-run", action="store_true")
    ap.add_argument("--loop", action="store_true", help="run forever")
    ap.add_argument("--interval", type=int, default=120)
    a = ap.parse_args()
    while True:
        r = reconcile_once(dry=a.dry_run)
        print(json.dumps(r))
        if not a.loop:
            break
        time.sleep(a.interval)


if __name__ == "__main__":
    main()
