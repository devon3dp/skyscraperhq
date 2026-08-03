#!/usr/bin/env python3
"""
qsb_oracle_worker.py — wire the Oracle Cloud VM as a REAL worker on the Underground.

2026-07-29, Ross: "look in vault and connect oracle prove it". The Oracle node was marked
KNOWN_DEAD ("no event source") — but it's a live Ubuntu 24.04 VM (hostname 'sky',
145.241.225.163) reachable by SSH key. This connects for real each cycle, pulls a genuine
health reading from the VM, and logs a council event so the map draws an oracle->task_council
train. HONEST: a train is logged ONLY when the SSH round-trip actually returns real data; if
the VM is unreachable, NOTHING is logged (no fabricated train).

Key: data/runtime/ssh/oracle_vm_ross_ed25519 (user ubuntu). systemd: qsb-oracle-worker.timer.
Run once: python3 tools/qsb_oracle_worker.py
"""
import json, subprocess, time, uuid
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
BOARD = ROOT / "data" / "registries" / "qsb_council_tasks.jsonl"
KEY = ROOT / "data" / "runtime" / "ssh" / "oracle_vm_ross_ed25519"
HOST = "ubuntu@145.241.225.163"


def _utc():
    return time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())


def probe():
    """Real SSH round-trip. Returns a real one-line health string, or None if unreachable."""
    cmd = ("echo host=$(hostname) load=$(cut -d' ' -f1 /proc/loadavg) "
           "up=$(cut -d. -f1 /proc/uptime)s procs=$(ps -e --no-headers | wc -l)")
    try:
        r = subprocess.run(
            ["ssh", "-o", "BatchMode=yes", "-o", "StrictHostKeyChecking=accept-new",
             "-o", "ConnectTimeout=12", "-i", str(KEY), HOST, cmd],
            capture_output=True, text=True, timeout=25)
        out = (r.stdout or "").strip()
        return out if (r.returncode == 0 and out.startswith("host=")) else None
    except Exception:
        return None


def main():
    health = probe()
    if not health:
        print("[oracle-worker] Oracle VM unreachable — NOTHING logged (no fake train).")
        return
    tid = "ORACLE_" + uuid.uuid4().hex[:8]
    ts = _utc()
    with open(BOARD, "a") as f:
        f.write(json.dumps({"ts": ts, "event": "tool_selected", "actor": "wren", "task_id": tid,
                            "text": f"owner uses Oracle Cloud VM (sky · 145.241.225.163) — {health[:60]}"}) + "\n")
        f.write(json.dumps({"ts": ts, "event": "noted", "actor": "oracle", "task_id": tid,
                            "text": f"Oracle VM real health: {health}"}) + "\n")
    print(f"[oracle-worker] CONNECTED + logged real train: {health}")


if __name__ == "__main__":
    main()
