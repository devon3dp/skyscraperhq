"""QSB Cognitive Kernel — 20-layer cognitive architecture.

Phase: QSB_KERNEL_COGNITIVE_ARCHITECTURE_BUILD_V1
Reflection memo: QSB_KERNEL_COGNITIVE_ARCHITECTURE_REFLECTION_V1

Safety contract (immutable, every layer reasserts):
  - execution_allowed = False
  - real_money_live_trading_enabled = False
  - openclaw_real_tool_execution_enabled = False
  - autonomous_dispatch_enabled = False
  - worker_execution_enabled = False
  - live_payments_enabled = False
  - live_listings_publishing_enabled = False
  - external_api_calls_enabled = False
  - Kernel may THINK, SPEAK, PROPOSE. Kernel may not DO.
"""

from pathlib import Path
import json
import time

ROOT = Path("/vaults/nvme0/qsb_tower_v1")
REG = ROOT / "data/registries"
COG_REG = REG / "cognitive"
COG_LOG = ROOT / "data/logs/cognitive"
COG_REG.mkdir(parents=True, exist_ok=True)
COG_LOG.mkdir(parents=True, exist_ok=True)

SAFETY = {
    "execution_allowed": False,
    "active_local_only": True,
    "advisory_only": True,
    "real_money_live_trading_enabled": False,
    "openclaw_real_tool_execution_enabled": False,
    "autonomous_dispatch_enabled": False,
    "worker_execution_enabled": False,
    "live_payments_enabled": False,
    "live_listings_publishing_enabled": False,
    "external_api_calls_enabled": False,
    "self_rewrite_of_code_enabled": False,
    "self_rewrite_of_registries_enabled": False,
}


def now() -> str:
    return time.strftime("%Y-%m-%dT%H:%M:%S+00:00", time.gmtime())


def load(path: Path, fallback=None):
    """Load a JSON file, return fallback if absent or broken."""
    if not path.exists():
        return fallback if fallback is not None else {}
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        return fallback if fallback is not None else {}


def write_registry(name: str, payload: dict) -> Path:
    """Write a cognitive registry with safety envelope stamped."""
    out = dict(payload)
    out.update(SAFETY)
    p = COG_REG / name
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(json.dumps(out, indent=2, default=str), encoding="utf-8")
    return p


def append_log(name: str, record: dict) -> None:
    """Append a JSONL line to a cognitive log."""
    record = dict(record)
    record.setdefault("ts", now())
    p = COG_LOG / name
    with p.open("a", encoding="utf-8") as f:
        f.write(json.dumps(record, default=str) + "\n")


__all__ = [
    "ROOT", "REG", "COG_REG", "COG_LOG", "SAFETY",
    "now", "load", "write_registry", "append_log",
]
