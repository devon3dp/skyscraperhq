"""Orchestrator — Layer 7 · The cognition cycle.

Runs the layers in order, once per tick:

  1. Perception           → events
  2. Working Memory ingest event payloads (with novelty/urgency-derived priority)
  3. UpgradeAssimilation  → notice any new Claude phase
  4. SelfModel refresh    (occasional, not every tick)
  5. OpenClawSupervisor   → observe routing
  6. WorkerExchange       → digest worker scene
  7. MLRLAdvisory         → observe lab state
  8. Reasoning            → fire rules
  9. Contradiction        → cross-belief check
 10. LessonToBelief       → promote stable lessons
 11. Curiosity absorb_safety_net
 12. Reflection           → introspect (occasional)
 13. CausalPhaseModel.predict_for_latest_phase  (occasional)
 14. Counterfactual       → on-demand only, not every tick
 15. Persist all          → cognitive_*.json registries

ThoughtTrace records a line from each layer with the current tick_id.

The orchestrator does NOT execute actions. It only THINKS, SPEAKS,
PROPOSES.
"""

from __future__ import annotations
from dataclasses import dataclass, field
from typing import Dict, List, Optional
import time
import uuid

from . import append_log, write_registry, now, SAFETY
from .working_memory import blackboard
from .self_model import self_model
from .identity_gate import gate_state, persist as persist_identity_gate
from .perception import perception, persist_state as persist_perception
from .attention import attention, AttentionScore
from .curiosity import curiosity
from .uncertainty import uncertainty
from .long_term_memory import long_term_memory
from .reasoning import reasoning
from .contradiction import contradiction_detector
from .goals import goals
from .reflection import reflection
from .thought_trace import thought_trace
from .action_proposal import action_proposer
from .learning import learning
from .upgrade_assimilation import upgrade_assimilator
from .lesson_to_belief import lesson_to_belief
from .openclaw_supervisor import openclaw_supervisor
from .worker_exchange import worker_exchange
from .ml_rl_advisory import ml_rl_advisory
from .floor_mind_map import floor_mind_map
from .counterfactual import counterfactual
from .causal_phase_model import causal_phase_model
# Finance lineage v1 modules
from .worker_certification import worker_certification
from .worker_pnl import worker_pnl
from .worker_genetics import worker_genetics
from .family_tree import family_tree
from .population import persist as persist_population_status
from .trading_authority import persist_gate as persist_authority_gate
from .reward_engine import reward_engine
from .classroom import classroom as classroom_layer
# V2 evolution modules
from .bank import bank
from .compensation import compensation_engine
from .lineage_beliefs import lineage_beliefs
from .curriculum_evolution import curriculum_evolution
from .free_image_catalog import persist as persist_free_image_catalog
from .cognition_self_audit import cognition_self_audit
# V3 evolution modules
from .banking_gateway import persist as persist_banking_gateway
from .worker_spawn import worker_spawn
from .oanda_attribution import persist as persist_oanda_attribution
from .free_image_promotion import free_image_promotion
from .bank_spend import bank_spend
from .morning_briefing import morning_briefing
# V4 — Tower Studio + Lumen AI floors
from tower.floors.floor_49_tower_studio.state import persist_floor_state as persist_studio_state
from tower.floors.floor_49_tower_studio.services import persist_services as persist_studio_services
from tower.floors.floor_49_tower_studio.customers import customers_db as studio_customers
from tower.floors.floor_49_tower_studio.projects import projects_db as studio_projects
from tower.floors.floor_49_tower_studio.workers import persist_workers as persist_studio_workers
from tower.floors.floor_48_lumen_ai.state import persist_lumen_state
from tower.floors.floor_48_lumen_ai.tiers import persist_tiers as persist_lumen_tiers
from tower.floors.floor_48_lumen_ai.chat import persist_conversations as persist_lumen_conversations


@dataclass
class TickResult:
    tick_id: str
    started_ts: float
    finished_ts: float
    perception_event_count: int
    reasoning_conclusion_count: int
    contradiction_count: int
    reflection_note_count: int
    proposal_count_open: int
    curiosity_open_count: int
    notes: List[str] = field(default_factory=list)


class Orchestrator:
    def __init__(self):
        self._tick_count = 0
        self._last_self_model_refresh = 0.0
        self._last_reflection = 0.0
        self._last_causal_predict = 0.0

    def tick(self, user_focus_keys: Optional[List[str]] = None,
             do_self_model_refresh: bool = False,
             do_reflection: bool = False,
             do_causal_predict: bool = False) -> TickResult:
        self._tick_count += 1
        tick_id = f"tick_{int(time.time())}_{self._tick_count}"
        started = time.time()
        tt = thought_trace()
        notes: List[str] = []

        # 1. Perception
        events = perception().tick()
        persist_perception(events)
        tt.think(tick_id, "perception",
                 f"Saw {len(events)} new events.",
                 refs=[e.source for e in events[:5]])

        # 2. Working Memory ingest
        bb = blackboard()
        for e in events:
            bb.write(
                key=self._wm_key_for(e.source),
                value=e.payload, source=e.source,
                priority=max(0.4, 0.3 * e.urgency + 0.5 * e.novelty),
                ttl_seconds=900,
                tags=[e.kind, "perception"],
            )
        bb.age_out()

        # 3. UpgradeAssimilation
        upgrade_assimilator().assimilate_once()

        # 4. SelfModel refresh (every ~10 ticks or on demand)
        if do_self_model_refresh or (self._tick_count % 10 == 1):
            self_model().refresh_all()
            self._last_self_model_refresh = time.time()
            tt.think(tick_id, "self_model", "Refreshed topics + registries.")

        # 5-7. Supervisory observations
        openclaw_supervisor().observe()
        worker_exchange().digest()
        ml_rl_advisory().observe()
        tt.think(tick_id, "supervisors",
                 "OpenClaw observed; worker scene digested; ML/RL advisory updated.")

        # 8. Attention — score working memory slots
        gs = goals()
        att = attention()
        att.mark_user_focus(user_focus_keys or [])
        att.mark_goal_focus(gs.active_focus_keys())
        scores: List[AttentionScore] = []
        now_ts = time.time()
        for slot in bb.all_slots():
            age = max(0.0, now_ts - slot.last_touched_ts)
            novelty = 0.5 if (now_ts - slot.inserted_ts) < 60 else 0.2
            urgency = max(0.3, slot.priority)
            scores.append(att.score(slot.key, urgency=urgency,
                                     novelty=novelty, age_seconds=age))
        ranked = att.rank(scores)
        att.persist(ranked)
        tt.think(tick_id, "attention",
                 f"Scored {len(scores)} slots; top: {ranked[0].target_key if ranked else 'none'}",
                 refs=[r.target_key for r in ranked[:5]])

        # 9. Reasoning
        conclusions = reasoning().run_once()
        tt.think(tick_id, "reasoning",
                 f"Derived {len(conclusions)} conclusions.",
                 refs=[c.key for c in conclusions])

        # 10. Contradiction
        contras = contradiction_detector().scan()
        if contras:
            tt.think(tick_id, "contradiction",
                     f"Found {len(contras)} contradiction pair(s).",
                     refs=[c.a_key for c in contras])

        # 11. Lesson → belief promotion
        promoted = lesson_to_belief().promote_once()
        if promoted:
            tt.think(tick_id, "lesson_to_belief",
                     f"Promoted {len(promoted)} lesson(s) to active beliefs.")

        # 12. Curiosity absorb safety-net
        curiosity().absorb_safety_net()

        # 13. Reflection (every ~5 ticks or on demand)
        ref_count = 0
        if do_reflection or (self._tick_count % 5 == 1):
            notes_ref = reflection().reflect_once()
            ref_count = len(notes_ref)
            self._last_reflection = time.time()
            tt.think(tick_id, "reflection",
                     f"Wrote {ref_count} reflection note(s).")

        # 14. Causal phase prediction (every ~20 ticks)
        if do_causal_predict or (self._tick_count % 20 == 1):
            cpm = causal_phase_model()
            cpm.ingest_phase_history()
            cpm.predict_for_latest_phase()
            self._last_causal_predict = time.time()
            tt.think(tick_id, "causal_phase_model",
                     "Updated phase causal graph; filed predictions.")

        # 15. Persist everything
        bb.persist()
        self_model().refresh_all() if (self._tick_count % 10 == 1) else None
        persist_identity_gate()
        att.persist(ranked)
        curiosity().persist()
        uncertainty().persist()
        long_term_memory().persist()
        reasoning().persist()
        contradiction_detector().persist()
        goals().persist()
        reflection().persist()
        thought_trace().persist()
        action_proposer().persist()
        learning().persist()
        upgrade_assimilator().persist()
        lesson_to_belief().persist()
        openclaw_supervisor().persist()
        worker_exchange().persist()
        ml_rl_advisory().persist()
        floor_mind_map().persist()
        counterfactual().persist()
        causal_phase_model().persist()
        # Finance lineage v1 — keep registries fresh between ticks
        try:
            worker_pnl().refresh()
            worker_pnl().persist()
            worker_certification().load_from_snapshot()
            worker_certification().persist()
            worker_genetics().persist()
            family_tree().load_from_snapshot()
            family_tree().persist()
            persist_authority_gate()
            persist_population_status()
            reward_engine().load_from_snapshot()
            reward_engine().persist()
            classroom_layer().persist()
        except Exception as _e:
            append_log("orchestrator.jsonl",
                       {"event": "finance_lineage_persist_error",
                        "error": str(_e)})
        # V2 evolution — bank, compensation, lineage beliefs, curriculum, audit
        try:
            bank().load_from_snapshot()
            compensation_engine().load_from_snapshot()
            compensation_engine().settle_round()
            bank().persist()
            compensation_engine().persist()
            lineage_beliefs().persist()
            curriculum_evolution().persist()
            persist_free_image_catalog()
            cognition_self_audit().persist()
            # Now that ActionProposer rehydrates, do that too
            action_proposer().load_from_snapshot()
            action_proposer().persist()
        except Exception as _e:
            append_log("orchestrator.jsonl",
                       {"event": "v2_evolution_persist_error",
                        "error": str(_e)})
        # V3 evolution — banking gateway, spawn, attribution, promote, spend, briefing
        try:
            persist_banking_gateway()
            ws = worker_spawn()
            ws.collect_pending()
            ws.write_roster()
            ws.persist()
            persist_oanda_attribution()
            fip = free_image_promotion()
            fip.load_approvals()
            fip.promote_approved()
            fip.persist()
            bs = bank_spend()
            bs.load_from_snapshot()
            bs.persist()
            morning_briefing().persist()
        except Exception as _e:
            append_log("orchestrator.jsonl",
                       {"event": "v3_evolution_persist_error",
                        "error": str(_e)})
        # V4 — Floors 48 + 49
        try:
            persist_studio_state()
            persist_studio_services()
            studio_customers().persist()
            studio_projects().persist()
            persist_studio_workers()
            persist_lumen_state()
            persist_lumen_tiers()
            persist_lumen_conversations()
        except Exception as _e:
            append_log("orchestrator.jsonl",
                       {"event": "v4_evolution_persist_error",
                        "error": str(_e)})
        # V5 — research queue + finance live status
        try:
            rq = research_queue()
            rq.load_from_snapshot()
            rq.persist()
            persist_finance_live_status()
            # V6 — OANDA certified-worker trades (real practice account)
            from .oanda_worker_trades import persist as persist_oanda_worker_trades
            persist_oanda_worker_trades()
            # V7 — sessions, comms scaffold, Floor 42 state
            from .trading_sessions import persist as persist_sessions
            from .comms import persist as persist_comms
            from tower.floors.floor_42_binance_testnet.state import persist_floor_state as persist_f42
            persist_sessions()
            persist_comms()
            persist_f42()
        except Exception as _e:
            append_log("orchestrator.jsonl",
                       {"event": "v5_evolution_persist_error",
                        "error": str(_e)})

        finished = time.time()
        result = TickResult(
            tick_id=tick_id, started_ts=started, finished_ts=finished,
            perception_event_count=len(events),
            reasoning_conclusion_count=len(conclusions),
            contradiction_count=len(contras),
            reflection_note_count=ref_count,
            proposal_count_open=len(action_proposer().open_proposals()),
            curiosity_open_count=len(curiosity().open_items()),
            notes=notes,
        )
        append_log("orchestrator.jsonl", {
            "event": "tick",
            "tick_id": tick_id,
            "duration_s": round(finished - started, 4),
            "events": len(events),
            "conclusions": len(conclusions),
            "contradictions": len(contras),
            "reflections": ref_count,
            "proposals_open": result.proposal_count_open,
            "curiosity_open": result.curiosity_open_count,
        })
        # Persist a per-tick summary registry the dashboard can show
        write_registry("cognitive_orchestrator_last_tick.json", {
            "ok": True, "kind": "cognitive_orchestrator_last_tick",
            "generated_ts": now(),
            "tick_id": tick_id,
            "duration_seconds": round(finished - started, 4),
            "events": len(events),
            "conclusions": len(conclusions),
            "contradictions": len(contras),
            "reflections": ref_count,
            "proposals_open": result.proposal_count_open,
            "curiosity_open": result.curiosity_open_count,
            "policy": "Kernel THINKS, SPEAKS, PROPOSES. Kernel does NOT execute.",
            "safety_envelope": dict(SAFETY),
        })
        return result

    @staticmethod
    def _wm_key_for(source: str) -> str:
        # source is a registry path like "data/registries/eqsb_guardian_state.json"
        name = source.split("/")[-1].replace(".json", "").replace(".jsonl", "")
        # Translate familiar names into canonical keys
        m = {
            "eqsb_guardian_state": "guardian_state",
            "qsb_floor41_oanda_pnl": "oanda_pnl_state",
            "qsb_openclaw_route": "openclaw_route",
            "qsb_openclaw_tickets": "openclaw_tickets",
            "qsb_lift_scene_state": "lift_scene",
            "qsb_worker_scene_state": "worker_scene",
            "qsb_3d_skyscraper_state": "skyscraper_3d",
            "eqsb_last_claude_change_summary": "last_claude_change",
            "qsb_ml_rl_lab_status": "ml_rl_lab_status",
            "eqsb_cadence_state": "cadence_state",
        }
        return m.get(name, name)


_ORCH: Optional[Orchestrator] = None


def orchestrator() -> Orchestrator:
    global _ORCH
    if _ORCH is None:
        _ORCH = Orchestrator()
    return _ORCH
