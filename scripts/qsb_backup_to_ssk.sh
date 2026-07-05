#!/usr/bin/env bash
# qsb_backup_to_ssk.sh — nightly backup of QSB tower to SSK Cloud drive.
# Mirrors current state (with delete) + optional dated snapshot copy.
#
# Mode A (default): mirror — fast, always-current, no history.
# Mode B (--snapshot): also drop a dated tree alongside (full copy, eats space).
#
# Excludes: .venv, vendored OSS repos, UE build artifacts, churny dynamic JSONLs,
# logs, screenshots, model weight caches.

set -u
ROOT=/vaults/nvme0/qsb_tower_v1
DEST_BASE="/media/ross/SSK Cloud/qsb_tower_backups"
MIRROR="$DEST_BASE/mirror"
SNAP="$DEST_BASE/snapshots"
TS=$(date -u +%Y-%m-%dT%H%M%SZ)
LOG_DIR="$ROOT/logs/intelligence"
LOG="$LOG_DIR/backup_ssk.log"
mkdir -p "$LOG_DIR"

[[ -d "$DEST_BASE" ]] || mkdir -p "$DEST_BASE" || { echo "destination unmountable"; exit 2; }

# Pre-flight: drive present?
if ! mountpoint -q "/media/ross/SSK Cloud"; then
  echo "[$TS] SSK Cloud NOT mounted — aborting" | tee -a "$LOG"
  exit 3
fi

echo "[$TS] backup starting → $MIRROR" | tee -a "$LOG"

# rsync the tower (excluding heavy/churny paths)
rsync -a --delete --stats \
  --exclude='.venv/' \
  --exclude='external/' \
  --exclude='external_oss/' \
  --exclude='__pycache__/' \
  --exclude='*.pyc' \
  --exclude='**/Saved/' \
  --exclude='**/Intermediate/' \
  --exclude='**/DerivedDataCache/' \
  --exclude='**/Binaries/' \
  --exclude='data/registries/cognitive/' \
  --exclude='data/registries/qsb_*_journal*.jsonl' \
  --exclude='data/registries/qsb_*_tick_stream*.jsonl' \
  --exclude='data/registries/wren_rag/' \
  --exclude='data/registries/team_memory_*/' \
  --exclude='data/registries/f47_snapshots/' \
  --exclude='data/registries/pitstops/tmp/' \
  --exclude='logs/' \
  --exclude='data/screenshots/' \
  --exclude='data/logs/*.log' \
  --exclude='tools/galaxy_apks/' \
  --exclude='tools/whatsapp_inbound/auth_data/' \
  --exclude='hf_downloads/' \
  --exclude='*.bin' --exclude='*.safetensors' --exclude='*.gguf' --exclude='*.onnx' \
  --exclude='*.swp' --exclude='*~' \
  "$ROOT/" "$MIRROR/" 2>&1 | tail -20 | tee -a "$LOG"

RC=${PIPESTATUS[0]}
SIZE=$(du -sh "$MIRROR" 2>/dev/null | cut -f1)
echo "[$TS] mirror size: $SIZE  rsync_rc: $RC" | tee -a "$LOG"

# Optional weekly snapshot (Sunday only, in addition to mirror)
if [[ "${1:-}" == "--snapshot" ]] || [[ "$(date +%u)" == "7" ]]; then
  SNAP_DIR="$SNAP/$TS"
  echo "[$TS] also taking snapshot → $SNAP_DIR" | tee -a "$LOG"
  mkdir -p "$SNAP_DIR"
  cp -a "$MIRROR/." "$SNAP_DIR/" 2>>"$LOG"
  echo "[$TS] snapshot done: $(du -sh "$SNAP_DIR" | cut -f1)" | tee -a "$LOG"
fi

# Stamp F47
cat >> "$ROOT/data/registries/qsb_f47_team_records.jsonl" <<EOF
{"ts": "$TS", "kind": "ssk_backup", "role": "maintenance", "subject": "QSB tower → SSK Cloud mirror", "mirror_size": "$SIZE", "rsync_rc": $RC, "dest": "$MIRROR"}
EOF

echo "[$TS] backup done" | tee -a "$LOG"
exit $RC
