import sys
from pathlib import Path

ROOT = Path('/vaults/nvme0/qsb_tower_v1')
sys.path.insert(0, str(ROOT / 'src'))

from tower.foundation_completeness import FoundationCompleteness

fc = FoundationCompleteness()
report = fc.run()

assert report['kernel_installed'] is False
assert report['kernel_logic_present'] is False
assert report['worker_execution_enabled'] is False
assert report['provider_execution_enabled'] is False
assert report['checks_run'] >= 60, report
assert report['critical_failures'] == 0, report

dash = fc.dashboard()
assert dash['status'] in ['healthy', 'degraded']
assert dash['critical_failures'] == 0

print('FOUNDATION COMPLETENESS V1.3A VALIDATION PASSED')
print('Status:', report['status'])
print('Checks run:', report['checks_run'])
print('Passed:', report['passed'])
print('Critical failures:', report['critical_failures'])
print('Warnings:', report['warnings'])
print('Next:', report['next_recommended_phase'])
