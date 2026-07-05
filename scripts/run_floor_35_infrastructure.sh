#!/usr/bin/env bash
cd /vaults/nvme0/qsb_tower_v1
export PYTHONPATH=/vaults/nvme0/qsb_tower_v1/src
python3 - <<'PY2'
from tower.infrastructure_services import InfrastructureServices
import json
dept = InfrastructureServices()
snap = dept.collect_status()
print(json.dumps({
    "status": snap["status"],
    "critical_issues": snap["critical_issues"],
    "warnings": snap["warnings"],
    "script_checks": len(snap["script_checks"]),
    "database_files": len(snap["database_checks"]["sqlite_files"]),
    "backup_ready": snap["backup_readiness"]["ready"],
    "repair_hooks": snap["hook_checks"]["repair_count"],
    "maintenance_hooks": snap["hook_checks"]["maintenance_count"]
}, indent=2))
print("Status written to: floors/floor_35_infrastructure_services_department/service_control/latest_status.json")
PY2
