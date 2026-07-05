#!/usr/bin/env bash
# QSB Tower V1.3 — Security Spine Kernel Clearance Status
# Read-only script that prints the clearance review summary.
# Does NOT grant clearance, activate the kernel, or modify any registry.

set -euo pipefail
cd "$(dirname "$0")/.."

echo "======================================================"
echo "  QSB Tower V1.3 — Security Spine Clearance Status"
echo "======================================================"
echo ""

python3 - <<'PYEOF'
import json, sys
from pathlib import Path

REG  = Path('data/registries')
status_path = REG / 'security_spine_kernel_clearance_status.json'
review_path = REG / 'security_spine_kernel_clearance_review.json'

if not status_path.exists():
    print("  ERROR: clearance status report not found.")
    sys.exit(1)

s = json.loads(status_path.read_text())
r = json.loads(review_path.read_text()) if review_path.exists() else {}

print(f"  Security Spine         : {s.get('security_spine_status')}  ({s.get('security_spine_checks')} checks)")
print(f"  Critical Failures      : {s.get('security_spine_critical_failures')}")
print()
print("  Floor Status")
print(f"    Floor 28 Security    : {s.get('guardian_status','?')}")
print(f"    Floor 29 Guardian    : {s.get('guardian_status','?')}")
print(f"    Floor 30 Permissions : {s.get('permissions_status','?')}")
print(f"    Floor 31 Audit       : {s.get('audit_status','?')}")
print(f"    Floor 32 Compliance  : {s.get('compliance_status','?')}")
print()
print("  Pre-conditions")
print(f"    Forbidden paths absent          : {s.get('forbidden_paths_absent')}")
print(f"    Rebased unit tests passed       : {s.get('rebased_kernel_unit_tests_passed')}")
print(f"    Path rebase complete            : {s.get('path_rebase_complete')}")
print(f"    Activation gate                 : {s.get('activation_gate_passed')} passed")
print(f"    Blocking findings               : {s.get('blocking_findings')}")
print(f"    Advisory findings               : {s.get('advisory_findings')}")
print()
print("  Clearance Review")
print(f"    review_complete                 : {s.get('security_clearance_review_complete')}")
print(f"    clearance_RECOMMENDED           : {s.get('security_clearance_recommended')}")
print(f"    clearance_GRANTED               : {s.get('security_clearance_granted')}  (human decision required)")
print()
print("  Safety State")
print(f"    activation_allowed              : {s.get('activation_allowed')}")
print(f"    operator_approval_recorded      : {s.get('operator_approval_recorded')}")
print(f"    kernel_installed                : {s.get('kernel_installed')}")
print(f"    QSBKernelCore_instantiated      : {s.get('QSBKernelCore_instantiated')}")
print(f"    worker_execution_enabled        : {s.get('worker_execution_enabled')}")
print(f"    provider_execution_enabled      : {s.get('provider_execution_enabled')}")
print(f"    model_inference_enabled         : {s.get('model_inference_enabled')}")
print()

# Show advisory findings
if r.get('advisory_findings'):
    print("  Advisory Findings (informational — no action required):")
    for af in r['advisory_findings']:
        print(f"    [{af['id']}] {af['finding'][:100]}")
    print()

print(f"  Next Recommended Phase : {s.get('next_recommended_phase')}")
PYEOF

echo ""
echo "======================================================"
