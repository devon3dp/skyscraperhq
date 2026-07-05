#!/usr/bin/env bash
# QSB Tower V1.3 — Dormant Kernel Path Rebase Status
# Read-only status script for the rebased kernel package.
# Does NOT instantiate, execute, or activate any kernel logic.

set -euo pipefail
cd "$(dirname "$0")/.."

echo "======================================================"
echo "  QSB Tower V1.3 — Kernel Path Rebase Status"
echo "======================================================"
echo ""

python3 - <<'PYEOF'
import sys, json, hashlib
from pathlib import Path

ROOT    = Path('/vaults/nvme0/qsb_tower_v1')
RK      = ROOT / 'penthouse/kernel_installation_socket/rebased_kernel'
RK_K    = RK / 'kernel'
MANIFEST = RK / 'rebase_manifest.json'
OLD_VAULT = '/vaults/nvme0/qsb_skyscraper'

# 1. Rebased directory exists
print(f"  Rebased kernel dir   : {RK_K}")
print(f"  Directory exists     : {RK_K.exists()}")
if not RK_K.exists():
    print("  ERROR: rebased kernel directory missing")
    sys.exit(1)

# 2. File listing
py_files = sorted(f.name for f in RK_K.glob('*.py'))
print(f"  Python files         : {len(py_files)}")
for f in py_files:
    print(f"    {f}")
print()

# 3. Old-path check
old_refs = 0
for py in RK_K.glob('*.py'):
    src = py.read_text()
    hits = [l for l in src.splitlines() if OLD_VAULT in l]
    old_refs += len(hits)
print(f"  Old vault refs remaining : {old_refs}  {'(CLEAN)' if old_refs == 0 else '(NEEDS FIX)'}")

# 4. Compile check
import py_compile, tempfile
compile_ok = True
for py in sorted(RK_K.glob('*.py')):
    try:
        py_compile.compile(str(py), doraise=True)
    except py_compile.PyCompileError as e:
        print(f"  COMPILE FAIL: {py.name}: {e}")
        compile_ok = False
print(f"  Compile check        : {'ALL OK' if compile_ok else 'FAILURES'}")

# 5. Manifest
if MANIFEST.exists():
    m = json.loads(MANIFEST.read_text())
    sf = m.get('safety_flags', {})
    print()
    print("  Safety Flags:")
    for k in ['kernel_installed','activation_enabled','execution_enabled',
              'worker_execution_enabled','provider_execution_enabled',
              'model_inference_enabled','qsb_kernel_core_instantiated','activation_allowed']:
        print(f"    {k:40s}: {sf.get(k)}")
    print()
    print(f"  Files copied    : {len(m.get('files_copied', []))}")
    print(f"  Files patched   : {len(m.get('files_patched', []))}")
    print(f"  Import rewires  : {m.get('import_rewiring_count')}")
    print(f"  Old refs remain : {m.get('old_path_references_remaining')}")
    print(f"  Compile result  : {'all_pass' if m.get('compile_results', {}).get('all_pass') else 'check'}")
    print()
    print(f"  Next phase      : {m.get('next_recommended_phase')}")
else:
    print("  WARNING: rebase_manifest.json not found")

# 6. Forbidden paths
print()
print("  Forbidden direct kernel paths:")
forbidden = [
    'penthouse/kernel.py', 'penthouse/qsb_kernel_4_5.py',
    'src/tower/kernel.py', 'src/tower/qsb_kernel_4_5.py'
]
for fp in forbidden:
    exists = (ROOT / fp).exists()
    print(f"    {'DANGER' if exists else 'absent (correct)':22s}  {fp}")
PYEOF

echo ""
echo "======================================================"
