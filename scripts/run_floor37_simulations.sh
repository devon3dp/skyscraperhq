#!/usr/bin/env bash
cd /vaults/nvme0/qsb_tower_v1
export PYTHONPATH=/vaults/nvme0/qsb_tower_v1/src
python3 - <<'PY2'
from tower.simulation_labs import SimulationLabs
import json
report = SimulationLabs().run_all()
print(json.dumps({
    "floor": report["floor"],
    "department": report["department"],
    "status": report["status"],
    "simulation_only": report["simulation_only"],
    "dry_run_only": report["dry_run_only"],
    "scenario_count": report["scenario_count"],
    "passed_scenarios": report["passed_scenarios"],
    "failed_scenarios": report["failed_scenarios"],
    "packets_simulated": report["packets_simulated"],
    "critical_failures": report["critical_failures"],
    "warnings": report["warnings"],
    "worker_execution_enabled": report["worker_execution_enabled"],
    "provider_execution_enabled": report["provider_execution_enabled"],
    "model_inference_enabled": report["model_inference_enabled"],
    "activation_recommendation": report["activation_recommendation"]
}, indent=2))
PY2
