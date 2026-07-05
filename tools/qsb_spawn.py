#!/usr/bin/env python3
"""qsb_spawn.py — Operator CLI for committing pending births.

Reads qsb_workforce_pending_births.json (written by the Kernel) and
either COMMITs a pending birth into the canonical workforce registry,
or DECLINEs / DEFERs it.

Commands:
  qsb_spawn.py list
  qsb_spawn.py show <child_id>
  qsb_spawn.py commit <child_id> [-n note]      # writes into workforce
  qsb_spawn.py decline <child_id> [-n note]
  qsb_spawn.py defer <child_id> [-n note]

The canonical workforce registry path is read from
QSB_WORKFORCE_REGISTRY env (defaults to data/registries/qsb_workforce_v1.json).
If the canonical file doesn't exist we refuse to commit and tell the
operator to point us at it.
"""

from __future__ import annotations
import argparse
import json
import os
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from tower.cognitive_kernel import REG


PENDING_PATH = REG / "qsb_workforce_pending_births.json"
WORKFORCE_PATH = Path(os.environ.get(
    "QSB_WORKFORCE_REGISTRY",
    str(REG / "qsb_workforce_v1.json"),
))


def _load_pending() -> dict:
    if not PENDING_PATH.exists():
        return {"pending_births": []}
    return json.loads(PENDING_PATH.read_text(encoding="utf-8"))


def _save_pending(d: dict) -> None:
    PENDING_PATH.write_text(json.dumps(d, indent=2), encoding="utf-8")


def _find_pending(child_id: str):
    d = _load_pending()
    for r in d.get("pending_births") or []:
        if r.get("child_id") == child_id:
            return d, r
    return d, None


def cmd_list(args) -> int:
    d = _load_pending()
    rows = d.get("pending_births") or []
    if not rows:
        print("(no pending births)")
        return 0
    print(f"{len(rows)} pending birth(s):")
    for r in rows:
        gene = r.get("inherited_gene") or {}
        print(f"  · {r.get('child_id')}  parent={r.get('parent_id')}  "
              f"status={r.get('spawn_status')}  "
              f"gene={gene.get('instrument', '?')}/"
              f"{gene.get('style', '?')}  "
              f"role={r.get('proposed_workforce_role')}  "
              f"floor={r.get('proposed_floor_assignment')}")
    return 0


def cmd_show(args) -> int:
    _d, r = _find_pending(args.child_id)
    if not r:
        print(f"child {args.child_id} not found.", file=sys.stderr)
        return 2
    print(json.dumps(r, indent=2))
    return 0


def _stamp_pending(child_id: str, new_status: str, note: str) -> int:
    d, r = _find_pending(child_id)
    if not r:
        print(f"child {child_id} not found.", file=sys.stderr)
        return 2
    r["spawn_status"] = new_status
    r["operator_decision_at"] = time.strftime("%Y-%m-%dT%H:%M:%S+00:00",
                                                 time.gmtime())
    if note:
        r.setdefault("notes", []).append(note)
    _save_pending(d)
    print(f"{new_status}: {child_id}")
    return 0


def cmd_commit(args) -> int:
    if not WORKFORCE_PATH.exists():
        print(f"canonical workforce registry not at {WORKFORCE_PATH}.",
              file=sys.stderr)
        print("  Set QSB_WORKFORCE_REGISTRY=... and re-run.", file=sys.stderr)
        return 3
    d, r = _find_pending(args.child_id)
    if not r:
        print(f"child {args.child_id} not found.", file=sys.stderr)
        return 2
    if r.get("spawn_status") == "operator_committed":
        print(f"{args.child_id} already committed.")
        return 0
    # Read workforce, append, write
    wf = json.loads(WORKFORCE_PATH.read_text(encoding="utf-8"))
    workers = wf.get("workers")
    if workers is None:
        # Best-effort: support both shapes
        workers = []
        wf["workers"] = workers
    if any(w.get("worker_id") == r["child_id"] for w in workers):
        print(f"{args.child_id} already present in workforce; marking committed.")
    else:
        new_worker = {
            "worker_id": r["child_id"],
            "parent_id": r.get("parent_id"),
            "grant_id": r.get("grant_id"),
            "role": r.get("proposed_workforce_role"),
            "floor": r.get("proposed_floor_assignment"),
            "status": "training",
            "born_ts": time.strftime("%Y-%m-%dT%H:%M:%S+00:00",
                                       time.gmtime()),
            "inherited_gene": r.get("inherited_gene"),
            "source": "qsb_spawn_cli",
        }
        workers.append(new_worker)
        wf["last_spawn_ts"] = new_worker["born_ts"]
        WORKFORCE_PATH.write_text(json.dumps(wf, indent=2), encoding="utf-8")
        print(f"committed to workforce: {args.child_id} → {WORKFORCE_PATH}")
    return _stamp_pending(args.child_id, "operator_committed", args.note or "")


def cmd_decline(args) -> int:
    return _stamp_pending(args.child_id, "operator_declined", args.note or "")


def cmd_defer(args) -> int:
    return _stamp_pending(args.child_id, "pending_birth", args.note or "deferred")


def main():
    parser = argparse.ArgumentParser(
        description="QSB pending-birth CLI (operator commits/declines child grants).")
    sub = parser.add_subparsers(dest="cmd", required=True)
    sub.add_parser("list").set_defaults(func=cmd_list)
    p = sub.add_parser("show"); p.add_argument("child_id")
    p.set_defaults(func=cmd_show)
    for name, fn in (("commit", cmd_commit), ("decline", cmd_decline), ("defer", cmd_defer)):
        p = sub.add_parser(name)
        p.add_argument("child_id")
        p.add_argument("-n", "--note", default="")
        p.set_defaults(func=fn)
    args = parser.parse_args()
    sys.exit(args.func(args))


if __name__ == "__main__":
    main()
