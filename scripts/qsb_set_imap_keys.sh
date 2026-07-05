#!/usr/bin/env bash
# qsb_set_imap_keys.sh — install IMAP credentials for any provider.
# Supports Outlook/Microsoft, Yahoo, Zoho, Fastmail, GMX, AOL, custom.
#
# Prerequisites per provider:
#   - Outlook/Microsoft: enable 2-step, generate "App password" at account.microsoft.com/security
#   - Yahoo:             account.yahoo.com → Manage account security → Generate app password
#   - Zoho:              accounts.zoho.com → Security → App Passwords
#   - Fastmail:          settings → password & security → App passwords
#
set -euo pipefail
ROOT="/vaults/nvme0/qsb_tower_v1"
VAULT_DIR="$ROOT/floors/floor_28_security_department/vault"
mkdir -p "$VAULT_DIR" && chmod 700 "$VAULT_DIR"

echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
echo " IMAP installer (any provider) · QSB Tower F164 Email Ops"
echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
echo
echo " Choose provider:"
echo "   1) Outlook.com / Microsoft Live  (recommended)"
echo "   2) Yahoo Mail"
echo "   3) Zoho Mail"
echo "   4) Fastmail"
echo "   5) GMX"
echo "   6) AOL"
echo "   7) Custom (enter host yourself)"
read -rp " choice [1-7]: " choice
case $choice in
  1) HOST="outlook.office365.com"; PORT=993; PROVIDER="outlook" ;;
  2) HOST="imap.mail.yahoo.com"; PORT=993; PROVIDER="yahoo" ;;
  3) HOST="imap.zoho.eu"; PORT=993; PROVIDER="zoho_eu" ;;
  4) HOST="imap.fastmail.com"; PORT=993; PROVIDER="fastmail" ;;
  5) HOST="imap.gmx.com"; PORT=993; PROVIDER="gmx" ;;
  6) HOST="imap.aol.com"; PORT=993; PROVIDER="aol" ;;
  7) read -rp " IMAP host: " HOST; read -rp " IMAP port [993]: " PORT; PORT=${PORT:-993}; PROVIDER="custom" ;;
  *) echo "bad choice"; exit 1 ;;
esac

ENV_FILE="$VAULT_DIR/.env.${PROVIDER}.imap"
echo
read -rp " Email address: " EMAIL
read -srp " Password / App Password (hidden): " PWD; echo
PWD="$(echo "$PWD" | tr -d '[:space:]')"
TS="$(date -u +%Y-%m-%dT%H:%M:%SZ)"

cat > "$ENV_FILE" <<EOT
# IMAP credentials — installed $TS  provider=$PROVIDER  chmod 600
IMAP_PROVIDER='$PROVIDER'
IMAP_HOST='$HOST'
IMAP_PORT='$PORT'
IMAP_EMAIL='$EMAIL'
IMAP_PASSWORD='$PWD'
EOT
chmod 600 "$ENV_FILE"
echo " ✓ wrote $ENV_FILE (chmod 600)"

echo
echo " smoke-testing IMAP login..."
python3 -c "
import imaplib
try:
    m = imaplib.IMAP4_SSL('$HOST', $PORT)
    m.login('$EMAIL', '$PWD')
    typ, data = m.list()
    print(f'  ✓ login OK · {len(data)} mailbox folders')
    typ, data = m.select('INBOX')
    print(f'  ✓ INBOX has {int(data[0])} messages')
    m.logout()
except Exception as e:
    print(f'  ✗ login failed: {e}')
"
