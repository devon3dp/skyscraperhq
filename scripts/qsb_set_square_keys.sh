#!/usr/bin/env bash
# qsb_set_square_keys.sh — install Square credentials for F44.
set -euo pipefail
ROOT="/vaults/nvme0/qsb_tower_v1"
VAULT_DIR="$ROOT/floors/floor_28_security_department/vault"
ENV_FILE="$VAULT_DIR/.env.square"
mkdir -p "$VAULT_DIR" && chmod 700 "$VAULT_DIR"
echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
echo " Square key installer · QSB Tower Floor 44 Accounts"
echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
echo
echo " Find these at: https://developer.squareup.com/apps"
echo " Pick: Production (real money) or Sandbox (test)."
echo
read -rp " Mode (production/sandbox): " MODE
[[ "$MODE" != "production" && "$MODE" != "sandbox" ]] && { echo "bad mode"; exit 1; }
read -rp " Application ID: " APP_ID
read -srp " Access Token (hidden): " TOK; echo
read -rp " Location ID: " LOC
read -srp " Webhook Signature Key (hidden, or blank): " WHK; echo
TS="$(date -u +%Y-%m-%dT%H:%M:%SZ)"
cat > "$ENV_FILE" <<EOT
# Square credentials — installed $TS  mode=$MODE  chmod 600  DO NOT commit
SQUARE_MODE='$MODE'
SQUARE_APPLICATION_ID='$APP_ID'
SQUARE_ACCESS_TOKEN='$TOK'
SQUARE_LOCATION_ID='$LOC'
SQUARE_WEBHOOK_SIGNATURE_KEY='$WHK'
EOT
chmod 600 "$ENV_FILE"
echo " wrote $ENV_FILE (chmod 600)"
HOST="https://connect.squareup.com"
[ "$MODE" = "sandbox" ] && HOST="https://connect.squareupsandbox.com"
echo " smoke-testing against $HOST..."
RESP="$(curl -fsS -H "Authorization: Bearer $TOK" -H "Square-Version: 2024-04-17" "$HOST/v2/locations" 2>&1 || true)"
if echo "$RESP" | grep -q '"locations"'; then
  echo " ✓ smoke test passed"
else
  echo " ✗ smoke test failed: $(echo "$RESP" | head -c 200)"
fi
