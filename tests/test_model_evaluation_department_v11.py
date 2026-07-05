import sys
from pathlib import Path

ROOT = Path('/vaults/nvme0/qsb_tower_v1')
sys.path.insert(0, str(ROOT / 'src'))

from tower.model_evaluation_department import ModelEvaluationDepartment

me = ModelEvaluationDepartment()
report = me.run_evaluation()

assert report['floor'] == 'floor_26'
assert report['kernel_installed'] is False
assert report['kernel_logic_present'] is False
assert report['execution_enabled'] is False
assert report['worker_execution_enabled'] is False
assert report['provider_execution_enabled'] is False
assert report['model_inference_enabled'] is False
assert report['autonomous_workers_enabled'] is False
assert report['live_dispatch_enabled'] is False
assert report['candidate_count'] >= 5
assert report['average_score'] > 0
assert report['critical_failures'] == 0, report
assert report['activation_recommendation'] == 'do_not_activate_workers_or_providers'

dash = me.dashboard()
assert dash['status'] in ['healthy', 'degraded']
assert dash['candidate_count'] >= 5
assert dash['worker_execution_enabled'] is False
assert dash['provider_execution_enabled'] is False
assert dash['model_inference_enabled'] is False

ids = [x['candidate_id'] for x in dash['evaluated_candidates']]
assert 'claude_code' in ids
assert 'openclaw' in ids

print('FLOOR 26 MODEL EVALUATION V1.1 VALIDATION PASSED')
print('Status:', report['status'])
print('Candidates:', report['candidate_count'])
print('Average score:', report['average_score'])
print('Critical failures:', report['critical_failures'])
print('Warnings:', report['warnings'])
print('Activation recommendation:', report['activation_recommendation'])
