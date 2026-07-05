import sys
from pathlib import Path

ROOT = Path('/vaults/nvme0/qsb_tower_v1')
sys.path.insert(0, str(ROOT / 'src'))

from tower.sandbox_operations import SandboxOperations

sb = SandboxOperations()
r = sb.run_all()

assert r['floor'] == 'floor_38'
assert r['sandbox_only'] is True
assert r['dry_run_only'] is True
assert r['kernel_installed'] is False
assert r['kernel_logic_present'] is False
assert r['execution_enabled'] is False
assert r['worker_execution_enabled'] is False
assert r['provider_execution_enabled'] is False
assert r['model_inference_enabled'] is False
assert r['shell_execution_enabled'] is False
assert r['filesystem_write_enabled'] is False
assert r['network_enabled'] is False
assert r['real_process_spawn_enabled'] is False
assert r['envelope_count'] >= 5
assert r['contained_envelopes'] == r['envelope_count'], r
assert r['rejected_envelopes'] == 0, r
assert r['critical_failures'] == 0, r
assert r['warnings'] == 0, r

print('FLOOR 38 SANDBOX OPERATIONS V1.1 VALIDATION PASSED')
print('Status:', r['status'])
print('Envelopes:', r['envelope_count'])
print('Contained:', r['contained_envelopes'])
print('Rejected:', r['rejected_envelopes'])
print('Critical failures:', r['critical_failures'])
print('Warnings:', r['warnings'])
print('Recommendation:', r['activation_recommendation'])
