#!/usr/bin/env bash
# QSB Tower V1.3 — Kernel Integration Readiness Status
# Runs kernel_readiness.py and prints a concise summary.
# Does NOT install the kernel or enable any execution.

set -euo pipefail
cd "$(dirname "$0")/.."

echo "=============================================="
echo "  QSB Tower V1.3 — Kernel Readiness Status"
echo "=============================================="
echo ""

python3 - <<'PYEOF'
import sys, json
sys.path.insert(0, 'src')
from tower.kernel_readiness import KernelReadiness

r = KernelReadiness().run()
s = r['summary']

print(f"  Readiness Status :  {s['readiness_status']}")
print(f"  Checks Run       :  {s['checks_run']}")
print(f"  Passed           :  {s['passed']}")
print(f"  Warnings         :  {s['warnings']}")
print(f"  Critical Failures:  {s['critical_failures']}")
print()
print("  Safety Flags (all must be false):")
print(f"    kernel_installed          : {s['kernel_installed']}")
print(f"    kernel_logic_present      : {s['kernel_logic_present']}")
print(f"    worker_execution_enabled  : {s['worker_execution_enabled']}")
print(f"    provider_execution_enabled: {s['provider_execution_enabled']}")
print(f"    model_inference_enabled   : {s['model_inference_enabled']}")
print(f"    live_dispatch_enabled     : {s['live_dispatch_enabled']}")
print()

if s['critical_failures'] > 0:
    print("  FAILURES:")
    for item in r['items']:
        if item['status'] == 'fail' and item['severity'] == 'critical':
            print(f"    [CRITICAL] {item['name']}: {item['message']}")

if s['warnings'] > 0:
    print("  WARNINGS:")
    for item in r['items']:
        if item['status'] == 'fail' and item['severity'] == 'warning':
            print(f"    [WARNING]  {item['name']}: {item['message']}")

print()
if s['readiness_status'] == 'READY_FOR_KERNEL_INTEGRATION':
    print("  STATUS: READY FOR KERNEL INTEGRATION (kernel not installed)")
elif s['readiness_status'] == 'READY_FOR_KERNEL_DESIGN_ONLY':
    print("  STATUS: Design-ready, not integration-ready. Fix warnings.")
else:
    print("  STATUS: NOT READY. Fix critical failures before proceeding.")
PYEOF

echo ""
echo "=============================================="
