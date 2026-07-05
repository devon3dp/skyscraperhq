#!/usr/bin/env bash
# qsb_godot_launch_with_feature_check.sh — runs the smoke test, then launches.
set -uo pipefail
ROOT="${QSB_ROOT:-/vaults/nvme0/qsb_tower_v1}"

cd "${ROOT}"

echo "============================================================"
echo "  Pre-launch smoke test"
echo "============================================================"
./scripts/qsb_godot_feature_migration_smoke_test.sh
SMOKE=$?
if [ "${SMOKE}" -ne 0 ]; then
  echo
  echo "Smoke test FAILED. Launch aborted. Inspect the log printed above."
  exit "${SMOKE}"
fi

echo
echo "============================================================"
echo "  Launching primary cockpit (Godot)"
echo "============================================================"
exec "${ROOT}/scripts/qsb_launch_primary_cockpit.sh"
