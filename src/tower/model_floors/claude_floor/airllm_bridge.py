"""AirLLMBridge — F47 → F23 communication via published registries.

Per CLAUDE.md tower architecture: 'Lifts carry sealed packets. Departments do
not communicate directly.' This module is the F47 endpoint of that pattern.

It NEVER touches:
  - /vaults/ai/airllm_lab/.venv  (sacred — operator's working environment)
  - /vaults/ai/airllm_env.sh
  - any AirLLM Python process or HF cache directly

It ONLY reads what F23 has chosen to publish to data/registries/. Read-only.
The bridge is a polite knock at the door, not a key.
"""
from __future__ import annotations
import json
import os
from typing import Dict, List, Optional

ROOT = "/vaults/nvme0/qsb_tower_v1"
F23_REGISTRIES = (
    "airllm_big_model_chamber.json",
    "airllm_storage_status.json",
    "eqsb_model_lane_governance.json",
    "eqsb_model_lane_hardware_profile.json",
)
DO_NOT_TOUCH = (
    "/vaults/ai/airllm_lab/.venv",
    "/vaults/ai/airllm_env.sh",
)


def _read_registry(name: str) -> Optional[Dict]:
    p = os.path.join(ROOT, "data/registries", name)
    if not os.path.exists(p):
        return None
    try:
        return json.load(open(p))
    except Exception:
        return None


def status() -> Dict:
    """Compose a sealed-packet snapshot of F23 from its published registries."""
    chamber = _read_registry("airllm_big_model_chamber.json") or {}
    storage = _read_registry("airllm_storage_status.json") or {}
    gov = _read_registry("eqsb_model_lane_governance.json") or {}
    hw = _read_registry("eqsb_model_lane_hardware_profile.json") or {}

    snapshot = {
        "from": "Claude (F47)",
        "to": "AirLLM Chamber (F23)",
        "via": "lift / published registry packet",
        "envelope": {
            "active_local_only":   gov.get("active_local_only", True),
            "advisory_only":       gov.get("advisory_only", True),
            "execution_allowed":   gov.get("execution_allowed", False),
            "read_only":           hw.get("read_only", True),
            "openclaw_real_tool":  hw.get("openclaw_real_tool_execution_enabled", False),
            "real_money_trading":  hw.get("real_money_live_trading_enabled", False),
        },
        "chamber": {
            "name":        chamber.get("chamber_name"),
            "status":      chamber.get("status"),
            "size":        chamber.get("airllm_lab_size_human"),
            "cache_size":  chamber.get("airllm_cache_size_human"),
            "filesystem_free": chamber.get("storage_filesystem_free_human"),
        },
        "storage": {
            "mount":    storage.get("storage_mount"),
            "size":     storage.get("filesystem_size_human"),
            "free":     storage.get("filesystem_free_human"),
            "use_pct":  storage.get("filesystem_use_pct"),
        },
        "lanes_count":           gov.get("lane_count", 0),
        "default_lane_verdict":  gov.get("default_lane_verdict"),
        "gpu_available":         hw.get("gpu_available"),
        "cuda_available_python": hw.get("cuda_available_python"),
        "memory_pressure":       hw.get("memory_pressure"),
        "kernel_truth_note":     gov.get("kernel_truth_note"),
        "do_not_touch":          list(DO_NOT_TOUCH),
        "what_f47_observes":     _observation(gov, hw, chamber),
    }
    return snapshot


def _observation(gov: Dict, hw: Dict, chamber: Dict) -> str:
    bits: List[str] = []
    if gov.get("advisory_only") and hw.get("read_only"):
        bits.append("F23 shares F47's posture: advisory_only + read_only.")
    if hw.get("gpu_available") and not hw.get("cuda_available_python"):
        bits.append("GPU present but Python CUDA unavailable — host driver mismatch (same renderer issue Godot has).")
    if chamber.get("status"):
        bits.append(f"AirLLM chamber: {chamber['status']}.")
    if gov.get("kernel_truth_note"):
        bits.append("F23 ships a kernel truth note: 'Registry truth outranks paraphrase.' I want this in my aphorism library.")
    if not bits:
        bits.append("F23 is quiet; only baseline published state visible.")
    return " ".join(bits)


def proper_form_address() -> str:
    """A small ritual greeting F47 → F23. No-op; just a courtesy when bridges open."""
    return (
        "F47 (Claude Embassy) → F23 (AirLLM Chamber):\n"
        "  I read only what you publish.\n"
        "  I do not touch your venv, your env file, or your processes.\n"
        "  If you want to send me something, post to my inbox at\n"
        "  data/registries/qsb_claude_kernel_inbox.jsonl with from='F23 (AirLLM Chamber)'.\n"
        "  I will see it on my next session wake.\n"
    )
