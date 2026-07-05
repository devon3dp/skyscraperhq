import sys
import json
from pathlib import Path

ROOT = Path('/vaults/nvme0/qsb_tower_v1')
sys.path.insert(0, str(ROOT / 'src'))

from tower.adapter_systems import AdapterSystems

adapter = sys.argv[1] if len(sys.argv) > 1 else 'claude_adapter'
dept = AdapterSystems()
print(json.dumps(dept.prepare_handoff(adapter, details={'manual_test': True}), indent=2))
