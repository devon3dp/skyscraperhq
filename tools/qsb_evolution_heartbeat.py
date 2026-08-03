#!/usr/bin/env python3
"""qsb_evolution_heartbeat.py — the GLUE that makes the tower evolve as a WHOLE.

2026-07-29, Ross: build the single orchestration heartbeat that wires the loop
so the tower evolves as one organism instead of a pile of disconnected tools.

The loop this coordinator nudges forward, ONE honest step per tick:

    self-audit finds problems  ->  they become proposals (queued)
        -> sandbox verifies queued proposals -> surfaced READY-FOR-SIGNATURE
        -> (the >=3 multi-sig + Ross gate stays with HUMANS; we NEVER cross it)
        -> outcomes of the tick recorded to the knowledge store so the tower LEARNS

This file is a THIN COORDINATOR. It does NOT reimplement any stage. It calls the
already-built, CLAUDE.md-authorized pieces as libraries/subprocesses and records
what actually happened:

    stage A  audit     -> tools/qsb_codebase_audit_run.main()      (writes proposals)
    stage B  advance   -> tools/qsb_proposal_advance.advance()     (sandbox -> ready-for-sig)
    stage C  learn     -> tools/qsb_knowledge.add()                (record real outcomes)

HARD GUARDRAILS (verified in code, matching the 2026-06-13 bench authorization):
  * Coordinate only. NEVER apply a patch. NEVER add a signature. NEVER flip a gate.
  * The advance stage surfaces proposals only up to `ready_for_signature=True`.
    The >=3 unique-class sig threshold + Ross signoff gate stay entirely human.
  * We READ the autoapply gate to report it; we never write it.
  * Resilient: if a sub-piece is missing/broken (agents still building it), we
    SKIP it gracefully, log the skip, and carry on — a bad stage never crashes
    the heartbeat.
  * Every tick appends REAL events (no fabrication) to
    data/registries/qsb_evolution_log.jsonl.

Run one tick:   python3 tools/qsb_evolution_heartbeat.py
Dry summary:    python3 tools/qsb_evolution_heartbeat.py --json
"""
from __future__ import annotations

import argparse
import contextlib
import importlib
import io
import json
import traceback
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
REG = ROOT / "data" / "registries"
EVO_LOG = REG / "qsb_evolution_log.jsonl"
GATE = REG / "qsb_proposal_autoapply_gate.json"
TOOLS = ROOT / "tools"

# INVARIANTS this coordinator must never violate. Kept as data so the log can
# echo them every tick — a permanent, auditable promise.
INVARIANTS = {
    "auto_applied": False,   # we never apply a patch to the live tree
    "auto_signed": False,    # we never add a signature
    "gate_flipped": False,   # we never write any execution/autoapply gate
}


def utcnow() -> str:
    return datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")


def _append_log(rec: dict) -> None:
    EVO_LOG.parent.mkdir(parents=True, exist_ok=True)
    with EVO_LOG.open("a") as f:
        f.write(json.dumps(rec) + "\n")


def _import(mod_name: str):
    """Import an orchestrated tool module by name, or return None if absent/broken.
    We add tools/ to sys.path lazily so this file has no hard import-time deps."""
    import sys
    if str(TOOLS) not in sys.path:
        sys.path.insert(0, str(TOOLS))
    try:
        return importlib.import_module(mod_name)
    except Exception:
        return None


def _gate_state() -> dict:
    """Read-only view of the autoapply gate. Never written here."""
    try:
        g = json.loads(GATE.read_text())
        return {"present": True, "enabled": bool(g.get("enabled", False))}
    except Exception:
        return {"present": False, "enabled": False}


# --------------------------------------------------------------------------- #
# STAGE A — self-audit finds problems -> queues them as proposals             #
# --------------------------------------------------------------------------- #
def stage_audit() -> dict:
    mod = _import("qsb_codebase_audit_run")
    if mod is None or not hasattr(mod, "main"):
        return {"stage": "audit", "status": "skipped",
                "reason": "qsb_codebase_audit_run not present/importable — agents may still be building it"}
    try:
        # main() picks ONE track round-robin, scans, writes <=3 proposals, prints
        # a F47 record dict. We call it as a library; its own state file advances
        # the track cursor so successive ticks cover different lenses.
        state_before = _audit_state()
        # The audit tool prints its own F47 record to stdout; capture it so the
        # coordinator's own stdout (esp. --json) stays clean machine output.
        with contextlib.redirect_stdout(io.StringIO()):
            rc = mod.main()
        state_after = _audit_state()
        wrote = max(0, state_after.get("proposals_total", 0) - state_before.get("proposals_total", 0))
        return {"stage": "audit", "status": "ok", "rc": rc,
                "track": _last_audit_track(),
                "problems_queued_this_tick": wrote,
                "proposals_total_all_time": state_after.get("proposals_total", 0)}
    except Exception as exc:
        return {"stage": "audit", "status": "error",
                "reason": str(exc)[:300], "trace": traceback.format_exc()[-600:]}


def _audit_state() -> dict:
    p = REG / "qsb_audit_crew_state.json"
    try:
        return json.loads(p.read_text())
    except Exception:
        return {}


def _last_audit_track() -> str | None:
    # The audit tool advances track_cursor AFTER picking, so the track it just
    # ran is (cursor - 1). Best-effort only; purely informational.
    try:
        mod = _import("qsb_codebase_audit_run")
        tracks = getattr(mod, "TRACKS", [])
        cur = _audit_state().get("track_cursor", 0)
        if tracks:
            return tracks[(cur - 1) % len(tracks)]
    except Exception:
        pass
    return None


# --------------------------------------------------------------------------- #
# STAGE B — sandbox queued proposals -> surface READY-FOR-SIGNATURE            #
#           (never signs, never applies)                                      #
# --------------------------------------------------------------------------- #
def stage_advance(limit: int) -> dict:
    """Advance queued proposals through the sandbox to READY-FOR-SIGNATURE.

    There are two proposal files that feed the same bench:
      * qsb_proposal_queue.jsonl   — where Wren/provider agents write; the
        existing qsb_proposal_advance.advance() consumes this one.
      * qsb_code_proposals.jsonl   — where the self-audit crew writes its
        freshly-found problems. The advancer's queue-reader does NOT read this
        file, so audit-produced problems would never reach the sandbox stage.

    To close the loop end-to-end (audit -> sandbox -> ready_for_sig) WITHOUT
    editing either individual tool, this coordinator:
      1. delegates the primary queue to qsb_proposal_advance.advance() verbatim, and
      2. drives the LEGACY audit queue through the SAME authorized sandbox
         (qsb_proposal_sandbox.run_sandbox) applying the advancer's identical
         honesty guards. It stamps only readiness — never a sig, never an apply.
    """
    mod = _import("qsb_proposal_advance")
    if mod is None or not hasattr(mod, "advance"):
        return {"stage": "advance", "status": "skipped",
                "reason": "qsb_proposal_advance not present/importable — agents may still be building it"}
    try:
        # (1) primary queue — verbatim, its own contract stamps auto_signed/
        # auto_applied=False on every log row; we surface its numbers as-is.
        summary = mod.advance(limit=limit)
        primary = {
            "processed": summary.get("processed", 0),
            "now_ready_for_sig": summary.get("green_ready_for_sig", 0),
            "red": summary.get("red", 0),
            "not_runnable": summary.get("not_runnable", 0),
            "safety_refused": summary.get("safety_refused", 0),
        }

        # (2) legacy audit queue — same sandbox, same honesty guards.
        legacy = _advance_legacy_queue(mod, limit=limit)

        return {"stage": "advance", "status": "ok",
                "processed": primary["processed"] + legacy["processed"],
                "now_ready_for_sig": primary["now_ready_for_sig"] + legacy["now_ready_for_sig"],
                "red": primary["red"] + legacy["red"],
                "not_runnable": primary["not_runnable"] + legacy["not_runnable"],
                "safety_refused": primary["safety_refused"] + legacy["safety_refused"],
                "primary_queue": primary,
                "audit_queue": legacy,
                "apply_authorized_gate": summary.get("apply_authorized", None)}
    except Exception as exc:
        return {"stage": "advance", "status": "error",
                "reason": str(exc)[:300], "trace": traceback.format_exc()[-600:]}


def _advance_legacy_queue(adv, limit: int) -> dict:
    """Sandbox un-sandboxed rows in qsb_code_proposals.jsonl (the audit crew's
    output) and stamp readiness. Mirrors qsb_proposal_advance.advance() honesty
    guards exactly. NEVER signs, NEVER applies, NEVER flips a gate."""
    sandbox = _import("qsb_proposal_sandbox")
    legacy_path = REG / "qsb_code_proposals.jsonl"
    out = {"processed": 0, "now_ready_for_sig": 0, "red": 0,
           "not_runnable": 0, "safety_refused": 0}
    if sandbox is None or not hasattr(sandbox, "run_sandbox") or not legacy_path.exists():
        return out

    try:
        rows = [json.loads(l) for l in legacy_path.read_text().splitlines() if l.strip()]
    except Exception:
        return out

    done = adv.already_sandboxed_pids()
    changed = False
    for row in rows:
        pid = adv.pid_of(row)
        if not pid:
            continue
        if row.get("applied") or row.get("rejected"):
            continue
        if row.get("sandbox_verdict") or pid in done:
            continue
        if out["processed"] >= limit:
            break

        res = sandbox.run_sandbox(pid)
        verdict = res.get("verdict", "error")
        smokes = res.get("smokes", [])
        out["processed"] += 1
        changed = True

        # HONESTY GUARD (identical to advancer): empty-smoke green verified
        # nothing -> not_runnable, never surfaced ready.
        if verdict == "green" and not smokes:
            row["sandbox_verdict"] = "not_runnable"
            row["sandbox_ts"] = res.get("ts", utcnow())
            row["status"] = "not_runnable"
            row["ready_for_signature"] = False
            row["sandbox_error"] = ("no file_replacements to run and no existing target file "
                                    "to syntax-check — not sandbox-runnable.")
            out["not_runnable"] += 1
            _stamp_advance_log(adv, pid, "not_runnable", False)
            continue

        row["sandbox_verdict"] = verdict
        row["sandbox_ts"] = res.get("ts", utcnow())
        if verdict == "green":
            row["status"] = "sandbox_green"
            row["ready_for_signature"] = True   # readiness ONLY — not a sig, not an apply
            if not row.get("file_replacements"):
                row["checked_original_only"] = True
                row["sandbox_note"] = ("green = existing target compiles; the proposed change "
                                       "itself was not run (no file_replacements).")
            else:
                row["checked_original_only"] = False
            out["now_ready_for_sig"] += 1
        elif verdict == "red":
            row["status"] = "sandbox_red"
            row["ready_for_signature"] = False
            failing = [s for s in smokes if s.get("rc", 1) != 0]
            row["sandbox_error"] = (failing[0].get("stderr_tail", "") if failing
                                    else "sandbox red (no smoke detail)")[:800]
            out["red"] += 1
        elif verdict == "safety_refused":
            row["status"] = "safety_refused"
            row["ready_for_signature"] = False
            row["sandbox_error"] = res.get("reason", "safety_refused")
            out["safety_refused"] += 1
        else:
            row["status"] = "sandbox_" + verdict
            row["ready_for_signature"] = False
            if verdict == "not_found":
                out["not_runnable"] += 1

        _stamp_advance_log(adv, pid, verdict, bool(row.get("ready_for_signature")))

    if changed:
        # atomic-ish rewrite of the legacy queue with the stamped readiness.
        tmp = legacy_path.with_suffix(".jsonl.tmp")
        tmp.write_text("".join(json.dumps(r) + "\n" for r in rows))
        tmp.replace(legacy_path)
    return out


def _stamp_advance_log(adv, pid: str, verdict: str, ready: bool) -> None:
    """Reuse the advancer's own log stamper so both queues share one audit
    trail, with the auto_signed/auto_applied=False invariants intact."""
    try:
        adv.stamp_log({"ts": utcnow(), "proposal_id": pid, "verdict": verdict,
                       "ready_for_signature": ready,
                       "auto_signed": False, "auto_applied": False,
                       "queue": "qsb_code_proposals.jsonl", "via": "evolution_heartbeat"})
    except Exception:
        pass


def _ready_for_sig_count() -> int:
    """Count proposals currently flagged ready_for_signature across both queues.
    Read-only — used to report the standing size of the human-signature backlog."""
    n = 0
    for name in ("qsb_proposal_queue.jsonl", "qsb_code_proposals.jsonl"):
        p = REG / name
        if not p.exists():
            continue
        try:
            for ln in p.read_text().splitlines():
                ln = ln.strip()
                if not ln:
                    continue
                r = json.loads(ln)
                if r.get("ready_for_signature") and not r.get("applied") and not r.get("rejected"):
                    n += 1
        except Exception:
            continue
    return n


# --------------------------------------------------------------------------- #
# STAGE C — record this tick's outcomes so the tower LEARNS                    #
# --------------------------------------------------------------------------- #
def stage_learn(audit_res: dict, advance_res: dict, ready_now: int) -> dict:
    mod = _import("qsb_knowledge")
    if mod is None or not hasattr(mod, "add"):
        return {"stage": "learn", "status": "skipped",
                "reason": "qsb_knowledge not present/importable — outcomes not persisted this tick"}
    recorded = 0
    attempted = 0
    try:
        # Only record REAL, substantive outcomes. qsb_knowledge.add() has its own
        # junk/dedup gate, so repeat no-op ticks won't bloat the store (they just
        # bump `seen`). We record the honest facts of what moved, if anything did.
        learnings: list[tuple[str, str]] = []

        wrote = audit_res.get("problems_queued_this_tick", 0)
        if audit_res.get("status") == "ok" and wrote:
            track = audit_res.get("track") or "audit"
            learnings.append((
                f"Self-audit track '{track}' surfaced {wrote} new problem(s) and queued them "
                f"as code proposals for the bench pipeline.", "outcome"))

        ready = advance_res.get("now_ready_for_sig", 0)
        red = advance_res.get("red", 0)
        if advance_res.get("status") == "ok" and (ready or red):
            learnings.append((
                f"Sandbox advanced {advance_res.get('processed', 0)} queued proposal(s): "
                f"{ready} now READY-FOR-SIGNATURE (compiled clean), {red} failed sandbox (red). "
                f"None signed, none applied — the >=3 multi-sig + Ross gate stays human.",
                "finding"))

        for text, kind in learnings:
            attempted += 1
            row = mod.add(text, source="evolution_heartbeat", kind=kind, topic="evolution_loop")
            if row is not None:
                recorded += 1

        return {"stage": "learn", "status": "ok",
                "learnings_attempted": attempted,
                "learnings_recorded_new": recorded,
                "ready_for_sig_backlog": ready_now,
                "note": "dedup/junk-gated by qsb_knowledge; recorded==0 with attempted>0 means a dup was reaffirmed"}
    except Exception as exc:
        return {"stage": "learn", "status": "error",
                "reason": str(exc)[:300], "trace": traceback.format_exc()[-600:]}


# --------------------------------------------------------------------------- #
# TICK                                                                         #
# --------------------------------------------------------------------------- #
def tick(advance_limit: int = 25) -> dict:
    started = utcnow()
    gate = _gate_state()

    audit_res = stage_audit()
    advance_res = stage_advance(limit=advance_limit)
    ready_now = _ready_for_sig_count()
    learn_res = stage_learn(audit_res, advance_res, ready_now)

    moved = (
        bool(audit_res.get("problems_queued_this_tick"))
        or bool(advance_res.get("processed"))
        or bool(learn_res.get("learnings_recorded_new"))
    )

    rec = {
        "ts": utcnow(),
        "started_ts": started,
        "event": "evolution_tick",
        "coordinator": "qsb_evolution_heartbeat",
        "loop": "audit -> queue -> sandbox -> ready_for_sig -> learn",
        "moved_forward": moved,
        "autoapply_gate": gate,
        "invariants": INVARIANTS,   # permanent promise, echoed every tick
        "stages": {
            "audit": audit_res,
            "advance": advance_res,
            "learn": learn_res,
        },
        "human_gate_remaining": {
            "ready_for_signature_backlog": ready_now,
            "still_requires": ">=3 unique-class signatures + Ross signoff (NOT done here)",
        },
    }
    _append_log(rec)
    return rec


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--limit", type=int, default=25,
                    help="max proposals to sandbox this tick (advance stage)")
    ap.add_argument("--json", action="store_true", help="print full tick record as JSON")
    args = ap.parse_args()

    rec = tick(advance_limit=args.limit)

    if args.json:
        print(json.dumps(rec, indent=2))
    else:
        s = rec["stages"]
        print(f"[evolution] tick {rec['ts']}  moved_forward={rec['moved_forward']}")
        print(f"  audit   : {s['audit'].get('status')}  "
              f"queued+{s['audit'].get('problems_queued_this_tick', 0)}  "
              f"track={s['audit'].get('track')}")
        print(f"  advance : {s['advance'].get('status')}  "
              f"processed={s['advance'].get('processed', 0)}  "
              f"->ready_for_sig={s['advance'].get('now_ready_for_sig', 0)}  "
              f"red={s['advance'].get('red', 0)}")
        print(f"  learn   : {s['learn'].get('status')}  "
              f"recorded+{s['learn'].get('learnings_recorded_new', 0)}")
        print(f"  human gate: {rec['human_gate_remaining']['ready_for_signature_backlog']} "
              f"proposal(s) awaiting >=3 sigs + Ross. "
              f"APPLIED nothing, SIGNED nothing.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
