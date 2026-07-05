#!/usr/bin/env bash
set -euo pipefail

cd /vaults/nvme0/qsb_tower_v1

TS="$(date -u +%Y%m%dT%H%M%SZ)"
BACKUP_DIR="data/backups/kernel_ready_${TS}"
ARCHIVE="data/backups/qsb_tower_kernel_ready_${TS}.tar.gz"

mkdir -p "$BACKUP_DIR"

echo "=== QSB TOWER KERNEL-READY SNAPSHOT ==="
echo "Timestamp: $TS"
echo "Backup dir: $BACKUP_DIR"
echo "Archive: $ARCHIVE"

export PYTHONPATH=/vaults/nvme0/qsb_tower_v1/src

echo
echo "=== FINAL PREFLIGHT ==="
bash scripts/final_kernel_preflight.sh | tee "$BACKUP_DIR/final_kernel_preflight.txt"

echo
echo "=== READINESS JSON COPY ==="
cp -f data/registries/kernel_readiness_latest.json "$BACKUP_DIR/kernel_readiness_latest.json" 2>/dev/null || true
cp -f penthouse/kernel_occupancy_acceptance/latest_kernel_readiness_report.json "$BACKUP_DIR/latest_kernel_readiness_report.json" 2>/dev/null || true

echo
echo "=== FORBIDDEN KERNEL FILE CHECK ==="
{
for f in \
  penthouse/qsb_kernel_4_5.py \
  penthouse/kernel.py \
  src/tower/qsb_kernel_4_5.py \
  src/tower/kernel.py
do
  if [ -e "$f" ]; then
    echo "FORBIDDEN PRESENT: $f"
    exit 1
  else
    echo "absent: $f"
  fi
done
} | tee "$BACKUP_DIR/forbidden_kernel_file_check.txt"

echo
echo "=== CREATE ARCHIVE ==="
tar \
  --exclude='./data/backups' \
  --exclude='./.git' \
  -czf "$ARCHIVE" .

sha256sum "$ARCHIVE" | tee "$BACKUP_DIR/archive.sha256"

echo
echo "=== SNAPSHOT COMPLETE ==="
echo "$ARCHIVE"
