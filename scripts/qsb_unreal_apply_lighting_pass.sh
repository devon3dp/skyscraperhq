#!/usr/bin/env bash
set -u
cd /vaults/nvme0/qsb_tower_v1 || exit 1
exec .venv/bin/python3 scripts/qsb_unreal_apply_lighting_pass.py "$@"
