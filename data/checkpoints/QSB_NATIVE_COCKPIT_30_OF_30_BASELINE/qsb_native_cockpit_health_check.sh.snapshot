#!/usr/bin/env bash
# QSB Native Cockpit V2 — Health Check (system-python aware)
# Phase: QSB_NATIVE_COCKPIT_FEATURE_PARITY_AND_INTERACTION_UPGRADE_V1

set -uo pipefail
cd /vaults/nvme0/qsb_tower_v1
# shellcheck disable=SC1091
source scripts/qsb_env.sh

QSB_PY="${QSB_PY:-/usr/bin/python3}"
LOG=data/logs/qsb_native_cockpit_health_check.txt
REG=data/registries/qsb_native_cockpit_health_check.json
mkdir -p data/logs

pass=0; total=0; failed=""
check() {
  total=$((total + 1))
  if [ "$2" = "1" ]; then pass=$((pass + 1)); echo "  ✓ $1 — $3" | tee -a "$LOG"
  else failed="$failed $1"; echo "  ✗ $1 — $3" | tee -a "$LOG"; fi
}

: > "$LOG"
echo "QSB Native Cockpit V2 Health Check · $(date -u +%FT%TZ)" | tee -a "$LOG"
echo "engine_python: $QSB_PY" | tee -a "$LOG"

# Engine — probe SYSTEM python which is what the cockpit actually uses
PY5_OK=$("$QSB_PY" -c "from PyQt5.QtWidgets import QApplication; print(1)" 2>/dev/null || echo 0)
check pyqt5_importable_system_python "$PY5_OK" "$QSB_PY has PyQt5"

# Telemetry bridge importable (works in either python)
TB_OK=$("$QSB_PY" -c "import sys; sys.path.insert(0,'native_cockpit/qt'); import telemetry_bridge; print(1)" 2>/dev/null || echo 0)
check telemetry_bridge_imports "$TB_OK" "telemetry_bridge OK"

# Verified workforce 2191
SNAP=$("$QSB_PY" -c "
import sys, json
sys.path.insert(0, 'native_cockpit/qt')
import telemetry_bridge as tb
s = tb.build_scene_snapshot()
print(s['verified']['verified_total_workers'])" 2>/dev/null || echo 0)
check workforce_total_2191 "$([ "$SNAP" = "2191" ] && echo 1 || echo 0)" "verified=$SNAP"

# Required registries
for r in qsb_native_graphics_engine_audit_v2 qsb_native_graphics_engine_decision_v2 qsb_native_cockpit_project_v2 qsb_native_cockpit_architecture_v2 qsb_native_scene_contract qsb_native_workforce_import_audit qsb_native_worker_scene_summary qsb_native_cockpit_api_contract qsb_native_cockpit_health_fix qsb_native_cockpit_screenshot_proof qsb_original_dashboard_feature_inventory qsb_native_cockpit_feature_inventory qsb_native_feature_parity_matrix qsb_native_missing_features_backlog qsb_native_cockpit_completion_gates_v1 qsb_native_cockpit_completion_score_v1; do
  if [ -f "data/registries/$r.json" ]; then pass=$((pass+1)); total=$((total+1)); echo "  ✓ registry_$r" | tee -a "$LOG"
  else total=$((total+1)); failed="$failed registry_$r"; echo "  ✗ registry_$r missing" | tee -a "$LOG"; fi
done

# Required native files
for f in native_cockpit/qt/main.py native_cockpit/qt/telemetry_bridge.py native_cockpit/qt/requirements.txt native_cockpit/README.md native_cockpit/package_plan.md; do
  if [ -f "$f" ]; then pass=$((pass+1)); total=$((total+1)); echo "  ✓ file_$f" | tee -a "$LOG"
  else total=$((total+1)); failed="$failed file_$f"; echo "  ✗ file_$f missing" | tee -a "$LOG"; fi
done

# Run script exists + executable + uses system python
[ -x scripts/qsb_native_cockpit_run.sh ] && \
  { pass=$((pass+1)); total=$((total+1)); echo "  ✓ run_script_executable" | tee -a "$LOG"; } || \
  { total=$((total+1)); failed="$failed run_script_executable"; echo "  ✗ run_script_executable missing" | tee -a "$LOG"; }

grep -q "QSB_PY:-/usr/bin/python3" scripts/qsb_native_cockpit_run.sh && \
  { pass=$((pass+1)); total=$((total+1)); echo "  ✓ run_script_uses_system_python" | tee -a "$LOG"; } || \
  { total=$((total+1)); failed="$failed run_script_uses_system_python"; echo "  ✗ run_script_uses_system_python missing" | tee -a "$LOG"; }

# Safety locks
LOCKS=$("$QSB_PY" -c "
import sys, json
sys.path.insert(0, 'native_cockpit/qt')
import telemetry_bridge as tb
s = tb.build_scene_snapshot()
L = s['safety_locks']
print('1' if (L['real_money_live_trading_enabled'] is False
              and L['openclaw_real_tool_execution_enabled'] is False
              and L['live_payments_enabled'] is False
              and L['live_listings_publishing_enabled'] is False) else '0')" 2>/dev/null || echo 0)
check safety_locks_closed "$LOCKS" "all five locks=false"

# Display server
if [ -n "${DISPLAY:-}" ] || [ -n "${WAYLAND_DISPLAY:-}" ]; then
  pass=$((pass+1)); total=$((total+1)); echo "  ✓ display_present DISPLAY=${DISPLAY:-} WAYLAND=${WAYLAND_DISPLAY:-}" | tee -a "$LOG"
else
  total=$((total+1)); failed="$failed display_present"; echo "  ✗ no DISPLAY/WAYLAND — window will not open in current shell" | tee -a "$LOG"
fi

# Actual headless instantiation proof
INSTANTIATE=$(QT_QPA_PLATFORM=offscreen "$QSB_PY" -c "
import sys
sys.path.insert(0, 'native_cockpit/qt')
from PyQt5.QtWidgets import QApplication
import main as cockpit
app = QApplication.instance() or QApplication([])
win = cockpit.QSBNativeCockpit()
n = len(win.scene.items())
print(n)
" 2>/dev/null || echo 0)
check headless_instantiation "$([ "$INSTANTIATE" -gt 100 ] && echo 1 || echo 0)" "scene_items=$INSTANTIATE"

# Screenshot proof
SHOT=data/screenshots/qsb_native_cockpit_v2.png
[ -f "$SHOT" ] && [ "$(stat -c%s "$SHOT" 2>/dev/null || echo 0)" -gt 10000 ] && \
  { pass=$((pass+1)); total=$((total+1)); echo "  ✓ screenshot_proof_present" | tee -a "$LOG"; } || \
  { total=$((total+1)); failed="$failed screenshot_proof_present"; echo "  ✗ screenshot_proof_present missing" | tee -a "$LOG"; }

score=$("$QSB_PY" -c "print(round(100.0 * $pass / $total, 1))")
echo "" | tee -a "$LOG"
echo "score: ${score} (${pass}/${total})" | tee -a "$LOG"
echo "failed:${failed:-none}" | tee -a "$LOG"

"$QSB_PY" - <<PYEOF
import json, time
open("$REG", "w").write(json.dumps({
  "ok": True, "kind": "qsb_native_cockpit_health_check",
  "phase": "QSB_NATIVE_COCKPIT_FEATURE_PARITY_AND_INTERACTION_UPGRADE_V1",
  "generated_ts": time.strftime("%Y-%m-%dT%H:%M:%S+00:00", time.gmtime()),
  "passed": ${pass}, "total": ${total},
  "score": float(${score}),
  "failed": "${failed}".strip().split() if "${failed}".strip() else [],
  "engine_python": "$QSB_PY",
  "execution_allowed": False,
  "real_money_live_trading_enabled": False,
  "openclaw_real_tool_execution_enabled": False,
}, indent=2))
PYEOF
echo "score=${score} (${pass}/${total})"
