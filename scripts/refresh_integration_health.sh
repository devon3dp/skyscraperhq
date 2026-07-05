#!/usr/bin/env bash
cd /vaults/nvme0/qsb_tower_v1
export PYTHONPATH=/vaults/nvme0/qsb_tower_v1/src
python3 - <<'PY2'
from tower.integration_services import IntegrationServices
import json
dept = IntegrationServices()
print(json.dumps(dept.refresh_health(), indent=2))
PY2
