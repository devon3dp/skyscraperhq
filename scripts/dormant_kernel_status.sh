#!/usr/bin/env bash
# QSB Tower V1.3 — Dormant Kernel Import Status
# Read-only status report for the dormant imported kernel package.
# Does NOT instantiate, execute, or activate any kernel logic.

set -euo pipefail
cd "$(dirname "$0")/.."

echo "=============================================="
echo "  QSB Tower V1.3 — Dormant Kernel Status"
echo "=============================================="
echo ""

python3 - <<'PYEOF'
import sys, json
sys.path.insert(0, 'src')
from tower.dormant_kernel_adapter import DormantKernelAdapter

d = DormantKernelAdapter().dashboard()

print(f"  Dormant Import Dir  : {d['dormant_import_dir']}")
print(f"  Kernel Version      : {d['kernel_version']}")
print(f"  Kernel Role         : {d['kernel_role']}")
print(f"  Principle           : {d['kernel_principle']}")
print(f"  Continuity Status   : {d['continuity_status']}")
print(f"  Continuity TS       : {d['continuity_ts']}")
print()
print(f"  Imported Files      : {d['imported_files_total']}")
print(f"  Hash Verification   : {d['hash_verification']}")
print(f"  Hashes Checked      : {d['hashes_checked']}")
print()
print("  Safety Flags:")
print(f"    kernel_installed          : {d['kernel_installed']}")
print(f"    kernel_logic_present      : {d['kernel_logic_present']}")
print(f"    execution_enabled         : {d['execution_enabled']}")
print(f"    worker_execution_enabled  : {d['worker_execution_enabled']}")
print(f"    provider_execution_enabled: {d['provider_execution_enabled']}")
print(f"    model_inference_enabled   : {d['model_inference_enabled']}")
print(f"    live_dispatch_enabled     : {d['live_dispatch_enabled']}")
print(f"    activation_enabled        : {d['activation_enabled']}")
print(f"    direct_execution_allowed  : {d['direct_execution_allowed']}")
print()
print(f"  Forbidden Paths Absent : {d['forbidden_paths_absent']}")
if d['forbidden_paths_found']:
    print(f"  WARNING forbidden paths found: {d['forbidden_paths_found']}")
print()
print(f"  Next Step: {d['next_step']}")
print()
print(f"  Compatibility Risks: {d['compatibility_risks']}")
PYEOF

echo ""
echo "=============================================="
