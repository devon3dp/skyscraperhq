"""
qsb_f38_sandbox_ops_loop.py — Floor 38 (Sandbox Operations) day-shift ticker.

30 workers (10 sandbox_runner / 10 rl_experimenter / 10 result_analyst).
Read-only, advisory_only.

  sandbox_runner   -> reads openclaw_sandbox_latest.json + counts tick events
  rl_experimenter  -> reads qsb_f47_quantum_experiments.jsonl, counts recent
  result_analyst   -> summarises the last hour of sandbox events
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
ROSTER = ROOT / "data/registries/qsb_f38_roster.json"
TICK_LOG = ROOT / "data/registries/qsb_f38_tick_log.jsonl"
F47_RECORDS = ROOT / "data/registries/qsb_f47_team_records.jsonl"
ACTIVITY_TAIL = ROOT / "data/registries/qsb_tower_activity_tail.jsonl"

OPENCLAW_LATEST = ROOT / "data/registries/openclaw_sandbox_latest.json"
QUANTUM_EXP = ROOT / "data/registries/qsb_f47_quantum_experiments.jsonl"
OPENCLAW_LOG = ROOT / "data/registries/openclaw_sandbox_layer.jsonl"

TICK_INTERVAL_S = int(os.environ.get("QSB_F38_TICK_S", "60"))
WORK_HOURS = (int(os.environ.get("QSB_F38_OPEN_H", "8")),
              int(os.environ.get("QSB_F38_CLOSE_H", "17")))

logging.basicConfig(level=logging.INFO,
                    format="[%(asctime)s] %(levelname)s qsb.f38 - %(message)s")
log = logging.getLogger("qsb.f38")
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


def _count_jsonl_recent(path: Path, window_s: int) -> int:
    if not path.exists():
        return 0
    cutoff = time.time() - window_s
    n = 0
    try:
        with path.open("r", encoding="utf-8") as f:
            for ln in f:
                ln = ln.strip()
                if not ln:
                    continue
                try:
                    r = json.loads(ln)
                except ValueError:
                    continue
                ts = r.get("ts", "")
                try:
                    t = time.mktime(time.strptime(ts, "%Y-%m-%dT%H:%M:%SZ"))
                except ValueError:
                    continue
                if t >= cutoff:
                    n += 1
    except OSError:
        return -1
    return n


def task_sandbox_runner(_worker: dict) -> dict:
    if not OPENCLAW_LATEST.exists():
        return {"task": "read_sandbox_latest", "result": {"file_missing": True}}
    try:
        d = json.loads(OPENCLAW_LATEST.read_text(encoding="utf-8"))
        return {"task": "read_sandbox_latest",
                "result": {"ts": d.get("ts"),
                            "tick_count": d.get("tick_count"),
                            "recommendations": len(d.get("recommendations", []) or [])}}
    except (OSError, ValueError) as e:
        return {"task": "read_sandbox_latest", "error": repr(e)}


def task_rl_experimenter(_worker: dict) -> dict:
    return {"task": "count_recent_experiments",
            "result": {"last_hour": _count_jsonl_recent(QUANTUM_EXP, 3600),
                        "exists": QUANTUM_EXP.exists()}}


def task_result_analyst(_worker: dict) -> dict:
    return {"task": "scan_sandbox_layer",
            "result": {"last_hour": _count_jsonl_recent(OPENCLAW_LOG, 3600),
                        "exists": OPENCLAW_LOG.exists()}}


ROLE_TASKS = {
    "sandbox_runner": task_sandbox_runner,
    "rl_experimenter": task_rl_experimenter,
    "result_analyst": task_result_analyst,
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
    log.info("F38 loop start; %d workers; tick=%ds",
             len(workers), TICK_INTERVAL_S)
    _stamp(ACTIVITY_TAIL, {"ts": _now_iso(), "event_kind": "f38_loop_started",
                            "summary": f"F38 loop online; {len(workers)} workers"})
    _stamp(F47_RECORDS, {"ts": _now_iso(), "kind": "f47_team_record",
                          "lead": "wren", "job": "f38_sandbox_ops_loop_v1",
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
                                       "job": "f38_sweep_completed",
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
    log.info("F38 loop stopped at cursor=%d", cursor)
    return 0


if __name__ == "__main__":
    sys.exit(main())
