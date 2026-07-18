#!/usr/bin/env bash
set -u

ROOT="/vaults/nvme0/qsb_tower_v1"
HUB="$ROOT/tools/qsb_boardroom_hub.py"
STAMP="$(date +%Y%m%d_%H%M%S)"
OUTDIR="/home/ross/Desktop/qsb_smoke_tests"
REPORT="$OUTDIR/qsb_ipad_smoke_$STAMP.txt"

mkdir -p "$OUTDIR"

PASS=0
WARN=0
FAIL=0

G="\033[1;32m"
Y="\033[1;33m"
R="\033[1;31m"
B="\033[1;36m"
P="\033[1;35m"
X="\033[0m"

exec > >(tee "$REPORT") 2>&1

ok(){ echo -e "${G}[PASS]${X} $*"; PASS=$((PASS+1)); }
warn(){ echo -e "${Y}[WARN]${X} $*"; WARN=$((WARN+1)); }
bad(){ echo -e "${R}[FAIL]${X} $*"; FAIL=$((FAIL+1)); }
info(){ echo -e "${B}[INFO]${X} $*"; }
sec(){ echo ""; echo -e "${P}========== $* ==========${X}"; }

http_get(){
  local name="$1"
  local url="$2"
  local required="${3:-warn}"
  local tmp="/tmp/qsb_ipad_get_$$.txt"
  local err="/tmp/qsb_ipad_get_err_$$.txt"
  local code
  code="$(curl -L -sS --max-time 7 -o "$tmp" -w "%{http_code}" "$url" 2>"$err")"
  local rc=$?

  if [ "$rc" -ne 0 ]; then
    code="000"
  fi

  local bytes
  bytes="$(wc -c < "$tmp" 2>/dev/null || echo 0)"

  if [ "$code" = "200" ] || [ "$code" = "204" ] || [ "$code" = "301" ] || [ "$code" = "302" ]; then
    ok "$name HTTP $code bytes=$bytes -> $url"
    echo "      preview:"
    head -c 220 "$tmp" 2>/dev/null | tr '\n' ' '
    echo ""
  else
    if [ "$required" = "fail" ]; then
      bad "$name HTTP $code bytes=$bytes -> $url"
      [ -s "$err" ] && sed 's/^/      curl: /' "$err" | head -5
    else
      warn "$name HTTP $code bytes=$bytes -> $url"
      [ -s "$err" ] && sed 's/^/      curl: /' "$err" | head -5
    fi
  fi

  rm -f "$tmp" "$err"
}

http_post_json(){
  local name="$1"
  local url="$2"
  local json="$3"
  local required="${4:-warn}"
  local tmp="/tmp/qsb_ipad_post_$$.txt"
  local err="/tmp/qsb_ipad_post_err_$$.txt"
  local code
  code="$(curl -sS --max-time 8 -o "$tmp" -w "%{http_code}" \
    -H "Content-Type: application/json" \
    -X POST \
    --data "$json" \
    "$url" 2>"$err")"
  local rc=$?

  if [ "$rc" -ne 0 ]; then
    code="000"
  fi

  local bytes
  bytes="$(wc -c < "$tmp" 2>/dev/null || echo 0)"

  if [ "$code" = "200" ] || [ "$code" = "204" ]; then
    ok "$name POST HTTP $code bytes=$bytes -> $url"
    head -c 260 "$tmp" 2>/dev/null | tr '\n' ' '
    echo ""
  else
    if [ "$required" = "fail" ]; then
      bad "$name POST HTTP $code bytes=$bytes -> $url"
      [ -s "$err" ] && sed 's/^/      curl: /' "$err" | head -5
    else
      warn "$name POST HTTP $code bytes=$bytes -> $url"
      [ -s "$err" ] && sed 's/^/      curl: /' "$err" | head -5
    fi
  fi

  rm -f "$tmp" "$err"
}

port_check(){
  local port="$1"
  local name="$2"
  local required="${3:-warn}"

  if ss -ltnp 2>/dev/null | grep -q ":$port\b"; then
    ok "$name listening on port $port"
    ss -ltnp 2>/dev/null | grep ":$port\b"
  else
    if [ "$required" = "fail" ]; then
      bad "$name NOT listening on port $port"
    else
      warn "$name NOT listening on port $port"
    fi
  fi
}

sec "QSB iPAD DASH SMOKE TEST"
echo "Generated: $(date -Is)"
echo "Host: $(hostname)"
echo "User: $(whoami)"
echo "Root: $ROOT"
echo "Hub: $HUB"
echo "Report: $REPORT"

sec "1. FILE AND PROCESS CHECK"
if [ -d "$ROOT" ]; then ok "QSB root exists"; else bad "QSB root missing"; exit 1; fi
if [ -f "$HUB" ]; then ok "Boardroom/iPad hub exists: $HUB"; else bad "Boardroom/iPad hub missing"; exit 1; fi

echo ""
echo "Active hub process:"
ps aux | grep -E "qsb_boardroom_hub|--port 8852" | grep -v grep || warn "No qsb_boardroom_hub process seen"

sec "2. PORT CHECK"
port_check 8852 "Boardroom hub / iPad dash" fail
port_check 8851 "Wren dash" warn
port_check 9100 "HQ node listener" warn
port_check 8795 "Voice server" warn
port_check 8796 "STT / voice helper" warn
port_check 11434 "Ollama" fail
port_check 8765 "Full Skyscraper dashboard" warn
port_check 9110 "TP-Pip from this box" warn

sec "3. iPAD CORE PAGE TESTS"
http_get "Boardroom root" "http://127.0.0.1:8852/" fail
http_get "iPad cockpit" "http://127.0.0.1:8852/ipad" fail
http_get "iPad post section anchor" "http://127.0.0.1:8852/ipad#sec-post" fail
http_get "Team Live" "http://127.0.0.1:8852/team_live" warn
http_get "Brain Router page" "http://127.0.0.1:8852/brain" warn
http_get "Task Council page" "http://127.0.0.1:8852/tasks" warn
http_get "Trading page" "http://127.0.0.1:8852/trading" warn
http_get "Annexes page" "http://127.0.0.1:8852/annexes" warn

sec "4. iPAD DATA ENDPOINT TESTS"
http_get "Team Live data" "http://127.0.0.1:8852/team_live/data" warn
http_get "Tasks data" "http://127.0.0.1:8852/tasks/data" warn
http_get "Brain usage" "http://127.0.0.1:8852/brain/usage" warn
http_get "HQ stats" "http://127.0.0.1:8852/hq/stats" warn
http_get "Town square feed" "http://127.0.0.1:8852/town_square_feed" warn
http_get "Diagnostics" "http://127.0.0.1:8852/diagnostics" warn
http_get "Link health" "http://127.0.0.1:8852/link_health" warn
http_get "Trader scoreboard" "http://127.0.0.1:8852/trader_scoreboard" warn
http_get "Talk data" "http://127.0.0.1:8852/talk/data" warn
http_get "iPad button diag tail" "http://127.0.0.1:8852/ipad_button_diag/tail" warn
http_get "Trading data" "http://127.0.0.1:8852/trading/data" warn

sec "5. DASHBOARD LINK TESTS FROM iPAD"
http_get "Wren dash direct" "http://127.0.0.1:8851/" warn
http_get "Wren dash proxy" "http://127.0.0.1:8852/proxy/wren" warn
http_get "TP-Pip direct LAN" "http://192.168.1.91:9110/" warn
http_get "TP-Pip proxy" "http://127.0.0.1:8852/proxy/tp" warn
http_get "TP-Pip heartbeat LAN" "http://192.168.1.91:9110/heartbeat.json" warn
http_get "TP-Pip proof LAN" "http://192.168.1.91:9110/proof.json" warn
http_get "Full Skyscraper dashboard 8765" "http://127.0.0.1:8765/" warn
http_get "Full Skyscraper unified API" "http://127.0.0.1:8765/api/unified" warn
http_get "Ollama tags" "http://127.0.0.1:11434/api/tags" fail
http_get "HQ node listener" "http://127.0.0.1:9100/" warn

sec "6. SAFE POST TESTS"
NOW="$(date -Is)"
http_post_json "iPad button diagnostic log" "http://127.0.0.1:8852/ipad_button_diag" "{\"ts\":\"$NOW\",\"button\":\"CLI_SMOKE_TEST\",\"url\":\"cli://smoke_ipad_dash_now\",\"ok\":true,\"note\":\"safe diagnostic smoke test from Ross CLI\"}" warn

http_post_json "Town Square / iPad sendChat path" "http://127.0.0.1:8852/town/post" "{\"from\":\"ross\",\"text\":\"🧪 iPad smoke test from Linux CLI at $NOW — harmless diagnostic post\",\"to\":\"council\",\"src\":\"ipad_cli_smoke\"}" warn

sec "7. JAVASCRIPT / ROUTE STATIC SCAN"
echo "Important iPad route/function lines:"
grep -nE "IPAD_HTML|TEAM_LIVE_HTML|def do_GET|def do_POST|/ipad|/team_live|/town/post|/ipad_button_diag|/proxy/wren|/proxy/tp|function sendChat|async function sendChat|forceRefreshAll|kickWren|dispatchTeam|pingTP|pingAcer|emergencyPause|massSignoff|cullDuds|runQualifier|speechSynthesis|SpeechRecognition" "$HUB" | head -260

echo ""
echo "Hardcoded remote links found:"
grep -oE "https?://[0-9A-Za-z._:/#?=&%-]+" "$HUB" | sort -u | sed 's/^/ - /' | head -160

sec "8. BROKEN-LINK SUMMARY"
echo "Expected healthy:"
echo " - 8852 /ipad"
echo " - 8852 /team_live"
echo " - 8852 /town/post"
echo " - 8852 /ipad_button_diag"
echo " - 8851 Wren dash"
echo " - 9100 HQ node listener"
echo " - 11434 Ollama"
echo ""
echo "Expected current warnings from previous proof:"
echo " - 8765 full dashboard may be down"
echo " - 192.168.1.91:9110 TP-Pip may be unreachable from HQ LAN"
echo " - proxy/tp will fail if TP-Pip LAN is unreachable"
echo ""
echo "Dangerous buttons NOT executed:"
echo " - emergencyPause"
echo " - cullDuds"
echo " - massSignoff"
echo " - runQualifier"
echo " - kill-switch"
echo " - direct ceo_mind dispatch"

sec "9. FINAL SUMMARY"
echo -e "${G}PASS:${X} $PASS"
echo -e "${Y}WARN:${X} $WARN"
echo -e "${R}FAIL:${X} $FAIL"
echo "Report saved:"
echo "$REPORT"

if [ "$FAIL" -eq 0 ]; then
  echo -e "${G}RESULT: iPAD CORE IS ALIVE; CHECK WARNINGS${X}"
else
  echo -e "${R}RESULT: iPAD CORE HAS REAL FAILURES${X}"
fi
