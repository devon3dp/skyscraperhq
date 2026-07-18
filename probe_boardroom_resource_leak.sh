#!/usr/bin/env bash
set -u

ROOT="/vaults/nvme0/qsb_tower_v1"
HUB="$ROOT/tools/qsb_boardroom_hub.py"
STAMP="$(date +%Y%m%d_%H%M%S)"
REPORT="/home/ross/Desktop/qsb_boardroom_resource_probe_$STAMP.txt"

exec > >(tee "$REPORT") 2>&1

echo "============================================================"
echo "QSB BOARDROOM / iPAD RESOURCE PROBE"
echo "Generated: $(date -Is)"
echo "Root: $ROOT"
echo "Hub: $HUB"
echo "Report: $REPORT"
echo "============================================================"
echo

PID="$(pgrep -f "python3 tools/qsb_boardroom_hub.py --port 8852" | head -1 || true)"

if [ -z "$PID" ]; then
  echo "[FAIL] Boardroom process not found"
  echo "Trying wider search:"
  ps aux | grep -E "qsb_boardroom_hub|8852" | grep -v grep || true
  exit 1
fi

echo "[OK] Boardroom PID: $PID"
echo

echo "===== 1. PROCESS STATUS ====="
ps -p "$PID" -o pid,ppid,pcpu,pmem,rss,vsz,etime,nlwp,cmd
echo

echo "===== 2. TOP THREADS ====="
ps -L -p "$PID" -o pid,tid,pcpu,pmem,etime,comm | sort -k3 -nr | head -30
echo

echo "===== 3. OPEN FILE LIMIT ====="
cat "/proc/$PID/limits" | grep -Ei "open files|max processes|stack|cpu|address" || true
echo

echo "===== 4. OPEN FILE COUNT ====="
FD_COUNT="$(ls "/proc/$PID/fd" 2>/dev/null | wc -l)"
echo "Open FD count: $FD_COUNT"
echo

echo "===== 5. FD TYPE BREAKDOWN ====="
for fd in /proc/$PID/fd/*; do
  [ -e "$fd" ] || continue
  readlink "$fd" 2>/dev/null || true
done | awk '
  /socket:/ {socket++ ; next}
  /pipe:/ {pipe++ ; next}
  /anon_inode/ {anon++ ; next}
  /deleted/ {deleted++ ; next}
  /^\/.*\.jsonl/ {jsonl++ ; next}
  /^\/.*\.json/ {json++ ; next}
  /^\/.*\.log/ {log++ ; next}
  /^\/.*$/ {file++ ; next}
  {other++}
  END {
    print "socket:", socket+0
    print "pipe:", pipe+0
    print "anon_inode:", anon+0
    print "deleted:", deleted+0
    print "jsonl:", jsonl+0
    print "json:", json+0
    print "log:", log+0
    print "other files:", file+0
    print "other:", other+0
  }'
echo

echo "===== 6. FIRST 120 OPEN FDS ====="
ls -l "/proc/$PID/fd" 2>/dev/null | head -120
echo

echo "===== 7. REPEATED OPEN TARGETS ====="
for fd in /proc/$PID/fd/*; do
  [ -e "$fd" ] || continue
  readlink "$fd" 2>/dev/null || true
done | sort | uniq -c | sort -nr | head -60
echo

echo "===== 8. SOCKET STATES FOR PID ====="
if command -v ss >/dev/null 2>&1; then
  ss -tanp 2>/dev/null | grep "pid=$PID" | head -120 || true
else
  echo "ss missing"
fi
echo

echo "===== 9. LSOF SNAPSHOT IF AVAILABLE ====="
if command -v lsof >/dev/null 2>&1; then
  lsof -p "$PID" | head -160
else
  echo "lsof not installed"
fi
echo

echo "===== 10. SLOW ENDPOINT TIMINGS ====="
for url in \
  "http://127.0.0.1:8852/" \
  "http://127.0.0.1:8852/ipad" \
  "http://127.0.0.1:8852/annexes" \
  "http://127.0.0.1:8852/diagnostics" \
  "http://127.0.0.1:8852/link_health" \
  "http://127.0.0.1:8852/team_live/data" \
  "http://127.0.0.1:8852/tasks/data" \
  "http://127.0.0.1:8852/town_square_feed"
do
  echo "--- $url"
  curl -sS --max-time 10 -o /tmp/qsb_probe_body.txt \
    -w "http=%{http_code} total=%{time_total}s connect=%{time_connect}s starttransfer=%{time_starttransfer}s size=%{size_download}\n" \
    "$url" 2>&1 | head -5
  head -c 240 /tmp/qsb_probe_body.txt 2>/dev/null | tr '\n' ' '
  echo
done
echo

echo "===== 11. CODE LOCATIONS FOR SLOW ROUTES ====="
grep -nE 'if self.path == "/diagnostics"|if self.path == "/annexes"|if self.path == "/link_health"|if self.path == "/team_live/data"|if self.path == "/tasks/data"|if self.path == "/town_square_feed"|urlopen|requests|get_json|open\(' "$HUB" | head -260
echo

echo "===== 12. RECENT ERRORS ====="
grep -RInE "Too many open files|Errno 24|Traceback|Exception|timeout|timed out|Connection refused|BrokenPipe|ResourceWarning" \
  "$ROOT/logs" "$ROOT/data/registries" "$ROOT/tools" 2>/dev/null | tail -160
echo

echo "===== 13. QUICK VERDICT ====="
if [ "$FD_COUNT" -gt 900 ]; then
  echo "[BAD] FD count is very high: $FD_COUNT"
elif [ "$FD_COUNT" -gt 300 ]; then
  echo "[WARN] FD count is elevated: $FD_COUNT"
else
  echo "[OK] FD count is not huge: $FD_COUNT"
fi

CPU="$(ps -p "$PID" -o pcpu= | awk '{print int($1)}')"
if [ "$CPU" -gt 100 ]; then
  echo "[BAD] CPU is too high: ${CPU}%"
elif [ "$CPU" -gt 50 ]; then
  echo "[WARN] CPU elevated: ${CPU}%"
else
  echo "[OK] CPU acceptable: ${CPU}%"
fi

echo
echo "Report saved:"
echo "$REPORT"
echo "============================================================"
