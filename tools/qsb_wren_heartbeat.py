#!/usr/bin/env python3
"""qsb_wren_heartbeat.py — Wren's single liveness heartbeat.

The ONE allowed pulse (Ross 2026-07-08: "1 heartbeat as there are other
heartbeats in the system as well"). Cheap: one CEO health check via
qsb_wren_ceo_health.check_all(). NO 14B inference here.

Edge-triggered on purpose: it only wakes Wren's MIND (by appending a note to
her self-schedule wake-queue) when the set of MISSING CEOs CHANGES. TP/Acer are
often offline, so a level-triggered check would nudge her every pulse and churn
inference through the back door. Edge-triggered = wake her once when something
newly breaks (or newly recovers), not on every tick.

Her mind (qsb_wren_evolution_loop) watches wren_self_schedule.jsonl and wakes on
append — so this heartbeat detects, her mind reacts only to real change.
"""
import json
import sys
import time
from pathlib import Path

ROOT = Path("/vaults/nvme0/qsb_tower_v1")
REG = ROOT / "data/registries"
STATE = REG / "qsb_wren_heartbeat_state.json"
SCHED = REG / "wren_self_schedule.jsonl"
LOG = ROOT / "data/logs/wren_heartbeat.log"

sys.path.insert(0, str(ROOT / "tools"))
from qsb_wren_ceo_health import check_all  # cheap curl health check, no inference


def _last_missing():
    """Returns previous missing-set, or None on first-ever run."""
    try:
        return sorted(json.loads(STATE.read_text()).get("missing", []))
    except Exception:
        return None


def main():
    now = time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())
    r = check_all()
    missing = sorted(r.get("missing", []))
    last = _last_missing()
    changed = (last is None) or (missing != last)

    woke = False
    if changed and missing:
        # edge: the missing-set changed AND someone is down -> wake her mind once
        SCHED.parent.mkdir(parents=True, exist_ok=True)
        with SCHED.open("a") as f:
            f.write(json.dumps({
                "ts": now,
                "source": "wren_heartbeat",
                "wake_reason": "quorum_changed",
                "missing": missing,
                "online_count": r.get("online_count"),
            }) + "\n")
        woke = True

    STATE.write_text(json.dumps({
        "ts": now, "missing": missing, "quorum_met": r.get("quorum_met"),
    }))
    LOG.parent.mkdir(parents=True, exist_ok=True)
    with LOG.open("a") as f:
        f.write(f"{now} online={r.get('online_count')} missing={missing} woke_wren={woke}\n")

    print(json.dumps({
        "ts": now, "online_count": r.get("online_count"),
        "quorum_met": r.get("quorum_met"), "missing": missing, "woke_wren": woke,
    }))


if __name__ == "__main__":
    main()
