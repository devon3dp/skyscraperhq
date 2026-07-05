#!/usr/bin/env bash
# QSB Native Cockpit V2 — Launcher (with system-Python PyQt5 fix)
# Phase: QSB_NATIVE_COCKPIT_FEATURE_PARITY_AND_INTERACTION_UPGRADE_V1
#
# Uses the SYSTEM python interpreter (/usr/bin/python3) because the
# project's .venv does not have PyQt5 installed — PyQt5 ships via apt
# in /usr/lib/python3/dist-packages/PyQt5 and only the system Python
# can see it.

set -uo pipefail
cd /vaults/nvme0/qsb_tower_v1

# Source project env for PYTHONPATH but force system python for Qt.
# shellcheck disable=SC1091
source scripts/qsb_env.sh

QSB_PY="${QSB_PY:-/usr/bin/python3}"
LOG=data/logs/native_cockpit_launch.log
STATUS=data/registries/qsb_native_cockpit_status.json
mkdir -p data/logs

if ! "$QSB_PY" -c "from PyQt5.QtWidgets import QApplication" >/dev/null 2>&1; then
  echo "ERROR: System python ($QSB_PY) cannot import PyQt5." | tee -a "$LOG"
  echo "Install with: sudo apt install python3-pyqt5" | tee -a "$LOG"
  echo "Fallback URL: http://127.0.0.1:8765/?v=next3d&floor=55"
  exit 2
fi

if [ -z "${DISPLAY:-}" ] && [ -z "${WAYLAND_DISPLAY:-}" ]; then
  echo "WARNING: no DISPLAY / WAYLAND_DISPLAY — Qt window will not open." | tee -a "$LOG"
  echo "Open browser fallback: http://127.0.0.1:8765/?v=next3d&floor=55"
  exit 3
fi

if curl -s -o /dev/null -w "%{http_code}" http://127.0.0.1:8765/api/unified 2>/dev/null | grep -q 200; then
  echo "Backend available at :8765 ✓"
else
  echo "Backend not running — cockpit will read local registries only."
fi

ts=$(date -u +%FT%TZ)
echo "[$ts] launching native cockpit (python=$QSB_PY)" | tee -a "$LOG"

"$QSB_PY" - <<PYEOF
import json, time
from pathlib import Path
p = Path("$STATUS")
s = json.loads(p.read_text())
s["last_launch_ts"] = time.strftime("%Y-%m-%dT%H:%M:%S+00:00", time.gmtime())
s["last_launch_result"] = "launching"
s["engine_python"] = "$QSB_PY"
p.write_text(json.dumps(s, indent=2))
PYEOF

exec "$QSB_PY" native_cockpit/qt/main.py
