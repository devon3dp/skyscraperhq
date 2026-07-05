#!/usr/bin/env bash
# QSB Tower V1.3 — Dormant Kernel Compatibility Review Summary
# Read-only script that prints the compatibility review report.
# Does NOT execute any kernel logic.

set -euo pipefail
cd "$(dirname "$0")/.."

echo "======================================================"
echo "  QSB Tower V1.3 — Dormant Kernel Compatibility Review"
echo "======================================================"
echo ""

python3 - <<'PYEOF'
import json, sys
from pathlib import Path

REG = Path('data/registries')
report_path = REG / 'dormant_kernel_compatibility_review.json'

if not report_path.exists():
    print("  ERROR: compatibility review report not found.")
    print(f"  Expected at: {report_path}")
    sys.exit(1)

r = json.loads(report_path.read_text())

ki = r.get('kernel_identity', {})
print("  Kernel Identity")
print(f"    Name               : {ki.get('name')}")
print(f"    Version            : {ki.get('version')}")
print(f"    Cognitive Upgrade  : {ki.get('cognitive_upgrade')}")
print(f"    Continuity Status  : {ki.get('continuity_status_at_import')}")
print()

fc = r.get('imported_file_count', {})
hv = r.get('hash_verification', {})
print("  Import Status")
print(f"    Total files        : {fc.get('total')}")
print(f"    Hash verification  : {hv.get('result')}")
print(f"    Files checked      : {hv.get('files_checked')}")
print()

cs = r.get('compatibility_score', {})
print(f"  Compatibility Score  : {cs.get('score')}/100")
print(f"  Verdict              : {cs.get('overall_verdict')}")
print()

print("  Key Risk Areas")
path_risk = r.get('old_path_assumptions', {})
print(f"    Old path assumptions  : {path_risk.get('verdict','?')}")
ph_risk = r.get('old_penthouse_assumptions', {})
print(f"    Old penthouse deps    : {ph_risk.get('verdict','?')}")
mc_risk = r.get('model_call_risks', {}).get('kernel_sub_cores', {})
print(f"    Model calls (kernel)  : {mc_risk.get('verdict','?')}")
fs_risk = r.get('filesystem_write_risks', {})
print(f"    Filesystem writes     : {fs_risk.get('verdict','?')}")
net_risk = r.get('provider_network_risks', {})
print(f"    Network/provider risk : kernel_sub_cores={net_risk.get('kernel_sub_cores','?')}")
print()

adapters = r.get('required_adapter_changes_before_activation', [])
blocking = [a for a in adapters if a.get('priority') == 'BLOCKING']
high     = [a for a in adapters if a.get('priority') == 'HIGH']
print(f"  Required Adapter Changes: {len(adapters)} total")
print(f"    BLOCKING : {len(blocking)}")
for a in blocking:
    print(f"      [{a['id']}] {a['title']}")
print(f"    HIGH     : {len(high)}")
for a in high:
    print(f"      [{a['id']}] {a['title']}")
print()

gates = r.get('required_safety_gates_before_activation', [])
print(f"  Safety Gates Required: {len(gates)}")
for g in gates:
    state = g.get('current_state', '?')
    print(f"    [{g['id']}] {g['gate']}: {state}")
print()

tstate = r.get('current_tower_state_at_review_time', {})
print("  Current Tower Safety State")
print(f"    activation_allowed          : {r.get('activation_allowed')}")
print(f"    kernel_installed            : {tstate.get('kernel_installed')}")
print(f"    kernel_logic_present        : {tstate.get('kernel_logic_present')}")
print(f"    dormant_kernel_imported     : {tstate.get('dormant_kernel_imported')}")
print(f"    dormant_activation_enabled  : {tstate.get('dormant_kernel_activation_enabled')}")
print(f"    worker_execution_enabled    : {tstate.get('worker_execution_enabled')}")
print(f"    provider_execution_enabled  : {tstate.get('provider_execution_enabled')}")
print(f"    model_inference_enabled     : {tstate.get('model_inference_enabled')}")
print(f"    forbidden_paths_absent      : {tstate.get('forbidden_paths_absent')}")
print()

nrp = r.get('next_recommended_phase', {})
print(f"  Next Recommended Phase: {nrp.get('phase')}")
print(f"    {nrp.get('description','')[:100]}")
PYEOF

echo ""
echo "======================================================"
