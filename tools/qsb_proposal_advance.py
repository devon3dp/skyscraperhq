#!/usr/bin/env python3
"""qsb_proposal_advance.py — advance queued proposals through the sandbox.

Wires the BACK HALF of the honest pipeline (RC-4 / P3 in
docs/CODEX_BETTER_USE_PLAN.md). Today the proposal queue is WRITE-ONLY:
335 proposals, 0 ever sandboxed/applied. This loop consumes the queue.

What it does (and ONLY this):
  1. Read every queued proposal from data/registries/qsb_proposal_queue.jsonl
     (and the legacy qsb_code_proposals.jsonl).
  2. Skip proposals that are already applied / rejected / already-sandboxed.
  3. For each un-sandboxed proposal, run tools/qsb_proposal_sandbox.run_sandbox(pid)
     — the EXISTING, CLAUDE.md-authorized (2026-06-13) sandbox machinery.
  4. Record the REAL verdict on the queue row:
        · green         → surfaced as READY-FOR-SIGNATURE (needs >=3 sigs + Ross)
        · red           → marked red with the REAL sandbox error (nothing hidden)
        · safety_refused→ marked, stays out of the active queue
  5. Summarise to F47 + stdout.

What it MUST NEVER do (guardrails, verified in code below):
  · NEVER add a signature / never touch `sigs`.
  · NEVER apply a patch to the live tree.
  · NEVER flip any gate.
  · SAFETY_DENY paths stay refused (the sandbox already refuses them; we
    just record the refusal).

The >=3 unique-class multi-sig + Ross gate stays entirely with humans/CEOs.
A green verdict here only means "runnable + syntactically clean" — it is a
PREREQUISITE for signing, not a substitute for it.

Kill switch: data/registries/qsb_proposal_autoapply_gate.json. We READ it to
respect it (never write it). Because this tool never applies anything, the
kill switch cannot be violated by us; when enabled=false we still sandbox and
surface readiness (per the gate's own note: "Surfacing-as-ready continues"),
but we clearly flag apply_authorized=false in the summary.
"""
from __future__ import annotations
import argparse
import json
import sys
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path("/vaults/nvme0/qsb_tower_v1")
REG = ROOT / "data/registries"
PROPOSAL_QUEUE = REG / "qsb_proposal_queue.jsonl"
LEGACY_QUEUE = REG / "qsb_code_proposals.jsonl"
RESULTS = REG / "qsb_proposal_sandbox_results.jsonl"
GATE = REG / "qsb_proposal_autoapply_gate.json"
F47 = REG / "qsb_f47_team_records.jsonl"
ADVANCE_LOG = REG / "qsb_proposal_advance_log.jsonl"

sys.path.insert(0, str(ROOT / "tools"))
import qsb_proposal_sandbox as sandbox  # noqa: E402


def utcnow() -> str:
    return datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")


def pid_of(row: dict) -> str | None:
    return row.get("proposal_id") or row.get("id") or row.get("ts")


def gate_apply_authorized() -> bool:
    """READ-ONLY. Whether the multi-sig auto-apply gate is enabled.

    This tool never applies, so this only affects how we LABEL readiness in
    the summary — it is not an apply switch we obey by applying."""
    if not GATE.exists():
        return False
    try:
        return bool(json.loads(GATE.read_text()).get("enabled", False))
    except Exception:
        return False


def already_sandboxed_pids() -> set[str]:
    """PIDs that already have a verdict recorded in the results ledger."""
    done: set[str] = set()
    if RESULTS.exists():
        for ln in RESULTS.read_text().splitlines():
            ln = ln.strip()
            if not ln:
                continue
            try:
                r = json.loads(ln)
            except Exception:
                continue
            if r.get("id") and r.get("verdict"):
                done.add(r["id"])
    return done


def load_queue_rows() -> list[dict]:
    rows: list[dict] = []
    if PROPOSAL_QUEUE.exists():
        for ln in PROPOSAL_QUEUE.read_text().splitlines():
            ln = ln.strip()
            if not ln:
                continue
            try:
                rows.append(json.loads(ln))
            except Exception:
                continue
    return rows


def rewrite_queue(rows: list[dict]) -> None:
    """Persist annotated rows back to the queue. We ONLY ever add/overwrite the
    advancer's own bookkeeping fields (sandbox_verdict, sandbox_ts,
    sandbox_error, ready_for_signature, status). We NEVER touch `sigs`,
    `applied`, or `rejected`."""
    tmp = PROPOSAL_QUEUE.with_suffix(".jsonl.tmp")
    with tmp.open("w") as f:
        for r in rows:
            f.write(json.dumps(r) + "\n")
    tmp.replace(PROPOSAL_QUEUE)


def stamp_log(rec: dict) -> None:
    with ADVANCE_LOG.open("a") as f:
        f.write(json.dumps(rec) + "\n")


def stamp_f47(summary: dict) -> None:
    rec = {
        "ts": utcnow(),
        "kind": "proposal_advance_summary",
        "floor": "F47",
        "operator": "background",
        "executed_by": "qsb_proposal_advance",
        "signed_off_by": ["qsb_proposal_advance", "f47_background_tick"],
        # explicit: this tool signs/applies NOTHING
        "auto_signed": 0,
        "auto_applied": 0,
        **summary,
    }
    with F47.open("a") as f:
        f.write(json.dumps(rec) + "\n")


def advance(limit: int | None = None) -> dict:
    apply_authorized = gate_apply_authorized()
    done = already_sandboxed_pids()
    rows = load_queue_rows()

    processed = 0
    greens: list[str] = []
    reds: list[dict] = []
    refused: list[str] = []
    skipped_no_content = 0

    changed = False
    for row in rows:
        pid = pid_of(row)
        if not pid:
            continue
        # skip anything already resolved by humans or already sandboxed
        if row.get("applied") or row.get("rejected"):
            continue
        if row.get("sandbox_verdict") or pid in done:
            continue
        if limit is not None and processed >= limit:
            break

        res = sandbox.run_sandbox(pid)
        verdict = res.get("verdict", "error")
        smokes = res.get("smokes", [])
        processed += 1
        changed = True

        # HONESTY GUARD: the sandbox returns verdict=green when NOTHING ran
        # (empty smokes) — e.g. a proposal with no file_replacements whose
        # target does not exist on disk. An empty-smoke "green" verified
        # nothing, so it must NOT be surfaced as ready-for-signature. We
        # downgrade it to `not_runnable` with a truthful reason. Only a green
        # that actually executed >=1 smoke can be ready-for-sig.
        if verdict == "green" and not smokes:
            row["sandbox_verdict"] = "not_runnable"
            row["sandbox_ts"] = res.get("ts", utcnow())
            row["status"] = "not_runnable"
            row["ready_for_signature"] = False
            row["sandbox_error"] = ("no file_replacements to run and no existing target file to "
                                    "syntax-check — proposal is not sandbox-runnable. Re-propose "
                                    "with file_replacements={relpath: full new file content}.")
            skipped_no_content += 1
            stamp_log({"ts": utcnow(), "proposal_id": pid, "verdict": "not_runnable",
                       "ready_for_signature": False, "auto_signed": False, "auto_applied": False})
            continue

        row["sandbox_verdict"] = verdict
        row["sandbox_ts"] = res.get("ts", utcnow())
        if verdict == "green":
            # Surfaced as READY-FOR-SIGNATURE. This is a prerequisite flag,
            # NOT a signature and NOT an apply. Humans/CEOs still add >=3 sigs.
            row["status"] = "sandbox_green"
            row["ready_for_signature"] = True
            # HONESTY: distinguish "proposed change compiles" (has runnable
            # file_replacements) from "only the existing on-disk target was
            # syntax-checked" (legacy row with no file_replacements). The
            # latter did NOT validate the proposal's actual change — reviewers
            # must know that before they sign.
            if not row.get("file_replacements"):
                row["checked_original_only"] = True
                row["sandbox_note"] = ("green = existing target file compiles; the PROPOSED change "
                                       "itself was not run (row has no file_replacements). Re-propose "
                                       "with file_replacements to validate the actual change.")
            else:
                row["checked_original_only"] = False
            greens.append(pid)
        elif verdict == "red":
            # Honest: record the real error, mark red, keep out of ready set.
            row["status"] = "sandbox_red"
            row["ready_for_signature"] = False
            failing = [s for s in res.get("smokes", []) if s.get("rc", 1) != 0]
            err = failing[0].get("stderr_tail", "") if failing else "sandbox red (no smoke detail)"
            row["sandbox_error"] = err[:800]
            reds.append({"pid": pid, "error": err[:200]})
        elif verdict == "safety_refused":
            row["status"] = "safety_refused"
            row["ready_for_signature"] = False
            row["sandbox_error"] = res.get("reason", "safety_refused")
            refused.append(pid)
        else:  # not_found / error / empty
            row["status"] = "sandbox_" + verdict
            row["ready_for_signature"] = False
            if verdict in ("not_found",):
                skipped_no_content += 1

        stamp_log({
            "ts": utcnow(),
            "proposal_id": pid,
            "verdict": verdict,
            "ready_for_signature": bool(row.get("ready_for_signature")),
            "auto_signed": False,   # invariant
            "auto_applied": False,  # invariant
        })

    if changed:
        rewrite_queue(rows)

    summary = {
        "processed": processed,
        "green_ready_for_sig": len(greens),
        "red": len(reds),
        "safety_refused": len(refused),
        "not_runnable": skipped_no_content,
        "apply_authorized": apply_authorized,  # gate state (read-only)
        "greens": greens[:15],
        "reds": reds[:15],
        "note": ("advancer sandboxes + surfaces readiness only; >=3 unique-class "
                 "sigs + Ross gate stay with humans. Nothing signed, nothing applied."),
    }
    stamp_f47(summary)
    return summary


def main():
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--limit", type=int, default=25,
                    help="max un-sandboxed proposals to advance this pass (default 25)")
    ap.add_argument("--all", action="store_true",
                    help="advance every un-sandboxed proposal in the queue")
    args = ap.parse_args()
    limit = None if args.all else args.limit
    summary = advance(limit=limit)
    print(json.dumps(summary, indent=2))
    return 0


if __name__ == "__main__":
    sys.exit(main())
