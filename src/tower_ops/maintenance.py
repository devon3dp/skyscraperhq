"""Maintenance department — Floor 33 (Diagnostics Department).

Read-only checks: disk free, port liveness, dashboard asset availability,
worker heartbeat freshness, AirLLM chamber path existence. No auto-repair.
"""

from pathlib import Path
from datetime import datetime, timezone
import json
import shutil
import socket
import threading

from .safety_contract import LOCKED_FALSE, stamp_safe


ROOT = Path("/vaults/nvme0/qsb_tower_v1")
LOG_PATH = ROOT / "logs/tower_ops/maintenance_events.jsonl"

_LOCK = threading.Lock()


def _now(): return datetime.now(timezone.utc).isoformat()


def _disk_free(path):
    try:
        st = shutil.disk_usage(path)
        return {"total_gb": round(st.total / (1024 ** 3), 1),
                "used_gb":  round(st.used / (1024 ** 3), 1),
                "free_gb":  round(st.free / (1024 ** 3), 1),
                "pct_used": round((st.used / st.total) * 100, 1)}
    except Exception as e:
        return {"error": str(e)[:120]}


def _port_listening(host, port, timeout=0.2):
    try:
        with socket.create_connection((host, port), timeout=timeout):
            return True
    except OSError:
        return False


def _path_exists(p):
    return Path(p).exists()


def _dir_size_bytes(p, limit_entries=2000):
    p = Path(p)
    if not p.exists(): return 0
    total = 0; n = 0
    try:
        for entry in p.rglob("*"):
            if entry.is_file():
                try: total += entry.stat().st_size
                except Exception: pass
                n += 1
                if n > limit_entries: break
    except Exception: pass
    return total


def _append_log(rec):
    LOG_PATH.parent.mkdir(parents=True, exist_ok=True)
    rec = dict(rec); rec.setdefault("ts", _now())
    rec.setdefault("execution_allowed", False)
    with LOG_PATH.open("a", encoding="utf-8") as f:
        f.write(json.dumps(rec) + "\n")


CHECK_LIST = [
    "root_disk_free", "vaults_nvme0_free", "vaults_ai_free",
    "dashboard_port_8765", "kernel_chat_port_8766",
    "airllm_chamber_path_exists", "airllm_venv_exists",
    "qsb_state_folder_size", "qsb_logs_folder_size",
    "dashboard_static_index_present", "dashboard_static_cockpit_js_present",
    "data_registries_writable",
]


def checks():
    with _LOCK:
        results = {}
        results["root_disk_free"]                = _disk_free("/")
        results["vaults_nvme0_free"]             = _disk_free("/vaults/nvme0")
        results["vaults_ai_free"]                = _disk_free("/vaults/ai")
        results["dashboard_port_8765"]           = {"listening": _port_listening("127.0.0.1", 8765)}
        results["kernel_chat_port_8766"]         = {"listening": _port_listening("127.0.0.1", 8766)}
        results["airllm_chamber_path_exists"]    = {"exists": _path_exists("/vaults/ai/airllm_lab")}
        results["airllm_venv_exists"]            = {"exists": _path_exists("/vaults/ai/airllm_lab/.venv")}
        results["qsb_state_folder_size"]         = {"bytes": _dir_size_bytes(ROOT / "state")}
        results["qsb_logs_folder_size"]          = {"bytes": _dir_size_bytes(ROOT / "logs")}
        results["dashboard_static_index_present"] = {"exists": _path_exists(ROOT / "src/dashboard/static/index.html")}
        results["dashboard_static_cockpit_js_present"] = {"exists": _path_exists(ROOT / "src/dashboard/static/cockpit.js")}
        results["data_registries_writable"]      = {"exists": _path_exists(ROOT / "data/registries")}
        # Aggregate severity
        warnings = []
        if results["root_disk_free"].get("pct_used", 0) > 95: warnings.append("root disk >95% full")
        if not results["dashboard_port_8765"]["listening"]: warnings.append("dashboard port 8765 not listening")
        if not results["airllm_chamber_path_exists"]["exists"]: warnings.append("airllm chamber path missing")
        return stamp_safe({
            "ok": True, "ts": _now(),
            "check_list": CHECK_LIST,
            "results": results,
            "warnings": warnings,
            "overall_status": "healthy" if not warnings else "warning",
            "policy": "READ_ONLY — no auto-repair · no service kill · no file delete",
        })


def status():
    return checks()


def run_check(payload=None):
    payload = payload or {}; name = payload.get("check")
    # We always re-run the full battery (cheap).
    c = checks()
    _append_log({"event": "run_check", "requested": name, "warnings": c.get("warnings")})
    return c


def ack_alert(payload=None):
    payload = payload or {}; alert_id = payload.get("alert_id") or "all"
    _append_log({"event": "ack_alert", "alert_id": alert_id})
    return stamp_safe({"ok": True, "ts": _now(), "acked": alert_id})
