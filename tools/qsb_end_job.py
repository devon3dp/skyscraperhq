#!/usr/bin/env python3
"""qsb_end_job.py — END gate: closes a job that was started via qsb_start_job.py.

  python3 tools/qsb_end_job.py <job_id> \\
      --result   "<one-line what changed>" \\
      --proof    "<path-to-screenshot or curl-output OR a short verifiable string>" \\
      --team-contribution "<who-on-the-team-helped and what>" \\
      [--status  completed|blocked]   default: completed

Refuses to stamp `job_completed` if any of result/proof/team-contribution
are missing. Per Ross 2026-06-16: "team contribution noted or it's not closed".
"""

from __future__ import annotations
import argparse, datetime, json, os, sys
from pathlib import Path

ROOT = Path("/vaults/nvme0/qsb_tower_v1")
REG  = ROOT / "data/registries"


def _now():
    return datetime.datetime.now(datetime.timezone.utc).isoformat(
        timespec="seconds").replace("+00:00", "Z")


def _stamp(path: Path, row: dict):
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("a") as f:
        f.write(json.dumps(row) + "\n")


def _find_start(job_id: str) -> dict | None:
    p = REG / "qsb_f47_team_records.jsonl"
    if not p.exists():
        return None
    last = None
    with p.open() as f:
        for line in f:
            line = line.strip()
            if not line:
                continue
            try:
                d = json.loads(line)
            except Exception:
                continue
            if d.get("kind") == "job_started" and d.get("job_id") == job_id:
                last = d
    return last


def main():
    p = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    p.add_argument("job_id")
    p.add_argument("--result", required=True)
    p.add_argument("--proof", required=True,
                   help="path to artifact OR short verifiable string")
    p.add_argument("--team-contribution", required=True,
                   help="who on the team helped and what they contributed")
    p.add_argument("--status", default="completed",
                   choices=["completed", "blocked"])
    args = p.parse_args()

    if not args.result.strip() or not args.proof.strip() \
       or not args.team_contribution.strip():
        print("REFUSED: result/proof/team-contribution all required", file=sys.stderr)
        sys.exit(2)

    start = _find_start(args.job_id)
    if not start:
        print(f"WARN: no job_started row found for {args.job_id} — will close anyway",
              file=sys.stderr)

    ts = _now()
    row = {
        "ts": ts, "kind": f"job_{args.status}", "operator": "claude",
        "job_id": args.job_id,
        "title": (start or {}).get("title", "(unknown title)"),
        "result": args.result[:300],
        "proof": args.proof[:300],
        "team_contribution": args.team_contribution[:300],
        "advisor_at_start": (start or {}).get("advisor_consulted", "?"),
        "team_at_start": (start or {}).get("team_dispatched", "?"),
    }
    _stamp(REG / "qsb_f47_team_records.jsonl", row)
    _stamp(REG / "qsb_tower_activity_tail.jsonl", {
        "ts": ts, "event_kind": f"job_{args.status}",
        "worker_id": "claude",
        "payload": {"job_id": args.job_id, "result": args.result[:120]}})

    # Append a session diary line so future sessions can see
    try:
        diary = ROOT / "qsb_session_diary.md"
        with diary.open("a") as f:
            f.write(f"{ts}  {args.status}: {args.result[:200]} (team: {args.team_contribution[:100]})\n")
    except Exception:
        pass

    print(json.dumps(row, indent=2))


if __name__ == "__main__":
    main()
