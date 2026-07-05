import sys
from pathlib import Path

ROOT = Path('/vaults/nvme0/qsb_tower_v1')
sys.path.insert(0, str(ROOT / 'src'))

from tower.infrastructure_services import InfrastructureServices

dept = InfrastructureServices()
snap = dept.collect_status()

assert snap['floor'] == 'floor_35'
assert snap['department'] == 'Infrastructure Services Department'
assert snap['execution_enabled'] is False
assert snap['kernel_required'] is False
assert snap['models_required'] is False
assert len(snap['script_checks']) >= 5
assert len(snap['database_checks']['sqlite_files']) >= 1
assert snap['hook_checks']['repair_count'] >= 4
assert snap['hook_checks']['maintenance_count'] >= 4

dash = dept.dashboard()
assert dash['floor'] == 'floor_35'
assert dash['execution_enabled'] is False
assert dash['latest_status'].endswith('latest_status.json')

print('INFRASTRUCTURE SERVICES V1.1 VALIDATION PASSED')
print('Status:', snap['status'])
print('Critical issues:', snap['critical_issues'])
print('Warnings:', snap['warnings'])
print('Database files:', len(snap['database_checks']['sqlite_files']))
print('Backup ready:', snap['backup_readiness']['ready'])
