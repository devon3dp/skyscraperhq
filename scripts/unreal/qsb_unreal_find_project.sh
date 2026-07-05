#!/usr/bin/env bash
set -u
cd /vaults/nvme0/qsb_tower_v1 || exit 1
TS=$(date -u +%Y-%m-%dT%H:%M:%SZ)
PROJECT=/vaults/nvme0/qsb_unreal_skyscraper/QSB_Skyscraper.uproject
ENGINE=/vaults/nvme0/UnrealEngine/Engine/Binaries/Linux/UnrealEditor
PROJECT_OK=no; ENGINE_OK=no
[[ -f "$PROJECT" ]] && PROJECT_OK=yes
[[ -x "$ENGINE" ]] && ENGINE_OK=yes
echo "ts=$TS"
echo "project=$PROJECT  found=$PROJECT_OK"
echo "engine=$ENGINE  found=$ENGINE_OK"
mkdir -p data/registries
cat > data/registries/qsb_unreal_cli_driver_status.json <<EOF
{
  "ts": "$TS",
  "project_path": "$PROJECT",
  "project_found": "$PROJECT_OK",
  "engine_path": "$ENGINE",
  "engine_found": "$ENGINE_OK"
}
EOF
