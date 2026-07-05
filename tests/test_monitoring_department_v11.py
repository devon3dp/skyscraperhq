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
assert snap['kernel_required'] is False
assert snap['models_required'] is False
assert 'system' in snap
assert 'dashboard_heartbeat' in snap
assert 'lift_traffic' in snap
assert 'packet_flow' in snap
assert 'provider_socket_watch' in snap
assert 'diagnostics_watch' in snap

dash = dept.dashboard()
assert dash['floor'] == 'floor_34'
assert dash['execution_enabled'] is False
assert dash['latest_snapshot'].endswith('latest_snapshot.json')

print('MONITORING DEPARTMENT V1.1 VALIDATION PASSED')
print('Status:', snap['status'])
print('Dashboard online:', snap['dashboard_heartbeat'].get('online'))
print('Lift traffic total:', snap['lift_traffic'].get('total_traffic'))
print('Packet count recent:', snap['packet_flow'].get('recent_count'))
print('Diagnostics status:', snap['diagnostics_watch'].get('status'))
