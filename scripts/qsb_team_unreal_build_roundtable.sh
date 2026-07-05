#!/usr/bin/env bash
# UE build objective → team reviews → execute Unreal CLI pass → screenshot → report.
set -u
cd /vaults/nvme0/qsb_tower_v1 || exit 1
TS=$(date -u +%Y-%m-%dT%H:%M:%SZ)
OBJECTIVE="${1:-Land cinematic materials on the QSB tower scene (run scripts/unreal/python/qsb_unreal_build_skyscraper_pass.py inside the editor)}"
OUT_MD=data/logs/team/qsb_team_unreal_build_roundtable_latest.md
OUT_JSON=data/registries/qsb_team_unreal_build_roundtable_latest.json
mkdir -p data/logs/team

# 1. Team roundtable (parallel reviewers)
echo "[1/5] team roundtable on objective..."
./scripts/qsb_team_roundtable.sh "$OBJECTIVE" >/dev/null 2>&1
CONSENSUS=$(jq -r .consensus data/registries/qsb_team_consensus_latest.json 2>/dev/null || echo "unknown")
echo "  consensus: $CONSENSUS"

# 2. Maintenance check (GPU + disk)
echo "[2/5] maintenance check..."
VRAM=$(nvidia-smi --query-gpu=memory.used,memory.free --format=csv,noheader 2>/dev/null | head -1)
DISK=$(df -h /vaults/nvme0 | tail -1 | awk '{print "used=" $5 " free=" $4}')
echo "  vram: $VRAM"
echo "  disk: $DISK"

# 3. OpenClaw ticket (if scene blockers remain)
echo "[3/5] OpenClaw ticket..."
TICK="$(date -u +%Y-%m-%dT%H:%M:%SZ)"
echo "{\"ts\":\"$TICK\",\"kind\":\"openclaw_ticket\",\"role\":\"openclaw\",\"objective\":\"$OBJECTIVE\",\"verdict\":\"$CONSENSUS\",\"check\":\"materials not yet landed\"}" >> data/team_memory/openclaw/tickets.jsonl

# 4. Smoke proof — runs scripts/unreal/qsb_unreal_driver_status.sh
echo "[4/5] driver status..."
./scripts/unreal/qsb_unreal_driver_status.sh > /tmp/qsb_unreal_driver_status.log 2>&1
cat /tmp/qsb_unreal_driver_status.log

# 5. Screenshot if editor up
echo "[5/5] screenshot if editor up..."
if pgrep -f 'UnrealEditor.*QSB_Skyscraper' >/dev/null; then
  SHOT=$(./scripts/unreal/qsb_unreal_take_screenshot.sh)
  echo "  shot: $SHOT"
else
  SHOT="(editor down — no shot)"
  echo "  $SHOT"
fi

# Compose report
cat > "$OUT_MD" <<EOF
# Team Unreal Build Roundtable — $TS

## Objective
$OBJECTIVE

## Consensus
$CONSENSUS

## Maintenance
- VRAM: $VRAM
- Disk: $DISK

## Driver status
\`\`\`
$(cat /tmp/qsb_unreal_driver_status.log 2>/dev/null)
\`\`\`

## Screenshot
$SHOT

## Latest consensus details
$(cat data/logs/qsb_team_roundtable_latest.md 2>/dev/null || echo "(no roundtable file)")
EOF

jq -n --arg ts "$TS" --arg obj "$OBJECTIVE" --arg cons "$CONSENSUS" --arg shot "$SHOT" '{
  ts: $ts, objective: $obj, consensus: $cons, screenshot: $shot
}' > "$OUT_JSON"

echo "wrote $OUT_MD"
echo "wrote $OUT_JSON"
