#!/usr/bin/env bash
set -u

ROOT="/vaults/nvme0/qsb_tower_v1"
STAMP="$(date +%Y%m%d_%H%M%S)"
REPORT="/home/ross/Desktop/find_original_claude_hq_dash_$STAMP.txt"

exec > >(tee "$REPORT") 2>&1

echo "============================================================"
echo "FIND ORIGINAL CLAUDE HQ DASHBOARD — READ ONLY"
echo "Generated: $(date -Is)"
echo "Root: $ROOT"
echo "Report: $REPORT"
echo "============================================================"

cd "$ROOT" || exit 1

echo
echo "===== 1. CURRENT PROCESSES / PORTS ====="
ps aux | grep -Ei "claude|hq|dash|dashboard|8850|boardroom|wren" | grep -v grep || true
echo
ss -ltnp | grep -E ':(8850|8851|8852|8765|9100|9110|9000|9200|9201|9202)\b' || true

echo
echo "===== 2. FILES WITH HQ / CLAUDE / DASH NAMES ====="
find . \
  -path './.git' -prune -o \
  -path './.venv' -prune -o \
  -path './venv' -prune -o \
  -path './node_modules' -prune -o \
  -type f \( \
    -iname '*claude*' -o \
    -iname '*hq*' -o \
    -iname '*dash*' -o \
    -iname '*dashboard*' \
  \) -print | sort | head -300

echo
echo "===== 3. FILES MENTIONING PORT 8850 ====="
grep -RIn --exclude-dir=.git --exclude-dir=.venv --exclude-dir=venv --exclude-dir=node_modules \
  "8850" . 2>/dev/null | head -260

echo
echo "===== 4. FILES MENTIONING HQ-Claude DASH ====="
grep -RIn --exclude-dir=.git --exclude-dir=.venv --exclude-dir=venv --exclude-dir=node_modules \
  -E "HQ-Claude|hq_claude|HQ dash|Claude dash|HQ dashboard|Claude HQ|HQ-Bench" . 2>/dev/null | head -320

echo
echo "===== 5. START / RUN SCRIPTS THAT MAY LAUNCH HQ DASH ====="
find . \
  -path './.git' -prune -o \
  -path './.venv' -prune -o \
  -path './venv' -prune -o \
  -type f \( -iname 'run*' -o -iname 'start*' -o -iname '*launch*' -o -iname '*restart*' \) \
  -print | sort | while read -r f; do
    if grep -qiE "8850|hq|claude|dashboard|dash" "$f" 2>/dev/null; then
      echo "--- $f"
      sed -n '1,180p' "$f"
    fi
  done

echo
echo "===== 6. LOGS MENTIONING HQ DASH / 8850 ====="
grep -RIn --exclude-dir=.git --exclude-dir=.venv --exclude-dir=venv \
  -E "8850|HQ-Claude|hq_claude|HQ dash|Claude dashboard|HQ-Bench" logs data tools 2>/dev/null | tail -260

echo
echo "===== 7. BOARDROOM LINK HEALTH DEFINITIONS ====="
grep -RIn --exclude-dir=.git --exclude-dir=.venv --exclude-dir=venv \
  -E "HQ-Claude|127.0.0.1:8850|/proxy/hq|proxy/hq" tools src data 2>/dev/null | head -260

echo
echo "===== 8. HISTORICAL PROOF / SELF DASHBOARDS ====="
find "$ROOT" /vaults/nvme0/qsb_skyscraper 2>/dev/null \
  -path '*/.git' -prune -o \
  -path '*/.venv' -prune -o \
  -path '*/venv' -prune -o \
  -type f \( -iname '*8850*' -o -iname '*hq*' -o -iname '*claude*' -o -iname '*dashboard*' \) \
  -print | sort | head -300

echo
echo "===== 9. CANDIDATE PYTHON DASHBOARD FILES QUICK HEADERS ====="
find . \
  -path './.git' -prune -o \
  -path './.venv' -prune -o \
  -path './venv' -prune -o \
  -type f -name '*.py' -print | while read -r f; do
    if grep -qiE "ThreadingHTTPServer|HTTPServer|Flask|FastAPI|streamlit|8850|HQ-Claude|hq_claude|HQ dashboard|Claude dashboard" "$f" 2>/dev/null; then
      echo "--- $f"
      grep -nE "ThreadingHTTPServer|HTTPServer|Flask|FastAPI|streamlit|8850|HQ-Claude|hq_claude|HQ dashboard|Claude dashboard|add_argument\\(\"--port\"" "$f" 2>/dev/null | head -40
    fi
  done

echo
echo "============================================================"
echo "READ-ONLY SEARCH COMPLETE"
echo "Report:"
echo "$REPORT"
echo "============================================================"
