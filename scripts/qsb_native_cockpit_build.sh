#!/usr/bin/env bash
# QSB Native Cockpit V2 — Standalone executable build (PyInstaller)
# Phase: QSB_NATIVE_COCKPIT_STANDALONE_SKYSCRAPER_PLATFORM_V2

set -uo pipefail
cd /vaults/nvme0/qsb_tower_v1
# shellcheck disable=SC1091
source scripts/qsb_env.sh

if ! python3 -c "import PyInstaller" >/dev/null 2>&1; then
  echo "PyInstaller not installed."
  echo "Install with: pip install pyinstaller"
  exit 2
fi

cd native_cockpit/qt
pyinstaller --onefile \
  --name qsb_native_cockpit \
  --distpath ../build/dist \
  --workpath ../build/work \
  --specpath ../build \
  main.py
echo "Output: native_cockpit/build/dist/qsb_native_cockpit"
