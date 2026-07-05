"""
qsb_f25_worker_recruitment_loop.py — Floor 25 (Worker Recruitment) day-shift
ticker. Read-only, advisory_only.

36 workers (12 interviewer / 12 spawn_clerk / 12 onboarding_guide) take turns
once every 60s during working hours. Each tick reads a registry and writes
a short audit row. No external calls, no money, no provider invocations.

Audit: data/registries/qsb_f25_tick_log.jsonl
F47:   data/registries/qsb_f47_team_records.jsonl (one row per full sweep)
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
ROSTER = ROOT / "data/registries/qsb_f25_roster.json"
TICK_LOG = ROOT / "data/registries/qsb_f25_tick_log.jsonl"
F47_RECORDS = ROOT / "data/registries/qsb_f47_team_records.jsonl"
ACTIVITY_TAIL = ROOT / "data/registries/qsb_tower_activity_tail.jsonl"
CERT_LEDGER = ROOT / "data/registries/qsb_certification_ledger.jsonl"
CANONICAL_WORKERS = ROOT / "data/registries/qsb_canonical_workers.json"

TICK_INTERVAL_S = int(os.environ.get("QSB_F25_TICK_S", "60"))
WORK_HOURS = (int(os.environ.get("QSB_F25_OPEN_H", "8")),
              int(os.environ.get("QSB_F25_CLOSE_H", "17")))

logging.basicConfig(level=logging.INFO,
                    format="[%(asctime)s] %(levelname)s qsb.f25 - %(message)s")
log = logging.getLogger("qsb.f25")

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


def task_interviewer(worker: dict) -> dict:
    """Read the canonical roster, count employed-by-role."""
    try:
        cw = json.loads(CANONICAL_WORKERS.read_text(encoding="utf-8"))
        total = cw.get("total_canonical_workers", 0)
        active = cw.get("total_active_workers", 0)
        return {"task": "audit_canonical_roster",
                "result": {"total": total, "active": active,
                            "utilization_pct": round(100 * active / total, 2)
                            if total else None}}
    except (OSError, ValueError) as e:
        return {"task": "audit_canonical_roster", "error": repr(e)}


def task_spawn_clerk(worker: dict) -> dict:
    """Count certified workers from the ledger."""
    if not CERT_LEDGER.exists():
        return {"task": "count_certified", "result": {"certified": 0,
                                                       "ledger_missing": True}}
    try:
        n = 0
        with CERT_LEDGER.open("r", encoding="utf-8") as f:
            for ln in f:
                ln = ln.strip()
                if not ln:
                    continue
                try:
                    row = json.loads(ln)
                except ValueError:
                    continue
                if row.get("status") in ("certified", "qualified", "passed"):
                    n += 1
        return {"task": "count_certified", "result": {"certified": n}}
    except OSError as e:
        return {"task": "count_certified", "error": repr(e)}


def task_onboarding_guide(worker: dict) -> dict:
    """Scan today's tick log for recent intake events on this floor."""
    if not TICK_LOG.exists():
        return {"task": "scan_recent_intake", "result": {"recent_ticks": 0}}
    cutoff = time.time() - 3600
    n = 0
    try:
        with TICK_LOG.open("r", encoding="utf-8") as f:
            for ln in f:
                ln = ln.strip()
                if not ln:
                    continue
                try:
                    row = json.loads(ln)
                except ValueError:
                    continue
                ts = row.get("ts", "")
                try:
                    t = time.mktime(time.strptime(ts, "%Y-%m-%dT%H:%M:%SZ"))
                except ValueError:
                    continue
                if t >= cutoff:
                    n += 1
        return {"task": "scan_recent_intake",
                "result": {"ticks_last_hour": n}}
    except OSError as e:
        return {"task": "scan_recent_intake", "error": repr(e)}


ROLE_TASKS = {
    "interviewer": task_interviewer,
    "spawn_clerk": task_spawn_clerk,
    "onboarding_guide": task_onboarding_guide,
}


def run_one_tick(workers: list[dict], cursor: int) -> int:
    if not workers:
        log.warning("empty roster, nothing to tick")
        return cursor
    worker = workers[cursor % len(workers)]
    role = worker.get("role")
    fn = ROLE_TASKS.get(role)
    if fn is None:
        log.warning("no task for role %r, skipping", role)
        _stamp(TICK_LOG, {"ts": _now_iso(), "worker": worker.get("worker_id"),
                            "role": role, "task": "skip_unknown_role",
                            "result": None})
        return cursor + 1
    try:
        outcome = fn(worker)
    except Exception as e:
        log.error("task %s failed: %r", role, e)
        outcome = {"task": role, "error": repr(e)}
    _stamp(TICK_LOG, {"ts": _now_iso(),
                       "worker": worker.get("worker_id"),
                       "role": role,
                       **outcome})
    return cursor + 1


def _handle_sigterm(*_a) -> None:
    global _stop
    _stop = True
    log.info("SIGTERM received; shutting down at next tick")


def main() -> int:
    signal.signal(signal.SIGTERM, _handle_sigterm)
    signal.signal(signal.SIGINT, _handle_sigterm)
    workers = _load_roster()
    role_counts = Counter(w.get("role") for w in workers)
    log.info("F25 loop start; %d workers; roles=%s; tick=%ds; hours=%d-%d",
             len(workers), dict(role_counts), TICK_INTERVAL_S,
             WORK_HOURS[0], WORK_HOURS[1])
    _stamp(ACTIVITY_TAIL, {"ts": _now_iso(), "event_kind": "f25_loop_started",
                            "summary": f"F25 loop online; {len(workers)} workers"})
    _stamp(F47_RECORDS, {"ts": _now_iso(), "kind": "f47_team_record",
                          "lead": "wren", "job": "f25_worker_loop_v1",
                          "status": "loop_started",
                          "advisory_only": True,
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
                                       "job": "f25_sweep_completed",
                                       "status": "sweep_completed",
                                       "advisory_only": True,
                                       "detail": f"{len(workers)} workers ticked"})
                sweep_started = cursor
        else:
            log.info("outside hours (%d-%d); sleeping",
                     WORK_HOURS[0], WORK_HOURS[1])
        for _ in range(TICK_INTERVAL_S):
            if _stop:
                break
            time.sleep(1)
    log.info("F25 loop stopped at cursor=%d", cursor)
    _stamp(ACTIVITY_TAIL, {"ts": _now_iso(),
                            "event_kind": "f25_loop_stopped",
                            "summary": f"F25 loop stopped; cursor={cursor}"})
    return 0


if __name__ == "__main__":
    sys.exit(main())
