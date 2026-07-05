#!/usr/bin/env bash
cd /vaults/nvme0/qsb_tower_v1
export PYTHONPATH=/vaults/nvme0/qsb_tower_v1/src
python3 - <<'PY2'
from tower.local_model_operations import LocalModelOperations
import json
dept = LocalModelOperations()
print(json.dumps(dept.detect_ollama(), indent=2))
print(json.dumps({
    "recommendations": dept.recommend_bindings()
}, indent=2))
PY2
