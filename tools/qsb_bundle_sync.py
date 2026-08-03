#!/usr/bin/env python3
"""qsb_bundle_sync.py — tower-side choreographer for the offline-first cycle.

Delivers a work bundle to a worker box, and (when the box is reachable again)
collects its results and applies them to the tower. This is the SYNC transport
layer. It is deliberately the ONLY thing that needs HQ<->box connectivity —
the box's grind (deploy/qsb_box_grind_agent.py) runs against local Ollama and
needs no HQ at all.

Boxes:  thinkpad = budds@192.168.1.91 , acer = budds@192.168.1.41
Transport: ssh/scp as budds. If the box is unreachable, deliver/collect fail
gracefully and the box keeps grinding whatever it already has locally.

  deploy  --box  : scp the grind agent onto the box (one-time / on update)
  push    --box --bundle <path> : deliver a bundle -> box:%USERPROFILE%\\.qsb\\bundle.json
  drive   --box  : ssh the box to run `grind` then `rollup` (used in test; in prod
                   the box runs grind on its own timer, offline-safe)
  collect --box  : scp the box's results_bundle.json back to the tower + apply it
  reachable --box: 0/1 whether HQ can currently reach the box
"""
from __future__ import annotations
import argparse, json, subprocess, sys, tempfile, os
from pathlib import Path

ROOT = Path("/vaults/nvme0/qsb_tower_v1")
REG = ROOT / "data/registries"
INBOX = REG / "work_results_inbox"
AGENT = ROOT / "deploy/qsb_box_grind_agent.py"

BOXES = {
    "thinkpad": {"host": "192.168.1.91", "user": "budds"},
    "acer": {"host": "192.168.1.41", "user": "budds"},
}
# Windows box paths (budds home)
REMOTE_DIR = r"C:\Users\budds\.qsb"
# python.exe path differs per box (ThinkPad=Program Files\Python311,
# Acer=AppData\...\Python312) so we resolve it live per box.
REMOTE_PY_FALLBACK = r"C:\Program Files\Python311\python.exe"
# The box authorizes the hqskyscraper key; pin it + IdentitiesOnly so this works
# under systemd (no ssh-agent) as well as interactively.
SSH_KEY = "/home/ross/.ssh/skyscraper_ed25519"
SSH_OPTS = ["-o", "BatchMode=yes", "-o", "ConnectTimeout=5", "-o", "StrictHostKeyChecking=no",
            "-o", "UserKnownHostsFile=/dev/null", "-o", "IdentitiesOnly=yes", "-i", SSH_KEY]


def _target(box):
    b = BOXES[box]
    return f"{b['user']}@{b['host']}"


def _remote_py(box) -> str:
    """Resolve the box's real python.exe (skips the WindowsApps stub)."""
    tgt = _target(box)
    r = subprocess.run(["ssh", *SSH_OPTS, tgt, "where python"],
                       capture_output=True, text=True, timeout=15)
    for line in r.stdout.splitlines():
        line = line.strip()
        if line.lower().endswith("python.exe") and "windowsapps" not in line.lower():
            return line
    return REMOTE_PY_FALLBACK


def reachable(box) -> bool:
    try:
        r = subprocess.run(["ssh", *SSH_OPTS, _target(box), "echo ok"],
                           capture_output=True, text=True, timeout=12)
    except subprocess.TimeoutExpired:
        return False
    return r.returncode == 0 and "ok" in r.stdout


def deploy(box):
    tgt = _target(box)
    subprocess.run(["ssh", *SSH_OPTS, tgt, f'mkdir "{REMOTE_DIR}" 2>nul & echo done'],
                   capture_output=True, text=True, timeout=15)
    r = subprocess.run(["scp", *SSH_OPTS, str(AGENT),
                        f"{tgt}:C:/Users/budds/.qsb/qsb_box_grind_agent.py"],
                       capture_output=True, text=True, timeout=30)
    return {"box": box, "deployed": r.returncode == 0, "stderr": r.stderr.strip()[:200]}


def push(box, bundle_path):
    tgt = _target(box)
    subprocess.run(["ssh", *SSH_OPTS, tgt, f'mkdir "{REMOTE_DIR}" 2>nul & echo done'],
                   capture_output=True, text=True, timeout=15)
    r = subprocess.run(["scp", *SSH_OPTS, bundle_path, f"{tgt}:C:/Users/budds/.qsb/bundle.json"],
                       capture_output=True, text=True, timeout=30)
    return {"box": box, "pushed": r.returncode == 0, "bundle": bundle_path,
            "stderr": r.stderr.strip()[:200]}


def drive(box):
    """Trigger a grind+rollup on the box (box uses its LOCAL model only)."""
    tgt = _target(box)
    py = _remote_py(box)
    cmd = f'"{py}" "{REMOTE_DIR}\\qsb_box_grind_agent.py" grind & '\
          f'"{py}" "{REMOTE_DIR}\\qsb_box_grind_agent.py" rollup'
    r = subprocess.run(["ssh", *SSH_OPTS, tgt, cmd],
                       capture_output=True, text=True, timeout=600)
    return {"box": box, "rc": r.returncode, "stdout": r.stdout[-1500:], "stderr": r.stderr[-400:]}


def collect(box):
    tgt = _target(box)
    INBOX.mkdir(parents=True, exist_ok=True)
    local = INBOX / f"{box}_results_bundle.json"
    # OpenSSH scp on Windows: quote + forward-slash the remote path to avoid
    # backslash escaping mangling.
    remote = "C:/Users/budds/.qsb/results_bundle.json"
    r = subprocess.run(["scp", *SSH_OPTS, f"{tgt}:{remote}", str(local)],
                       capture_output=True, text=True, timeout=30)
    if r.returncode != 0:
        return {"box": box, "collected": False, "stderr": r.stderr.strip()[:200]}
    # apply on the tower
    sys.path.insert(0, str(ROOT / "tools"))
    import qsb_work_bundle as wb
    applied = wb.apply(str(local))
    return {"box": box, "collected": True, "local": str(local), "apply": applied}


def main():
    ap = argparse.ArgumentParser()
    sub = ap.add_subparsers(dest="cmd", required=True)
    for name in ("deploy", "drive", "collect", "reachable"):
        p = sub.add_parser(name)
        p.add_argument("--box", required=True, choices=list(BOXES))
    pp = sub.add_parser("push")
    pp.add_argument("--box", required=True, choices=list(BOXES))
    pp.add_argument("--bundle", required=True)
    args = ap.parse_args()
    if args.cmd == "reachable":
        ok = reachable(args.box)
        print(json.dumps({"box": args.box, "reachable": ok}))
        sys.exit(0 if ok else 1)
    fn = {"deploy": lambda: deploy(args.box), "push": lambda: push(args.box, args.bundle),
          "drive": lambda: drive(args.box), "collect": lambda: collect(args.box)}[args.cmd]
    print(json.dumps(fn(), indent=2))


if __name__ == "__main__":
    main()
