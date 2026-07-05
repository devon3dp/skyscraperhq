import sys
from pathlib import Path

ROOT = Path('/vaults/nvme0/qsb_tower_v1')
sys.path.insert(0, str(ROOT / 'src'))

from tower.model_routing_department import ModelRoutingDepartment

dept = ModelRoutingDepartment()
processed = dept.process_coding_requests()
dash = dept.dashboard()

assert dash['floor'] == 'floor_24'
assert dash['execution_enabled'] is False
assert dash['direct_provider_access'] is False
assert dash['incoming_lift'] == 'service_lift'
assert dash['outgoing_lift'] == 'model_lift'
assert len(dash['policies']) >= 4
assert len(dash['worker_slots']) >= 5

decision = dept.create_route_decision(
    source_system='test_suite',
    source_request_id=999001,
    request_type='coding',
    origin_floor='floor_05',
    title='Validation route',
    description='Test Floor 24 routing decision.'
)

assert decision['routing_floor'] == 'floor_24'
assert decision['selected_lift'] == 'model_lift'
assert decision['execution_enabled'] == 0
assert decision['status'] == 'routed_to_socket_layer'

print('MODEL ROUTING DEPARTMENT V1.1 VALIDATION PASSED')
print('Processed coding requests:', len(processed))
print('Route decisions:', dept.dashboard()['route_decisions'])
