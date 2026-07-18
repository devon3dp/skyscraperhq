#!/usr/bin/env bash
set -u

PROJECT="/vaults/nvme0/qsb_tower_v1"

RUN_ROOT="/home/ross/Desktop/SKYSCRAPERHQ_RUNS"
SEND="$RUN_ROOT/00_SEND_THIS_TO_CHATGPT"
STAMP="$(date +%Y%m%d_%H%M%S)"
RUN_DIR="$RUN_ROOT/${STAMP}_dashboard_service_layer_truth_smoke"
REPORT="$RUN_DIR/reports/dashboard_service_layer_truth_smoke_report.txt"

mkdir -p "$RUN_DIR/reports" "$RUN_DIR/logs" "$SEND" "$PROJECT/runtime" "$PROJECT/logs" "$PROJECT/data/registries"
rm -f "$RUN_ROOT/LATEST"
ln -s "$RUN_DIR" "$RUN_ROOT/LATEST"

exec > >(tee "$REPORT") 2>&1

echo "============================================================"
echo "SKYSCRAPERHQ — DASHBOARD / SERVICE LAYER TRUTH SMOKE"
echo "Generated: $(date -Is)"
echo "Project: $PROJECT"
echo "============================================================"
echo "Purpose:"
echo " - Stop circular task-routing noise."
echo " - Smoke-test Claude HQ, Wren, TP, Acer, Boardroom, Gene Pool."
echo " - Do not repair yet."
echo " - Do not mark tasks done."
echo " - Do not touch keys."
echo " - Do not touch trading."
echo "============================================================"

cd "$PROJECT" || exit 1

echo
echo "===== 1. PAUSE AUTONOMOUS LOOPS THAT CAN KEEP REPEATING ====="

pause_pidfile() {
  local name="$1"
  local pidfile="$2"
  if [ -f "$pidfile" ]; then
    local pid
    pid="$(cat "$pidfile" 2>/dev/null || true)"
    if [ -n "$pid" ] && kill -0 "$pid" 2>/dev/null; then
      kill "$pid" 2>/dev/null || true
      echo "[PAUSED] $name pid=$pid"
    else
      echo "[OK] $name not running from pidfile"
    fi
  else
    echo "[OK] $name pidfile missing"
  fi
}

pause_pidfile "Task Council Auto Dispatcher" "$PROJECT/runtime/task_council_auto_dispatcher.pid"
pause_pidfile "Worker Executor Verifier" "$PROJECT/runtime/worker_executor_verifier.pid"

pkill -f "qsb_task_council_auto_dispatcher.py" 2>/dev/null || true
pkill -f "qsb_worker_executor_verifier.py" 2>/dev/null || true

echo "[OK] repetitive execution loops paused"
sleep 2

echo
echo "===== 2. CURRENT RUNNING SKYSCRAPER PROCESSES ====="
ps -eo pid,ppid,etime,cmd | grep -E "qsb_|skyscraper_|boardroom|wren|claude|acer|tp|gene_pool|8850|8851|8852|8853|8860|9000|9100" | grep -v grep || true

echo
echo "===== 3. LISTENING PORTS 8765 / 8850-8860 / 9000 / 9100 ====="
ss -ltnp 2>/dev/null | grep -E ":(8765|8850|8851|8852|8853|8854|8855|8856|8857|8858|8859|8860|9000|9100)\b" || true

echo
echo "===== 4. DASHBOARD FILE DISCOVERY ====="
echo "--- known dashboard/service files ---"
find "$PROJECT" -maxdepth 3 -type f \
  \( -iname '*claude*' -o -iname '*hq*' -o -iname '*wren*' -o -iname '*tp*' -o -iname '*acer*' -o -iname '*boardroom*' -o -iname '*gene_pool*' -o -iname '*dashboard*' \) \
  | sort | sed "s#^$PROJECT/##" | head -n 240

echo
echo "===== 5. BOARDROOM LINK HEALTH ====="
curl -sS --max-time 35 "http://127.0.0.1:8852/link_health" > "$RUN_DIR/reports/link_health.json" 2>"$RUN_DIR/logs/link_health.err" || true
python3 - <<PY
import json, pathlib
p=pathlib.Path("$RUN_DIR/reports/link_health.json")
if not p.exists() or not p.read_text(errors="ignore").strip():
    print("[FAIL] /link_health did not return JSON")
else:
    try:
        d=json.loads(p.read_text(errors="ignore"))
        print(json.dumps(d, indent=2)[:12000])
    except Exception as e:
        print("[FAIL] link_health parse error:", repr(e))
        print(p.read_text(errors="ignore")[:4000])
PY

echo
echo "===== 6. DIRECT PORT SMOKE ====="

smoke_url() {
  local label="$1"
  local url="$2"
  local out="$RUN_DIR/logs/$(echo "$label" | tr ' /:' '____').body"
  echo "--- $label"
  echo "URL: $url"
  curl -sS --max-time 20 -o "$out" -w "http=%{http_code} total=%{time_total}s size=%{size_download}\n" "$url" || true
  head -c 500 "$out" 2>/dev/null || true
  echo
}

smoke_url "Boardroom iPad 8852" "http://127.0.0.1:8852/ipad"
smoke_url "Boardroom link_health 8852" "http://127.0.0.1:8852/link_health"
smoke_url "Claude HQ direct 8850" "http://127.0.0.1:8850/"
smoke_url "Wren direct 8851" "http://127.0.0.1:8851/"
smoke_url "Wren metrics 8851" "http://127.0.0.1:8851/wren_metrics"
smoke_url "Wren metrics sidecar 8853" "http://127.0.0.1:8853/api/metrics"
smoke_url "Gene Pool direct 8860" "http://127.0.0.1:8860/"
smoke_url "Gene Pool API direct 8860" "http://127.0.0.1:8860/api/live"
smoke_url "TP likely 9000" "http://127.0.0.1:9000/"
smoke_url "Acer likely 9000 data guess" "http://127.0.0.1:9000/data"
smoke_url "HQ node 9100" "http://127.0.0.1:9100/"

echo
echo "===== 7. BOARDROOM PROXY SMOKE ====="
smoke_url "proxy hq" "http://127.0.0.1:8852/proxy/hq"
smoke_url "proxy wren" "http://127.0.0.1:8852/proxy/wren"
smoke_url "proxy tp" "http://127.0.0.1:8852/proxy/tp"
smoke_url "proxy acer" "http://127.0.0.1:8852/proxy/acer"
smoke_url "proxy gene_pool" "http://127.0.0.1:8852/proxy/gene_pool"
smoke_url "team_live" "http://127.0.0.1:8852/team_live"
smoke_url "team_live data" "http://127.0.0.1:8852/team_live/data"
smoke_url "tasks" "http://127.0.0.1:8852/tasks"
smoke_url "tasks data" "http://127.0.0.1:8852/tasks/data"
smoke_url "town square" "http://127.0.0.1:8852/town_square"
smoke_url "town feed" "http://127.0.0.1:8852/town_square_feed"

echo
echo "===== 8. BOARDROOM ROUTE MAP EXTRACT ====="
python3 - <<'PY'
from pathlib import Path
import re
p=Path("/vaults/nvme0/qsb_tower_v1/tools/qsb_boardroom_hub.py")
if not p.exists():
    print("[FAIL] Boardroom file missing")
    raise SystemExit
s=p.read_text(errors="ignore")
routes=sorted(set(re.findall(r'["\'](/[A-Za-z0-9_./?=&{}:-]+)["\']', s)))
for r in routes:
    if any(x in r.lower() for x in ["proxy", "wren", "claude", "hq", "tp", "acer", "team", "task", "town", "council", "gene", "link", "health"]):
        print(r)
PY

echo
echo "===== 9. RECENT LOG ERRORS ====="

show_errors() {
  local label="$1"
  local file="$2"
  echo "--- $label: $file"
  if [ -f "$file" ]; then
    tail -n 220 "$file" | grep -Ei "error|exception|traceback|Errno|connection refused|not found|failed|broken|too many|timeout|refused|8850|8851|8852|9000|acer|tp|wren|claude|hq" || true
  else
    echo "[missing]"
  fi
}

show_errors "Boardroom" "$PROJECT/logs/boardroom_hub_8852.log"
show_errors "Claude HQ" "$PROJECT/logs/hq_claude_8850.log"
show_errors "Wren" "$PROJECT/logs/wren_local_agent_8851.log"
show_errors "Wren metrics sidecar" "$PROJECT/logs/wren_metrics_sidecar_8853.log"
show_errors "Gene Pool" "$PROJECT/logs/gene_pool_router_8860.log"
show_errors "Task auto dispatcher" "$PROJECT/logs/task_council_auto_dispatcher.log"
show_errors "Worker executor verifier" "$PROJECT/logs/worker_executor_verifier.log"

echo
echo "===== 10. MACHINE SUMMARY ====="
python3 - <<PY'
import json, pathlib, re

run = pathlib.Path("$RUN_DIR/logs")
checks = []
for f in run.glob("*.body"):
    pass

# Parse link health if available.
link_path = pathlib.Path("$RUN_DIR/reports/link_health.json")
if link_path.exists():
    try:
        d=json.loads(link_path.read_text(errors="ignore"))
        links=d.get("links", [])
        print("LINK HEALTH SUMMARY:")
        for x in links:
            print(f"- {x.get('name')}: ok={x.get('ok')} url={x.get('url')} err={x.get('err','')[:100]}")
    except Exception as e:
        print("Could not parse link health:", e)

print("")
print("CRITICAL INTERPRETATION:")
print("- If Claude HQ 8850 is refused, the Claude HQ dashboard service is not running.")
print("- If Wren 8851 is refused, the Wren dashboard service is not running.")
print("- If proxy/tp or proxy/acer fails, Boardroom has links but the remote/local service behind that proxy is down or misconfigured.")
print("- If team_live works but named dashboards fail, the team panel is not enough; each dashboard needs its own process or reachable proxy target.")
print("- Do not restart autonomous task loops until dashboard service layer is repaired.")
PY

echo
echo "===== 11. LAN URLS ====="
LAN_IP="$(hostname -I 2>/dev/null | awk '{print $1}')"
echo "Boardroom iPad:"
echo "http://${LAN_IP:-127.0.0.1}:8852/ipad"
echo
echo "Claude HQ expected:"
echo "http://${LAN_IP:-127.0.0.1}:8850/"
echo
echo "Wren expected:"
echo "http://${LAN_IP:-127.0.0.1}:8851/"
echo
echo "Wren metrics expected:"
echo "http://${LAN_IP:-127.0.0.1}:8851/wren_metrics"
echo
echo "Gene Pool:"
echo "http://${LAN_IP:-127.0.0.1}:8852/proxy/gene_pool"

echo
echo "============================================================"
echo "DONE — DASHBOARD SERVICE LAYER TRUTH SMOKE COMPLETE"
echo "Report:"
echo "$REPORT"
echo "Send-back:"
echo "$SEND/LATEST_REPORT.txt"
echo "============================================================"

cp -a "$REPORT" "$SEND/LATEST_REPORT.txt"
cp -a "$RUN_DIR/reports/link_health.json" "$SEND/link_health.json" 2>/dev/null || true
