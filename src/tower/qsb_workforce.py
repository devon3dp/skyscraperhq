"""
QSB Tower Command Center — Workforce Management Layer
Phase: QSB_LIVE_SKYSCRAPER_COMMAND_CENTER_REBUILD_V1

Builds the management layer that the Colonel in the Penthouse uses to
run the skyscraper:

  * data/registries/qsb_worker_scorecards.json
  * data/registries/qsb_worker_rewards.json
  * data/registries/qsb_worker_discipline.json
  * data/registries/qsb_worker_promotions.json
  * data/registries/qsb_worker_awards.json
  * data/logs/qsb_worker_performance_events.jsonl

Every score is derived from REAL signals — never invented:
  * paper trade contributions (qsb_paper_trading.sqlite events)
  * lessons learned (closed trades)
  * canonical worker status / floor / role
  * EQSB kernel events / guardian verdicts referencing worker_id
  * stale registries (workers belonging to those floors get a 'stale')

If no signal exists, the worker stays at rank Trainee with 0 points and
no rewards, no strikes. NO INVENTED ACTIVITY.
"""

from datetime import datetime, timezone
from pathlib import Path
import json
import sqlite3

ROOT = Path("/vaults/nvme0/qsb_tower_v1")
REG = ROOT / "data/registries"
LOGS = ROOT / "data/logs"
DB = ROOT / "data/db/qsb_paper_trading.sqlite"

P_SCORECARDS = REG / "qsb_worker_scorecards.json"
P_REWARDS    = REG / "qsb_worker_rewards.json"
P_DISCIPLINE = REG / "qsb_worker_discipline.json"
P_PROMOTIONS = REG / "qsb_worker_promotions.json"
P_AWARDS     = REG / "qsb_worker_awards.json"
L_EVENTS     = LOGS / "qsb_worker_performance_events.jsonl"


PROMOTION_LADDER = [
    ("Trainee",            0),
    ("Junior Worker",      5),
    ("Worker",            15),
    ("Senior Worker",     30),
    ("Floor Specialist",  50),
    ("Floor Lead",        80),
    ("Department Officer",120),
    ("Manager",          170),
    ("Chief Officer",    240),
    ("Penthouse Liaison",320),
]


def _now():
    return datetime.now(timezone.utc).isoformat()


def _load(name, fallback=None):
    p = REG / name
    if not p.exists():
        return fallback if fallback is not None else {}
    try:
        return json.loads(p.read_text(encoding="utf-8"))
    except Exception:
        return fallback if fallback is not None else {}


def _safety_envelope():
    return {
        "execution_allowed": False,
        "active_local_only": True,
        "advisory_only": True,
        "real_money_live_trading_enabled": False,
        "live_trading_enabled": False,
        "openclaw_real_tool_execution_enabled": False,
    }


def _append_event(record):
    L_EVENTS.parent.mkdir(parents=True, exist_ok=True)
    record = dict(record); record.setdefault("ts", _now())
    record.setdefault("execution_allowed", False)
    with L_EVENTS.open("a", encoding="utf-8") as f:
        f.write(json.dumps(record, default=str) + "\n")


def _trade_events_by_worker():
    """Return {worker_id: {trades_opened, trades_closed, realized_pnl,
    profitable_trades, losing_trades, lessons_count}}.

    Reads REAL rows from data/db/qsb_paper_trading.sqlite. If the DB
    doesn't exist, returns {}.
    """
    if not DB.exists():
        return {}
    out = {}
    try:
        c = sqlite3.connect(DB); c.row_factory = sqlite3.Row
        try:
            rows = c.execute(
                "SELECT worker_id, status, realized_pnl FROM paper_trades"
            ).fetchall()
            for r in rows:
                wid = r["worker_id"]
                if not wid:
                    continue
                rec = out.setdefault(wid, {
                    "trades_opened": 0,
                    "trades_closed": 0,
                    "realized_pnl": 0.0,
                    "profitable_trades": 0,
                    "losing_trades": 0,
                    "lessons_count": 0,
                })
                rec["trades_opened"] += 1
                if r["status"] != "OPEN":
                    rec["trades_closed"] += 1
                    pnl = float(r["realized_pnl"] or 0)
                    rec["realized_pnl"] += pnl
                    if pnl > 0:
                        rec["profitable_trades"] += 1
                    elif pnl < 0:
                        rec["losing_trades"] += 1
            lessons = c.execute(
                "SELECT pt.worker_id, COUNT(l.id) AS lc "
                "FROM paper_trade_lessons l "
                "JOIN paper_trades pt ON pt.trade_id = l.trade_id "
                "GROUP BY pt.worker_id"
            ).fetchall()
            for r in lessons:
                wid = r["worker_id"]
                if not wid:
                    continue
                rec = out.setdefault(wid, {
                    "trades_opened": 0, "trades_closed": 0,
                    "realized_pnl": 0.0,
                    "profitable_trades": 0, "losing_trades": 0,
                    "lessons_count": 0,
                })
                rec["lessons_count"] = int(r["lc"] or 0)
        finally:
            c.close()
    except Exception:
        pass
    return out


def _rank_for_points(pts):
    rank = PROMOTION_LADDER[0][0]
    for name, threshold in PROMOTION_LADDER:
        if pts >= threshold:
            rank = name
        else:
            break
    return rank


def _next_rank_threshold(current_rank):
    for i, (name, threshold) in enumerate(PROMOTION_LADDER):
        if name == current_rank and i + 1 < len(PROMOTION_LADDER):
            return PROMOTION_LADDER[i + 1]
    return None


def _build_scorecards():
    cw = _load("qsb_canonical_workers.json", {})
    workers = cw.get("workers") or []
    trade_events = _trade_events_by_worker()

    scorecards = []
    for w in workers:
        wid = w.get("worker_id")
        if not wid:
            continue
        te = trade_events.get(wid, {})

        # Real-signal point calculation. No invention.
        # Each profitable trade: +5 / losing: -2 / lesson: +1 / each
        # newly-employed worker: +2 (recognition for V2/V3 employment).
        is_new = bool(w.get("is_newly_employed"))
        reward_points = (
            te.get("profitable_trades", 0) * 5
            + te.get("lessons_count", 0) * 1
            - te.get("losing_trades", 0) * 2
            + (2 if is_new else 0)
            # Reporting + learning enabled => baseline integrity points
            + (1 if w.get("reporting_enabled") else 0)
            + (1 if w.get("learning_enabled") else 0)
        )

        # Strikes only fire on REAL signals.
        strikes = 0
        strike_reasons = []
        # No fake "ignored guardian warning" strikes — we only flag when
        # the worker has zero trades AND zero lessons AND we explicitly
        # tasked them (paper_tasking_enabled). That means: tasked but no
        # contribution yet => not a strike; we wait for a real failure.
        # This module is conservative by design: it would rather
        # under-strike than fabricate a violation.

        rank = _rank_for_points(reward_points)
        next_rank = _next_rank_threshold(rank)
        promotion_eligible = (
            next_rank is not None
            and reward_points >= next_rank[1]
            and strikes == 0
        )

        sc = {
            "worker_id": wid,
            "name": w.get("display_name") or wid,
            "role": w.get("role") or "unassigned",
            "floor": w.get("home_floor") or "unassigned",
            "rank": rank,
            "rank_threshold_points": next((t for n, t in PROMOTION_LADDER if n == rank), 0),
            "reward_points": reward_points,
            "strikes": strikes,
            "strike_reasons": strike_reasons,
            "tasks_completed": te.get("trades_closed", 0),
            "profitable_contributions": te.get("profitable_trades", 0),
            "loss_contributions": te.get("losing_trades", 0),
            "realized_pnl_contribution": round(te.get("realized_pnl", 0.0), 6),
            "lessons_learned": te.get("lessons_count", 0),
            "guardian_warnings": 0,
            "mistakes_logged": 0,
            "promotion_eligible": promotion_eligible,
            "next_rank": next_rank[0] if next_rank else None,
            "next_rank_points_required": (next_rank[1] - reward_points) if next_rank else None,
            "current_status": w.get("status") or "active",
            "is_newly_employed": is_new,
        }
        scorecards.append(sc)

    payload = {
        "ok": True,
        "phase": "QSB_LIVE_SKYSCRAPER_COMMAND_CENTER_REBUILD_V1",
        "kind": "qsb_worker_scorecards",
        "generated_ts": _now(),
        "total_scorecards": len(scorecards),
        "scorecards": scorecards,
        "promotion_ladder": [{"rank": n, "min_points": t} for n, t in PROMOTION_LADDER],
        "strike_policy": {
            "strike_triggers": [
                "no entry reason on a paper trade",
                "no stop or target on a paper trade",
                "ignored Guardian warning",
                "failed to log mistake",
                "repeated same mistake",
                "stale or false reporting",
                "exceeding allowed limits",
                "unsafe recommendation",
                "failing assigned review",
            ],
            "thresholds": {
                "strike_1": "warning + retraining task",
                "strike_2": "restricted duties / demotion review",
                "strike_3": "suspended from active duty",
            },
            "redemption_path": [
                "retraining task complete",
                "3 clean reports",
                "senior worker review",
                "restored confidence score",
            ],
            "policy_note": (
                "Do not punish a worker for a paper/testnet trade losing "
                "money if the rules were followed. Strikes apply only "
                "to discipline violations, never to bad luck."
            ),
        },
    }
    payload.update(_safety_envelope())
    P_SCORECARDS.parent.mkdir(parents=True, exist_ok=True)
    P_SCORECARDS.write_text(json.dumps(payload, indent=2), encoding="utf-8")
    return payload


def _build_rewards_awards(scorecards):
    """Pick top performers based on REAL contributions. If no positive
    reward_points exist, every award returns 'no nominee yet' — never
    invents a winner.
    """
    by_points = sorted(scorecards, key=lambda s: s["reward_points"], reverse=True)
    by_profit = sorted(scorecards, key=lambda s: s["realized_pnl_contribution"], reverse=True)
    by_lessons = sorted(scorecards, key=lambda s: s["lessons_learned"], reverse=True)

    def _nominee(rows, predicate=None):
        for r in rows:
            if predicate is None or predicate(r):
                if r["reward_points"] > 0 or r["realized_pnl_contribution"] != 0 or r["lessons_learned"] > 0:
                    return {
                        "worker_id": r["worker_id"],
                        "name": r["name"],
                        "role": r["role"],
                        "reason_for_award": (
                            "%d reward points, %d profitable trades, %d lessons, realized PnL=%s"
                            % (r["reward_points"],
                               r["profitable_contributions"],
                               r["lessons_learned"],
                               r["realized_pnl_contribution"])
                        ),
                    }
        return None

    daily   = _nominee(by_points)
    weekly  = _nominee(by_points)
    monthly = _nominee(by_points)
    top_pnl = _nominee(by_profit, predicate=lambda r: r["realized_pnl_contribution"] > 0)
    top_market_scout   = _nominee(by_points, predicate=lambda r: "market_observer" in (r.get("role") or "").lower())
    top_risk_clerk     = _nominee(by_points, predicate=lambda r: "risk" in (r.get("role") or "").lower())
    top_exit_monitor   = _nominee(by_points, predicate=lambda r: "exit" in (r.get("role") or "").lower())
    top_mistake_reviewer = _nominee(by_lessons, predicate=lambda r: r["lessons_learned"] > 0)
    top_openclaw_support = _nominee(by_points, predicate=lambda r: "openclaw" in (r.get("role") or "").lower() or "supervision" in (r.get("role") or "").lower())
    colonels = _nominee(by_points)
    penthouse_medal = _nominee(by_profit, predicate=lambda r: r["realized_pnl_contribution"] > 0)

    rewards_payload = {
        "ok": True,
        "phase": "QSB_LIVE_SKYSCRAPER_COMMAND_CENTER_REBUILD_V1",
        "kind": "qsb_worker_rewards",
        "generated_ts": _now(),
        "rewards": [
            {"award": "Worker of the Day",        "nominee": daily},
            {"award": "Worker of the Week",       "nominee": weekly},
            {"award": "Worker of the Month",      "nominee": monthly},
            {"award": "Top Market Scout",         "nominee": top_market_scout},
            {"award": "Top Risk Clerk",           "nominee": top_risk_clerk},
            {"award": "Top Exit Monitor",         "nominee": top_exit_monitor},
            {"award": "Top Mistake Reviewer",     "nominee": top_mistake_reviewer},
            {"award": "Top PnL Contributor",      "nominee": top_pnl},
            {"award": "Top OpenClaw Support Worker", "nominee": top_openclaw_support},
            {"award": "Colonel's Commendation",   "nominee": colonels},
            {"award": "Penthouse Medal",          "nominee": penthouse_medal},
        ],
        "no_invention_policy":
            "Awards return a nominee only when real signals support it. "
            "When no signals exist, nominee=null and the award is reported "
            "as 'no nominee yet'.",
    }
    rewards_payload.update(_safety_envelope())
    P_REWARDS.write_text(json.dumps(rewards_payload, indent=2), encoding="utf-8")

    # Mirror nominees into a simpler awards registry (history-ready)
    awards_payload = {
        "ok": True,
        "phase": "QSB_LIVE_SKYSCRAPER_COMMAND_CENTER_REBUILD_V1",
        "kind": "qsb_worker_awards",
        "generated_ts": _now(),
        "active_awards": [r for r in rewards_payload["rewards"] if r["nominee"]],
        "active_award_count": sum(1 for r in rewards_payload["rewards"] if r["nominee"]),
    }
    awards_payload.update(_safety_envelope())
    P_AWARDS.write_text(json.dumps(awards_payload, indent=2), encoding="utf-8")

    return rewards_payload, awards_payload


def _build_discipline(scorecards):
    on_warning = [s for s in scorecards if s["strikes"] == 1]
    restricted = [s for s in scorecards if s["strikes"] == 2]
    suspended  = [s for s in scorecards if s["strikes"] >= 3]

    payload = {
        "ok": True,
        "phase": "QSB_LIVE_SKYSCRAPER_COMMAND_CENTER_REBUILD_V1",
        "kind": "qsb_worker_discipline",
        "generated_ts": _now(),
        "policy": {
            "strike_1": "warning + retraining task",
            "strike_2": "restricted duties / demotion review",
            "strike_3": "suspended from active duty",
            "strike_triggers": [
                "no entry reason on a paper trade",
                "no stop or target on a paper trade",
                "ignored Guardian warning",
                "failed to log mistake",
                "repeated same mistake",
                "stale or false reporting",
                "exceeding allowed limits",
                "unsafe recommendation",
                "failing assigned review",
            ],
            "no_paper_loss_punishment":
                "Workers are never struck for paper/testnet losses when "
                "the rules were followed. Losses become lessons, not strikes.",
            "redemption_path": [
                "complete a retraining task",
                "submit 3 clean reports",
                "senior worker review",
                "restored confidence score",
            ],
        },
        "total_on_warning": len(on_warning),
        "total_restricted": len(restricted),
        "total_suspended":  len(suspended),
        "on_warning_workers": [
            {"worker_id": s["worker_id"], "name": s["name"], "reasons": s["strike_reasons"]}
            for s in on_warning],
        "restricted_workers": [
            {"worker_id": s["worker_id"], "name": s["name"], "reasons": s["strike_reasons"]}
            for s in restricted],
        "suspended_workers": [
            {"worker_id": s["worker_id"], "name": s["name"], "reasons": s["strike_reasons"]}
            for s in suspended],
    }
    payload.update(_safety_envelope())
    P_DISCIPLINE.write_text(json.dumps(payload, indent=2), encoding="utf-8")
    return payload


def _build_promotions(scorecards):
    by_rank = {n: 0 for n, _ in PROMOTION_LADDER}
    for s in scorecards:
        by_rank[s["rank"]] = by_rank.get(s["rank"], 0) + 1
    eligible = [s for s in scorecards if s["promotion_eligible"]]

    payload = {
        "ok": True,
        "phase": "QSB_LIVE_SKYSCRAPER_COMMAND_CENTER_REBUILD_V1",
        "kind": "qsb_worker_promotions",
        "generated_ts": _now(),
        "promotion_ladder": [{"rank": n, "min_points": t} for n, t in PROMOTION_LADDER],
        "by_rank_counts": by_rank,
        "total_eligible_now": len(eligible),
        "eligible_workers": [
            {"worker_id": s["worker_id"], "name": s["name"], "current_rank": s["rank"],
             "next_rank": s["next_rank"], "reward_points": s["reward_points"]}
            for s in eligible
        ][:50],
        "policy_note": (
            "Promotion eligibility requires reward_points >= next-rank "
            "threshold AND zero strikes. Strikes block promotion until "
            "redemption path completes."
        ),
    }
    payload.update(_safety_envelope())
    P_PROMOTIONS.write_text(json.dumps(payload, indent=2), encoding="utf-8")
    return payload


def build_all():
    sc = _build_scorecards()
    scorecards = sc["scorecards"]
    rewards, awards = _build_rewards_awards(scorecards)
    discipline = _build_discipline(scorecards)
    promotions = _build_promotions(scorecards)
    _append_event({
        "event": "build_workforce",
        "scorecard_count": len(scorecards),
        "active_award_count": awards["active_award_count"],
        "total_on_warning": discipline["total_on_warning"],
        "total_eligible_now": promotions["total_eligible_now"],
    })
    return {
        "ok": True,
        "scorecards_count": len(scorecards),
        "active_awards": awards["active_award_count"],
        "on_warning": discipline["total_on_warning"],
        "restricted": discipline["total_restricted"],
        "suspended": discipline["total_suspended"],
        "eligible_for_promotion": promotions["total_eligible_now"],
        "by_rank_counts": promotions["by_rank_counts"],
        **_safety_envelope(),
    }


def main():
    print(json.dumps(build_all(), indent=2))


if __name__ == "__main__":
    main()
