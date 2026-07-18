#!/usr/bin/env bash
set -euo pipefail

echo "============================================================"
echo " QSB TOWER VAULT · CLAUDE / ANTHROPIC API KEY INSTALLER"
echo "============================================================"
echo

QSB_ROOT="/vaults/nvme0/qsb_tower_v1"
VAULT_ROOT="$QSB_ROOT/vaults"
TS="$(date +%Y%m%d_%H%M%S)"

if [ ! -d "$QSB_ROOT" ]; then
  echo "ERROR: QSB root not found:"
  echo "$QSB_ROOT"
  exit 1
fi

mkdir -p "$VAULT_ROOT/keys" "$VAULT_ROOT/backups" "$VAULT_ROOT/loaders"
chmod 700 "$VAULT_ROOT" "$VAULT_ROOT/keys" "$VAULT_ROOT/backups" "$VAULT_ROOT/loaders" 2>/dev/null || true

KEY_FILE="$VAULT_ROOT/keys/anthropic_api.env"
BACKUP_FILE="$VAULT_ROOT/backups/anthropic_api.env.backup_$TS"
LOADER_FILE="$VAULT_ROOT/loaders/load_anthropic_key.sh"
LOCAL_LOADER="$HOME/load_qsb_claude_key.sh"
INDEX_FILE="$VAULT_ROOT/vault_index.md"

echo "[1/7] Using QSB root:"
echo "$QSB_ROOT"
echo
echo "[2/7] Using vault root:"
echo "$VAULT_ROOT"
echo

if [ -f "$KEY_FILE" ]; then
  echo "[3/7] Existing key file found. Backing it up..."
  cp "$KEY_FILE" "$BACKUP_FILE"
  chmod 600 "$BACKUP_FILE"
  echo "Backup saved:"
  echo "$BACKUP_FILE"
else
  echo "[3/7] No existing anthropic_api.env found. Fresh install."
fi

echo
echo "[4/7] Paste the NEW Claude / Anthropic API key."
echo "It will NOT show while typing."
read -rsp "New API key: " NEW_KEY
echo

if [ -z "$NEW_KEY" ]; then
  echo "ERROR: No key entered. Nothing changed."
  exit 1
fi

echo
echo "[5/7] Writing new key into QSB Tower vault..."

cat > "$KEY_FILE" <<ENVEOF
# QSB Tower Vault · Claude / Anthropic API key
# Created: $TS
# Root: $QSB_ROOT
# Vault: $VAULT_ROOT
export ANTHROPIC_API_KEY="$NEW_KEY"
ENVEOF

chmod 600 "$KEY_FILE"

cat > "$LOADER_FILE" <<LOADEREOF
#!/usr/bin/env bash
set -euo pipefail
source "$KEY_FILE"
export ANTHROPIC_API_KEY
echo "Loaded Claude / Anthropic API key from QSB Tower vault."
echo "Vault key file: $KEY_FILE"
echo "Key preview: \${ANTHROPIC_API_KEY:0:12}...loaded"
LOADEREOF

chmod 700 "$LOADER_FILE"

cat > "$LOCAL_LOADER" <<LOCALLOADEREOF
#!/usr/bin/env bash
set -euo pipefail
source "$KEY_FILE"
export ANTHROPIC_API_KEY
echo "Loaded Claude / Anthropic API key from QSB Tower vault."
echo "Vault key file: $KEY_FILE"
echo "Key preview: \${ANTHROPIC_API_KEY:0:12}...loaded"
LOCALLOADEREOF

chmod 700 "$LOCAL_LOADER"

echo
echo "[6/7] Updating vault index..."

touch "$INDEX_FILE"

cat >> "$INDEX_FILE" <<IDXEOF

## anthropic_api.env
- Updated: $TS
- Purpose: Claude / Anthropic API key for QSB Tower CEOs, Claude CLI, Brain Router, and approved external AI access.
- Secret file: $KEY_FILE
- Loader: $LOADER_FILE
- Local loader: $LOCAL_LOADER
- Rule: never print the raw key into Town Square, Task Council, Boardroom, logs, screenshots, or chat.
IDXEOF

chmod 600 "$INDEX_FILE" 2>/dev/null || true

echo
echo "[7/7] Optional shell startup loader..."

SOURCE_LINE="source \"$KEY_FILE\""

if ! grep -Fq "$SOURCE_LINE" "$HOME/.bashrc" 2>/dev/null; then
  echo >> "$HOME/.bashrc"
  echo "# Load QSB Tower Claude / Anthropic API key" >> "$HOME/.bashrc"
  echo "$SOURCE_LINE" >> "$HOME/.bashrc"
  echo "Added key loader to ~/.bashrc"
else
  echo "Key loader already exists in ~/.bashrc"
fi

echo
echo "============================================================"
echo " DONE"
echo "============================================================"
echo
echo "Key installed at:"
echo "$KEY_FILE"
echo
echo "Loader created at:"
echo "$LOCAL_LOADER"
echo
echo "Now run:"
echo "source \"$KEY_FILE\""
echo
echo "Then test:"
echo "echo \${ANTHROPIC_API_KEY:0:12}...loaded"
echo "claude doctor"
echo
echo "Or start Claude with:"
echo "source \"$KEY_FILE\" && claude"
echo
echo "Nothing else was changed:"
echo "- no CEO memories touched"
echo "- no dashboards touched"
echo "- no Task Council files touched"
echo "- no Rule Book touched"
echo "- no Skyscraper code touched"
echo
