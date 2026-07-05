#!/usr/bin/env python3
"""qsb_classroom_apply.py — Phase 2 of the trader learning loop.

Reads qsb_classroom_verdicts.jsonl (where `applied=false`) and APPLIES
each verdict to qsb_worker_certification_status.json. Closes the gap
that's been blocking promotions and suspensions since the V1 evaluator
shipped advisory-only on 2026-06-17.

Per memory project_helm_sprint_2026-06-17:
  "Classroom evaluator (...) emits verdict (hold/watch/promote/suspend)
   to qsb_classroom_verdicts.jsonl. V1 is advisory — does NOT flip
   certs yet."

This is the V2 that flips.

Decision semantics (matching evaluator):
  - promote_recommended  → grant (worker, instrument) cert authority
  - suspend_recommended  → revoke (worker, instrument) cert authority
  - watch_recommended    → no cert change, log only
  - hold                 → no cert change, log only

Safety rails:
  - --promote-only        : only act on promote verdicts (default OFF)
  - --suspend-only        : only act on suspend verdicts
  - --since-ts <ISO>      : only consider verdicts after this timestamp
  - --dry-run             : print decisions, don't write
  - --skip-workers <CSV>  : never touch these worker IDs (e.g., known
                            broken-not-bad workers like the F43 ones
                            whose underlying daemon was broken)

Run modes:
  python3 tools/qsb_classroom_apply.py --dry-run --since-ts 2026-06-20T17:00:00Z
  python3 tools/qsb_classroom_apply.py --promote-only --since-ts 2026-06-20T17:00:00Z
"""

from __future__ import annotations
import argparse, datetime, json, sys
from pathlib import Path

ROOT = Path("/vaults/nvme0/qsb_tower_v1")
REG = ROOT / "data/registries"
VERDICTS = REG / "qsb_classroom_verdicts.jsonl"
CERT = REG / "qsb_worker_certification_status.json"
AUDIT = REG / "qsb_classroom_apply_audit.jsonl"
WREN_CERTS = REG / "qsb_wren_certified_traders.json"


def utc_iso() -> str:
    return datetime.datetime.now(datetime.UTC).isoformat().replace("+00:00", "Z")


def load_verdicts(since_ts: str | None):
    """Return list of unapplied verdicts, optionally filtered by ts."""
    out = []
    if not VERDICTS.exists():
        return out
    with VERDICTS.open() as f:
        for line in f:
            try:
                r = json.loads(line)
            except Exception:
                continue
            if r.get("applied"):
                continue
            if since_ts and r.get("ts", "") < since_ts:
                continue
            out.append(r)
    return out


def load_cert():
    if not CERT.exists():
        return {"ok": True, "kind": "worker_certification_status",
                "workers": {}}
    return json.loads(CERT.read_text())


def save_cert(cert: dict) -> None:
    cert["last_apply_ts"] = utc_iso()
    CERT.write_text(json.dumps(cert, indent=2))


def apply_one(cert: dict, verdict: dict, dry_run: bool) -> dict:
    """Apply a single verdict. Returns audit row."""
    worker = verdict.get("worker") or verdict.get("worker_id")
    inst = verdict.get("instrument")
    decision = verdict.get("decision")
    floor = verdict.get("floor")
    workers = cert.setdefault("workers", {})
    w = workers.setdefault(worker, {"id": worker, "floor": floor,
                                     "instruments": {}})
    insts = w.setdefault("instruments", {})
    before = insts.get(inst, {}).get("authorized")
    changed = False
    if decision == "promote_recommended":
        if not before:
            insts[inst] = {"authorized": True,
                            "granted_ts": utc_iso(),
                            "by_decision": decision,
                            "by_verdict_ts": verdict.get("ts")}
            changed = True
        action = "granted"
    elif decision == "suspend_recommended":
        if before:
            insts[inst] = {"authorized": False,
                            "revoked_ts": utc_iso(),
                            "by_decision": decision,
                            "by_verdict_ts": verdict.get("ts"),
                            "reason": verdict.get("reason")}
            changed = True
        action = "revoked"
    else:
        action = "skipped_nochange"
    return {
        "ts": utc_iso(), "kind": "classroom_apply",
        "worker": worker, "instrument": inst, "floor": floor,
        "decision": decision, "action": action,
        "before_authorized": before, "changed": changed,
        "dry_run": dry_run,
        "verdict_ts": verdict.get("ts"),
        "reason": verdict.get("reason", ""),
    }


def stamp_verdict_applied(verdict: dict) -> None:
    """Re-read the file, find the verdict by ts+worker+instrument,
    rewrite with applied=true. (jsonl append-only would be cleaner but
    the file format already has `applied:false` as a known field.)"""
    if not VERDICTS.exists():
        return
    lines = VERDICTS.read_text().splitlines()
    key = (verdict.get("ts"), verdict.get("worker"),
            verdict.get("instrument"))
    out = []
    for line in lines:
        try:
            r = json.loads(line)
        except Exception:
            out.append(line)
            continue
        if (r.get("ts"), r.get("worker"), r.get("instrument")) == key:
            r["applied"] = True
            r["applied_ts"] = utc_iso()
            out.append(json.dumps(r))
        else:
            out.append(line)
    VERDICTS.write_text("\n".join(out) + "\n")


def audit_append(row: dict) -> None:
    AUDIT.parent.mkdir(parents=True, exist_ok=True)
    with AUDIT.open("a") as f:
        f.write(json.dumps(row) + "\n")


def refresh_wren_certs_view(cert: dict) -> None:
    """Sync the lighter qsb_wren_certified_traders.json view.
    UNION with existing IDs — the file is sourced from multiple places
    (workforce expansion roster + classroom evaluator + our apply tool)
    so we must not OVERWRITE with only our subset. Drops the '<floor>'
    placeholder that creeps in from evaluator data quality issue.
    Bug fix 2026-06-20 after first run dropped 30 IDs → 3."""
    ids = set()
    for wid, w in cert.get("workers", {}).items():
        if any(i.get("authorized") for i in w.get("instruments", {}).values()):
            if wid and wid != "<floor>":
                ids.add(wid)
    # Union with existing file's IDs (preserve other sources)
    if WREN_CERTS.exists():
        try:
            prior = json.loads(WREN_CERTS.read_text())
            for pid in prior.get("certified_worker_ids", []):
                if pid and pid != "<floor>":
                    ids.add(pid)
        except Exception:
            pass
    view = {
        "ok": True, "kind": "wren_certified_traders",
        "updated_ts": utc_iso(),
        "certified_count": len(ids),
        "certified_worker_ids": sorted(ids),
        "real_money": False, "advisory_only": True,
    }
    WREN_CERTS.write_text(json.dumps(view, indent=2))


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--dry-run", action="store_true")
    ap.add_argument("--promote-only", action="store_true")
    ap.add_argument("--suspend-only", action="store_true")
    ap.add_argument("--since-ts", default="",
                    help="ISO ts; only consider verdicts after this")
    ap.add_argument("--skip-workers", default="",
                    help="CSV worker IDs to skip (broken-not-bad guard)")
    args = ap.parse_args()

    skip = set(s.strip() for s in args.skip_workers.split(",") if s.strip())
    verdicts = load_verdicts(args.since_ts or None)
    print(f"[apply] {len(verdicts)} unapplied verdicts in window", flush=True)
    if not verdicts:
        return 0

    cert = load_cert()
    counts = {"promoted": 0, "suspended": 0, "skipped": 0,
              "skipped_worker": 0}
    audit_rows = []

    for v in verdicts:
        worker = v.get("worker") or v.get("worker_id")
        if worker in skip:
            print(f"  SKIP (worker on skip list): {worker} {v.get('instrument')}")
            counts["skipped_worker"] += 1
            continue
        decision = v.get("decision")
        if args.promote_only and decision != "promote_recommended":
            counts["skipped"] += 1
            continue
        if args.suspend_only and decision != "suspend_recommended":
            counts["skipped"] += 1
            continue
        row = apply_one(cert, v, args.dry_run)
        audit_rows.append(row)
        if row["changed"]:
            if decision == "promote_recommended": counts["promoted"] += 1
            elif decision == "suspend_recommended": counts["suspended"] += 1
        else:
            counts["skipped"] += 1
        print(f"  [{row['action']:8s}] {row['worker']:25s} {row['instrument']:8s} "
              f"decision={decision:22s} {'CHANGED' if row['changed'] else 'no-op'}")

    if args.dry_run:
        print(f"\n[DRY RUN] would have written: promoted={counts['promoted']} "
              f"suspended={counts['suspended']} "
              f"skipped={counts['skipped']} "
              f"skip_worker={counts['skipped_worker']}")
        return 0

    save_cert(cert)
    for row in audit_rows:
        audit_append(row)
    for v in verdicts:
        if (v.get("worker") or v.get("worker_id")) in skip:
            continue
        if args.promote_only and v.get("decision") != "promote_recommended":
            continue
        if args.suspend_only and v.get("decision") != "suspend_recommended":
            continue
        stamp_verdict_applied(v)
    refresh_wren_certs_view(cert)

    print(f"\n[APPLIED] promoted={counts['promoted']} "
          f"suspended={counts['suspended']} "
          f"skipped={counts['skipped']} "
          f"skip_worker={counts['skipped_worker']}")
    print(f"cert file: {CERT.relative_to(ROOT)}")
    print(f"audit: {AUDIT.relative_to(ROOT)}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
