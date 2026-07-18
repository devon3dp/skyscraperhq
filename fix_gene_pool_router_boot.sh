#!/usr/bin/env bash
set -u

PROJECT="/vaults/nvme0/qsb_tower_v1"
APP="$PROJECT/tools/skyscraper_gene_pool_router.py"
STARTER="$PROJECT/run_gene_pool_router.sh"
PORT="8860"
LOG="$PROJECT/logs/gene_pool_router_8860.log"
PIDFILE="$PROJECT/runtime/gene_pool_router_8860.pid"

RUN_ROOT="/home/ross/Desktop/SKYSCRAPERHQ_RUNS"
SEND="$RUN_ROOT/00_SEND_THIS_TO_CHATGPT"
STAMP="$(date +%Y%m%d_%H%M%S)"
RUN_DIR="$RUN_ROOT/${STAMP}_fix_gene_pool_router_boot"
REPORT="$RUN_DIR/reports/fix_gene_pool_router_boot_report.txt"

mkdir -p "$RUN_DIR/reports" "$RUN_DIR/backups" "$SEND" "$PROJECT/logs" "$PROJECT/runtime"
exec > >(tee "$REPORT") 2>&1

echo "============================================================"
echo "FIX GENE POOL ROUTER BOOT"
echo "Generated: $(date -Is)"
echo "Project: $PROJECT"
echo "Port: $PORT"
echo "============================================================"

cd "$PROJECT" || exit 1

if [ ! -f "$APP" ]; then
  echo "[FAIL] Missing app: $APP"
  exit 1
fi

echo
echo "===== 1. BACKUP APP ====="
cp -a "$APP" "$RUN_DIR/backups/skyscraper_gene_pool_router.py.bak_$STAMP"
echo "[OK] backup written"

echo
echo "===== 2. PATCH BOOT SO SERVER STARTS BEFORE VAULT SCAN ====="
python3 - <<'PY'
from pathlib import Path

p = Path("/vaults/nvme0/qsb_tower_v1/tools/skyscraper_gene_pool_router.py")
s = p.read_text(errors="ignore")

# Correct Wren naming.
s = s.replace("Ren/GPU", "Wren/GPU")
s = s.replace("Ren owns", "Wren owns")
s = s.replace("Ren or a local GPU fallback", "Wren or a local GPU fallback")
s = s.replace("Ren/GPU untouched", "Wren/GPU untouched")
s = s.replace('"ren": "owns local GPU; no CEO local fallback"', '"wren": "owns local GPU; no CEO local fallback"')

# Remove boot-time full scan before serve_forever.
old = """    scan_keys()
    httpd = ThreadingHTTPServer((HOST, PORT), Handler)
    httpd.serve_forever()
"""
new = """    # Do NOT run a full vault scan before opening the port.
    # The dashboard must come online first; scans run from /api/providers or the Scan button.
    httpd = ThreadingHTTPServer((HOST, PORT), Handler)
    print(f"[READY] dashboard serving on http://127.0.0.1:{PORT}", flush=True)
    httpd.serve_forever()
"""

if old not in s:
    print("[WARN] Exact boot block not found; applying safer line removal")
    s = s.replace("    scan_keys()\n    httpd = ThreadingHTTPServer((HOST, PORT), Handler)\n", "    httpd = ThreadingHTTPServer((HOST, PORT), Handler)\n    print(f\"[READY] dashboard serving on http://127.0.0.1:{PORT}\", flush=True)\n")
else:
    s = s.replace(old, new)

p.write_text(s, encoding="utf-8")
print("[OK] patched boot")
PY

echo
echo "===== 3. COMPILE CHECK ====="
python3 -m py_compile "$APP" && echo "[OK] app compiles" || exit 2

echo
echo "===== 4. STOP OLD ROUTER ====="
if [ -f "$PIDFILE" ]; then
  OLD="$(cat "$PIDFILE" 2>/dev/null || true)"
  if [ -n "$OLD" ]; then
    kill "$OLD" 2>/dev/null || true
  fi
fi

pkill -f "skyscraper_gene_pool_router.py" 2>/dev/null || true
sleep 2

echo
echo "===== 5. RESTART ROUTER ====="
nohup "$STARTER" >> "$LOG" 2>&1 &
PID="$!"
echo "$PID" > "$PIDFILE"
echo "[OK] started pid=$PID"

echo
echo "===== 6. WAIT FOR DASHBOARD PORT ====="
OK="NO"
for i in $(seq 1 20); do
  if curl -sS --max-time 2 "http://127.0.0.1:$PORT/health" >/tmp/gene_pool_health.json 2>/dev/null; then
    OK="YES"
    break
  fi
  sleep 1
done

if [ "$OK" != "YES" ]; then
  echo "[FAIL] Still did not come online."
  echo "--- process check ---"
  ps -ef | grep -E "skyscraper_gene_pool_router.py|gene_pool" | grep -v grep || true
  echo "--- log tail ---"
  tail -n 120 "$LOG" || true
  cp -a "$REPORT" "$SEND/LATEST_REPORT.txt"
  exit 3
fi

echo "[OK] dashboard is online"

echo
echo "===== 7. HEALTH CHECK ====="
curl -sS --max-time 10 "http://127.0.0.1:$PORT/health" | python3 -m json.tool || true

echo
echo "===== 8. OPEN DASHBOARD ====="
LAN_IP="$(hostname -I 2>/dev/null | awk '{print $1}')"
echo "Local: http://127.0.0.1:$PORT"
echo "LAN:   http://${LAN_IP:-127.0.0.1}:$PORT"

if command -v xdg-open >/dev/null 2>&1; then
  xdg-open "http://127.0.0.1:$PORT" >/dev/null 2>&1 || true
fi

echo
echo "===== 9. QUICK PAGE CHECK ====="
curl -sS --max-time 10 "http://127.0.0.1:$PORT/" | head -c 500
echo

echo
echo "============================================================"
echo "DONE"
echo "Dashboard:"
echo "http://127.0.0.1:$PORT"
echo "Report:"
echo "$REPORT"
echo "Send-back:"
echo "$SEND/LATEST_REPORT.txt"
echo "============================================================"

cp -a "$REPORT" "$SEND/LATEST_REPORT.txt"
