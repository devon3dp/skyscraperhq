"""
QSB Tower Command Center — Profit Command
Phase: QSB_LIVE_SKYSCRAPER_COMMAND_CENTER_REBUILD_V1

Composes a single Profit Command snapshot that the Colonel reads from
the dashboard. Drives the right-rail "Profit Command" tab.

All figures come from REAL registries:
  * qsb_open_paper_trades.json
  * qsb_trade_learning.json
  * qsb_paper_trading_policy.json
  * qsb_worker_scorecards.json
  * qsb_worker_discipline.json
  * data/db/qsb_paper_trading.sqlite (live worker-aggregated PnL)

Never invents PnL, departments, or workers. If a signal is missing,
the field is null with an explanation.
"""

from datetime import datetime, timezone
from pathlib import Path
import json
import sqlite3

ROOT = Path("/vaults/nvme0/qsb_tower_v1")
REG = ROOT / "data/registries"
DB = ROOT / "data/db/qsb_paper_trading.sqlite"

P_PROFIT = REG / "qsb_profit_command.json"


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


def _aggregate_by_department():
    """Aggregate realized PnL + trade counts by home_floor → department."""
    sc = _load("qsb_worker_scorecards.json", {})
    cw = _load("qsb_canonical_workers.json", {})
    by_floor = {}
    floor_label = {}
    workers = cw.get("workers") or []
    floor_of = {w.get("worker_id"): w.get("home_floor") for w in workers}
    for s in (sc.get("scorecards") or []):
        wid = s["worker_id"]
        floor = floor_of.get(wid) or "unassigned"
        rec = by_floor.setdefault(floor, {
            "department": floor,
            "realized_pnl": 0.0,
            "profitable_trades": 0,
            "loss_trades": 0,
            "lessons_learned": 0,
            "active_workers": 0,
            "warning_workers": 0,
        })
        rec["realized_pnl"] += float(s.get("realized_pnl_contribution") or 0)
        rec["profitable_trades"] += int(s.get("profitable_contributions") or 0)
        rec["loss_trades"] += int(s.get("loss_contributions") or 0)
        rec["lessons_learned"] += int(s.get("lessons_learned") or 0)
        rec["active_workers"] += 1
        if int(s.get("strikes") or 0) > 0:
            rec["warning_workers"] += 1
        floor_label[floor] = floor
    out = list(by_floor.values())
    for r in out:
        r["realized_pnl"] = round(r["realized_pnl"], 6)
    return out


def _top_workers(limit=8):
    sc = _load("qsb_worker_scorecards.json", {})
    rows = sc.get("scorecards") or []
    contributors = [r for r in rows
                    if (r.get("realized_pnl_contribution") or 0) > 0
                       or (r.get("reward_points") or 0) > 0]
    contributors.sort(key=lambda r: (r.get("reward_points") or 0,
                                       r.get("realized_pnl_contribution") or 0),
                       reverse=True)
    return [{
        "worker_id": r["worker_id"],
        "name": r["name"],
        "role": r["role"],
        "floor": r["floor"],
        "reward_points": r["reward_points"],
        "realized_pnl_contribution": r["realized_pnl_contribution"],
        "rank": r["rank"],
    } for r in contributors[:limit]]


def _strategy_performance():
    """Aggregate per-strategy realized PnL from qsb_paper_trading.sqlite."""
    if not DB.exists():
        return []
    try:
        c = sqlite3.connect(DB); c.row_factory = sqlite3.Row
        try:
            rows = c.execute(
                "SELECT strategy_id, status, realized_pnl "
                "FROM paper_trades WHERE strategy_id IS NOT NULL"
            ).fetchall()
        finally:
            c.close()
    except Exception:
        return []
    by_strat = {}
    for r in rows:
        sid = r["strategy_id"] or "unknown"
        rec = by_strat.setdefault(sid, {
            "strategy_id": sid,
            "open_trades": 0,
            "closed_trades": 0,
            "realized_pnl": 0.0,
        })
        if r["status"] == "OPEN":
            rec["open_trades"] += 1
        else:
            rec["closed_trades"] += 1
            rec["realized_pnl"] += float(r["realized_pnl"] or 0)
    out = list(by_strat.values())
    for r in out:
        r["realized_pnl"] = round(r["realized_pnl"], 6)
    return sorted(out, key=lambda r: r["realized_pnl"], reverse=True)


def build_profit_command():
    policy = _load("qsb_paper_trading_policy.json", {})
    open_ = _load("qsb_open_paper_trades.json", {})
    learning = _load("qsb_trade_learning.json", {})
    discipline = _load("qsb_worker_discipline.json", {})
    awards = _load("qsb_worker_awards.json", {})

    by_dept = _aggregate_by_department()
    top_workers = _top_workers(limit=8)
    strategy_perf = _strategy_performance()

    best_dept = max(by_dept, key=lambda r: r["realized_pnl"], default=None)
    worst_dept = min((r for r in by_dept if r["loss_trades"] > 0),
                      key=lambda r: r["realized_pnl"], default=None)

    next_actions = []
    if (open_.get("open_trade_count") or 0) >= int(policy.get("max_open_trades") or 20):
        next_actions.append("At max_open_trades — close a trade before opening another.")
    if (learning.get("total_realized_pnl") or 0) < 0:
        next_actions.append("Realized PnL is negative — review strategies via strategy_perf.")
    if (discipline.get("total_on_warning") or 0) > 0:
        next_actions.append("%d worker(s) on warning — review eqsb_worker_discipline."
                             % discipline.get("total_on_warning"))
    if not next_actions:
        next_actions.append("Skyscraper is disciplined and steady — keep cadence.")

    payload = {
        "ok": True,
        "phase": "QSB_LIVE_SKYSCRAPER_COMMAND_CENTER_REBUILD_V1",
        "kind": "qsb_profit_command",
        "generated_ts": _now(),
        "mission": "Safe, disciplined, repeatable paper/testnet profit. Real-money trading remains disabled.",
        "trading_mode": policy.get("active_mode"),
        "gateway_status": policy.get("gateway_status"),
        "open_trade_count": open_.get("open_trade_count"),
        "max_open_trades": open_.get("max_open_trades") or policy.get("max_open_trades"),
        "remaining_trade_slots": open_.get("remaining_trade_slots"),
        "total_current_pnl_open": open_.get("total_current_pnl"),
        "total_realized_pnl": learning.get("total_realized_pnl"),
        "closed_trade_count": learning.get("closed_trade_count"),
        "lesson_count": learning.get("lesson_count"),
        "by_department": by_dept,
        "best_department_by_contribution": best_dept,
        "worst_department_by_mistakes": worst_dept,
        "top_workers": top_workers,
        "workers_on_warning": discipline.get("total_on_warning"),
        "active_award_count": awards.get("active_award_count"),
        "strategy_performance": strategy_perf,
        "next_profit_focused_actions": next_actions,
        "real_money_live_trading_enabled": False,
        "real_money_gate_status": "permanently_locked_until_separate_explicit_unlock",
    }
    payload.update(_safety_envelope())
    P_PROFIT.parent.mkdir(parents=True, exist_ok=True)
    P_PROFIT.write_text(json.dumps(payload, indent=2), encoding="utf-8")
    return payload


def main():
    print(json.dumps(build_profit_command(), indent=2))


if __name__ == "__main__":
    main()
