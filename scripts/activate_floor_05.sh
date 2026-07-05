#!/usr/bin/env bash
set -euo pipefail

ROOT="${QSB_TOWER_ROOT:-/vaults/nvme0/qsb_tower_v1}"
FLOOR_ID="floor_05"

echo "QSB Tower protected activation hook"
echo "Floor: $FLOOR_ID"
echo "Status: BLOCKED_SAFE_STUB"
echo "Execution: disabled"
echo
echo "This file exists to satisfy registry activation_hook references."
echo "It does not activate floors."
echo "It does not start workers."
echo "It does not install the QSB Kernel."
echo
echo "Future activation must pass:"
echo "- Floor 36 Expansion Planning approval"
echo "- Security Spine approval"
echo "- Manual operator approval"
echo "- Registry validation"
echo
exit 2
