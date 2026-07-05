#!/usr/bin/env bash
# QSB Tower V1.3 — Run All Tower Checks
# Executes every available tower status script in sequence.
# Does NOT activate workers, install the kernel, or call providers.

set -uo pipefail
cd "$(dirname "$0")/.."

PASS=0; FAIL=0

run_check() {
    local label="$1"; local script="$2"
    if bash "$script" > /tmp/qsb_check_out.txt 2>&1; then
        echo "  [PASS] $label"
        PASS=$((PASS+1))
    else
        echo "  [FAIL] $label"
        FAIL=$((FAIL+1))
        head -5 /tmp/qsb_check_out.txt | sed 's/^/         /'
    fi
}

echo "================================================"
echo "  QSB Tower V1.3 — All Tower Checks"
echo "================================================"
echo ""

run_check "Kernel Readiness"         scripts/kernel_readiness_status.sh
run_check "OpenClaw Candidate Status" scripts/openclaw_candidate_status.sh
run_check "Model/Worker Staging"      scripts/model_worker_staging_status.sh
run_check "Penthouse Readiness"       scripts/run_penthouse_acceptance.sh
run_check "Security Spine"            scripts/run_security_spine_check.sh
run_check "Floor 33 Diagnostics"      scripts/run_floor_33_diagnostics.sh
run_check "Floor 34 Monitoring"       scripts/run_floor_34_monitoring.sh
run_check "Floor 35 Infrastructure"   scripts/run_floor_35_infrastructure.sh
run_check "Floor 36 Expansion"        scripts/run_floor_36_expansion.sh
run_check "Floor 37 Simulations"      scripts/run_floor37_simulations.sh
run_check "Floor 38 Sandboxes"        scripts/run_floor38_sandboxes.sh
run_check "Floor 25 Prechecks"        scripts/run_floor25_prechecks.sh
run_check "Floor 26 Evaluation"       scripts/run_floor26_evaluation.sh

echo ""
echo "  Passed: $PASS   Failed: $FAIL"
echo ""
if [ "$FAIL" -eq 0 ]; then
    echo "  RESULT: ALL TOWER CHECKS PASSED"
else
    echo "  RESULT: $FAIL check(s) failed — review output above"
fi
echo "================================================"
