#!/usr/bin/env python3
"""
qsb_tower_health.py — REAL tower telemetry (Wren's eyes). 2026-07-20, Ross: "give wren real eyes".

Wren's mind (qwen2.5:14b) has no live view of the tower, so when asked she guesses "all healthy"
even when the event bus is dead and the traders aren't trading. This collects the ACTUAL state from
the live system (services, event bus, traders, disk/load, task council) into a compact snapshot that
gets fed into her chat context. This does NOT touch her mind/persona/loop — it's a data source she reads.

Usage:
  python3 tools/qsb_tower_health.py            # print snapshot json + write the cache file
  from qsb_tower_health import snapshot         # dict
  from qsb_tower_health import brief             # one-paragraph human string (what Wren sees)
"""
import os, sys, json, time, subprocess, shutil
from datetime import datetime, timezone

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
CACHE = os.path.join(ROOT, "data", "registries", "qsb_tower_health_snapshot.json")
CORE_SERVICES = ["qsb-leadership-relay", "qsb-task-council-autorunner", "qsb-wren-dash",
                 "qsb-wren-mind", "qsb-brain-router-v4", "qsb-boardroom", "qsb-event-bus",
                 "qsb-ceo-room-bridge", "qsb-tour-guide"]


def _utc():
    return datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")


def _sh(cmd, t=5):
    try:
        return subprocess.run(cmd, shell=True, capture_output=True, text=True, timeout=t).stdout.strip()
    except Exception:
        return ""


def snapshot() -> dict:
    s = {"ts": _utc()}
    # services (read-only, no sudo needed for is-active)
    up, down = [], []
    for svc in CORE_SERVICES:
        st = _sh(f"systemctl is-active {svc}.service")
        (up if st == "active" else down).append(svc)
    s["services"] = {"up": len(up), "total": len(CORE_SERVICES), "down": down}
    # event bus
    s["event_bus_bound"] = bool(_sh("ss -xlnp 2>/dev/null | grep -c qsb_bus") not in ("", "0"))
    # traders
    n_traders = _sh("ps -eo cmd ww 2>/dev/null | grep -c '[b]elief_driven_trader.py'") or "0"
    s["traders_alive"] = int(n_traders) if n_traders.isdigit() else 0
    # trading recently? (broker place attempts in last 10 min)
    audit = os.path.join(ROOT, "data", "registries", "qsb_broker_place_audit.jsonl")
    trading_recent = False
    last_attempt = None
    try:
        if os.path.exists(audit) and (time.time() - os.path.getmtime(audit)) < 600:
            trading_recent = True
            tail = _sh(f"tail -1 {audit}")
            if tail:
                d = json.loads(tail)
                last_attempt = f"{(d.get('ts') or '')[:19]} {d.get('worker_id')} {d.get('venue')} {d.get('side')} ok={d.get('ok')}"
    except Exception:
        pass
    s["traders_attempting_orders_recently"] = trading_recent
    s["last_broker_attempt"] = last_attempt
    # disk + load
    s["root_disk_pct"] = _sh("df -P / | awk 'NR==2{print $5}'")
    la = os.getloadavg()
    s["load_1m"] = round(la[0], 1)
    # task council
    try:
        sys.path.insert(0, os.path.join(ROOT, "tools"))
        import qsb_council_tasks as T
        from collections import Counter
        c = Counter(t.get("state") for t in T.snapshot().get("tasks", []))
        s["task_council"] = {"open": c.get("open", 0), "in_progress": c.get("in_progress", 0) + c.get("claimed", 0),
                             "blocked": c.get("blocked", 0), "done": c.get("done", 0)}
    except Exception:
        s["task_council"] = None
    return s


def brief(s: dict = None) -> str:
    s = s or snapshot()
    bus = "LIVE" if s.get("event_bus_bound") else "DEAD"
    trading = "trading" if s.get("traders_attempting_orders_recently") else "NOT trading (no orders in 10min)"
    down = s.get("services", {}).get("down") or []
    svc = f"{s['services']['up']}/{s['services']['total']} core services up" + (f" (DOWN: {', '.join(down)})" if down else "")
    tc = s.get("task_council") or {}
    return (f"LIVE TOWER TELEMETRY ({s['ts']}): {svc}. Event bus {bus}. "
            f"{s.get('traders_alive', 0)} traders alive, {trading}"
            + (f" (last: {s['last_broker_attempt']})" if s.get("last_broker_attempt") else "")
            + f". Root disk {s.get('root_disk_pct','?')}, load {s.get('load_1m','?')}. "
            f"Task council: {tc.get('done',0)} done / {tc.get('in_progress',0)} in-progress / "
            f"{tc.get('blocked',0)} blocked / {tc.get('open',0)} open.")


if __name__ == "__main__":
    snap = snapshot()
    try:
        tmp = CACHE + ".tmp"
        json.dump({**snap, "brief": brief(snap)}, open(tmp, "w"), indent=2)
        os.replace(tmp, CACHE)
    except Exception as e:
        print("cache write err:", e, file=sys.stderr)
    print(brief(snap))
