#!/usr/bin/env bash
# qsb_set_stripe_keys.sh
#
# Interactive helper to install Stripe credentials for F44 finance integration.
#
#   * Reads keys from your terminal — silent input for secrets.
#   * Writes vault/.env.stripe chmod 600.
#   * Smoke-tests TEST keys via a read-only API call to api.stripe.com.
#   * Defaults to TEST keys. Live keys ONLY accepted after CLAUDE.md clause.
#
# Find your keys at:
#   TEST:  https://dashboard.stripe.com/test/apikeys
#   LIVE:  https://dashboard.stripe.com/apikeys  (locked here until CLAUDE.md auth)
#
# Re-run any time to overwrite.

set -euo pipefail

ROOT="/vaults/nvme0/qsb_tower_v1"
VAULT_DIR="$ROOT/floors/floor_28_security_department/vault"
ENV_FILE="$VAULT_DIR/.env.stripe"
GITIGNORE="$ROOT/.gitignore"

mkdir -p "$VAULT_DIR" && chmod 700 "$VAULT_DIR"

echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
echo " Stripe key installer · QSB Tower Floor 44 Accounts"
echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
echo
echo " You will paste 3 values from your Stripe Dashboard:"
echo "   1. Publishable key  (starts pk_test_… or pk_live_…)"
echo "   2. Secret key       (starts sk_test_… or sk_live_…)"
echo "   3. Webhook sig sec  (starts whsec_…) — OPTIONAL (skip if no webhook yet)"
echo
echo " Dashboard: https://dashboard.stripe.com/test/apikeys"
echo " Use TEST keys first — they look identical but charge nothing."
echo " LIVE keys: I'll refuse them unless you confirm CLAUDE.md auth is in place."
echo
read -rp " Continue? [y/N] " confirm
case "$confirm" in
  y|Y|yes|YES) ;;
  *) echo " aborted."; exit 1 ;;
esac

# Publishable key — not sensitive, visible
echo
echo " Paste your PUBLISHABLE KEY then press Enter:"
read -rp " pk_…: " PK
PK="$(echo "$PK" | tr -d '[:space:]')"
if [ -z "$PK" ]; then
  echo " (no publishable key — aborting)" >&2; exit 1
fi
if [[ "$PK" != pk_test_* && "$PK" != pk_live_* ]]; then
  echo " expected pk_test_… or pk_live_… — got '$PK' — aborting" >&2; exit 1
fi
MODE="test"
[[ "$PK" == pk_live_* ]] && MODE="live"

# Secret key — silent input, sensitive
echo
echo " Paste your SECRET KEY then press Enter (input hidden):"
read -srp " sk_…: " SK
echo
SK="$(echo "$SK" | tr -d '[:space:]')"
if [ -z "$SK" ]; then
  echo " (no secret key — aborting)" >&2; exit 1
fi
if [[ "$SK" != sk_test_* && "$SK" != sk_live_* ]]; then
  echo " expected sk_test_… or sk_live_… — got malformed — aborting" >&2; exit 1
fi
# Mode consistency check
SK_MODE="test"; [[ "$SK" == sk_live_* ]] && SK_MODE="live"
if [ "$MODE" != "$SK_MODE" ]; then
  echo " publishable was $MODE-mode but secret is $SK_MODE-mode — keys must match — aborting" >&2; exit 1
fi

# Live-mode gate
if [ "$MODE" = "live" ]; then
  echo
  echo " ⚠ LIVE KEYS DETECTED."
  echo " Per CLAUDE.md V1.5, live_payments_enabled is locked FALSE."
  echo " A CLAUDE.md clause must explicitly authorize live mode."
  read -rp " Type 'CLAUDE.MD AUTH IS IN PLACE' to continue, anything else to abort: " liveconf
  if [ "$liveconf" != "CLAUDE.MD AUTH IS IN PLACE" ]; then
    echo " aborted — keys NOT written."; exit 1
  fi
fi

# Webhook signing — optional, silent
echo
echo " Paste WEBHOOK SIGNING SECRET (whsec_…) or press Enter to skip:"
read -srp " whsec_…: " WHSEC
echo
WHSEC="$(echo "$WHSEC" | tr -d '[:space:]')"
if [ -n "$WHSEC" ] && [[ "$WHSEC" != whsec_* ]]; then
  echo " (warning: doesn't look like a whsec_… — using anyway)"
fi

# Write env file
TS="$(date -u +%Y-%m-%dT%H:%M:%SZ)"
cat > "$ENV_FILE" <<EOT
# Stripe credentials — installed $TS by qsb_set_stripe_keys.sh
# Mode: $MODE
# DO NOT commit. DO NOT share. chmod 600.
STRIPE_MODE='$MODE'
STRIPE_PUBLISHABLE_KEY='$PK'
STRIPE_SECRET_KEY='$SK'
STRIPE_WEBHOOK_SIGNING_SECRET='$WHSEC'
EOT
chmod 600 "$ENV_FILE"
echo
echo " wrote $ENV_FILE (chmod 600)"

# Smoke-test: read balance via Stripe API
echo
echo " smoke-testing keys against api.stripe.com..."
RESP="$(curl -fsS -u "$SK:" https://api.stripe.com/v1/balance 2>&1 || true)"
if echo "$RESP" | grep -q '"object": "balance"'; then
  echo " ✓ smoke test passed — keys are valid and authenticated"
  AVAIL=$(echo "$RESP" | python3 -c 'import sys,json; d=json.load(sys.stdin); a=d.get("available",[]); print(", ".join(f"{x[\"amount\"]/100:.2f} {x[\"currency\"].upper()}" for x in a))' 2>/dev/null || echo "?")
  echo "   available balance: $AVAIL"
else
  echo " ✗ smoke test FAILED — keys may be wrong or revoked"
  echo "   response: $(echo "$RESP" | head -c 300)"
  echo "   keys WRITTEN regardless; re-run script to overwrite"
fi

# Ensure .gitignore
if [ -f "$GITIGNORE" ]; then
  if ! grep -q '^\.env\*$\|^floors/floor_28' "$GITIGNORE"; then
    echo "floors/floor_28_security_department/vault/.env*" >> "$GITIGNORE"
    echo " added vault/.env* to .gitignore"
  fi
fi

echo
echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
echo " done. Stripe $MODE keys installed for F44."
echo " Re-run any time to update."
echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
