#!/usr/bin/env bash
set -u

ROOT="/vaults/nvme0/qsb_tower_v1"
ORIG="$ROOT/tools/qsb_hq_claude_dash.py"
GEN="$ROOT/tools/qsb_hq_claude_dash_8850.py"
STAMP="$(date +%Y%m%d_%H%M%S)"
REPORT="/home/ross/Desktop/restore_original_hq_claude_dash_$STAMP.txt"
LOG="$ROOT/logs/hq_claude_original_8850.log"

exec > >(tee "$REPORT") 2>&1

echo "============================================================"
echo "RESTORE ORIGINAL HQ-CLAUDE DASHBOARD"
echo "Generated: $(date -Is)"
echo "Root: $ROOT"
echo "Original: $ORIG"
echo "Generated temp: $GEN"
echo "Report: $REPORT"
echo "============================================================"

cd "$ROOT" || exit 1
mkdir -p logs tools/quarantine_generated_dashboards

echo
echo "===== 1. VERIFY ORIGINAL DASHBOARD EXISTS ====="
if [ ! -f "$ORIG" ]; then
  echo "[FAIL] Original HQ-Claude dashboard not found: $ORIG"
  echo "Search:"
  find "$ROOT" -iname '*hq*claude*dash*.py' -o -iname '*claude*dash*.py' 2>/dev/null
  exit 1
fi

echo "[PASS] Original found: $ORIG"

echo
echo "===== 2. PROVE IT IS THE ORIGINAL BENCH DASH ====="
grep -nE "qsb_hq_claude_dash.py|HQ-Claude's own dashboard|HQ-Claude · Bench|Beacon Hall|CONVERSATION FEED|ask HQ-Claude|add_argument.*--port|default=8850|HQ-Claude bench dashboard" "$ORIG" | head -80

echo
echo "===== 3. COMPILE ORIGINAL ====="
python3 -m py_compile "$ORIG"
if [ "$?" -ne 0 ]; then
  echo "[FAIL] Original dashboard does not compile"
  exit 1
fi
echo "[PASS] Original dashboard compiles"

echo
echo "===== 4. QUARANTINE TEMP GENERATED DASHBOARD IF PRESENT ====="
if [ -f "$GEN" ]; then
  Q="$ROOT/tools/quarantine_generated_dashboards/qsb_hq_claude_dash_8850.generated_wrong_$STAMP.py"
  cp -a "$GEN" "$Q"
  mv "$GEN" "$GEN.generated_wrong_$STAMP"
  echo "[PASS] Moved generated temporary dashboard aside:"
  echo "       $GEN.generated_wrong_$STAMP"
  echo "[PASS] Safety copy:"
  echo "       $Q"
else
  echo "[OK] No generated temp dashboard file present"
fi

echo
echo "===== 5. STOP ANY DASH USING PORT 8850 ====="
tmux kill-session -t hqdash 2>/dev/null || true
tmux kill-session -t hq_claude_dash 2>/dev/null || true

PIDS="$(ss -ltnp 2>/dev/null | awk '/:8850/ {print}' | sed -n 's/.*pid=\([0-9]\+\).*/\1/p' | sort -u)"
if [ -n "$PIDS" ]; then
  echo "Killing old 8850 pids: $PIDS"
  for p in $PIDS; do kill "$p" 2>/dev/null || true; done
  sleep 2
fi

pkill -f "qsb_hq_claude_dash_8850.py" 2>/dev/null || true
pkill -f "tools/qsb_hq_claude_dash.py.*--port 8850" 2>/dev/null || true
sleep 1

echo
echo "===== 6. START ORIGINAL HQ-CLAUDE DASHBOARD ====="
if grep -q -- "--host" "$ORIG"; then
  CMD="cd '$ROOT' && python3 -u tools/qsb_hq_claude_dash.py --host 0.0.0.0 --port 8850 >> '$LOG' 2>&1"
else
  CMD="cd '$ROOT' && python3 -u tools/qsb_hq_claude_dash.py --port 8850 >> '$LOG' 2>&1"
fi

echo "Command:"
echo "$CMD"

tmux new-session -d -s hqdash "$CMD"
sleep 4

echo
echo "===== 7. PROCESS / PORT CHECK ====="
ps aux | grep -E "qsb_hq_claude_dash.py|hqdash" | grep -v grep || true
ss -ltnp | grep ':8850' || true

echo
echo "===== 8. PAGE TESTS ====="
curl -sS --max-time 8 -o /tmp/hq_original_8850.html \
  -w "HQ_ORIGINAL_PAGE http=%{http_code} total=%{time_total}s size=%{size_download}\n" \
  http://127.0.0.1:8850/ || true

echo
echo "Title/proof strings from served page:"
grep -oE "HQ-Claude · Bench|HQ-Claude|Beacon Hall|CONVERSATION FEED|ask HQ-Claude" /tmp/hq_original_8850.html | sort -u || true

echo
echo "Proxy through Boardroom:"
curl -sS --max-time 8 -o /tmp/hq_proxy.html \
  -w "HQ_PROXY http=%{http_code} total=%{time_total}s size=%{size_download}\n" \
  http://127.0.0.1:8852/proxy/hq || true

echo
echo "Link health check:"
curl -sS --max-time 10 http://127.0.0.1:8852/link_health | head -c 1200
echo

echo
echo "===== 9. LOG TAIL ====="
tail -80 "$LOG" 2>/dev/null || true

echo
echo "============================================================"
echo "DONE"
echo "Open on iPad/LAN:"
echo "http://192.168.1.71:8850/"
echo
echo "Report:"
echo "$REPORT"
echo "============================================================"
