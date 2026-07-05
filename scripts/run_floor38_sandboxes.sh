#!/usr/bin/env bash
cd /vaults/nvme0/qsb_tower_v1
export PYTHONPATH=/vaults/nvme0/qsb_tower_v1/src
python3 - <<'PY2'
from tower.sandbox_operations import SandboxOperations
import json
r = SandboxOperations().run_all()
print(json.dumps({
    "floor": r["floor"],
    "department": r["department"],
    "status": r["status"],
    "sandbox_only": r["sandbox_only"],
    "dry_run_only": r["dry_run_only"],
    "envelope_count": r["envelope_count"],
    "contained_envelopes": r["contained_envelopes"],
    "rejected_envelopes": r["rejected_envelopes"],
    "critical_failures": r["critical_failures"],
    "warnings": r["warnings"],
    "worker_execution_enabled": r["worker_execution_enabled"],
    "provider_execution_enabled": r["provider_execution_enabled"],
    "model_inference_enabled": r["model_inference_enabled"],
    "network_enabled": r["network_enabled"],
    "activation_recommendation": r["activation_recommendation"]
}, indent=2))
PY2
