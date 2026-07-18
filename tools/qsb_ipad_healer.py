#!/usr/bin/env python3
"""qsb_ipad_healer.py — continuous check + auto-heal for iPad-visible services.

Ross 2026-07-06 #221: "i need a healer to work on ipad to always check whats
working and whats down or not working etc"

Every 30s: probe hub + HQ dash + Wren dash + watcher + traders dash.
If any is down: auto-restart it. Log heal actions to a JSONL the iPad reads.
"""
from __future__ import annotations
import json, os, subprocess, time, urllib.request
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path("/vaults/nvme0/qsb_tower_v1")
REG = ROOT / "data/registries"
HEALER_LOG = REG / "qsb_ipad_healer.jsonl"
HEALER_STATE = REG / "qsb_ipad_healer_state.json"
HEALER_LOG.parent.mkdir(parents=True, exist_ok=True)

CHECK_EVERY_S = 30

# Service definitions: name → (probe URL, restart command)
SERVICES = [
    {
        "name": "hub",
        "url": "http://127.0.0.1:8852/ipad",
        "cmd": ["python3", str(ROOT/"tools/qsb_boardroom_hub.py"), "--port", "8852"],
        "log": "/tmp/hub_boot.log",
        "critical": True,
    },
    {
        "name": "hq_dash",
        "url": "http://127.0.0.1:8850/",
        "cmd": ["python3", str(ROOT/"tools/qsb_hq_claude_dash.py"), "--port", "8850"],
        "log": "/tmp/hq_dash.log",
        "critical": True,
    },
    {
        "name": "wren_dash",
        "url": "http://127.0.0.1:8851/",
        "cmd": ["python3", str(ROOT/"tools/qsb_wren_dash.py"), "--port", "8851"],
        "log": "/tmp/wren_dash.log",
        "critical": True,
    },
    {
        "name": "traders_dash",
        "url": "http://127.0.0.1:8847/",
        "cmd": ["python3", str(ROOT/"tools/qsb_traders_live_serve.py"), "--port", "8847"],
        "log": "/tmp/traders_dash.log",
        "critical": False,
    },
    {
        "name": "watcher",
        "url": None,  # no HTTP — probe by process
        "pgrep": "qsb_council_watcher.py",
        "cmd": ["python3", str(ROOT/"tools/qsb_council_watcher.py")],
        "log": "/tmp/watcher.log",
        "critical": True,
    },
    {
        "name": "heartbeat",
        "url": None,
        "pgrep": "qsb_ceo_heartbeat.py",
        "cmd": ["python3", str(ROOT/"tools/qsb_ceo_heartbeat.py")],
        "log": "/tmp/heartbeat.log",
        "critical": False,
    },
]

def _utc(): return datetime.now(timezone.utc).isoformat().replace("+00:00","Z")

def _log(row: dict):
    row["ts"] = _utc()
    with HEALER_LOG.open("a") as f:
        f.write(json.dumps(row) + "\n")

def _write_state(state: dict):
    HEALER_STATE.write_text(json.dumps(state, indent=2))

def probe_service(s: dict) -> tuple[bool, str]:
    if s.get("url"):
        try:
            with urllib.request.urlopen(s["url"], timeout=3) as r:
                return (r.status < 500, f"http {r.status}")
        except Exception as e:
            return (False, str(e)[:80])
    elif s.get("pgrep"):
        try:
            r = subprocess.run(["pgrep","-f", s["pgrep"]], capture_output=True, text=True, timeout=3)
            alive = bool(r.stdout.strip())
            return (alive, f"pids: {r.stdout.strip() or 'none'}")
        except Exception as e:
            return (False, str(e)[:80])
    return (False, "no probe defined")

def restart_service(s: dict) -> tuple[bool, str]:
    try:
        # kill first (any lingering)
        if s.get("pgrep"):
            subprocess.run(["pkill","-f", s["pgrep"]], timeout=3)
        elif s.get("url"):
            # kill by port
            port = s["url"].rsplit(":",1)[-1].split("/")[0]
            subprocess.run(["fuser","-k", f"{port}/tcp"], timeout=3, capture_output=True)
        time.sleep(2)
        # relaunch detached
        log_path = s.get("log","/tmp/heal.log")
        subprocess.Popen(s["cmd"], stdout=open(log_path,"ab"), stderr=subprocess.STDOUT,
                         start_new_session=True, close_fds=True)
        time.sleep(5)
        ok, detail = probe_service(s)
        return (ok, f"restart → probe {detail}")
    except Exception as e:
        return (False, f"restart error: {str(e)[:80]}")

def main():
    print(f"  ipad-healer starting · cadence {CHECK_EVERY_S}s · {len(SERVICES)} services")
    while True:
        state = {"ts": _utc(), "services": []}
        heals = 0
        for s in SERVICES:
            ok, detail = probe_service(s)
            entry = {"name": s["name"], "ok": ok, "detail": detail, "critical": s.get("critical", False)}
            if not ok:
                _log({"kind":"probe_fail","service":s["name"],"detail":detail})
                if s.get("critical", False):
                    _log({"kind":"heal_attempt","service":s["name"]})
                    healed, hdetail = restart_service(s)
                    entry["healed"] = healed
                    entry["heal_detail"] = hdetail
                    _log({"kind":"heal_result","service":s["name"],"healed":healed,"detail":hdetail})
                    heals += 1
            state["services"].append(entry)
        state["last_heal_count"] = heals
        _write_state(state)
        time.sleep(CHECK_EVERY_S)

if __name__ == "__main__":
    main()
