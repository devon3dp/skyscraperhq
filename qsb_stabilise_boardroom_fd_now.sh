#!/usr/bin/env bash
set -u

ROOT="/vaults/nvme0/qsb_tower_v1"
STAMP="$(date +%Y%m%d_%H%M%S)"
REPORT="/home/ross/Desktop/qsb_stabilise_boardroom_fd_$STAMP.txt"
LOG="$ROOT/logs/boardroom_hub_8852.log"

exec > >(tee "$REPORT") 2>&1

echo "============================================================"
echo "QSB BOARDROOM FD STABILISE — NO CODE PATCH"
echo "Generated: $(date -Is)"
echo "Root: $ROOT"
echo "Report: $REPORT"
echo "============================================================"
echo
echo "Purpose:"
echo " - recover Boardroom/iPad 8852 from Errno 24 too many open files"
echo " - keep original HQ-Claude dash 8850"
echo " - keep Wren dash 8851"
echo " - keep 8765 dashboard"
echo " - no live trading"
echo " - no emergency buttons"
echo " - no code replacement"
echo

cd "$ROOT" || exit 1
mkdir -p logs

echo "===== 1. BEFORE STATE ====="
ps aux | grep -E "qsb_boardroom_hub.py --port 8852|tmux new-session -d -s br" | grep -v grep || true
echo
ss -ltnp | grep -E ':(8852|8851|8850|8765|9100|11434|9000|9110|9201|9202|19200)\b' || true

PY_PID="$(ps -eo pid=,args= | awk '/python3/ && /tools\/qsb_boardroom_hub.py/ && /--port 8852/ && !/awk/ {print $1; exit}')"
if [ -n "$PY_PID" ]; then
  echo
  echo "Boardroom PID before: $PY_PID"
  ps -p "$PY_PID" -o pid,ppid,pcpu,pmem,rss,vsz,etime,nlwp,cmd
  echo "open_fds_before=$(ls /proc/$PY_PID/fd 2>/dev/null | wc -l)"
fi

echo
echo "===== 2. STOP ONLY BOARDROOM 8852 ====="
tmux kill-session -t br 2>/dev/null || true
sleep 1

PIDS="$(ps -eo pid=,args= | awk '/python3/ && /tools\/qsb_boardroom_hub.py/ && /--port 8852/ && !/awk/ {print $1}')"
if [ -n "$PIDS" ]; then
  echo "Stopping old Boardroom pids: $PIDS"
  for p in $PIDS; do kill "$p" 2>/dev/null || true; done
  sleep 2
fi

PIDS2="$(ps -eo pid=,args= | awk '/python3/ && /tools\/qsb_boardroom_hub.py/ && /--port 8852/ && !/awk/ {print $1}')"
if [ -n "$PIDS2" ]; then
  echo "Force stopping stubborn Boardroom pids: $PIDS2"
  for p in $PIDS2; do kill -9 "$p" 2>/dev/null || true; done
  sleep 1
fi

echo
echo "===== 3. START BOARDROOM WITH HIGH FD LIMIT ====="
tmux new-session -d -s br "cd '$ROOT' && ulimit -n 65535 && export MALLOC_ARENA_MAX=2 && exec python3 -u tools/qsb_boardroom_hub.py --port 8852 >> '$LOG' 2>&1"

sleep 5

echo
echo "===== 4. AFTER PROCESS / FD STATE ====="
PY_PID="$(ps -eo pid=,args= | awk '/python3/ && /tools\/qsb_boardroom_hub.py/ && /--port 8852/ && !/awk/ {print $1; exit}')"
echo "Boardroom PID after: $PY_PID"

if [ -n "$PY_PID" ]; then
  ps -p "$PY_PID" -o pid,ppid,pcpu,pmem,rss,vsz,etime,nlwp,cmd
  echo "open_fds_after=$(ls /proc/$PY_PID/fd 2>/dev/null | wc -l)"
  echo "nofile_limit:"
  grep -i "open files" "/proc/$PY_PID/limits" 2>/dev/null || true
fi

echo
echo "===== 5. CORE ROUTE TESTS ====="
for url in \
  "http://127.0.0.1:8852/ipad" \
  "http://127.0.0.1:8852/" \
  "http://127.0.0.1:8852/link_health" \
  "http://127.0.0.1:8852/diagnostics" \
  "http://127.0.0.1:8852/team_live/data" \
  "http://127.0.0.1:8852/tasks/data" \
  "http://127.0.0.1:8852/proxy/hq" \
  "http://127.0.0.1:8852/proxy/wren" \
  "http://127.0.0.1:8852/proxy/acer" \
  "http://127.0.0.1:8850/" \
  "http://127.0.0.1:8851/" \
  "http://127.0.0.1:8765/" \
  "http://127.0.0.1:8765/api/unified"
do
  echo "--- $url"
  curl -sS --max-time 12 -o /tmp/qsb_fd_body \
    -w "http=%{http_code} total=%{time_total}s size=%{size_download}\n" \
    "$url" 2>&1 || true
  head -c 220 /tmp/qsb_fd_body 2>/dev/null | tr '\n' ' '
  echo
done

echo
echo "===== 6. FD WATCH 60 SECONDS ====="
if [ -n "$PY_PID" ]; then
  for i in 1 2 3 4 5 6; do
    echo "--- tick $i $(date -Is)"
    ps -p "$PY_PID" -o pid,pcpu,pmem,rss,vsz,etime,nlwp,cmd
    echo "open_fds=$(ls /proc/$PY_PID/fd 2>/dev/null | wc -l)"
    sleep 10
  done
fi

echo
echo "===== 7. RECENT ERRORS AFTER RESTART ====="
grep -iE "too many open files|traceback|exception|error|broken pipe|empty reply" "$LOG" 2>/dev/null | tail -80 || true

echo
echo "============================================================"
echo "DONE"
echo "Report:"
echo "$REPORT"
echo "============================================================"
