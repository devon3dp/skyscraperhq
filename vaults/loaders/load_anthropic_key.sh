#!/usr/bin/env bash
set -euo pipefail
source "/vaults/nvme0/qsb_tower_v1/vaults/keys/anthropic_api.env"
export ANTHROPIC_API_KEY
echo "Loaded Claude / Anthropic API key from QSB Tower vault."
echo "Vault key file: /vaults/nvme0/qsb_tower_v1/vaults/keys/anthropic_api.env"
echo "Key preview: ${ANTHROPIC_API_KEY:0:12}...loaded"
