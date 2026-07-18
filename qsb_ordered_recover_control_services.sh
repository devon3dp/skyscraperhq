#!/usr/bin/env bash
set -u

DESK="/home/ross/Desktop"
RUN_ROOT="$DESK/QSB_CONTROL_RUNS"
STAMP="$(date +%Y%m%d_%H%M%S)"
RUN_DIR="$RUN_ROOT/${STAMP}_recover_control_services"
REPORT="$RUN_DIR/reports/recover_control_services_report.txt"

mkdir -p "$RUN_DIR/scripts" "$RUN_DIR/reports" "$RUN_DIR/logs" "$RUN_DIR/json" "$RUN_ROOT/imported_old_desktop_outputs"

rm -f "$RUN_ROOT/LATEST"
ln -s "$RUN_DIR" "$RUN_ROOT/LATEST"

exec > >(tee "$REPORT") 2>&1

echo "============================================================"
echo "QSB ORDERED RECOVER CONTROL SERVICES"
echo "Generated: $(date -Is)"
echo "Run folder: $RUN_DIR"
echo "Report: $REPORT"
echo "============================================================"

cd /vaults/nvme0/qsb_tower_v1 || exit 1

echo
echo "===== 1. IMPORT OLD LOOSE DESKTOP REPORTS ====="
find "$DESK" -maxdepth 1 -type f \( \
  -name 'qsb_*.txt' -o \
  -name 'restore_original_hq_claude_dash_*.txt' -o \
  -name 'find_original_claude_hq_dash_*.txt' -o \
  -name 'claude_api_token_audit_*.txt' -o \
  -name 'claude_api_token_audit_*.json' -o \
  -name 'wren_nightly_build_reply_*.json' \
\) -print0 2>/dev/null | while IFS= read -r -d '' f; do
  base="$(basename "$f")"
  echo "[MOVE] $base -> $RUN_ROOT/imported_old_desktop_outputs/"
  mv -n "$f" "$RUN_ROOT/imported_old_desktop_outputs/"
done

cat > "$RUN_ROOT/README.txt" <<README
QSB_CONTROL_RUNS

All QSB scripts, reports, logs, and JSON outputs should go here.

LATEST
  Symlink to newest run folder.

00_LATEST_REPORT.txt
  Copy of newest report.

imported_old_desktop_outputs
  Old loose Desktop reports moved here.

Do not scatter qsb_*.txt files loose on the Desktop.
README

echo
echo "===== 2. CURRENT PORTS BEFORE RECOVERY ====="
ss -ltnp | grep -E ':(8850|8851|8852|8765|9100|11434|9000|9110|9201|9202|19200)\b' || true

echo
echo "===== 3. STOP ONLY CONTROL DASH SESSIONS ====="
tmux kill-session -t br 2>/dev/null || true
tmux kill-session -t hqdash 2>/dev/null || true
tmux kill-session -t wren 2>/dev/null || true
tmux kill-session -t wrendash 2>/dev/null || true
tmux kill-session -t dash8765 2>/dev/null || true
sleep 2

echo
echo "===== 4. START ORIGINAL HQ-CLAUDE DASHBOARD 8850 ====="
if [ -f tools/qsb_hq_claude_dash.py ]; then
  python3 -m py_compile tools/qsb_hq_claude_dash.py && echo "[OK] HQ original compiles"
  tmux new-session -d -s hqdash "cd /vaults/nvme0/qsb_tower_v1 && exec python3 -u tools/qsb_hq_claude_dash.py --host 0.0.0.0 --port 8850 >> logs/hq_claude_original_8850.log 2>&1"
else
  echo "[FAIL] tools/qsb_hq_claude_dash.py missing"
fi

sleep 3

echo
echo "===== 5. START WREN ORIGINAL DASHBOARD 8851 ====="
if [ -f tools/qsb_wren_local_agent.py ]; then
  python3 -m py_compile tools/qsb_wren_local_agent.py && echo "[OK] Wren agent compiles"

  HELP="$(python3 tools/qsb_wren_local_agent.py --help 2>&1 | head -80 || true)"
  echo "$HELP" > "$RUN_DIR/logs/wren_help.txt"

  if echo "$HELP" | grep -q -- "--dash-port"; then
    tmux new-session -d -s wren "cd /vaults/nvme0/qsb_tower_v1 && exec python3 -u tools/qsb_wren_local_agent.py --host 0.0.0.0 --dash-port 8851 >> logs/wren_8851.log 2>&1"
  elif echo "$HELP" | grep -q -- "--port"; then
    tmux new-session -d -s wren "cd /vaults/nvme0/qsb_tower_v1 && exec python3 -u tools/qsb_wren_local_agent.py --host 0.0.0.0 --port 8851 >> logs/wren_8851.log 2>&1"
  else
    tmux new-session -d -s wren "cd /vaults/nvme0/qsb_tower_v1 && exec python3 -u tools/qsb_wren_local_agent.py >> logs/wren_8851.log 2>&1"
  fi
else
  echo "[FAIL] tools/qsb_wren_local_agent.py missing"
fi

sleep 5

echo
echo "===== 6. START FULL ANIMATED DASHBOARD 8765 ====="
if [ -f src/dashboard/server.py ]; then
  python3 -m py_compile src/dashboard/server.py && echo "[OK] dashboard server compiles"
  tmux new-session -d -s dash8765 "cd /vaults/nvme0/qsb_tower_v1 && PYTHONPATH=/vaults/nvme0/qsb_tower_v1/src exec python3 -u src/dashboard/server.py >> logs/dashboard_8765.log 2>&1"
else
  echo "[FAIL] src/dashboard/server.py missing"
fi

sleep 5

echo
echo "===== 7. START BOARDROOM/IPAD 8852 LAST WITH HIGH FD LIMIT ====="
if [ -f tools/qsb_boardroom_hub.py ]; then
  python3 -m py_compile tools/qsb_boardroom_hub.py && echo "[OK] Boardroom compiles"
  tmux new-session -d -s br "cd /vaults/nvme0/qsb_tower_v1 && ulimit -n 65535 && export MALLOC_ARENA_MAX=2 && exec python3 -u tools/qsb_boardroom_hub.py --port 8852 >> logs/boardroom_hub_8852.log 2>&1"
else
  echo "[FAIL] tools/qsb_boardroom_hub.py missing"
fi

sleep 6

echo
echo "===== 8. REAL PYTHON PID CHECKS ====="
for pattern in \
  "tools/qsb_hq_claude_dash.py" \
  "tools/qsb_wren_local_agent.py" \
  "src/dashboard/server.py" \
  "tools/qsb_boardroom_hub.py"
do
  echo "--- $pattern"
  ps -eo pid,ppid,comm,pcpu,pmem,rss,vsz,etime,nlwp,args \
    | awk -v pat="$pattern" '$3 ~ /python/ && index($0, pat) {print}'
done

echo
echo "===== 9. BOARDROOM REAL PYTHON FD LIMIT ====="
BR_PID="$(ps -eo pid=,comm=,args= | awk '$2 ~ /python/ && /tools\/qsb_boardroom_hub.py/ && /--port 8852/ {print $1; exit}')"
echo "BR_PID=$BR_PID"
if [ -n "$BR_PID" ]; then
  ps -p "$BR_PID" -o pid,ppid,pcpu,pmem,rss,vsz,etime,nlwp,cmd
  echo "open_fds=$(ls /proc/$BR_PID/fd 2>/dev/null | wc -l)"
  grep -i "open files" "/proc/$BR_PID/limits" 2>/dev/null || true
fi

echo
echo "===== 10. PORT CHECKS ====="
ss -ltnp | grep -E ':(8850|8851|8852|8765|9100|11434|9000|9110|9201|9202|19200)\b' || true

echo
echo "===== 11. URL CHECKS ====="
for url in \
  "http://127.0.0.1:8850/" \
  "http://127.0.0.1:8851/" \
  "http://127.0.0.1:8765/" \
  "http://127.0.0.1:8765/api/unified" \
  "http://127.0.0.1:8852/ipad" \
  "http://127.0.0.1:8852/proxy/hq" \
  "http://127.0.0.1:8852/proxy/wren" \
  "http://127.0.0.1:8852/link_health" \
  "http://127.0.0.1:8852/team_live/data" \
  "http://127.0.0.1:8852/tasks/data" \
  "http://127.0.0.1:9100/" \
  "http://127.0.0.1:11434/api/tags" \
  "http://192.168.1.41:9000/" \
  "http://192.168.1.91:9110/"
do
  echo "--- $url"
  tmp="$(mktemp /tmp/qsb_recover_XXXXXX)"
  curl -sS --max-time 12 -o "$tmp" \
    -w "http=%{http_code} total=%{time_total}s size=%{size_download}\n" \
    "$url" 2>&1 || true
  head -c 180 "$tmp" 2>/dev/null | tr '\n' ' '
  echo
  rm -f "$tmp"
done

echo
echo "===== 12. FD WATCH 30 SECONDS ====="
BR_PID="$(ps -eo pid=,comm=,args= | awk '$2 ~ /python/ && /tools\/qsb_boardroom_hub.py/ && /--port 8852/ {print $1; exit}')"
if [ -n "$BR_PID" ]; then
  for i in 1 2 3; do
    echo "--- tick $i $(date -Is)"
    ps -p "$BR_PID" -o pid,pcpu,pmem,rss,vsz,etime,nlwp,cmd
    echo "open_fds=$(ls /proc/$BR_PID/fd 2>/dev/null | wc -l)"
    sleep 10
  done
fi

echo
echo "===== 13. RECENT LOG ERRORS ====="
grep -iE "too many open files|traceback|exception|error|connection refused|no route|empty reply" logs/boardroom_hub_8852.log 2>/dev/null | tail -80 || true

echo
echo "============================================================"
echo "DONE"
echo "Run folder:"
echo "$RUN_DIR"
echo "Report:"
echo "$REPORT"
echo "Latest pointer:"
echo "$RUN_ROOT/LATEST"
echo "============================================================"

cp -a "$REPORT" "$RUN_ROOT/00_LATEST_REPORT.txt"
