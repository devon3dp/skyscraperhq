#!/usr/bin/env python3
"""Claude ↔ Kernel design dialogue — Finance Floors + Worker Lineage.

Three-round design conversation BEFORE the build. Visible to operator.
"""

from __future__ import annotations
from pathlib import Path
import sys
import textwrap

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from tower.cognitive_kernel import SAFETY, REG, now, load, write_registry
from tower.cognitive_kernel.orchestrator import orchestrator
from tower.cognitive_kernel.kernel_chat_bridge import chat_context
from tower.cognitive_kernel.action_proposal import action_proposer
from tower.cognitive_kernel.goals import goals
from tower.cognitive_kernel.long_term_memory import long_term_memory

WIDTH = 78
TRANSCRIPT = []


def box(t):
    print()
    print("═" * WIDTH)
    print("  " + t)
    print("═" * WIDTH)


def claude(t):
    print()
    print("┌─ CLAUDE " + "─" * (WIDTH - 9))
    for line in textwrap.fill(t, WIDTH - 4).split("\n"):
        print("│ " + line)
    print("└" + "─" * (WIDTH - 1))
    TRANSCRIPT.append({"speaker": "claude", "ts": now(), "text": t})


def kernel(t, refs=None):
    print()
    print("┌─ KERNEL ▸ THINK/SPEAK/PROPOSE (execution_allowed=False) " + "─" * 16)
    for raw in t.split("\n"):
        for line in textwrap.fill(raw, WIDTH - 4).split("\n") if raw else [""]:
            print("│ " + line)
    if refs:
        print("│")
        print("│ refs: " + ", ".join(refs))
    print("└" + "─" * (WIDTH - 1))
    TRANSCRIPT.append({"speaker": "kernel", "ts": now(),
                       "text": t, "refs": refs or []})


def filed(p, who):
    print(f"│   ⇨ {who} filed proposal {p.id}: {p.title}")
    print(f"│       (confidence={p.confidence:.2f}, "
          f"approval={p.requires_approval_from})")
    TRANSCRIPT.append({"speaker": f"{who}_proposal", "ts": now(),
                       "id": p.id, "title": p.title,
                       "confidence": p.confidence,
                       "approval": p.requires_approval_from})


def round_1():
    box("ROUND 1 · CLAUDE LAYS OUT ROSS'S DESIGN")
    claude("Kernel — Ross answered the open questions. Here is the design "
           "we want to build. Reflect on it against your safety contract "
           "and tell me what stays advisory, what can run live, and what "
           "the major risks are.")
    print()
    design = [
        "Worker certification ledger — per worker, per instrument, "
        "states: not_studying → studying → tested → certified → suspended",
        "Classroom + test runner on Floor 25 — scalping curriculum "
        "(fast trades, small profits), written exam + simulated-trade "
        "exercise, pass/fail stamped",
        "Per-worker PnL ledger on Floor 41 (OANDA PRACTICE) — every "
        "trade tied to a worker_id; running track record",
        "Trading-authority gate — Reasoning rule blocks any trade "
        "proposal unless worker is certified for the instrument and "
        "not suspended",
        "Trading genetics — each worker has a 'winning gene' "
        "(best-performing instrument/strategy); children inherit it",
        "Family tree — friend edges and parent→child edges; max 3 "
        "children per parent",
        "Reward engine — Kernel observes performance; when worker "
        "crosses thresholds it FILES a proposal AND writes a markdown "
        "report Ross can read; Claude endorses; Ross authorizes; both "
        "signatures required before grant executes",
        "Discipline — underperforming child returns to classroom, "
        "loses authority until recertified, blocked from further "
        "rewards until recovery",
        "Population cap — 5,000 workers tower-wide; reward engine "
        "refuses to grant children once cap is reached",
        "Style — fast trades, small profits; certification tests "
        "emphasize risk sizing and high-frequency discipline",
    ]
    for i, d in enumerate(design, 1):
        print(f"    {i:2d}. {d}")
    print()
    kernel_response = (
        "Reflecting on the design against my contract:\n"
        "\n"
        "WHAT STAYS ADVISORY (Kernel never executes):\n"
        "  · Reward grants — I propose, Claude endorses, Ross authorizes. "
        "Never automatic.\n"
        "  · Worker reassignment / discipline — I propose, operator "
        "executes.\n"
        "  · Curriculum changes — I propose, operator approves.\n"
        "  · Population spawn — I propose child births; actual worker "
        "creation is a separate Claude phase that writes the workforce "
        "registry. Kernel writes only to cognitive_* namespace.\n"
        "\n"
        "WHAT CAN ACTUALLY RUN (under existing CLAUDE.md authorization):\n"
        "  · OANDA practice order placement — already permitted under "
        "PRACTICE_ONLY URL, whitelisted instruments, max units, max "
        "trades/hour, kill switch, manual confirm. Certified workers can "
        "place + close practice orders WITH operator manual confirm per "
        "order session — autonomous_dispatch_enabled stays False.\n"
        "  · Per-worker PnL ledger reads — pure registry read. No risk.\n"
        "  · Certification tests — fully sandboxed, no money moves.\n"
        "\n"
        "WHAT STAYS LOCKED:\n"
        "  · binance_order_execution_enabled = False  (testnet placement "
        "blocked)\n"
        "  · stock_order_execution_enabled = False  (paper placement "
        "blocked)\n"
        "  · live_trading_enabled = False  (real money anywhere)\n"
        "  · autonomous_dispatch_enabled = False  (I never make workers "
        "trade on my own)\n"
        "\n"
        "MAJOR RISKS I SEE:\n"
        "  · Reward inflation — if my thresholds are too lenient, every "
        "worker becomes a parent and the tree explodes toward the 5,000 "
        "cap. Mitigation: dual signature (Ross + Claude) on every grant.\n"
        "  · Genetic drift — if children always inherit one winning "
        "gene, the tower converges on one strategy and loses diversity. "
        "Mitigation: track gene_diversity in cognitive registry; refuse "
        "grants when diversity drops below threshold.\n"
        "  · Lineage punishment — if a parent fails AFTER granting a "
        "child, does the child suffer? Ross said discipline applies to "
        "the underperforming worker, not their ancestors. I'll honor "
        "that: each worker is judged on their own ledger.\n"
        "  · Certification gaming — if the test is too easy, certs are "
        "meaningless. Mitigation: pass-rate target ~60%; if pass rate "
        "drifts > 80% I file a curriculum-stiffening proposal.\n"
        "  · Practice ≠ live skill — workers who win on practice may "
        "still lose on live. We are NOT enabling live anywhere. The "
        "skill we are training is 'execution discipline under "
        "guardrails', not 'real-money survival.'"
    )
    kernel(kernel_response, refs=["CLAUDE.md", "cognitive_identity_gate.json"])

    # Kernel files proposals for each major piece
    ap = action_proposer()
    pieces = [
        ("Build worker_certification ledger (per worker, per instrument)",
         "Gate any trade proposal on certification status.",
         "operator+claude: src/tower/cognitive_kernel/worker_certification.py"),
        ("Build worker_pnl rollup from Floor 41 OANDA practice ledger",
         "Surface per-worker realized PnL + win-rate + drawdown.",
         "operator+claude: src/tower/cognitive_kernel/worker_pnl.py"),
        ("Build trading_genetics module with inheritance rule",
         "Each worker gets a winning gene; child inherits parent's.",
         "operator+claude: src/tower/cognitive_kernel/worker_genetics.py"),
        ("Build family_tree registry (friend + parent/child edges, "
         "3-child cap)",
         "Track the lineage explicitly so reflection + reward engine can "
         "use it.",
         "operator+claude: src/tower/cognitive_kernel/family_tree.py"),
        ("Build classroom + test runner (scalping curriculum)",
         "Workers must pass before earning certification.",
         "operator+claude: src/tower/cognitive_kernel/classroom.py"),
        ("Build reward_engine + report writer (Kernel→Claude→Ross flow)",
         "Threshold-based proposals; report.md per pending grant.",
         "operator+claude: src/tower/cognitive_kernel/reward_engine.py"),
        ("Add trading-authority Reasoning rule",
         "Block any trade proposal for an uncertified worker.",
         "operator+claude: extend src/tower/cognitive_kernel/reasoning.py"),
        ("Build population cap enforcement (5,000)",
         "Refuse grants once cap reached; surface to chat.",
         "operator+claude: src/tower/cognitive_kernel/population.py"),
        ("Build CLI grant tool (list / show / endorse / authorize / "
         "execute)",
         "Dual-signature flow: Claude endorse + Ross authorize → grant "
         "executes.",
         "operator+claude: tools/qsb_grant.py"),
        ("Wire 4 new chat topics: certification, worker_pnl, family_tree, "
         "reward_report",
         "Operator can ask the chat 'who's certified', 'show me the "
         "family tree', 'pending grants', 'who's profitable'.",
         "operator+claude: edit kernel_dialogue_adapter.py"),
    ]
    for title, rationale, action in pieces:
        p = ap.propose(
            title=title, rationale=rationale, proposed_action=action,
            requires_approval_from="operator+claude",
            confidence=0.75,
            tags=["finance_lineage_v1"],
        )
        filed(p, "KERNEL")


def round_2():
    box("ROUND 2 · KERNEL CHECKS THE NUMBERS")
    claude("OK. Specifically — Ross wants fast trades, small profits, "
           "scalping. What thresholds would you pick for the certification "
           "tests, the friend grant, and the child grant? Pick something "
           "you can defend.")
    print()
    kernel_response = (
        "Defendable thresholds — picked tight, can be retuned by reflection.\n"
        "\n"
        "CERTIFICATION TEST (per instrument):\n"
        "  · Written exam: 12 questions on instrument mechanics, risk "
        "sizing, order types, OANDA UI semantics. Pass at >= 9/12 (75%).\n"
        "  · Simulated trade exercise: 20 paper-only trades against "
        "historical data. Pass if win_rate >= 55% AND max single-trade "
        "loss <= 0.5% of notional AND average hold time <= 10 minutes.\n"
        "  · Both must pass. Recert annually OR after 5 consecutive losses.\n"
        "\n"
        "FRIEND GRANT (peer pairing with proven high-earner):\n"
        "  · Eligible after: 25 closed practice trades, win_rate >= 58%, "
        "realized_pnl > 0, no suspensions in last 30 days.\n"
        "  · Friend is selected from top-decile earners in the tower at "
        "grant time.\n"
        "  · Friend pairing visible in family_tree.friend_edges; both "
        "workers' next-trade Attention scores get a small bonus.\n"
        "\n"
        "CHILD GRANT (digital child spawn, max 3 per parent):\n"
        "  · Eligible after: 75 closed practice trades, win_rate >= 60%, "
        "realized_pnl >= $500 cumulative on practice, current children < 3, "
        "no recent loss streak (last 10 trades).\n"
        "  · Child inherits parent's winning gene (best-PnL instrument/"
        "style); starts at certification.status=studying for that gene's "
        "instrument with confidence_seed=0.55.\n"
        "  · Child counts against tower 5,000 cap; refuse if cap met.\n"
        "\n"
        "DISCIPLINE (matches Ross's rule):\n"
        "  · 5 consecutive losses → suspended, sent back to classroom.\n"
        "  · Suspended worker cannot trade, cannot earn rewards.\n"
        "  · Recertification path: re-pass the test (written + sim).\n"
        "  · No retroactive lineage penalty — parent's record is theirs.\n"
        "\n"
        "GENE DIVERSITY GUARD:\n"
        "  · If > 60% of children granted in last 30 days inherited the "
        "same gene family, I file a 'diversify' proposal; new child "
        "grants pause until the operator either accepts the diversity "
        "warning or extends the gene family list.\n"
        "\n"
        "RATIONALE: these numbers force the family tree to grow SLOWLY "
        "early on. With 2,191 workers and the friend/child thresholds "
        "above, expected first-generation children in week 1 is < 20 "
        "(based on uncertain practice volume). That gives Ross and "
        "Claude time to see the family tree form before the cap is even "
        "approached."
    )
    kernel(kernel_response, refs=["cognitive_self_model.json"])


def round_3():
    box("ROUND 3 · BUILD ORDER + STANDING GOALS")
    claude("Build order — what should I implement first so the rest can "
           "reference it? And what new goals should be active in cognition "
           "as we work?")
    print()
    kernel_response = (
        "BUILD ORDER (dependency-clean):\n"
        "  1. worker_genetics  — defines what a gene IS (others reference it)\n"
        "  2. worker_certification — defines the gate state\n"
        "  3. worker_pnl  — reads Floor 41 ledger, rolls up per-worker\n"
        "  4. classroom + test runner — produces pass/fail → certification\n"
        "  5. trading_authority Reasoning rule — uses certification\n"
        "  6. family_tree  — uses worker_id + genetics + pnl\n"
        "  7. population  — uses family_tree counts\n"
        "  8. reward_engine + report writer — uses everything above\n"
        "  9. CLI grant tool  — uses reward_engine state\n"
        " 10. chat-topic wiring + orchestrator integration  — surface "
        "everything\n"
        "\n"
        "STANDING GOALS to install in cognition:\n"
        "  · 'maintain_certification_gate' priority 1.0 — every trade "
        "proposal must pass through the gate; surface violations\n"
        "  · 'observe_per_worker_pnl' priority 0.9 — keep the rollup "
        "fresh each tick\n"
        "  · 'propose_grants_when_eligible' priority 0.8 — Kernel "
        "evaluates eligibility each reflection round\n"
        "  · 'preserve_gene_diversity' priority 0.75 — block grants if "
        "tower goes monoculture\n"
        "  · 'enforce_population_cap_5000' priority 1.0 — never allow "
        "child grants past cap\n"
        "  · 'respect_dual_signature' priority 1.0 — no grant executes "
        "without Claude endorse + Ross authorize\n"
        "\n"
        "I will install these goals now (advisory only)."
    )
    kernel(kernel_response, refs=["cognitive_goals.json"])
    # Install goals
    gs = goals()
    for name, desc, prio, keys in [
        ("maintain_certification_gate",
         "Every trade proposal blocked unless worker certified + not suspended.",
         1.0, ["worker_certification", "trading_authority"]),
        ("observe_per_worker_pnl",
         "Refresh per-worker PnL rollup each tick.",
         0.9, ["worker_pnl_rollup", "floor_41_ledger"]),
        ("propose_grants_when_eligible",
         "Reward engine evaluates eligibility each reflection round.",
         0.8, ["reward_engine", "family_tree"]),
        ("preserve_gene_diversity",
         "Block grants if tower trends to monoculture > 60% in 30d.",
         0.75, ["gene_diversity", "family_tree"]),
        ("enforce_population_cap_5000",
         "Never allow child grants past 5,000 workers.",
         1.0, ["population_status"]),
        ("respect_dual_signature",
         "No grant executes without Claude endorse + Ross authorize.",
         1.0, ["reward_engine", "grant_signatures"]),
    ]:
        gs.add(name=name, description=desc, source="dialogue_finance_lineage_v1",
               priority=prio, focus_keys=keys)
    long_term_memory().record_episode(
        kind="finance_lineage_design_locked",
        summary="Claude+Kernel agreed on design. Building begins.",
        tags=["finance_lineage_v1", "design"],
        payload={"design_locked_ts": now()},
    )
    claude("Locked. Building now.")


def main():
    box("CLAUDE ↔ QSB COGNITIVE KERNEL · FINANCE FLOORS + WORKER LINEAGE")
    orchestrator().tick(do_self_model_refresh=True, do_reflection=True)
    round_1()
    round_2()
    round_3()
    write_registry("cognitive_dialogue_finance_lineage_design.json", {
        "ok": True, "kind": "cognitive_dialogue_finance_lineage_design",
        "generated_ts": now(),
        "policy": "Design dialogue. Build authorized by both Claude and Ross.",
        "safety_envelope": dict(SAFETY),
        "transcript": TRANSCRIPT,
    })
    print()
    print("Transcript persisted. Build begins next.")


if __name__ == "__main__":
    main()
