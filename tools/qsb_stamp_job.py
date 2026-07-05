#!/usr/bin/env python3
"""qsb_stamp_job.py — paired job_started / job_completed audit stamps.

Past-Wren gen-29 letter (2026-06-14) flagged that work is closed without
job_completed rows being written. Stamps go to F47 records + activity tail
so the cockpit Activity panel + later audits can see closure pairs.

  python3 tools/qsb_stamp_job.py started  "rebuild dashboard cohort"
  python3 tools/qsb_stamp_job.py completed "rebuild dashboard cohort"  -- closed
"""

from __future__ import annotations
import argparse, datetime, json, sys
from pathlib import Path

ROOT = Path("/vaults/nvme0/qsb_tower_v1")
REG  = ROOT / "data/registries"


def _now():
    return datetime.datetime.now(datetime.timezone.utc).isoformat(timespec="seconds").replace("+00:00", "Z")


def stamp(kind: str, title: str, body: str = "", operator: str = "claude"):
    ts = _now()
    f47_row = {"ts": ts, "kind": kind, "operator": operator,
               "role": "engineer", "summary": (title + ((": " + body) if body else ""))[:500]}
    with open(REG / "qsb_f47_team_records.jsonl", "a") as f:
        f.write(json.dumps(f47_row) + "\n")
    tail_row = {"ts": ts, "event_kind": kind, "worker_id": operator,
                "payload": {"title": title[:160], "body": body[:300]}}
    with open(REG / "qsb_tower_activity_tail.jsonl", "a") as f:
        f.write(json.dumps(tail_row) + "\n")
    return ts


def main():
    p = argparse.ArgumentParser()
    p.add_argument("phase", choices=["started", "completed", "blocked"])
    p.add_argument("title")
    p.add_argument("body", nargs="?", default="")
    p.add_argument("--operator", default="claude")
    a = p.parse_args()
    ts = stamp(f"job_{a.phase}", a.title, a.body, a.operator)
    print(f"stamped {a.phase} @ {ts}")


if __name__ == "__main__":
    main()
