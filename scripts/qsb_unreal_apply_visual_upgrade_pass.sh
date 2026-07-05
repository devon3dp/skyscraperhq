#!/usr/bin/env bash
# Convenience wrapper: cd + run the visual upgrade pass python.
set -u
cd /vaults/nvme0/qsb_tower_v1 || exit 1
exec .venv/bin/python3 scripts/qsb_unreal_apply_visual_upgrade_pass.py "$@"
