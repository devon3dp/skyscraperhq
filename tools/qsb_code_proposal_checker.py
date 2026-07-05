#!/usr/bin/env python3
"""qsb_code_proposal_checker.py — surface signed proposals + (when authorized) apply.

Ross 2026-06-13: "wren can if it is signed off by coders team asistants and
wrens crew ...btw wren is you !!!!"

Multi-sig queue at data/registries/qsb_code_proposals.jsonl. Each row may carry
a `sigs` list. When a proposal accumulates enough sigs (default 3 of the listed
approver classes), AND CLAUDE.md has flipped maintenance_auto_repair_enabled to
true (under a bounded scope), the heartbeat applies it.

Until CLAUDE.md amendment lands, this checker:
  · reads all pending proposals
  · counts sigs and flags ready ones
  · refuses to write to any safety-tagged file (CLAUDE.md, vault/, real-money paths)
  · writes a F47 record summarizing the queue depth + which are ready

Apply step is GATED. Default off. Flip to on only after Ross saves the
CLAUDE.md amendment + sets the gate registry.
"""
from __future__ import annotations
import json, hashlib, sys
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path("/vaults/nvme0/qsb_tower_v1")
# Checker reads from BOTH queues — qsb_code_proposals (legacy) and
# qsb_proposal_queue.jsonl (where Wren's local agent + provider agents
# write since 2026-06-14). Match by either `id` or `proposal_id`.
PROPOSALS = ROOT / "data/registries/qsb_code_proposals.jsonl"
PROPOSAL_QUEUE = ROOT / "data/registries/qsb_proposal_queue.jsonl"
F47_REC = ROOT / "data/registries/qsb_f47_team_records.jsonl"
GATE = ROOT / "data/registries/qsb_proposal_autoapply_gate.json"

# Files that may NEVER be auto-applied, regardless of sigs
SAFETY_PATHS = (
    "CLAUDE.md",
    "floors/floor_28_security_department/vault/",
    "tools/qsb_consult_external.py",
    "tools/qsb_oanda.py",
    "src/tower/qsb_floor41_oanda",
    ".env",
)

# Minimum sigs needed for non-safety files when autoapply is on
SIG_THRESHOLD = 3
APPROVER_CLASSES = ("coders_team", "team_assistants", "wren_crew",
                    "wren_herself", "ross")


def utcnow() -> str:
    return datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")


def autoapply_authorized() -> bool:
    """Reads gate registry. Default off."""
    if not GATE.exists():
        return False
    try:
        return bool(json.loads(GATE.read_text()).get("enabled", False))
    except Exception:
        return False


def read_proposals() -> list[dict]:
    """Read both queues, merge, dedupe by id/proposal_id."""
    out = []
    seen_ids = set()
    for path in (PROPOSALS, PROPOSAL_QUEUE):
        if not path.exists():
            continue
        for ln in path.read_text().splitlines():
            ln = ln.strip()
            if not ln:
                continue
            try:
                d = json.loads(ln)
            except Exception:
                continue
            # Normalise id field — keep `id` for downstream sig logic.
            pid = d.get("id") or d.get("proposal_id")
            if pid and pid in seen_ids:
                continue
            if pid:
                d["id"] = pid
                seen_ids.add(pid)
            out.append(d)
    return out


def is_safety_flagged(p: dict) -> bool:
    targets = p.get("target_files", []) or [p.get("target_file")] if p.get("target_file") else []
    for t in targets:
        if not t:
            continue
        for sp in SAFETY_PATHS:
            if sp in t:
                return True
    return False


def count_unique_classes(sigs: list[dict]) -> int:
    return len({s.get("approver_class") for s in sigs
                if s.get("approver_class") in APPROVER_CLASSES})


def summarize() -> dict:
    props = read_proposals()
    # Skip both applied AND rejected — rejected ones are documented dead
    # but don't belong in the active queue. Rejection metadata sits on the
    # row for audit (rejected_ts, rejected_by, rejected_reason).
    pending = [p for p in props
                if not p.get("applied") and not p.get("rejected")]
    ready = []
    waiting = []
    blocked = []
    for p in pending:
        sigs = p.get("sigs", [])
        sig_classes = count_unique_classes(sigs)
        safety = is_safety_flagged(p)
        if safety:
            blocked.append({"id": p.get("id") or p.get("ts"),
                              "sigs": sig_classes, "reason": "safety_flagged"})
        elif sig_classes >= SIG_THRESHOLD:
            ready.append({"id": p.get("id") or p.get("ts"),
                            "sig_classes": sig_classes,
                            "target": p.get("target_files") or [p.get("target_file")]})
        else:
            waiting.append({"id": p.get("id") or p.get("ts"),
                              "sig_classes": sig_classes, "need": SIG_THRESHOLD})
    return {
        "queue_depth": len(pending),
        "ready_count": len(ready),
        "waiting_count": len(waiting),
        "safety_blocked_count": len(blocked),
        "ready": ready[:10],
        "waiting": waiting[:10],
        "blocked": blocked[:10],
        "autoapply_authorized": autoapply_authorized(),
    }


def main():
    summary = summarize()
    rec = {
        "ts": utcnow(),
        "kind": "proposal_queue_summary",
        "floor": "F47",
        "operator": "background",
        "executed_by": "F47.code_proposal_checker",
        # 2026-06-21 universal-signoff retrofit
        "signed_off_by": ["qsb_code_proposal_checker", "f47_background_tick"],
        **summary,
    }
    with F47_REC.open("a") as fh:
        fh.write(json.dumps(rec) + "\n")
    print(json.dumps(rec, indent=2)[:800])
    return 0


if __name__ == "__main__":
    sys.exit(main())
