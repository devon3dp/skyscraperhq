"""live_tower_status — grounded live telemetry for Wren.

Reads the health snapshot the heartbeat writes; if it's older than max_age_s,
re-runs qsb_tower_health.py snapshot() for a fresh read. Read-only.
"""
import json, subprocess, sys, time
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[3]
SNAP = ROOT / "data/registries/qsb_tower_health_snapshot.json"
TOOLS = ROOT / "tools"


def _age_s(ts: str) -> float:
    try:
        t = datetime.fromisoformat(ts.replace("Z", "+00:00"))
        return (datetime.now(timezone.utc) - t).total_seconds()
    except Exception:
        return 1e9


def run(max_age_s: int = 180):
    snap = None
    src = "snapshot_file"
    if SNAP.exists():
        try:
            snap = json.loads(SNAP.read_text())
        except Exception:
            snap = None
    age = _age_s(snap.get("ts", "")) if snap else 1e9
    if snap is None or age > max_age_s:
        # try a fresh in-process snapshot from the health tool
        try:
            sys.path.insert(0, str(TOOLS))
            import qsb_tower_health as H  # type: ignore
            fresh = H.snapshot()
            fresh["brief"] = H.brief(fresh)
            snap = fresh
            src = "fresh_snapshot"
            age = 0.0
        except Exception as e:
            if snap is None:
                return {"ok": False, "error": f"no snapshot and fresh failed: {e}"}
            src = "snapshot_file_stale"
    svc = snap.get("services", {})
    tc = snap.get("task_council", {})
    return {
        "ok": True,
        "source": src,
        "snapshot_ts": snap.get("ts"),
        "age_s": round(age, 1),
        "services_up": svc.get("up"),
        "services_total": svc.get("total"),
        "services_down": svc.get("down", []),
        "event_bus_bound": snap.get("event_bus_bound"),
        "traders_alive": snap.get("traders_alive"),
        "traders_attempting_orders_recently": snap.get("traders_attempting_orders_recently"),
        "root_disk_pct": snap.get("root_disk_pct"),
        "load_1m": snap.get("load_1m"),
        "task_council": {
            "open": tc.get("open"), "in_progress": tc.get("in_progress"),
            "blocked": tc.get("blocked"), "done": tc.get("done"),
        },
        "brief": snap.get("brief"),
    }


if __name__ == "__main__":
    print(json.dumps(run(), indent=2))
