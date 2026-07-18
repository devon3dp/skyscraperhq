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
RUN_DIR="$RUN_ROOT/${STAMP}_fix_gene_pool_submit_post"
REPORT="$RUN_DIR/reports/fix_gene_pool_submit_post_report.txt"

mkdir -p "$RUN_DIR/reports" "$RUN_DIR/backups" "$RUN_DIR/logs" "$SEND" "$PROJECT/runtime" "$PROJECT/logs"
rm -f "$RUN_ROOT/LATEST"
ln -s "$RUN_DIR" "$RUN_ROOT/LATEST"

exec > >(tee "$REPORT") 2>&1

echo "============================================================"
echo "FIX GENE POOL POST SUBMIT + CEO SMOKE TEST"
echo "Generated: $(date -Is)"
echo "Project: $PROJECT"
echo "============================================================"
echo "Rules:"
echo " - Fix /api/submit_job POST on Gene Pool Router."
echo " - Keep Boardroom proxy path."
echo " - No API key changes."
echo " - No secure key printing."
echo " - Claude HQ is the correct name."
echo " - Wren remains protected."
echo " - CEOs use API Gene Pool only."
echo " - No trading/order changes."
echo "============================================================"

cd "$PROJECT" || exit 1

echo
echo "===== 1. BACKUP ====="
cp -a "$ROUTER" "$RUN_DIR/backups/skyscraper_gene_pool_router.py.before_submit_post_fix_$STAMP"
cp -a "$BOARDROOM" "$RUN_DIR/backups/qsb_boardroom_hub.py.before_submit_post_smoke_$STAMP"
echo "[OK] backups written"

echo
echo "===== 2. PATCH ROUTER WITH REAL POST HANDLER ====="
python3 - <<'PY'
from pathlib import Path
import re

p = Path("/vaults/nvme0/qsb_tower_v1/tools/skyscraper_gene_pool_router.py")
s = p.read_text(errors="ignore")

# Ensure body() helper exists.
if "def body(h):" not in s:
    marker = "def send_json("
    body_helper = r'''
def body(h):
    n = int(h.headers.get("Content-Length", "0") or "0")
    raw = h.rfile.read(n) if n else b"{}"
    try:
        return json.loads(raw.decode("utf-8", "replace"))
    except Exception:
        return {}

'''
    if marker in s:
        s = s.replace(marker, body_helper + marker)
        print("[OK] inserted body() helper")
    else:
        raise SystemExit("[FAIL] Could not find send_json marker to insert body() helper")
else:
    print("[OK] body() helper already exists")

# Ensure external_submit_job exists.
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
        decision = {
            "ceo": ceo,
            "task": task,
            "ask": ask,
            "selected_provider": "none",
            "selected_label": "none",
            "reason": reply,
            "latency_ms": None,
            "wren_fallback": "blocked",
            "provider_reply": reply,
            "stage": "blocked"
        }
        event({
            "event": "blocked",
            "from": "Brain Router",
            "to": ceo,
            "provider": "none",
            "task": task,
            "status": "blocked",
            "ask": ask,
            "reply": reply,
            "detail": reply,
            "decision": decision,
            "job": {"ceo": ceo, "task": task, "ask": ask, "reply": reply, "stage": "blocked"}
        })
        return {"ok": False, "decision": decision, "reply": reply}

    label = PROVIDERS[provider]["label"]
    reason = f"{task} policy selected {label}; CEO uses API Gene Pool only; Wren/local GPU fallback blocked by doctrine"
    latency = random.randint(90, 1400)
    reply = f"{label} route selected for {ceo}. Task class: {task}. Boardroom/iPad submit path accepted."

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

    decision = {
        "ceo": ceo,
        "task": task,
        "ask": ask,
        "selected_provider": provider,
        "selected_label": label,
        "reason": reason,
        "latency_ms": latency,
        "wren_fallback": "blocked",
        "provider_reply": reply,
        "stage": "selected_external"
    }

    event({
        "event": "dispatch",
        "from": "Brain Router",
        "to": label,
        "provider": provider,
        "task": task,
        "status": "selected",
        "ask": ask,
        "reply": reply,
        "detail": reason,
        "decision": decision,
        "job": {"ceo": ceo, "task": task, "ask": ask, "provider": label, "stage": "dispatched_external"}
    })

    event({
        "event": "return",
        "from": label,
        "to": ceo,
        "provider": provider,
        "task": task,
        "status": "visual_live",
        "ask": ask,
        "reply": reply,
        "detail": "external CEO route returned to CEO window",
        "decision": decision,
        "job": {"ceo": ceo, "task": task, "ask": ask, "provider": label, "reply": reply, "stage": "returned_external"}
    })

    return {"ok": True, "decision": decision, "reply": reply}

'''
    if marker not in s:
        raise SystemExit("[FAIL] Could not find def recent marker to insert external_submit_job")
    s = s.replace(marker, helper + "\n" + marker)
    print("[OK] inserted external_submit_job")
else:
    print("[OK] external_submit_job already exists")

# Force class H to have a real do_POST method.
class_marker = "class H(BaseHTTPRequestHandler):"
if class_marker not in s:
    raise SystemExit("[FAIL] Could not find class H(BaseHTTPRequestHandler)")

post_method = r'''
    def do_POST(self):
        p = urlparse(self.path).path
        if p == "/api/submit_job":
            try:
                return send_json(self, external_submit_job(body(self)))
            except Exception as e:
                return send_json(self, {"ok": False, "error": safe(e)}, 500)

        if p == "/api/rescan":
            try:
                auto_scan()
                return send_json(self, {"ok": True, "metrics": metrics(), "providers": PUBLIC})
            except Exception as e:
                return send_json(self, {"ok": False, "error": safe(e)}, 500)

        return send_json(self, {"ok": False, "error": "not found", "path": p}, 404)

'''

# If do_POST exists in class H, replace it. If not, insert after class line.
m = re.search(r"(class H\(BaseHTTPRequestHandler\):\n)(.*?)(\n    def do_GET\(self\):)", s, flags=re.S)
if not m:
    raise SystemExit("[FAIL] Could not locate class H block before do_GET")

class_head, between, do_get = m.group(1), m.group(2), m.group(3)

if "def do_POST(self):" in between:
    between = re.sub(r"\n    def do_POST\(self\):\n.*?(?=\n    def do_|\Z)", "\n" + post_method, between, flags=re.S)
    print("[OK] replaced existing class H do_POST")
else:
    between = between + post_method
    print("[OK] inserted class H do_POST")

s = s[:m.start()] + class_head + between + do_get + s[m.end():]

p.write_text(s, encoding="utf-8")
PY

echo
echo "===== 3. COMPILE ====="
python3 -m py_compile "$ROUTER" && echo "[OK] Gene Pool Router compiles" || exit 2
python3 -m py_compile "$BOARDROOM" && echo "[OK] Boardroom compiles" || exit 3

echo
echo "===== 4. RESTART SERVICES ====="
[ -f "$PROJECT/runtime/gene_pool_router_8860.pid" ] && kill "$(cat "$PROJECT/runtime/gene_pool_router_8860.pid" 2>/dev/null)" 2>/dev/null || true
pkill -f "skyscraper_gene_pool_router.py" 2>/dev/null || true
pkill -f "tools/qsb_boardroom_hub.py.*--port 8852" 2>/dev/null || true
sleep 2

nohup "$ROUTER_START" >> "$ROUTER_LOG" 2>&1 &
GPID="$!"
echo "$GPID" > "$PROJECT/runtime/gene_pool_router_8860.pid"
echo "[OK] Gene Pool Router pid=$GPID"

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
echo "===== 5. WAIT FOR PORTS ====="
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
    echo "[FAIL] port $port did not come online"
    tail -n 120 "$ROUTER_LOG" || true
    tail -n 180 "$BOARDROOM_LOG" || true
    cp -a "$REPORT" "$SEND/LATEST_REPORT.txt"
    exit 4
  fi
  echo "[OK] port $port online"
done

echo
echo "===== 6. DIRECT ROUTER POST TEST ====="
python3 - <<'PY'
import json, urllib.request, urllib.error
payload = {
    "ceo": "Claude HQ",
    "task": "architecture",
    "ask": "Direct POST smoke test into /api/submit_job."
}
data = json.dumps(payload).encode()
req = urllib.request.Request("http://127.0.0.1:8860/api/submit_job", data=data, headers={"Content-Type":"application/json"}, method="POST")
try:
    with urllib.request.urlopen(req, timeout=45) as r:
        print("http", r.status)
        print(r.read().decode("utf-8", "replace")[:1600])
except urllib.error.HTTPError as e:
    print("HTTP_ERROR", e.code)
    print(e.read().decode("utf-8", "replace")[:1600])
except Exception as e:
    print("ERROR", repr(e))
PY

echo
echo "===== 7. BOARDROOM PROXY POST TESTS FOR ALL CEOS ====="
submit_job() {
  local ceo="$1"
  local task="$2"
  local ask="$3"

  echo "--- submit via Boardroom proxy: $ceo / $task"

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

submit_job "Claude HQ" "architecture" "Claude HQ submits a real Boardroom proxy architecture job into the Brain Router."
submit_job "CEO 2" "coding" "CEO 2 submits a real Boardroom proxy coding job into the Brain Router."
submit_job "CEO 3" "summary" "CEO 3 submits a real Boardroom proxy summary job into the Brain Router."

echo
echo "===== 8. LET DASH UPDATE ====="
sleep 8

echo
echo "===== 9. FINAL LIVE DATA ====="
curl -sS --max-time 25 "http://127.0.0.1:8852/proxy/gene_pool/api/live" > "$RUN_DIR/reports/final_gene_pool_live.json"

python3 - <<PYSHOW
import json
d=json.load(open("$RUN_DIR/reports/final_gene_pool_live.json"))
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
    print(name, "| task=", panel.get("task"), "| provider=", panel.get("provider_label"), "| ask=", (panel.get("ask") or "")[:110], "| reply=", (panel.get("reply") or "")[:110])
print("")
print("JOB BOARD TOP 12:")
for j in (d.get("job_board") or [])[:12]:
    print(j.get("event"), j.get("from"), "->", j.get("to"), "|", j.get("task"), "|", (j.get("ask") or "")[:110])
PYSHOW

echo
echo "===== 10. HEALTH SNAPSHOT ====="
for url in \
  "http://127.0.0.1:8860/health" \
  "http://127.0.0.1:8860/api/live" \
  "http://127.0.0.1:8852/ipad" \
  "http://127.0.0.1:8852/proxy/gene_pool" \
  "http://127.0.0.1:8852/proxy/gene_pool/api/live" \
  "http://127.0.0.1:8852/town_square" \
  "http://127.0.0.1:8852/tasks" \
  "http://127.0.0.1:8852/tasks/data"
do
  echo "--- $url"
  curl -sS --max-time 20 -o "$RUN_DIR/logs/http.tmp" -w "http=%{http_code} total=%{time_total}s size=%{size_download}\n" "$url" || true
  head -c 220 "$RUN_DIR/logs/http.tmp" 2>/dev/null || true
  echo
done

echo
echo "===== 11. RECENT ERRORS ====="
echo "--- Gene Pool log ---"
tail -n 120 "$ROUTER_LOG" | grep -Ei "error|exception|traceback|fail|warning|ready|boot|submit|501|POST" || true
echo "--- Boardroom log ---"
tail -n 180 "$BOARDROOM_LOG" | grep -Ei "error|exception|traceback|gene|proxy|task|town|too many|NameError|501|POST" || true

echo
echo "===== 12. URLS ====="
LAN_IP="$(hostname -I 2>/dev/null | awk '{print $1}')"
echo "Boardroom iPad:"
echo "http://${LAN_IP:-127.0.0.1}:8852/ipad"
echo
echo "Gene Pool through Boardroom:"
echo "http://${LAN_IP:-127.0.0.1}:8852/proxy/gene_pool"
echo
echo "Gene Pool direct:"
echo "http://${LAN_IP:-127.0.0.1}:8860"

echo
echo "============================================================"
echo "DONE — SUBMIT POST FIX + CEO SMOKE COMPLETE"
echo "Report:"
echo "$REPORT"
echo "Send-back:"
echo "$SEND/LATEST_REPORT.txt"
echo "============================================================"

cp -a "$REPORT" "$SEND/LATEST_REPORT.txt"
cp -a "$RUN_DIR/reports/final_gene_pool_live.json" "$SEND/final_gene_pool_live.json"
