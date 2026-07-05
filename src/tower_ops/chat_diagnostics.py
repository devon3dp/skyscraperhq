"""Kernel chat diagnostics — verifies sidecar liveness + adapter health."""

from datetime import datetime, timezone
from pathlib import Path
import json
import socket
import urllib.request

from .safety_contract import stamp_safe

ROOT = Path("/vaults/nvme0/qsb_tower_v1")


def _now(): return datetime.now(timezone.utc).isoformat()


def _port_listening(host, port, timeout=0.2):
    try:
        with socket.create_connection((host, port), timeout=timeout):
            return True
    except OSError:
        return False


def diagnostics():
    listening = _port_listening("127.0.0.1", 8766, timeout=0.3)
    health = None; health_err = None
    if listening:
        try:
            with urllib.request.urlopen("http://127.0.0.1:8766/api/kernel_chat_health", timeout=1.5) as r:
                health = json.loads(r.read().decode("utf-8"))
        except Exception as e:
            health_err = str(e)[:200]
    # Adapter check — does load_kernel return a real kernel or a sentinel?
    adapter_check = {}
    try:
        from tower.kernel_dialogue_adapter import load_kernel
        k = load_kernel()
        adapter_check["loaded"] = not isinstance(k, dict)
        if isinstance(k, dict):
            adapter_check["kernel_unavailable_reason"] = k.get("reason")
            adapter_check["fallback_path"] = "symbolic_reply + local_model_inference_gateway"
    except Exception as exc:
        adapter_check["loaded"] = False
        adapter_check["error"] = str(exc)[:200]
    return stamp_safe({
        "ok": True, "ts": _now(),
        "sidecar_port": 8766,
        "sidecar_listening": listening,
        "sidecar_health": health,
        "sidecar_health_error": health_err,
        "adapter_check": adapter_check,
        "recursion_guard_active": True,
        "dashboard_routes": ["GET /api/kernel_chat_status",
                              "GET /api/kernel_chat_history",
                              "POST /api/kernel_chat"],
        "recommendation": "If adapter loaded=true: chat is live. If adapter loaded=false and "
                           "fallback_path is set: chat degrades gracefully via symbolic+local-model "
                           "(no execution unlocks).",
    })
