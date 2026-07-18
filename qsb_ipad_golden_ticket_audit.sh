#!/usr/bin/env bash
set -u

ROOT="/vaults/nvme0/qsb_tower_v1"
HUB="$ROOT/tools/qsb_boardroom_hub.py"
STAMP="$(date +%Y%m%d_%H%M%S)"
OUT="/home/ross/Desktop/qsb_ipad_golden_ticket_audit_$STAMP.txt"

PASS=0
WARN=0
FAIL=0

G="\033[1;32m"; Y="\033[1;33m"; R="\033[1;31m"; B="\033[1;36m"; P="\033[1;35m"; X="\033[0m"

exec > >(tee "$OUT") 2>&1

ok(){ echo -e "${G}[PASS]${X} $*"; PASS=$((PASS+1)); }
warn(){ echo -e "${Y}[WARN]${X} $*"; WARN=$((WARN+1)); }
bad(){ echo -e "${R}[FAIL]${X} $*"; FAIL=$((FAIL+1)); }
info(){ echo -e "${B}[INFO]${X} $*"; }
sec(){ echo ""; echo -e "${P}========== $* ==========${X}"; }

get_url(){
  local name="$1"
  local url="$2"
  local required="${3:-warn}"
  local max="${4:-8}"
  local tmp
  tmp="$(mktemp /tmp/qsb_gt_XXXXXX)"

  local line
  line="$(curl -L -sS --max-time "$max" -o "$tmp" -w "http=%{http_code} total=%{time_total}s size=%{size_download}" "$url" 2>&1)"
  local code
  code="$(echo "$line" | sed -n 's/.*http=\([0-9][0-9][0-9]\).*/\1/p' | tail -1)"
  [ -z "$code" ] && code="000"

  if [ "$code" = "200" ] || [ "$code" = "204" ] || [ "$code" = "301" ] || [ "$code" = "302" ]; then
    ok "$name -> $line -> $url"
    head -c 180 "$tmp" 2>/dev/null | tr '\n' ' '
    echo
  else
    if [ "$required" = "fail" ]; then
      bad "$name -> $line -> $url"
    else
      warn "$name -> $line -> $url"
    fi
  fi

  rm -f "$tmp"
}

port_check(){
  local port="$1"
  local name="$2"
  local required="${3:-warn}"
  if ss -ltnp 2>/dev/null | grep -q ":$port\b"; then
    ok "$name listening on $port"
    ss -ltnp 2>/dev/null | grep ":$port\b" | head -2
  else
    if [ "$required" = "fail" ]; then bad "$name not listening on $port"; else warn "$name not listening on $port"; fi
  fi
}

sec "QSB iPAD GOLDEN TICKET AUDIT"
echo "Generated: $(date -Is)"
echo "Root: $ROOT"
echo "Hub: $HUB"
echo "Report: $OUT"

cd "$ROOT" || { bad "Cannot cd to $ROOT"; exit 1; }

sec "1. ROOT / HUB / PROCESS"
[ -d "$ROOT" ] && ok "QSB root exists" || bad "QSB root missing"
[ -f "$HUB" ] && ok "Boardroom hub file exists" || bad "Boardroom hub missing"

PY_PID="$(ps -eo pid=,ppid=,pcpu=,pmem=,rss=,vsz=,etime=,nlwp=,args= | awk '/python3/ && /tools\/qsb_boardroom_hub.py/ && /--port 8852/ && !/awk/ {print $1; exit}')"
if [ -n "$PY_PID" ]; then
  ok "Real Python Boardroom process found: $PY_PID"
  ps -p "$PY_PID" -o pid,ppid,pcpu,pmem,rss,vsz,etime,nlwp,cmd
  echo "open_fds=$(ls /proc/$PY_PID/fd 2>/dev/null | wc -l)"
else
  bad "Real Python Boardroom process not found"
fi

sec "2. REQUIRED PORTS"
port_check 8852 "Boardroom / iPad cockpit" fail
port_check 8851 "Wren dashboard" fail
port_check 9100 "HQ node listener" fail
port_check 11434 "Ollama" fail
port_check 8795 "Voice server" warn
port_check 8796 "STT / voice helper" warn
port_check 8765 "Full animated Skyscraper dashboard" warn
port_check 9110 "TP-Pip local/HQ-side check" warn
port_check 8850 "HQ-Claude old dash" warn
port_check 9000 "Acer-Cass LAN/local dash check" warn
port_check 9200 "Oracle annex" warn
port_check 9201 "Annex 9201" warn
port_check 9202 "Annex 9202" warn

sec "3. CORE iPAD PAGES"
get_url "Boardroom root" "http://127.0.0.1:8852/" fail 8
get_url "iPad cockpit" "http://127.0.0.1:8852/ipad" fail 8
get_url "Team Live page" "http://127.0.0.1:8852/team_live" fail 8
get_url "Task Council page" "http://127.0.0.1:8852/tasks" fail 8
get_url "Trading page" "http://127.0.0.1:8852/trading" fail 8
get_url "Town Square page" "http://127.0.0.1:8852/town_square" warn 8
get_url "Council page" "http://127.0.0.1:8852/council" warn 8
get_url "Rules page" "http://127.0.0.1:8852/rules" warn 8
get_url "Timeline page" "http://127.0.0.1:8852/timeline" warn 8
get_url "Annexes page" "http://127.0.0.1:8852/annexes" warn 8
get_url "Teamwork page" "http://127.0.0.1:8852/teamwork" warn 8
get_url "Brain page" "http://127.0.0.1:8852/brain" warn 8

sec "4. CORE DATA / COUNTERS / TASKS"
get_url "Tasks data" "http://127.0.0.1:8852/tasks/data" fail 8
get_url "Team Live data" "http://127.0.0.1:8852/team_live/data" warn 12
get_url "Trading data" "http://127.0.0.1:8852/trading/data" warn 8
get_url "Town Square feed" "http://127.0.0.1:8852/town_square_feed" warn 8
get_url "Talk data" "http://127.0.0.1:8852/talk/data" warn 8
get_url "Brain usage" "http://127.0.0.1:8852/brain/usage" warn 8
get_url "HQ stats" "http://127.0.0.1:8852/hq/stats" warn 8
get_url "Link health" "http://127.0.0.1:8852/link_health" warn 10
get_url "Diagnostics" "http://127.0.0.1:8852/diagnostics" warn 12
get_url "Trader scoreboard / rev counter" "http://127.0.0.1:8852/trader_scoreboard" warn 8
get_url "iPad button diag tail" "http://127.0.0.1:8852/ipad_button_diag/tail" warn 8

sec "5. DASHBOARD EMBEDS / PROXIES"
get_url "Wren direct" "http://127.0.0.1:8851/" fail 8
get_url "Wren proxy from iPad" "http://127.0.0.1:8852/proxy/wren" fail 8
get_url "TP-Pip direct LAN" "http://192.168.1.91:9110/" warn 6
get_url "TP-Pip proxy from iPad" "http://127.0.0.1:8852/proxy/tp" warn 8
get_url "Full dashboard 8765" "http://127.0.0.1:8765/" warn 6
get_url "Full dashboard API 8765" "http://127.0.0.1:8765/api/unified" warn 6
get_url "HQ node listener" "http://127.0.0.1:9100/" fail 6
get_url "Ollama tags" "http://127.0.0.1:11434/api/tags" fail 8

sec "6. iPAD HTML LINK EXTRACTION"
HTML="/tmp/qsb_ipad_html_$STAMP.html"
curl -sS --max-time 8 "http://127.0.0.1:8852/ipad" -o "$HTML" || true

python3 - "$HTML" <<'PY'
import re, sys
from urllib.parse import urlparse
html_path = sys.argv[1]
try:
    html = open(html_path, encoding="utf-8", errors="ignore").read()
except Exception as e:
    print("[FAIL] cannot read iPad HTML:", e)
    raise SystemExit(0)

patterns = [
    r"""href=['"]([^'"]+)['"]""",
    r"""src=['"]([^'"]+)['"]""",
    r"""fetch\(['"]([^'"]+)['"]""",
    r"""window\.open\(['"]([^'"]+)['"]""",
]
links = []
for pat in patterns:
    links += re.findall(pat, html)

clean = []
for x in links:
    if not x or x.startswith("#") or x.startswith("javascript:"):
        continue
    if x not in clean:
        clean.append(x)

print("Found links/actions:", len(clean))
for x in clean[:220]:
    print(" -", x)

print()
print("Static feature checks:")
checks = {
    "setInterval live polling": "setInterval" in html,
    "speech synthesis": "speechSynthesis" in html,
    "speech recognition": ("SpeechRecognition" in html or "webkitSpeechRecognition" in html),
    "button diagnostics": "ipad_button_diag" in html,
    "task council": "/tasks" in html,
    "town square": "town_square" in html,
    "trading/rev counters": ("trader_scoreboard" in html or "trading/data" in html or "trading" in html),
    "Wren proxy": "/proxy/wren" in html,
    "TP proxy": "/proxy/tp" in html,
    "emergency controls present": ("emergencyPause" in html and "kill-switch" in html),
}
for k,v in checks.items():
    print(("PASS" if v else "WARN"), "-", k)
PY

sec "7. STATIC CODE BONES"
echo "Important iPad bones in hub:"
grep -nE "IPAD_HTML|TEAM_LIVE_HTML|TRADING_HTML|TASKS_HTML|def do_GET|def do_POST|/ipad|/tasks/data|/team_live/data|/town/post|/ipad_button_diag|/proxy/wren|/proxy/tp|/brain/usage|/diagnostics|/link_health|trader_scoreboard|speechSynthesis|SpeechRecognition|setInterval|requestAnimationFrame|rev|counter" "$HUB" | head -260

sec "8. TASK COUNCIL SNAPSHOT"
TASK_TMP="/tmp/qsb_tasks_$STAMP.json"
curl -sS --max-time 8 "http://127.0.0.1:8852/tasks/data" -o "$TASK_TMP" || true
python3 - "$TASK_TMP" <<'PY'
import json, sys
p=sys.argv[1]
try:
    d=json.load(open(p))
    print("task_total:", d.get("total"))
    print("open:", d.get("open"))
    print("in_progress:", d.get("in_progress"))
    print("blocked:", d.get("blocked"))
    print("done:", d.get("done"))
    tasks=d.get("tasks", [])[:8]
    print("sample_tasks:")
    for t in tasks:
        print(" -", t.get("id"), "|", t.get("state"), "|", t.get("owner"), "|", (t.get("title") or t.get("description") or "")[:80])
except Exception as e:
    print("task_parse_error:", e)
PY

sec "9. TEAM LIVE SNAPSHOT"
TL_TMP="/tmp/qsb_teamlive_$STAMP.json"
curl -sS --max-time 12 "http://127.0.0.1:8852/team_live/data" -o "$TL_TMP" || true
python3 - "$TL_TMP" <<'PY'
import json, sys
p=sys.argv[1]
try:
    d=json.load(open(p))
    q=d.get("quorum") or {}
    print("quorum_online:", q.get("online_count"))
    print("quorum_met:", q.get("quorum_met"))
    for c in q.get("ceos", []):
        print(" -", c.get("ceo"), "online=", c.get("online"), "err=", (c.get("error") or "")[:90])
    print("town_square_messages:", len(d.get("town_square", [])))
    print("cards:", list((d.get("cards") or {}).keys()))
except Exception as e:
    print("team_live_parse_error:", e)
PY

sec "10. GOLDEN TICKET VERDICT"
echo "PASS=$PASS"
echo "WARN=$WARN"
echo "FAIL=$FAIL"
echo
echo "Golden-ticket meaning:"
echo " - FAIL 0 means the iPad core did not hard-fail."
echo " - WARN 0 means 100% connected."
echo " - Any WARN means not golden-ticket yet."
echo
echo "Known expected warnings until fixed:"
echo " - TP-Pip 192.168.1.91:9110 unreachable"
echo " - Full dashboard 8765 down"
echo " - /brain route may be wrong while /brain/usage works"
echo " - /team_live/data can drag if it waits for dead peers"
echo
echo "Dangerous controls NOT executed:"
echo " - emergencyPause"
echo " - cullDuds"
echo " - massSignoff"
echo " - runQualifier"
echo " - kill-switch"
echo " - trading execution"
echo
echo "Report saved:"
echo "$OUT"

if [ "$FAIL" -eq 0 ] && [ "$WARN" -eq 0 ]; then
  echo -e "${G}GOLDEN TICKET: YES — iPAD 100% CONNECTED${X}"
elif [ "$FAIL" -eq 0 ]; then
  echo -e "${Y}GOLDEN TICKET: NOT YET — CORE ALIVE, WARNINGS REMAIN${X}"
else
  echo -e "${R}GOLDEN TICKET: NO — HARD FAILURES REMAIN${X}"
fi
