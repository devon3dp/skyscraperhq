#!/usr/bin/env bash
# QSB Godot audit — checks engine + Panda3D fallback availability.
set -uo pipefail
cd /vaults/nvme0/qsb_tower_v1

echo "== QSB Godot/Panda3D Audit =="
if [ -x native_cockpit/bin/qsb-godot ]; then
  V=$(native_cockpit/bin/qsb-godot --version 2>&1 | head -1)
  echo "godot: OK ($V)"
else
  echo "godot: MISSING wrapper"
fi
if [ -x native_cockpit/.venv_3d/bin/python ]; then
  V=$(native_cockpit/.venv_3d/bin/python -c "from panda3d.core import PandaSystem; print(PandaSystem.get_version_string())" 2>&1 | head -1)
  echo "panda3d: OK ($V)"
else
  echo "panda3d: MISSING venv"
fi
for f in native_cockpit/godot_qsb/project.godot \
         native_cockpit/godot_qsb/scenes/Main.tscn \
         native_cockpit/godot_qsb/scripts/Main.gd \
         native_cockpit/godot_qsb/scripts/TelemetryBridge.gd \
         native_cockpit/godot_qsb/scripts/TowerRenderer.gd \
         native_cockpit/godot_qsb/scripts/CameraController.gd; do
  if [ -f "$f" ]; then echo "  ✓ $f"; else echo "  ✗ $f MISSING"; fi
done
echo "PyQt cockpit role: $(jq -r .role data/registries/qsb_pyqt_admin_fallback_status.json 2>/dev/null || echo unknown)"
