import sys
from pathlib import Path

ROOT = Path('/vaults/nvme0/qsb_tower_v1')
sys.path.insert(0, str(ROOT / 'src'))

from tower.diagnostics_department import DiagnosticsDepartment

dept = DiagnosticsDepartment()
report = dept.run_all()
summary = report['summary']

assert summary['floor'] == 'floor_33'
assert summary['department'] == 'Diagnostics Department'
assert summary['execution_enabled'] is False
assert summary['kernel_required'] is False
assert summary['models_required'] is False
assert summary['checks_run'] >= 25
assert summary['critical_failures'] == 0, report

dash = dept.dashboard()
assert dash['floor'] == 'floor_33'
assert dash['execution_enabled'] is False

print('DIAGNOSTICS DEPARTMENT V1.1 VALIDATION PASSED')
print('Status:', summary['status'])
print('Checks run:', summary['checks_run'])
print('Critical failures:', summary['critical_failures'])
print('Warning failures:', summary['warning_failures'])
