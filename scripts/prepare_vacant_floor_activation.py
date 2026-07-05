import sys
import json
from pathlib import Path

ROOT = Path('/vaults/nvme0/qsb_tower_v1')
sys.path.insert(0, str(ROOT / 'src'))

from tower.expansion_planning import ExpansionPlanning

floor_id = sys.argv[1] if len(sys.argv) > 1 else 'floor_41'
blueprint_id = sys.argv[2] if len(sys.argv) > 2 else None

dept = ExpansionPlanning()
print(json.dumps(dept.prepare_activation_plan(floor_id, blueprint_id), indent=2))
