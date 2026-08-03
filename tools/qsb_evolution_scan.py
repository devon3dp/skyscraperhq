#!/usr/bin/env python3
"""
qsb_evolution_scan.py — self-evolution OBSERVE->LEARN->DRAFT layer (PROPOSE-ONLY).

Purpose
-------
The tower already produces real problem signals (healer logs, the continuous
self-audit findings, the folded worker-needs queue) but several of them never
turn into a durable improvement proposal:

  * The healers (ollama-wedge, grinder) restart wedged services reactively and
    log every restart, but NOTHING reads that log to notice a CHRONIC restart
    pattern and draft a root-cause fix. A masked recurring fault stays masked.
  * The self-audit re-books the SAME finding tick after tick (status
    "requeued"/"persisted"). A finding that keeps recurring is a chronic fault
    that deserves one durable improvement proposal, not endless re-booking.
  * The worker-needs queue folds 100k+ worker reports into ~dozens of distinct
    open needs, but only the top few are delivered — the structural long tail
    (skeleton floor cards, headcount reconciles) never becomes a proposal.

This scanner reads those REAL signals and, for each genuine detected issue,
DRAFTS a structured improvement proposal and appends it to the existing bench
intake queue (data/registries/qsb_proposal_queue.jsonl) as status
`queued_unsigned` with EMPTY sigs. That is exactly where qsb_ceo_proposer.py
and the provider agents queue proposals; qsb_proposal_advance.py then sandboxes
them and the >=3-unique-class-signature + Ross gate stays entirely with humans.

HARD ENVELOPE (this tool NEVER crosses it):
  * PROPOSE-ONLY. It appends proposal rows and writes its own audit log. It
    NEVER signs (sigs stays []), NEVER applies, NEVER restarts/fixes anything,
    NEVER flips a gate, NEVER calls a provider or the network.
  * Idempotent: a finding is not re-queued while an un-applied/un-rejected
    proposal for the same finding_key already sits in the queue, or while it is
    within the cooldown window in this tool's own audit log. The periodic timer
    therefore cannot spam the human gate.
  * It refuses to target any SAFETY_DENY path (it never sets target_files to
    one; its proposals are advisory findings + recommendations, carrying no
    file_replacements, so the advancer marks them `not_runnable` and surfaces
    them for human review — honest: a human must act, not auto-code).

Audit -> data/registries/qsb_evolution_scan_audit.jsonl  (NEW, this tool's own).
"""
from __future__ import annotations

import argparse
import datetime as _dt
import hashlib
import json
import uuid
from collections import Counter, defaultdict
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
REG = ROOT / "data" / "registries"

PROPOSAL_QUEUE = REG / "qsb_proposal_queue.jsonl"          # existing bench intake (append-only)
AUDIT = REG / "qsb_evolution_scan_audit.jsonl"            # NEW: this tool's own audit log

OLLAMA_HEALER = REG / "qsb_ollama_wedge_healer.jsonl"
GRINDER_HEALER = REG / "qsb_grinder_healer.jsonl"
SELF_AUDIT_FINDINGS = REG / "qsb_self_audit_findings.jsonl"
WORKER_NEEDS = REG / "qsb_worker_needs_queue.json"

# Mirror of the bench SAFETY_DENY list — this tool must never point a proposal
# at one of these, regardless of anything.
SAFETY_PATHS = (
    "CLAUDE.md",
    "floors/floor_28_security_department/vault/",
    "tools/qsb_consult_external.py",
    "tools/qsb_oanda.py",
    "src/tower/qsb_floor41_oanda",
    ".env",
    "data/registries/qsb_proposal_autoapply_gate.json",
    "data/registries/qsb_provider_agentic_gate.json",
    "data/registries/qsb_wren_local_agentic_gate.json",
)

# Detector thresholds (conservative — only fire on genuinely chronic signal).
OLLAMA_RESTART_THRESHOLD = 6      # software restarts within the window
GRINDER_RESTART_THRESHOLD = 3
PERSISTENT_FINDING_MIN_OCCURRENCES = 3   # same finding key seen >= this many audit rows
WORKER_NEEDS_BACKLOG_THRESHOLD = 20      # distinct open needs


def _utc() -> str:
    return _dt.datetime.now(_dt.timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def _now() -> _dt.datetime:
    return _dt.datetime.now(_dt.timezone.utc)


def _parse_ts(s: str) -> _dt.datetime | None:
    if not s:
        return None
    try:
        return _dt.datetime.fromisoformat(s.replace("Z", "+00:00"))
    except Exception:
        return None


def _iter_jsonl(p: Path):
    if not p.exists():
        return
    for line in p.read_text().splitlines():
        line = line.strip().lstrip("\x00")   # tolerate boat power-loss NUL padding
        if not line:
            continue
        try:
            yield json.loads(line)
        except Exception:
            continue


def _finding_key(kind: str, subject: str) -> str:
    return f"evoscan:{kind}:{subject}"


def _is_safety(relpath: str) -> bool:
    return any(sp in (relpath or "") for sp in SAFETY_PATHS)


# ── de-dup against the live queue + this tool's own audit ────────────────────

def _open_finding_keys_in_queue() -> set[str]:
    """finding_keys that already have an un-applied, un-rejected proposal queued."""
    keys: set[str] = set()
    for row in _iter_jsonl(PROPOSAL_QUEUE):
        if row.get("source") != "evolution_scan":
            continue
        if row.get("applied") or row.get("rejected"):
            continue
        fk = row.get("finding_key")
        if fk:
            keys.add(fk)
    return keys


def _recently_queued_keys(cooldown_hours: float) -> set[str]:
    """finding_keys this tool queued within the cooldown window (audit log)."""
    cutoff = _now() - _dt.timedelta(hours=cooldown_hours)
    keys: set[str] = set()
    for row in _iter_jsonl(AUDIT):
        if row.get("event") != "queued":
            continue
        ts = _parse_ts(row.get("ts", ""))
        if ts and ts >= cutoff:
            fk = row.get("finding_key")
            if fk:
                keys.add(fk)
    return keys


# ── detectors (each returns a list of finding dicts) ─────────────────────────

def detect_chronic_healer_restarts(window_hours: float) -> list[dict]:
    findings: list[dict] = []
    cutoff = _now() - _dt.timedelta(hours=window_hours)

    def scan(path: Path, restart_actions: set[str], threshold: int,
             subject_of, label: str):
        by_subject: dict[str, list[_dt.datetime]] = defaultdict(list)
        for row in _iter_jsonl(path):
            if row.get("action") not in restart_actions:
                continue
            ts = _parse_ts(row.get("ts", ""))
            if ts and ts >= cutoff:
                by_subject[subject_of(row)].append(ts)
        for subject, stamps in by_subject.items():
            if len(stamps) < threshold:
                continue
            stamps.sort()
            findings.append({
                "kind": "chronic_healer_restarts",
                "subject": f"{label}:{subject}",
                "severity": "red",
                "title": f"Chronic auto-restarts: {label} '{subject}' "
                         f"({len(stamps)} in {int(window_hours)}h)",
                "detail": (f"The {label} healer restarted '{subject}' {len(stamps)} times in "
                           f"the last {int(window_hours)}h. Reactive restarts mask a recurring "
                           f"root-cause fault that is never fixed."),
                "evidence": (f"{len(stamps)} restart events; first={stamps[0].isoformat()} "
                             f"last={stamps[-1].isoformat()}; source={path.name}"),
                "recommendation": (
                    f"Investigate the root cause of the '{subject}' wedge rather than relying on "
                    f"the healer's reactive restart. Candidate remediations for a human to weigh: "
                    f"(a) systemd hardening (memory/concurrency limits, MemoryMax, "
                    f"OOMScoreAdjust); (b) load-shedding / request queueing upstream; "
                    f"(c) a preemptive health probe that throttles before the wedge. "
                    f"This is an operational fix — a human must choose and apply it."),
                "metric": {"restarts_in_window": len(stamps), "window_hours": window_hours},
            })

    if OLLAMA_HEALER.exists():
        scan(OLLAMA_HEALER, {"restarted_ollama_software"}, OLLAMA_RESTART_THRESHOLD,
             lambda r: r.get("box") or r.get("host") or "main_box", "ollama_wedge")
    if GRINDER_HEALER.exists():
        scan(GRINDER_HEALER, {"restarted", "restarted_grinder"}, GRINDER_RESTART_THRESHOLD,
             lambda r: r.get("box") or "grinder", "grinder")
    return findings


def detect_persistent_audit_findings(min_occurrences: int) -> list[dict]:
    """A self-audit finding key that recurs (or is explicitly requeued/persisted)
    across many audit rows is a chronic fault the self-audit only re-books; it
    deserves one durable improvement proposal."""
    seen: dict[str, list[dict]] = defaultdict(list)
    for row in _iter_jsonl(SELF_AUDIT_FINDINGS):
        key = row.get("key")
        if key:
            seen[key].append(row)

    findings: list[dict] = []
    for key, rows in seen.items():
        rows.sort(key=lambda r: r.get("ts", ""))
        occurrences = len(rows)
        persisted = any(r.get("status") in ("requeued",) or r.get("reason") == "persisted"
                        for r in rows)
        # Only escalate genuinely chronic ones: recurred enough AND still not resolved.
        if occurrences < min_occurrences and not persisted:
            continue
        latest = rows[-1]
        if latest.get("status") in ("resolved", "closed", "done"):
            continue
        sev = latest.get("severity", "amber")
        findings.append({
            "kind": "persistent_audit_finding",
            "subject": key,
            "severity": sev if sev in ("red", "amber") else "amber",
            "title": f"Persistent audit finding: {latest.get('title', key)}",
            "detail": (f"Self-audit has recorded '{key}' {occurrences} time(s) and it remains "
                       f"unresolved (latest status={latest.get('status')}, "
                       f"reason={latest.get('reason')}). Re-booking the same task each cycle is "
                       f"not fixing it."),
            "evidence": (f"occurrences={occurrences}; first={rows[0].get('ts')}; "
                         f"last={latest.get('ts')}; latest_task_id={latest.get('task_id')}; "
                         f"latest_evidence={str(latest.get('evidence'))[:200]}"),
            "recommendation": (
                f"Escalate '{key}' out of the re-book loop into a real remediation: assign an "
                f"owner, reproduce the failure, and draft a concrete fix (code or config). "
                f"A human decides the fix; this proposal just surfaces the chronic recurrence."),
            "metric": {"occurrences": occurrences, "latest_task_id": latest.get("task_id")},
        })
    return findings


def detect_worker_needs_backlog(threshold: int) -> list[dict]:
    if not WORKER_NEEDS.exists():
        return []
    try:
        data = json.loads(WORKER_NEEDS.read_text())
    except Exception:
        return []
    needs = data.get("needs", []) if isinstance(data, dict) else []
    open_needs = [n for n in needs if (n.get("status") or "open") == "open"]
    if len(open_needs) < threshold:
        return []

    cats: Counter = Counter()
    for n in open_needs:
        t = (n.get("need") or "").lower()
        if "skeleton" in t:
            cats["skeleton_floor_card"] += 1
        elif "headcount reconcile" in t:
            cats["headcount_reconcile"] += 1
        else:
            cats["other"] += 1
    top = ", ".join(f"{k}={v}" for k, v in cats.most_common())
    return [{
        "kind": "worker_needs_backlog",
        "subject": "distinct_open_needs",
        "severity": "amber",
        "title": f"Worker-needs backlog: {len(open_needs)} distinct open needs unactioned",
        "detail": (f"{len(open_needs)} distinct real worker needs are open "
                   f"(folded from {data.get('worker_reports_folded', '?')} worker reports). "
                   f"Only the top few are delivered each cycle; the structural long tail is "
                   f"never turned into work."),
        "evidence": f"open_needs={len(open_needs)} by category: {top}",
        "recommendation": (
            "Batch the structural long tail into real tasks: the skeleton-floor-card needs "
            "into a floor-card fit-out pass, and the headcount-reconcile needs into a roster "
            "audit. A human prioritises which batch to schedule."),
        "metric": {"open_needs": len(open_needs), "categories": dict(cats)},
    }]


DETECTORS = [
    ("chronic_healer_restarts", lambda a: detect_chronic_healer_restarts(a.window_hours)),
    ("persistent_audit_finding", lambda a: detect_persistent_audit_findings(a.min_occurrences)),
    ("worker_needs_backlog", lambda a: detect_worker_needs_backlog(a.needs_threshold)),
]


# ── proposal drafting + queueing ─────────────────────────────────────────────

def draft_proposal(finding: dict) -> dict:
    fk = _finding_key(finding["kind"], finding["subject"])
    pid = f"evoscan_{uuid.uuid4().hex[:10]}"
    body = (
        f"# Improvement proposal (auto-drafted from a REAL tower signal)\n\n"
        f"**Finding**: {finding['title']}\n"
        f"**Severity**: {finding['severity']}\n\n"
        f"**What the signal shows**\n{finding['detail']}\n\n"
        f"**Evidence (real, current)**\n{finding['evidence']}\n\n"
        f"**Recommended remediation (for a human to decide)**\n{finding['recommendation']}\n\n"
        f"---\n"
        f"Drafted by qsb_evolution_scan (propose-only). NOT signed, NOT applied. "
        f"Requires >=3 unique-class signatures + Ross before anything happens.\n"
    )
    return {
        "ts": _utc(),
        "proposal_id": pid,
        "source": "evolution_scan",
        "kind": "evolution_scan_finding",
        "finding_key": fk,
        "detector": finding["kind"],
        "severity": finding["severity"],
        "worklist_item": finding["title"],
        "title": finding["title"],
        "rationale": finding["detail"],
        "evidence": finding["evidence"],
        "recommendation": finding["recommendation"],
        "metric": finding.get("metric", {}),
        "patch_body": body,
        "target_files": [],            # advisory: no file target, no code to auto-apply
        "file_replacements": {},        # empty -> advancer marks not_runnable (human must act)
        "advisory_only": True,
        "human_gate": True,
        "status": "queued_unsigned",    # NEVER auto-signed / auto-applied
        "sigs": [],                     # empty — needs >=3 unique-class + Ross
    }


def _append_audit(row: dict) -> None:
    with AUDIT.open("a") as f:
        f.write(json.dumps(row) + "\n")


def run_scan(args) -> dict:
    findings: list[dict] = []
    for name, fn in DETECTORS:
        try:
            findings.extend(fn(args))
        except Exception as e:  # a broken detector must never crash the scan
            _append_audit({"ts": _utc(), "event": "detector_error",
                           "detector": name, "error": str(e)[:300]})

    # Safety: drop any finding that somehow references a SAFETY_DENY path.
    findings = [f for f in findings if not _is_safety(f.get("subject", ""))]

    open_keys = _open_finding_keys_in_queue()
    recent_keys = _recently_queued_keys(args.cooldown_hours)

    queued, skipped = [], []
    for finding in findings:
        fk = _finding_key(finding["kind"], finding["subject"])
        if fk in open_keys:
            skipped.append((fk, "already_queued_pending"))
            continue
        if fk in recent_keys:
            skipped.append((fk, "within_cooldown"))
            continue

        proposal = draft_proposal(finding)
        if args.dry_run:
            queued.append((fk, proposal["proposal_id"], "DRY_RUN"))
            continue

        with PROPOSAL_QUEUE.open("a") as f:      # append-only bench intake
            f.write(json.dumps(proposal) + "\n")
        _append_audit({
            "ts": _utc(), "event": "queued", "finding_key": fk,
            "proposal_id": proposal["proposal_id"], "detector": finding["kind"],
            "severity": finding["severity"], "title": finding["title"],
            "auto_signed": False, "auto_applied": False,
        })
        queued.append((fk, proposal["proposal_id"], finding["severity"]))
        open_keys.add(fk)   # avoid double-queue within one run

    _append_audit({
        "ts": _utc(), "event": "scan_complete", "dry_run": args.dry_run,
        "findings": len(findings), "queued": len(queued), "skipped": len(skipped),
        "note": "propose-only; nothing signed, nothing applied, no gate flipped.",
    })
    return {"findings": findings, "queued": queued, "skipped": skipped}


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--window-hours", type=float, default=24.0,
                    help="lookback window for chronic-restart detection")
    ap.add_argument("--cooldown-hours", type=float, default=24.0,
                    help="do not re-queue the same finding within this window")
    ap.add_argument("--min-occurrences", type=int, default=PERSISTENT_FINDING_MIN_OCCURRENCES)
    ap.add_argument("--needs-threshold", type=int, default=WORKER_NEEDS_BACKLOG_THRESHOLD)
    ap.add_argument("--dry-run", action="store_true",
                    help="detect + print, queue NOTHING")
    args = ap.parse_args()

    res = run_scan(args)
    tag = "DRY-RUN — nothing queued" if args.dry_run else "queued (unsigned, human-gated)"
    print(f"[evolution-scan] {len(res['findings'])} real finding(s); "
          f"{len(res['queued'])} {tag}; {len(res['skipped'])} skipped (dedup/cooldown).")
    for fk, pid, sev in res["queued"]:
        print(f"  + {sev:5} {pid}  {fk}")
    for fk, why in res["skipped"]:
        print(f"  . skip  {fk}  ({why})")
    print("[evolution-scan] SIGNED nothing, APPLIED nothing, flipped no gate. "
          "Ross + >=3 sigs remain the sole path to action.")


if __name__ == "__main__":
    main()
