#!/usr/bin/env bash
# QSB Panda3D Fallback Cockpit launcher.
set -uo pipefail
cd /vaults/nvme0/qsb_tower_v1

if [ ! -x native_cockpit/.venv_3d/bin/python ]; then
  echo "ERROR: Panda3D venv missing. Run installer."
  exit 2
fi
if [ -z "${DISPLAY:-}" ] && [ -z "${WAYLAND_DISPLAY:-}" ]; then
  echo "ERROR: no DISPLAY"
  exit 3
fi
exec native_cockpit/.venv_3d/bin/python native_cockpit/panda3d_qsb/main.py
