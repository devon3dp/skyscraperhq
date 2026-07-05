#!/usr/bin/env python3
"""qsb_proposal_sign.py — add a signature to a code-change proposal.

Sig classes (each can sign at most once per proposal):
  coders_team, team_assistants, wren_crew, wren_herself, ross

Threshold for auto-apply: 3 unique classes, AND sandbox verdict = green,
AND CLAUDE.md amendment has authorized the gate.
"""
from __future__ import annotations
import json, sys, argparse, hashlib
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path("/vaults/nvme0/qsb_tower_v1")
PROPOSALS = ROOT / "data/registries/qsb_code_proposals.jsonl"

VALID_CLASSES = {"coders_team", "team_assistants", "wren_crew",
                  "wren_herself", "ross"}


def utcnow() -> str:
    return datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")


def rewrite_proposal(pid: str, mutator) -> dict | None:
    if not PROPOSALS.exists():
        return None
    rows = []
    target_row = None
    for ln in PROPOSALS.read_text().splitlines():
        ln = ln.strip()
        if not ln:
            continue
        try:
            r = json.loads(ln)
        except Exception:
            rows.append(ln)
            continue
        if r.get("id") == pid or r.get("ts") == pid:
            r = mutator(r)
            target_row = r
            rows.append(json.dumps(r))
        else:
            rows.append(json.dumps(r))
    PROPOSALS.write_text("\n".join(rows) + "\n")
    return target_row


def sign(pid: str, who: str, klass: str, note: str = "") -> dict | None:
    if klass not in VALID_CLASSES:
        raise ValueError(f"unknown approver_class: {klass} (valid: {VALID_CLASSES})")
    def add_sig(p):
        sigs = p.setdefault("sigs", [])
        # one class per proposal — replace if same class signs again
        sigs = [s for s in sigs if s.get("approver_class") != klass]
        sigs.append({
            "ts": utcnow(),
            "approver_class": klass,
            "approver_id": who,
            "note": note,
        })
        p["sigs"] = sigs
        return p
    return rewrite_proposal(pid, add_sig)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("proposal_id")
    ap.add_argument("--who", required=True, help="approver id (worker_id or 'ross')")
    ap.add_argument("--klass", required=True, choices=sorted(VALID_CLASSES))
    ap.add_argument("--note", default="")
    args = ap.parse_args()
    r = sign(args.proposal_id, args.who, args.klass, args.note)
    if r is None:
        print(json.dumps({"ok": False, "error": "proposal not found"}, indent=2))
        return 1
    classes_now = sorted({s["approver_class"] for s in r.get("sigs", [])})
    print(json.dumps({"ok": True, "id": args.proposal_id,
                       "sigs_classes_now": classes_now,
                       "sig_count": len(classes_now)}, indent=2))
    return 0


if __name__ == "__main__":
    sys.exit(main())
