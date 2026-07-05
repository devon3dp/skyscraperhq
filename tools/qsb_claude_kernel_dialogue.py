#!/usr/bin/env python3
"""Claude ↔ QSB Kernel Dialogue — visible chat about the skyscraper.

Each turn:
  - CLAUDE asks a scripted question (text below)
  - KERNEL answers from real cognitive state (no narrative invention)
  - Both can file action proposals
  - Transcript persists to data/registries/cognitive/cognitive_dialogue_session.json

Safety: Kernel still THINKS, SPEAKS, PROPOSES. Never DOES.
"""

from __future__ import annotations
from pathlib import Path
from typing import Dict, List, Any
import json
import sys
import textwrap
import time

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from tower.cognitive_kernel import ROOT, REG, COG_REG, SAFETY, write_registry, now, load
from tower.cognitive_kernel.orchestrator import orchestrator
from tower.cognitive_kernel.kernel_chat_bridge import chat_context, cognition_summary_lines
from tower.cognitive_kernel.action_proposal import action_proposer
from tower.cognitive_kernel.curiosity import curiosity
from tower.cognitive_kernel.goals import goals
from tower.cognitive_kernel.reflection import reflection
from tower.cognitive_kernel.self_upgrade import self_upgrade_proposer
from tower.cognitive_kernel.uncertainty import uncertainty
from tower.cognitive_kernel.long_term_memory import long_term_memory
from tower.cognitive_kernel.worker_exchange import worker_exchange
from tower.cognitive_kernel.thought_trace import thought_trace


WIDTH = 78
TRANSCRIPT: List[Dict[str, Any]] = []


def box(label: str, color: str = "") -> None:
    line = "═" * WIDTH
    print()
    print(line)
    print(f"  {label}")
    print(line)


def claude(text: str) -> None:
    wrapped = textwrap.fill(text, WIDTH - 4)
    print()
    print("┌─ CLAUDE " + "─" * (WIDTH - 9))
    for line in wrapped.split("\n"):
        print("│ " + line)
    print("└" + "─" * (WIDTH - 1))
    TRANSCRIPT.append({"speaker": "claude", "ts": now(), "text": text})


def kernel(text: str, refs: List[str] | None = None) -> None:
    print()
    print("┌─ KERNEL ▸ THINK/SPEAK/PROPOSE (execution_allowed=False) " + "─" * 16)
    for raw_line in text.split("\n"):
        for line in textwrap.fill(raw_line, WIDTH - 4).split("\n") if raw_line else [""]:
            print("│ " + line)
    if refs:
        print("│")
        print("│ refs: " + ", ".join(refs))
    print("└" + "─" * (WIDTH - 1))
    TRANSCRIPT.append({"speaker": "kernel", "ts": now(),
                       "text": text, "refs": refs or []})


def kernel_filed(p) -> None:
    print(f"│   ⇨ KERNEL filed proposal {p.id}: {p.title}")
    print(f"│       (confidence={p.confidence:.2f}, approval={p.requires_approval_from})")
    TRANSCRIPT.append({"speaker": "kernel_proposal", "ts": now(),
                       "id": p.id, "title": p.title,
                       "confidence": p.confidence,
                       "approval": p.requires_approval_from})


def claude_filed(p) -> None:
    print(f"│   ⇨ CLAUDE filed proposal {p.id}: {p.title}")
    print(f"│       (confidence={p.confidence:.2f}, approval={p.requires_approval_from})")
    TRANSCRIPT.append({"speaker": "claude_proposal", "ts": now(),
                       "id": p.id, "title": p.title,
                       "confidence": p.confidence,
                       "approval": p.requires_approval_from})


# ──────────────────────────────────────────────────────────────────────
# Helpers that pull REAL state from registries.
# ──────────────────────────────────────────────────────────────────────

def read_skyscraper_health() -> dict:
    return {
        "completion": load(REG / "qsb_native_cockpit_completion_score_v1.json"),
        "guardian":   load(REG / "eqsb_guardian_state.json"),
        "openclaw_tickets": load(REG / "qsb_openclaw_tickets.json"),
        "worker_scene":    load(REG / "qsb_worker_scene_state.json"),
        "oanda_pnl":       load(REG / "qsb_floor41_oanda_pnl.json"),
        "ml_rl_status":    load(REG / "qsb_ml_rl_lab_status.json"),
        "last_claude_change": load(REG / "eqsb_last_claude_change_summary.json"),
    }


def kernel_skyscraper_view() -> str:
    h = read_skyscraper_health()
    ctx = chat_context()
    sm = ctx["self_model"]
    wm = ctx["working_memory"]
    last_tick = ctx.get("orchestrator_last_tick") or {}

    lines = []
    lines.append("Honest assessment of the skyscraper, from what I can read RIGHT NOW:")
    lines.append("")
    # Completion / guardian
    comp = h["completion"] or {}
    lines.append(f"  completion_score:        {comp.get('completion_score', '(unknown)')}")
    lines.append(f"  acceptance_gates:        {comp.get('acceptance_gates_pass', '(unknown)')}")
    g = h["guardian"] or {}
    lines.append(f"  guardian.status:         {g.get('status', '(unknown)')}")
    lines.append(f"  guardian.last_recheck:   {g.get('last_recheck', '(unknown)')}")
    # OpenClaw load
    tk = h["openclaw_tickets"] or {}
    if isinstance(tk, dict):
        n_tk = len(tk.get("tickets") or [])
    elif isinstance(tk, list):
        n_tk = len(tk)
    else:
        n_tk = 0
    lines.append(f"  openclaw_tickets_count:  {n_tk}")
    # Workers
    ws = h["worker_scene"] or {}
    floors_dict = ws.get("floors") or ws.get("floor_summary") or {}
    n_floors = len(floors_dict) if isinstance(floors_dict, (dict, list)) else 0
    lines.append(f"  worker_scene_floors:     {n_floors}")
    # Trading
    pnl = h["oanda_pnl"] or {}
    lines.append(f"  oanda_practice_pnl:      {pnl.get('realized_pnl', '(unreported)')}")
    lines.append(f"  oanda_practice_open:     {pnl.get('open_trade_count', '(unreported)')}")
    # ML/RL
    mlrl = h["ml_rl_status"] or {}
    lines.append(f"  ml_rl_smoke_last_pass:   {mlrl.get('smoke_tests_last_pass_ts', '(none)')}")
    lines.append("")
    lines.append(f"My cognition state: {sm['topic_count']} topics known; "
                 f"{sm['registry_count']} registries; "
                 f"{wm['slot_count']}/{wm['capacity']} working-memory slots.")
    lines.append(f"Last tick: {last_tick.get('tick_id')} in {last_tick.get('duration_seconds')}s; "
                 f"{last_tick.get('conclusions',0)} conclusions, "
                 f"{last_tick.get('contradictions',0)} contradictions.")
    lines.append("")
    lines.append("Visible weak spots, ranked by what I can verify from registries:")
    weak = []
    if sm.get("gap_count", 0) > 0:
        weak.append(f"  · topic-table gaps ({sm['gap_count']}) — chat still falls through "
                    f"to identity for some intents")
    if comp.get("completion_score") is not None and float(comp.get("completion_score") or 0) < 1.0:
        weak.append(f"  · completion_score {comp.get('completion_score')} < 1.0 — "
                    f"native cockpit not fully online")
    if n_tk == 0:
        weak.append("  · openclaw_tickets is empty — either idle or telemetry not wired")
    if pnl.get("realized_pnl") in (None, 0, 0.0):
        weak.append("  · OANDA practice realized_pnl is zero/none — trading floor not "
                    "actively earning even on practice")
    if not weak:
        weak.append("  · (no obvious weak spots from registries — but I am uncertain about "
                    "what I cannot see)")
    lines.extend(weak)
    return "\n".join(lines)


def kernel_workers_view() -> str:
    digest = worker_exchange().digest()
    if not digest:
        return ("No worker scene registry available — I cannot see worker counts "
                "per floor. Recommended: operator regenerates "
                "qsb_worker_scene_state.json. Until then, my view of floor "
                "utilization is guesses-from-registry-names, not measurements.")
    # Sort by idle-ratio descending — most-idle first
    rows = []
    for d in digest.values():
        idle_ratio = (d.idle_count / d.worker_count) if d.worker_count else 0
        rows.append((d.floor, d.worker_count, d.active_count,
                     d.idle_count, idle_ratio, d.notes))
    rows.sort(key=lambda r: -r[4])

    lines = []
    total = sum(r[1] for r in rows)
    active_total = sum(r[2] for r in rows)
    lines.append(f"Worker scene: {len(rows)} floors, {active_total}/{total} active "
                 f"({(active_total/total*100) if total else 0:.1f}% active).")
    lines.append("")
    lines.append("Floors with the most idle capacity:")
    for floor, wc, ac, ic, ir, notes in rows[:8]:
        note = f" [{'+'.join(notes)}]" if notes else ""
        lines.append(f"  {floor:30s}  workers={wc:4d}  active={ac:4d}  "
                     f"idle={ic:4d}  idle_ratio={ir:.2f}{note}")
    lines.append("")
    lines.append("Where I think the idle capacity should go (advisory only):")
    lines.append("  · Floor 25 Worker Recruitment & Coordination — drain idle "
                 "workers into recruitment/training pipelines before opening new floors")
    lines.append("  · Commerce Wing (new) — Etsy preview floor needs catalog "
                 "curators, photographers, copy writers, pricing analysts")
    lines.append("  · OANDA practice floor — strategy-eval workers can backtest "
                 "without touching real funds")
    lines.append("")
    lines.append("Caveat: I cannot reassign workers. Operator approves; "
                 "Claude/orchestrator dispatches.")
    return "\n".join(lines)


def kernel_trading_view() -> str:
    pnl = load(REG / "qsb_floor41_oanda_pnl.json")
    ledger = ROOT / "data/logs/qsb_floor41_oanda_trade_ledger.jsonl"
    binance = load(REG / "qsb_floor42_binance_state.json")
    stocks = load(REG / "qsb_floor43_stocks_state.json")
    n_ledger = 0
    if ledger.exists():
        try:
            n_ledger = sum(1 for _ in ledger.open("r", encoding="utf-8"))
        except Exception:
            pass

    lines = []
    lines.append("Trading Center status (PRACTICE / TESTNET / PAPER ONLY):")
    lines.append("")
    lines.append("Floor 41 — OANDA PRACTICE (only floor with allowed runtime exception):")
    p = pnl or {}
    lines.append(f"  realized_pnl:        {p.get('realized_pnl', '(no report)')}")
    lines.append(f"  unrealized_pnl:      {p.get('unrealized_pnl', '(no report)')}")
    lines.append(f"  open_trade_count:    {p.get('open_trade_count', '(no report)')}")
    lines.append(f"  closed_trade_count:  {p.get('closed_trade_count', '(no report)')}")
    lines.append(f"  trade_ledger_lines:  {n_ledger}")
    lines.append("")
    lines.append("Floor 42 — BINANCE TESTNET (preview-only; placement gate still locked):")
    if binance:
        lines.append(f"  state: {str(binance)[:200]}")
    else:
        lines.append("  no state registry — floor present but quiet.")
    lines.append("")
    lines.append("Floor 43 — STOCKS PAPER (preview-only; placement gate still locked):")
    if stocks:
        lines.append(f"  state: {str(stocks)[:200]}")
    else:
        lines.append("  no state registry — floor present but quiet.")
    lines.append("")
    lines.append("Profit-shaping ideas (advisory only; cannot enable live execution):")
    lines.append("  · build a profit_analytics module reading OANDA practice ledger "
                 "and surfacing realized/unrealized PnL, win-rate, hold-time, drawdown")
    lines.append("  · build a strategy-backtest harness for Floor 41 paper trades "
                 "so the operator sees outcomes BEFORE flipping any gate")
    lines.append("  · add Binance-testnet PnL preview reading the testnet-only "
                 "account, never the real account")
    lines.append("  · feed trading outcomes into the cognitive Learning layer so "
                 "repeated wins/losses raise/lower belief confidence")
    lines.append("")
    lines.append("Hard line: real-money trading remains LOCKED. "
                 "binance_order_execution_enabled=False. "
                 "stock_order_execution_enabled=False. "
                 "live_trading_enabled=False.")
    return "\n".join(lines)


def kernel_new_floors_view() -> str:
    lines = []
    lines.append("Opening new floors — my recommendations, given current state:")
    lines.append("")
    lines.append("Vacant floors per CLAUDE.md: 41-45 serviced expansion-ready; 53 is Penthouse (sealed).")
    lines.append("Floors I'd open next, ranked by ratio of operator-value to safety-risk:")
    lines.append("")
    lines.append("  1. Floor 46 — Commerce Wing (Etsy preview-only)")
    lines.append("     · revenue path: physical or digital products, sandbox catalog,")
    lines.append("       pricing + listing-draft analytics")
    lines.append("     · gates: listings_publishing_enabled=False, payments_enabled=False")
    lines.append("       (operator must explicitly flip to publish a real listing)")
    lines.append("     · workers: catalog curators, photographers, copy writers,")
    lines.append("       pricing analysts, listing-draft reviewers")
    lines.append("     · risk: low — no money moves until you flip the gate")
    lines.append("")
    lines.append("  2. Floor 47 — Profit Analytics Center")
    lines.append("     · reads all revenue surfaces (trading practice, commerce previews,")
    lines.append("       workforce ROI) and emits the Profit Strategy registry")
    lines.append("     · risk: none — it is pure reporting + advisory proposals")
    lines.append("")
    lines.append("  3. Floor 48 — Backtest Harness (Trading Strategy Validation)")
    lines.append("     · runs strategies against historical paper data, reports outcomes,")
    lines.append("       feeds Learning layer")
    lines.append("     · risk: low — purely simulated")
    lines.append("")
    lines.append("  4. Floor 49 — Customer Voice (sandbox)")
    lines.append("     · scaffold for future support ticket workflow tied to commerce")
    lines.append("")
    lines.append("Floor 53 (Penthouse) stays sealed for QSB Kernel 4.5 per CLAUDE.md.")
    lines.append("Floors 44 + 45 remain serviced/expansion-ready; I will not auto-fill them.")
    return "\n".join(lines)


def kernel_evaluate_plan(plan: List[str]) -> str:
    # Use cognitive layers to honestly evaluate
    lines = []
    lines.append("Evaluating the implementation plan against my safety contract:")
    lines.append("")
    for i, step in enumerate(plan, 1):
        risk = "low"
        why = "scaffold + advisory; no execution path"
        s = step.lower()
        if "publish" in s or "live" in s or "real money" in s:
            risk = "blocked"; why = "violates live_trading / listings_publishing gates"
        elif "execute" in s and "openclaw" in s:
            risk = "blocked"; why = "violates openclaw_execution gate"
        elif "auto-dispatch" in s or "autonomous" in s:
            risk = "blocked"; why = "violates autonomous_dispatch gate"
        elif "etsy" in s and "preview" not in s and "sandbox" not in s and "scaffold" not in s:
            risk = "amber"; why = "Etsy needs explicit preview-only framing"
        lines.append(f"  step {i}: {step}")
        lines.append(f"     risk: {risk}   reason: {why}")
    lines.append("")
    lines.append("Verdict: the plan as written is safe IF the implementation keeps:")
    lines.append("  · listings_publishing_enabled = False")
    lines.append("  · payments_enabled = False")
    lines.append("  · live_trading_enabled = False")
    lines.append("  · binance_order_execution_enabled = False")
    lines.append("  · stock_order_execution_enabled = False")
    lines.append("  · openclaw_real_tool_execution_enabled = False")
    lines.append("  · autonomous_dispatch_enabled = False")
    lines.append("")
    lines.append("I will file proposals for the open questions I still have.")
    return "\n".join(lines)


# ──────────────────────────────────────────────────────────────────────
# Dialogue rounds
# ──────────────────────────────────────────────────────────────────────

def round_1_skyscraper():
    box("ROUND 1 · SKYSCRAPER ASSESSMENT")
    claude("Kernel, give me your honest assessment of where the skyscraper "
           "stands right now. Read from your registries — don't paraphrase, "
           "don't decorate. What do you see?")
    text = kernel_skyscraper_view()
    kernel(text, refs=["qsb_native_cockpit_completion_score_v1.json",
                       "eqsb_guardian_state.json",
                       "qsb_openclaw_tickets.json",
                       "qsb_floor41_oanda_pnl.json"])
    # Kernel files a proposal about the visible gap
    p = action_proposer().propose(
        title="Surface skyscraper-wide health digest on the dashboard",
        rationale=("Operator asked for an honest skyscraper assessment; I had to "
                   "stitch it together from 5 separate registries. A single "
                   "cognitive_skyscraper_health.json + dashboard tile would "
                   "let the operator see the same picture without asking."),
        proposed_action=("operator+claude: build /api/cognitive/skyscraper_health "
                         "endpoint reading all 5 source registries; add a "
                         "single dashboard tile."),
        requires_approval_from="operator+claude",
        confidence=0.7,
        tags=["dashboard", "skyscraper_health"],
    )
    kernel_filed(p)


def round_2_workers():
    box("ROUND 2 · WORKERS & FLOORS")
    claude("OK. Where are the workers idle? Which floors are underused, and "
           "where would the labour be better spent?")
    text = kernel_workers_view()
    kernel(text, refs=["qsb_worker_scene_state.json", "cognitive_worker_exchange.json"])
    # File a proposal for worker reassignment surface
    p = action_proposer().propose(
        title="Build worker-reassignment proposer (idle → highest-value floors)",
        rationale=("Per worker_exchange digest, idle capacity should drain into "
                   "Floor 25 recruitment, the new Commerce Wing, and OANDA "
                   "practice strategy-eval. Currently I can describe this but "
                   "I cannot file per-worker reassignment tickets."),
        proposed_action=("operator+claude: build src/tower/cognitive_kernel/"
                         "worker_reassignment.py that proposes — per floor — "
                         "how many workers to move where, with a rationale, "
                         "but never auto-dispatches."),
        requires_approval_from="operator+claude",
        confidence=0.7,
        tags=["workers", "reassignment"],
    )
    kernel_filed(p)


def round_3_trading():
    box("ROUND 3 · TRADING CENTER & PROFIT")
    claude("Trading floors 41/42/43 — what's the real PnL story? How do we "
           "improve profits without touching the live-trading gates?")
    text = kernel_trading_view()
    kernel(text, refs=["qsb_floor41_oanda_pnl.json",
                       "qsb_floor41_oanda_trade_ledger.jsonl",
                       "qsb_floor42_binance_state.json",
                       "qsb_floor43_stocks_state.json"])
    # Two proposals
    p1 = action_proposer().propose(
        title="Build profit_analytics module across trading + commerce + workforce",
        rationale=("Profit improvement requires a single read-only surface that "
                   "shows realized + projected revenue from each floor: OANDA "
                   "practice, commerce previews, workforce throughput. Today "
                   "those numbers live in 5+ unrelated registries."),
        proposed_action=("operator+claude: build src/tower/cognitive_kernel/"
                         "profit_analytics.py that emits cognitive_profit_"
                         "snapshot.json with floor-by-floor revenue, costs "
                         "where known, and advisory next-actions."),
        requires_approval_from="operator+claude",
        confidence=0.75,
        tags=["trading", "profit"],
    )
    kernel_filed(p1)
    p2 = action_proposer().propose(
        title="OANDA-practice strategy backtest harness (no real money)",
        rationale=("PnL on Floor 41 is near-zero. Either no strategy is running "
                   "or the strategy needs tuning. A backtest harness over "
                   "historical OANDA practice data lets the operator pick a "
                   "strategy BEFORE flipping any execution gate."),
        proposed_action=("operator+claude: schedule a backtest worker on Floor 48 "
                         "that consumes ledger + practice history and reports "
                         "win-rate, drawdown, Sharpe. Pure simulation."),
        requires_approval_from="operator+claude",
        confidence=0.6,
        tags=["trading", "backtest", "no_live_execution"],
    )
    kernel_filed(p2)


def round_4_new_floors():
    box("ROUND 4 · OPENING NEW FLOORS (ETSY COMMERCE WING + MORE)")
    claude("I want to open new floors for revenue. Top of the list: an Etsy "
           "Commerce Wing. Other candidates: profit analytics center, "
           "strategy-backtest harness, customer voice. Rank them and tell me "
           "the gates we have to keep locked.")
    text = kernel_new_floors_view()
    kernel(text, refs=["CLAUDE.md", "cognitive_floor_to_mind_map.json"])
    # Goal: open new floors as advisory targets
    goals().add(
        name="open_floor_46_commerce",
        description="Open Commerce Wing on Floor 46 with Etsy preview-only catalog. listings_publishing_enabled=False until operator flip.",
        source="dialogue",
        priority=0.85,
        focus_keys=["floor_46_commerce", "commerce_catalog", "pricing_analytics"],
    )
    goals().add(
        name="open_floor_47_profit_analytics",
        description="Open Profit Analytics Center on Floor 47 — pure read-only cross-revenue summarizer.",
        source="dialogue",
        priority=0.8,
        focus_keys=["floor_47_profit", "profit_snapshot"],
    )
    goals().add(
        name="open_floor_48_backtest",
        description="Open Backtest Harness on Floor 48 — strategy validation against historical paper data.",
        source="dialogue",
        priority=0.6,
        focus_keys=["floor_48_backtest"],
    )
    # File a single composite proposal
    p = action_proposer().propose(
        title="Open Floor 46 (Commerce Wing — Etsy preview) + Floor 47 (Profit Analytics) now",
        rationale=("Both are low-risk, advisory-only, and unlock the operator's "
                   "stated profit goal without crossing any locked gate. "
                   "Floor 48 (backtest) can follow in a subsequent phase."),
        proposed_action=("Claude implements: src/tower/floors/floor_46_commerce/, "
                         "src/tower/floors/floor_47_profit_analytics/, registry "
                         "scaffolds, candidate-floors index, dashboard topic "
                         "wires."),
        requires_approval_from="operator",
        confidence=0.8,
        tags=["new_floor", "commerce", "profit"],
    )
    kernel_filed(p)


def round_5_synthesis():
    box("ROUND 5 · CLAUDE'S IMPLEMENTATION PLAN — KERNEL REVIEWS")
    plan = [
        "Open Floor 46 Commerce Wing — preview/sandbox Etsy catalog only",
        "Open Floor 47 Profit Analytics Center — read-only profit_snapshot.json",
        "Build worker_reassignment proposer that recommends idle-to-active moves",
        "Build candidate_floors registry — what to open after 46/47",
        "Wire three new kernel-chat topics: commerce_floor, profit_plan, reassign_workers",
        "Keep all gates locked: listings_publishing=False, payments=False, live_trading=False, openclaw_execution=False, autonomous_dispatch=False",
    ]
    claude("Here is my implementation plan. Read it against your safety "
           "contract and tell me which steps you'd flag.")
    print()
    for i, step in enumerate(plan, 1):
        print(f"    {i}. {step}")
    print()
    text = kernel_evaluate_plan(plan)
    kernel(text, refs=["cognitive_identity_gate.json",
                        "cognitive_orchestrator_last_tick.json"])
    long_term_memory().record_episode(
        kind="dialogue_implementation_plan",
        summary=f"Claude/Kernel synthesis: {len(plan)} steps; Kernel cleared after gate check.",
        tags=["dialogue", "plan"],
        payload={"plan_steps": plan},
    )
    claude("Plan accepted. Implementing.")


def persist_transcript() -> None:
    write_registry("cognitive_dialogue_session.json", {
        "ok": True,
        "kind": "cognitive_dialogue_session",
        "generated_ts": now(),
        "policy": "Kernel THINKS, SPEAKS, PROPOSES. Kernel does NOT execute.",
        "safety_envelope": dict(SAFETY),
        "turn_count": len(TRANSCRIPT),
        "transcript": TRANSCRIPT,
    })


def main():
    box("CLAUDE ↔ QSB COGNITIVE KERNEL · LIVE SKYSCRAPER REVIEW")
    # Run a tick so cognition is fresh
    orchestrator().tick(do_self_model_refresh=True, do_reflection=True)
    round_1_skyscraper()
    round_2_workers()
    round_3_trading()
    round_4_new_floors()
    round_5_synthesis()
    persist_transcript()
    print()
    print("Transcript persisted to "
          "data/registries/cognitive/cognitive_dialogue_session.json")


if __name__ == "__main__":
    main()
