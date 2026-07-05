import sys
import importlib.util
import py_compile
from pathlib import Path

ROOT = Path('/vaults/nvme0/qsb_tower_v1')
server = ROOT / 'src' / 'dashboard' / 'server.py'

py_compile.compile(str(server), doraise=True)

spec = importlib.util.spec_from_file_location('dashboard_server_floor25', str(server))
mod = importlib.util.module_from_spec(spec)
spec.loader.exec_module(mod)

assert 'agent_coordination' in mod.live_payload()
payload = mod.live_payload()
agent = payload['agent_coordination']

assert agent['floor'] == 'floor_25'
assert agent['worker_execution_enabled'] is False
assert agent['provider_execution_enabled'] is False
assert agent['live_dispatch_enabled'] is False
assert agent['critical_failures'] == 0
assert 'id="agentGrid"' in mod.HTML
assert 'Floor 25 Worker Recruitment' in mod.HTML

print('DASHBOARD FLOOR 25 V1.1 VALIDATION PASSED')
print('Agent status:', agent['status'])
print('Candidates:', agent['candidate_workers'])
print('Worker slots:', agent['worker_slots'])
print('Live dispatch:', agent['live_dispatch_enabled'])
