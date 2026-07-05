"""L12 — sandbox snapshot diff subcommand. Ross-directed 2026-07-05.""

from __future__ import annotations

import hashlib

from pathlib import Path

ROOT = Path("/vaults/nvme0/qsb_tower_v1")
SNAP_ROOT = ROOT / "data/sandbox_snapshots"

def diff_snapshots(owner, old_ts, new_ts):
    if not SNAP_ROOT.joinpath(owner).joinpath(old_ts).exists() or not SNAP_ROOT.joinpath(owner).joinpath(new_ts).exists():
        return {"added": [], "removed": [], "modified": [], "error": "missing snapshot"}
    def hashes(root):
        out = {}
        for p in root.rglob("*"):
            if p.is_file():
                rel = str(p.relative_to(root))
                out[rel] = hashlib.sha256(p.read_bytes()).hexdigest()
        return out
    a, b = hashes(SNAP_ROOT.joinpath(owner).joinpath(old_ts)), hashes(SNAP_ROOT.joinpath(owner).joinpath(new_ts))
    added = sorted(set(b) - set(a))
    removed = sorted(set(a) - set(b))