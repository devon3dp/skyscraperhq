import sys
from pathlib import Path

ROOT = Path('/vaults/nvme0/qsb_tower_v1')
sys.path.insert(0, str(ROOT / 'src'))

from tower.coding_department import CodingDepartment

dept = CodingDepartment()
dash = dept.dashboard()

assert dash['floor'] == 'floor_05'
assert dash['direct_provider_access'] is False
assert dash['routes_through'] == 'floor_24'
assert dash['models_required'] is False
assert dash['kernel_required'] is False
assert len(dash['workspaces']) >= 3
assert len(dash['worker_slots']) >= 5

req = dept.create_request(
    'Validation coding request',
    'code_generation',
    'Test sealed path from Floor 5 to Floor 24.',
    send_lift=True
)

assert req['origin_floor'] == 'floor_05'
assert req['routing_floor'] == 'floor_24'
assert req['first_lift'] == 'service_lift'
assert req['status'] == 'queued_for_routing'

print('CODING DEPARTMENT V1.1 VALIDATION PASSED')
print('Requests:', dept.dashboard()['requests'])
print('Patch queue:', dept.dashboard()['patch_queue'])
print('Review queue:', dept.dashboard()['review_queue'])
print('Test queue:', dept.dashboard()['test_queue'])
