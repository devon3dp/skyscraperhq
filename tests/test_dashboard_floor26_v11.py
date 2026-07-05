import sys
import importlib.util
import py_compile
from pathlib import Path

ROOT = Path('/vaults/nvme0/qsb_tower_v1')
server = ROOT / 'src/dashboard/server.py'

py_compile.compile(str(server), doraise=True)

spec = importlib.util.spec_from_file_location('dashboard_server_floor26', str(server))
mod = importlib.util.module_from_spec(spec)
spec.loader.exec_module(mod)

payload = mod.live_payload()
assert 'model_evaluation' in payload
me = payload['model_evaluation']

assert me['floor'] == 'floor_26'
assert me['worker_execution_enabled'] is False
assert me['provider_execution_enabled'] is False
assert me['model_inference_enabled'] is False
assert me['activation_recommendation'] == 'do_not_activate_workers_or_providers'
assert me['critical_failures'] == 0
assert 'id="modelEvalGrid"' in mod.HTML
assert 'Floor 26 Model Evaluation' in mod.HTML

print('DASHBOARD FLOOR 26 V1.1 VALIDATION PASSED')
print('Status:', me['status'])
print('Candidates:', me['candidate_count'])
print('Average score:', me['average_score'])
print('Model inference:', me['model_inference_enabled'])
print('Recommendation:', me['activation_recommendation'])
