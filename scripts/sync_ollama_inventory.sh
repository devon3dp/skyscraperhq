#!/usr/bin/env bash
cd /vaults/nvme0/qsb_tower_v1
export PYTHONPATH=/vaults/nvme0/qsb_tower_v1/src
python3 - <<'PY2'
from tower.model_infrastructure import ModelInfrastructure
import json
print(json.dumps(ModelInfrastructure().detect_ollama(), indent=2))
PY2
