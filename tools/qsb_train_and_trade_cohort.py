#!/usr/bin/env python3
"""qsb_train_and_trade_cohort.py — train + certify + first-trade a worker cohort.

Picks N uncertified workers, runs them through classroom.run_full_test() for a
named instrument, stamps "certified" for passers, then has each certified
worker place ONE small paper trade on the named venue.

  python3 tools/qsb_train_and_trade_cohort.py \
      --cohort 10 --instrument EUR_USD --venue oanda_practice --units 100

Safety:
  · only paper / practice / testnet venues are dispatched here
  · the certified-worker gate is the only path that can trade real OANDA practice
  · Binance testnet placement is gated by binance_testnet_placement_enabled (Tier B)
  · Alpaca paper placement is gated by stock_paper_order_execution_enabled (Tier B)
  · no real-money venues are reachable from this tool by design

Cohort selection:
  · pulls uncertified workers from qsb_wren_team_roster.json first (Wren team),
    falls back to qsb_canonical_workers.json. Workers must be in 'employed' status.
"""

from __future__ import annotations
import argparse, datetime, json, sys
from pathlib import Path

ROOT = Path("/vaults/nvme0/qsb_tower_v1")
sys.path.insert(0, str(ROOT / "src"))
REG = ROOT / "data/registries"

from tower.cognitive_kernel.classroom import classroom
from tower.cognitive_kernel.worker_certification import worker_certification

# Add tools/ to path so we can import qsb_risk_cap as a sibling tool.
sys.path.insert(0, str(ROOT / "tools"))
from qsb_risk_cap import check_gbp_cap, GBP_CAP_PER_TRADE   # noqa: E402

STRATEGY_LIBRARY_PATH = REG / "qsb_wren_strategy_library.json"


def load_strategy(strategy_id: str) -> dict:
    lib = json.loads(STRATEGY_LIBRARY_PATH.read_text(encoding="utf-8"))
    for s in lib.get("strategies", []):
        if s.get("strategy_id") == strategy_id:
            return s
    raise SystemExit(
        f"unknown strategy_id {strategy_id!r}. "
        f"Available: {', '.join(s['strategy_id'] for s in lib.get('strategies', []))}"
    )


def list_strategies() -> None:
    lib = json.loads(STRATEGY_LIBRARY_PATH.read_text(encoding="utf-8"))
    print(f"Strategy library · {lib['strategy_count']} approved within £{GBP_CAP_PER_TRADE:.0f} cap")
    print("─" * 80)
    for s in lib.get("strategies", []):
        print(f"  {s['strategy_id']:24s} {s['venue']:18s} {s['instrument']:10s} "
              f"units={s['units']:<6}  est £{s['estimated_gbp_exposure']}")
        print(f"    {s['name']} · style={s['style']}")


def now() -> str:
    return datetime.datetime.now(datetime.UTC).isoformat(timespec="seconds").replace("+00:00", "Z")


def load_json(rel: str, fallback=None):
    p = REG / rel
    if not p.exists():
        return fallback if fallback is not None else {}
    try:
        return json.loads(p.read_text(encoding="utf-8"))
    except Exception:
        return fallback if fallback is not None else {}


def _floor_workers(floor_id: str) -> list[str]:
    """Return all worker_ids belonging to floor_id (e.g. 'F41').

    Pulls from the dedicated per-floor worker registry if it exists, plus
    the generic F{N}.W{nn} workers from the master interior registry.
    """
    ids: list[str] = []
    # 1) Floor-specific named workers (F41 has these)
    name_map = {"F41": "qsb_floor41_oanda_workers.json"}
    if floor_id in name_map:
        d = load_json(name_map[floor_id], {})
        workers = d.get("workers", []) if isinstance(d, dict) else []
        for w in workers:
            wid = w.get("worker_id") if isinstance(w, dict) else None
            if wid:
                ids.append(wid)
    # 2) Generic master-registry workers (F{N}.W{nn})
    master = load_json("qsb_floor_interior_master_registry.json", {})
    for f in master.get("floors", []):
        if not isinstance(f, dict):
            continue
        if f.get("floor_id") != floor_id:
            continue
        for w in f.get("workers", []) or []:
            wid = w.get("id") if isinstance(w, dict) else None
            if wid and wid not in ids:
                ids.append(wid)
        break
    return ids


def pick_uncertified_cohort(instrument: str, n: int,
                              from_floor: str | None = None) -> list[str]:
    """Pull N worker_ids that aren't yet certified for instrument.

    If from_floor is set (e.g. 'F41'), only pull workers belonging to that
    floor. Otherwise, prefer Wren's team roster, then fall back to canonical.
    """
    wc = worker_certification()
    # Rehydrate prior certifications from the persisted snapshot so we don't
    # re-certify the same workers across runs.
    try:
        wc.load_from_snapshot()
    except Exception:
        pass
    candidates: list[str] = []

    if from_floor:
        for wid in _floor_workers(from_floor):
            e = wc.get_or_create(wid, instrument)
            if e.status != "certified":
                candidates.append(wid)
            if len(candidates) >= n:
                break
        return candidates[:n]

    # Default behavior: Wren team first, then canonical
    roster = load_json("qsb_wren_team_roster.json", {})
    for w in roster.get("workers", []):
        if not isinstance(w, dict):
            continue
        if w.get("status") != "employed":
            continue
        wid = w.get("worker_id")
        if not wid:
            continue
        e = wc.get_or_create(wid, instrument)
        if e.status != "certified":
            candidates.append(wid)
        if len(candidates) >= n:
            return candidates[:n]

    # Fall back to canonical pool
    canon = load_json("qsb_canonical_workers.json", {})
    pool = canon.get("workers") or canon.get("canonical_workers") or []
    for w in pool:
        if not isinstance(w, dict):
            continue
        wid = w.get("worker_id")
        if not wid or wid in candidates:
            continue
        if w.get("status") not in (None, "employed", "active"):
            continue
        e = wc.get_or_create(wid, instrument)
        if e.status != "certified":
            candidates.append(wid)
        if len(candidates) >= n:
            break
    return candidates[:n]


def run_classroom_for(worker_id: str, instrument: str) -> dict:
    """Returns a dict with passed + rationale + cert state after."""
    result = classroom().run_full_test(worker_id, instrument)
    wc = worker_certification()
    cert_after = wc.get_or_create(worker_id, instrument)
    return {
        "worker_id": worker_id,
        "instrument": instrument,
        "passed": result.passed,
        "written_score": f"{result.written_score}/{result.written_max}",
        "sim_win_rate": result.sim_win_rate,
        "sim_worst_loss_pct": result.sim_worst_loss_pct,
        "rationale": result.rationale,
        "cert_status_after": cert_after.status,
    }


def place_trade_oanda(worker_id: str, instrument: str, units: float,
                       direction: str = "buy",
                       strategy_name: str = "cohort_first_trade_v1") -> dict:
    from tower.qsb_floor41_oanda import open_paper_trade, refresh_all, engine_mode
    # OANDA accepts ints for FX, fractional for XAU. Cast safely.
    units_to_pass = float(units) if isinstance(units, float) and units != int(units) else int(units)
    # V2 (2026-06-10): default to oanda_practice_api when creds are present so trades
    # run against REAL OANDA practice quotes (which actually move) instead of the
    # local paper_simulator drift band. F47 lab proposed this; Wren accepted.
    mode = engine_mode()
    result = open_paper_trade(
        instrument=instrument,
        direction=direction,
        units=units_to_pass,
        entry_reason=f"cohort {strategy_name} for {worker_id}",
        strategy_name=strategy_name,
        worker_id=worker_id,
        execution_mode=mode,
    )
    try:
        refresh_all()
    except Exception:
        pass
    return result


def place_trade_binance_testnet(worker_id: str, symbol: str,
                                 quote_qty_usdt: float = 11.0,
                                 side: str = "BUY") -> dict:
    """Real testnet placement via Floor 42's place_for_worker.

    Tier B authorized (CLAUDE.md 2026-06-10): binance_testnet_placement_enabled.
    Keys read from Floor 28 vault. Fake money only.
    """
    try:
        from tower.floors.floor_42_binance_testnet.placement import place_for_worker
        # Ensure vault env vars are present in this process
        import os, pathlib
        if "QSB_BINANCE_TESTNET_API_KEY" not in os.environ:
            vault = pathlib.Path(
                "/vaults/nvme0/qsb_tower_v1/floors/floor_28_security_department/vault/.env.binance_testnet"
            )
            if vault.exists():
                for line in vault.read_text(encoding="utf-8").splitlines():
                    line = line.strip()
                    if line.startswith("#") or "=" not in line:
                        continue
                    if line.startswith("export "):
                        line = line[7:]
                    k, v = line.split("=", 1)
                    os.environ.setdefault(k.strip(), v.strip().strip('"').strip("'"))
        return place_for_worker(
            worker_id=worker_id, symbol=symbol,
            side=side, quote_qty_usdt=float(quote_qty_usdt),
            entry_reason=f"cohort first-trade (testnet) for {worker_id}",
            confirm_practice_order=True,   # cohort runner is explicit consent
        )
    except Exception as e:
        return {"ok": False, "error": f"binance_testnet_path_unavailable: {str(e)[:160]}"}


def place_trade_alpaca_paper(worker_id: str, symbol: str,
                              qty: int = 1) -> dict:
    # Alpaca paper placement isn't wrapped in a place_for_worker yet;
    # use a stub that records intent so we can wire later.
    return {"ok": False,
            "stage": "intent_recorded",
            "reason": "alpaca_paper_place_for_worker_not_wrapped_yet",
            "worker_id": worker_id, "symbol": symbol, "qty": qty,
            "venue": "alpaca_paper",
            "next_step": ("wrap StockPaperStrategyLab in a place_for_worker(...) "
                          "that goes through Floor 43 with the same audit trail.")}


VENUES = {
    "oanda_practice":  ("OANDA practice (Floor 41)",  place_trade_oanda),
    "binance_testnet": ("Binance testnet (Floor 42)", place_trade_binance_testnet),
    "alpaca_paper":    ("Alpaca paper (Floor 43)",    place_trade_alpaca_paper),
}


def main():
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    ap.add_argument("--cohort", type=int, default=10,
                    help="how many workers to put through the loop")
    ap.add_argument("--strategy", default=None,
                    help="strategy_id from qsb_wren_strategy_library.json. "
                         "When set, --instrument / --venue / --units are taken from the library.")
    ap.add_argument("--instrument", default=None,
                    help="(only without --strategy) e.g. EUR_USD, XAU_USD, BTCUSDT")
    ap.add_argument("--venue", default=None, choices=list(VENUES.keys()),
                    help="(only without --strategy)")
    ap.add_argument("--units", type=float, default=None,
                    help="(only without --strategy)")
    ap.add_argument("--direction", default="buy",
                    help="buy/sell direction; BUY/SELL for Binance")
    ap.add_argument("--dry-run", action="store_true",
                    help="run classroom + certify, skip the trade placement")
    ap.add_argument("--list-strategies", action="store_true",
                    help="print the strategy library and exit")
    ap.add_argument("--from-floor", default=None,
                    help="pull workers from a specific floor (e.g. F41, F42, F43) "
                         "instead of Wren's team")
    args = ap.parse_args()

    if args.list_strategies:
        list_strategies()
        sys.exit(0)

    if args.strategy:
        strategy = load_strategy(args.strategy)
        venue = strategy["venue"]
        instrument = strategy["instrument"]
        units = strategy["units"]
        # Risk-cap recheck right before use (live price could have moved)
        ok, gbp, reason = check_gbp_cap(venue, instrument, units)
        if not ok:
            print(f"  risk cap recheck FAILED: {reason}")
            sys.exit(2)
        print(f"  strategy: {strategy['name']} ({args.strategy})")
        print(f"  est exposure right now: £{gbp:.2f}")
    else:
        if not (args.instrument and args.venue and args.units is not None):
            print("  must pass --strategy OR all of --instrument --venue --units")
            sys.exit(1)
        instrument = args.instrument
        venue = args.venue
        units = args.units
        ok, gbp, reason = check_gbp_cap(venue, instrument, units)
        if not ok:
            print(f"  trade BLOCKED by risk cap: {reason}")
            sys.exit(2)
        strategy = None

    venue_label, trade_fn = VENUES[venue]
    # rebind argparse-style attrs for the rest of main() below
    args.instrument = instrument
    args.venue = venue
    args.units = units

    print(f"━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━")
    print(f"  Cohort training run · {now()}")
    if strategy:
        print(f"  strategy: {strategy['strategy_id']} ({strategy['style']})")
    print(f"  cohort_size={args.cohort}  instrument={args.instrument}  venue={venue_label}")
    print(f"  units/qty={args.units}  direction={args.direction}  dry_run={args.dry_run}")
    print(f"  risk cap: £{GBP_CAP_PER_TRADE:.0f} per trade")
    print(f"━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━")

    cohort = pick_uncertified_cohort(args.instrument, args.cohort,
                                      from_floor=args.from_floor)
    if not cohort:
        print("  no uncertified workers available — aborting.")
        sys.exit(1)
    print(f"  selected {len(cohort)} workers for cohort.")

    transcript: list[dict] = []
    passed = failed = traded = trade_blocked = 0

    for i, wid in enumerate(cohort, 1):
        row = run_classroom_for(wid, args.instrument)
        line_parts = [
            f"[{i:02d}] {wid}",
            f"  {row['rationale']}",
            f"  cert_status: {row['cert_status_after']}",
        ]
        if row["passed"]:
            passed += 1
            if not args.dry_run:
                trade_dir = (args.direction.upper()
                              if args.venue == "binance_testnet"
                              else args.direction)
                strategy_name = strategy["strategy_id"] if strategy else "ad_hoc_cohort"
                if args.venue == "alpaca_paper":
                    trade = trade_fn(wid, args.instrument, args.units)
                elif args.venue == "oanda_practice":
                    trade = trade_fn(wid, args.instrument, args.units, trade_dir, strategy_name)
                else:
                    trade = trade_fn(wid, args.instrument, args.units, trade_dir)
                ok = bool(trade.get("ok"))
                trade_id = (trade.get("trade_id") or trade.get("request_id")
                             or trade.get("order_id") or trade.get("stage") or "—")
                if ok or trade.get("stage") == "intent_recorded":
                    line_parts.append(f"  trade: {ok}  ref: {trade_id}")
                    if ok:
                        traded += 1
                    else:
                        trade_blocked += 1
                else:
                    line_parts.append(
                        f"  trade BLOCKED · {trade.get('error') or trade.get('reason') or 'unknown'}"
                    )
                    trade_blocked += 1
                row["trade_result"] = trade
            else:
                line_parts.append("  trade: SKIPPED (dry-run)")
        else:
            failed += 1
            line_parts.append("  trade: skipped (did not certify)")
        print("\n".join(line_parts))
        transcript.append(row)

    summary = {
        "ts": now(),
        "cohort_size": len(cohort),
        "instrument": args.instrument,
        "venue": args.venue,
        "dry_run": args.dry_run,
        "passed_cert": passed,
        "failed_cert": failed,
        "first_trade_placed": traded,
        "first_trade_blocked": trade_blocked,
        "rows": transcript,
    }

    # Persist the certification snapshot so future runs rehydrate correctly.
    try:
        worker_certification().persist()
    except Exception:
        pass

    out_path = REG / "qsb_cohort_training_runs.jsonl"
    with out_path.open("a", encoding="utf-8") as f:
        f.write(json.dumps(summary) + "\n")

    print(f"━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━")
    print(f"  Cohort summary:")
    print(f"    cert passed: {passed}/{len(cohort)}")
    print(f"    cert failed: {failed}/{len(cohort)}")
    if not args.dry_run:
        print(f"    first trade placed: {traded}")
        print(f"    first trade blocked: {trade_blocked}")
    print(f"  Stamped to: {out_path.relative_to(ROOT)}")
    print(f"━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━")


if __name__ == "__main__":
    main()
