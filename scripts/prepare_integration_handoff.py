import sys
import json
from pathlib import Path

ROOT = Path('/vaults/nvme0/qsb_tower_v1')
sys.path.insert(0, str(ROOT / 'src'))

from tower.integration_services import IntegrationServices

service_id = sys.argv[1] if len(sys.argv) > 1 else 'coding_to_adapter_to_routing'
dept = IntegrationServices()
print(json.dumps(dept.prepare_integration_handoff(service_id, details={'manual_test': True}), indent=2))
