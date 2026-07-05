#!/usr/bin/env bash
# qsb_godot_capture_visual_state.sh — best-effort screenshot capture.
# Tries xwd; reports honestly if no PNG-capable tool is available.
set -uo pipefail
ROOT="${QSB_ROOT:-/vaults/nvme0/qsb_tower_v1}"
OUT_DIR="${ROOT}/data/screenshots/godot_loop"
TS="$(date +%Y%m%d_%H%M%S)"
mkdir -p "${OUT_DIR}"

echo "[capture] looking for QSB Godot window..."
WIN_ID="$(xwininfo -tree -root 2>/dev/null | grep -oE '0x[0-9a-f]+ "QSB[^"]*"' | grep -i godot | head -1 | awk '{print $1}')"

if [ -z "${WIN_ID}" ]; then
  echo "[capture] FAIL — no QSB Godot window found via xwininfo."
  echo "  Visual inspection unavailable this iteration. Loop will proceed using log + registry signals only."
  exit 2
fi
echo "[capture] window id: ${WIN_ID}"

OUT="${OUT_DIR}/godot_loop_${TS}.xwd"
if command -v xwd >/dev/null 2>&1; then
  xwd -id "${WIN_ID}" -out "${OUT}" 2>&1
  if [ -f "${OUT}" ]; then
    echo "[capture] xwd ok: ${OUT}"
    # Try to convert to PNG if ImageMagick exists
    if command -v convert >/dev/null 2>&1; then
      PNG="${OUT_DIR}/godot_loop_${TS}.png"
      convert "${OUT}" "${PNG}" && echo "[capture] converted to: ${PNG}"
    elif command -v magick >/dev/null 2>&1; then
      PNG="${OUT_DIR}/godot_loop_${TS}.png"
      magick "${OUT}" "${PNG}" && echo "[capture] converted to: ${PNG}"
    else
      echo "[capture] note: no convert/magick — .xwd kept; install imagemagick to get PNG"
    fi
    # Report file size as a basic 'we got something' signal
    BYTES="$(stat -c '%s' "${OUT}" 2>/dev/null || echo 0)"
    echo "[capture] size: ${BYTES} bytes"
    exit 0
  fi
fi

echo "[capture] FAIL — capture tool present but did not produce file"
exit 3
