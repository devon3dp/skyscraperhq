import sys
import json
from pathlib import Path
ROOT = Path('/vaults/nvme0/qsb_tower_v1')
sys.path.insert(0, str(ROOT / 'src'))
from tower.local_model_operations import LocalModelOperations
dept = LocalModelOperations()
print(json.dumps(dept.recommend_bindings(), indent=2))
