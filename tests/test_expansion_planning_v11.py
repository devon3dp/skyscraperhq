import sys
from pathlib import Path

ROOT = Path('/vaults/nvme0/qsb_tower_v1')
sys.path.insert(0, str(ROOT / 'src'))

from tower.expansion_planning import ExpansionPlanning

dept = ExpansionPlanning()
report = dept.run_expansion_readiness()
summary = report['summary']

assert summary['floor'] == 'floor_36'
assert summary['department'] == 'Expansion Planning Department'
assert summary['execution_enabled'] is False
assert summary['activation_execution_enabled'] is False
assert summary['managed_vacant_floors'] == 5
assert summary['future_department_blueprints'] >= 5
assert summary['activation_hooks'] >= 5
assert summary['checks_run'] >= 25
assert summary['critical_failures'] == 0, report

plan = dept.prepare_activation_plan('floor_41')
assert plan['floor_id'] == 'floor_41'
assert plan['status'] == 'prepared_not_executed'
assert plan['execution_enabled'] is False

dash = dept.dashboard()
assert dash['floor'] == 'floor_36'
assert dash['managed_vacant_floors'] == 5
assert len(dash['vacant_floors']) == 5

print('EXPANSION PLANNING V1.1 VALIDATION PASSED')
print('Status:', summary['status'])
print('Managed vacant floors:', summary['managed_vacant_floors'])
print('Checks run:', summary['checks_run'])
print('Critical failures:', summary['critical_failures'])
print('Warnings:', summary['warnings'])
