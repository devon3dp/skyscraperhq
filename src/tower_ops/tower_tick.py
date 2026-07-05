"""Tower Tick V1 — lightweight read-side advancement.

Advances worker location indicators and produces a `live_state` snapshot
the renderer reads each tick. Does NOT execute trading, dispatch, or
OpenClaw. Does NOT modify execution locks.
"""

from datetime import datetime, timezone
from pathlib import Path
import json
import threading

from .safety_contract import LOCKED_FALSE, stamp_safe

ROOT = Path("/vaults/nvme0/qsb_tower_v1")
TICK_PATH = ROOT / "state/tower_ops/tick.json"
LOG_PATH  = ROOT / "logs/tower_ops/tick_events.jsonl"

_LOCK = threading.Lock()


def _now(): return datetime.now(timezone.utc).isoformat()


def _read():
    if not TICK_PATH.exists():
        TICK_PATH.parent.mkdir(parents=True, exist_ok=True)
        return {"ts": _now(), "tick_count": 0, **LOCKED_FALSE}
    try: return json.loads(TICK_PATH.read_text(encoding="utf-8"))
    except Exception: return {"ts": _now(), "tick_count": 0}


def _write(d):
    d["ts"] = _now()
    d.update(LOCKED_FALSE)
    TICK_PATH.write_text(json.dumps(d, indent=2), encoding="utf-8")


def tick(payload=None):
    """Advance one tick. Updates worker heartbeats + tick_count."""
    with _LOCK:
        # Calling worker_registry.status() stamps heartbeats on every worker.
        try:
            from .worker_registry import status as _ws
            ws = _ws()
        except Exception as exc:
            ws = {"error": str(exc)[:200]}
        st = _read()
        st["tick_count"] = (st.get("tick_count") or 0) + 1
        st["last_tick_ts"] = _now()
        st["last_worker_count"] = ws.get("total_workers")
        _write(st)
        with LOG_PATH.open("a", encoding="utf-8") as f:
            f.write(json.dumps({"ts": _now(), "tick_count": st["tick_count"],
                                "execution_allowed": False}) + "\n")
        return stamp_safe({"ok": True, "ts": _now(),
                            "tick_count": st["tick_count"],
                            "last_worker_count": ws.get("total_workers"),
                            "policy": "READ_SIDE_ONLY — no execution"})


def live_state():
    """Snapshot the renderer reads each cycle."""
    from .lifts import status as lift_status
    from .worker_directory import directory
    from .worker_registry import status as ws_status
    try:    lifts = lift_status()
    except Exception: lifts = {"lifts": []}
    try:    d  = directory()
    except Exception: d  = {"directory": []}
    try:    ws = ws_status()
    except Exception: ws = {}
    return stamp_safe({
        "ok": True, "ts": _now(),
        "phase": "QSB_TOWER_OPERATIONS_V2",
        "tick_state":   _read(),
        "worker_count": ws.get("total_workers"),
        "lift_count":   len(lifts.get("lifts") or []),
        "lifts":        lifts.get("lifts") or [],
        "renderer_version": "QSB_SKYSCRAPER_RENDERER_V3",
    })
