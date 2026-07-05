#!/usr/bin/env python3
"""qsb_supervisor.py — daemon supervisor + escalation log.

Ross 2026-06-14: "100% persistent. If it falls, it can get back up."

The heartbeat's daemon_sweep already revives dead daemons. This supervisor
adds the escalation layer that wasn't there: if any daemon needs revival
more than 3 times in 1 hour, that's a real failure, not a transient — alert
Ross via the message board AND stamp a high-severity F47 record.

Honors Helix strand 9: this is a SUPERVISOR (observer), not an autonomous
worker. It doesn't dispatch tasks, doesn't call providers, doesn't flip
gates. It only watches the revival log and alerts.

Run one-shot from the heartbeat each tick.
"""
from __future__ import annotations
import json, os, subprocess, sys
from datetime import datetime, timezone, timedelta
from pathlib import Path

ROOT = Path("/vaults/nvme0/qsb_tower_v1")
REVIVAL_LOG = ROOT / "data/registries/qsb_supervisor_revival_log.jsonl"
ESCALATION_LOG = ROOT / "data/registries/qsb_supervisor_escalations.jsonl"
F47 = ROOT / "data/registries/qsb_f47_team_records.jsonl"
MSG_BOARD_TOOL = ROOT / "tools/qsb_message_board.py"
TOMBSTONE_FILE = ROOT / "data/registries/qsb_tombstoned_daemons.json"

DAEMONS = [
    ("dashboard",       "src/dashboard/server.py"),
    ("lumen",           "qsb_lumen_serve.py"),
    ("vision",          "qsb_vision_floor.py"),
    ("heartbeat",       "qsb_tower_heartbeat.py"),
    ("cloudflared",     "cloudflared"),
    ("qualify_loop",    "qsb_qualify_everyone.py"),
]


def _tombstoned() -> set:
    """Return set of daemon names that are tombstoned (must not be revived)."""
    if not TOMBSTONE_FILE.exists():
        return set()
    try:
        data = json.loads(TOMBSTONE_FILE.read_text())
        return set(data.get("tombstoned", []) or [])
    except Exception:
        return set()

REVIVAL_WINDOW_MIN = 60   # 1 hour
ESCALATE_THRESHOLD = 3    # >3 revivals in window → escalate


def utcnow():
    return datetime.now(timezone.utc).isoformat().replace("+00:00","Z")


def _is_alive(pat: str) -> bool:
    try:
        r = subprocess.run(["pgrep","-f",pat], capture_output=True, text=True, timeout=4)
        return r.returncode == 0 and r.stdout.strip() != ""
    except Exception:
        return False


def _read_jsonl(path: Path):
    if not path.exists():
        return []
    rows = []
    for ln in path.read_text().splitlines():
        ln = ln.strip()
        if not ln: continue
        try: rows.append(json.loads(ln))
        except: continue
    return rows


def _append(path: Path, row: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("a") as f:
        f.write(json.dumps(row) + "\n")


def _record_revival(daemon: str) -> None:
    _append(REVIVAL_LOG, {"ts": utcnow(), "daemon": daemon})


def _recent_revivals(daemon: str, window_min: int) -> int:
    rows = _read_jsonl(REVIVAL_LOG)
    cutoff = (datetime.now(timezone.utc) - timedelta(minutes=window_min))
    count = 0
    for r in rows:
        if r.get("daemon") != daemon:
            continue
        try:
            ts = datetime.fromisoformat(r["ts"].replace("Z","+00:00"))
        except Exception:
            continue
        if ts >= cutoff:
            count += 1
    return count


def _escalate(daemon: str, revivals: int) -> None:
    row = {
        "ts": utcnow(),
        "daemon": daemon,
        "revivals_in_window": revivals,
        "window_min": REVIVAL_WINDOW_MIN,
        "severity": "high",
        "message": (f"Daemon `{daemon}` has been revived {revivals} times in "
                    f"{REVIVAL_WINDOW_MIN} min — that's flapping, not a transient. "
                    "Investigate: check daemon log, recent commits, OOM, port bind."),
    }
    _append(ESCALATION_LOG, row)
    # Stamp F47 + push to message board (highest priority)
    _append(F47, {**row, "kind": "supervisor_escalation", "floor": "F47",
                  "operator": "supervisor"})
    try:
        subprocess.run([
            "python3", str(MSG_BOARD_TOOL), "post",
            "--title", f"⚠ Supervisor escalation: {daemon} flapping",
            "--body", row["message"],
            "--priority", "high",
            "--audience", "Ross",
            "--author", "Supervisor",
        ], cwd=str(ROOT), timeout=10, capture_output=True)
    except Exception:
        pass


def tick() -> dict:
    """One pass: check each daemon, record revival if dead, escalate if flapping."""
    results = {"checked": [], "down_now": [], "escalated": [], "tombstoned_skipped": []}
    tombstoned = _tombstoned()
    for name, pat in DAEMONS:
        if name in tombstoned:
            # Tombstoned daemons are intentionally dead. Do NOT record revival,
            # do NOT escalate. Note the skip so audit trail is honest.
            results["tombstoned_skipped"].append(name)
            continue
        alive = _is_alive(pat)
        results["checked"].append({"name": name, "alive": alive})
        if alive:
            continue
        # Daemon down — note revival event (heartbeat tick 1 will actually revive it)
        _record_revival(name)
        results["down_now"].append(name)
        # Count recent revivals
        n = _recent_revivals(name, REVIVAL_WINDOW_MIN)
        if n > ESCALATE_THRESHOLD:
            _escalate(name, n)
            results["escalated"].append({"name": name, "revivals": n})
    rec = {
        "ts": utcnow(),
        "kind": "supervisor_tick",
        "floor": "F47",
        "operator": "supervisor",
        **results,
    }
    _append(F47, rec)
    return rec


def main():
    rec = tick()
    print(json.dumps({
        "ok": True,
        "ts": rec["ts"],
        "down_now": rec["down_now"],
        "escalated": rec["escalated"],
    }, indent=2))
    return 0


if __name__ == "__main__":
    sys.exit(main())
