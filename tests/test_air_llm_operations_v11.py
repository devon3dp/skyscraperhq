import sys
from pathlib import Path

ROOT = Path('/vaults/nvme0/qsb_tower_v1')
sys.path.insert(0, str(ROOT / 'src'))

from tower.air_llm_operations import AirLLMOperations

dept = AirLLMOperations()
dash = dept.dashboard()

assert dash['floor'] == 'floor_23'
assert dash['providers_are_external'] is True
assert dash['execution_enabled'] is False
assert dash['hardwired_providers'] is False
assert dash['models_required'] is False
assert dash['kernel_required'] is False
assert dash['incoming_lift'] == 'model_lift'
assert dash['provider_count'] >= 6
assert dash['socket_count'] >= 6

handoff = dept.record_handoff('claude', details={'test': 'validation'})
assert handoff['provider'] == 'claude'
assert handoff['status'] == 'prepared_not_executed'
assert handoff['execution_enabled'] is False

print('AIR LLM OPERATIONS V1.1 VALIDATION PASSED')
print('Providers:', dash['provider_count'])
print('Sockets:', dash['socket_count'])
