#!/usr/bin/env bash
cd /vaults/nvme0/qsb_tower_v1
export PYTHONPATH=/vaults/nvme0/qsb_tower_v1/src
python3 - <<'PY2'
from tower.penthouse_readiness import PenthouseReadiness
import json
dept = PenthouseReadiness()
report = dept.run_acceptance()
print(json.dumps(report["summary"], indent=2))
print("Report written to: penthouse/kernel_occupancy_acceptance/latest_acceptance_report.json")
PY2
