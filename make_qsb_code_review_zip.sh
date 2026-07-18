#!/usr/bin/env bash
set -euo pipefail

ROOT="/vaults/nvme0/qsb_tower_v1"
STAMP="$(date +%Y%m%d_%H%M%S)"
PACK="/home/ross/Desktop/qsb_code_review_pack_$STAMP"
ZIP="/home/ross/Desktop/qsb_code_review_pack_$STAMP.zip"

echo "Building QSB code review ZIP..."
echo "Root: $ROOT"
echo "Pack: $PACK"
echo "Zip:  $ZIP"

rm -rf "$PACK"
mkdir -p "$PACK"

cd "$ROOT"

# 1. Main inspection notes
{
  echo "QSB TOWER CODE REVIEW PACK"
  echo "Generated: $(date -Is)"
  echo "Host: $(hostname)"
  echo "Root: $ROOT"
  echo ""
  echo "Main areas to inspect:"
  echo "- Floor 47 rulebook"
  echo "- Boardroom hub"
  echo "- Task council / council files"
  echo "- Town Square / Talent Square / Team Live files"
  echo "- Wren dashboard and local agent"
  echo "- Brain router / CEO mind"
  echo "- Main dashboard server"
  echo "- Registries and recent logs"
} > "$PACK/READ_ME_FIRST.txt"

# 2. Directory map
find "$ROOT" \
  -path "$ROOT/.venv" -prune -o \
  -path "$ROOT/node_modules" -prune -o \
  -path "$ROOT/backups" -prune -o \
  -path "$ROOT/archive" -prune -o \
  -path "$ROOT/_archive" -prune -o \
  -path "$ROOT/photos" -prune -o \
  -path "$ROOT/external_oss" -prune -o \
  -path "$ROOT/__pycache__" -prune -o \
  -print | sed "s|$ROOT/||" | sort > "$PACK/DIRECTORY_MAP.txt"

# 3. Latest smoke test report if present
LATEST_SMOKE="$(ls -t /home/ross/Desktop/qsb_smoke_test_*.txt 2>/dev/null | head -1 || true)"
if [ -n "$LATEST_SMOKE" ]; then
  cp "$LATEST_SMOKE" "$PACK/LATEST_SMOKE_TEST_REPORT.txt"
fi

# 4. Make selected review folders
mkdir -p "$PACK/code"
mkdir -p "$PACK/code/tools"
mkdir -p "$PACK/code/src"
mkdir -p "$PACK/code/floors"
mkdir -p "$PACK/code/config"
mkdir -p "$PACK/code/data_registries"
mkdir -p "$PACK/code/logs"

# 5. Main root files
for f in \
  README.md \
  CLAUDE.md \
  MEMORY.md \
  CHANGELOG.md \
  requirements.txt \
  requirements_qsb_runtime.txt \
  run.sh \
  restart.sh \
  status.sh \
  qsb_router_ceo_mind.py \
  qsb_wren_dash.py \
  qsb_session_diary.md
do
  [ -f "$ROOT/$f" ] && cp "$ROOT/$f" "$PACK/code/" || true
done

# 6. Boardroom / Wren / Council / Task / Square files
find "$ROOT/tools" "$ROOT/src" "$ROOT/floors" "$ROOT/config" "$ROOT/data" "$ROOT/ground" "$ROOT/penthouse" "$ROOT/basement" "$ROOT/roof" \
  -type f 2>/dev/null \
  \( \
    -iname "*boardroom*" -o \
    -iname "*task*council*" -o \
    -iname "*task*board*" -o \
    -iname "*council*" -o \
    -iname "*town*square*" -o \
    -iname "*talent*square*" -o \
    -iname "*team_live*" -o \
    -iname "*wren*" -o \
    -iname "*rulebook*" -o \
    -iname "*router*" -o \
    -iname "*dashboard*" -o \
    -iname "*server*" \
  \) \
  | while read -r file; do
      rel="${file#$ROOT/}"
      mkdir -p "$PACK/code/$(dirname "$rel")"
      cp "$file" "$PACK/code/$rel"
    done

# 7. Important Floor 47 files
if [ -d "$ROOT/floors/floor_47_executive_operations_department" ]; then
  mkdir -p "$PACK/code/floors/floor_47_executive_operations_department"
  cp -a "$ROOT/floors/floor_47_executive_operations_department/." "$PACK/code/floors/floor_47_executive_operations_department/" 2>/dev/null || true
fi

# 8. Registries: copy small json/jsonl/txt/md files only
if [ -d "$ROOT/data/registries" ]; then
  find "$ROOT/data/registries" -maxdepth 1 -type f \
    \( -iname "*.json" -o -iname "*.jsonl" -o -iname "*.txt" -o -iname "*.md" \) \
    -size -10M \
    | while read -r file; do
        cp "$file" "$PACK/code/data_registries/" || true
      done
fi

# 9. Recent logs, not huge ones
find "$ROOT" \
  -path "$ROOT/.venv" -prune -o \
  -path "$ROOT/node_modules" -prune -o \
  -path "$ROOT/backups" -prune -o \
  -path "$ROOT/archive" -prune -o \
  -path "$ROOT/_archive" -prune -o \
  -type f \
  \( -iname "*.log" -o -iname "*error*" -o -iname "*stderr*" \) \
  -size -5M \
  -printf '%T@ %p\n' 2>/dev/null \
  | sort -nr | head -30 | cut -d' ' -f2- \
  | while read -r file; do
      rel="${file#$ROOT/}"
      mkdir -p "$PACK/code/logs/$(dirname "$rel")"
      cp "$file" "$PACK/code/logs/$rel" || true
    done

# 10. Python syntax report for included Python files
{
  echo "PYTHON SYNTAX CHECK"
  echo "Generated: $(date -Is)"
  echo ""
  find "$PACK/code" -type f -iname "*.py" | sort | while read -r py; do
    if python3 -m py_compile "$py" 2>/tmp/qsb_zip_py_err.txt; then
      echo "[OK]   ${py#$PACK/}"
    else
      echo "[FAIL] ${py#$PACK/}"
      cat /tmp/qsb_zip_py_err.txt
      echo ""
    fi
  done
} > "$PACK/PYTHON_SYNTAX_REPORT.txt"

rm -f /tmp/qsb_zip_py_err.txt

# 11. File list inside pack
find "$PACK" -type f | sed "s|$PACK/||" | sort > "$PACK/ZIP_CONTENTS.txt"

# 12. Create single zip
cd "/home/ross/Desktop"
rm -f "$ZIP"

if command -v zip >/dev/null 2>&1; then
  zip -r -9 "$ZIP" "$(basename "$PACK")" >/dev/null
else
  python3 - <<PY
import shutil
shutil.make_archive("$PACK", "zip", "/home/ross/Desktop", "$(basename "$PACK")")
PY
fi

echo ""
echo "DONE."
echo "Attach this one file:"
echo "$ZIP"
echo ""
ls -lh "$ZIP"
