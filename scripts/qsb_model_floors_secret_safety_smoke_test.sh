#!/usr/bin/env bash
set -uo pipefail
ROOT="${QSB_ROOT:-/vaults/nvme0/qsb_tower_v1}"
TS="$(date +%Y%m%d_%H%M%S)"
OUT="${ROOT}/data/registries/qsb_model_floors_secret_safety_smoke_test_latest.json"
# Run the existing secret scan
"${ROOT}/scripts/qsb_model_floor_secret_scan.sh" >/dev/null 2>&1
hits=$(jq -r '.hits' "${ROOT}/data/registries/qsb_model_floor_secret_scan_latest.json")
cat > "${OUT}" <<EOF
{"ok": $([ "${hits}" -eq 0 ] && echo true || echo false), "kind":"qsb_model_floors_secret_safety_smoke_test_latest","ts":"${TS}","scan_hits":${hits}}
EOF
cat "${OUT}"
[ "${hits}" -eq 0 ] && exit 0 || exit 1
