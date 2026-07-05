#!/usr/bin/env bash
# QSB Tower V1.3 — Kernel Activation Gate Status
# Read-only script that evaluates and prints the activation gate report.
# Does NOT instantiate, execute, or activate any kernel logic.

set -euo pipefail
cd "$(dirname "$0")/.."

echo "======================================================"
echo "  QSB Tower V1.3 — Kernel Activation Gate Status"
echo "======================================================"
echo ""

python3 - <<'PYEOF'
import sys, json
sys.path.insert(0, 'src')
from tower.kernel_activation_gate import KernelActivationGate

gate = KernelActivationGate()
r = gate.evaluate()

print(f"  Gate Status          : {r['gate_status']}")
print(f"  Activation Allowed   : {r['activation_allowed']}")
print(f"  Gates Passed         : {r['gates_passed']}")
print(f"  Gates Blocked        : {r['gates_blocked']}")
print()

if r['blocked_reasons']:
    print("  Blocked Reasons:")
    for br in r['blocked_reasons']:
        print(f"    - {br[:110]}")
    print()

print("  Key State:")
print(f"    kernel_installed           : {r['kernel_installed']}")
print(f"    QSBKernelCore_instantiated : {r['QSBKernelCore_instantiated']}")
print(f"    operator_approval_recorded : {r['operator_approval_recorded']}")
print(f"    security_clearance         : {r['security_spine_clearance']}")
print(f"    forbidden_paths_absent     : {r['forbidden_paths_absent']}")
print(f"    rebased_kernel_present     : {r['rebased_kernel_present']}")
print(f"    path_rebase_complete       : {r['path_rebase_complete']}")
print()
print("  Safety Flags (must all be false):")
print(f"    worker_execution_enabled   : {r['worker_execution_enabled']}")
print(f"    provider_execution_enabled : {r['provider_execution_enabled']}")
print(f"    model_inference_enabled    : {r['model_inference_enabled']}")
print()
print(f"  Next Recommended Phase: {r['next_recommended_phase']}")
PYEOF

echo ""
echo "======================================================"
