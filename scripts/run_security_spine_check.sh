#!/usr/bin/env bash
cd /vaults/nvme0/qsb_tower_v1
export PYTHONPATH=/vaults/nvme0/qsb_tower_v1/src
python3 - <<'PY2'
from tower.security_spine import SecuritySpine
import json
spine = SecuritySpine()
report = spine.run_security_spine_check()
print(json.dumps(report["summary"], indent=2))
print("Report written to: floors/floor_32_compliance_department/compliance_reports/latest_security_spine_report.json")
PY2
