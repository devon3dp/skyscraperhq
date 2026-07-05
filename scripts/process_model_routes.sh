#!/usr/bin/env bash
cd /vaults/nvme0/qsb_tower_v1
export PYTHONPATH=/vaults/nvme0/qsb_tower_v1/src
python3 - <<'PY2'
from tower.model_routing_department import ModelRoutingDepartment
import json
dept = ModelRoutingDepartment()
processed = dept.process_coding_requests()
print(json.dumps({
    "processed": len(processed),
    "decisions": processed
}, indent=2))
PY2
