import sys
from pathlib import Path

ROOT = Path('/vaults/nvme0/qsb_tower_v1')
sys.path.insert(0, str(ROOT / 'src'))

from tower.security_spine import SecuritySpine

spine = SecuritySpine()
report = spine.run_security_spine_check()
summary = report['summary']

assert summary['spine'] == 'security_spine'
assert summary['execution_enabled'] is False
assert summary['enforcement_enabled'] is False
assert summary['checks_run'] >= 20
assert summary['critical_failures'] == 0, report
assert summary['status'] in ['healthy', 'degraded']

dash = spine.dashboard()
assert dash['spine'] == 'security_spine'
assert dash['security_gates'] >= 4
assert dash['guardian_rules'] >= 5
assert dash['permission_roles'] >= 4
assert dash['lift_permissions'] >= 9
assert dash['compliance_rules'] >= 5

print('SECURITY SPINE V1.1 VALIDATION PASSED')
print('Status:', summary['status'])
print('Checks run:', summary['checks_run'])
print('Critical failures:', summary['critical_failures'])
print('Warnings:', summary['warnings'])
print('Enforcement enabled:', summary['enforcement_enabled'])
