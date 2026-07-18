"""
qsb_wren_team_dispatch.py — heartbeat step that ticks the Wren team during
work hours so they're actively contributing alongside Otto / Dex, not just
sitting idle.

Five team members get one short read-only task per tick:
  pip    (assistant)     -> 3-sentence briefing from the activity tail
  forge  (code_drafter)  -> propose a one-line improvement for a tool
  mira   (reviewer)      -> review the latest signoff queue row
  bram   (triage)        -> count failed jobs in the last 50 F47 records
  cass   (scribe)        -> append a one-line state summary to the diary

Tasks are advisory_only. Output is written verbatim to:
  data/registries/qsb_wren_team_dispatch.jsonl   (one row per worker)
  data/registries/qsb_tower_activity_tail.jsonl  (one summary row per tick)

Per-worker wall cap: 60s. Total tick cap: 5 min. Outside 08:00-17:00 the
dispatch is a no-op (the team rests with the rest of the floor).
"""

from __future__ import annotations

import json
import os
import subprocess
import sys
import time
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path("/vaults/nvme0/qsb_tower_v1")
TEAM_TOOL = ROOT / "tools/qsb_wren_team.py"
OUT_LOG = ROOT / "data/registries/qsb_wren_team_dispatch.jsonl"
ACTIVITY_TAIL = ROOT / "data/registries/qsb_tower_activity_tail.jsonl"

WALL_PER_WORKER_S = int(os.environ.get("QSB_WREN_DISPATCH_WALL_S", "60"))
WORK_HOURS = (8, 17)

TASKS = [
    ("pip",
     "Read the last 10 rows of data/registries/qsb_tower_activity_tail.jsonl"
     " using cat + tail and summarize the tower's state in 3 sentences."),
    ("forge",
     "Pick one file in tools/ that looks small (< 200 lines). Suggest a single"
     " one-line improvement (a clearer name, a missing log line, an extra"
     " stamp). Output only the file path and the suggested change."),
    ("mira",
     "Read the LAST row of data/registries/qsb_claude_signoff_queue.jsonl."
     " Either say it looks OK, or flag one concern about it."),
    ("bram",
     "Read data/registries/qsb_f47_team_records.jsonl with tail -50 and"
     " count how many rows have status containing 'fail' or 'blocked'."
     " Reply with the integer and the most recent failure's job slug."),
    ("cass",
     "Append ONE line to data/registries/qsb_session_diary.md describing the"
     " current state of the tower in under 25 words, beginning with the"
     " current UTC ts in 'YYYY-MM-DDTHH:MM:SSZ ' form."),
]


def _now_iso() -> str:
    return time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())


def _within_hours() -> bool:
    # FORCE override for Claude-initiated emergency / out-of-hours dispatches.
    # Ross 2026-06-16: "delegate" — team must work when I do, not on a clock.
    if os.environ.get("QSB_WREN_DISPATCH_FORCE") in ("1", "true", "yes"):
        return True
    h = datetime.now(timezone.utc).astimezone().hour
    return WORK_HOURS[0] <= h < WORK_HOURS[1]


def _stamp(path: Path, row: dict) -> None:
    try:
        path.parent.mkdir(parents=True, exist_ok=True)
        with path.open("a", encoding="utf-8") as f:
            f.write(json.dumps(row, separators=(",", ":")) + "\n")
    except OSError:
        pass


def run_worker(worker: str, task: str) -> dict:
    t0 = time.time()
    try:
        r = subprocess.run(
            [".venv/bin/python3", str(TEAM_TOOL),
             "--worker", worker, "--task", task],
            cwd=str(ROOT), capture_output=True, text=True,
            timeout=WALL_PER_WORKER_S,
        )
        wall = round(time.time() - t0, 2)
        reply = (r.stdout or "")[-1200:]
        return {"worker": worker, "ok": r.returncode == 0,
                "wall_s": wall, "reply_tail": reply,
                "exit_code": r.returncode}
    except subprocess.TimeoutExpired:
        return {"worker": worker, "ok": False, "wall_s": WALL_PER_WORKER_S,
                "exit_code": -1, "error": "timeout"}
    except Exception as e:
        return {"worker": worker, "ok": False, "wall_s": round(time.time()-t0, 2),
                "exit_code": -2, "error": repr(e)}


def main() -> int:
    if not _within_hours():
        _stamp(ACTIVITY_TAIL, {"ts": _now_iso(),
                                "event_kind": "wren_team_dispatch_skipped",
                                "summary": "outside work hours, team resting"})
        print("outside hours, skipping")
        return 0
    if not TEAM_TOOL.exists():
        print(f"missing {TEAM_TOOL}", file=sys.stderr)
        return 2
    started = time.time()
    results = []
    for worker, task in TASKS:
        r = run_worker(worker, task)
        results.append(r)
        _stamp(OUT_LOG, {"ts": _now_iso(), **r,
                          "task_head": task[:120]})
    total_wall = round(time.time() - started, 2)
    n_ok = sum(1 for r in results if r["ok"])
    summary = {"ts": _now_iso(),
               "event_kind": "wren_team_dispatched",
               "summary": f"Wren team tick: {n_ok}/{len(results)} ok in {total_wall}s"}
    _stamp(ACTIVITY_TAIL, summary)
    print(json.dumps({"ok": n_ok == len(results),
                       "n": len(results), "n_ok": n_ok,
                       "wall_s": total_wall,
                       "by_worker": [{"worker": r["worker"],
                                       "ok": r["ok"],
                                       "wall_s": r["wall_s"]}
                                       for r in results]}, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
