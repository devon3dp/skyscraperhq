import sys, importlib.util, py_compile
from pathlib import Path

ROOT = Path('/vaults/nvme0/qsb_tower_v1')
server = ROOT / 'src/dashboard/server.py'

py_compile.compile(str(server), doraise=True)

spec = importlib.util.spec_from_file_location('dashboard_server_floor38', str(server))
mod = importlib.util.module_from_spec(spec)
spec.loader.exec_module(mod)

payload = mod.live_payload()
assert 'sandbox_operations' in payload, 'sandbox_operations missing from live_payload'
sb = payload['sandbox_operations']

assert sb['floor'] == 'floor_38'
assert sb['sandbox_only'] is True
assert sb['dry_run_only'] is True
assert sb['worker_execution_enabled'] is False
assert sb['provider_execution_enabled'] is False
assert sb['model_inference_enabled'] is False
assert sb['network_enabled'] is False
assert sb['critical_failures'] == 0

print('DASHBOARD FLOOR 38 V1.1 VALIDATION PASSED')
print('Status:', sb['status'])
print('Envelopes:', sb['envelope_count'])
print('Contained:', sb['contained_envelopes'])
print('Rejected:', sb['rejected_envelopes'])
print('Network:', sb['network_enabled'])
print('HTML panel present:', 'id="sandboxGrid"' in mod.HTML)
