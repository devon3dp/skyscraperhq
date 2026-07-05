#!/usr/bin/env python3
"""End-to-end demo of the Finance Floors + Worker Lineage system.

Seeds a synthetic Floor 41 ledger so the Kernel has something to read,
then runs:
  · classroom certification for two demo workers
  · per-worker PnL rollup
  · reward_engine observe → friend grant + child grant proposed
  · report rendered
  · Claude endorse + Ross authorize + execute
  · final family tree print

This is a SEED demo — meant to show the flow works end-to-end. In
production the ledger is populated by real practice trades.
"""

from __future__ import annotations
from pathlib import Path
import json
import random
import sys
import time

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from tower.cognitive_kernel import ROOT
from tower.cognitive_kernel.classroom import classroom
from tower.cognitive_kernel.worker_certification import worker_certification
from tower.cognitive_kernel.worker_pnl import worker_pnl
from tower.cognitive_kernel.worker_genetics import worker_genetics
from tower.cognitive_kernel.family_tree import family_tree
from tower.cognitive_kernel.population import persist as persist_population
from tower.cognitive_kernel.trading_authority import (
    check_authority, install_authority_rule, persist_gate,
)
from tower.cognitive_kernel.reward_engine import reward_engine
from tower.cognitive_kernel.orchestrator import orchestrator


LEDGER = ROOT / "data/logs/qsb_floor41_oanda_trade_ledger.jsonl"
DEMO_TAG = "FINANCE_LINEAGE_E2E_DEMO_SEED"


def seed_synthetic_ledger():
    """Append synthetic trades for two demo workers — does NOT delete
    existing rows. Marked so they can be filtered later."""
    LEDGER.parent.mkdir(parents=True, exist_ok=True)
    seed_workers = [
        # (id, instrument, style, win_rate, n_trades, base_pnl)
        # demo_worker_A clears BOTH thresholds (friend AND child)
        ("demo_worker_A", "EUR_USD", "scalp", 0.78, 120, 10.0),
        # demo_worker_B clears the friend threshold only
        ("demo_worker_B", "USD_JPY", "scalp", 0.65, 40,  5.0),
    ]
    rng = random.Random(42)
    now_ts = time.time()
    with LEDGER.open("a", encoding="utf-8") as f:
        for (wid, inst, style, wr, n, base) in seed_workers:
            for i in range(n):
                is_win = rng.random() < wr
                pnl = (base * (0.6 + rng.random())) if is_win else -(base * (0.4 + 0.6 * rng.random()))
                open_ts = now_ts - (n - i) * 60
                close_ts = open_ts + (30 + rng.random() * 300)
                row = {
                    "tag": DEMO_TAG,
                    "ts": time.strftime("%Y-%m-%dT%H:%M:%S+00:00", time.gmtime(close_ts)),
                    "worker_id": wid,
                    "instrument": inst,
                    "style": style,
                    "units": 1000,
                    "side": "buy" if (i % 2 == 0) else "sell",
                    "open_ts": open_ts,
                    "close_ts": close_ts,
                    "open_price": 1.0850 + rng.random() * 0.01,
                    "close_price": 1.0855 + rng.random() * 0.01,
                    "realized_pnl": round(pnl, 2),
                }
                f.write(json.dumps(row) + "\n")
    print(f"seeded synthetic ledger rows for {[w[0] for w in seed_workers]}")


def main():
    print("=" * 72)
    print("END-TO-END DEMO · Finance Floors + Worker Lineage")
    print("=" * 72)

    # 1) Seed ledger
    seed_synthetic_ledger()

    # 2) Run classroom test for demo workers
    print()
    print("--- Classroom tests ---")
    cr = classroom()
    cr.persist()
    for wid, inst in (("demo_worker_A", "EUR_USD"),
                      ("demo_worker_B", "USD_JPY")):
        r = cr.run_full_test(wid, inst,
                              knowledge_seed=0.85, skill_seed=0.7)
        print(f"  {wid} / {inst}: written={r.written_score}/{r.written_max} "
              f"sim_win_rate={r.sim_win_rate} sim_pass={r.sim_pass} "
              f"PASSED={r.passed}")

    # 3) Trading authority gate check
    print()
    print("--- Authority gate checks ---")
    install_authority_rule()
    for wid, inst in (("demo_worker_A", "EUR_USD"),
                       ("demo_worker_B", "USD_JPY"),
                       ("uncertified_X", "EUR_USD")):
        ac = check_authority(wid, inst)
        print(f"  {wid} / {inst}: {ac.decision} — {ac.reason}")
    persist_gate()

    # 4) PnL rollup
    print()
    print("--- Per-worker PnL rollup ---")
    pnl = worker_pnl()
    pnl.refresh()
    snap = pnl.snapshot()
    print(f"  ledger_lines_read = {snap['ledger_lines_read']}")
    print(f"  worker_count      = {snap['worker_count']}")
    print(f"  total_practice_pnl= ${snap['total_realized_pnl_practice']:.2f}")
    for r in snap['top_earners'][:5]:
        print(f"  · {r['worker_id']}  trades={r['closed_trade_count']}  "
              f"win_rate={r['win_rate']}  pnl=${r['realized_pnl']:.2f}")
    pnl.persist()

    # 5) Genetics — reveal genes from PnL
    print()
    print("--- Genetics reveal ---")
    wg = worker_genetics()
    for wid in ("demo_worker_A", "demo_worker_B"):
        gene = wg.reveal_or_update(
            wid,
            pnl_by_pair=pnl.pnl_by_pair(wid),
            total_trades=pnl.closed_trade_count_for(wid),
        )
        if gene:
            print(f"  {wid} gene revealed: {gene.instrument}/{gene.style} "
                  f"(family={gene.family}, conf={gene.confidence})")
        else:
            print(f"  {wid} gene not yet revealed")
    wg.persist()

    # 6) Reward engine — observe + propose
    print()
    print("--- Reward engine observe → propose ---")
    re_ = reward_engine()
    family_tree().load_from_snapshot()
    re_.load_from_snapshot()
    proposed = re_.observe_and_propose()
    print(f"  proposed: {len(proposed)} grant(s)")
    for g in proposed:
        print(f"    · {g.grant_id}  [{g.kind}]  candidate={g.candidate_worker_id}")
        if g.report_path:
            print(f"        report → {g.report_path}")
    re_.persist()
    persist_population()

    # 7) Print one full report
    if proposed:
        first = proposed[0]
        print()
        print("--- Sample report (first grant) ---")
        if first.report_path and Path(first.report_path).exists():
            print(Path(first.report_path).read_text(encoding="utf-8"))

    # 8) Endorse + authorize + execute the first grant
    if proposed:
        first = proposed[0]
        print()
        print(f"--- Endorse + Authorize + Execute: {first.grant_id} ---")
        re_.endorse(first.grant_id, note="demo: Claude endorses")
        re_.authorize(first.grant_id, note="demo: Ross authorizes")
        executed = re_.execute_authorized()
        print(f"  executed: {executed}")
        re_.persist()
        family_tree().persist()

    # 9) Final family tree
    print()
    print("--- Final family tree snapshot ---")
    snap = family_tree().snapshot()
    print(f"  friend_edges:  {snap['friend_edge_count']}")
    print(f"  child_edges:   {snap['child_edge_count']}")
    for e in (snap.get('friends_sample') or [])[:5]:
        print(f"    friend: {e['a']} ↔ {e['b']}  grant={e['grant_id']}")
    for e in (snap.get('children_sample') or [])[:5]:
        gene = e.get('inherited_gene') or {}
        print(f"    child:  {e['parent_id']} → {e['child_id']}  "
              f"gene={gene.get('instrument', '?')}/{gene.get('style', '?')}  "
              f"status={e['status']}")

    # 10) Run orchestrator tick so cognition absorbs all this
    print()
    print("--- Final orchestrator tick ---")
    r = orchestrator().tick(do_reflection=True)
    print(f"  tick={r.tick_id}  conclusions={r.reasoning_conclusion_count}  "
          f"reflections={r.reflection_note_count}  "
          f"open_proposals={r.proposal_count_open}  "
          f"curiosity={r.curiosity_open_count}")

    print()
    print("=" * 72)
    print("DONE.  Try the chat now:")
    print("  · 'who is profitable'             → per-worker PnL")
    print("  · 'show me the family tree'       → lineage")
    print("  · 'pending grants'                → reward report")
    print("  · 'who is certified'              → certification ledger")
    print("=" * 72)


if __name__ == "__main__":
    main()
