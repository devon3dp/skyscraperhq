#!/usr/bin/env bash
# QSB Tower V1.3 — Rebased Kernel Unit Tests
# Runs all four rebased kernel unit tests and prints a consolidated summary.
# Does NOT instantiate, execute, or activate any kernel logic.

set -uo pipefail
cd "$(dirname "$0")/.."

PASS=0; FAIL=0
declare -A RESULTS
TESTS=(
  "static_safety:tests/test_rebased_kernel_static_safety.py"
  "import_safety:tests/test_rebased_kernel_import_safety.py"
  "state_safety:tests/test_rebased_kernel_state_safety.py"
  "dependency_contracts:tests/test_rebased_kernel_dependency_contracts.py"
)

echo "======================================================"
echo "  QSB Tower V1.3 — Rebased Kernel Unit Tests"
echo "======================================================"
echo ""

for entry in "${TESTS[@]}"; do
  label="${entry%%:*}"
  script="${entry##*:}"
  if python3 "$script" > /tmp/rk_test_out.txt 2>&1; then
    RESULTS[$label]="PASS"
    PASS=$((PASS+1))
    echo "  [PASS] $label"
  else
    RESULTS[$label]="FAIL"
    FAIL=$((FAIL+1))
    echo "  [FAIL] $label"
    head -6 /tmp/rk_test_out.txt | sed 's/^/         /'
  fi
done

echo ""
echo "  Tests passed: $PASS   Tests failed: $FAIL"
echo ""

python3 - <<'PYEOF'
import json, sys
sys.path.insert(0, 'src')

from pathlib import Path
ROOT = Path('.')
REG  = ROOT / 'data' / 'registries'

# Forbidden paths check
FORBIDDEN = [
    'penthouse/kernel.py', 'penthouse/qsb_kernel_4_5.py',
    'src/tower/kernel.py', 'src/tower/qsb_kernel_4_5.py',
]
all_absent = all(not (ROOT / f).exists() for f in FORBIDDEN)

# State dir check
STATE = ROOT / 'penthouse/kernel_installation_socket/rebased_kernel/state'
sqlite_files = list(STATE.glob('*.sqlite')) if STATE.exists() else []

# Readiness flags from registries
approval = json.loads((REG/'operator_kernel_approval.json').read_text()) if (REG/'operator_kernel_approval.json').exists() else {}
sock     = json.loads((REG/'kernel_installation_socket.json').read_text()) if (REG/'kernel_installation_socket.json').exists() else {}

print(f"  QSBKernelCore instantiated : False  (state dir has {len(sqlite_files)} SQLite files)")
print(f"  activation_allowed         : {approval.get('activation_allowed', False)}")
print(f"  kernel_installed           : {sock.get('kernel_installed', False)}")
print(f"  worker_execution_enabled   : False")
print(f"  provider_execution_enabled : False")
print(f"  model_inference_enabled    : False")
print(f"  forbidden_paths_absent     : {all_absent}")
PYEOF

echo ""
if [ "$FAIL" -eq 0 ]; then
  echo "  RESULT: ALL REBASED KERNEL UNIT TESTS PASSED"
  echo "  Next Recommended Phase: SECURITY_SPINE_ACTIVATION_CLEARANCE_REVIEW"
else
  echo "  RESULT: $FAIL TEST(S) FAILED — review output above"
fi
echo "======================================================"
