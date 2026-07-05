"""CandidateFloors — Layer · A standing registry of which floors to open next.

The skyscraper has expansion-ready floors (44, 45, 46, 47, 48, 49, 50,
51, 52). The Penthouse (53) is sealed for QSB Kernel 4.5. Each candidate
carries:
  · floor number
  · proposed role / purpose
  · revenue or value path
  · safety class (LOW / AMBER / RED)
  · which gates must stay locked for it to be safe
  · current status (planned / scaffolded / opened / sealed)

This module never opens a floor. It only proposes which to open next
and exposes a registry the dashboard + chat can read.
"""

from __future__ import annotations
from dataclasses import dataclass, field, asdict
from typing import Dict, List, Optional, Any

from . import write_registry, now


@dataclass
class CandidateFloor:
    floor: str                       # canonical floor name
    floor_number: int
    purpose: str
    value_path: str
    safety_class: str                # LOW | AMBER | RED
    gates_must_stay_locked: List[str] = field(default_factory=list)
    desired_worker_roles: List[str] = field(default_factory=list)
    estimated_setup_effort_phases: int = 1
    status: str = "planned"          # planned | scaffolded | opened | sealed
    notes: str = ""


CANDIDATES: List[CandidateFloor] = [
    CandidateFloor(
        floor="floor_44_expansion_a",
        floor_number=44,
        purpose="Reserved expansion floor — uncommitted.",
        value_path="(none yet)",
        safety_class="LOW",
        gates_must_stay_locked=["autonomous_dispatch_enabled"],
        desired_worker_roles=[],
        status="sealed",
        notes="Expansion-ready per CLAUDE.md; do not auto-fill.",
    ),
    CandidateFloor(
        floor="floor_45_expansion_b",
        floor_number=45,
        purpose="Reserved expansion floor — uncommitted.",
        value_path="(none yet)",
        safety_class="LOW",
        gates_must_stay_locked=["autonomous_dispatch_enabled"],
        desired_worker_roles=[],
        status="sealed",
        notes="Expansion-ready per CLAUDE.md; do not auto-fill.",
    ),
    CandidateFloor(
        floor="floor_46_commerce",
        floor_number=46,
        purpose="Commerce Wing — Etsy preview-only digital storefront.",
        value_path=("digital + physical product catalog → pricing analytics "
                     "→ listing drafts → (operator-approved) publishing"),
        safety_class="LOW",
        gates_must_stay_locked=[
            "live_listings_publishing_enabled",
            "payments_enabled",
            "external_api_calls_enabled",
        ],
        desired_worker_roles=["catalog_curator", "product_photographer",
                               "copywriter", "pricing_analyst",
                               "listing_draft_reviewer"],
        estimated_setup_effort_phases=2,
        status="scaffolded",
        notes="Floor 46 scaffolded in 2026-06-09 V1.5 phase.",
    ),
    CandidateFloor(
        floor="floor_47_profit_analytics",
        floor_number=47,
        purpose="Cross-floor profit summary + advisory proposer.",
        value_path=("OANDA practice PnL + commerce projections + workforce "
                     "ROI → profit_snapshot → advisory action proposals"),
        safety_class="LOW",
        gates_must_stay_locked=[],
        desired_worker_roles=["analyst", "report_writer"],
        estimated_setup_effort_phases=1,
        status="scaffolded",
        notes="Floor 47 scaffolded in 2026-06-09 V1.5 phase.",
    ),
    CandidateFloor(
        floor="floor_48_backtest",
        floor_number=48,
        purpose="Trading-strategy backtest harness — pure simulation.",
        value_path=("historical OANDA practice + Binance testnet data → "
                     "strategy outcomes → Learning layer beliefs"),
        safety_class="LOW",
        gates_must_stay_locked=[
            "live_trading_enabled",
            "binance_order_execution_enabled",
            "stock_order_execution_enabled",
        ],
        desired_worker_roles=["strategy_evaluator", "backtester"],
        estimated_setup_effort_phases=2,
        status="planned",
        notes="Open after 46 + 47 prove themselves.",
    ),
    CandidateFloor(
        floor="floor_49_customer_voice",
        floor_number=49,
        purpose="Sandbox customer-support workflow tied to commerce drafts.",
        value_path=("scaffold support tickets for hypothetical buyers of "
                     "the sandbox catalog — operator learns the workflow "
                     "before any real customer exists"),
        safety_class="AMBER",
        gates_must_stay_locked=[
            "external_api_calls_enabled",
            "payments_enabled",
        ],
        desired_worker_roles=["support_rep", "qa_reviewer"],
        estimated_setup_effort_phases=2,
        status="planned",
        notes="AMBER because customer-voice flows tempt premature live wiring.",
    ),
    CandidateFloor(
        floor="floor_50_ml_rl_lab",
        floor_number=50,
        purpose="ML/RL Lab interaction layer (advisory only).",
        value_path=("read /vaults/ai/qsb_ml_rl_lab status; advise on "
                     "retraining cadence and checkpoint freshness"),
        safety_class="LOW",
        gates_must_stay_locked=[],
        desired_worker_roles=["ml_advisor"],
        estimated_setup_effort_phases=1,
        status="opened",
        notes="Already represented in cognitive_floor_to_mind_map.",
    ),
    CandidateFloor(
        floor="floor_51_research",
        floor_number=51,
        purpose="Curiosity & long-term-memory research bench.",
        value_path=("operator's open questions + Kernel curiosity items → "
                     "long-term-memory semantic entries"),
        safety_class="LOW",
        gates_must_stay_locked=[],
        desired_worker_roles=["researcher"],
        estimated_setup_effort_phases=1,
        status="opened",
        notes="Already represented in cognitive_floor_to_mind_map.",
    ),
    CandidateFloor(
        floor="floor_52_reflection",
        floor_number=52,
        purpose="Reflection + contradiction + lesson-to-belief surface.",
        value_path=("introspective surface for operator review of "
                     "cognition health"),
        safety_class="LOW",
        gates_must_stay_locked=[],
        desired_worker_roles=["meta_reviewer"],
        estimated_setup_effort_phases=1,
        status="opened",
        notes="Already represented in cognitive_floor_to_mind_map.",
    ),
    CandidateFloor(
        floor="floor_53_penthouse",
        floor_number=53,
        purpose="RESERVED for QSB Kernel 4.5 installation.",
        value_path="(sealed)",
        safety_class="RED",
        gates_must_stay_locked=[
            "self_rewrite_of_code_enabled",
            "self_rewrite_of_registries_enabled",
        ],
        desired_worker_roles=[],
        estimated_setup_effort_phases=0,
        status="sealed",
        notes=("Penthouse is sealed per CLAUDE.md. Inherited symbolic "
                "kernel artifact lives here but must not execute logic."),
    ),
]


def snapshot() -> Dict[str, Any]:
    rows = [asdict(c) for c in CANDIDATES]
    by_status: Dict[str, int] = {}
    by_class: Dict[str, int] = {}
    for r in rows:
        by_status[r["status"]] = by_status.get(r["status"], 0) + 1
        by_class[r["safety_class"]] = by_class.get(r["safety_class"], 0) + 1
    return {
        "ok": True,
        "kind": "cognitive_candidate_floors",
        "generated_ts": now(),
        "policy": ("Advisory registry. Opening a floor still requires a "
                    "Claude phase. Sealed floors stay sealed."),
        "total_candidates": len(rows),
        "by_status": by_status,
        "by_safety_class": by_class,
        "candidates": rows,
    }


def persist() -> Dict[str, Any]:
    snap = snapshot()
    write_registry("cognitive_candidate_floors.json", snap)
    return snap
