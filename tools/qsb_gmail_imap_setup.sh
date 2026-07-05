#!/usr/bin/env bash
# qsb_gmail_imap_setup.sh — Gmail IMAP via App Password (no Cloud Console needed).
#
# Prerequisites for Ross:
#   1. Enable 2-Step Verification at https://myaccount.google.com/security
#   2. Generate App Password at https://myaccount.google.com/apppasswords
#      App: "Mail"  Device: "Skyscraper Inbox Reader"
#      Google shows a 16-char password like "abcd efgh ijkl mnop"
#
# Then run this script.

set -euo pipefail
ROOT="/vaults/nvme0/qsb_tower_v1"
VAULT_DIR="$ROOT/floors/floor_28_security_department/vault"
ENV_FILE="$VAULT_DIR/.env.google.imap"
mkdir -p "$VAULT_DIR" && chmod 700 "$VAULT_DIR"

echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
echo " Gmail IMAP installer (App Password) · QSB Tower F164 Email Ops"
echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
echo
read -rp " Gmail address: " GMAIL
read -srp " App Password (16 chars, hidden): " APP_PWD; echo
APP_PWD="$(echo "$APP_PWD" | tr -d '[:space:]')"
TS="$(date -u +%Y-%m-%dT%H:%M:%SZ)"
cat > "$ENV_FILE" <<EOT
# Gmail IMAP credentials — installed $TS  chmod 600  DO NOT commit
GMAIL_ADDRESS='$GMAIL'
GMAIL_APP_PASSWORD='$APP_PWD'
GMAIL_IMAP_HOST='imap.gmail.com'
GMAIL_IMAP_PORT='993'
EOT
chmod 600 "$ENV_FILE"
echo " wrote $ENV_FILE (chmod 600)"
echo
# Smoke-test IMAP login
echo " smoke-testing IMAP login..."
python3 -c "
import imaplib
try:
    m = imaplib.IMAP4_SSL('imap.gmail.com', 993)
    m.login('$GMAIL', '$APP_PWD')
    typ, data = m.list()
    print(f'  ✓ login OK · {len(data)} mailbox folders visible')
    m.logout()
except Exception as e:
    print(f'  ✗ login failed: {e}')
"
