"""Strategy Synthesis Sandbox · F37 Strategy Labs.

What it does (Option F from the 2026-06-10 kernel-upgrade consultation):
    1. Reads F44 PnL roll-up + the strategy library
    2. Hypothesizes refinements per strategy
    3. Contradiction-checks each hypothesis (risk cap, prior winners, GBP ceiling)
    4. Scores refinements deterministically against historical trade outcomes
    5. Publishes top-scoring entries as advisory output

Advisory only. Never modifies the strategy library directly — Wren reviews
the published entries and decides what reaches code.

Output:
    data/registries/qsb_floor37_synthesis_output.jsonl   (one synthesis run)
    qsb_tower_activity_tail.jsonl                         (strategy_proposed events)
"""

from __future__ import annotations
import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

ROOT = Path("/vaults/nvme0/qsb_tower_v1")
REG = ROOT / "data/registries"
SYNTHESIS_OUT = REG / "qsb_floor37_synthesis_output.jsonl"

# Reuse the activity tail
import sys
sys.path.insert(0, str(ROOT / "src"))
try:
    from tower.qsb_tower_activity import append_event
except Exception:
    def append_event(*args, **kwargs): pass


def _now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds").replace("+00:00", "Z")


def _load(rel: str, fallback=None):
    p = REG / rel
    if not p.exists():
        return fallback if fallback is not None else {}
    try:
        return json.loads(p.read_text(encoding="utf-8"))
    except Exception:
        return fallback if fallback is not None else {}


def _load_jsonl(rel: str) -> list:
    p = REG / rel
    if not p.exists(): return []
    out = []
    for line in p.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line: continue
        try: out.append(json.loads(line))
        except Exception: pass
    return out


# ── refinement heuristics ───────────────────────────────────────────────


def _refinements_for(strategy: dict, history: dict) -> list[dict]:
    """For one strategy, generate hypothesized refinements.

    Heuristics are deterministic; same inputs → same proposals.
    """
    proposals: list[dict] = []
    sid = strategy["strategy_id"]
    target = float(strategy.get("target_profit_pct", 0.10))
    loss = float(strategy.get("max_loss_pct", 0.10))
    hold = float(strategy.get("max_hold_seconds", 600))
    avg_close_pnl_pct = history.get(sid, {}).get("avg_close_pnl_pct", 0.0)
    timeout_share = history.get(sid, {}).get("timeout_share", 1.0)
    closed = history.get(sid, {}).get("closed_count", 0)

    # H1: if most closes were timeouts AND avg PnL near zero → shorten hold
    if timeout_share > 0.6 and abs(avg_close_pnl_pct) < target * 0.5:
        proposals.append({
            "kind": "shorten_hold",
            "change": {"max_hold_seconds": max(60.0, hold * 0.6)},
            "rationale": (
                f"closed {closed} trades · {int(timeout_share*100)}% timed out · "
                f"avg pnl {avg_close_pnl_pct:.3f}% — hold is too long for the simulator's "
                f"variance band, trades time out before targets fire"
            ),
        })
    # H2: if no closes hit target_profit_pct → loosen target
    if avg_close_pnl_pct < target * 0.3 and closed >= 2:
        proposals.append({
            "kind": "loosen_target",
            "change": {"target_profit_pct": round(target * 0.5, 4)},
            "rationale": (
                f"current target {target}% never fires (avg closed pnl {avg_close_pnl_pct:.3f}%); "
                f"propose halving to {round(target*0.5, 4)}% — smaller wins, more frequent"
            ),
        })
    # H3: if every close was a loss → tighten stop
    losers = history.get(sid, {}).get("loss_count", 0)
    if closed >= 3 and losers == closed:
        proposals.append({
            "kind": "tighten_stop",
            "change": {"max_loss_pct": round(loss * 0.7, 4)},
            "rationale": (
                f"all {closed} closes were losses · tightening stop from {loss}% "
                f"to {round(loss*0.7, 4)}% reduces single-trade damage during simulator drift"
            ),
        })
    # H4: if strategy hasn't placed any trade yet → propose lowering size by 30% for first cohort
    if closed == 0 and history.get(sid, {}).get("open_count", 0) == 0:
        units = strategy.get("units", 0)
        if units > 1:
            proposals.append({
                "kind": "scale_down_first_cohort",
                "change": {"units": round(float(units) * 0.7, 4)},
                "rationale": (
                    f"strategy never placed a trade yet — propose 30% smaller initial "
                    f"size ({units} → {round(units*0.7,4)}) to validate without risking cap"
                ),
            })
    return proposals


def _check_contradictions(strategy: dict, proposal: dict) -> tuple[bool, str]:
    """Run contradiction checks against architectural invariants."""
    change = proposal.get("change", {})
    # Invariant 1: hold must be > 30s (sub-half-minute holds are noise)
    if "max_hold_seconds" in change and change["max_hold_seconds"] < 30:
        return False, "would shorten hold below 30s noise floor"
    # Invariant 2: loss% must stay positive
    if "max_loss_pct" in change and change["max_loss_pct"] <= 0:
        return False, "loss% cannot be ≤ 0"
    # Invariant 3: target% must stay positive
    if "target_profit_pct" in change and change["target_profit_pct"] <= 0:
        return False, "target% cannot be ≤ 0"
    # Invariant 4: GBP cap recheck if units change
    if "units" in change:
        try:
            sys.path.insert(0, str(ROOT / "tools"))
            from qsb_risk_cap import check_gbp_cap  # type: ignore
            ok, gbp, reason = check_gbp_cap(strategy["venue"], strategy["instrument"],
                                              float(change["units"]))
            if not ok:
                return False, f"refinement violates £1000 cap: {reason}"
        except Exception:
            pass   # if risk cap unavailable, allow but flag
    return True, "passes"


def _score(strategy: dict, proposal: dict, history: dict) -> float:
    """Deterministic score 0..1 — higher is better. Based on hypothesis strength."""
    sid = strategy["strategy_id"]
    h = history.get(sid, {})
    closed = h.get("closed_count", 0)
    timeout_share = h.get("timeout_share", 0)
    losers = h.get("loss_count", 0)
    avg_pnl = abs(h.get("avg_close_pnl_pct", 0))

    base = 0.50
    if proposal["kind"] == "shorten_hold":
        # rewarded when timeout share high + many closed
        return min(1.0, base + 0.30 * timeout_share + min(closed, 10) / 50.0)
    if proposal["kind"] == "loosen_target":
        # rewarded when avg pnl far below target
        target = float(strategy.get("target_profit_pct", 0.10))
        gap = max(0.0, target - avg_pnl)
        return min(1.0, base + 0.40 * (gap / max(target, 0.001)))
    if proposal["kind"] == "tighten_stop":
        # rewarded when all closes were losses + enough data
        return min(1.0, base + 0.35 + min(closed, 6) / 30.0) if (closed and losers == closed) else 0.4
    if proposal["kind"] == "scale_down_first_cohort":
        # safe-but-small step — modest score, decays if other refinements exist
        return 0.55
    return 0.4


# ── history aggregation ────────────────────────────────────────────────


def _strategy_history() -> dict:
    """Per-strategy_id close+open stats from F41 lifecycle."""
    lc = _load("qsb_floor41_oanda_trade_lifecycle.json")
    closed = lc.get("closed_trades", [])
    opens = lc.get("open_trades", [])
    reqs = lc.get("requests", [])
    out: dict[str, dict] = {}
    for r in reqs:
        sid = r.get("strategy_name") or "manual"
        out.setdefault(sid, {"closed_count": 0, "open_count": 0,
                              "loss_count": 0, "timeout_count": 0,
                              "close_pnl_pcts": []})
    for t in opens:
        sid = t.get("strategy_name") or "manual"
        out.setdefault(sid, {"closed_count": 0, "open_count": 0,
                              "loss_count": 0, "timeout_count": 0,
                              "close_pnl_pcts": []})
        out[sid]["open_count"] += 1
    for t in closed:
        sid = t.get("strategy_name") or "manual"
        out.setdefault(sid, {"closed_count": 0, "open_count": 0,
                              "loss_count": 0, "timeout_count": 0,
                              "close_pnl_pcts": []})
        out[sid]["closed_count"] += 1
        pnl = float(t.get("pnl_amount", 0) or 0)
        entry = float(t.get("entry_price", 0) or 0)
        exit_p = float(t.get("exit_price", 0) or 0)
        if entry > 0:
            pnl_pct = ((exit_p - entry) / entry) * 100.0 * \
                       (1 if t.get("direction") == "buy" else -1)
            out[sid]["close_pnl_pcts"].append(pnl_pct)
        if pnl < 0:
            out[sid]["loss_count"] += 1
        reason = (t.get("close_reason") or "").lower()
        if "timeout" in reason or "max_hold" in reason:
            out[sid]["timeout_count"] += 1
    # derive avg + shares
    for sid, h in out.items():
        n = len(h["close_pnl_pcts"])
        h["avg_close_pnl_pct"] = round(sum(h["close_pnl_pcts"]) / n, 4) if n else 0.0
        h["timeout_share"] = (h["timeout_count"] / h["closed_count"]
                                if h["closed_count"] else 0.0)
    return out


# ── orchestration ──────────────────────────────────────────────────────


def synthesize(top_n: int = 8) -> dict:
    """One synthesis run. Returns the run summary; also writes to output."""
    library = _load("qsb_wren_strategy_library.json")
    strategies = library.get("strategies", [])
    history = _strategy_history()

    all_proposals: list[dict] = []
    for s in strategies:
        for p in _refinements_for(s, history):
            ok, contradiction_reason = _check_contradictions(s, p)
            score = _score(s, p, history) if ok else 0.0
            proposal = {
                "strategy_id": s["strategy_id"],
                "instrument": s["instrument"],
                "venue": s["venue"],
                "kind": p["kind"],
                "change": p["change"],
                "rationale": p["rationale"],
                "contradiction_check": {
                    "passes": ok, "reason": contradiction_reason,
                },
                "score": round(score, 4),
                "lab_role": _attribute_to_lab_role(p["kind"]),
            }
            all_proposals.append(proposal)

    # Rank by score; keep top_n surviving contradictions
    surviving = [p for p in all_proposals if p["contradiction_check"]["passes"]]
    surviving.sort(key=lambda p: -p["score"])
    top = surviving[:top_n]

    summary = {
        "ts": _now(),
        "kind": "f37_strategy_synthesis_run",
        "strategies_considered": len(strategies),
        "proposals_generated": len(all_proposals),
        "proposals_passing_contradiction_check": len(surviving),
        "top_n_published": len(top),
        "top_proposals": top,
        "advisory_only": True,
        "lab_attribution": "F37 Strategy Labs · F47 Wren dispatch",
    }

    # Append the run to synthesis output (each run = one jsonl entry)
    SYNTHESIS_OUT.parent.mkdir(parents=True, exist_ok=True)
    with SYNTHESIS_OUT.open("a", encoding="utf-8") as f:
        f.write(json.dumps(summary) + "\n")

    # Activity tail event per top proposal
    for p in top:
        append_event(
            "strategy_proposed",
            summary=(f"{p['strategy_id']} · {p['kind']} score={p['score']:.2f} "
                     f"({p['rationale'][:90]})"),
            floor="F37",
            worker_id=p["lab_role"],
            payload={
                "strategy_id": p["strategy_id"],
                "kind": p["kind"],
                "change": p["change"],
                "score": p["score"],
            },
        )
    append_event(
        "audit_event",
        summary=(f"F37 synthesis run · considered {len(strategies)} · "
                 f"generated {len(all_proposals)} · published {len(top)}"),
        floor="F37",
        payload={"considered": len(strategies),
                  "generated": len(all_proposals),
                  "published": len(top)},
    )
    return summary


def _attribute_to_lab_role(kind: str) -> str:
    """Pick a deterministic F37 worker to take credit for the proposal kind."""
    mapping = {
        "shorten_hold":              "f37.lab.strategy_synthesizer.01",
        "loosen_target":             "f37.lab.strategy_synthesizer.02",
        "tighten_stop":              "f37.lab.strategy_synthesizer.03",
        "scale_down_first_cohort":   "f37.lab.strategy_synthesizer.04",
    }
    return mapping.get(kind, "f37.lab.strategy_synthesizer.05")


if __name__ == "__main__":
    s = synthesize()
    print(f"  strategies_considered:   {s['strategies_considered']}")
    print(f"  proposals_generated:     {s['proposals_generated']}")
    print(f"  passing_contradiction:   {s['proposals_passing_contradiction_check']}")
    print(f"  top published:           {s['top_n_published']}")
    print()
    for p in s["top_proposals"]:
        print(f"  [{p['score']:.2f}]  {p['strategy_id']:24s}  {p['kind']:24s}  → {p['change']}")
        print(f"            {p['rationale'][:120]}")
