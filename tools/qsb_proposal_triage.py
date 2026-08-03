#!/usr/bin/env python3
"""
qsb_proposal_triage.py — triage the sandbox-green proposal queue so only REAL, current,
low-risk fixes reach a human signature. sandbox_green only means "py_compile passed"
(syntactically valid) — NOT that a change is wanted, correct, or safely-targeted.

This REJECTS (status -> triaged_rejected, with a reason — rows KEPT for audit) any green
proposal that is:
  · targeting a dependency/artifact path (.venv, site-packages, node_modules)
  · targeting a DATA file, not code (data/registries/*.jsonl, *.json, proof_of_work/*)
  · from wren_local_agent with an EMPTY rationale (stale/unclear prior-session noise)
  · a DUPLICATE target (keep only the newest proposal per target file)
  · an absolute-path variant of a relative-path target (dedup)
It KEEPS genuinely-good current fixes (real code file + rationale, or tonight's curated
sources) as sandbox_green, ready for the ≥3-sig + Ross gate.

NEVER signs, NEVER applies. Writes a triage log; rewrites the queue with updated statuses
after backing it up. Run: python3 tools/qsb_proposal_triage.py [--apply]
"""
import json, sys, time, shutil, os
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
QUEUE = ROOT / "data" / "registries" / "qsb_proposal_queue.jsonl"
TLOG = ROOT / "data" / "registries" / "qsb_proposal_triage.jsonl"

BAD_PATH_BITS = (".venv", "site-packages", "node_modules", "/proof_of_work/", "proof_of_work/")
DATA_SUFFIXES = (".jsonl", ".json", ".log", ".md")   # not code — don't auto-apply to these
CODE_SUFFIXES = (".py", ".js", ".css", ".html", ".sh")
CURATED_SOURCES = ("ceo_proposer", "provider_agent:codex", "p4", "codex")


def _norm_target(t):
    t = (t or "").strip()
    # normalize absolute -> repo-relative so abs/rel variants dedup together
    p = str(ROOT) + "/"
    if t.startswith(p):
        t = t[len(p):]
    return t


def classify(r):
    """Return (keep: bool, reason: str)."""
    tgt = _norm_target(r.get("target_file"))
    src = (r.get("source") or "")
    rationale = (r.get("rationale") or "").strip()
    low = tgt.lower()
    if not tgt:
        return False, "no target file"
    if any(b in low for b in BAD_PATH_BITS):
        return False, f"bad path (dependency/artifact): {tgt}"
    if low.endswith(DATA_SUFFIXES) and not low.endswith(CODE_SUFFIXES):
        return False, f"targets a data/doc file, not code: {tgt}"
    if not low.endswith(CODE_SUFFIXES):
        return False, f"non-code target: {tgt}"
    if src == "wren_local_agent" and not rationale:
        return False, "stale wren_local_agent proposal with empty rationale"
    return True, "code fix with intent — kept for signature"


def main():
    apply = "--apply" in sys.argv
    rows = [json.loads(l) for l in QUEUE.read_text(errors="ignore").splitlines() if l.strip()]
    green = [r for r in rows if r.get("status") == "sandbox_green"]

    # first pass: rule-based keep/reject
    decisions = {}
    for r in green:
        pid = r.get("proposal_id")
        keep, reason = classify(r)
        decisions[pid] = [keep, reason]

    # second pass: dedup kept-by-target (keep newest ts per normalized target)
    seen_target = {}
    for r in sorted(green, key=lambda x: x.get("ts", ""), reverse=True):
        pid = r.get("proposal_id")
        if not decisions[pid][0]:
            continue
        tgt = _norm_target(r.get("target_file"))
        if tgt in seen_target:
            decisions[pid] = [False, f"duplicate of newer proposal for {tgt} ({seen_target[tgt]})"]
        else:
            seen_target[tgt] = pid

    kept = [r for r in green if decisions[r.get("proposal_id")][0]]
    rejected = [r for r in green if not decisions[r.get("proposal_id")][0]]

    print(f"=== TRIAGE of {len(green)} sandbox-green proposals ===")
    print(f"  KEEP (real, current, unique code fixes): {len(kept)}")
    print(f"  REJECT (stale/dup/bad-path/data-file):   {len(rejected)}")
    print("\n  --- KEPT, ready for your signature ---")
    for r in sorted(kept, key=lambda x: x.get("ts", ""), reverse=True):
        print(f"    [{r.get('proposal_id','')[:22]}] {_norm_target(r.get('target_file'))}")
        rat = (r.get('rationale') or '').strip()
        if rat:
            print(f"        {rat[:110]}")
    # reason histogram for the rejects
    import collections
    rj = collections.Counter(decisions[r.get("proposal_id")][1].split(":")[0].split("(")[0].strip()
                             for r in rejected)
    print("\n  --- REJECT reasons ---")
    for reason, n in rj.most_common():
        print(f"    {n:3}  {reason}")

    if not apply:
        print("\n  (dry run — re-run with --apply to write the triage to the queue)")
        return

    # write triage log + rewrite queue with updated statuses (audit preserved: rows kept)
    ts = time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())
    shutil.copy(QUEUE, str(QUEUE) + f".bak_{ts.replace(':','').replace('-','')}_pretriage")
    with open(TLOG, "a") as tf:
        for r in rejected:
            pid = r.get("proposal_id")
            tf.write(json.dumps({"ts": ts, "proposal_id": pid, "decision": "rejected",
                                 "reason": decisions[pid][1], "target": r.get("target_file")}) + "\n")
    rej_ids = {r.get("proposal_id") for r in rejected}
    out = []
    for r in rows:
        if r.get("proposal_id") in rej_ids and r.get("status") == "sandbox_green":
            r = dict(r, status="triaged_rejected",
                     triage_reason=decisions[r.get("proposal_id")][1], triage_ts=ts)
        out.append(r)
    QUEUE.write_text("\n".join(json.dumps(r) for r in out) + "\n")
    print(f"\n  APPLIED: {len(rejected)} rejected -> triaged_rejected (audit in {TLOG.name}); "
          f"{len(kept)} remain sandbox_green ready for signature.")


if __name__ == "__main__":
    main()
