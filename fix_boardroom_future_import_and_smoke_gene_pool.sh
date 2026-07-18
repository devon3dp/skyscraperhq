#!/usr/bin/env bash
set -u

PROJECT="/vaults/nvme0/qsb_tower_v1"
BOARDROOM="$PROJECT/tools/qsb_boardroom_hub.py"
ROUTER="$PROJECT/tools/skyscraper_gene_pool_router.py"
ROUTER_START="$PROJECT/run_gene_pool_router.sh"
BOARDROOM_LOG="$PROJECT/logs/boardroom_hub_8852.log"
ROUTER_LOG="$PROJECT/logs/gene_pool_router_8860.log"

RUN_ROOT="/home/ross/Desktop/SKYSCRAPERHQ_RUNS"
SEND="$RUN_ROOT/00_SEND_THIS_TO_CHATGPT"
STAMP="$(date +%Y%m%d_%H%M%S)"
RUN_DIR="$RUN_ROOT/${STAMP}_fix_boardroom_future_gene_pool"
REPORT="$RUN_DIR/reports/fix_boardroom_future_gene_pool_report.txt"

mkdir -p "$RUN_DIR/reports" "$RUN_DIR/backups" "$RUN_DIR/logs" "$SEND" "$PROJECT/runtime" "$PROJECT/logs"
rm -f "$RUN_ROOT/LATEST"
ln -s "$RUN_DIR" "$RUN_ROOT/LATEST"

exec > >(tee "$REPORT") 2>&1

echo "============================================================"
echo "FIX BOARDROOM FUTURE IMPORT + SMOKE GENE POOL IPAD WIRING"
echo "Generated: $(date -Is)"
echo "Project: $PROJECT"
echo "============================================================"
echo "Rules:"
echo " - Fix Boardroom syntax only."
echo " - Keep Claude HQ name."
echo " - Keep Wren protected."
echo " - CEOs use API Gene Pool only."
echo " - No key changes."
echo " - No secure key printing."
echo " - No trading changes."
echo "============================================================"

cd "$PROJECT" || exit 1

echo
echo "===== 1. BACKUP CURRENT BROKEN FILE ====="
cp -a "$BOARDROOM" "$RUN_DIR/backups/qsb_boardroom_hub.py.broken_before_future_fix_$STAMP"
cp -a "$ROUTER" "$RUN_DIR/backups/skyscraper_gene_pool_router.py.before_smoke_$STAMP"
echo "[OK] backups written"

echo
echo "===== 2. FIX FUTURE IMPORT POSITION PROBLEM ====="
python3 - <<'PY'
from pathlib import Path

p = Path("/vaults/nvme0/qsb_tower_v1/tools/qsb_boardroom_hub.py")
s = p.read_text(errors="ignore")

count = s.count("from __future__ import annotations")
if count:
    s = s.replace("from __future__ import annotations\n", "")
    s = s.replace("from __future__ import annotations\r\n", "")
    p.write_text(s, encoding="utf-8")
    print(f"[OK] removed {count} future import line(s); not needed on Python 3.12")
else:
    print("[OK] no future import line found")
PY

echo
echo "===== 3. COMPILE CHECKS ====="
python3 -m py_compile "$ROUTER" && echo "[OK] Gene Pool Router compiles" || exit 2
python3 -m py_compile "$BOARDROOM" && echo "[OK] Boardroom compiles" || exit 3

echo
echo "===== 4. RESTART GENE POOL ROUTER ====="
[ -f "$PROJECT/runtime/gene_pool_router_8860.pid" ] && kill "$(cat "$PROJECT/runtime/gene_pool_router_8860.pid" 2>/dev/null)" 2>/dev/null || true
pkill -f "skyscraper_gene_pool_router.py" 2>/dev/null || true
sleep 2

nohup "$ROUTER_START" >> "$ROUTER_LOG" 2>&1 &
GPID="$!"
echo "$GPID" > "$PROJECT/runtime/gene_pool_router_8860.pid"
echo "[OK] Gene Pool Router pid=$GPID"

echo
echo "===== 5. RESTART BOARDROOM/IPAD ====="
pkill -f "tools/qsb_boardroom_hub.py.*--port 8852" 2>/dev/null || true
sleep 2

(
  cd "$PROJECT" || exit 1
  ulimit -n 65535
  export MALLOC_ARENA_MAX=2
  exec python3 -u tools/qsb_boardroom_hub.py --port 8852 >> "$BOARDROOM_LOG" 2>&1
) &
BPID="$!"
echo "$BPID" > "$PROJECT/runtime/boardroom_hub_8852.pid"
echo "[OK] Boardroom pid=$BPID"

echo
echo "===== 6. WAIT FOR PORTS ====="
for port in 8860 8852; do
  OK=NO
  for i in $(seq 1 30); do
    if curl -sS --max-time 2 "http://127.0.0.1:$port/" >/tmp/qsb_port_check.html 2>/dev/null; then
      OK=YES
      break
    fi
    sleep 1
  done

  if [ "$OK" != YES ]; then
    echo "[FAIL] Port $port did not come online"
    echo "--- Gene Pool log tail ---"
    tail -n 100 "$ROUTER_LOG" || true
    echo "--- Boardroom log tail ---"
    tail -n 160 "$BOARDROOM_LOG" || true
    cp -a "$REPORT" "$SEND/LATEST_REPORT.txt"
    exit 4
  fi

  echo "[OK] port $port online"
done

echo
echo "===== 7. HTTP SMOKE TESTS ====="
for url in \
  "http://127.0.0.1:8860/health" \
  "http://127.0.0.1:8860/api/live" \
  "http://127.0.0.1:8852/ipad" \
  "http://127.0.0.1:8852/proxy/gene_pool" \
  "http://127.0.0.1:8852/proxy/gene_pool/api/live"
do
  echo "--- $url"
  curl -sS --max-time 25 -o "$RUN_DIR/logs/http.tmp" -w "http=%{http_code} total=%{time_total}s size=%{size_download}\n" "$url" || true
  head -c 260 "$RUN_DIR/logs/http.tmp" 2>/dev/null || true
  echo
done

echo
echo "===== 8. CEO SUBMIT SMOKE TESTS THROUGH BOARDROOM PROXY ====="

submit_job() {
  local ceo="$1"
  local task="$2"
  local ask="$3"

  echo "--- submit: $ceo / $task"

  python3 - "$ceo" "$task" "$ask" <<'PY'
import sys, json, urllib.request, urllib.error

ceo, task, ask = sys.argv[1], sys.argv[2], sys.argv[3]
payload = {"ceo": ceo, "task": task, "ask": ask}
data = json.dumps(payload).encode("utf-8")

req = urllib.request.Request(
    "http://127.0.0.1:8852/proxy/gene_pool/api/submit_job",
    data=data,
    headers={"Content-Type": "application/json"},
    method="POST",
)

try:
    with urllib.request.urlopen(req, timeout=45) as r:
        body = r.read().decode("utf-8", "replace")
        print("http", r.status)
        print(body[:1600])
except urllib.error.HTTPError as e:
    print("HTTP_ERROR", e.code)
    print(e.read().decode("utf-8", "replace")[:1600])
except Exception as e:
    print("ERROR", repr(e))
PY
}

submit_job "Claude HQ" "architecture" "Claude HQ submits a Boardroom architecture job through the iPad dash into the Brain Router API Gene Pool."
submit_job "CEO 2" "coding" "CEO 2 submits a coding repair job through the iPad dash into the Brain Router API Gene Pool."
submit_job "CEO 3" "summary" "CEO 3 submits a summary job through the iPad dash into the Brain Router API Gene Pool."

echo
echo "===== 9. LET DASH UPDATE ====="
sleep 8

echo
echo "===== 10. FINAL LIVE DATA CHECK ====="
curl -sS --max-time 25 "http://127.0.0.1:8860/api/live" > "$RUN_DIR/reports/final_gene_pool_live.json"

python3 - <<PYSHOW
import json
p="$RUN_DIR/reports/final_gene_pool_live.json"
d=json.load(open(p))
m=d.get("metrics",{})
print("ok:", d.get("ok"))
print("stored_key_count:", m.get("stored_key_count"))
print("active_provider_count:", m.get("active_provider_count"))
print("route_count:", m.get("autonomy",{}).get("route_count"))
print("events:", len(d.get("logs",[])))
print("latest_decision:", d.get("latest_decision"))
print("")
print("CEO PANELS:")
for name,panel in (d.get("ceo_panels") or {}).items():
    print(name, "| task=", panel.get("task"), "| provider=", panel.get("provider_label"), "| ask=", (panel.get("ask") or "")[:100], "| reply=", (panel.get("reply") or "")[:100])
print("")
print("JOB BOARD TOP 9:")
for j in (d.get("job_board") or [])[:9]:
    print(j.get("event"), j.get("from"), "->", j.get("to"), "|", j.get("task"), "|", (j.get("ask") or "")[:100])
PYSHOW

echo
echo "===== 11. LAN URLS ====="
LAN_IP="$(hostname -I 2>/dev/null | awk '{print $1}')"
echo "Gene Pool direct:"
echo "http://${LAN_IP:-127.0.0.1}:8860"
echo
echo "Boardroom iPad:"
echo "http://${LAN_IP:-127.0.0.1}:8852/ipad"
echo
echo "Gene Pool through iPad/Boardroom proxy:"
echo "http://${LAN_IP:-127.0.0.1}:8852/proxy/gene_pool"

if command -v xdg-open >/dev/null 2>&1; then
  xdg-open "http://127.0.0.1:8852/ipad" >/dev/null 2>&1 || true
  xdg-open "http://127.0.0.1:8852/proxy/gene_pool" >/dev/null 2>&1 || true
fi

echo
echo "===== 12. RECENT ERRORS ====="
echo "--- Gene Pool log ---"
tail -n 100 "$ROUTER_LOG" | grep -Ei "error|exception|traceback|fail|warning|ready|boot" || true
echo "--- Boardroom log ---"
tail -n 160 "$BOARDROOM_LOG" | grep -Ei "error|exception|traceback|gene|proxy|8852|too many|ready|boot|future" || true

echo
echo "============================================================"
echo "DONE — BOARDROOM FIXED + IPAD/CEO SMOKE TEST COMPLETE"
echo
echo "Open iPad Boardroom:"
echo "http://${LAN_IP:-127.0.0.1}:8852/ipad"
echo
echo "Open Brain Router through Boardroom:"
echo "http://${LAN_IP:-127.0.0.1}:8852/proxy/gene_pool"
echo
echo "Direct Brain Router:"
echo "http://${LAN_IP:-127.0.0.1}:8860"
echo
echo "Report:"
echo "$REPORT"
echo
echo "Send-back:"
echo "$SEND/LATEST_REPORT.txt"
echo "============================================================"

cp -a "$REPORT" "$SEND/LATEST_REPORT.txt"
cp -a "$RUN_DIR/reports/final_gene_pool_live.json" "$SEND/final_gene_pool_live.json"
