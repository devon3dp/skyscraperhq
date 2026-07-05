#!/usr/bin/env python3
"""qsb_while_away_report.py — what the tower did while Ross was gone.

Ross 2026-06-13: "i expect a list of whats been done while away /// i will ask
when back good luck"

Reads F47 records + code apply audits + proposal queue + activity tail since
the most recent `ross_away_start` marker (or a --since override). Renders a
clean chronological list for "when you're back, here's the play-by-play".

Usage:
    python3 tools/qsb_while_away_report.py
    python3 tools/qsb_while_away_report.py --since 2026-06-13T09:00:00Z
    python3 tools/qsb_while_away_report.py --json
    python3 tools/qsb_while_away_report.py --mark-away   # stamp start
"""
from __future__ import annotations
import json, sys, argparse
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path("/vaults/nvme0/qsb_tower_v1")
F47_REC = ROOT / "data/registries/qsb_f47_team_records.jsonl"
APPLY_AUDIT = ROOT / "data/registries/qsb_code_apply_audit.jsonl"
PROPOSALS = ROOT / "data/registries/qsb_code_proposals.jsonl"
SANDBOX_RES = ROOT / "data/registries/qsb_proposal_sandbox_results.jsonl"
ACTIVITY = ROOT / "data/registries/qsb_tower_activity_tail.jsonl"
AWAY_MARKER = ROOT / "data/registries/qsb_ross_away_marker.json"


def utcnow_dt():
    return datetime.now(timezone.utc)


def utcnow():
    return utcnow_dt().isoformat().replace("+00:00", "Z")


def parse_ts(s: str | None):
    if not s:
        return None
    try:
        return datetime.fromisoformat(s.replace("Z", "+00:00"))
    except Exception:
        return None


def mark_away(reason: str = "") -> dict:
    rec = {"ts": utcnow(), "reason": reason or "Ross stepped away"}
    AWAY_MARKER.write_text(json.dumps(rec, indent=2))
    return rec


def get_window_start(override: str | None) -> datetime:
    if override:
        return parse_ts(override)
    if AWAY_MARKER.exists():
        try:
            return parse_ts(json.loads(AWAY_MARKER.read_text()).get("ts"))
        except Exception:
            pass
    # default: last hour
    return utcnow_dt().replace(microsecond=0) - \
            (utcnow_dt() - utcnow_dt().replace(hour=0, minute=0, second=0))


def read_jsonl_since(path: Path, since: datetime) -> list[dict]:
    if not path.exists():
        return []
    out = []
    for ln in path.read_text().splitlines():
        ln = ln.strip()
        if not ln:
            continue
        try:
            r = json.loads(ln)
        except Exception:
            continue
        rts = parse_ts(r.get("ts"))
        if rts and since and rts >= since:
            out.append(r)
    return out


def summarize(since: datetime) -> dict:
    f47 = read_jsonl_since(F47_REC, since)
    applies = read_jsonl_since(APPLY_AUDIT, since)
    sandbox = read_jsonl_since(SANDBOX_RES, since)
    activity = read_jsonl_since(ACTIVITY, since)

    # counts by kind from F47 records
    by_kind = {}
    for r in f47:
        k = r.get("kind", "unknown")
        by_kind[k] = by_kind.get(k, 0) + 1

    # heartbeat ticks specifically
    ticks = [r for r in f47 if r.get("kind") == "heartbeat_tick"]

    # graphics crew progress
    gx = [r for r in f47 if r.get("kind") == "graphics_research_tick"]
    gx_total_analyzed = sum(r.get("screenshots_analyzed", 0) for r in gx)
    gx_proposals = sum(r.get("proposals_written", 0) for r in gx)

    # proposal queue last summary
    queue_summaries = [r for r in f47 if r.get("kind") == "proposal_queue_summary"]
    queue_now = queue_summaries[-1] if queue_summaries else {}

    return {
        "window_start": since.isoformat().replace("+00:00", "Z") if since else None,
        "now": utcnow(),
        "heartbeat_ticks": len(ticks),
        "graphics_screenshots_analyzed": gx_total_analyzed,
        "graphics_proposals_written": gx_proposals,
        "code_patches_applied": len(applies),
        "sandbox_runs": len(sandbox),
        "f47_records_count": len(f47),
        "f47_records_by_kind": by_kind,
        "current_queue": {
            "queue_depth": queue_now.get("queue_depth"),
            "ready_count": queue_now.get("ready_count"),
            "waiting_count": queue_now.get("waiting_count"),
        },
        "applied_patches": [
            {"ts": a.get("ts"), "proposal_id": a.get("proposal_id"),
              "files": a.get("target_files")}
            for a in applies
        ],
        "activity_events_count": len(activity),
    }


def render_text(s: dict) -> str:
    L = []
    L.append("╔══════════════════════════════════════════════════════════════════╗")
    L.append("║  WHILE YOU WERE AWAY — Wren's report                             ║")
    L.append("╚══════════════════════════════════════════════════════════════════╝")
    L.append(f"  window: {s.get('window_start')}  →  {s.get('now')}")
    L.append("")
    L.append(f"── Heartbeat ──")
    L.append(f"  ticks completed: {s.get('heartbeat_ticks')}")
    L.append("")
    L.append(f"── Graphics research crew ──")
    L.append(f"  screenshots analyzed: {s.get('graphics_screenshots_analyzed')}")
    L.append(f"  CSS/palette proposals written: {s.get('graphics_proposals_written')}")
    L.append("")
    L.append(f"── Proposal bench ──")
    q = s.get("current_queue") or {}
    L.append(f"  queue depth: {q.get('queue_depth')}")
    L.append(f"  ready (≥3 sigs): {q.get('ready_count')}")
    L.append(f"  waiting (<3 sigs): {q.get('waiting_count')}")
    L.append(f"  sandbox runs this window: {s.get('sandbox_runs')}")
    L.append(f"  code patches applied: {s.get('code_patches_applied')}")
    for a in s.get("applied_patches", []):
        L.append(f"    · {a.get('ts')} → {a.get('files')}")
    L.append("")
    L.append(f"── F47 records by kind ──")
    for k, c in sorted(s.get("f47_records_by_kind", {}).items()):
        L.append(f"  {k:36s} {c}")
    L.append("")
    L.append(f"  total tower activity events: {s.get('activity_events_count')}")
    return "\n".join(L)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--since", help="ISO ts override (e.g. 2026-06-13T09:00:00Z)")
    ap.add_argument("--mark-away", action="store_true",
                    help="stamp now as the start of the away window")
    ap.add_argument("--json", action="store_true")
    ap.add_argument("--reason", default="")
    args = ap.parse_args()

    if args.mark_away:
        rec = mark_away(args.reason)
        print(json.dumps(rec, indent=2))
        return 0

    since = get_window_start(args.since)
    summary = summarize(since)
    if args.json:
        print(json.dumps(summary, indent=2))
    else:
        print(render_text(summary))
    return 0


if __name__ == "__main__":
    sys.exit(main())
