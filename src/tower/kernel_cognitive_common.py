"""kernel_cognitive_common.py — shared helpers for cognitive modules.

Read-only registry/log helpers used by:
    kernel_perception_layer
    kernel_attention_layer
    kernel_working_memory
    kernel_self_model
    kernel_reflection_layer
    kernel_learning_assimilation
    kernel_goal_stack
    kernel_curiosity_queue
    kernel_opencore_supervision_bridge

Safety contract (every helper here MUST honor):
    - No execution.
    - No external network calls.
    - No worker dispatch.
    - No secret exposure (skips dotfiles, .env, *.key, *.pem, *.secret*).
    - All file reads are best-effort with safe fallbacks.
"""

from pathlib import Path
from datetime import datetime, timezone
import json
import os
import time

ROOT = Path("/vaults/nvme0/qsb_tower_v1")
REG = ROOT / "data/registries"
LOGS = ROOT / "data/logs"

STALE_SECONDS_DEFAULT = 6 * 3600  # 6h

_SECRET_PATTERNS = (".env", ".key", ".pem", ".secret", "_secret", "credentials")


def utc_now_iso():
    return datetime.now(timezone.utc).isoformat()


def utc_now_stamp():
    return datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")


def _path_is_safe(p):
    name = Path(p).name.lower()
    for pat in _SECRET_PATTERNS:
        if pat in name:
            return False
    return True


def load_registry(name, fallback=None):
    """Read data/registries/<name> as JSON. Always returns a value.
    Returns fallback (default {}) when missing or unparseable.
    """
    p = REG / name
    if not _path_is_safe(p):
        return fallback if fallback is not None else {}
    if not p.exists():
        return fallback if fallback is not None else {}
    try:
        return json.loads(p.read_text(encoding="utf-8"))
    except Exception:
        return fallback if fallback is not None else {}


def registry_exists(name):
    p = REG / name
    return _path_is_safe(p) and p.is_file()


def registry_age_seconds(name):
    p = REG / name
    if not p.exists():
        return None
    try:
        return max(0.0, time.time() - p.stat().st_mtime)
    except Exception:
        return None


def registry_is_stale(name, max_age_seconds=STALE_SECONDS_DEFAULT):
    age = registry_age_seconds(name)
    if age is None:
        return False
    return age > max_age_seconds


def latest_log_matching(prefix):
    """Return the newest data/logs/<prefix>* file path or None."""
    if not LOGS.exists():
        return None
    candidates = []
    try:
        for entry in LOGS.iterdir():
            if not entry.is_file():
                continue
            if not _path_is_safe(entry):
                continue
            if entry.name.startswith(prefix):
                candidates.append(entry)
    except Exception:
        return None
    if not candidates:
        return None
    candidates.sort(key=lambda p: p.stat().st_mtime, reverse=True)
    return candidates[0]


def append_jsonl(name, record):
    """Append a record to data/logs/<name>. Best-effort, never raises."""
    p = LOGS / name
    try:
        p.parent.mkdir(parents=True, exist_ok=True)
        with p.open("a", encoding="utf-8") as f:
            f.write(json.dumps(record, default=str) + "\n")
    except Exception:
        pass


def write_registry(name, payload):
    """Atomically write data/registries/<name>. Returns the path written."""
    p = REG / name
    try:
        p.parent.mkdir(parents=True, exist_ok=True)
        tmp = p.with_suffix(p.suffix + ".tmp")
        tmp.write_text(json.dumps(payload, indent=2, default=str) + "\n",
                       encoding="utf-8")
        os.replace(tmp, p)
    except Exception:
        try:
            p.write_text(json.dumps(payload, indent=2, default=str) + "\n",
                         encoding="utf-8")
        except Exception:
            pass
    return str(p.relative_to(ROOT))


def classify_sources(names, stale_seconds=STALE_SECONDS_DEFAULT):
    """For a list of registry names, return three sublists:
    (present_fresh, present_stale, missing).
    Each item is just the name string."""
    present_fresh, present_stale, missing = [], [], []
    for n in names:
        if not registry_exists(n):
            missing.append(n)
        elif registry_is_stale(n, stale_seconds):
            present_stale.append(n)
        else:
            present_fresh.append(n)
    return present_fresh, present_stale, missing


def safety_block():
    """Standard locked-false safety block stamped on every cognitive payload."""
    return {
        "advisory_only": True,
        "execution_allowed": False,
        "worker_execution_enabled": False,
        "provider_execution_enabled": False,
        "model_inference_enabled": False,
        "live_dispatch_enabled": False,
        "autonomous_workers_enabled": False,
        "direct_provider_access": False,
        "live_trading_enabled": False,
        "real_order_execution_enabled": False,
        "openclaw_execution_enabled": False,
        "binance_order_execution_enabled": False,
        "stock_order_execution_enabled": False,
        "web_access_autonomous_enabled": False,
        "maintenance_auto_repair_enabled": False,
        "kernel_state": "active_local_only",
        "kernel_source": "rebased_kernel",
        "scope": "local_only_advisory_cognition",
    }
