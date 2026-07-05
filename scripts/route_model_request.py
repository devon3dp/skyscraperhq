import sys
from pathlib import Path
import json
ROOT = Path('/vaults/nvme0/qsb_tower_v1')
sys.path.insert(0, str(ROOT / 'src'))
from tower.model_infrastructure import ModelInfrastructure
request_type = sys.argv[1] if len(sys.argv) > 1 else 'coding'
print(json.dumps(ModelInfrastructure().route_plan(request_type), indent=2))
