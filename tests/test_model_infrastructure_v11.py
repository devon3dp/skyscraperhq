import sys
from pathlib import Path
ROOT = Path('/vaults/nvme0/qsb_tower_v1')
sys.path.insert(0, str(ROOT / 'src'))
from tower.model_infrastructure import ModelInfrastructure

infra = ModelInfrastructure()
dash = infra.dashboard()

assert dash['building_runs_without_models'] is True
assert dash['hardwired_providers'] is False
assert dash['execution_enabled'] is False
assert len(dash['sockets']) >= 7
assert len(dash['worker_slots']) >= 5
assert len(dash['request_paths']) >= 4

coding = infra.route_plan('coding')
assert coding['ok'] is True
assert coding['path']['origin_floor'] == 'floor_05'
assert coding['path']['first_hop'] == 'floor_24'
assert coding['path']['direct_provider_access'] is False
assert coding['execution_enabled'] is False

print('MODEL INFRASTRUCTURE V1.1 VALIDATION PASSED')
print('Sockets:', len(dash['sockets']))
print('Worker slots:', len(dash['worker_slots']))
print('Request paths:', len(dash['request_paths']))
