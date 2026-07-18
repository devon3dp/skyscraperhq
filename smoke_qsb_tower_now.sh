#!/usr/bin/env bash
set -u

ROOT="/vaults/nvme0/qsb_tower_v1"
STAMP="$(date +%Y%m%d_%H%M%S)"
OUTDIR="/home/ross/Desktop/qsb_smoke_tests"
REPORT="$OUTDIR/qsb_smoke_test_$STAMP.txt"

mkdir -p "$OUTDIR"

GREEN="\033[1;32m"
YELLOW="\033[1;33m"
RED="\033[1;31m"
BLUE="\033[1;36m"
PURPLE="\033[1;35m"
RESET="\033[0m"

PASS_COUNT=0
WARN_COUNT=0
FAIL_COUNT=0

exec > >(tee "$REPORT") 2>&1

pass(){ echo -e "${GREEN}[PASS]${RESET} $*"; PASS_COUNT=$((PASS_COUNT+1)); }
warn(){ echo -e "${YELLOW}[WARN]${RESET} $*"; WARN_COUNT=$((WARN_COUNT+1)); }
fail(){ echo -e "${RED}[FAIL]${RESET} $*"; FAIL_COUNT=$((FAIL_COUNT+1)); }
info(){ echo -e "${BLUE}[INFO]${RESET} $*"; }
headx(){ echo ""; echo -e "${PURPLE}========== $* ==========${RESET}"; }

check_path(){
  local p="$1"
  local name="$2"
  if [ -e "$p" ]; then
    pass "$name exists: $p"
  else
    fail "$name missing: $p"
  fi
}

check_optional_path(){
  local p="$1"
  local name="$2"
  if [ -e "$p" ]; then
    pass "$name exists: $p"
  else
    warn "$name not found: $p"
  fi
}

check_cmd(){
  local c="$1"
  if command -v "$c" >/dev/null 2>&1; then
    pass "Command available: $c -> $(command -v "$c")"
  else
    warn "Command missing: $c"
  fi
}

check_url(){
  local url="$1"
  local name="$2"
  if ! command -v curl >/dev/null 2>&1; then
    warn "curl missing, cannot test URL: $name $url"
    return
  fi

  local tmp="/tmp/qsb_smoke_url_$$.txt"
  local code
  code="$(curl -L -sS --max-time 5 -o "$tmp" -w "%{http_code}" "$url" 2>/dev/null || true)"

  if [ "$code" = "200" ] || [ "$code" = "204" ] || [ "$code" = "301" ] || [ "$code" = "302" ]; then
    pass "$name reachable: $url HTTP $code"
    echo "       Response preview:"
    head -c 300 "$tmp" 2>/dev/null | tr '\n' ' '
    echo ""
  else
    warn "$name not reachable or not HTTP OK: $url HTTP ${code:-NO_RESPONSE}"
  fi

  rm -f "$tmp"
}

headx "QSB TOWER SMOKE TEST"
echo "Generated: $(date -Is)"
echo "Host: $(hostname)"
echo "User: $(whoami)"
echo "Root: $ROOT"
echo "Report: $REPORT"

headx "ROOT CHECK"
if [ -d "$ROOT" ]; then
  pass "QSB root exists"
  cd "$ROOT" || exit 1
else
  fail "QSB root missing: $ROOT"
  exit 1
fi

pwd
echo ""
echo "Top-level items:"
find "$ROOT" -mindepth 1 -maxdepth 1 -printf '%f\n' 2>/dev/null | sort | sed 's/^/ - /'

headx "CORE FOLDERS"
check_path "$ROOT/config" "config"
check_path "$ROOT/data" "data"
check_path "$ROOT/floors" "floors"
check_path "$ROOT/ground" "ground"
check_path "$ROOT/basement" "basement"
check_path "$ROOT/roof" "roof"
check_path "$ROOT/penthouse" "penthouse"
check_path "$ROOT/scripts" "scripts"
check_path "$ROOT/tools" "tools"
check_path "$ROOT/docs" "docs"
check_path "$ROOT/protocols" "protocols"
check_path "$ROOT/logs" "logs"
check_optional_path "$ROOT/native_cockpit" "native_cockpit"
check_optional_path "$ROOT/proof_of_work" "proof_of_work"
check_optional_path "$ROOT/skills" "skills"
check_optional_path "$ROOT/state" "state"
check_optional_path "$ROOT/vaults" "vaults"

headx "CORE FILES"
check_optional_path "$ROOT/README.md" "README"
check_optional_path "$ROOT/CLAUDE.md" "CLAUDE instructions"
check_optional_path "$ROOT/MEMORY.md" "MEMORY"
check_optional_path "$ROOT/CHANGELOG.md" "CHANGELOG"
check_optional_path "$ROOT/run.sh" "run script"
check_optional_path "$ROOT/status.sh" "status script"
check_optional_path "$ROOT/stop.sh" "stop script"
check_optional_path "$ROOT/restart.sh" "restart script"
check_optional_path "$ROOT/setup.sh" "setup script"
check_optional_path "$ROOT/requirements.txt" "requirements.txt"
check_optional_path "$ROOT/requirements_qsb_runtime.txt" "requirements_qsb_runtime.txt"

headx "RULEBOOK / FLOOR 47 / COUNCIL / BOARDROOM / SQUARE SEARCH"
echo "Rulebook / rules:"
RULES="$(find "$ROOT" \( -iname "*rule*" -o -iname "*rulebook*" -o -iname "*constitution*" -o -iname "*protocol*" \) 2>/dev/null | sort)"
if [ -n "$RULES" ]; then
  echo "$RULES" | sed "s|$ROOT/| - |"
  pass "Rule/protocol files found"
else
  warn "No rulebook/rule/protocol files found by filename"
fi

echo ""
echo "Floor 47:"
F47="$(find "$ROOT" \( -ipath "*floor*47*" -o -ipath "*floor47*" -o -ipath "*47*" \) 2>/dev/null | sort | head -100)"
if [ -n "$F47" ]; then
  echo "$F47" | sed "s|$ROOT/| - |"
  pass "Floor 47 related paths found"
else
  warn "No Floor 47 path found by filename/path"
fi

echo ""
echo "Task council / boardroom / talent square / town square:"
SPECIAL="$(find "$ROOT" \( -iname "*task*" -o -iname "*council*" -o -iname "*boardroom*" -o -iname "*talent*square*" -o -iname "*town*square*" -o -iname "*square*" -o -iname "*team*live*" \) 2>/dev/null | sort)"
if [ -n "$SPECIAL" ]; then
  echo "$SPECIAL" | sed "s|$ROOT/| - |"
  pass "Council/boardroom/square related paths found"
else
  warn "No council/boardroom/square files found by filename"
fi

headx "TOOLS AND RUNTIME COMMANDS"
check_cmd bash
check_cmd python3
check_cmd pip3
check_cmd sqlite3
check_cmd curl
check_cmd jq
check_cmd git
check_cmd zip
check_cmd ollama
check_cmd node
check_cmd npm

headx "PYTHON VERSION"
if command -v python3 >/dev/null 2>&1; then
  python3 --version && pass "Python responds"
else
  fail "python3 not available"
fi

headx "DISK AND STORAGE"
df -h "$ROOT" || true
echo ""
du -sh "$ROOT" 2>/dev/null || warn "Could not calculate root size"
echo ""
echo "Largest top-level folders/files:"
du -sh "$ROOT"/* 2>/dev/null | sort -h | tail -30 || true

headx "FILE COUNTS"
TOTAL_DIRS="$(find "$ROOT" -type d 2>/dev/null | wc -l)"
TOTAL_FILES="$(find "$ROOT" -type f 2>/dev/null | wc -l)"
TOTAL_PY="$(find "$ROOT" -type f -name "*.py" 2>/dev/null | wc -l)"
TOTAL_SH="$(find "$ROOT" -type f -name "*.sh" 2>/dev/null | wc -l)"
TOTAL_HTML="$(find "$ROOT" -type f -name "*.html" 2>/dev/null | wc -l)"
TOTAL_JSON="$(find "$ROOT" -type f -name "*.json" 2>/dev/null | wc -l)"
TOTAL_DB="$(find "$ROOT" -type f \( -name "*.db" -o -name "*.sqlite" -o -name "*.sqlite3" \) 2>/dev/null | wc -l)"

echo "Directories: $TOTAL_DIRS"
echo "Files:       $TOTAL_FILES"
echo "Python:      $TOTAL_PY"
echo "Shell:       $TOTAL_SH"
echo "HTML:        $TOTAL_HTML"
echo "JSON:        $TOTAL_JSON"
echo "SQLite DB:   $TOTAL_DB"

[ "$TOTAL_FILES" -gt 0 ] && pass "Files are present" || fail "No files found"
[ "$TOTAL_PY" -gt 0 ] && pass "Python files are present" || warn "No Python files found"
[ "$TOTAL_HTML" -gt 0 ] && pass "HTML/dashboard files are present" || warn "No HTML files found"

headx "EXECUTABLE SCRIPT CHECK"
for s in run.sh status.sh stop.sh restart.sh setup.sh qsb_lockdown_record.sh; do
  if [ -f "$ROOT/$s" ]; then
    if [ -x "$ROOT/$s" ]; then
      pass "$s is executable"
    else
      warn "$s exists but is not executable"
    fi
  fi
done

headx "SHELL SCRIPT SYNTAX CHECK"
SH_FAILS=0
while IFS= read -r shfile; do
  if bash -n "$shfile" 2>/tmp/qsb_sh_err.txt; then
    pass "Shell syntax OK: ${shfile#$ROOT/}"
  else
    fail "Shell syntax FAIL: ${shfile#$ROOT/}"
    cat /tmp/qsb_sh_err.txt
    SH_FAILS=$((SH_FAILS+1))
  fi
done < <(find "$ROOT" -maxdepth 2 -type f -name "*.sh" 2>/dev/null | sort | head -80)
rm -f /tmp/qsb_sh_err.txt

if [ "$SH_FAILS" -eq 0 ]; then
  pass "No shell syntax failures in checked scripts"
else
  fail "$SH_FAILS shell syntax failures found"
fi

headx "PYTHON SYNTAX SMOKE TEST"
if command -v python3 >/dev/null 2>&1; then
  python3 - <<PY
import os, py_compile, sys
root = "$ROOT"
skip_parts = ["/archive/", "/_archive/", "/backups/", "/__pycache__/", "/.venv/", "/venv/", "/node_modules/"]
files = []
for base, dirs, names in os.walk(root):
    if any(part in base for part in skip_parts):
        continue
    for n in names:
        if n.endswith(".py"):
            files.append(os.path.join(base,n))
files = sorted(files)
limit = 300
print(f"Python files found: {len(files)}")
print(f"Python files checked limit: {min(len(files), limit)}")
bad = []
for f in files[:limit]:
    try:
        py_compile.compile(f, doraise=True)
    except Exception as e:
        bad.append((f, str(e)))
if bad:
    print("[PYTHON_FAILS]")
    for f,e in bad[:50]:
        print("FAIL:", os.path.relpath(f, root))
        print(e)
    sys.exit(1)
else:
    print("[PYTHON_OK] checked Python files compiled")
PY
  if [ "$?" -eq 0 ]; then
    pass "Python syntax smoke test passed"
  else
    fail "Python syntax smoke test found failures"
  fi
else
  warn "Skipped Python syntax test: python3 missing"
fi

headx "JSON VALIDATION"
JSON_BAD=0
if command -v python3 >/dev/null 2>&1; then
  while IFS= read -r jf; do
    python3 -m json.tool "$jf" >/dev/null 2>/tmp/qsb_json_err.txt
    if [ "$?" -eq 0 ]; then
      pass "JSON OK: ${jf#$ROOT/}"
    else
      fail "JSON FAIL: ${jf#$ROOT/}"
      cat /tmp/qsb_json_err.txt
      JSON_BAD=$((JSON_BAD+1))
    fi
  done < <(find "$ROOT" -maxdepth 4 -type f -name "*.json" 2>/dev/null | sort | head -120)
else
  warn "Skipped JSON validation: python3 missing"
fi
rm -f /tmp/qsb_json_err.txt

if [ "$JSON_BAD" -eq 0 ]; then
  pass "No JSON failures in checked files"
else
  fail "$JSON_BAD JSON failures found"
fi

headx "SQLITE DATABASE CHECK"
if command -v sqlite3 >/dev/null 2>&1; then
  DB_COUNT=0
  while IFS= read -r db; do
    DB_COUNT=$((DB_COUNT+1))
    echo "Checking DB: ${db#$ROOT/}"
    if sqlite3 "$db" "PRAGMA integrity_check;" 2>/tmp/qsb_db_err.txt | grep -qi "ok"; then
      pass "SQLite OK: ${db#$ROOT/}"
    else
      warn "SQLite issue or not a normal SQLite DB: ${db#$ROOT/}"
      cat /tmp/qsb_db_err.txt
    fi
  done < <(find "$ROOT" -type f \( -name "*.db" -o -name "*.sqlite" -o -name "*.sqlite3" \) 2>/dev/null | sort | head -50)
  [ "$DB_COUNT" -gt 0 ] || warn "No SQLite DB files found"
else
  warn "Skipped SQLite check: sqlite3 missing"
fi
rm -f /tmp/qsb_db_err.txt

headx "RUNNING PROCESSES"
echo "QSB/Python/Ollama related processes:"
ps aux | grep -Ei 'qsb|tower|dashboard|router|ollama|python|uvicorn|streamlit|gunicorn' | grep -v grep | head -80 || true

headx "LISTENING PORTS"
if command -v ss >/dev/null 2>&1; then
  ss -ltnp 2>/dev/null | grep -E '(:8765|:8852|:11434|:9110|:9130|:879|:877|python|ollama)' || warn "No expected listening ports seen in ss output"
else
  warn "ss command not available"
fi

headx "NETWORK / DASHBOARD / ROUTER SMOKE TESTS"
check_url "http://127.0.0.1:8765/" "Local Skyscraper dashboard 8765"
check_url "http://127.0.0.1:8852/" "Local Brain Router 8852"
check_url "http://127.0.0.1:11434/api/tags" "Local Ollama tags"
check_url "http://192.168.1.71:8852/" "HQ Brain Router LAN 8852"
check_url "http://192.168.1.71:11434/api/tags" "HQ Ollama LAN tags"
check_url "http://192.168.1.91:9110/heartbeat.json" "TP-Pip heartbeat LAN 9110"
check_url "http://192.168.1.91:9110/proof.json" "TP-Pip proof LAN 9110"
check_url "http://127.0.0.1:9110/heartbeat.json" "Local TP-Pip heartbeat 9110"
check_url "http://127.0.0.1:9130/" "Old TP dashboard 9130"

headx "OLLAMA MODEL CHECK"
if command -v ollama >/dev/null 2>&1; then
  if ollama list >/tmp/qsb_ollama_list.txt 2>/tmp/qsb_ollama_err.txt; then
    cat /tmp/qsb_ollama_list.txt
    pass "ollama list responded"
    for model in "qwen3.5:9b" "llama3.2:latest" "mistral:7b" "codellama:13b" "qwen2.5:7b-instruct" "nomic-embed-text:latest"; do
      if grep -q "$model" /tmp/qsb_ollama_list.txt; then
        pass "Model present: $model"
      else
        warn "Model missing from local ollama list: $model"
      fi
    done
  else
    warn "ollama command exists but did not respond"
    cat /tmp/qsb_ollama_err.txt
  fi
else
  warn "ollama not installed or not in PATH"
fi
rm -f /tmp/qsb_ollama_list.txt /tmp/qsb_ollama_err.txt

headx "RECENT LOG ERRORS"
if [ -d "$ROOT/logs" ]; then
  echo "Recent ERROR / Traceback / Exception lines from logs:"
  grep -RInE "Traceback|ERROR|Exception|Errno|CRITICAL|failed|FAILED" "$ROOT/logs" 2>/dev/null | tail -80 || warn "No recent obvious error lines found in logs"
else
  warn "logs folder missing"
fi

headx "LOCK / SAFETY SEARCH"
echo "Searching for live trading / execution lock references:"
grep -RInE "live_trading|live trading|paper_trading|execution lock|orders OFF|LIVE|OANDA|Binance|API_KEY|SECRET|TOKEN" \
  "$ROOT/config" "$ROOT/data" "$ROOT/floors" "$ROOT/scripts" "$ROOT/penthouse" 2>/dev/null | head -120 || warn "No safety/lock references found in checked folders"

headx "MISSING / IMPROVE NOTES"
echo "This smoke test checks structure, syntax, JSON, DBs, ports, Ollama, dashboards, and important QSB files."
echo ""
echo "Main things to improve if WARN/FAIL appears:"
echo " - Missing core folders/files: restore or rebuild that floor/module."
echo " - URL not reachable: start that service or fix the port/router."
echo " - Python syntax fail: inspect the named file and traceback."
echo " - JSON fail: repair malformed JSON."
echo " - DB warning: check whether that file is really SQLite."
echo " - Missing rulebook/council/boardroom/square paths: locate or rebuild those modules."
echo " - Safety lock references missing: verify live execution is still locked down."

headx "FINAL SUMMARY"
echo -e "${GREEN}PASS:${RESET} $PASS_COUNT"
echo -e "${YELLOW}WARN:${RESET} $WARN_COUNT"
echo -e "${RED}FAIL:${RESET} $FAIL_COUNT"
echo ""
echo "Report saved to:"
echo "$REPORT"

if [ "$FAIL_COUNT" -gt 0 ]; then
  echo ""
  echo -e "${RED}SMOKE TEST RESULT: FAILURES FOUND${RESET}"
  exit 1
elif [ "$WARN_COUNT" -gt 0 ]; then
  echo ""
  echo -e "${YELLOW}SMOKE TEST RESULT: WORKING WITH WARNINGS${RESET}"
  exit 0
else
  echo ""
  echo -e "${GREEN}SMOKE TEST RESULT: CLEAN PASS${RESET}"
  exit 0
fi
