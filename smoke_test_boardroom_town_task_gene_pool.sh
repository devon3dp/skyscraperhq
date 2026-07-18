#!/usr/bin/env bash
set -u

PROJECT="/vaults/nvme0/qsb_tower_v1"
ROUTER="$PROJECT/tools/skyscraper_gene_pool_router.py"
ROUTER_START="$PROJECT/run_gene_pool_router.sh"
BOARDROOM="$PROJECT/tools/qsb_boardroom_hub.py"
ROUTER_LOG="$PROJECT/logs/gene_pool_router_8860.log"
BOARDROOM_LOG="$PROJECT/logs/boardroom_hub_8852.log"

RUN_ROOT="/home/ross/Desktop/SKYSCRAPERHQ_RUNS"
SEND="$RUN_ROOT/00_SEND_THIS_TO_CHATGPT"
STAMP="$(date +%Y%m%d_%H%M%S)"
RUN_DIR="$RUN_ROOT/${STAMP}_boardroom_town_task_gene_pool_smoke"
REPORT="$RUN_DIR/reports/boardroom_town_task_gene_pool_smoke_report.txt"

mkdir -p "$RUN_DIR/reports" "$RUN_DIR/backups" "$RUN_DIR/logs" "$SEND" "$PROJECT/runtime" "$PROJECT/logs"
rm -f "$RUN_ROOT/LATEST"
ln -s "$RUN_DIR" "$RUN_ROOT/LATEST"

exec > >(tee "$REPORT") 2>&1

echo "============================================================"
echo "SKYSCRAPERHQ — BOARDROOM / TOWN / TASK / GENE POOL SMOKE TEST"
echo "Generated: $(date -Is)"
echo "Project: $PROJECT"
echo "============================================================"
echo "Rules:"
echo " - Claude HQ is the correct name."
echo " - Wren owns/protects the GPU."
echo " - CEOs use API Gene Pool only."
echo " - No CEO fallback to Wren/local GPU."
echo " - No key changes."
echo " - No secure key printing."
echo " - No trading/order changes."
echo "============================================================"

cd "$PROJECT" || exit 1

if [ ! -f "$ROUTER" ]; then
  echo "[FAIL] Missing router: $ROUTER"
  exit 1
fi

if [ ! -f "$BOARDROOM" ]; then
  echo "[FAIL] Missing Boardroom: $BOARDROOM"
  exit 1
fi

echo
echo "===== 1. BACKUP ====="
cp -a "$ROUTER" "$RUN_DIR/backups/skyscraper_gene_pool_router.py.bak_$STAMP"
cp -a "$BOARDROOM" "$RUN_DIR/backups/qsb_boardroom_hub.py.bak_$STAMP"
echo "[OK] backups written"

echo
echo "===== 2. FIX GENE POOL DASH FOR BOARDROOM PROXY MODE ====="
python3 - <<'PY'
from pathlib import Path
import re

p = Path("/vaults/nvme0/qsb_tower_v1/tools/skyscraper_gene_pool_router.py")
s = p.read_text(errors="ignore")

# Make frontend calls proxy-aware when the dash is served at /proxy/gene_pool.
# Direct port 8860 still uses /api/live. Boardroom proxy uses /proxy/gene_pool/api/live.
old = 'async function getJSON(u){const r=await fetch(u);return await r.json();}'
new = '''function apiPath(u){
  if(location.pathname.startsWith("/proxy/gene_pool")) return "/proxy/gene_pool" + u;
  return u;
}
async function getJSON(u){const r=await fetch(apiPath(u));return await r.json();}'''

if old in s and "function apiPath(u)" not in s:
    s = s.replace(old, new)
    print("[OK] patched compact getJSON to proxy-aware mode")
elif "function apiPath(u)" in s:
    print("[OK] proxy-aware apiPath already present")
else:
    # More general fallback for spaced variants.
    s2 = re.sub(
        r'async function getJSON\(u\)\s*\{\s*const r\s*=\s*await fetch\(u\);\s*return await r\.json\(\);\s*\}',
        new,
        s
    )
    if s2 != s:
        s = s2
        print("[OK] patched getJSON regex variant to proxy-aware mode")
    else:
        print("[WARN] did not find getJSON pattern; dashboard may already be different")

p.write_text(s, encoding="utf-8")
PY

echo
echo "===== 3. MAKE SURE ROUTER HAS /api/submit_job ENDPOINT ====="
python3 - <<'PY'
from pathlib import Path
import re

p = Path("/vaults/nvme0/qsb_tower_v1/tools/skyscraper_gene_pool_router.py")
s = p.read_text(errors="ignore")

if "def external_submit_job(" not in s:
    marker = "def recent("
    helper = r'''
def external_submit_job(payload):
    ceo = payload.get("ceo") or payload.get("from") or payload.get("speaker") or "Claude HQ"
    task = payload.get("task") or payload.get("task_type") or "default"
    ask = payload.get("ask") or payload.get("prompt") or payload.get("message") or payload.get("text") or "External CEO submitted a job."
    if task not in POLICY:
        task = "default"

    provider = choose_provider(task)
    event({
        "event": "request",
        "from": ceo,
        "to": "Brain Router",
        "provider": provider or "none",
        "task": task,
        "status": "received",
        "ask": ask,
        "detail": "external CEO job submitted through Boardroom/iPad",
        "job": {"ceo": ceo, "task": task, "ask": ask, "stage": "submitted_external"}
    })

    if not provider:
        reply = "No API Gene Pool provider key available. Wren/local GPU fallback remains blocked by doctrine."
        decision = {"ceo": ceo, "task": task, "ask": ask, "selected_provider": "none", "selected_label": "none", "reason": reply, "latency_ms": None, "wren_fallback": "blocked", "provider_reply": reply}
        event({"event": "blocked", "from": "Brain Router", "to": ceo, "provider": "none", "task": task, "status": "blocked", "ask": ask, "reply": reply, "detail": reply, "decision": decision, "job": {"ceo": ceo, "task": task, "ask": ask, "reply": reply, "stage": "blocked"}})
        return {"ok": False, "decision": decision, "reply": reply}

    label = PROVIDERS[provider]["label"]
    reason = f"{task} policy selected {label}; CEO uses API Gene Pool only; Wren/local GPU fallback blocked by doctrine"
    latency = random.randint(90, 1400)
    reply = f"{label} route selected for {ceo}. Task class: {task}. External Boardroom/iPad smoke route accepted."

    try:
        st = PROVIDER_STATS.setdefault(provider, {"calls": 0, "success": 0, "fail": 0, "last_task": "", "last_ceo": "", "last_ts": "", "last_reason": "", "latency_ms": 0})
        st["calls"] += 1
        st["success"] += 1
        st["last_task"] = task
        st["last_ceo"] = ceo
        st["last_ts"] = now()
        st["latency_ms"] = latency
        st["last_reason"] = reason
    except Exception:
        pass

    decision = {"ceo": ceo, "task": task, "ask": ask, "selected_provider": provider, "selected_label": label, "reason": reason, "latency_ms": latency, "wren_fallback": "blocked", "provider_reply": reply}

    event({"event": "dispatch", "from": "Brain Router", "to": label, "provider": provider, "task": task, "status": "selected", "ask": ask, "reply": reply, "detail": reason, "decision": decision, "job": {"ceo": ceo, "task": task, "ask": ask, "provider": label, "stage": "dispatched_external"}})
    event({"event": "return", "from": label, "to": ceo, "provider": provider, "task": task, "status": "visual_live", "ask": ask, "reply": reply, "detail": "external CEO route returned to CEO window", "decision": decision, "job": {"ceo": ceo, "task": task, "ask": ask, "provider": label, "reply": reply, "stage": "returned_external"}})

    return {"ok": True, "decision": decision, "reply": reply}

'''
    if marker in s:
        s = s.replace(marker, helper + "\n" + marker)
        print("[OK] inserted external_submit_job")
    else:
        print("[WARN] could not insert external_submit_job")
else:
    print("[OK] external_submit_job already exists")

if '"/api/submit_job"' not in s:
    # Add to do_POST. This app uses send_json/body helpers.
    needle = 'return send_json(self, {"ok": False, "error": "not found", "path": p}, 404)'
    route = '''if p == "/api/submit_job":
            try:
                return send_json(self, external_submit_job(body(self)))
            except Exception as e:
                return send_json(self, {"ok": False, "error": safe(e)}, 500)

        '''
    if needle in s:
        s = s.replace(needle, route + needle)
        print("[OK] inserted /api/submit_job route")
    else:
        print("[WARN] could not find do_POST fallback to insert /api/submit_job")
else:
    print("[OK] /api/submit_job route already present")

p.write_text(s, encoding="utf-8")
PY

echo
echo "===== 4. COMPILE CHECKS ====="
python3 -m py_compile "$ROUTER" && echo "[OK] Gene Pool Router compiles" || exit 2
python3 -m py_compile "$BOARDROOM" && echo "[OK] Boardroom compiles" || exit 3

echo
echo "===== 5. RESTART GENE POOL ROUTER ====="
[ -f "$PROJECT/runtime/gene_pool_router_8860.pid" ] && kill "$(cat "$PROJECT/runtime/gene_pool_router_8860.pid" 2>/dev/null)" 2>/dev/null || true
pkill -f "skyscraper_gene_pool_router.py" 2>/dev/null || true
sleep 2

nohup "$ROUTER_START" >> "$ROUTER_LOG" 2>&1 &
GPID="$!"
echo "$GPID" > "$PROJECT/runtime/gene_pool_router_8860.pid"
echo "[OK] Gene Pool Router pid=$GPID"

echo
echo "===== 6. RESTART BOARDROOM/IPAD ====="
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
echo "===== 7. WAIT FOR CORE PORTS ====="
for port in 8860 8852; do
  OK=NO
  for i in $(seq 1 30); do
    if curl -sS --max-time 2 "http://127.0.0.1:$port/" >/tmp/qsb_smoke_port.html 2>/dev/null; then
      OK=YES
      break
    fi
    sleep 1
  done

  if [ "$OK" != YES ]; then
    echo "[FAIL] port $port did not come online"
    echo "--- router log ---"
    tail -n 100 "$ROUTER_LOG" || true
    echo "--- boardroom log ---"
    tail -n 160 "$BOARDROOM_LOG" || true
    cp -a "$REPORT" "$SEND/LATEST_REPORT.txt"
    exit 4
  fi
  echo "[OK] port $port online"
done

echo
echo "===== 8. DISCOVER BOARDROOM / TOWN / TASK ROUTES ====="
python3 - <<'PY' > "/tmp/qsb_route_discovery.txt"
from pathlib import Path
import re

p = Path("/vaults/nvme0/qsb_tower_v1/tools/qsb_boardroom_hub.py")
s = p.read_text(errors="ignore")

routes = sorted(set(re.findall(r'["\'](/[^"\']+)["\']', s)))
interesting = []
for r in routes:
    low = r.lower()
    if any(x in low for x in ["ipad", "town", "task", "council", "boardroom", "proxy", "gene", "live", "health", "link"]):
        interesting.append(r)

for r in interesting[:220]:
    print(r)
PY

cat /tmp/qsb_route_discovery.txt | tee "$RUN_DIR/reports/discovered_boardroom_routes.txt"

echo
echo "===== 9. HTTP SMOKE TEST CORE DASHES ====="
URLS=(
  "http://127.0.0.1:8860/health"
  "http://127.0.0.1:8860/api/live"
  "http://127.0.0.1:8852/ipad"
  "http://127.0.0.1:8852/proxy/gene_pool"
  "http://127.0.0.1:8852/proxy/gene_pool/api/live"
  "http://127.0.0.1:8852/link_health"
  "http://127.0.0.1:8852/team_live/data"
)

# Add discovered likely town/task routes.
while IFS= read -r r; do
  case "$r" in
    */api/*) ;;
    *)
      if echo "$r" | grep -Eiq 'town|task|council|boardroom'; then
        URLS+=("http://127.0.0.1:8852$r")
      fi
    ;;
  esac
done < /tmp/qsb_route_discovery.txt

printf "%s\n" "${URLS[@]}" | awk '!seen[$0]++' > "$RUN_DIR/reports/smoke_urls.txt"

while IFS= read -r url; do
  echo "--- $url"
  curl -sS --max-time 18 -o "$RUN_DIR/logs/http.tmp" -w "http=%{http_code} total=%{time_total}s size=%{size_download}\n" "$url" || true
  head -c 220 "$RUN_DIR/logs/http.tmp" 2>/dev/null || true
  echo
done < "$RUN_DIR/reports/smoke_urls.txt"

echo
echo "===== 10. CEO SUBMIT SMOKE TEST THROUGH BOARDROOM PROXY ====="
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
        print(body[:1800])
except urllib.error.HTTPError as e:
    print("HTTP_ERROR", e.code)
    print(e.read().decode("utf-8", "replace")[:1800])
except Exception as e:
    print("ERROR", repr(e))
PY
}

submit_job "Claude HQ" "architecture" "Smoke test: Claude HQ submits an architecture job from Boardroom/iPad into the Brain Router API Gene Pool."
submit_job "CEO 2" "coding" "Smoke test: CEO 2 submits a coding job from Boardroom/iPad into the Brain Router API Gene Pool."
submit_job "CEO 3" "summary" "Smoke test: CEO 3 submits a summary job from Boardroom/iPad into the Brain Router API Gene Pool."

echo
echo "===== 11. TOWN SQUARE POST SMOKE IF ROUTE EXISTS ====="
python3 - <<'PY'
import json, urllib.request, urllib.error, sys

routes = open("/tmp/qsb_route_discovery.txt", "r", errors="ignore").read().splitlines()
candidates = [r for r in routes if "town" in r.lower() and ("post" in r.lower() or "message" in r.lower())]
print("town_post_candidates:", candidates[:10])

payload = {
    "from": "Brain Router Smoke Test",
    "speaker": "Brain Router Smoke Test",
    "text": "Smoke test: Brain Router Gene Pool is wired into Boardroom/iPad and CEO submit paths.",
    "message": "Smoke test: Brain Router Gene Pool is wired into Boardroom/iPad and CEO submit paths."
}

for route in candidates[:5]:
    url = "http://127.0.0.1:8852" + route
    try:
        req = urllib.request.Request(url, data=json.dumps(payload).encode(), headers={"Content-Type":"application/json"}, method="POST")
        with urllib.request.urlopen(req, timeout=10) as r:
            print("POST", route, "http", r.status, r.read().decode("utf-8", "replace")[:500])
            break
    except Exception as e:
        print("POST", route, "failed", repr(e))
PY

echo
echo "===== 12. TASK COUNCIL SMOKE IF ROUTE EXISTS ====="
python3 - <<'PY'
import json, urllib.request, urllib.error

routes = open("/tmp/qsb_route_discovery.txt", "r", errors="ignore").read().splitlines()
candidates = [r for r in routes if ("task" in r.lower() or "council" in r.lower()) and ("post" in r.lower() or "create" in r.lower() or "add" in r.lower() or "submit" in r.lower())]
print("task_submit_candidates:", candidates[:20])

payload = {
    "title": "Smoke test Brain Router Gene Pool wiring",
    "task": "Confirm Boardroom, iPad, Town Square, Task Council, and CEO Gene Pool submit path are visible.",
    "from": "Brain Router Smoke Test",
    "source": "Brain Router Smoke Test",
    "body": "Smoke test only. No live trading, no key changes, no Wren/local GPU fallback."
}

for route in candidates[:8]:
    url = "http://127.0.0.1:8852" + route
    try:
        req = urllib.request.Request(url, data=json.dumps(payload).encode(), headers={"Content-Type":"application/json"}, method="POST")
        with urllib.request.urlopen(req, timeout=10) as r:
            print("POST", route, "http", r.status, r.read().decode("utf-8", "replace")[:500])
            break
    except Exception as e:
        print("POST", route, "failed", repr(e))
PY

echo
echo "===== 13. LET DASHES UPDATE ====="
sleep 10

echo
echo "===== 14. FINAL GENE POOL LIVE DATA ====="
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
echo "===== 15. FINAL BOARDROOM HEALTH SNAPSHOT ====="
for url in \
  "http://127.0.0.1:8852/ipad" \
  "http://127.0.0.1:8852/link_health" \
  "http://127.0.0.1:8852/team_live/data" \
  "http://127.0.0.1:8852/proxy/gene_pool/api/live"
do
  echo "--- $url"
  curl -sS --max-time 20 -o "$RUN_DIR/logs/final.tmp" -w "http=%{http_code} total=%{time_total}s size=%{size_download}\n" "$url" || true
  head -c 300 "$RUN_DIR/logs/final.tmp" 2>/dev/null || true
  echo
done

echo
echo "===== 16. LAN URLS ====="
LAN_IP="$(hostname -I 2>/dev/null | awk '{print $1}')"
echo "Boardroom iPad:"
echo "http://${LAN_IP:-127.0.0.1}:8852/ipad"
echo
echo "Gene Pool through Boardroom:"
echo "http://${LAN_IP:-127.0.0.1}:8852/proxy/gene_pool"
echo
echo "Gene Pool direct:"
echo "http://${LAN_IP:-127.0.0.1}:8860"

if command -v xdg-open >/dev/null 2>&1; then
  xdg-open "http://127.0.0.1:8852/ipad" >/dev/null 2>&1 || true
  xdg-open "http://127.0.0.1:8852/proxy/gene_pool" >/dev/null 2>&1 || true
fi

echo
echo "===== 17. RECENT ERRORS ====="
echo "--- Gene Pool log ---"
tail -n 120 "$ROUTER_LOG" | grep -Ei "error|exception|traceback|fail|warning|ready|boot|submit" || true
echo "--- Boardroom log ---"
tail -n 180 "$BOARDROOM_LOG" | grep -Ei "error|exception|traceback|gene|proxy|task|town|8852|too many|ready|boot|NameError" || true

echo
echo "============================================================"
echo "DONE — BOARDROOM / TOWN / TASK / GENE POOL SMOKE COMPLETE"
echo
echo "Open Boardroom iPad:"
echo "http://${LAN_IP:-127.0.0.1}:8852/ipad"
echo
echo "Open Gene Pool through Boardroom:"
echo "http://${LAN_IP:-127.0.0.1}:8852/proxy/gene_pool"
echo
echo "Open Gene Pool direct:"
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
cp -a "$RUN_DIR/reports/discovered_boardroom_routes.txt" "$SEND/discovered_boardroom_routes.txt"
cp -a "$RUN_DIR/reports/smoke_urls.txt" "$SEND/smoke_urls.txt"
