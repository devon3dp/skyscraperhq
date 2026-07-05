import sys
from pathlib import Path

ROOT = Path('/vaults/nvme0/qsb_tower_v1')
sys.path.insert(0, str(ROOT / 'src'))

from tower.local_model_operations import LocalModelOperations

dept = LocalModelOperations()
dept.sync_from_existing_discovery()
dash = dept.dashboard()

assert dash['floor'] == 'floor_27'
assert dash['models_required'] is False
assert dash['kernel_required'] is False
assert dash['execution_enabled'] is False
assert dash['hardwired_models'] is False
assert dash['incoming_lift'] == 'model_lift'
assert isinstance(dash['catalog'], list)
assert isinstance(dash['recommendations'], list)

print('LOCAL MODEL OPERATIONS V1.1 VALIDATION PASSED')
print('Detected models:', dash['detected_models'])
print('Role summary:', dash['role_summary'])
print('Recommendations:', len(dash['recommendations']))
