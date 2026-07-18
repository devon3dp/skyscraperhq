#!/usr/bin/env python3
"""qsb_trader_trainer.py — batch trainer that reads trade closes,
analyzes wins vs losses per trader, writes learned rules to per-trader
memory files.

Ross 2026-07-06 #229: "train the traders to win".
Target: 75% win rate.

Output: data/registries/trader_memory/<trader_id>_learned.json
"""
from __future__ import annotations
import json, sys
from collections import defaultdict
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path("/vaults/nvme0/qsb_tower_v1")
REG = ROOT / "data/registries"
PNL_BUS = REG / "qsb_trader_pnl_bus_tail.jsonl"
MEM_DIR = REG / "trader_memory"
MEM_DIR.mkdir(parents=True, exist_ok=True)

WIN_TARGET = 0.75

def _utc(): return datetime.now(timezone.utc).isoformat().replace("+00:00","Z")

def train():
    if not PNL_BUS.exists():
        print("  no pnl bus"); return {}
    by_trader = defaultdict(list)
    for line in PNL_BUS.read_text(errors="ignore").splitlines():
        try:
            d = json.loads(line)
            wid = d.get("worker_id","?")
            by_trader[wid].append(d)
        except Exception: pass

    learned = {}
    for wid, rows in by_trader.items():
        if not rows: continue
        wins = [r for r in rows if r.get("won")]
        losses = [r for r in rows if not r.get("won")]
        total = len(rows)
        wr = len(wins)/total if total else 0

        # Learn: what's the average duration + PnL of wins vs losses
        avg_win_pnl = sum(r.get("pnl",0) for r in wins)/max(1,len(wins))
        avg_loss_pnl = sum(r.get("pnl",0) for r in losses)/max(1,len(losses))

        # Learn: which venues + instruments performed best/worst
        by_instr = defaultdict(lambda: {"wins":0,"losses":0,"pnl":0})
        for r in rows:
            inst = r.get("instrument","?")
            by_instr[inst]["wins" if r.get("won") else "losses"] += 1
            by_instr[inst]["pnl"] += r.get("pnl",0)

        best_instr = max(by_instr.items(), key=lambda kv: kv[1]["pnl"], default=("?",{"pnl":0}))
        worst_instr = min(by_instr.items(), key=lambda kv: kv[1]["pnl"], default=("?",{"pnl":0}))

        # Learned rules — actionable adjustments
        gap = WIN_TARGET - wr
        rules = []
        if wr >= WIN_TARGET:
            rules.append("MAINTAIN — at or above 75% target · protect the edge")
        elif wr >= 0.55:
            rules.append(f"IMPROVE — {int(wr*100)}% vs 75% target · tighten stops, avoid worst-performing instrument")
        else:
            rules.append(f"OVERHAUL — {int(wr*100)}% far below 75% · SUSPEND and re-strategize")

        if worst_instr[1]["pnl"] < -0.5:
            rules.append(f"DROP {worst_instr[0]} · losing ${worst_instr[1]['pnl']:.2f}")
        if best_instr[1]["pnl"] > 0.5:
            rules.append(f"AMP {best_instr[0]} · winning +${best_instr[1]['pnl']:.2f}")

        if avg_loss_pnl < -1.0 and abs(avg_loss_pnl) > 2 * avg_win_pnl:
            rules.append(f"CUT LOSSES FASTER · avg loss ${avg_loss_pnl:.2f} vs avg win ${avg_win_pnl:.2f}")

        # Target adjustment
        target_units = 500 if wr >= WIN_TARGET else 250

        card = {
            "trader_id": wid,
            "trained_at": _utc(),
            "closes_analyzed": total,
            "win_rate_current": round(wr, 3),
            "win_rate_target": WIN_TARGET,
            "gap_to_target": round(gap, 3),
            "avg_win_pnl": round(avg_win_pnl, 4),
            "avg_loss_pnl": round(avg_loss_pnl, 4),
            "best_instrument": {"name": best_instr[0], "pnl": round(best_instr[1]["pnl"], 4)},
            "worst_instrument": {"name": worst_instr[0], "pnl": round(worst_instr[1]["pnl"], 4)},
            "learned_rules": rules,
            "recommended_units": target_units,
            "verdict": "PASS" if wr >= WIN_TARGET else ("TRAIN" if wr >= 0.55 else "SUSPEND"),
        }

        # Write to trader's own memory
        mem_file = MEM_DIR / f"{wid}_learned.json"
        mem_file.write_text(json.dumps(card, indent=2))
        learned[wid] = card

    # Save summary
    summary = {
        "trained_at": _utc(),
        "traders_trained": len(learned),
        "meeting_target": sum(1 for c in learned.values() if c["verdict"] == "PASS"),
        "need_training": sum(1 for c in learned.values() if c["verdict"] == "TRAIN"),
        "suspend": sum(1 for c in learned.values() if c["verdict"] == "SUSPEND"),
        "target_win_rate": WIN_TARGET,
    }
    (REG / "qsb_trader_trainer_summary.json").write_text(json.dumps(summary, indent=2))
    return {"summary": summary, "cards": learned}

if __name__ == "__main__":
    r = train()
    s = r.get("summary", {})
    print(f"\n═══ TRAINING COMPLETE ═══")
    print(f"  traders trained: {s.get('traders_trained')}")
    print(f"  ✅ meeting 75% target: {s.get('meeting_target')}")
    print(f"  🎯 need training: {s.get('need_training')}")
    print(f"  🛑 suspend: {s.get('suspend')}")
    # Print top per-trader
    cards = r.get("cards", {})
    tops = sorted(cards.values(), key=lambda c: c["win_rate_current"], reverse=True)[:8]
    print(f"\n  TOP 8 by win rate:")
    for c in tops:
        mark = "✅" if c["verdict"] == "PASS" else ("🎯" if c["verdict"] == "TRAIN" else "🛑")
        print(f"    {mark} {c['trader_id']:35s} wr={c['win_rate_current']:.1%} · closes={c['closes_analyzed']} · rules={c['learned_rules'][0][:50]}")
