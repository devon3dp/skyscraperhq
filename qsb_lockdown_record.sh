#!/usr/bin/env bash
set -euo pipefail

cd /vaults/nvme0/qsb_tower_v1 || exit 1
source scripts/qsb_env.sh 2>/dev/null || true

TS="$(date -u +%Y%m%dT%H%M%SZ)"
MILESTONE="EQSB_KERNEL_MAJOR_DEEP_SYMBOLIC_QUANTUM_CORE_ACTIVE_LOCAL_ONLY_OK"
OUT="data/lockdowns/${TS}_${MILESTONE}"
BACKUP_DIR="data/backups"
ARCHIVE="${BACKUP_DIR}/qsb_${MILESTONE}_${TS}.tar.gz"

mkdir -p "$OUT" "$BACKUP_DIR"

echo "[1/8] Writing lockdown state marker..."

cat > data/registries/qsb_lockdown_state.json <<JSON
{
  "schema_version": "1.0",
  "milestone": "${MILESTONE}",
  "locked_at_utc": "${TS}",
  "qsb_root": "/vaults/nvme0/qsb_tower_v1",
  "dashboard_url": "http://127.0.0.1:8765/?v=unified",
  "kernel_expected_mode": "active_local_only",
  "record_type": "soft_lockdown_snapshot",
  "notes": [
    "This record captures the current QSB/EQSB kernel checkpoint.",
    "The system is not hard-frozen; runtime logs and dashboard state may continue writing.",
    "Use this archive and checksum as the rollback/reference point."
  ],
  "expected_disabled": {
    "worker_execution_enabled": false,
    "provider_execution_enabled": false,
    "openclaw_real_execution_enabled": false,
    "autonomous_dispatch_enabled": false
  }
}
JSON

echo "[2/8] Capturing system and environment facts..."

{
  echo "# QSB Lockdown Summary"
  echo
  echo "Milestone: ${MILESTONE}"
  echo "Timestamp UTC: ${TS}"
  echo "Root: /vaults/nvme0/qsb_tower_v1"
  echo "Dashboard: http://127.0.0.1:8765/?v=unified"
  echo
  echo "## Host"
  hostnamectl 2>/dev/null || true
  echo
  echo "## Kernel"
  uname -a
  echo
  echo "## Python"
  python --version 2>&1 || true
  which python 2>/dev/null || true
  echo
  echo "## Disk"
  df -h / /vaults/nvme0 /vaults/ai 2>/dev/null || df -h
  echo
  echo "## Git"
  git rev-parse HEAD 2>/dev/null || echo "No git HEAD found"
  git status --short 2>/dev/null || true
} > "$OUT/LOCKDOWN_SUMMARY.md"

echo "[3/8] Running preflight/status checks..."

{
  echo "===== final_active_kernel_preflight ====="
  ./scripts/final_active_kernel_preflight.sh 2>&1 || true
  echo
  echo "===== status.sh ====="
  ./status.sh 2>&1 || true
  echo
  echo "===== eqsb_systems_check if present ====="
  if [ -x ./scripts/eqsb_systems_check.sh ]; then
    ./scripts/eqsb_systems_check.sh 2>&1 || true
  else
    echo "eqsb_systems_check.sh not present or not executable"
  fi
  echo
  echo "===== sandbox_autoloop_status if present ====="
  if [ -x ./scripts/sandbox_autoloop_status.sh ]; then
    ./scripts/sandbox_autoloop_status.sh 2>&1 | head -120 || true
  else
    echo "sandbox_autoloop_status.sh not present or not executable"
  fi
} | tee "$OUT/preflight_and_status.txt"

echo "[4/8] Capturing kernel chat verification if available..."

{
  echo "===== Kernel verification prompt ====="
  echo "Kernel, explain your axioms, Guardian, cadence, memory, belief lifecycle, symbolic graph, entropy, quantum signal, hypotheses, contradictions, and why you are not a model."
  echo
  if [ -x ./scripts/qsb_kernel_chat.sh ]; then
    ./scripts/qsb_kernel_chat.sh "Kernel, explain your axioms, Guardian, cadence, memory, belief lifecycle, symbolic graph, entropy, quantum signal, hypotheses, contradictions, and why you are not a model." 2>&1 | head -500 || true
  else
    echo "qsb_kernel_chat.sh not present or not executable"
  fi
} > "$OUT/kernel_chat_verification.txt"

echo "[5/8] Copying critical registries..."

mkdir -p "$OUT/registries" "$OUT/scripts_index" "$OUT/source_index"

find data/registries -maxdepth 1 -type f \
  \( -name "*.json" -o -name "*.jsonl" \) \
  -print0 2>/dev/null | xargs -0 -I{} cp -a "{}" "$OUT/registries/" 2>/dev/null || true

find scripts -maxdepth 1 -type f -print | sort > "$OUT/scripts_index/scripts_files.txt" 2>/dev/null || true
find src rebased_kernel penthouse floors -type f 2>/dev/null | sort > "$OUT/source_index/source_files.txt" || true

echo "[6/8] Creating checksums..."

{
  echo "===== Registry hashes ====="
  find data/registries -type f -print0 2>/dev/null | sort -z | xargs -0 sha256sum 2>/dev/null || true
  echo
  echo "===== Script/source hashes ====="
  find scripts src rebased_kernel penthouse floors \
    -type f \
    ! -path "*/__pycache__/*" \
    -print0 2>/dev/null | sort -z | xargs -0 sha256sum 2>/dev/null || true
} > "$OUT/project_file_hashes.sha256"

find "$OUT" -type f -print0 | sort -z | xargs -0 sha256sum > "$OUT/lockdown_record_hashes.sha256"

echo "[7/8] Creating rollback archive..."

tar \
  --exclude='./.venv' \
  --exclude='./__pycache__' \
  --exclude='./data/backups' \
  --exclude='./.git' \
  -czf "$ARCHIVE" .

sha256sum "$ARCHIVE" | tee "${ARCHIVE}.sha256"

echo "[8/8] Freezing the lockdown record folder read-only..."

chmod -R a-w "$OUT" || true
ln -sfn "$(basename "$OUT")" data/lockdowns/LATEST

echo
echo "============================================================"
echo "QSB LOCKDOWN RECORD COMPLETE"
echo "============================================================"
echo "Milestone : ${MILESTONE}"
echo "Record    : ${OUT}"
echo "Archive   : ${ARCHIVE}"
echo "Checksum  : ${ARCHIVE}.sha256"
echo
echo "Verify archive with:"
echo "sha256sum -c ${ARCHIVE}.sha256"
echo
echo "Open summary with:"
echo "cat ${OUT}/LOCKDOWN_SUMMARY.md"
echo "============================================================"
