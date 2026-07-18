#!/usr/bin/env bash
set -u

DESK="/home/ross/Desktop"
ROOT="$DESK/QSB_CONTROL_RUNS"
STAMP="$(date +%Y%m%d_%H%M%S)"
INBOX="$ROOT/000_IMPORTED_OLD_DESKTOP_OUTPUTS_$STAMP"
LATEST_LINK="$ROOT/LATEST"
LATEST_REPORT="$ROOT/00_LATEST_REPORT.txt"

echo "============================================================"
echo "ORGANISE QSB DESKTOP OUTPUTS"
echo "Desktop: $DESK"
echo "Root:    $ROOT"
echo "Import:  $INBOX"
echo "============================================================"

mkdir -p "$ROOT" "$INBOX/scripts" "$INBOX/reports" "$INBOX/json" "$INBOX/logs" "$INBOX/other"

cat > "$ROOT/README.txt" <<README
QSB CONTROL RUNS

This is the ordered folder for Ross's QSB / Skyscraper control scripts and reports.

LATEST
  Symlink to the newest run folder.

00_LATEST_REPORT.txt
  Copy of the newest important report.

000_IMPORTED_OLD_DESKTOP_OUTPUTS_*
  Old loose Desktop files imported here.

Future reports should go into timestamped folders like:
  YYYYMMDD_HHMMSS_task_name/

Do not scatter qsb_*.txt files loose on the Desktop.
README

move_match(){
  local pattern="$1"
  local dest="$2"

  find "$DESK" -maxdepth 1 -type f -name "$pattern" -print0 2>/dev/null | while IFS= read -r -d '' f; do
    base="$(basename "$f")"
    echo "[MOVE] $base -> $dest/"
    mv -n "$f" "$dest/"
  done
}

echo
echo "===== IMPORT OLD LOOSE FILES ====="

move_match "qsb_*.txt" "$INBOX/reports"
move_match "find_original_claude_hq_dash_*.txt" "$INBOX/reports"
move_match "restore_original_hq_claude_dash_*.txt" "$INBOX/reports"
move_match "claude_api_token_audit_*.txt" "$INBOX/reports"
move_match "claude_api_token_audit_*.json" "$INBOX/json"
move_match "wren_nightly_build_reply_*.json" "$INBOX/json"
move_match "*.log" "$INBOX/logs"

echo
echo "===== MAKE LATEST POINTER ====="

rm -f "$LATEST_LINK"
ln -s "$INBOX" "$LATEST_LINK"

latest_txt="$(find "$INBOX" -type f -name '*.txt' -printf '%T@ %p\n' 2>/dev/null | sort -nr | head -1 | cut -d' ' -f2-)"
if [ -n "${latest_txt:-}" ] && [ -f "$latest_txt" ]; then
  cp -a "$latest_txt" "$LATEST_REPORT"
  echo "[OK] Latest report copied:"
  echo "$LATEST_REPORT"
else
  echo "No txt report found in imported folder yet." > "$LATEST_REPORT"
fi

cat > "$ROOT/new_qsb_run_folder.sh" <<'RUN'
#!/usr/bin/env bash
set -u

TASK="${1:-qsb_run}"
SAFE_TASK="$(echo "$TASK" | tr ' /:' '___' | tr -cd 'A-Za-z0-9_.-')"
STAMP="$(date +%Y%m%d_%H%M%S)"
ROOT="/home/ross/Desktop/QSB_CONTROL_RUNS"
RUN_DIR="$ROOT/${STAMP}_${SAFE_TASK}"

mkdir -p "$RUN_DIR/scripts" "$RUN_DIR/reports" "$RUN_DIR/json" "$RUN_DIR/logs"

rm -f "$ROOT/LATEST"
ln -s "$RUN_DIR" "$ROOT/LATEST"

echo "$RUN_DIR"
RUN

chmod +x "$ROOT/new_qsb_run_folder.sh"

echo
echo "===== DONE ====="
echo "Main folder:"
echo "$ROOT"
echo
echo "Latest folder:"
readlink -f "$LATEST_LINK" 2>/dev/null || true
echo
echo "Latest report:"
echo "$LATEST_REPORT"
echo
echo "Helper for future runs:"
echo "$ROOT/new_qsb_run_folder.sh"
echo
echo "Open it:"
echo "xdg-open '$ROOT' >/dev/null 2>&1 &"
echo "============================================================"
