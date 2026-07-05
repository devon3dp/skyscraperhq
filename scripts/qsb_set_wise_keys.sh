#!/usr/bin/env bash
# qsb_set_wise_keys.sh — install Wise Business credentials for ops-float outbound.
set -euo pipefail
ROOT="/vaults/nvme0/qsb_tower_v1"
VAULT_DIR="$ROOT/floors/floor_28_security_department/vault"
ENV_FILE="$VAULT_DIR/.env.wise"
mkdir -p "$VAULT_DIR" && chmod 700 "$VAULT_DIR"
echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
echo " Wise Business key installer · QSB Tower Floor 44 Accounts"
echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
echo
echo " Find at: https://wise.com/settings/api-tokens"
echo " Sandbox: https://api.sandbox.transferwise.tech"
echo " Live:    https://api.wise.com"
echo
read -rp " Mode (live/sandbox): " MODE
[[ "$MODE" != "live" && "$MODE" != "sandbox" ]] && { echo "bad mode"; exit 1; }
read -srp " API Token (hidden): " TOK; echo
read -rp " Profile ID (numeric): " PROF
TS="$(date -u +%Y-%m-%dT%H:%M:%SZ)"
cat > "$ENV_FILE" <<EOT
# Wise Business credentials — installed $TS  mode=$MODE  chmod 600
WISE_MODE='$MODE'
WISE_API_TOKEN='$TOK'
WISE_PROFILE_ID='$PROF'
EOT
chmod 600 "$ENV_FILE"
echo " wrote $ENV_FILE (chmod 600)"
HOST="https://api.wise.com"
[ "$MODE" = "sandbox" ] && HOST="https://api.sandbox.transferwise.tech"
echo " smoke-testing against $HOST..."
RESP="$(curl -fsS -H "Authorization: Bearer $TOK" "$HOST/v2/profiles" 2>&1 || true)"
if echo "$RESP" | grep -q '"id"'; then
  echo " ✓ smoke test passed"
else
  echo " ✗ smoke test failed: $(echo "$RESP" | head -c 200)"
fi
