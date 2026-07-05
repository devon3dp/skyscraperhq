import sys
import json
from pathlib import Path

ROOT = Path('/vaults/nvme0/qsb_tower_v1')
sys.path.insert(0, str(ROOT / 'src'))

from tower.air_llm_operations import AirLLMOperations

provider = sys.argv[1] if len(sys.argv) > 1 else 'claude'
dept = AirLLMOperations()
print(json.dumps(dept.record_handoff(provider, details={'manual_test': True}), indent=2))
