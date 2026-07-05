#!/usr/bin/env bash
# QSB Tower V1.3 — Verify Dormant Kernel Import
# Verifies file presence and SHA-256 hashes of the dormant imported kernel.
# Read-only. Does NOT execute any kernel logic.

set -euo pipefail
cd "$(dirname "$0")/.."

echo "=============================================="
echo "  QSB Tower V1.3 — Verify Dormant Import"
echo "=============================================="
echo ""

python3 - <<'PYEOF'
import sys, json, hashlib
sys.path.insert(0, 'src')
from pathlib import Path
from tower.dormant_kernel_adapter import DormantKernelAdapter, DORMANT_DIR, FORBIDDEN_PATHS

adapter = DormantKernelAdapter()

# 1. File presence
files_info = adapter.list_imported_files()
print("  Kernel files in dormant import:")
for f in files_info['kernel_files']:
    print(f"    {f}")
print()
print("  Source support files:")
for f in files_info['support_files']:
    print(f"    {f}")
print()
print(f"  Total: {files_info['total']} files")
print()

# 2. Hash verification
hashes = adapter.verify_hashes()
print(f"  Hash verification: {hashes['status']}")
all_match = True
for rel, result in hashes['results'].items():
    status = 'OK' if result['match'] else 'MISMATCH'
    if not result['match']:
        all_match = False
    print(f"    [{status}] {rel}")
print()

# 3. Forbidden paths
forbidden = adapter.check_forbidden_paths()
print("  Forbidden path check:")
for p in forbidden['checked']:
    exists = Path(p).exists()
    print(f"    {'DANGER' if exists else 'absent (correct)':20s}  {p}")
print()

# 4. Old source kernel still present
src_kernel = Path('/vaults/nvme0/qsb_skyscraper/kernel')
src_present = src_kernel.exists()
print(f"  Old source kernel present : {src_present}  ({src_kernel})")
print()

# Overall
ok = all_match and forbidden['all_absent'] and src_present and files_info['total'] >= 10
if ok:
    print("  RESULT: DORMANT IMPORT VERIFIED OK")
else:
    print("  RESULT: VERIFICATION ISSUES DETECTED")
    if not all_match:
        print("    Hash mismatch in dormant files")
    if not forbidden['all_absent']:
        print("    Forbidden paths present")
    if not src_present:
        print("    Old source kernel missing from /vaults/nvme0/qsb_skyscraper/kernel")
PYEOF

echo ""
echo "=============================================="
