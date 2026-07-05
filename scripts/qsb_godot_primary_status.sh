#!/usr/bin/env bash
# qsb_godot_primary_status.sh — Godot project health snapshot.
set -uo pipefail
ROOT="${QSB_ROOT:-/vaults/nvme0/qsb_tower_v1}"
PROJECT="/home/ross/qsb_godot_native_cockpit"

pass() { printf "  \033[32m✓\033[0m %s\n" "$1"; }
fail() { printf "  \033[31m✗\033[0m %s\n" "$1"; }
warn() { printf "  \033[33m!\033[0m %s\n" "$1"; }

echo "============================================================"
echo "  QSB Godot · Primary Cockpit Status"
echo "============================================================"
echo
echo "Project: ${PROJECT}"
echo

# Files
for f in project.godot scenes/Main.tscn scripts/Main.gd; do
  if [ -f "${PROJECT}/${f}" ]; then pass "${f} present"; else fail "${f} MISSING"; fi
done

# Renderer
RENDERER="$(grep -E 'renderer/rendering_method' "${PROJECT}/project.godot" 2>/dev/null | head -1 | sed 's/.*="\(.*\)"/\1/' || true)"
echo
if [ "${RENDERER}" = "gl_compatibility" ]; then
  warn "renderer: gl_compatibility (llvmpipe software fallback — slower than NVIDIA HW)"
elif [ "${RENDERER}" = "forward_plus" ] || [ "${RENDERER}" = "mobile" ]; then
  pass "renderer: ${RENDERER}"
else
  warn "renderer: ${RENDERER:-(not set)}"
fi

# Scripts inventory
echo
echo "Scripts present:"
EXPECTED_SCRIPTS=(
  Main.gd
  ControlBar.gd
  KernelChatPanel.gd
  KernelChatBridge.gd
  TelemetryBridge.gd
  VoiceControlBridge.gd
  TowerRenderer.gd
  HUDController.gd
  CameraController.gd
  FloorInteraction.gd
  FloorInspector.gd
  OpenClawRenderer.gd
  LiftRenderer.gd
  WorkerRenderer.gd
  EventStreamAnimator.gd
  FloorInteriorRenderer.gd
)
present=0; missing=0
for s in "${EXPECTED_SCRIPTS[@]}"; do
  if [ -f "${PROJECT}/scripts/${s}" ]; then
    pass "${s}"; present=$((present + 1))
  else
    fail "${s}"; missing=$((missing + 1))
  fi
done
echo
echo "  Scripts present: ${present} / ${#EXPECTED_SCRIPTS[@]}"

# Binary
echo
GODOT_BIN=""
if [ -x "${ROOT}/native_cockpit/bin/qsb-godot" ]; then
  GODOT_BIN="${ROOT}/native_cockpit/bin/qsb-godot"
elif command -v godot4 >/dev/null 2>&1; then
  GODOT_BIN="godot4"
elif [ -x /snap/bin/godot-4 ]; then
  GODOT_BIN="/snap/bin/godot-4"
fi
if [ -n "${GODOT_BIN}" ]; then
  pass "Godot binary resolvable at: ${GODOT_BIN}"
else
  fail "Godot binary not found"
fi

# Launch script
if [ -x "${ROOT}/scripts/qsb_godot_run.sh" ]; then
  pass "Launch script: scripts/qsb_godot_run.sh"
else
  fail "Launch script missing: scripts/qsb_godot_run.sh"
fi

echo
echo "Primary cockpit launch command:"
echo "  ./scripts/qsb_launch_primary_cockpit.sh"
