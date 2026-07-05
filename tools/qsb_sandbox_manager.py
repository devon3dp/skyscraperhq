#!/usr/bin/env python3
"""qsb_sandbox_manager.py — safe versioned snapshots + stale cleanup across
ALL Council sandboxes. Wren-designed 2026-07-04, HQ-Claude shipped clean.

Sandboxes (auto-discovered): data/*_sandbox/
  · ross_sandbox, wren_sandbox, tp_pip_sandbox, acer_cass_sandbox
  · claude_sandbox, team_sandbox, hermes_sandbox, iquest_sandbox

Snapshots land in a SIBLING dir data/sandbox_snapshots/<owner>/<ts>/ so
the sandbox itself stays clean AND snapshot walking never recurses into
snapshots. This was Wren's v1 bug — snapshots inside the sandbox path.

Staleness uses MAX content mtime (walk the files inside), not the dir's
own mtime which changes whenever anything inside touches.

Cleanup is CONSERVATIVE:
  · Only touches data/sandbox_snapshots/<owner>/<ts>/ dirs
  · Never touches the active sandbox itself
  · Default 30-day threshold for snapshot expiry

USAGE
  python3 tools/qsb_sandbox_manager.py list
  python3 tools/qsb_sandbox_manager.py snapshot                 # snapshot all
  python3 tools/qsb_sandbox_manager.py snapshot wren            # snapshot one
  python3 tools/qsb_sandbox_manager.py cleanup                  # prune stale snapshots
  python3 tools/qsb_sandbox_manager.py cleanup --days 60
"""
from __future__ import annotations
import argparse, glob, os, shutil, sys, time
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path("/vaults/nvme0/qsb_tower_v1")
DATA = ROOT / "data"
SNAP_ROOT = DATA / "sandbox_snapshots"


def _utc_stamp() -> str:
    return datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")


def discover_sandboxes() -> list[Path]:
    return sorted(Path(p) for p in glob.glob(str(DATA / "*_sandbox")) if os.path.isdir(p))


def owner_of(sandbox: Path) -> str:
    return sandbox.name.removesuffix("_sandbox")


def content_mtime(path: Path) -> float:
    """Max mtime of any file inside path. Falls back to path's own mtime."""
    best = path.stat().st_mtime
    for root, _, files in os.walk(path):
        for f in files:
            try:
                best = max(best, os.path.getmtime(os.path.join(root, f)))
            except FileNotFoundError:
                pass
    return best


def create_snapshot(sandbox: Path) -> Path:
    owner = owner_of(sandbox)
    stamp = _utc_stamp()
    dst = SNAP_ROOT / owner / stamp
    dst.mkdir(parents=True, exist_ok=True)
    files_copied = 0
    for src in sandbox.rglob("*"):
        if src.is_dir(): continue
        rel = src.relative_to(sandbox)
        target = dst / rel
        target.parent.mkdir(parents=True, exist_ok=True)
        try:
            shutil.copy2(src, target)
            files_copied += 1
        except (PermissionError, OSError):
            pass
    (dst / ".manifest").write_text(
        f"owner={owner}\nts={stamp}\nfiles={files_copied}\nsource={sandbox}\n")
    return dst


def cleanup_stale(days: int = 30) -> list[Path]:
    """Prune snapshot directories older than N days (by CONTENT mtime).
    ONLY touches SNAP_ROOT/<owner>/<ts>/ paths — safety belt."""
    if not SNAP_ROOT.exists(): return []
    cutoff = time.time() - (days * 86400)
    removed = []
    for owner_dir in SNAP_ROOT.iterdir():
        if not owner_dir.is_dir(): continue
        for snap_dir in owner_dir.iterdir():
            if not snap_dir.is_dir(): continue
            # SAFETY: refuse to remove anything not under SNAP_ROOT
            resolved = snap_dir.resolve()
            if SNAP_ROOT.resolve() not in resolved.parents:
                continue
            if content_mtime(snap_dir) < cutoff:
                shutil.rmtree(snap_dir)
                removed.append(snap_dir)
    return removed


def cmd_list():
    print(f"=== Council sandboxes at {DATA} ===")
    for s in discover_sandboxes():
        n_files = sum(1 for _ in s.rglob("*") if _.is_file())
        mtime = datetime.fromtimestamp(content_mtime(s), tz=timezone.utc)
        age = (datetime.now(timezone.utc) - mtime).total_seconds() / 86400
        print(f"  {owner_of(s):<12} · {n_files:>4} files · content_age={age:.1f}d · {s}")
    if SNAP_ROOT.exists():
        print(f"\n=== snapshots at {SNAP_ROOT} ===")
        for owner_dir in sorted(SNAP_ROOT.iterdir()):
            if owner_dir.is_dir():
                n_snaps = sum(1 for _ in owner_dir.iterdir() if _.is_dir())
                print(f"  {owner_dir.name}: {n_snaps} snapshots")


def cmd_snapshot(who: str | None):
    targets = [s for s in discover_sandboxes()
               if who is None or owner_of(s) == who]
    if not targets:
        print(f"no sandbox matched: {who}"); return
    for s in targets:
        dst = create_snapshot(s)
        print(f"  ✓ snapshot: {owner_of(s):<12} → {dst}")


def cmd_cleanup(days: int):
    removed = cleanup_stale(days)
    print(f"pruned {len(removed)} stale snapshot(s) older than {days}d")
    for p in removed:
        print(f"  · {p}")


def main():
    ap = argparse.ArgumentParser()
    sub = ap.add_subparsers(dest="cmd", required=True)
    sub.add_parser("list")
    sp = sub.add_parser("snapshot")
    sp.add_argument("who", nargs="?", default=None)
    cp = sub.add_parser("cleanup")
    cp.add_argument("--days", type=int, default=30)
    args = ap.parse_args()
    if args.cmd == "list": cmd_list()
    elif args.cmd == "snapshot": cmd_snapshot(args.who)
    elif args.cmd == "cleanup": cmd_cleanup(args.days)


if __name__ == "__main__":
    main()
