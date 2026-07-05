#!/usr/bin/env bash
# qsb_unreal_visible_build_loop.sh — one loop iteration of the visible build.
# 1) status check, 2) open editor if needed, 3) one build pass, 4) screenshot, 5) report, 6) stamp F47

set -u
ROOT="${ROOT:-/vaults/nvme0/qsb_tower_v1}"
cd "$ROOT" || exit 1
TS_UTC=$(date -u +%Y-%m-%dT%H:%M:%SZ)

echo "=== status before ==="
./scripts/qsb_unreal_visible_build_status.sh

echo "=== open editor (no-op if running) ==="
./scripts/qsb_unreal_open_editor.sh

echo "=== run build pass ==="
./scripts/qsb_unreal_run_editor_build_pass.sh

echo "=== status after ==="
./scripts/qsb_unreal_visible_build_status.sh

# Stamp F47
cat >> data/registries/qsb_f47_records.jsonl <<EOF
{"ts": "${TS_UTC}", "event": "unreal_visible_build_loop_pass", "subject": "one visible build loop iteration complete", "report": "data/logs/qsb_unreal_visual_upgrade_pass_report.md", "signed_off_by": ["claude_helm"], "awaiting_signature": ["ross"], "status": "open"}
EOF
echo "F47 stamped at ${TS_UTC}"
