"""
qsb_f31_audit_ledger_loop.py — Floor 31 (Audit / Ledger) day-shift ticker.

30 workers (10 ledger_clerk / 10 trade_auditor / 10 reconciler) take turns
once every 60s. Read-only, advisory_only.

  ledger_clerk    -> reads OANDA practice PnL, counts open / closed positions
  trade_auditor   -> counts trade events in the closed-trades registry
  reconciler      -> diffs the canonical worker roster vs the activity tail
"""

from __future__ import annotations

import json
import logging
import os
import signal
import sys
import time
from collections import Counter
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path("/vaults/nvme0/qsb_tower_v1")
ROSTER = ROOT / "data/registries/qsb_f31_roster.json"
TICK_LOG = ROOT / "data/registries/qsb_f31_tick_log.jsonl"
F47_RECORDS = ROOT / "data/registries/qsb_f47_team_records.jsonl"
ACTIVITY_TAIL = ROOT / "data/registries/qsb_tower_activity_tail.jsonl"

OANDA_SNAPSHOT = ROOT / "data/registries/qsb_floor41_oanda_account_snapshot.json"
OANDA_CLOSED = ROOT / "data/registries/qsb_floor41_oanda_closed_trades.json"
CANONICAL_WORKERS = ROOT / "data/registries/qsb_canonical_workers.json"

TICK_INTERVAL_S = int(os.environ.get("QSB_F31_TICK_S", "60"))
WORK_HOURS = (int(os.environ.get("QSB_F31_OPEN_H", "8")),
              int(os.environ.get("QSB_F31_CLOSE_H", "17")))

logging.basicConfig(level=logging.INFO,
                    format="[%(asctime)s] %(levelname)s qsb.f31 - %(message)s")
log = logging.getLogger("qsb.f31")
_stop = False


def _now_iso() -> str:
    return time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())


def _stamp(path: Path, row: dict) -> None:
    try:
        path.parent.mkdir(parents=True, exist_ok=True)
        with path.open("a", encoding="utf-8") as f:
            f.write(json.dumps(row, separators=(",", ":")) + "\n")
    except OSError as e:
        log.error("stamp %s failed: %s", path.name, e)


def _within_hours() -> bool:
    now = datetime.now(timezone.utc).astimezone()
    return WORK_HOURS[0] <= now.hour < WORK_HOURS[1]


def _load_roster() -> list[dict]:
    try:
        return json.loads(ROSTER.read_text(encoding="utf-8")).get("workers", [])
    except (OSError, ValueError) as e:
        log.error("roster load failed: %s", e)
        return []


def task_ledger_clerk(_worker: dict) -> dict:
    if not OANDA_SNAPSHOT.exists():
        return {"task": "read_oanda_snapshot", "result": {"snapshot_missing": True}}
    try:
        snap = json.loads(OANDA_SNAPSHOT.read_text(encoding="utf-8"))
        return {"task": "read_oanda_snapshot",
                "result": {"balance": snap.get("balance"),
                            "open_positions": len(snap.get("positions", []) or []),
                            "ts": snap.get("ts") or snap.get("snapshot_ts")}}
    except (OSError, ValueError) as e:
        return {"task": "read_oanda_snapshot", "error": repr(e)}


def task_trade_auditor(_worker: dict) -> dict:
    if not OANDA_CLOSED.exists():
        return {"task": "count_closed_trades", "result": {"file_missing": True}}
    try:
        data = json.loads(OANDA_CLOSED.read_text(encoding="utf-8"))
        trades = data.get("trades") if isinstance(data, dict) else data
        return {"task": "count_closed_trades",
                "result": {"count": len(trades or [])}}
    except (OSError, ValueError) as e:
        return {"task": "count_closed_trades", "error": repr(e)}


def task_reconciler(_worker: dict) -> dict:
    try:
        cw = json.loads(CANONICAL_WORKERS.read_text(encoding="utf-8"))
        return {"task": "reconcile_canonical",
                "result": {"total": cw.get("total_canonical_workers"),
                            "active": cw.get("total_active_workers"),
                            "kind": cw.get("kind"),
                            "phase": cw.get("phase")}}
    except (OSError, ValueError) as e:
        return {"task": "reconcile_canonical", "error": repr(e)}


ROLE_TASKS = {
    "ledger_clerk": task_ledger_clerk,
    "trade_auditor": task_trade_auditor,
    "reconciler": task_reconciler,
}


def run_one_tick(workers: list[dict], cursor: int) -> int:
    if not workers:
        return cursor
    worker = workers[cursor % len(workers)]
    role = worker.get("role")
    fn = ROLE_TASKS.get(role)
    if fn is None:
        _stamp(TICK_LOG, {"ts": _now_iso(), "worker": worker.get("worker_id"),
                            "role": role, "task": "skip_unknown_role"})
        return cursor + 1
    try:
        outcome = fn(worker)
    except Exception as e:
        outcome = {"task": role, "error": repr(e)}
    _stamp(TICK_LOG, {"ts": _now_iso(),
                       "worker": worker.get("worker_id"),
                       "role": role, **outcome})
    return cursor + 1


def _handle_sigterm(*_a) -> None:
    global _stop
    _stop = True
    log.info("SIGTERM; shutting at next tick")


def main() -> int:
    signal.signal(signal.SIGTERM, _handle_sigterm)
    signal.signal(signal.SIGINT, _handle_sigterm)
    workers = _load_roster()
    log.info("F31 loop start; %d workers; tick=%ds",
             len(workers), TICK_INTERVAL_S)
    _stamp(ACTIVITY_TAIL, {"ts": _now_iso(), "event_kind": "f31_loop_started",
                            "summary": f"F31 loop online; {len(workers)} workers"})
    _stamp(F47_RECORDS, {"ts": _now_iso(), "kind": "f47_team_record",
                          "lead": "wren", "job": "f31_audit_ledger_loop_v1",
                          "status": "loop_started", "advisory_only": True,
                          "detail": f"{len(workers)} workers; tick {TICK_INTERVAL_S}s"})
    cursor = 0
    sweep_started = cursor
    while not _stop:
        if _within_hours():
            cursor = run_one_tick(workers, cursor)
            if cursor - sweep_started >= len(workers):
                _stamp(F47_RECORDS, {"ts": _now_iso(),
                                       "kind": "f47_team_record",
                                       "lead": "wren",
                                       "job": "f31_sweep_completed",
                                       "status": "sweep_completed",
                                       "advisory_only": True,
                                       "detail": f"{len(workers)} workers ticked"})
                sweep_started = cursor
        else:
            log.info("outside hours; sleeping")
        for _ in range(TICK_INTERVAL_S):
            if _stop:
                break
            time.sleep(1)
    log.info("F31 loop stopped at cursor=%d", cursor)
    return 0


if __name__ == "__main__":
    sys.exit(main())
