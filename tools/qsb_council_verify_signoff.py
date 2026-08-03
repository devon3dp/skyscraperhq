#!/usr/bin/env python3
"""qsb_council_verify_signoff.py — the Wren + Bill self-sign-off step.

Closes the tower's evolution loop WITHOUT a per-proposal human gate:

    green proposal  ->  Wren's mind verifies  ->  Bill's mind verifies
                    ->  real sigs on the proposal  ->  the EXISTING applier applies it.

This engine ONLY verifies + signs. It NEVER writes live code. Applying is done by
the trusted tools/qsb_proposal_applier.py (its queue pass), which still enforces
every gate: >=3 unique-class sigs, sandbox green, gate enabled, safety-clear.

Sig math (Ross 2026-08-03 decision):
  · Wren APPROVE  -> TWO classes: wren_herself + wren_crew
  · Bill APPROVE  -> ONE class:  coders_team
  Both must genuinely approve -> 3 unique classes -> the applier applies.
  Either alone is <3 -> nothing applies. A REJECT from either -> no sig from them.

The two verifiers are REAL minds, not a rubber-stamp:
  · Wren : tools/qsb_wren_local_agent.run_session (her qwen2.5:14b via Ollama)
  · Bill : leadership relay round-trip to his Mac responder
           (tools/qsb_ceo_task_worker.bill_ask / bill_probe)
If a mind is unreachable or returns nothing, that mind does NOT sign and the
outcome is logged honestly — a real sign-off requires a real answer.

Kill switch: honours the auto-apply gate. gate.enabled=false -> engine does nothing.

Usage:
  python3 tools/qsb_council_verify_signoff.py --once --limit 1     # proof: one proposal
  python3 tools/qsb_council_verify_signoff.py --limit 5            # bounded normal run
  python3 tools/qsb_council_verify_signoff.py --proposal <id>      # target a specific one
  python3 tools/qsb_council_verify_signoff.py --dry-run --limit 1  # verify, DON'T sign
"""
from __future__ import annotations
import argparse, json, os, re, sys, time
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path("/vaults/nvme0/qsb_tower_v1")
sys.path.insert(0, str(ROOT / "tools"))

import qsb_proposal_applier as A          # noqa: E402  reuse gates: is_safety_flagged/count_sigs/gate_on/sandbox_green_for

REG = ROOT / "data/registries"
PROPOSAL_QUEUE = REG / "qsb_proposal_queue.jsonl"
GATE = REG / "qsb_proposal_autoapply_gate.json"
VERIFY_AUDIT = REG / "qsb_verify_signoff_audit.jsonl"
F47_REC = REG / "qsb_f47_team_records.jsonl"

# ── autonomous TASK sign-off (--tasks mode) ────────────────────────────────
# Ross 2026-08-03: task sign-off moves off Ross onto the council. For each task
# waiting on a human accept, Wren and Bill each INDEPENDENTLY verify the work;
# only when BOTH approve does the task advance (peer_signoff → done) with no
# Ross gate. Same kill switch (gate.enabled) and same "unreachable mind never
# signs" honesty as the proposal path above.
TASK_SNAP = REG / "qsb_council_tasks_snapshot.json"
TASK_SIGNOFF_AUDIT = REG / "qsb_council_task_signoff_audit.jsonl"
TASK_WAIT_STATES = ("awaiting_peer_signoff", "awaiting_verification")

SIG_THRESHOLD = 3


def utcnow() -> str:
    return datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")


# ── gate / kill switch ──────────────────────────────────────────────────
def gate_enabled() -> bool:
    try:
        return bool(json.loads(GATE.read_text()).get("enabled", False))
    except Exception:
        return False


# ── queue io ────────────────────────────────────────────────────────────
def read_queue_latest() -> dict[str, dict]:
    out: dict[str, dict] = {}
    if not PROPOSAL_QUEUE.exists():
        return out
    for ln in PROPOSAL_QUEUE.read_text().splitlines():
        ln = ln.strip()
        if not ln:
            continue
        try:
            r = json.loads(ln)
        except Exception:
            continue
        pid = r.get("proposal_id") or r.get("id")
        if pid:
            out[pid] = r
    return out


def append_queue_row(row: dict) -> None:
    with PROPOSAL_QUEUE.open("a") as f:
        f.write(json.dumps(row) + "\n")


def targets_of(p: dict) -> list[str]:
    return p.get("target_files") or ([p.get("target_file")] if p.get("target_file") else [])


def is_candidate(p: dict) -> bool:
    """Green + not applied + safety-clear + under-threshold sigs + has content."""
    if p.get("status") != "sandbox_green":
        return False
    if p.get("applied"):
        return False
    if A.is_safety_flagged(p):
        return False
    if A.count_sigs(p) >= SIG_THRESHOLD:
        return False
    if not (p.get("patch_body") or p.get("file_replacements")):
        return False
    if not targets_of(p):
        return False
    return True


# ── verification prompt ─────────────────────────────────────────────────
def build_prompt(p: dict) -> str:
    pid = p.get("proposal_id") or p.get("id")
    targets = targets_of(p)
    body = p.get("patch_body")
    if not body and isinstance(p.get("file_replacements"), dict):
        body = "\n\n".join(f"# {k}\n{v}" for k, v in p["file_replacements"].items())
    body = (body or "")[:3500]
    worklist = p.get("worklist_item") or p.get("rationale") or "(none given)"
    src = p.get("tests_source") or "(n/a)"
    return (
        "You are a strict code-change VERIFIER for the QSB Tower evolution loop. "
        "A proposal has passed the sandbox (py_compile green). If you and one other "
        "verifier both approve, this change is APPLIED to the live repo automatically "
        "with no further human check. So be careful.\n\n"
        f"PROPOSAL ID : {pid}\n"
        f"TARGET FILE : {', '.join(targets)}  (a NEW file — additive)\n"
        f"SANDBOX     : green (py_compile passed)\n"
        f"INTENT      : {worklist}\n"
        f"SOURCE UNDER TEST: {src}\n\n"
        "----- FULL PROPOSED FILE CONTENT -----\n"
        f"{body}\n"
        "----- END -----\n\n"
        "Approve ONLY if the change is clearly correct, additive/safe, and you "
        "understand it. If uncertain, unclear, large, or risky -> REJECT.\n"
        "Answer with EXACTLY the single word APPROVE or REJECT on the first line, "
        "then ONE line explaining why."
    )


def parse_verdict(text: str) -> tuple[str, str]:
    """Return ('APPROVE'|'REJECT'|'UNCLEAR', one-line-reason). Fail-safe: anything
    that is not an unambiguous APPROVE is treated as not-approved."""
    if not text or not text.strip():
        return "UNCLEAR", "(empty answer)"
    t = text.strip()
    up = t.upper()
    # explicit reject wins
    reject = bool(re.search(r"\bREJECT\b|\bDISAPPROVE\b|\bDO NOT APPROVE\b|\bNOT APPROVE", up))
    approve = bool(re.search(r"\bAPPROVE\b", up)) and not re.search(r"\bNOT\s+APPROVE\b|\bDON'?T\s+APPROVE\b", up)
    # reason = first non-empty line that isn't just the verdict word
    reason = ""
    for ln in t.splitlines():
        s = ln.strip().strip("-*. ")
        if not s:
            continue
        if s.upper() in ("APPROVE", "REJECT"):
            continue
        reason = s[:300]
        break
    if not reason:
        reason = t.replace("\n", " ")[:300]
    if reject and not approve:
        return "REJECT", reason
    if approve and not reject:
        return "APPROVE", reason
    if approve and reject:
        return "UNCLEAR", "both APPROVE and REJECT present -> treated as not-approved: " + reason
    return "UNCLEAR", reason


# ── the two real minds ──────────────────────────────────────────────────
def ask_wren(prompt: str) -> tuple[str, str, str]:
    """Return (verdict, reason, raw). Uses Wren's real local model."""
    try:
        import qsb_wren_local_agent as W
    except Exception as e:
        return "UNREACHABLE", f"import qsb_wren_local_agent failed: {e}", ""
    system = (
        "You are Wren, reviewing a proposed code change as a strict verifier. "
        "Do not call tools unless you truly need to read the target module. "
        "Give your verdict directly. Answer APPROVE or REJECT then one line why."
    )
    try:
        out = W.run_session(prompt, system=system,
                            session_id=f"verify_{int(time.time())}")
    except SystemExit as e:
        # load_gate() raises SystemExit if Wren's gate is off
        return "UNREACHABLE", f"wren gate/agent unavailable: {e}", ""
    except Exception as e:
        return "UNREACHABLE", f"wren run_session error: {e}", ""
    raw = (out or {}).get("final_text", "") or ""
    v, reason = parse_verdict(raw)
    return v, reason, raw


def ask_bill(prompt: str) -> tuple[str, str, str]:
    """Return (verdict, reason, raw). Round-trips Bill's real Mac responder."""
    try:
        import qsb_ceo_task_worker as C
    except Exception as e:
        return "UNREACHABLE", f"import qsb_ceo_task_worker failed: {e}", ""
    # confirm his responder is actually live before we wait on a long answer
    try:
        if not C.bill_probe(timeout_wait=45):
            return "UNREACHABLE", "bill_probe failed (responder not live)", ""
    except Exception as e:
        return "UNREACHABLE", f"bill_probe error: {e}", ""
    try:
        reply, why = C.bill_ask(prompt)
    except Exception as e:
        return "UNREACHABLE", f"bill_ask error: {e}", ""
    if not reply:
        return "UNREACHABLE", f"bill no reply: {why}", ""
    v, reason = parse_verdict(reply)
    return v, reason, reply


# ── sig application ─────────────────────────────────────────────────────
def sig_row(klass: str, approver: str, note: str) -> dict:
    return {"approver_class": klass, "approver": approver, "approver_id": approver,
            "ts": utcnow(), "note": note[:300]}


def verify_one(p: dict, *, dry_run: bool) -> dict:
    pid = p.get("proposal_id") or p.get("id")
    # hard double-check: never sign a safety-flagged proposal
    if A.is_safety_flagged(p):
        return {"proposal_id": pid, "skipped": "safety_flagged"}

    prompt = build_prompt(p)
    wv, wr, w_raw = ask_wren(prompt)
    bv, br, b_raw = ask_bill(prompt)

    existing = list(p.get("sigs", []))
    added: list[dict] = []
    if wv == "APPROVE":
        # Wren = two classes
        added.append(sig_row("wren_herself", "wren", wr))
        added.append(sig_row("wren_crew", "wren", wr))
    if bv == "APPROVE":
        added.append(sig_row("coders_team", "bill", br))

    new_sigs = existing
    if added and not dry_run:
        # de-dupe by class (one per class), keep newest
        by_class = {s.get("approver_class"): s for s in existing}
        for s in added:
            by_class[s["approver_class"]] = s
        new_sigs = list(by_class.values())
        row = dict(p)
        row["sigs"] = new_sigs
        row["verify_signoff_ts"] = utcnow()
        append_queue_row(row)

    sigs_after = sorted({s.get("approver_class") for s in (new_sigs if not dry_run else existing + added)})
    audit = {
        "ts": utcnow(),
        "proposal_id": pid,
        "target_files": targets_of(p),
        "wren_verdict": wv, "wren_reason": wr,
        "bill_verdict": bv, "bill_reason": br,
        "sigs_after": sigs_after,
        "sig_count_after": len(sigs_after),
        "ready_to_apply": len(sigs_after) >= SIG_THRESHOLD,
        "dry_run": bool(dry_run),
    }
    with VERIFY_AUDIT.open("a") as f:
        f.write(json.dumps(audit) + "\n")
    # F47 trace
    try:
        with F47_REC.open("a") as f:
            f.write(json.dumps({
                "ts": utcnow(), "kind": "council_verify_signoff",
                "operator": "verify_signoff_engine", "proposal_id": pid,
                "summary": f"wren={wv} bill={bv} sigs={sigs_after} ready={audit['ready_to_apply']}",
            }) + "\n")
    except Exception:
        pass
    audit["wren_raw"] = w_raw[:600]
    audit["bill_raw"] = b_raw[:600]
    return audit


# ══════════════════════════════════════════════════════════════════════════
#  AUTONOMOUS TASK SIGN-OFF  (--tasks)
#  Wren + Bill independently verify a task's result → BOTH approve → the task
#  advances (peer_signoff → done) with NO Ross gate. Neither mind's verdict is
#  ever fabricated: an unreachable/UNCLEAR mind simply does not approve, and the
#  task stays exactly where it is, logged honestly.
# ══════════════════════════════════════════════════════════════════════════
def load_task_snapshot() -> dict:
    try:
        return json.loads(TASK_SNAP.read_text(errors="ignore"))
    except Exception:
        return {"tasks": []}


def task_candidates(limit: int) -> list[dict]:
    snap = load_task_snapshot()
    out = [t for t in snap.get("tasks", [])
           if (t.get("state") or "").lower() in TASK_WAIT_STATES]
    # highest-rework first — the ones that have been churning longest get eyes first
    out.sort(key=lambda t: -(t.get("rework_rounds") or 0))
    return out[:limit]


def build_task_prompt(t: dict) -> str:
    tid = t.get("id")
    title = t.get("title") or tid
    desc = (t.get("description") or "").strip()[:1800]
    owner = t.get("owner") or t.get("assignee") or "?"
    sandbox_by = t.get("sandbox_passed_by") or "(none)"
    notes = t.get("notes") or []
    note_lines = "\n".join(f"  - {n.get('by','?')}: {str(n.get('text',''))[:200]}"
                           for n in notes[-6:]) or "  (no notes)"
    return (
        "You are a strict TASK VERIFIER for the QSB Task Council. A worker has "
        "finished a task and it is waiting for sign-off. If you AND one other "
        "council mind both approve, the task is marked complete automatically with "
        "NO further human check. Approve ONLY if the described work is genuinely "
        "complete, correct and evidenced. If the result is thin, unproven, unclear, "
        "or still needs work -> REJECT so it goes back to the pool.\n\n"
        f"TASK ID     : {tid}\n"
        f"TITLE       : {title}\n"
        f"OWNER       : {owner}\n"
        f"STATE       : {t.get('state')}\n"
        f"SANDBOX BY  : {sandbox_by}\n"
        f"REWORK RNDS : {t.get('rework_rounds', 0)}\n\n"
        "----- TASK DESCRIPTION / RESULT -----\n"
        f"{desc or '(no description recorded)'}\n"
        "----- RECENT NOTES -----\n"
        f"{note_lines}\n"
        "----- END -----\n\n"
        "Answer with EXACTLY the single word APPROVE or REJECT on the first line, "
        "then ONE line explaining why."
    )


def signoff_task_one(t: dict, *, dry_run: bool) -> dict:
    tid = t.get("id")
    prompt = build_task_prompt(t)
    wv, wr, w_raw = ask_wren(prompt)
    bv, br, b_raw = ask_bill(prompt)
    both_approve = (wv == "APPROVE" and bv == "APPROVE")

    signed = False
    signed_actor = None
    advanced_to = t.get("state")
    err = ""
    if both_approve and not dry_run:
        try:
            import qsb_council_tasks as C
        except Exception as e:                                       # pragma: no cover
            err = f"import qsb_council_tasks failed: {e}"
        else:
            comment = f"Autonomous council sign-off — Wren: {wr[:120]} | Bill: {br[:120]}"
            # peer_signoff must come from a CEO who is NOT the task's taker; the
            # reducer enforces that, so we try each approver and take the first
            # the reducer accepts (Bill preferred as signer, Wren is often owner).
            for a in ("bill", "wren"):
                try:
                    r = C.peer_signoff(tid, a, "approve", comment=comment)
                except Exception as e:
                    err = f"peer_signoff error: {e}"
                    r = {"ok": False}
                if r.get("ok"):
                    signed, signed_actor = True, a
                    break
                err = r.get("error", err)
            if signed:
                try:
                    # complete it — this is the autonomous replacement for the old
                    # Ross 'accept'. sandbox_passed_by + approve = verified complete.
                    C.note(tid, "council_autonomous",
                           f"COUNCIL AUTONOMOUS SIGN-OFF: Wren APPROVE + Bill APPROVE. "
                           f"signed_by={signed_actor}. No Ross gate.")
                    C.update(tid, signed_actor, state="done")
                    advanced_to = "done"
                except Exception as e:
                    err = f"advance-to-done error: {e}"

    audit = {
        "ts": utcnow(),
        "task_id": tid,
        "title": (t.get("title") or tid)[:120],
        "owner": t.get("owner") or t.get("assignee"),
        "state_before": t.get("state"),
        "wren_verdict": wv, "wren_reason": wr,
        "bill_verdict": bv, "bill_reason": br,
        "both_approve": both_approve,
        "signed": signed, "signed_by": signed_actor,
        "advanced_to": advanced_to,
        "dry_run": bool(dry_run),
        "error": err,
    }
    with TASK_SIGNOFF_AUDIT.open("a") as f:
        f.write(json.dumps(audit) + "\n")
    try:
        with F47_REC.open("a") as f:
            f.write(json.dumps({
                "ts": utcnow(), "kind": "council_task_signoff",
                "operator": "task_signoff_engine", "task_id": tid,
                "summary": f"wren={wv} bill={bv} both={both_approve} "
                           f"signed={signed}->{advanced_to}",
            }) + "\n")
    except Exception:
        pass
    audit["wren_raw"] = (w_raw or "")[:600]
    audit["bill_raw"] = (b_raw or "")[:600]
    return audit


def run_tasks(limit: int, dry_run: bool) -> int:
    picks = task_candidates(limit)
    results = [signoff_task_one(t, dry_run=dry_run) for t in picks]
    print(json.dumps({"engine": "council_task_signoff",
                      "candidates": len(picks),
                      "processed": len(results),
                      "dry_run": bool(dry_run),
                      "advanced": sum(1 for r in results if r.get("signed")),
                      "results": results}, indent=2))
    return 0


# ── driver ──────────────────────────────────────────────────────────────
def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--once", action="store_true",
                    help="process at most --limit (default 1) then exit")
    ap.add_argument("--limit", type=int, default=None,
                    help="max proposals to process this run")
    ap.add_argument("--proposal", default=None, help="target a specific proposal_id")
    ap.add_argument("--tasks", action="store_true",
                    help="autonomous TASK sign-off: Wren+Bill verify awaiting tasks "
                         "and advance them (peer_signoff→done) with no Ross gate")
    ap.add_argument("--dry-run", action="store_true",
                    help="verify + log but do NOT write sigs / advance tasks")
    a = ap.parse_args()

    if not gate_enabled():
        print(json.dumps({"engine": "council_verify_signoff",
                          "status": "halted", "reason": "kill switch: gate.enabled=false"}))
        return 0

    limit = a.limit if a.limit is not None else (1 if a.once else 3)

    if a.tasks:                       # autonomous TASK sign-off path (Wren + Bill)
        return run_tasks(limit, a.dry_run)

    queue = read_queue_latest()

    if a.proposal:
        picks = [queue[a.proposal]] if a.proposal in queue and is_candidate(queue[a.proposal]) else []
        if not picks and a.proposal in queue:
            print(json.dumps({"error": f"{a.proposal} is not a signable candidate",
                              "detail": {"status": queue[a.proposal].get("status"),
                                         "applied": queue[a.proposal].get("applied"),
                                         "safety": A.is_safety_flagged(queue[a.proposal]),
                                         "sigs": A.count_sigs(queue[a.proposal])}}, indent=2))
            return 1
    else:
        cands = [p for p in queue.values() if is_candidate(p)]
        # stable-ish order by ts so runs are deterministic
        cands.sort(key=lambda r: r.get("ts", ""))
        picks = cands[:limit]

    results = []
    for p in picks[:limit]:
        results.append(verify_one(p, dry_run=a.dry_run))

    print(json.dumps({"engine": "council_verify_signoff",
                      "processed": len(results),
                      "dry_run": bool(a.dry_run),
                      "results": results}, indent=2))
    return 0


if __name__ == "__main__":
    sys.exit(main())
