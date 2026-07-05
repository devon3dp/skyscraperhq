#!/usr/bin/env python3
"""qsb_classroom_evaluator.py — Phase 2 of "traders run themselves" (Ross
2026-06-17 helm).

The trader daemons (F41/F42/F43) own their loops. The CLASSROOM grades
them. This script is the classroom: it reads recent decisions, scores each
trader, and emits a verdict per (worker_id, instrument) pair.

V1 (this file) is ADVISORY — it writes verdicts to
data/registries/qsb_classroom_verdicts.jsonl but does NOT flip cert files.
V2 will apply them by writing into cognitive_worker_certification.json
once Ross signs off on a few cycles of verdicts looking sane.

WHAT IT MEASURES
  Per (worker_id, instrument), over the last N attempts:
    * placement_success_rate: placed_ok=True / total
    * consecutive_failures: trailing count of placed_ok=False
    * total_attempts: count over window
    * last_seen_ts: when this worker was last active

RULES (mirror the existing certification policy)
  * suspend_recommended  → consecutive_failures >= 5
                           (matches the cert file's suspension_loss_streak)
  * watch_recommended    → success_rate < 0.7 over >=10 attempts
                           OR consecutive_failures >= 3
  * promote_recommended  → success_rate >= 0.95 over >=20 attempts
                           AND consecutive_failures == 0
  * hold                 → none of the above

USAGE
  python3 tools/qsb_classroom_evaluator.py            # one-shot
  python3 tools/qsb_classroom_evaluator.py --window 50

DESIGNED TO RUN
  Via systemd timer qsb-classroom-evaluator.timer every 30 min.
"""

from __future__ import annotations
import argparse, datetime, json, os
from collections import defaultdict
from pathlib import Path

ROOT = Path("/vaults/nvme0/qsb_tower_v1")
F47 = ROOT / "data/registries/qsb_f47_team_records.jsonl"
VERDICTS = ROOT / "data/registries/qsb_classroom_verdicts.jsonl"
PNL_LATEST = ROOT / "data/registries/qsb_trader_pnl_latest.json"

FLOORS = {
    "F41": {
        "log": ROOT / "data/registries/qsb_f41_trader_cycle.jsonl",
        # F41 daemon emits {"instrument": "EUR_USD", ...} per cycle —
        # no per-worker breakdown because cohort runner picks workers.
        # So for F41 we score by INSTRUMENT, not worker_id.
        "key_fields": ("daemon", "instrument"),
        "outcome_field": "opened",   # opened.ok is the placement result
        "outcome_path": ("opened", "ok"),
    },
    "F42": {
        "log": ROOT / "data/registries/qsb_f42_trader_cycle.jsonl",
        "key_fields": ("worker", "instrument"),
        "outcome_field": "placed",
        "outcome_path": ("placed", "ok"),
    },
    "F43": {
        "log": ROOT / "data/registries/qsb_f43_trader_cycle.jsonl",
        "key_fields": ("worker", "symbol"),
        "outcome_field": "placed",
        "outcome_path": ("placed", "ok"),
    },
}


def now_iso() -> str:
    return datetime.datetime.now(datetime.timezone.utc).isoformat(
        timespec="seconds").replace("+00:00", "Z")


def tail_jsonl(path: Path, n: int) -> list[dict]:
    """Tail n rows. Streams to handle big files efficiently."""
    if not path.exists():
        return []
    # Simple approach: read all then slice. F4x cycle logs stay small.
    out = []
    for line in path.read_text().splitlines():
        line = line.strip()
        if not line:
            continue
        try:
            out.append(json.loads(line))
        except Exception:
            continue
    return out[-n:]


def get_outcome(row: dict, path: tuple) -> bool | None:
    d = row
    for k in path:
        if not isinstance(d, dict):
            return None
        d = d.get(k)
    return bool(d) if d is not None else None


def load_pnl_by_worker(floor: str) -> dict:
    """Read latest PnL snapshot, return {(worker, instrument): realized_pnl}.
    PnL is GBP for F41, USDT for F42, USD for F43 — caller knows the unit
    from `floor`."""
    if not PNL_LATEST.exists():
        return {}
    try:
        d = json.loads(PNL_LATEST.read_text())
    except Exception:
        return {}
    out: dict[tuple, float] = {}
    f = d.get("by_floor", {}).get(floor, {})
    # F42/F43 path: broker_pnl_*_by_symbol.{sym}.by_worker.{w}.realized_pnl
    broker = f.get("broker", {})
    if broker.get("ok"):
        # F42 uses usdt key, F43 uses usd key
        pnl_key = ("broker_pnl_usdt_by_symbol"
                   if "broker_pnl_usdt_by_symbol" in broker
                   else "broker_pnl_usd_by_symbol")
        for sym, v in broker.get(pnl_key, {}).items():
            for w, wv in v.get("by_worker", {}).items():
                out[(w, sym)] = wv.get("realized_pnl", 0.0)
    # F41 path: top_workers list
    for w in f.get("top_workers", []):
        wid = w.get("worker_id")
        pnl = w.get("total_pnl")
        if wid is None or pnl is None:
            continue
        # F41 doesn't break out per instrument in top_workers — store under
        # ("*"). The score logic below handles wildcard match.
        out[(wid, "*")] = pnl
    return out


def score_traders(floor: str, cfg: dict, window: int) -> list[dict]:
    rows = tail_jsonl(cfg["log"], window * 20)
    if not rows:
        return []

    # Group by (worker, instrument)
    groups: dict[tuple, list[dict]] = defaultdict(list)
    for r in rows:
        w_field, i_field = cfg["key_fields"]
        worker = r.get(w_field, "<floor>") or "<floor>"
        instrument = r.get(i_field, "?")
        if not instrument:
            continue
        groups[(worker, instrument)].append(r)

    # Load PnL snapshot (per-worker, originator-attributed via broker join)
    pnl_map = load_pnl_by_worker(floor)

    verdicts = []
    for (worker, instrument), grp in groups.items():
        recent = grp[-window:]
        attempts = len(recent)
        outcomes = [get_outcome(r, cfg["outcome_path"]) for r in recent]
        attempts_with_outcome = [o for o in outcomes if o is not None]
        if not attempts_with_outcome:
            continue
        success = sum(1 for o in attempts_with_outcome if o)
        success_rate = success / len(attempts_with_outcome)
        # Trailing consecutive failures
        consec_fail = 0
        for o in reversed(outcomes):
            if o is False:
                consec_fail += 1
            else:
                break
        last_ts = recent[-1].get("ts", "?")
        # PnL lookup — exact (worker,instrument) then (worker,"*") fallback
        realized_pnl = pnl_map.get((worker, instrument),
                                     pnl_map.get((worker, "*")))

        # Decide verdict — combine placement-success and realized PnL
        if consec_fail >= 5:
            decision = "suspend_recommended"
            reason = f"{consec_fail} consecutive failures (>=5)"
        elif realized_pnl is not None and realized_pnl <= -1.0:
            # Hard PnL threshold: lost more than 1 unit currency → watch.
            decision = "watch_recommended"
            reason = (f"realized_pnl={realized_pnl:.4f} (loss > 1.0), "
                      f"success_rate={success_rate:.2f}")
        elif consec_fail >= 3 or (
                len(attempts_with_outcome) >= 10 and success_rate < 0.7):
            decision = "watch_recommended"
            reason = (f"success_rate={success_rate:.2f} over "
                      f"{len(attempts_with_outcome)} attempts, "
                      f"consec_fail={consec_fail}")
        elif (len(attempts_with_outcome) >= 20 and success_rate >= 0.95
              and consec_fail == 0
              and (realized_pnl is None or realized_pnl >= 0)):
            decision = "promote_recommended"
            reason = (f"success_rate={success_rate:.2f} over "
                      f"{len(attempts_with_outcome)} attempts, clean tail, "
                      f"pnl={realized_pnl}")
        else:
            decision = "hold"
            reason = (f"success_rate={success_rate:.2f} over "
                      f"{len(attempts_with_outcome)} attempts, "
                      f"consec_fail={consec_fail}, pnl={realized_pnl}")

        verdicts.append({
            "ts": now_iso(),
            "floor": floor,
            "worker": worker,
            "instrument": instrument,
            "window": window,
            "attempts": attempts,
            "attempts_with_outcome": len(attempts_with_outcome),
            "success_rate": round(success_rate, 3),
            "consec_failures": consec_fail,
            "realized_pnl": (round(realized_pnl, 4)
                              if realized_pnl is not None else None),
            "last_attempt_ts": last_ts,
            "decision": decision,
            "reason": reason,
            "applied": False,
        })
    return verdicts


def stamp_verdicts(verdicts: list[dict]) -> None:
    VERDICTS.parent.mkdir(parents=True, exist_ok=True)
    with open(VERDICTS, "a") as f:
        for v in verdicts:
            f.write(json.dumps(v) + "\n")


def stamp_f47(verdicts: list[dict]) -> None:
    counts = defaultdict(int)
    for v in verdicts:
        counts[v["decision"]] += 1
    summary = (
        f"Phase 2 classroom: {len(verdicts)} verdicts · "
        f"{dict(counts)}"
    )
    with open(F47, "a") as f:
        f.write(json.dumps({
            "ts": now_iso(),
            "kind": "classroom_evaluator_tick",
            "operator": "claude",
            "summary": summary[:500],
        }) + "\n")


def main() -> int:
    p = argparse.ArgumentParser()
    p.add_argument("--window", type=int, default=20,
                   help="last N attempts per (worker, instrument) "
                        "to score on")
    p.add_argument("--floor", choices=list(FLOORS.keys()) + ["all"],
                   default="all")
    p.add_argument("--dry-run", action="store_true",
                   help="print verdicts; don't stamp")
    a = p.parse_args()

    floors_to_run = list(FLOORS.keys()) if a.floor == "all" else [a.floor]
    all_verdicts: list[dict] = []
    for floor in floors_to_run:
        cfg = FLOORS[floor]
        verdicts = score_traders(floor, cfg, a.window)
        all_verdicts.extend(verdicts)

    if a.dry_run:
        print(json.dumps(all_verdicts, indent=2)[:5000])
    else:
        if all_verdicts:
            stamp_verdicts(all_verdicts)
            stamp_f47(all_verdicts)
        # Print compact summary for systemd log
        from collections import Counter
        c = Counter(v["decision"] for v in all_verdicts)
        print(f"[{now_iso()}] classroom evaluator: "
              f"{len(all_verdicts)} verdicts · {dict(c)}")
        # Show traders needing attention
        for v in all_verdicts:
            if v["decision"] in ("suspend_recommended",
                                  "watch_recommended",
                                  "promote_recommended"):
                print(f"  {v['decision']:<25s} {v['floor']} "
                      f"{v['worker']}/{v['instrument']} · "
                      f"success_rate={v['success_rate']} "
                      f"consec_fail={v['consec_failures']}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
