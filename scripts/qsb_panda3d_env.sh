#!/usr/bin/env bash
set -Eeuo pipefail

QSB_ROOT="${QSB_ROOT:-/vaults/nvme0/qsb_tower_v1}"
VENV_DIR="$QSB_ROOT/native_cockpit/.venv_3d"

if [ ! -d "$VENV_DIR" ]; then
  echo "ERROR: Panda3D venv missing: $VENV_DIR"
  echo "Run: bash /tmp/qsb_install_3d_engines.sh"
  exit 1
fi

source "$VENV_DIR/bin/activate"
python - <<'PY'
from panda3d.core import PandaSystem
print("Panda3D ready:", PandaSystem.get_version_string())
PY
