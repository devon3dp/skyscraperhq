"""
qsb_cloud_sync.py — Tailscale-tunneled rsync of data/registries between the
desktop and the cloud A1 VM. Runs on the heartbeat tick.

Direction:
  desktop -> cloud   (default; cloud is the mirror)
  cloud   -> desktop (after a power outage; merge cloud's deltas back)

JSONL is append-only, so conflict resolution is just:
  cat local.jsonl cloud.jsonl | sort -u -t'\\t' -k1 > merged.jsonl

Designed to be safe to call every 5 minutes from the heartbeat. Hard-coded
to NEVER sync the vault directory, .env files, or the proposal-autoapply
gate file — those stay on the desktop.

ENV:
  QSB_CLOUD_HOST     tailscale hostname of the cloud VM (default: qsb-tower-cloud)
  QSB_CLOUD_USER     ssh user on the cloud VM (default: ross)
  QSB_CLOUD_REMOTE_ROOT  remote path (default: /home/ross/qsb_tower_v1)
  QSB_CLOUD_SYNC_DRY     "1" to print the command without running it
"""

from __future__ import annotations

import json
import logging
import os
import subprocess
import sys
import time
from pathlib import Path

ROOT = Path("/vaults/nvme0/qsb_tower_v1")
LOCAL_REGISTRIES = ROOT / "data/registries"
LOG = ROOT / "data/registries/qsb_cloud_sync.jsonl"
ACTIVITY_TAIL = ROOT / "data/registries/qsb_tower_activity_tail.jsonl"

HOST = os.environ.get("QSB_CLOUD_HOST", "qsb-tower-cloud")
USER = os.environ.get("QSB_CLOUD_USER", "ross")
REMOTE_ROOT = os.environ.get("QSB_CLOUD_REMOTE_ROOT", "/home/ross/qsb_tower_v1")
DRY_RUN = os.environ.get("QSB_CLOUD_SYNC_DRY", "0") == "1"

EXCLUDES = [
    "--exclude=qsb_proposal_autoapply_gate.json",
    "--exclude=qsb_provider_agentic_gate.json",
    "--exclude=qsb_wren_local_agentic_gate.json",
    "--exclude=.env.*",
    "--exclude=*.lock",
    "--exclude=__pycache__",
]

logging.basicConfig(level=logging.INFO,
                    format="[%(asctime)s] %(levelname)s qsb.cloud_sync - %(message)s")
log = logging.getLogger("qsb.cloud_sync")


def _now_iso() -> str:
    return time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())


def _stamp(path: Path, row: dict) -> None:
    try:
        path.parent.mkdir(parents=True, exist_ok=True)
        with path.open("a", encoding="utf-8") as f:
            f.write(json.dumps(row, separators=(",", ":")) + "\n")
    except OSError as e:
        log.error("stamp %s failed: %s", path.name, e)


def _host_reachable() -> bool:
    try:
        r = subprocess.run(["tailscale", "ping", "--c", "1", "--timeout=2s", HOST],
                           capture_output=True, text=True, timeout=5)
        return r.returncode == 0
    except (FileNotFoundError, subprocess.TimeoutExpired):
        return False


def push() -> dict:
    """desktop → cloud"""
    if not _host_reachable():
        return {"ok": False, "reason": "host_unreachable", "host": HOST}
    cmd = ["rsync", "-az", "--delete-after"] + EXCLUDES + [
        f"{LOCAL_REGISTRIES.as_posix()}/",
        f"{USER}@{HOST}:{REMOTE_ROOT}/data/registries/",
    ]
    if DRY_RUN:
        return {"ok": True, "dry_run": True, "cmd": cmd}
    t0 = time.time()
    try:
        r = subprocess.run(cmd, capture_output=True, text=True, timeout=120)
        wall = round(time.time() - t0, 2)
        return {"ok": r.returncode == 0, "exit_code": r.returncode,
                "wall_s": wall,
                "stderr_tail": (r.stderr or "")[-400:]}
    except subprocess.TimeoutExpired:
        return {"ok": False, "reason": "rsync_timeout"}


def pull() -> dict:
    """cloud → desktop (post-outage merge)"""
    if not _host_reachable():
        return {"ok": False, "reason": "host_unreachable", "host": HOST}
    cmd = ["rsync", "-az"] + EXCLUDES + [
        f"{USER}@{HOST}:{REMOTE_ROOT}/data/registries/",
        f"{LOCAL_REGISTRIES.as_posix()}/",
    ]
    if DRY_RUN:
        return {"ok": True, "dry_run": True, "cmd": cmd}
    t0 = time.time()
    try:
        r = subprocess.run(cmd, capture_output=True, text=True, timeout=120)
        wall = round(time.time() - t0, 2)
        return {"ok": r.returncode == 0, "exit_code": r.returncode,
                "wall_s": wall,
                "stderr_tail": (r.stderr or "")[-400:]}
    except subprocess.TimeoutExpired:
        return {"ok": False, "reason": "rsync_timeout"}


def main() -> int:
    import argparse
    p = argparse.ArgumentParser()
    p.add_argument("--direction", choices=["push", "pull", "status"],
                   default="push")
    args = p.parse_args()
    if args.direction == "status":
        reachable = _host_reachable()
        print(json.dumps({"host": HOST, "user": USER,
                            "remote_root": REMOTE_ROOT,
                            "reachable": reachable,
                            "dry_run_env": DRY_RUN}, indent=2))
        return 0 if reachable else 2
    fn = push if args.direction == "push" else pull
    result = fn()
    row = {"ts": _now_iso(), "direction": args.direction, **result}
    _stamp(LOG, row)
    _stamp(ACTIVITY_TAIL, {"ts": row["ts"],
                            "event_kind": f"cloud_sync_{args.direction}",
                            "summary": f"ok={result['ok']} "
                                        f"reason={result.get('reason','-')}"})
    print(json.dumps(result, indent=2))
    return 0 if result["ok"] else 2


if __name__ == "__main__":
    raise SystemExit(main())
