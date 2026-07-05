#!/usr/bin/env bash
cd /vaults/nvme0/qsb_tower_v1
export PYTHONPATH=/vaults/nvme0/qsb_tower_v1/src
python3 - <<'PY2'
from tower.model_evaluation_department import ModelEvaluationDepartment
import json
report = ModelEvaluationDepartment().run_evaluation()
print(json.dumps({
    "floor": report["floor"],
    "department": report["department"],
    "status": report["status"],
    "evaluation_mode": report["evaluation_mode"],
    "candidate_count": report["candidate_count"],
    "average_score": report["average_score"],
    "critical_failures": report["critical_failures"],
    "warnings": report["warnings"],
    "worker_execution_enabled": report["worker_execution_enabled"],
    "provider_execution_enabled": report["provider_execution_enabled"],
    "model_inference_enabled": report["model_inference_enabled"],
    "activation_recommendation": report["activation_recommendation"]
}, indent=2))
PY2
