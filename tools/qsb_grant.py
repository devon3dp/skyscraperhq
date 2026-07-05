#!/usr/bin/env python3
"""qsb_grant.py — CLI for dual-signature grant flow.

Usage:
  qsb_grant.py observe                    # ask Kernel to scan + propose
  qsb_grant.py list                       # list all pending grants
  qsb_grant.py show <grant_id>            # show a grant + its report
  qsb_grant.py endorse <grant_id> [-n …]  # Claude signature
  qsb_grant.py authorize <grant_id> [-n …]# Ross signature
  qsb_grant.py decline <grant_id> [-n …]  # close the grant
  qsb_grant.py execute [<grant_id>]       # apply all authorized grants
                                          # or just one

Every command rehydrates state from cognitive_reward_engine_state.json
and cognitive_family_tree.json so it survives Python process restarts.
"""

from __future__ import annotations
import argparse
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from tower.cognitive_kernel.reward_engine import reward_engine
from tower.cognitive_kernel.family_tree import family_tree
from tower.cognitive_kernel.worker_genetics import worker_genetics
from tower.cognitive_kernel.worker_certification import worker_certification
from tower.cognitive_kernel.worker_pnl import worker_pnl
from tower.cognitive_kernel.population import persist as persist_population


def _rehydrate() -> None:
    family_tree().load_from_snapshot()
    reward_engine().load_from_snapshot()


def _persist_all() -> None:
    family_tree().persist()
    worker_genetics().persist()
    worker_certification().persist()
    worker_pnl().persist()
    reward_engine().persist()
    persist_population()


def cmd_observe(args) -> int:
    _rehydrate()
    re_ = reward_engine()
    new = re_.observe_and_propose()
    _persist_all()
    print(f"observed: {len(new)} new grant(s) proposed.")
    for g in new:
        print(f"  · {g.grant_id}  [{g.kind}]  candidate={g.candidate_worker_id}"
              f"  target={g.target_worker_id or '-'}")
        if g.report_path:
            print(f"      report: {g.report_path}")
    return 0


def cmd_list(args) -> int:
    _rehydrate()
    grants = reward_engine().all_grants()
    if not grants:
        print("(no grants on file)")
        return 0
    grants.sort(key=lambda g: g.proposed_ts)
    by_status = {}
    for g in grants:
        by_status[g.status] = by_status.get(g.status, 0) + 1
    print(f"{len(grants)} grant(s) total:  " +
          "  ".join(f"{k}={v}" for k, v in by_status.items()))
    print("-" * 76)
    for g in grants:
        sig_c = "✓" if g.signatures.get("claude") else " "
        sig_r = "✓" if g.signatures.get("ross") else " "
        print(f"  {g.grant_id:35s}  [{g.kind:6s}]  "
              f"sig:Claude[{sig_c}] Ross[{sig_r}]  status={g.status}")
        print(f"        candidate={g.candidate_worker_id}"
              + (f"  target={g.target_worker_id}"
                  if g.target_worker_id else ""))
    print()
    print("Tip:  qsb_grant.py show <grant_id>  to read the full report.")
    return 0


def cmd_show(args) -> int:
    _rehydrate()
    g = reward_engine().get(args.grant_id)
    if not g:
        print(f"grant {args.grant_id} not found.", file=sys.stderr)
        return 2
    print(f"grant_id:   {g.grant_id}")
    print(f"kind:       {g.kind}")
    print(f"candidate:  {g.candidate_worker_id}")
    if g.target_worker_id:
        print(f"target:     {g.target_worker_id}")
    if g.inherited_gene:
        print(f"gene:       {json.dumps(g.inherited_gene)}")
    print(f"status:     {g.status}")
    print(f"signatures: {g.signatures}")
    print(f"rationale:  {g.rationale}")
    if g.report_path and Path(g.report_path).exists():
        print()
        print("=" * 76)
        print("REPORT")
        print("=" * 76)
        print(Path(g.report_path).read_text(encoding="utf-8"))
    return 0


def cmd_endorse(args) -> int:
    _rehydrate()
    ok = reward_engine().endorse(args.grant_id, note=(args.note or ""))
    _persist_all()
    if not ok:
        print(f"endorse failed (grant not found or not endorseable).",
              file=sys.stderr)
        return 2
    g = reward_engine().get(args.grant_id)
    print(f"endorsed:   {args.grant_id}  status={g.status}  "
          f"signatures={g.signatures}")
    return 0


def cmd_authorize(args) -> int:
    _rehydrate()
    ok = reward_engine().authorize(args.grant_id, note=(args.note or ""))
    _persist_all()
    if not ok:
        print(f"authorize failed (grant not found or not authorizeable).",
              file=sys.stderr)
        return 2
    g = reward_engine().get(args.grant_id)
    print(f"authorized: {args.grant_id}  status={g.status}  "
          f"signatures={g.signatures}")
    return 0


def cmd_decline(args) -> int:
    _rehydrate()
    ok = reward_engine().decline(args.grant_id, note=(args.note or ""))
    _persist_all()
    if not ok:
        print(f"decline failed.", file=sys.stderr)
        return 2
    print(f"declined:   {args.grant_id}")
    return 0


def cmd_execute(args) -> int:
    _rehydrate()
    if args.grant_id:
        g = reward_engine().get(args.grant_id)
        if not g:
            print(f"grant {args.grant_id} not found.", file=sys.stderr)
            return 2
        if g.status != "authorized":
            print(f"grant {args.grant_id} status is '{g.status}'; "
                  "needs both signatures (status=authorized) before "
                  "execute.", file=sys.stderr)
            return 2
        executed = reward_engine().execute_authorized()
        _persist_all()
        if args.grant_id in executed:
            print(f"executed:   {args.grant_id}")
            return 0
        else:
            print(f"execute did not complete for {args.grant_id}.")
            return 2
    else:
        executed = reward_engine().execute_authorized()
        _persist_all()
        print(f"executed {len(executed)} grant(s):")
        for gid in executed:
            print(f"  · {gid}")
        return 0


def main():
    parser = argparse.ArgumentParser(
        description="QSB grant CLI (dual-signature reward flow).")
    sub = parser.add_subparsers(dest="cmd", required=True)

    sub.add_parser("observe").set_defaults(func=cmd_observe)
    sub.add_parser("list").set_defaults(func=cmd_list)

    p = sub.add_parser("show"); p.add_argument("grant_id")
    p.set_defaults(func=cmd_show)

    for name, fn in (("endorse", cmd_endorse),
                      ("authorize", cmd_authorize),
                      ("decline", cmd_decline)):
        p = sub.add_parser(name)
        p.add_argument("grant_id")
        p.add_argument("-n", "--note", default="")
        p.set_defaults(func=fn)

    p = sub.add_parser("execute")
    p.add_argument("grant_id", nargs="?", default=None)
    p.set_defaults(func=cmd_execute)

    args = parser.parse_args()
    sys.exit(args.func(args))


if __name__ == "__main__":
    main()
