#!/usr/bin/env bash
cd /vaults/nvme0/qsb_tower_v1
export PYTHONPATH=/vaults/nvme0/qsb_tower_v1/src
python3 - <<'PY2'
from tower.expansion_planning import ExpansionPlanning
import json
dept = ExpansionPlanning()
report = dept.run_expansion_readiness()
print(json.dumps(report["summary"], indent=2))
print("Report written to: floors/floor_36_expansion_planning_department/capacity_reports/latest_expansion_readiness_report.json")
PY2
