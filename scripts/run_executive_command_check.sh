#!/usr/bin/env bash
cd /vaults/nvme0/qsb_tower_v1
export PYTHONPATH=/vaults/nvme0/qsb_tower_v1/src
python3 - <<'PY2'
from tower.executive_command import ExecutiveCommand
import json
spine = ExecutiveCommand()
report = spine.run_executive_command_check()
print(json.dumps(report["summary"], indent=2))
print("Report written to: floors/floor_53_tower_command_department/tower_command_records/latest_executive_command_report.json")
PY2
