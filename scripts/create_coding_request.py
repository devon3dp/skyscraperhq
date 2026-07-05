import sys
import json
from pathlib import Path

ROOT = Path('/vaults/nvme0/qsb_tower_v1')
sys.path.insert(0, str(ROOT / 'src'))

from tower.coding_department import CodingDepartment

title = sys.argv[1] if len(sys.argv) > 1 else 'Build future coding worker scaffold'
request_type = sys.argv[2] if len(sys.argv) > 2 else 'code_generation'
description = ' '.join(sys.argv[3:]) if len(sys.argv) > 3 else 'Generated from Floor 5 Coding Department script.'

dept = CodingDepartment()
result = dept.create_request(title, request_type, description)
print(json.dumps(result, indent=2))
