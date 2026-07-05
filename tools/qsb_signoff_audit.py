"""qsb_signoff_audit.py — universal sign-off audit ledger.

Trigger: Ross 2026-06-21 — "all work from all workers ais agents and local
ais must also have there work signed off this way everyone can check whats
been signed off and whats left to do".

Team-decided design (Wren-fast + Hermes vote, signed off in F47):
  - Q1: 'open' = fewer than 2 unique signers (B)
  - Q2: output = jsonl stream of open items + summary stats (B)

Reads data/registries/qsb_f47_team_records.jsonl. For each row:
  - CLOSED      : signed_off_by has ≥ 2 unique signers
  - OPEN_WEAK   : signed_off_by exists but has < 2 unique signers
  - NO_SIGNOFF  : no signed_off_by field at all (worst — unsigned work)

Writes:
  - data/registries/qsb_signoff_audit_open.jsonl    (open items stream)
  - stdout summary table

Run:
    python3 tools/qsb_signoff_audit.py
    python3 tools/qsb_signoff_audit.py --since 2026-06-21
    python3 tools/qsb_signoff_audit.py --kind floor_staffed
    python3 tools/qsb_signoff_audit.py --closed-only        # show closed too
"""
from __future__ import annotations
import argparse, datetime, json
from collections import Counter, defaultdict
from pathlib import Path

REPO = Path("/vaults/nvme0/qsb_tower_v1")
F47 = REPO / "data/registries/qsb_f47_team_records.jsonl"
OPEN_OUT = REPO / "data/registries/qsb_signoff_audit_open.jsonl"

# These kinds are bookkeeping noise — never need sign-off.
NOISE_KINDS = {
    "heartbeat_tick", "auto_sigs_tick", "applier_tick",
    "chat_mirror_tick", "supervisor_tick", "audit_crew_tick",
    "build_forward_idle", "supervisor_escalation", "message_board_post",
    "f41_trader_daemon", "f42_trader_daemon", "f43_trader_daemon",
    "f41_position_flattener", "f42_position_flattener",
    "f43_position_flattener", "f43_flatten_event",
    "trader_pnl_aggregate_tick", "trader_pnl_aggregate",
    "f41_trader_cycle", "f42_trader_cycle", "f43_trader_cycle",
    "classroom_apply", "classroom_evaluator_tick",
    "oanda_history_pull", "oanda_history_tick", "hw_sample",
    "supervisor_tick",
}


def parse_since(s: str | None) -> str | None:
    """Return ISO date or None."""
    if not s: return None
    try:
        # accept YYYY-MM-DD or full ISO
        if len(s) == 10:
            return s + "T00:00:00Z"
        return s
    except Exception:
        return None


def classify(row: dict) -> str:
    signoffs = row.get("signed_off_by")
    if not signoffs:
        return "NO_SIGNOFF"
    if not isinstance(signoffs, list):
        return "NO_SIGNOFF"
    unique = {str(s).strip() for s in signoffs if s}
    if len(unique) >= 2:
        return "CLOSED"
    return "OPEN_WEAK"


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--since", default="2026-06-21",
                    help="ISO date or full ISO ts (default: today)")
    ap.add_argument("--kind", default=None,
                    help="Filter to a specific F47 kind")
    ap.add_argument("--closed-only", action="store_true",
                    help="Also emit closed rows (default: open only)")
    ap.add_argument("--include-noise", action="store_true",
                    help="Include trader_daemon / heartbeat ticks (default: skip)")
    args = ap.parse_args()

    since_iso = parse_since(args.since)

    by_status: Counter = Counter()
    by_kind_status: dict = defaultdict(lambda: Counter())
    by_signer: Counter = Counter()
    sample_open: list = []
    sample_closed_kinds: Counter = Counter()
    open_emitted = 0

    OPEN_OUT.parent.mkdir(parents=True, exist_ok=True)
    open_fh = OPEN_OUT.open("w")

    if not F47.exists():
        print("F47 file missing")
        return 1

    total_scanned = 0
    with F47.open() as f:
        for line in f:
            line = line.strip()
            if not line: continue
            try:
                row = json.loads(line)
            except Exception:
                continue
            ts = row.get("ts", "")
            if since_iso and ts < since_iso:
                continue
            kind = row.get("kind", "?")
            if not args.include_noise and kind in NOISE_KINDS:
                continue
            if args.kind and kind != args.kind:
                continue

            total_scanned += 1
            status = classify(row)
            by_status[status] += 1
            by_kind_status[kind][status] += 1

            signoffs = row.get("signed_off_by") or []
            if isinstance(signoffs, list):
                for s in signoffs:
                    by_signer[str(s).strip()] += 1

            if status != "CLOSED":
                # Stream open items
                open_emitted += 1
                open_fh.write(json.dumps({
                    "ts": ts,
                    "kind": kind,
                    "subject": row.get("subject"),
                    "status": status,
                    "signed_off_by": signoffs,
                    "missing_signers": max(0, 2 - len({str(s).strip() for s in signoffs if s})),
                    "proof_path": row.get("proof_path"),
                    "next_step": row.get("next_step"),
                }) + "\n")
                if len(sample_open) < 6:
                    sample_open.append((ts, kind, row.get("subject")))
            elif args.closed_only:
                open_fh.write(json.dumps({
                    "ts": ts, "kind": kind,
                    "subject": row.get("subject"),
                    "status": "CLOSED",
                    "signed_off_by": signoffs,
                }) + "\n")
                sample_closed_kinds[kind] += 1

    open_fh.close()

    print(f"\n=== sign-off audit · since {args.since} ===")
    print(f"  scanned             : {total_scanned} non-noise rows")
    print(f"  CLOSED (≥2 signers) : {by_status['CLOSED']}")
    print(f"  OPEN_WEAK (1 signer): {by_status['OPEN_WEAK']}")
    print(f"  NO_SIGNOFF          : {by_status['NO_SIGNOFF']}")
    closed_pct = 100 * by_status['CLOSED'] / max(total_scanned, 1)
    print(f"  ── closed rate: {closed_pct:.1f}% ──")

    print(f"\n=== top 8 kinds by OPEN count ===")
    rows = [(k, c["OPEN_WEAK"] + c["NO_SIGNOFF"], c["CLOSED"])
            for k, c in by_kind_status.items()]
    rows.sort(key=lambda r: -r[1])
    print(f"  {'kind':40s}  open  closed")
    for k, opn, cls in rows[:8]:
        print(f"  {k[:40]:40s}  {opn:4d}  {cls:4d}")

    print(f"\n=== top 6 signers (across closed AND open) ===")
    for s, c in by_signer.most_common(6):
        print(f"  {s[:50]:50s}  {c} stamps")

    print(f"\n=== sample OPEN items ===")
    for ts, kind, subj in sample_open:
        subj_s = (subj or "?")[:55]
        print(f"  [{ts[:19]}] {kind:30s} → {subj_s}")

    print(f"\n  open stream  → {OPEN_OUT.relative_to(REPO)}")
    print(f"  open count   → {open_emitted}")
    return 0


if __name__ == "__main__":
    import sys
    sys.exit(main())
