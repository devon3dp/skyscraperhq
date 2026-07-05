from pathlib import Path
from datetime import datetime, timezone
import py_compile

ROOT = Path("/vaults/nvme0/qsb_tower_v1")
P = ROOT / "scripts/final_kernel_preflight.sh"

ts = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
backup = P.with_suffix(f".sh.backup_before_dormant_wording_fix_{ts}")
text = P.read_text(encoding="utf-8")
backup.write_text(text, encoding="utf-8")

print("Backup:", backup)

# Keep this conservative: append a clear dormant-state block near the end if not present.
marker = "DORMANT KERNEL IMPORT STATE"
if marker not in text:
    insert = r'''

echo
echo "  DORMANT KERNEL IMPORT STATE"
python3 - <<'PY'
import json
from pathlib import Path

ROOT = Path("/vaults/nvme0/qsb_tower_v1")
manifest = ROOT / "data/registries/dormant_kernel_import_manifest.json"

if not manifest.exists():
    print("    dormant_kernel_imported       : False")
    print("    dormant_kernel_logic_present  : False")
    print("    activation_enabled            : False")
else:
    d = json.loads(manifest.read_text(encoding="utf-8"))
    safety = d.get("safety_flags", {})
    print("    dormant_kernel_imported       : True")
    print(f"    dormant_kernel_version        : {d.get('detected_version') or d.get('detected_identity', {}).get('version')}")
    print("    dormant_kernel_logic_present  : True")
    print(f"    active_kernel_installed       : {safety.get('kernel_installed', False)}")
    print(f"    activation_enabled            : {safety.get('activation_enabled', False)}")
    print(f"    worker_execution_enabled      : {safety.get('worker_execution_enabled', False)}")
    print(f"    provider_execution_enabled    : {safety.get('provider_execution_enabled', False)}")
    print(f"    model_inference_enabled       : {safety.get('model_inference_enabled', False)}")
    print(f"    direct_execution_allowed      : {safety.get('direct_execution_allowed', False)}")
