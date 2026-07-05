#!/usr/bin/env bash
cd /vaults/nvme0/qsb_tower_v1
export PYTHONPATH=/vaults/nvme0/qsb_tower_v1/src
python3 - <<'PY2'
from tower.diagnostics_department import DiagnosticsDepartment
import json
dept = DiagnosticsDepartment()
report = dept.run_all()
print(json.dumps(report["summary"], indent=2))
print("Report written to: floors/floor_33_diagnostics_department/inspection_reports/latest_report.json")
PY2
