#!/usr/bin/env bash
# qsb_model_floor_secret_scan.sh — scan registries + logs + Godot scripts for
# anything that looks like a real API key. Exits non-zero on any hit.
set -uo pipefail
ROOT="${QSB_ROOT:-/vaults/nvme0/qsb_tower_v1}"
PROJECT="/home/ross/qsb_godot_native_cockpit"
TS="$(date +%Y%m%d_%H%M%S)"
LOG="${ROOT}/data/logs/qsb_model_floor_secret_scan_${TS}.log"
mkdir -p "$(dirname "${LOG}")"

PATTERNS='(sk-[A-Za-z0-9]{16,}|sk-ant-[A-Za-z0-9_-]{16,}|ds-[A-Za-z0-9]{16,}|Bearer +[A-Za-z0-9._-]{12,})'

hits=0
for tree in "${ROOT}/data/registries" "${ROOT}/data/logs" "${PROJECT}/scripts" "${PROJECT}/scenes" "${ROOT}/src/tower/model_floors"; do
  found=$(grep -rEn "${PATTERNS}" "${tree}" 2>/dev/null | grep -v 'REDACTED\|XXX\|TEMPLATE\|template\|placeholder\|pattern\|patterns\|smoke\|scan\|policy\|README\|guide\|setup_guide' || true)
  if [ -n "${found}" ]; then
    echo "${found}" | tee -a "${LOG}"
    n=$(echo "${found}" | wc -l)
    hits=$((hits + n))
  fi
done

# Write summary
cat > "${ROOT}/data/registries/qsb_model_floor_secret_scan_latest.json" <<EOF
{"ok": $([ ${hits} -eq 0 ] && echo true || echo false), "kind":"qsb_model_floor_secret_scan_latest","ts":"${TS}","hits":${hits},"log_path":"${LOG}"}
EOF
echo "secret scan · hits=${hits}"
[ ${hits} -eq 0 ] && exit 0 || exit 1
