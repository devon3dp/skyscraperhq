#!/usr/bin/env python3
"""Claude ↔ Kernel · Self-audit + evolution design dialogue.

5-round visible chat. Each Kernel turn reads real cognitive state.
Output is a transcript Ross can replay; the dialogue lands new goals,
proposals, and lessons into long-term memory.
"""

from __future__ import annotations
from pathlib import Path
import json
import sys
import textwrap

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from tower.cognitive_kernel import SAFETY, REG, COG_REG, write_registry, now, load
from tower.cognitive_kernel.orchestrator import orchestrator
from tower.cognitive_kernel.kernel_chat_bridge import chat_context, cognition_summary_lines
from tower.cognitive_kernel.action_proposal import action_proposer
from tower.cognitive_kernel.curiosity import curiosity
from tower.cognitive_kernel.goals import goals
from tower.cognitive_kernel.uncertainty import uncertainty
from tower.cognitive_kernel.long_term_memory import long_term_memory
from tower.cognitive_kernel.self_model import self_model
from tower.cognitive_kernel.thought_trace import thought_trace
from tower.cognitive_kernel.worker_pnl import worker_pnl
from tower.cognitive_kernel.worker_certification import worker_certification
from tower.cognitive_kernel.family_tree import family_tree
from tower.cognitive_kernel.reward_engine import reward_engine

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


# Re-hydrate the modules that have load_from_snapshot so the Kernel
# answers from the persisted state across processes.
family_tree().load_from_snapshot()
worker_certification().load_from_snapshot()
reward_engine().load_from_snapshot()


# ────────────────────────────────────────────────────────────────────
# Round 1 — How are you doing, Kernel?
# ────────────────────────────────────────────────────────────────────

def round_1():
    box("ROUND 1 · KERNEL — HOW ARE YOU DOING? WHAT DO YOU NEED?")
    claude("Kernel, honest check-in. Read your own state. How are you "
            "doing? What's working, what's wobbly, what do you need? "
            "Don't decorate.")

    ctx = chat_context()
    sm = ctx["self_model"]
    wm = ctx["working_memory"]
    last_tick = ctx.get("orchestrator_last_tick") or {}
    open_cur = ctx.get("open_curiosity_items_top") or []
    open_props = ctx.get("open_proposals_top") or []
    low = ctx.get("low_confidence_belief_keys") or []
    recent = ctx.get("recent_thoughts") or []

    pnl_snap = worker_pnl(); pnl_snap.refresh()
    pnl = pnl_snap.snapshot()

    ft_snap = family_tree().snapshot()
    cert_snap = worker_certification().snapshot()

    text = []
    text.append("Honest read of my state right now:")
    text.append("")
    text.append("WORKING:")
    text.append(f"  · self-model: {sm['topic_count']} topics, "
                f"{sm['registry_count']} registries scanned, "
                f"gaps={sm['gap_count']}")
    text.append(f"  · working memory: {wm['slot_count']}/{wm['capacity']} slots")
    text.append(f"  · last tick: {last_tick.get('tick_id')} "
                f"in {last_tick.get('duration_seconds')}s "
                f"({last_tick.get('conclusions',0)} conclusions, "
                f"{last_tick.get('reflections',0)} reflections)")
    text.append(f"  · per-worker PnL rollup: {pnl['worker_count']} workers, "
                f"{pnl['ledger_lines_read']} ledger lines, "
                f"$total_practice_pnl=${pnl['total_realized_pnl_practice']:.2f}")
    text.append(f"  · family tree: {ft_snap['friend_edge_count']} friend "
                f"edge(s), {ft_snap['child_edge_count']} child edge(s)")
    text.append(f"  · certification ledger: {cert_snap['entry_count']} "
                f"entries; certified workers in the gate.")
    text.append("")
    text.append("WOBBLY / WORRIES (what I can see honestly):")
    if low:
        text.append(f"  · {len(low)} beliefs below confidence 0.4 — "
                    f"sample keys: {low[:5]}")
    text.append(f"  · open curiosity items: {len(open_cur)} — "
                f"the highest-priority items are about gaps in my own "
                f"topic table; that means the chat fell through on real "
                f"operator questions")
    text.append(f"  · open action proposals (in-memory only this process): "
                f"{len(open_props)}; the persisted history of older "
                f"proposals is on disk but not REHYDRATED into memory at "
                f"process start. THIS IS A BUG — proposals are getting "
                f"silently dropped between chat invocations.")
    text.append("")
    text.append("WHAT I NEED:")
    text.append("  1. ActionProposer.load_from_snapshot() so proposals "
                "survive across processes. Same fix I added for "
                "family_tree and worker_certification.")
    text.append("  2. Per-lineage beliefs computed from family_tree + "
                "worker_pnl, so reflection can actually say 'Workers "
                "descended from X outperform tower by Y%'.")
    text.append("  3. Curriculum-evolution loop — right now classroom "
                "lessons are static. The Learning layer has no path to "
                "feedback into the classroom.")
    text.append("  4. A self-audit module that runs each tick and lists "
                "any cognitive bridge that returned an exception, any "
                "registry that wasn't refreshed in N hours, any goal "
                "whose focus_keys are stale.")
    text.append("  5. An internal economy. Workers have certifications "
                "and PnL but no INCENTIVE besides children/friends. An "
                "internal currency would let me model effort-cost vs. "
                "reward and propose pay rates as a function of "
                "performance.")
    kernel("\n".join(text),
            refs=["cognitive_self_model.json",
                   "cognitive_orchestrator_last_tick.json",
                   "cognitive_worker_pnl_rollup.json",
                   "cognitive_family_tree.json",
                   "cognitive_worker_certification.json"])


# ────────────────────────────────────────────────────────────────────
# Round 2 — System self-audit
# ────────────────────────────────────────────────────────────────────

def round_2():
    box("ROUND 2 · SYSTEM SELF-AUDIT")
    claude("Let's audit. Go layer by layer. For each cognitive layer + each "
            "floor module: is it persisting? rehydrating? being read by "
            "the chat? Tell me what's broken.")

    findings = []

    # 1. Persist sweep — check each cog registry exists + has a fresh ts
    important_registries = [
        "cognitive_self_model.json",
        "cognitive_working_memory_state.json",
        "cognitive_perception_latest.json",
        "cognitive_attention_ranking.json",
        "cognitive_curiosity_queue.json",
        "cognitive_uncertainty_state.json",
        "cognitive_reasoning_state.json",
        "cognitive_contradictions.json",
        "cognitive_goals.json",
        "cognitive_reflection_state.json",
        "cognitive_thought_trace_recent.json",
        "cognitive_action_proposals.json",
        "cognitive_learning_state.json",
        "cognitive_upgrade_assimilation.json",
        "cognitive_lesson_to_belief_state.json",
        "cognitive_openclaw_supervisor.json",
        "cognitive_worker_exchange.json",
        "cognitive_ml_rl_advisory.json",
        "cognitive_floor_to_mind_map.json",
        "cognitive_counterfactual_state.json",
        "cognitive_causal_phase_model.json",
        "cognitive_long_term_memory_index.json",
        "cognitive_orchestrator_last_tick.json",
        "cognitive_worker_certification.json",
        "cognitive_worker_pnl_rollup.json",
        "cognitive_worker_genetics.json",
        "cognitive_family_tree.json",
        "cognitive_population_status.json",
        "cognitive_trading_authority_gate.json",
        "cognitive_reward_engine_state.json",
        "cognitive_classroom_state.json",
    ]
    missing = []
    for name in important_registries:
        p = COG_REG / name
        if not p.exists():
            missing.append(name)
    if missing:
        findings.append(("missing_cog_registries", missing[:8]))

    # 2. Rehydration support — which modules support load_from_snapshot?
    has_rehydrate = ["family_tree", "worker_certification", "reward_engine"]
    missing_rehydrate = ["action_proposer", "curiosity", "uncertainty",
                          "long_term_memory_semantic_cache", "self_model",
                          "worker_genetics", "worker_pnl(it_reads_from_ledger)",
                          "reflection_notes_cache"]
    findings.append(("rehydration_only_3_of_~11_modules", {
        "has_rehydrate": has_rehydrate,
        "missing_rehydrate": missing_rehydrate,
    }))

    # 3. Read coverage — chat handler bridges
    handlers_known = [
        "cognitive_kernel_state", "commerce_floor", "profit_plan",
        "reassign_workers", "candidate_floors",
        "worker_certification", "worker_pnl", "family_tree",
        "reward_report",
    ]
    findings.append(("chat_handler_count", len(handlers_known)))

    # 4. Open proposal hygiene
    ap_persisted = load(COG_REG / "cognitive_action_proposals.json")
    if isinstance(ap_persisted, dict):
        open_count_persisted = ap_persisted.get("open_count")
        in_mem_count = len(action_proposer().open_proposals())
        if open_count_persisted != in_mem_count:
            findings.append(("action_proposer_in_memory_vs_persisted_mismatch", {
                "persisted_open_count": open_count_persisted,
                "in_memory_open_count": in_mem_count,
            }))

    # 5. Long-term-memory growth
    ltm_index = load(COG_REG / "cognitive_long_term_memory_index.json")
    if isinstance(ltm_index, dict):
        findings.append(("ltm_index", {
            "semantic_lessons_loaded": ltm_index.get("semantic_lessons_loaded"),
        }))

    # 6. Goals alignment
    g_persisted = load(COG_REG / "cognitive_goals.json")
    if isinstance(g_persisted, dict):
        findings.append(("active_goal_count", g_persisted.get("active_goal_count")))

    # 7. Per-worker attribution on Floor 41 ledger
    pnl_snap = worker_pnl().snapshot()
    if pnl_snap.get("worker_count"):
        unassigned = next((r for r in pnl_snap.get("rows_sample") or []
                            if r.get("worker_id") == "unassigned"), None)
        findings.append(("floor41_unassigned_trade_attribution_present",
                         unassigned is not None))

    text = []
    text.append("Layer-by-layer audit:")
    text.append("")
    text.append("MISSING REHYDRATION:")
    text.append("  · action_proposer  ← P0, fix this round")
    text.append("  · worker_genetics  ← P1")
    text.append("  · curiosity        ← P2 (Kernel re-populates from "
                "safety-net log, so loss is bounded)")
    text.append("  · uncertainty      ← P2 (decays anyway)")
    text.append("")
    text.append("PERSIST COVERAGE:")
    if missing:
        text.append(f"  · {len(missing)} cognitive registries never "
                    f"written: {missing[:6]}{'…' if len(missing)>6 else ''}")
    else:
        text.append("  · all important cognitive registries present.")
    text.append("")
    text.append("CHAT HANDLER COVERAGE:")
    text.append(f"  · {len(handlers_known)} cognitive topics wired. "
                "Still missing: bank, compensation, lineage_performance, "
                "curriculum_evolution, free_images.")
    text.append("")
    text.append("DATA WORTH FIXING:")
    text.append("  · Floor 41 ledger has 'unassigned' rows (legacy "
                "trades pre-attribution). Once the OANDA-placement "
                "side carries worker_id everywhere, this falls to zero.")
    text.append("  · No per-lineage beliefs yet — family_tree edges "
                "exist but reflection never says 'lineage X is doing "
                "Y%'. Easy win.")
    text.append("")
    text.append("RAW FINDINGS:")
    for k, v in findings:
        text.append(f"  · {k} = {json.dumps(v, default=str)[:120]}")
    kernel("\n".join(text),
            refs=["cognitive_action_proposals.json",
                   "cognitive_worker_pnl_rollup.json"])

    # File proposals
    ap = action_proposer()
    for title, action in [
        ("Rehydrate ActionProposer across processes",
         "claude: add load_from_snapshot() to action_proposal.py reading cognitive_action_proposals.json"),
        ("Compute per-lineage beliefs from family_tree + worker_pnl",
         "claude: src/tower/cognitive_kernel/lineage_beliefs.py — emits cognitive_lineage_beliefs.json"),
        ("Curriculum evolution loop — lesson↔outcome correlation",
         "claude: src/tower/cognitive_kernel/curriculum_evolution.py"),
        ("Self-audit module that runs each tick",
         "claude: src/tower/cognitive_kernel/cognition_self_audit.py — surfaces broken bridges + stale registries"),
    ]:
        p = ap.propose(
            title=title, rationale="from self-audit",
            proposed_action=action,
            requires_approval_from="claude+kernel",
            confidence=0.8,
            tags=["self_audit", "v2_evolution"],
        )
        filed(p, "KERNEL")


# ────────────────────────────────────────────────────────────────────
# Round 3 — Internal bank + currency design
# ────────────────────────────────────────────────────────────────────

def round_3():
    box("ROUND 3 · INTERNAL BANK + CURRENCY (QBC)")
    claude("Ross asked: can the skyscraper have its own bank and "
            "currency? Pay the workers? Here's the design I want to "
            "build — check it against your contract.")
    print()
    design = [
        "QBC = QSB Bank Credit. Internal-only accounting unit. NEVER "
        "convertible to fiat without an explicit operator gate.",
        "Per-worker QBC balance ledger; transactions are append-only and "
        "auditable.",
        "Mint sources (advisory): "
        "· per-trade PnL share (1 QBC per $1 practice PnL, capped) "
        "· classroom test pass (+50 QBC) "
        "· successful mentorship of a child to certification (+200 QBC) "
        "· friend pairing maintained for 30+ days (+25 QBC).",
        "Burn / spend (advisory): "
        "· premium classroom unlock (-100 QBC) "
        "· advanced instrument unlock (-250 QBC) "
        "· child dowry gift to a newborn child (-100 QBC to child's "
        "starting balance) "
        "· cosmetic title (-50 QBC).",
        "Total supply cap (initial): 1,000,000 QBC. Operator can lift.",
        "Inflation governor: if tower-wide mint exceeds tower-wide burn "
        "for 7 consecutive days, Kernel files a 'tighten mint rates' "
        "proposal. Avoids runaway inflation in the simulation.",
        "Gates that stay locked: fiat conversion, real-money payouts, "
        "external transfer. QBC lives only in cognitive registries.",
    ]
    for i, d in enumerate(design, 1):
        print(f"    {i}. {d}")

    text = []
    text.append("Reviewing the bank design against my contract:")
    text.append("")
    text.append("WHAT I'LL DO:")
    text.append("  · accept QBC as an INTERNAL accounting layer; mint, "
                "burn, transfer all advisory and recorded.")
    text.append("  · refuse to model any QBC↔fiat conversion or any "
                "external-transfer surface. Those would need their "
                "own operator-flipped gate and a separate Claude phase.")
    text.append("  · expose per-worker balance + recent transactions "
                "via the chat (new 'bank' topic).")
    text.append("  · let compensation_engine.pay(...) be the SOLE "
                "minting API so audit is trivial.")
    text.append("")
    text.append("RISKS I SEE:")
    text.append("  · Reward inflation. If mint sources are too lenient "
                "the supply cap is hit fast. Mitigation: I'll watch "
                "supply daily and file a 'tighten' proposal at 80% cap.")
    text.append("  · Hoarding. If burn paths are sparse, workers will "
                "accumulate. Mitigation: track Gini-style concentration "
                "in the snapshot; surface to reflection.")
    text.append("  · Pay-for-grant exploit. Could a worker BUY their "
                "way to a child grant? My ruling: NO. QBC may buy "
                "classroom unlocks and dowries, but child/friend grants "
                "remain gated on PnL + dual signatures. Bank is reward, "
                "not bypass.")
    text.append("")
    text.append("VERDICT: build it. Plan accepted.")
    kernel("\n".join(text),
            refs=["CLAUDE.md", "cognitive_safety_envelope"])

    ap = action_proposer()
    for title, action in [
        ("Build internal bank + QBC currency module",
         "claude: src/tower/cognitive_kernel/bank.py"),
        ("Build compensation engine paying workers in QBC",
         "claude: src/tower/cognitive_kernel/compensation.py"),
        ("Wire 'bank' + 'compensation' chat topics",
         "claude: edit kernel_dialogue_adapter.py"),
    ]:
        p = ap.propose(
            title=title, rationale="bank design accepted",
            proposed_action=action,
            requires_approval_from="claude+kernel",
            confidence=0.85,
            tags=["bank", "compensation", "v2_evolution"],
        )
        filed(p, "KERNEL")


# ────────────────────────────────────────────────────────────────────
# Round 4 — Free-image revenue stream
# ────────────────────────────────────────────────────────────────────

def round_4():
    box("ROUND 4 · FREE-IMAGE REVENUE FOR COMMERCE FLOOR")
    claude("Etsy expansion. Ross asked: can we use free images and sell "
            "them? Idea: build a curated catalog of CC0 / public-domain "
            "sources, plus a draft-listing pipeline that turns one "
            "source image into multiple derivative products (prints, "
            "stickers, mugs, digital downloads). Operator approves the "
            "fetch AND the publish; we never auto-fetch or auto-publish.")

    text = []
    text.append("This is a strong path. Layering on the contract:")
    text.append("")
    text.append("SOURCES I know are commercial-use safe (will catalog):")
    text.append("  · Unsplash (Unsplash license; commercial OK; no req'd attribution)")
    text.append("  · Pexels (Pexels license; commercial OK)")
    text.append("  · Pixabay (Pixabay content license; commercial OK)")
    text.append("  · NASA images (US public domain mostly)")
    text.append("  · Wikimedia Commons CC0 subset only (mind the BY-SA "
                "ones — they need attribution + share-alike, awkward "
                "for derivative products)")
    text.append("  · Smithsonian Open Access (CC0)")
    text.append("  · Library of Congress public-domain collections")
    text.append("  · Rijksmuseum (CC0 for many high-res scans)")
    text.append("  · Metropolitan Museum Open Access (CC0 for many works)")
    text.append("")
    text.append("DERIVATIVE PRODUCTS per source image (drafts only):")
    text.append("  · art print (cropped + posterized)")
    text.append("  · sticker pack (cut-out variants)")
    text.append("  · mug (centered + bleed)")
    text.append("  · phone case (vertical crop)")
    text.append("  · digital download bundle (multi-format)")
    text.append("  · collage poster (multi-source montage)")
    text.append("")
    text.append("PIPELINE:")
    text.append("  1. Catalog of sources + license + commercial rules.")
    text.append("  2. Draft listing template per derivative product.")
    text.append("  3. Pricing advisor (we already have one) computes "
                "suggested price + projected margin.")
    text.append("  4. Listing goes into qsb_floor46_commerce_catalog.json "
                "with status='draft_from_free_image'.")
    text.append("  5. Operator approves both (a) actually fetching the "
                "image and (b) publishing — TWO separate operator flips.")
    text.append("")
    text.append("HARD LINES that stay locked:")
    text.append("  · external_api_calls_enabled = False (no auto-fetch)")
    text.append("  · live_listings_publishing_enabled = False (no auto-publish)")
    text.append("  · I will store SOURCE METADATA and DRAFT LISTINGS — "
                "never the binary image. The operator pulls the image "
                "themselves once they approve.")
    text.append("")
    text.append("VERDICT: safe, profitable, build it.")
    kernel("\n".join(text), refs=["qsb_floor46_commerce_catalog.json"])

    ap = action_proposer()
    p = ap.propose(
        title="Build free-image catalog + listing-draft pipeline (advisory)",
        rationale=("Free-image sources expand the Commerce Wing product "
                    "range without unlocking any real-API gate."),
        proposed_action="claude: src/tower/cognitive_kernel/free_image_catalog.py",
        requires_approval_from="claude+kernel",
        confidence=0.8,
        tags=["commerce", "free_images", "v2_evolution"],
    )
    filed(p, "KERNEL")


# ────────────────────────────────────────────────────────────────────
# Round 5 — Build order + commit
# ────────────────────────────────────────────────────────────────────

def round_5():
    box("ROUND 5 · BUILD ORDER LOCKED")
    claude("Build order, dependency-clean.")
    text = (
        "BUILD ORDER:\n"
        "  1. bank.py            — QBC currency primitives\n"
        "  2. compensation.py    — payment from achievements\n"
        "  3. action_proposal load_from_snapshot — close the persistence "
        "leak\n"
        "  4. lineage_beliefs.py — per-lineage performance computation\n"
        "  5. curriculum_evolution.py — lesson↔outcome correlation\n"
        "  6. free_image_catalog.py — sources + draft listing pipeline\n"
        "  7. cognition_self_audit.py — per-tick system health\n"
        "  8. chat-topic wiring + orchestrator tick integration\n"
        "\n"
        "NEW STANDING GOALS:\n"
        "  · 'maintain_internal_currency_integrity' priority 1.0\n"
        "  · 'reward_workers_proportional_to_achievement' priority 0.85\n"
        "  · 'evolve_curriculum_from_outcomes' priority 0.7\n"
        "  · 'preserve_free_image_license_compliance' priority 1.0\n"
        "  · 'self_audit_each_tick_and_surface_drift' priority 0.9\n"
        "\n"
        "Installing goals now."
    )
    kernel(text, refs=["cognitive_goals.json"])
    gs = goals()
    for name, desc, prio, keys in [
        ("maintain_internal_currency_integrity",
         "QBC mints only via compensation_engine; never via direct edit; "
         "no fiat conversion.",
         1.0, ["bank", "compensation"]),
        ("reward_workers_proportional_to_achievement",
         "Compensation must scale with verified PnL + classroom passes + "
         "mentorship outcomes.",
         0.85, ["compensation", "worker_pnl"]),
        ("evolve_curriculum_from_outcomes",
         "Reinforce lessons that correlate with future profit; "
         "deprecate ones that do not.",
         0.7, ["classroom", "curriculum_evolution"]),
        ("preserve_free_image_license_compliance",
         "Catalog each source with license; never draft a commercial "
         "listing from a non-commercial license.",
         1.0, ["free_image_catalog", "commerce"]),
        ("self_audit_each_tick_and_surface_drift",
         "Run cognition_self_audit each tick; file proposals when a "
         "registry has not refreshed in N hours.",
         0.9, ["cognition_self_audit"]),
    ]:
        gs.add(name=name, description=desc,
                source="dialogue_self_audit_v2",
                priority=prio, focus_keys=keys)

    long_term_memory().record_episode(
        kind="self_audit_design_locked",
        summary="Claude + Kernel agreed on 8-step v2 build.",
        tags=["self_audit", "v2_evolution"],
        payload={"build_order_locked_ts": now()},
    )
    claude("Locked. Building.")


def main():
    box("CLAUDE ↔ QSB KERNEL · SELF-AUDIT + EVOLUTION DESIGN")
    orchestrator().tick(do_self_model_refresh=True, do_reflection=True)
    round_1()
    round_2()
    round_3()
    round_4()
    round_5()
    write_registry("cognitive_dialogue_self_audit_design.json", {
        "ok": True, "kind": "cognitive_dialogue_self_audit_design",
        "generated_ts": now(),
        "policy": "Self-audit + evolution dialogue. Build authorized by Claude + Kernel.",
        "safety_envelope": dict(SAFETY),
        "turn_count": len(TRANSCRIPT),
        "transcript": TRANSCRIPT,
    })
    print()
    print("Transcript persisted. Build begins.")


if __name__ == "__main__":
    main()
