#!/usr/bin/env bash
cd /vaults/nvme0/qsb_tower_v1
export PYTHONPATH=/vaults/nvme0/qsb_tower_v1/src
python3 - <<'PY2'
from tower.monitoring_department import MonitoringDepartment
import json
dept = MonitoringDepartment()
snapshot = dept.collect_snapshot()
print(json.dumps({
    "status": snapshot["status"],
    "dashboard_online": snapshot["dashboard_heartbeat"].get("online"),
    "dashboard_pid": snapshot["service_uptime"].get("pid"),
    "uptime_seconds": snapshot["service_uptime"].get("uptime_seconds"),
    "cpu_percent": snapshot["system"].get("cpu_percent"),
    "memory_percent": snapshot["system"].get("memory_percent"),
    "tower_disk_percent": snapshot["system"].get("tower_disk_percent"),
    "tower_free_gb": snapshot["system"].get("tower_free_gb"),
    "lift_traffic_total": snapshot["lift_traffic"].get("total_traffic"),
    "packet_count_recent": snapshot["packet_flow"].get("recent_count"),
    "diagnostics_status": snapshot["diagnostics_watch"].get("status"),
    "critical_issues": snapshot["critical_issues"],
    "warnings": snapshot["warnings"]
}, indent=2))
print("Snapshot written to: floors/floor_34_monitoring_department/live_snapshots/latest_snapshot.json")
PY2
