#!/usr/bin/env bash
set -u

ROOT="/vaults/nvme0/qsb_tower_v1"
HUB="$ROOT/tools/qsb_boardroom_hub.py"
STAMP="$(date +%Y%m%d_%H%M%S)"
REPORT="/home/ross/Desktop/qsb_ipad_dash_map_$STAMP.txt"

exec > >(tee "$REPORT") 2>&1

echo "============================================================"
echo "QSB iPAD DASH / BOARDROOM MAP"
echo "Generated: $(date -Is)"
echo "Root: $ROOT"
echo "Hub: $HUB"
echo "Report: $REPORT"
echo "============================================================"
echo

if [ ! -f "$HUB" ]; then
  echo "[FAIL] Boardroom hub not found: $HUB"
  exit 1
fi

echo "===== 1. ACTIVE BOARDROOM HUB PROCESS ====="
ps aux | grep -E "qsb_boardroom_hub|8852" | grep -v grep || true
echo

echo "===== 2. ACTIVE PORTS ====="
ss -ltnp 2>/dev/null | grep -E ':(8765|8851|8852|8795|8796|9100|9110|9130|11434)\b' || true
echo

echo "===== 3. IMPORTANT ROUTES / STRINGS IN qsb_boardroom_hub.py ====="
grep -nE "def do_GET|def do_POST|/ipad|TEAM_LIVE_HTML|IPAD|team_live|town/post|ipad_button_diag|sec-dashes|all dashboards|TP dash|Brain Router|Ollama|9110|8765|8851|8852|11434|sendChat|forceRefreshAll|speechSynthesis|SpeechRecognition|ceo_mind|brain/route" "$HUB" | head -300
echo

echo "===== 4. HTML/JS FUNCTIONS AROUND CHAT SEND ====="
grep -nE "function sendChat|async function sendChat|fetch\\('/town/post|fetch\\(\"/town/post|from:'hq_claude'|from:\"hq_claude\"|from:'ross'|from:\"ross\"" "$HUB" | head -120
echo

echo "===== 5. DASHBOARD LINKS FOUND INSIDE HUB ====="
grep -oE "https?://[0-9A-Za-z._:/#?=&%-]+" "$HUB" | sort -u
echo

echo "===== 6. LOCAL ENDPOINT TESTS ====="
test_url(){
  name="$1"
  url="$2"
  code="$(curl -sS -o /tmp/qsb_ipad_body.txt -w '%{http_code}' --max-time 5 "$url" 2>/dev/null || echo 000)"
  if [ "$code" = "200" ]; then
    echo "[OK]   $name HTTP $code -> $url"
    head -c 220 /tmp/qsb_ipad_body.txt | tr '\n' ' '
    echo
  else
    echo "[WARN] $name HTTP $code -> $url"
  fi
}

test_url "Boardroom root" "http://127.0.0.1:8852/"
test_url "iPad cockpit" "http://127.0.0.1:8852/ipad"
test_url "iPad post anchor" "http://127.0.0.1:8852/ipad#sec-post"
test_url "Main dashboard 8765" "http://127.0.0.1:8765/"
test_url "Main dashboard unified API" "http://127.0.0.1:8765/api/unified"
test_url "Wren dash" "http://127.0.0.1:8851/"
test_url "Node listener" "http://127.0.0.1:9100/"
test_url "Ollama tags" "http://127.0.0.1:11434/api/tags"
test_url "TP-Pip LAN heartbeat" "http://192.168.1.91:9110/heartbeat.json"
test_url "TP-Pip LAN proof" "http://192.168.1.91:9110/proof.json"
echo

echo "===== 7. MOST LIKELY LIVE iPAD DASH CODE BLOCKS ====="
echo "--- around /ipad references ---"
grep -n "/ipad" "$HUB" | head -30
echo

echo "--- around TEAM_LIVE_HTML if present ---"
LINE="$(grep -n "TEAM_LIVE_HTML" "$HUB" | head -1 | cut -d: -f1 || true)"
if [ -n "$LINE" ]; then
  START=$((LINE-20))
  END=$((LINE+220))
  [ "$START" -lt 1 ] && START=1
  sed -n "${START},${END}p" "$HUB"
else
  echo "TEAM_LIVE_HTML not found by exact name"
fi
echo

echo "===== 8. SUMMARY ====="
echo "Main iPad/Boardroom file:"
echo "$HUB"
echo
echo "Full animated dashboard files:"
echo "$ROOT/src/dashboard/server.py"
echo "$ROOT/src/dashboard/static/index.html"
echo "$ROOT/src/dashboard/static/cockpit.js"
echo
echo "Report saved:"
echo "$REPORT"
echo "============================================================"
