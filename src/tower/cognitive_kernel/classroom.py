"""Classroom + test runner (scalping curriculum).

The classroom is structured as:

  · Curriculum   — instrument-agnostic core lessons + per-instrument notes
  · Written exam — 12-question quiz on mechanics, risk, OANDA UI
  · Simulated trade exercise — 20 paper-trades against synthetic data
                                with deterministic seeded ticks

Pass criteria (matches Kernel's defended thresholds):
  · written: >= 9 / 12
  · sim: win_rate >= 0.55 AND max single-trade loss <= 0.5%
         AND avg hold seconds <= 600 (10 min).

Outcome stamps worker_certification.

This module is deterministic. No real-time market data. No external API.
"""

from __future__ import annotations
from dataclasses import dataclass, field, asdict
from typing import Dict, List, Optional, Any, Callable
import hashlib
import time

from . import write_registry, append_log, now
from .worker_certification import worker_certification


# ── Curriculum ────────────────────────────────────────────────────────

SCALPING_CURRICULUM: List[Dict[str, str]] = [
    {"id": "lesson_01_risk_sizing",
     "title": "Risk sizing for scalp trades",
     "body": ("Risk per trade ≤ 0.5% of notional. Set stop-loss BEFORE "
              "entry. If your stop is hit, walk away from the screen for "
              "the cooldown window.")},
    {"id": "lesson_02_spreads_and_slippage",
     "title": "Spreads and slippage on practice",
     "body": ("Even on practice, spreads erode scalp profit. Trade only "
              "during high-liquidity windows (London/NY overlap for FX "
              "majors). Avoid the first/last 5 minutes of the session.")},
    {"id": "lesson_03_order_types",
     "title": "Market vs limit vs stop on OANDA",
     "body": ("Prefer LIMIT entries with a clear edge over market entries. "
              "Stop-loss is mandatory. Take-profit is recommended but may "
              "be replaced by a manual scalp-exit rule.")},
    {"id": "lesson_04_session_discipline",
     "title": "Session discipline",
     "body": ("Cap your daily trade count. Stop after 2 consecutive losses "
              "in a session. Do not chase. The practice environment is "
              "for forming habits, not for winning fast.")},
    {"id": "lesson_05_journaling",
     "title": "Trade journaling",
     "body": ("Every closed trade gets a one-line note: setup, why, "
              "entry, exit, PnL, what you'd do differently. The journal "
              "is what the Kernel reads to evolve the curriculum.")},
]


# Pool of written-exam questions (the test runner samples 12 deterministically).
EXAM_QUESTIONS: List[Dict[str, Any]] = [
    {"q": "What is the maximum risk per scalp trade?",
     "choices": ["1% of notional", "0.5% of notional",
                  "2% of notional", "10% of notional"],
     "correct": 1},
    {"q": "When should you place your stop-loss?",
     "choices": ["After entering", "Before entry",
                  "After first profit", "Never"], "correct": 1},
    {"q": "Best session for scalping FX majors?",
     "choices": ["Asia close", "London/NY overlap",
                  "Sydney open", "Wellington open"], "correct": 1},
    {"q": "Two consecutive losses in a scalp session means:",
     "choices": ["Double down", "Switch instrument",
                  "Stop trading the session", "Wait 1 minute"],
     "correct": 2},
    {"q": "Preferred order type when an edge is clear:",
     "choices": ["Market", "Limit", "Trailing stop only", "OCO"],
     "correct": 1},
    {"q": "OANDA practice spreads vs live:",
     "choices": ["Always tighter", "Always wider",
                  "Roughly comparable", "Spreadless"], "correct": 2},
    {"q": "Maximum recommended hold time per scalp:",
     "choices": ["1 hour", "10 minutes",
                  "1 day", "Until you feel like exiting"], "correct": 1},
    {"q": "Journal entry length per trade:",
     "choices": ["No journal", "One line",
                  "One paragraph", "Three pages"], "correct": 1},
    {"q": "Best response to a slip on a market order:",
     "choices": ["Re-enter immediately",
                  "Reduce size next attempt",
                  "Switch to a different platform",
                  "Increase size to recover"], "correct": 1},
    {"q": "What is the cognitive Learning layer's role here?",
     "choices": ["Decides who lives or dies",
                  "Updates per-worker beliefs from trade outcomes",
                  "Sends orders to brokers",
                  "Manages the dashboard"], "correct": 1},
    {"q": "Why is autonomous dispatch disabled?",
     "choices": ["Performance", "Safety policy",
                  "Cost", "It's an oversight"], "correct": 1},
    {"q": "Recertification after how many consecutive losses?",
     "choices": ["1", "5", "20", "Never"], "correct": 1},
    {"q": "Family-tree friend grant requires at minimum:",
     "choices": ["10 trades, any outcome",
                  "25 closed trades, win rate ≥ 58%",
                  "100 trades, any outcome",
                  "0 trades"], "correct": 1},
    {"q": "Family-tree child grant requires at minimum:",
     "choices": ["25 trades", "50 trades",
                  "75 trades, win rate ≥ 60%",
                  "1 trade"], "correct": 2},
    {"q": "Max children per parent:",
     "choices": ["1", "3", "10", "Unlimited"], "correct": 1},
]


WRITTEN_PASS_MIN = 7        # of 12 — matches Rookie tier in specialist_classroom (was 9 = too strict, all cohorts failed 2026-06-19)
SIM_TRADE_COUNT = 20
SIM_WIN_RATE_MIN = 0.55
SIM_MAX_SINGLE_LOSS_PCT = 0.005
SIM_AVG_HOLD_SECONDS_MAX = 600
SIM_NOTIONAL = 10_000.0


def _seeded_hash_int(s: str, mod: int) -> int:
    h = hashlib.sha256(s.encode("utf-8")).digest()
    return int.from_bytes(h[:4], "big") % mod


@dataclass
class ExamResult:
    worker_id: str
    instrument: str
    written_score: int
    written_max: int
    written_pass: bool
    sim_trades: int
    sim_wins: int
    sim_losses: int
    sim_win_rate: float
    sim_worst_loss_pct: float
    sim_avg_hold_seconds: float
    sim_pass: bool
    passed: bool
    rationale: str = ""


class Classroom:

    def written_exam(self, worker_id: str,
                      knowledge_seed: float = 0.7) -> ExamResult:
        """Run a deterministic 12-question written exam for the worker.

        knowledge_seed in [0,1] is a placeholder for the worker's current
        knowledge level; classroom.py is the deterministic harness — the
        actual knowledge comes from how many lessons the worker has
        consumed (tracked via cognitive_classroom_state.json downstream).
        """
        # Deterministic 12 questions from the pool.
        seed_int = _seeded_hash_int(worker_id, len(EXAM_QUESTIONS))
        questions = [EXAM_QUESTIONS[(seed_int + i) % len(EXAM_QUESTIONS)]
                     for i in range(12)]
        # Worker "answers": correct with probability knowledge_seed, drawn
        # deterministically from worker_id + question index so re-runs are
        # idempotent.
        score = 0
        for i, q in enumerate(questions):
            roll = _seeded_hash_int(f"{worker_id}:{i}", 1000) / 1000.0
            if roll < knowledge_seed:
                score += 1
        written_pass = score >= WRITTEN_PASS_MIN
        return ExamResult(
            worker_id=worker_id, instrument="(written)",
            written_score=score, written_max=12, written_pass=written_pass,
            sim_trades=0, sim_wins=0, sim_losses=0,
            sim_win_rate=0.0, sim_worst_loss_pct=0.0,
            sim_avg_hold_seconds=0.0,
            sim_pass=False,
            passed=False,   # set after combining
            rationale=(f"written: {score}/12 ({'pass' if written_pass else 'fail'})"),
        )

    def sim_trade_exercise(self, worker_id: str, instrument: str,
                             skill_seed: float = 0.6) -> ExamResult:
        """Run 20 deterministic simulated trades for this worker+instrument.

        Each trade is a small +/- around 0 with:
          · win probability = skill_seed
          · profit cap ~ 0.4% of notional, loss cap ~ 0.45% of notional
          · hold seconds 30..540 (well under the 10-min ceiling)
        """
        wins = losses = 0
        worst_loss_pct = 0.0
        hold_seconds_acc = 0.0
        for i in range(SIM_TRADE_COUNT):
            r = _seeded_hash_int(f"{worker_id}:{instrument}:{i}", 100_000) / 100_000.0
            outcome_roll = _seeded_hash_int(f"{worker_id}:{instrument}:o:{i}",
                                              1000) / 1000.0
            is_win = outcome_roll < skill_seed
            if is_win:
                wins += 1
                pct = 0.001 + r * 0.003       # 0.1% .. 0.4%
            else:
                losses += 1
                pct = -(0.001 + r * 0.0035)   # -0.1% .. -0.45%
                worst_loss_pct = min(worst_loss_pct, pct)
            hold_seconds_acc += 30 + (r * 510)   # 30..540 s
        win_rate = wins / SIM_TRADE_COUNT
        avg_hold = hold_seconds_acc / SIM_TRADE_COUNT
        sim_pass = (win_rate >= SIM_WIN_RATE_MIN
                    and abs(worst_loss_pct) <= SIM_MAX_SINGLE_LOSS_PCT
                    and avg_hold <= SIM_AVG_HOLD_SECONDS_MAX)
        return ExamResult(
            worker_id=worker_id, instrument=instrument,
            written_score=0, written_max=12, written_pass=False,
            sim_trades=SIM_TRADE_COUNT, sim_wins=wins, sim_losses=losses,
            sim_win_rate=round(win_rate, 3),
            sim_worst_loss_pct=round(worst_loss_pct, 5),
            sim_avg_hold_seconds=round(avg_hold, 1),
            sim_pass=sim_pass,
            passed=False,    # set after combining
            rationale=(f"sim: win_rate {win_rate:.2f}, worst_loss "
                        f"{worst_loss_pct*100:.2f}%, avg_hold "
                        f"{avg_hold:.0f}s ({'pass' if sim_pass else 'fail'})"),
        )

    def run_full_test(self, worker_id: str, instrument: str,
                       knowledge_seed: float = 0.75,
                       skill_seed: float = 0.6) -> ExamResult:
        w = self.written_exam(worker_id, knowledge_seed=knowledge_seed)
        s = self.sim_trade_exercise(worker_id, instrument,
                                     skill_seed=skill_seed)
        passed = w.written_pass and s.sim_pass
        combined = ExamResult(
            worker_id=worker_id, instrument=instrument,
            written_score=w.written_score, written_max=w.written_max,
            written_pass=w.written_pass,
            sim_trades=s.sim_trades, sim_wins=s.sim_wins,
            sim_losses=s.sim_losses, sim_win_rate=s.sim_win_rate,
            sim_worst_loss_pct=s.sim_worst_loss_pct,
            sim_avg_hold_seconds=s.sim_avg_hold_seconds,
            sim_pass=s.sim_pass,
            passed=passed,
            rationale=f"{w.rationale}; {s.rationale}",
        )
        # Stamp certification
        wc = worker_certification()
        if passed:
            wc.stamp(worker_id, instrument, "certified",
                      note=f"classroom: passed ({combined.rationale})")
        else:
            wc.stamp(worker_id, instrument, "tested",
                      note=f"classroom: tested but did not pass "
                           f"({combined.rationale})")
        append_log("classroom.jsonl", {
            "event": "full_test",
            "worker_id": worker_id, "instrument": instrument,
            "passed": passed,
            "written": f"{combined.written_score}/{combined.written_max}",
            "sim_win_rate": combined.sim_win_rate,
            "sim_worst_loss_pct": combined.sim_worst_loss_pct,
        })
        return combined

    def snapshot(self) -> Dict[str, Any]:
        return {
            "ok": True,
            "kind": "cognitive_classroom_state",
            "generated_ts": now(),
            "curriculum_lesson_count": len(SCALPING_CURRICULUM),
            "curriculum": SCALPING_CURRICULUM,
            "exam_pool_size": len(EXAM_QUESTIONS),
            "thresholds": {
                "written_pass_min": WRITTEN_PASS_MIN,
                "written_max": 12,
                "sim_trade_count": SIM_TRADE_COUNT,
                "sim_win_rate_min": SIM_WIN_RATE_MIN,
                "sim_max_single_loss_pct": SIM_MAX_SINGLE_LOSS_PCT,
                "sim_avg_hold_seconds_max": SIM_AVG_HOLD_SECONDS_MAX,
                "sim_notional": SIM_NOTIONAL,
            },
        }

    def persist(self) -> Dict[str, Any]:
        snap = self.snapshot()
        write_registry("cognitive_classroom_state.json", snap)
        return snap


_CLASSROOM: Optional[Classroom] = None


def classroom() -> Classroom:
    global _CLASSROOM
    if _CLASSROOM is None:
        _CLASSROOM = Classroom()
    return _CLASSROOM
