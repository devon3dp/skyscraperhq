#!/usr/bin/env bash
set -euo pipefail
cd /vaults/nvme0/qsb_tower_v1
export PYTHONPATH=/vaults/nvme0/qsb_tower_v1/src

echo "======================================================"
echo "  QSB Tower V1.3 — Active Kernel Preflight"
echo "======================================================"

python3 - <<'PY'
import json
from pathlib import Path
import urllib.request

ROOT = Path("/vaults/nvme0/qsb_tower_v1")

def load(path):
    try:
        return json.loads(Path(path).read_text())
    except Exception:
        return {}

activation = load(ROOT / "data/registries/kernel_activation_report.json")
local_model = load(ROOT / "data/registries/local_model_inference_status.json")

try:
    live = json.loads(urllib.request.urlopen("http://127.0.0.1:8765/api/live", timeout=3).read())
    building = live.get("status", {}).get("building", {})
except Exception:
    building = {}

forbidden = [
    ROOT / "penthouse/kernel.py",
    ROOT / "penthouse/qsb_kernel_4_5.py",
    ROOT / "src/tower/kernel.py",
    ROOT / "src/tower/qsb_kernel_4_5.py",
]

checks = {
    "kernel_installed": activation.get("kernel_installed") is True,
    "QSBKernelCore_instantiated": activation.get("QSBKernelCore_instantiated") is True,
    "activation_status_active_local_only": activation.get("activation_status") == "active_local_only",
    "active_kernel_source_rebased": activation.get("active_kernel_source") == "rebased_kernel",
    "worker_execution_disabled": activation.get("worker_execution_enabled") is False,
    "provider_execution_disabled": activation.get("provider_execution_enabled") is False,
    "model_inference_core_disabled": activation.get("model_inference_enabled") is False,
    "live_dispatch_disabled": activation.get("live_dispatch_enabled") is False,
    "forbidden_active_paths_absent": all(not p.exists() for p in forbidden),
}

failed = [k for k, v in checks.items() if not v]

print("Kernel installed              :", activation.get("kernel_installed"))
print("QSBKernelCore instantiated    :", activation.get("QSBKernelCore_instantiated"))
print("Activation status             :", activation.get("activation_status"))
print("Active kernel source          :", activation.get("active_kernel_source"))
print("Worker execution enabled      :", activation.get("worker_execution_enabled"))
print("Provider execution enabled    :", activation.get("provider_execution_enabled"))
print("Core model inference enabled  :", activation.get("model_inference_enabled"))
print("Local model inference enabled :", local_model.get("local_model_inference_enabled"))
print("Ollama detected               :", local_model.get("ollama_detected"))
print("Selected local model          :", local_model.get("selected_model"))
print("Dashboard kernel installed    :", building.get("kernel_installed"))
print("Forbidden paths absent        :", checks["forbidden_active_paths_absent"])

print()
if failed:
    print("FINAL VERDICT: NOT READY")
    print("Failed checks:", failed)
    raise SystemExit(1)

print("FINAL VERDICT: ACTIVE_LOCAL_ONLY_OK")
print("Kernel is active. Workers/providers/OpenClaw/autonomous dispatch remain disabled.")
PY

echo "======================================================"
