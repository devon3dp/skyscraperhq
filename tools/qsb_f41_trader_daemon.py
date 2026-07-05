#!/usr/bin/env python3
"""qsb_f41_trader_daemon.py — persistent per-instrument loop on F41 OANDA
practice floor. Mirror of qsb_f42_trader_daemon.py for the FX side.

Pattern is one daemon per FX instrument (EUR_USD, GBP_USD, USD_JPY) rather
than per-worker, because F41 has 60+ certified workers per instrument and
uses qsb_train_and_trade_cohort.py to pick from the pool internally. So
the daemon's job is to keep ONE instrument's lifecycle turning:

  forever:
    force_refresh()                            # local lifecycle snapshot
    close any trade older than --hold-secs     # for OUR instrument
    open_cohort_if_room()                      # top up via cohort runner
    sleep(--cycle-secs)

Verified live against OANDA practice: lifetime realized PL £+214.26
(2026-06-17 reality check via REST). This daemon takes over from the
qsb-f41-trader-cycle timer; no behavior change inside a cycle, just the
trigger swapped from systemd to a loop.

Usage:
  python3 tools/qsb_f41_trader_daemon.py \\
      --instrument EUR_USD --hold-secs 900 --units 100
"""

from __future__ import annotations
import argparse, datetime, json, signal, sys, time
from pathlib import Path

ROOT = Path("/vaults/nvme0/qsb_tower_v1")
sys.path.insert(0, str(ROOT / "src"))

F47 = ROOT / "data/registries/qsb_f47_team_records.jsonl"
OUT = ROOT / "data/registries/qsb_f41_trader_cycle.jsonl"

DEFAULT_CYCLE_S = 600     # match prior timer cadence (10 min)
IDLE_CYCLE_S = 1800       # back off when cohort runner refuses
DEFAULT_HOLD_S = 900      # close trades > 15 min old
DEFAULT_UNITS = 100

SHUTDOWN = False


def now_iso() -> str:
    return datetime.datetime.now(datetime.timezone.utc).isoformat(
        timespec="seconds").replace("+00:00", "Z")


def log(msg: str) -> None:
    print(f"[{now_iso()}] {msg}", flush=True)


def _on_sigterm(signum, frame):
    global SHUTDOWN
    SHUTDOWN = True
    log(f"received signal {signum}, will exit after current iteration")


signal.signal(signal.SIGTERM, _on_sigterm)
signal.signal(signal.SIGINT, _on_sigterm)


def _import_cycle_helpers():
    """Lazy-import the cycle script's helpers so the daemon stays a thin
    wrapper. If the cycle script changes, the daemon picks it up."""
    import importlib.util
    spec = importlib.util.spec_from_file_location(
        "qsb_f41_cycle", str(ROOT / "tools/qsb_f41_trader_cycle.py"))
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


def stamp(payload: dict) -> None:
    OUT.parent.mkdir(parents=True, exist_ok=True)
    with open(OUT, "a") as f:
        f.write(json.dumps(payload) + "\n")
    row = {
        "ts": payload["ts"], "kind": "f41_trader_daemon",
        "operator": "claude",
        "summary": (
            f"F41 daemon · {payload.get('instrument','?')} · "
            f"refresh={payload.get('refresh_ok')} "
            f"closed={payload.get('closed_count',0)} "
            f"skipped={payload.get('skipped_count',0)} "
            f"opened_cohort_ok={payload.get('opened',{}).get('ok','?')}"
        )[:500],
    }
    with open(F47, "a") as f:
        f.write(json.dumps(row) + "\n")


def run_loop(instrument: str, hold_secs: int, units: int,
             cycle_secs: int, max_iters: int | None = None) -> int:
    cyc = _import_cycle_helpers()
    log(f"daemon start · instrument={instrument} hold={hold_secs}s "
        f"units={units} cycle={cycle_secs}s")
    iters = 0
    failures = 0
    while not SHUTDOWN:
        iters += 1
        try:
            refresh = cyc.force_refresh()
            closed = cyc.close_aged_trades(hold_secs)
            opened = cyc.open_cohort_if_room(units, instrument)
            payload = {
                "ts": now_iso(), "kind": "f41_trader_daemon",
                "instrument": instrument, "hold_secs": hold_secs,
                "units": units,
                "refresh_ok": refresh.get("ok"),
                "closed": closed.get("closed", []),
                "closed_count": len(closed.get("closed", [])),
                "skipped_count": len(closed.get("skipped", [])),
                "opened": opened,
            }
            stamp(payload)
            opened_ok = opened.get("ok") if isinstance(opened, dict) else None
            log(f"cycle · refresh={refresh.get('ok')} "
                f"closed={payload['closed_count']} "
                f"opened_ok={opened_ok}")
            sleep_s = cycle_secs
            failures = 0
        except Exception as e:
            failures += 1
            log(f"cycle FAILED ({failures}): {type(e).__name__}: {str(e)[:200]}")
            sleep_s = min(cycle_secs * (2 ** min(failures, 4)), IDLE_CYCLE_S)

        if max_iters is not None and iters >= max_iters:
            log(f"max_iters reached ({iters}), exiting")
            return 0

        log(f"sleeping {sleep_s}s")
        remaining = sleep_s
        while remaining > 0 and not SHUTDOWN:
            chunk = min(5, remaining)
            time.sleep(chunk)
            remaining -= chunk
    log("daemon stop · clean shutdown")
    return 0


def main() -> int:
    p = argparse.ArgumentParser()
    p.add_argument("--instrument", required=True,
                   choices=["EUR_USD", "GBP_USD", "USD_JPY"])
    p.add_argument("--hold-secs", type=int, default=DEFAULT_HOLD_S,
                   help="close trades held > this many seconds")
    p.add_argument("--units", type=int, default=DEFAULT_UNITS,
                   help="cohort trade size in units")
    p.add_argument("--cycle-secs", type=int, default=DEFAULT_CYCLE_S,
                   help="sleep between cycles when healthy")
    p.add_argument("--max-iters", type=int, default=None,
                   help="Smoke-test mode: exit after N iters")
    p.add_argument("--dry-run", action="store_true")
    a = p.parse_args()

    if a.dry_run:
        print(json.dumps({
            "instrument": a.instrument, "hold_secs": a.hold_secs,
            "units": a.units, "cycle_secs": a.cycle_secs,
            "would_loop": True,
        }, indent=2))
        return 0

    return run_loop(a.instrument, a.hold_secs, a.units, a.cycle_secs,
                    max_iters=a.max_iters)


if __name__ == "__main__":
    sys.exit(main())
