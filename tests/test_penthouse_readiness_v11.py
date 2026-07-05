import sys
from pathlib import Path

ROOT = Path('/vaults/nvme0/qsb_tower_v1')
sys.path.insert(0, str(ROOT / 'src'))

from tower.penthouse_readiness import PenthouseReadiness

dept = PenthouseReadiness()
report = dept.run_acceptance()
summary = report['summary']

assert summary['penthouse'] == 'penthouse'
assert summary['reserved_for'] == 'Future QSB Kernel 4.5 Installation'
assert summary['kernel_installed'] is False
assert summary['kernel_logic_present'] is False
assert summary['execution_enabled'] is False
assert summary['checks_run'] >= 15
assert summary['critical_failures'] == 0, report
assert summary['readiness_status'] == 'ready_for_future_qsb_kernel_4_5', report

dash = dept.dashboard()
assert dash['penthouse'] == 'penthouse'
assert dash['kernel_installed'] is False
assert dash['connection_ports'] >= 8

print('PENTHOUSE READINESS V1.1 VALIDATION PASSED')
print('Readiness:', summary['readiness_status'])
print('Checks run:', summary['checks_run'])
print('Critical failures:', summary['critical_failures'])
print('Warnings:', summary['warnings'])
print('Kernel installed:', summary['kernel_installed'])
