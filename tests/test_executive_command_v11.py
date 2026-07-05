import sys
from pathlib import Path

ROOT = Path('/vaults/nvme0/qsb_tower_v1')
sys.path.insert(0, str(ROOT / 'src'))

from tower.executive_command import ExecutiveCommand

spine = ExecutiveCommand()
report = spine.run_executive_command_check()
summary = report['summary']

assert summary['spine'] == 'executive_command_spine'
assert summary['kernel_installed'] is False
assert summary['kernel_logic_present'] is False
assert summary['execution_enabled'] is False
assert summary['command_execution_enabled'] is False
assert summary['checks_run'] >= 25
assert summary['critical_failures'] == 0, report
assert summary['status'] in ['healthy', 'degraded']

dash = spine.dashboard()
assert dash['spine'] == 'executive_command_spine'
assert dash['executive_floors'] == 8
assert dash['command_channels'] >= 8
assert dash['governance_rules'] >= 6
assert dash['roadmap_items'] >= 4
assert dash['tower_command_handoff']['kernel_installed'] is False

print('EXECUTIVE COMMAND SPINE V1.1 VALIDATION PASSED')
print('Status:', summary['status'])
print('Checks run:', summary['checks_run'])
print('Critical failures:', summary['critical_failures'])
print('Warnings:', summary['warnings'])
print('Next recommended phase:', summary['next_recommended_phase'])
