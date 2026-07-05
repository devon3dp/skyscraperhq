#!/usr/bin/env bash
# qsb_unreal_run_editor_build_pass.sh — apply one visual upgrade pass to the UE scene.
# Each invocation = one improvement, then save level, then take screenshot, then report.

set -u
ROOT="${ROOT:-/vaults/nvme0/qsb_tower_v1}"
cd "$ROOT" || exit 1
TS_UTC=$(date -u +%Y-%m-%dT%H:%M:%SZ)

# Pre-condition: editor + TCP up
./scripts/qsb_unreal_open_editor.sh

# Run the upgrade pass — see scripts/qsb_unreal_apply_visual_upgrade_pass.py
PRE_SHOT=/tmp/qsb_pre_$(date -u +%Y%m%dT%H%M%SZ).png
./scripts/qsb_unreal_take_viewport_screenshot.sh "$PRE_SHOT" || true

.venv/bin/python3 scripts/qsb_unreal_apply_visual_upgrade_pass.py 2>&1 | tee /tmp/qsb_upgrade_pass.log

POST_SHOT=/tmp/qsb_post_$(date -u +%Y%m%dT%H%M%SZ).png
./scripts/qsb_unreal_take_viewport_screenshot.sh "$POST_SHOT" || true

REPORT=data/logs/qsb_unreal_visual_upgrade_pass_report.md
mkdir -p data/logs
cat > "$REPORT" <<EOF
# Visual Upgrade Pass — ${TS_UTC}

- Pre-shot:  ${PRE_SHOT}
- Post-shot: ${POST_SHOT}
- Pass log:  /tmp/qsb_upgrade_pass.log (last 30 lines below)

\`\`\`
$(tail -30 /tmp/qsb_upgrade_pass.log)
\`\`\`
EOF
echo "report: $REPORT"
