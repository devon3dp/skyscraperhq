#!/usr/bin/env bash
cd /vaults/nvme0/qsb_tower_v1
export PYTHONPATH=/vaults/nvme0/qsb_tower_v1/src
python3 - <<'PY2'
from tower.air_llm_operations import AirLLMOperations
import json
dept = AirLLMOperations()
print(json.dumps(dept.refresh_provider_health(), indent=2))
PY2
