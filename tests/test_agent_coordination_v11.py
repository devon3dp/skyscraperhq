import sys
from pathlib import Path

ROOT = Path('/vaults/nvme0/qsb_tower_v1')
sys.path.insert(0, str(ROOT / 'src'))

from tower.agent_coordination import AgentCoordination

ac = AgentCoordination()
report = ac.run_prechecks()

assert report['floor'] == 'floor_25'
assert report['kernel_installed'] is False
assert report['kernel_logic_present'] is False
assert report['execution_enabled'] is False
assert report['worker_execution_enabled'] is False
assert report['provider_execution_enabled'] is False
assert report['autonomous_workers_enabled'] is False
assert report['candidate_registration_enabled'] is True
assert report['live_dispatch_enabled'] is False
assert report['candidate_workers'] >= 5
assert report['worker_slots'] >= 6
assert report['onboarding_queue'] >= 3
assert report['critical_failures'] == 0, report

dash = ac.dashboard()
assert dash['status'] in ['healthy', 'degraded']
assert dash['worker_execution_enabled'] is False
assert dash['provider_execution_enabled'] is False
assert 'claude_code' in dash['known_candidates']
assert 'openclaw' in dash['known_candidates']

print('FLOOR 25 WORKER RECRUITMENT V1.1 VALIDATION PASSED')
print('Status:', report['status'])
print('Checks run:', report['checks_run'])
print('Passed:', report['passed'])
print('Critical failures:', report['critical_failures'])
print('Warnings:', report['warnings'])
print('Candidates:', report['candidate_workers'])
print('Worker slots:', report['worker_slots'])
print('Next:', report['next_recommended_phase'])
