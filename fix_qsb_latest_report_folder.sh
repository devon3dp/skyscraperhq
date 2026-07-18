#!/usr/bin/env bash
set -u

ROOT="/home/ross/Desktop/QSB_CONTROL_RUNS"
SEND="$ROOT/00_SEND_THIS_TO_CHATGPT"
ARCHIVE="$ROOT/99_IMPORTED_OLD_DESKTOP_OUTPUTS"

mkdir -p "$SEND" "$ARCHIVE"

echo "============================================================"
echo "FIX QSB LATEST REPORT FOLDER"
echo "Root: $ROOT"
echo "Send folder: $SEND"
echo "============================================================"

# Rename old confusing import folders out of the way.
find "$ROOT" -maxdepth 1 -type d -name '000_IMPORTED_OLD_DESKTOP_OUTPUTS_*' -print0 2>/dev/null | while IFS= read -r -d '' d; do
  base="$(basename "$d")"
  echo "[MOVE OLD IMPORT] $base -> 99_IMPORTED_OLD_DESKTOP_OUTPUTS/"
  mv -n "$d" "$ARCHIVE/"
done

# Find newest actual report from any run folder, not from old imported archive.
latest_report="$(
  find "$ROOT" -mindepth 3 -type f -name '*.txt' \
    ! -path "$ARCHIVE/*" \
    ! -path "$SEND/*" \
    -printf '%T@ %p\n' 2>/dev/null \
  | sort -nr \
  | head -1 \
  | cut -d' ' -f2-
)"

if [ -z "$latest_report" ] || [ ! -f "$latest_report" ]; then
  echo "[WARN] No latest report found yet."
  echo "No latest report found yet." > "$SEND/LATEST_REPORT.txt"
else
  echo "[OK] Latest report found:"
  echo "$latest_report"

  cp -a "$latest_report" "$SEND/LATEST_REPORT.txt"
  cp -a "$latest_report" "$ROOT/00_LATEST_REPORT.txt"

  {
    echo "QSB LATEST REPORT POINTER"
    echo "Updated: $(date -Is)"
    echo
    echo "Latest report copied to:"
    echo "$SEND/LATEST_REPORT.txt"
    echo
    echo "Original report:"
    echo "$latest_report"
    echo
    echo "Send this file back to ChatGPT:"
    echo "$SEND/LATEST_REPORT.txt"
  } > "$SEND/README_SEND_THIS.txt"

  rm -f "$ROOT/LATEST_REPORT.txt"
  ln -s "$SEND/LATEST_REPORT.txt" "$ROOT/LATEST_REPORT.txt" 2>/dev/null || true
fi

# Make a visible shortcut text file in the root.
cat > "$ROOT/OPEN_THIS_FOLDER.txt" <<TXT
Open this folder and send the file LATEST_REPORT.txt back to ChatGPT:

$SEND

Latest report file:

$SEND/LATEST_REPORT.txt
TXT

echo
echo "============================================================"
echo "DONE"
echo "Open this folder:"
echo "$SEND"
echo
echo "Send this file:"
echo "$SEND/LATEST_REPORT.txt"
echo "============================================================"

xdg-open "$SEND" >/dev/null 2>&1 &
