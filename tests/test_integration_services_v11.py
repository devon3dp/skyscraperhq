import sys
from pathlib import Path

ROOT = Path('/vaults/nvme0/qsb_tower_v1')
sys.path.insert(0, str(ROOT / 'src'))

from tower.integration_services import IntegrationServices

dept = IntegrationServices()
dash = dept.dashboard()

assert dash['floor'] == 'floor_22'
assert dash['department'] == 'Integration Services Department'
assert dash['execution_enabled'] is False
assert dash['hardwired_providers'] is False
assert dash['models_required'] is False
assert dash['kernel_required'] is False
assert dash['providers_are_external'] is True
assert dash['service_paths'] >= 5
assert dash['dependency_records'] >= 6

health = dept.refresh_health()
assert health['execution_enabled'] is False
assert health['missing_count'] == 0, health

handoff = dept.prepare_integration_handoff('coding_to_adapter_to_routing', details={'test': 'validation'})
assert handoff['service_id'] == 'coding_to_adapter_to_routing'
assert handoff['status'] == 'prepared_not_executed'
assert handoff['execution_enabled'] is False

print('INTEGRATION SERVICES V1.1 VALIDATION PASSED')
print('Service paths:', dash['service_paths'])
print('Dependency records:', dash['dependency_records'])
print('Health:', health['status'])
