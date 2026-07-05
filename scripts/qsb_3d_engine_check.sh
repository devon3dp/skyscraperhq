#!/usr/bin/env bash
set -Eeuo pipefail

QSB_ROOT="${QSB_ROOT:-/vaults/nvme0/qsb_tower_v1}"
NATIVE_DIR="$QSB_ROOT/native_cockpit"
VENV_DIR="$NATIVE_DIR/.venv_3d"
REG_DIR="$QSB_ROOT/data/registries"
LOG_DIR="$QSB_ROOT/data/logs"

mkdir -p "$REG_DIR" "$LOG_DIR"

echo "== QSB 3D ENGINE CHECK =="

GODOT_OK=false
PANDA_OK=false

if "$NATIVE_DIR/bin/qsb-godot" --version >/tmp/qsb_godot_version.txt 2>&1; then
  GODOT_OK=true
  GODOT_VERSION="$(cat /tmp/qsb_godot_version.txt | head -1)"
else
  GODOT_VERSION="missing"
fi

if [ -x "$VENV_DIR/bin/python" ]; then
  if "$VENV_DIR/bin/python" - <<'PY' >/tmp/qsb_panda_version.txt 2>&1
from panda3d.core import PandaSystem
print(PandaSystem.get_version_string())
PY
  then
    PANDA_OK=true
    PANDA_VERSION="$(cat /tmp/qsb_panda_version.txt | head -1)"
  else
    PANDA_VERSION="import_failed"
  fi
else
  PANDA_VERSION="venv_missing"
fi

cat > "$REG_DIR/qsb_3d_engine_status.json" <<JSON
{
  "godot_ok": $GODOT_OK,
  "godot_version": "$GODOT_VERSION",
  "panda3d_ok": $PANDA_OK,
  "panda3d_version": "$PANDA_VERSION",
  "godot_project": "$NATIVE_DIR/godot_qsb",
  "panda3d_venv": "$VENV_DIR",
  "pyqt_cockpit_role": "fallback_admin_only",
  "target_main_graphics_engine": "Godot",
  "fallback_graphics_engine": "Panda3D",
  "live_trading_enabled": false,
  "commerce_publish_enabled": false,
  "money_spend_enabled": false
}
JSON

cat "$REG_DIR/qsb_3d_engine_status.json" | jq .
