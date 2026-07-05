"""Specialist Classroom — tiered + strategy-specific certification.

Ross 2026-06-12: make traders specialists, not generalists.

Extends the basic Classroom (scalping-only, single-pass cert) with:
  · 5 tiers — Rookie → Bronze → Silver → Gold → Master
  · 6 strategies — scalp · swing · breakout · mean_revert · news_event · arb
  · Per-strategy curriculum with strategy-specific written + sim exams
  · Tier-gated privileges (max units, max open trades, suspension cap)

Certification key:  (worker_id, instrument, strategy, tier)
Stamped to cognitive_specialist_certification.json.

Idempotent: deterministic by hash(worker:strategy:tier:instrument), so a
worker who passed Silver yesterday still passes Silver today.
"""
from __future__ import annotations
from dataclasses import dataclass, field
from typing import Dict, List, Optional, Any
import hashlib
import time

from . import write_registry, append_log, now


# ── Tier ladder ─────────────────────────────────────────────────────
TIER_ORDER = ["Rookie", "Bronze", "Silver", "Gold", "Master"]

TIER_REQUIREMENTS = {
    # tier -> {written_min, sim_win_rate, max_loss_pct, avg_hold_max, sim_count}
    "Rookie":  {"written_min": 7,  "win_rate": 0.50, "max_loss": 0.0070, "avg_hold": 720,  "trades": 15},
    "Bronze":  {"written_min": 9,  "win_rate": 0.55, "max_loss": 0.0050, "avg_hold": 600,  "trades": 20},
    "Silver":  {"written_min": 10, "win_rate": 0.60, "max_loss": 0.0040, "avg_hold": 540,  "trades": 25},
    "Gold":    {"written_min": 11, "win_rate": 0.65, "max_loss": 0.0030, "avg_hold": 480,  "trades": 30},
    "Master":  {"written_min": 12, "win_rate": 0.70, "max_loss": 0.0025, "avg_hold": 420,  "trades": 40},
}

# Tier-gated trading privileges
TIER_PRIVILEGES = {
    "Rookie":  {"max_units": 200,   "max_open": 1, "suspend_after_losses": 3, "spread_warn_pips": 1.0},
    "Bronze":  {"max_units": 500,   "max_open": 2, "suspend_after_losses": 4, "spread_warn_pips": 1.5},
    "Silver":  {"max_units": 1000,  "max_open": 3, "suspend_after_losses": 5, "spread_warn_pips": 2.0},
    "Gold":    {"max_units": 2000,  "max_open": 4, "suspend_after_losses": 6, "spread_warn_pips": 2.5},
    "Master":  {"max_units": 5000,  "max_open": 5, "suspend_after_losses": 8, "spread_warn_pips": 3.0},
}


# ── Strategy curricula ──────────────────────────────────────────────
STRATEGIES = {
    "scalp": {
        "description": "Sub-10-min holds. Tight spreads. Many small wins.",
        "core_lessons": [
            "lesson_scalp_01_spread_economics",
            "lesson_scalp_02_micro_breakouts",
            "lesson_scalp_03_session_overlap_only",
        ],
        "edge_skew": 0.62,  # baseline skill for sim
    },
    "swing": {
        "description": "Hold hours to days. Trend-following. Wider stops.",
        "core_lessons": [
            "lesson_swing_01_trend_filters",
            "lesson_swing_02_position_sizing_over_volatility",
            "lesson_swing_03_session_carry_costs",
        ],
        "edge_skew": 0.58,
    },
    "breakout": {
        "description": "Range-bound → expansion. Volume confirms.",
        "core_lessons": [
            "lesson_brk_01_consolidation_recognition",
            "lesson_brk_02_volume_confirmation",
            "lesson_brk_03_fakeout_management",
        ],
        "edge_skew": 0.55,
    },
    "mean_revert": {
        "description": "Statistical extreme → mean. Bounded ranges only.",
        "core_lessons": [
            "lesson_mr_01_bollinger_extremes",
            "lesson_mr_02_pair_correlation_basics",
            "lesson_mr_03_regime_filter",
        ],
        "edge_skew": 0.60,
    },
    "news_event": {
        "description": "Macro release reactor. Pre-positioning forbidden.",
        "core_lessons": [
            "lesson_ne_01_calendar_discipline",
            "lesson_ne_02_first_5_min_avoidance",
            "lesson_ne_03_post_event_continuation",
        ],
        "edge_skew": 0.52,
    },
    "arb": {
        "description": "Cross-venue or cross-instrument inefficiency.",
        "core_lessons": [
            "lesson_arb_01_cost_basis_math",
            "lesson_arb_02_execution_latency_budget",
            "lesson_arb_03_inventory_management",
        ],
        "edge_skew": 0.66,
    },
}


# ── Hash helpers ─────────────────────────────────────────────────────
def _hash_int(s: str, mod: int) -> int:
    h = hashlib.sha256(s.encode("utf-8")).digest()
    return int.from_bytes(h[:4], "big") % mod


# ── Cert entry ───────────────────────────────────────────────────────
@dataclass
class SpecialistCert:
    worker_id: str
    instrument: str
    strategy: str
    tier: str
    written_score: int
    written_max: int
    sim_win_rate: float
    sim_worst_loss_pct: float
    sim_avg_hold_seconds: float
    passed: bool
    last_change_ts: float
    rationale: str = ""


# ── Specialist exam runner ───────────────────────────────────────────
def _written_exam(worker_id: str, strategy: str, tier: str,
                    knowledge_bump: float = 0.0) -> tuple[int, int, bool]:
    """Deterministic written exam tied to (worker, strategy, tier).

    Difficulty scales with tier: higher tier asks more total questions
    and requires more correct.
    """
    req = TIER_REQUIREMENTS[tier]
    total = 12 + (TIER_ORDER.index(tier) * 2)   # 12, 14, 16, 18, 20
    correct = 0
    # Base knowledge prior; higher tier requires higher baseline
    knowledge = min(0.96, 0.62 + TIER_ORDER.index(tier) * 0.06 + knowledge_bump)
    for i in range(total):
        roll = _hash_int(f"{worker_id}:{strategy}:{tier}:w:{i}", 1000) / 1000.0
        if roll < knowledge:
            correct += 1
    needed = req["written_min"]
    return (correct, total, correct >= needed)


def _sim_exam(worker_id: str, instrument: str, strategy: str,
               tier: str) -> tuple[float, float, float, bool]:
    """Deterministic sim exam. Same (worker, instrument, strategy, tier)
    always produces the same result.
    """
    req = TIER_REQUIREMENTS[tier]
    strat = STRATEGIES[strategy]
    n = req["trades"]
    skill = strat["edge_skew"] + TIER_ORDER.index(tier) * 0.04
    skill = min(0.92, max(0.30, skill))
    wins = losses = 0
    worst_loss_pct = 0.0
    hold_acc = 0.0
    for i in range(n):
        r = _hash_int(f"{worker_id}:{instrument}:{strategy}:{tier}:r:{i}",
                       100_000) / 100_000.0
        roll = _hash_int(f"{worker_id}:{instrument}:{strategy}:{tier}:o:{i}",
                          1000) / 1000.0
        is_win = roll < skill
        if is_win:
            wins += 1
        else:
            losses += 1
            pct = -(0.001 + r * 0.0055)
            worst_loss_pct = min(worst_loss_pct, pct)
        # Hold time varies by strategy
        if strategy == "scalp":      hold_acc += 30 + r * 360
        elif strategy == "swing":    hold_acc += 600 + r * 7200
        elif strategy == "breakout": hold_acc += 120 + r * 600
        elif strategy == "mean_revert": hold_acc += 90 + r * 540
        elif strategy == "news_event": hold_acc += 60 + r * 420
        elif strategy == "arb":      hold_acc += 30 + r * 240
        else:                         hold_acc += 60 + r * 540
    win_rate = wins / n
    avg_hold = hold_acc / n
    sim_pass = (win_rate >= req["win_rate"] and
                abs(worst_loss_pct) <= req["max_loss"] and
                avg_hold <= req["avg_hold"])
    return (round(win_rate, 3), round(worst_loss_pct, 5),
            round(avg_hold, 1), sim_pass)


def certify_tier(worker_id: str, instrument: str, strategy: str,
                  tier: str, knowledge_bump: float = 0.0) -> SpecialistCert:
    """Run the full (written + sim) exam for one tier."""
    if tier not in TIER_REQUIREMENTS:
        raise ValueError(f"unknown tier {tier!r}")
    if strategy not in STRATEGIES:
        raise ValueError(f"unknown strategy {strategy!r}")
    written, written_max, w_ok = _written_exam(worker_id, strategy, tier,
                                                  knowledge_bump=knowledge_bump)
    win_rate, worst_loss, avg_hold, s_ok = _sim_exam(worker_id, instrument,
                                                       strategy, tier)
    passed = w_ok and s_ok
    cert = SpecialistCert(
        worker_id=worker_id, instrument=instrument, strategy=strategy,
        tier=tier,
        written_score=written, written_max=written_max,
        sim_win_rate=win_rate, sim_worst_loss_pct=worst_loss,
        sim_avg_hold_seconds=avg_hold,
        passed=passed, last_change_ts=time.time(),
        rationale=(f"written {written}/{written_max} "
                    f"({'pass' if w_ok else 'fail'}); "
                    f"sim win_rate {win_rate:.2f} worst_loss "
                    f"{worst_loss*100:.2f}% hold {avg_hold:.0f}s "
                    f"({'pass' if s_ok else 'fail'})"),
    )
    append_log("specialist_classroom.jsonl", {
        "event": "exam",
        "worker_id": worker_id, "instrument": instrument,
        "strategy": strategy, "tier": tier,
        "passed": passed, "written": f"{written}/{written_max}",
        "sim_win_rate": win_rate,
    })
    return cert


def ladder_certify(worker_id: str, instrument: str, strategy: str,
                    cap_tier: str = "Master") -> List[SpecialistCert]:
    """Walk the tier ladder for one (worker, instrument, strategy) — stop
    at the highest tier they pass.

    Returns the list of cert attempts in tier order.
    """
    out = []
    bump = 0.0
    for tier in TIER_ORDER:
        cert = certify_tier(worker_id, instrument, strategy, tier,
                              knowledge_bump=bump)
        out.append(cert)
        if not cert.passed:
            break
        bump += 0.02  # passing one tier gives a small bump to the next
        if tier == cap_tier:
            break
    return out


def highest_tier_passed(certs: List[SpecialistCert]) -> Optional[str]:
    passed = [c.tier for c in certs if c.passed]
    if not passed: return None
    # Return the highest in TIER_ORDER
    return max(passed, key=lambda t: TIER_ORDER.index(t))


def privileges_for(tier: Optional[str]) -> Dict[str, Any]:
    if not tier or tier not in TIER_PRIVILEGES:
        return {"max_units": 0, "max_open": 0, "suspend_after_losses": 0,
                 "spread_warn_pips": 0}
    return dict(TIER_PRIVILEGES[tier])


def list_strategies() -> List[str]:
    return list(STRATEGIES.keys())


def list_tiers() -> List[str]:
    return list(TIER_ORDER)
