#!/usr/bin/env bash
cd /vaults/nvme0/qsb_tower_v1
export PYTHONPATH=/vaults/nvme0/qsb_tower_v1/src
python3 - <<'PY2'
from tower.adapter_systems import AdapterSystems
import json
dept = AdapterSystems()
print(json.dumps(dept.refresh_health(), indent=2))
PY2
