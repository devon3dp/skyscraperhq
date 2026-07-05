import sys
from pathlib import Path

ROOT = Path('/vaults/nvme0/qsb_tower_v1')
sys.path.insert(0, str(ROOT / 'src'))

from tower.adapter_systems import AdapterSystems

dept = AdapterSystems()
dash = dept.dashboard()

assert dash['floor'] == 'floor_21'
assert dash['department'] == 'Adapter Systems Department'
assert dash['execution_enabled'] is False
assert dash['hardwired_adapters'] is False
assert dash['models_required'] is False
assert dash['kernel_required'] is False
assert dash['providers_are_external'] is True
assert dash['adapter_count'] >= 8
assert dash['capability_records'] >= 8

handoff = dept.prepare_handoff('claude_adapter', source_floor='floor_24', details={'test': 'validation'})
assert handoff['adapter'] == 'claude_adapter'
assert handoff['status'] == 'prepared_not_executed'
assert handoff['execution_enabled'] is False

print('ADAPTER SYSTEMS V1.1 VALIDATION PASSED')
print('Adapters:', dash['adapter_count'])
print('Capability records:', dash['capability_records'])
