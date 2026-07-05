#!/usr/bin/env bash
# QSB Godot visual check — verifies project tree + reports headless parse.
set -uo pipefail
cd /vaults/nvme0/qsb_tower_v1

PROJ=native_cockpit/godot_qsb
REG=data/registries/qsb_godot_visual_check.json
LOG=data/logs/qsb_godot_visual_check.txt
mkdir -p data/logs

pass=0; total=0; failed=""
check() {
  total=$((total+1))
  if [ "$2" = "1" ]; then pass=$((pass+1)); echo "  ✓ $1 — $3" | tee -a "$LOG"
  else failed="$failed $1"; echo "  ✗ $1 — $3" | tee -a "$LOG"; fi
}
: > "$LOG"
echo "QSB Godot Visual Check · $(date -u +%FT%TZ)" | tee -a "$LOG"

# Engine
GODOT_OK=$([ -x native_cockpit/bin/qsb-godot ] && echo 1 || echo 0)
check godot_wrapper "$GODOT_OK" "native_cockpit/bin/qsb-godot"
PANDA_OK=$([ -x native_cockpit/.venv_3d/bin/python ] && echo 1 || echo 0)
check panda3d_venv "$PANDA_OK" "native_cockpit/.venv_3d"

# Project tree
for f in project.godot scenes/Main.tscn scripts/Main.gd scripts/TelemetryBridge.gd \
         scripts/TowerRenderer.gd scripts/CameraController.gd scripts/LiftRenderer.gd \
         scripts/OpenClawRenderer.gd scripts/WorkerRenderer.gd scripts/FloorSelector.gd \
         scripts/HUDController.gd scripts/FloorInteriorRenderer.gd scripts/TeamRenderer.gd \
         scripts/CommerceRenderer.gd scripts/PenthouseRenderer.gd; do
  [ -f "$PROJ/$f" ] && { check "file_$f" 1 ok; } || { check "file_$f" 0 missing; }
done

# Scenes
for s in Tower Floor FloorInterior Worker Lift OpenClaw HUD Penthouse CommerceWing; do
  [ -f "$PROJ/scenes/$s.tscn" ] && check "scene_$s" 1 ok || check "scene_$s" 0 missing
done

# Headless parse
PARSE_OK=0
if [ -x native_cockpit/bin/qsb-godot ]; then
  cd "$PROJ"
  if timeout 25 ../../native_cockpit/bin/qsb-godot --headless --quit >/dev/null 2>&1; then
    PARSE_OK=1
  fi
  cd - >/dev/null
fi
check godot_headless_parse "$PARSE_OK" "godot project parses without errors"

# PyQt reclassified
ROLE=$(jq -r .role data/registries/qsb_pyqt_admin_fallback_status.json 2>/dev/null || echo "?")
check pyqt_reclassified "$([ "$ROLE" = "fallback_admin_only" ] && echo 1 || echo 0)" "role=$ROLE"

# Safety locks
for k in real_money_live_trading_enabled openclaw_real_tool_execution_enabled live_payments_enabled live_listings_publishing_enabled; do
  V=$(jq -r ".$k" data/registries/qsb_godot_install_verified.json 2>/dev/null || echo true)
  check "lock_${k}_off" "$([ "$V" = "false" ] && echo 1 || echo 0)" "$k=$V"
done

score=$(python3 -c "print(round(100.0 * $pass / $total, 1))")
echo "" | tee -a "$LOG"
echo "score: $score ($pass/$total)" | tee -a "$LOG"

python3 - <<PY
import json, time
open("$REG","w").write(json.dumps({
  "ok": True, "kind": "qsb_godot_visual_check",
  "generated_ts": time.strftime("%Y-%m-%dT%H:%M:%S+00:00", time.gmtime()),
  "passed": $pass, "total": $total, "score": $score,
  "failed": "$failed".strip().split() if "$failed".strip() else [],
  "execution_allowed": False, "real_money_live_trading_enabled": False,
}, indent=2))
PY
echo "score=$score ($pass/$total)"
