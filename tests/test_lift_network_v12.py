import sys
from pathlib import Path

ROOT = Path('/vaults/nvme0/qsb_tower_v1')
sys.path.insert(0, str(ROOT / 'src'))

from tower.lifts import LiftNetwork

lift = LiftNetwork()

a = lift.send('floor_24', 'floor_27', 'model_lift', 5)
assert a['lift'] == 'model_lift', a

b = lift.send('floor_05', 'floor_24', 'service_lift', 5)
assert b['lift'] == 'service_lift', b

c = lift.send('ground', 'floor_01', 'main', 5)
assert c['lift'] in ['main_low_rise', 'service_lift', 'emergency_stairwell'], c

print('LIFT NETWORK V1.2 VALIDATION PASSED')
print('Model lift route:', a)
print('Service lift route:', b)
print('Main route:', c)
