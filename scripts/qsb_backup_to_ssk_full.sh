#!/usr/bin/env bash
# qsb_backup_to_ssk_full.sh — FULL backup of the tower for offline Claude use.
# Includes external/ + external_oss/ + .venv/ so the laptop has everything to read.
# Excludes only what's literally unbackable (sockets, churny tick streams).
set -u
ROOT=/vaults/nvme0/qsb_tower_v1
DEST="/media/ross/SSK Cloud/qsb_tower_full"
TS=$(date -u +%Y-%m-%dT%H%M%SZ)
LOG="$ROOT/logs/intelligence/backup_full_ssk.log"
mkdir -p "$(dirname "$LOG")"

mountpoint -q "/media/ross/SSK Cloud" || { echo "SSK Cloud not mounted"; exit 2; }

mkdir -p "$DEST"
echo "[$TS] FULL backup starting → $DEST" | tee -a "$LOG"

rsync -a --delete --stats \
  --exclude='**/state/qsb_bus.sock' \
  --exclude='data/registries/qsb_*_tick_stream*.jsonl' \
  --exclude='data/registries/qsb_*_journal*.jsonl' \
  --exclude='data/registries/cognitive/' \
  --exclude='logs/intelligence/*.log' \
  --exclude='data/screenshots/' \
  --exclude='**/Saved/' --exclude='**/Intermediate/' --exclude='**/DerivedDataCache/' --exclude='**/Binaries/' \
  --exclude='tools/whatsapp_inbound/auth_data/' \
  --exclude='**/*.bin' --exclude='**/*.safetensors' --exclude='**/*.gguf' \
  "$ROOT/" "$DEST/" 2>&1 | tail -25 | tee -a "$LOG"

RC=${PIPESTATUS[0]}
SIZE=$(du -sh "$DEST" 2>/dev/null | cut -f1)
echo "[$TS] FULL backup done size=$SIZE rsync_rc=$RC" | tee -a "$LOG"
cat >> "$ROOT/data/registries/qsb_f47_team_records.jsonl" <<EOF
{"ts": "$TS", "kind": "ssk_backup_full", "role": "maintenance", "subject": "Full QSB tower → SSK Cloud (for night-shift ThinkPad Claude)", "size": "$SIZE", "rsync_rc": $RC, "dest": "$DEST"}
EOF
exit $RC
