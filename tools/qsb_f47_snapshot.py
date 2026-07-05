"""qsb_f47_snapshot.py — daily snapshot of the F47 audit master file.

Per the 2026-06-20 evening adversarial team check (Wren flagged F47 single-
file risk + Hermes confirmed): the F47 master at
`data/registries/qsb_f47_team_records.jsonl` has NO rotation. A mid-append
crash on boat-lithium power loss could partial-write the trailing row, and
the master is the only copy.

This tool takes a daily snapshot to
`data/registries/f47_snapshots/qsb_f47_<UTC date>.jsonl`. It does NOT modify
the master — other tools that read or append to it keep working unchanged.
If the master corrupts, the most recent snapshot is the recovery point.

Idempotent: a same-day run only overwrites if the master has grown.

Run:
    python3 tools/qsb_f47_snapshot.py            # snapshot if needed
    python3 tools/qsb_f47_snapshot.py --force    # snapshot regardless
"""
from __future__ import annotations
import argparse, datetime, json, shutil, sys
from pathlib import Path

REPO = Path("/vaults/nvme0/qsb_tower_v1")
MASTER = REPO / "data" / "registries" / "qsb_f47_team_records.jsonl"
SNAP_DIR = REPO / "data" / "registries" / "f47_snapshots"
F47 = MASTER


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--force", action="store_true")
    args = ap.parse_args()

    if not MASTER.exists():
        print("[f47-snapshot] master missing — nothing to snapshot")
        return 1
    SNAP_DIR.mkdir(parents=True, exist_ok=True)

    today = datetime.datetime.now(datetime.UTC).strftime("%Y-%m-%d")
    target = SNAP_DIR / f"qsb_f47_{today}.jsonl"
    master_size = MASTER.stat().st_size

    skip = (not args.force) and target.exists() and target.stat().st_size >= master_size
    if skip:
        print(f"[f47-snapshot] {target.name} already current "
              f"({target.stat().st_size} >= master {master_size}) — skip")
        return 0

    # Wren round-3 catch: VALIDATE before snapshotting so a corrupt master
    # doesn't overwrite a good prior snapshot ("backup is a copy of the bug").
    # Parse every line as JSON. The last line may be partial from a mid-write
    # crash — that's a soft-fail. Mid-file corruption is hard-fail + abort.
    parsed = 0
    last_partial = False
    bad_line_no = None
    with MASTER.open() as f:
        lines = f.readlines()
    for i, line in enumerate(lines, start=1):
        line = line.strip()
        if not line:
            continue
        try:
            json.loads(line)
            parsed += 1
        except json.JSONDecodeError:
            if i == len(lines):
                last_partial = True
            else:
                bad_line_no = i
                break
    if bad_line_no is not None:
        # Hard fail — corruption mid-file.
        ts_err = datetime.datetime.now(datetime.UTC).strftime("%Y-%m-%dT%H:%M:%SZ")
        with F47.open("a") as f:
            f.write(json.dumps({
                "ts": ts_err, "kind": "f47_snapshot_aborted", "role": "claude",
                "subject": "validation_failed",
                "detail": (f"Master file invalid at line {bad_line_no}. "
                           f"Snapshot ABORTED — refusing to overwrite the "
                           f"prior good snapshot with a corrupt master. "
                           f"Check master integrity before re-running."),
            }) + "\n")
        print(f"[f47-snapshot] ❌ ABORT — line {bad_line_no} corrupt; "
              f"prior snapshot preserved; F47 stamped f47_snapshot_aborted")
        return 2

    if last_partial:
        # Trailing partial — known boat-lithium crash mode. Take the snapshot
        # but skip the bad tail. Log a warning.
        print(f"[f47-snapshot] ⚠ trailing line is partial — snapshot skips it")
        clean_lines = [L for L in lines[:-1]] if not lines[-1].strip().endswith("}") else lines
        with target.open("w") as f:
            for L in clean_lines:
                if L.strip():
                    f.write(L if L.endswith("\n") else L + "\n")
    else:
        shutil.copy2(MASTER, target)

    print(f"[f47-snapshot] ✓ validated {parsed} rows; copied → "
          f"{target.relative_to(REPO)}")

    # Audit our own work
    ts = datetime.datetime.now(datetime.UTC).strftime("%Y-%m-%dT%H:%M:%SZ")
    with F47.open("a") as f:
        f.write(json.dumps({
            "ts": ts, "kind": "f47_snapshot", "role": "claude",
            "subject": target.name,
            "detail": (f"Daily F47 snapshot — {master_size} bytes copied to "
                       f"{target.relative_to(REPO)}. Source of recovery if "
                       f"master corrupts mid-append."),
        }) + "\n")
    print(f"[f47-snapshot] stamped F47 kind=f47_snapshot")

    # Retention — keep last 14 daily snapshots
    keep = sorted(SNAP_DIR.glob("qsb_f47_*.jsonl"))[-14:]
    removed = []
    for old in SNAP_DIR.glob("qsb_f47_*.jsonl"):
        if old not in keep:
            removed.append(old.name)
            old.unlink()
    if removed:
        print(f"[f47-snapshot] retention sweep removed {len(removed)} old: {removed}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
