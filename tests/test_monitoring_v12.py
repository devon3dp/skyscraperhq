import sys
from pathlib import Path

ROOT = Path('/vaults/nvme0/qsb_tower_v1')
sys.path.insert(0, str(ROOT / 'src'))

from tower.monitoring_department import MonitoringDepartment

dept = MonitoringDepartment()
snap = dept.collect_snapshot()

assert snap['floor'] == 'floor_34'
assert snap['department'] == 'Monitoring Department'
assert snap['execution_enabled'] is False
assert snap['dashboard_heartbeat']['status_code'] == 'local_watch'
assert snap['dashboard_heartbeat']['counts']['floors'] == 53
assert snap['dashboard_heartbeat']['counts']['lifts'] >= 6
assert snap['diagnostics_watch']['status'] in ['healthy', 'unknown']

print('MONITORING V1.2 REPAIR VALIDATION PASSED')
print('Monitoring status:', snap['status'])
print('Dashboard online:', snap['dashboard_heartbeat']['online'])
print('PID running:', snap['dashboard_heartbeat']['pid_running'])
print('Registry OK:', snap['dashboard_heartbeat']['registry_ok'])
print('Floors:', snap['dashboard_heartbeat']['counts']['floors'])
print('Lifts:', snap['dashboard_heartbeat']['counts']['lifts'])
