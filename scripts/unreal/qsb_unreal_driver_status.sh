#!/usr/bin/env bash
set -u
cd /vaults/nvme0/qsb_tower_v1 || exit 1
TS=$(date -u +%Y-%m-%dT%H:%M:%SZ)
./scripts/unreal/qsb_unreal_find_project.sh >/dev/null
./scripts/unreal/qsb_unreal_editor_status.sh
echo ""
LATEST=$(ls -t data/screenshots/unreal_cli_driver/*.png 2>/dev/null | head -1)
echo "latest screenshot: ${LATEST:-(none)}"
echo ""
cat data/registries/qsb_unreal_cli_driver_status.json 2>/dev/null
