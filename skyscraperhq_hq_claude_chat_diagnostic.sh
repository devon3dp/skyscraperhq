#!/usr/bin/env bash
set -u

PROJECT="/vaults/nvme0/qsb_tower_v1"
RUN_ROOT="/home/ross/Desktop/SKYSCRAPERHQ_RUNS"
SEND="$RUN_ROOT/00_SEND_THIS_TO_CHATGPT"
STAMP="$(date +%Y%m%d_%H%M%S)"
RUN_DIR="$RUN_ROOT/${STAMP}_hq_claude_chat_diagnostic"
REPORT="$RUN_DIR/reports/hq_claude_chat_diagnostic_report.txt"

mkdir -p "$RUN_DIR/reports" "$RUN_DIR/scripts" "$RUN_DIR/logs" "$SEND"
rm -f "$RUN_ROOT/LATEST"
ln -s "$RUN_DIR" "$RUN_ROOT/LATEST"

exec > >(tee "$REPORT") 2>&1

echo "============================================================"
echo "SKYSCRAPERHQ HQ-CLAUDE CHAT DIAGNOSTIC — NO PATCH"
echo "Generated: $(date -Is)"
echo "Project: $PROJECT"
echo "Run folder: $RUN_DIR"
echo "============================================================"
echo

cd "$PROJECT" || exit 1

echo "===== 1. LIVE SERVICES ====="
ss -ltnp | grep -E ':(8850|8852)\b' || true

echo
echo "===== 2. HQ DASHBOARD FETCH / ROUTE LINES ====="
grep -RIn --exclude-dir=.git --exclude-dir=.venv --exclude-dir=venv \
  -E "fetch\\(|brain/route|/talk|/chat|NetworkError|caller|hq_claude" \
  tools/qsb_hq_claude_dash.py tools/qsb_boardroom_hub.py 2>/dev/null | head -220 || true

echo
echo "===== 3. BASIC PAGE CHECKS ====="
for url in \
  "http://127.0.0.1:8850/" \
  "http://127.0.0.1:8852/ipad" \
  "http://127.0.0.1:8852/proxy/hq" \
  "http://127.0.0.1:8852/hq/stats" \
  "http://127.0.0.1:8852/brain/usage"
do
  echo "--- $url"
  tmp="$(mktemp /tmp/skyscraperhq_hq_diag_XXXXXX)"
  curl -sS --max-time 10 -o "$tmp" -w "http=%{http_code} total=%{time_total}s size=%{size_download}\n" "$url" || true
  head -c 300 "$tmp" | tr '\n' ' '
  echo
  rm -f "$tmp"
done

echo
echo "===== 4. BRAIN ROUTE OPTIONS / CORS CHECK ====="
echo "--- OPTIONS /brain/route"
curl -i -sS --max-time 10 \
  -X OPTIONS \
  -H "Origin: http://192.168.1.71:8850" \
  -H "Access-Control-Request-Method: POST" \
  -H "Access-Control-Request-Headers: content-type" \
  "http://127.0.0.1:8852/brain/route" | head -80 || true

echo
echo "===== 5. BRAIN ROUTE POST TESTS ====="

echo
echo "--- POST style A: caller/message"
curl -i -sS --max-time 45 \
  -H "Content-Type: application/json" \
  -H "Origin: http://192.168.1.71:8850" \
  -d '{"caller":"hq_claude","message":"diagnostic ping from Ross via CLI","prompt":"diagnostic ping from Ross via CLI"}' \
  "http://127.0.0.1:8852/brain/route" | head -120 || true

echo
echo "--- POST style B: who/text"
curl -i -sS --max-time 45 \
  -H "Content-Type: application/json" \
  -H "Origin: http://192.168.1.71:8850" \
  -d '{"who":"hq_claude","text":"diagnostic ping from Ross via CLI"}' \
  "http://127.0.0.1:8852/brain/route" | head -120 || true

echo
echo "===== 6. LAN URL CHECKS FROM THIS MACHINE ====="
for url in \
  "http://192.168.1.71:8850/" \
  "http://192.168.1.71:8852/brain/usage" \
  "http://192.168.1.71:8852/brain/route"
do
  echo "--- $url"
  curl -sS --max-time 10 -o /tmp/skyscraperhq_lan_check.out \
    -w "http=%{http_code} total=%{time_total}s size=%{size_download}\n" "$url" || true
  head -c 260 /tmp/skyscraperhq_lan_check.out 2>/dev/null | tr '\n' ' '
  echo
done

echo
echo "===== 7. RECENT HQ / BOARDROOM LOG ERRORS ====="
echo "--- HQ log"
tail -120 logs/hq_claude_original_8850.log 2>/dev/null | grep -iE "error|traceback|exception|brain|route|anthropic|claude|cors|network" || true
echo
echo "--- Boardroom log"
tail -180 logs/boardroom_hub_8852.log 2>/dev/null | grep -iE "error|traceback|exception|brain|route|anthropic|claude|cors|network|401|403|429" || true

echo
echo "============================================================"
echo "DONE — NO PATCHES APPLIED"
echo "Report:"
echo "$REPORT"
echo "============================================================"

cp -a "$REPORT" "$SEND/LATEST_REPORT.txt"
cp -a "$REPORT" "$RUN_ROOT/00_LATEST_REPORT.txt"
