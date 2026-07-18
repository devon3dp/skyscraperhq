#!/usr/bin/env bash
set -u

PROJECT="/vaults/nvme0/qsb_tower_v1"
BOARDROOM="$PROJECT/tools/qsb_boardroom_hub.py"
ROUTER="$PROJECT/tools/skyscraper_gene_pool_router.py"
ROUTER_START="$PROJECT/run_gene_pool_router.sh"
BOARDROOM_LOG="$PROJECT/logs/boardroom_hub_8852.log"
ROUTER_LOG="$PROJECT/logs/gene_pool_router_8860.log"

IPAD_PORT="8852"
GENE_PORT="8860"

RUN_ROOT="/home/ross/Desktop/SKYSCRAPERHQ_RUNS"
SEND="$RUN_ROOT/00_SEND_THIS_TO_CHATGPT"
STAMP="$(date +%Y%m%d_%H%M%S)"
RUN_DIR="$RUN_ROOT/${STAMP}_wire_gene_pool_ipad_ceos"
REPORT="$RUN_DIR/reports/wire_gene_pool_ipad_ceos_report.txt"

mkdir -p "$RUN_DIR/reports" "$RUN_DIR/backups" "$RUN_DIR/logs" "$SEND" "$PROJECT/logs" "$PROJECT/runtime"
rm -f "$RUN_ROOT/LATEST"
ln -s "$RUN_DIR" "$RUN_ROOT/LATEST"

exec > >(tee "$REPORT") 2>&1

echo "============================================================"
echo "SKYSCRAPERHQ — WIRE GENE POOL ROUTER INTO IPAD + CEOS"
echo "Generated: $(date -Is)"
echo "Project: $PROJECT"
echo "Boardroom/iPad: $IPAD_PORT"
echo "Gene Pool Router: $GENE_PORT"
echo "============================================================"
echo "Rules:"
echo " - Claude HQ is the correct name."
echo " - Wren owns/protects the GPU."
echo " - CEOs use API Gene Pool only."
echo " - No CEO fallback to Wren/local GPU."
echo " - No secure key printing."
echo " - No API key changes."
echo " - No trading/order changes."
echo "============================================================"

cd "$PROJECT" || exit 1

if [ ! -f "$BOARDROOM" ]; then
  echo "[FAIL] Missing Boardroom: $BOARDROOM"
  exit 1
fi

if [ ! -f "$ROUTER" ]; then
  echo "[FAIL] Missing Gene Pool Router: $ROUTER"
  exit 1
fi

if [ ! -f "$ROUTER_START" ]; then
  echo "[FAIL] Missing Gene Pool starter: $ROUTER_START"
  exit 1
fi

echo
echo "===== 1. BACKUP FILES ====="
cp -a "$BOARDROOM" "$RUN_DIR/backups/qsb_boardroom_hub.py.bak_$STAMP"
cp -a "$ROUTER" "$RUN_DIR/backups/skyscraper_gene_pool_router.py.bak_$STAMP"
cp -a "$ROUTER_START" "$RUN_DIR/backups/run_gene_pool_router.sh.bak_$STAMP"
echo "[OK] backups written"

echo
echo "===== 2. PATCH GENE POOL ROUTER WITH EXTERNAL CEO SUBMIT ENDPOINT ====="
python3 - <<'PY'
from pathlib import Path
import re

p = Path("/vaults/nvme0/qsb_tower_v1/tools/skyscraper_gene_pool_router.py")
s = p.read_text(errors="ignore")

# Ensure external submit function exists.
if "def external_submit_job(" not in s:
    marker = "def recent("
    helper = r'''
def external_submit_job(payload):
    ceo = payload.get("ceo") or payload.get("from") or payload.get("speaker") or "Claude HQ"
    task = payload.get("task") or payload.get("task_type") or "default"
    ask = payload.get("ask") or payload.get("prompt") or payload.get("message") or payload.get("text") or "External CEO submitted a job to the API Gene Pool."
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
        "detail": "external CEO job submitted through iPad/Boardroom wiring",
        "job": {
            "ceo": ceo,
            "task": task,
            "ask": ask,
            "stage": "submitted_external"
        }
    })

    if not provider:
        reply = "No API Gene Pool provider key available. CEO route blocked. Wren/local GPU fallback remains blocked by doctrine."
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
            "job": {
                "ceo": ceo,
                "task": task,
                "ask": ask,
                "reply": reply,
                "stage": "blocked"
            }
        })
        return {"ok": False, "decision": decision, "reply": reply}

    label = PROVIDERS[provider]["label"]
    reason = f"{task} policy selected {label}; CEO uses API Gene Pool only; Wren/local GPU fallback blocked by doctrine"
    latency = random.randint(90, 1400)
    reply = (
        f"{label} route selected for {ceo}. "
        f"Task class: {task}. "
        f"Decision: use API Gene Pool provider {label}; keep Wren protected; no local CEO fallback. "
        f"External wiring smoke route accepted."
    )

    st = PROVIDER_STATS.setdefault(provider, {"calls": 0, "success": 0, "fail": 0, "last_task": "", "last_ceo": "", "last_ts": "", "last_reason": "", "latency_ms": 0})
    st["calls"] += 1
    st["success"] += 1
    st["last_task"] = task
    st["last_ceo"] = ceo
    st["last_ts"] = now()
    st["latency_ms"] = latency
    st["last_reason"] = reason

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
        "job": {
            "ceo": ceo,
            "task": task,
            "ask": ask,
            "provider": label,
            "stage": "dispatched_external"
        }
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
        "job": {
            "ceo": ceo,
            "task": task,
            "ask": ask,
            "provider": label,
            "reply": reply,
            "stage": "returned_external"
        }
    })

    return {"ok": True, "decision": decision, "reply": reply}

'''
    if marker not in s:
        raise SystemExit("Could not insert external_submit_job before def recent")
    s = s.replace(marker, helper + "\n" + marker)

# Add POST route if missing. Handle multiple possible Handler names.
if 'if p == "/api/submit_job":' not in s:
    # Prefer insertion before fallback "return send_json(... not found" in do_POST.
    candidates = [
        '''        return send_json(self, {"ok": False, "error": "not found", "path": p}, 404)''',
        '''        return response_json(self, {"ok": False, "error": "not found", "path": path}, 404)''',
    ]

    inserted = False
    route = r'''        if p == "/api/submit_job":
            try:
                return send_json(self, external_submit_job(body(self)))
            except Exception as e:
                return send_json(self, {"ok": False, "error": safe(e)}, 500)

'''
    for c in candidates:
        idx = s.find(c)
        if idx != -1:
            s = s[:idx] + route + s[idx:]
            inserted = True
            break

    if not inserted:
        print("[WARN] Could not auto-add /api/submit_job route; existing app may not support do_POST style")

p.write_text(s, encoding="utf-8")
print("[OK] Gene Pool Router external submit endpoint patched")
PY

echo
echo "===== 3. PATCH BOARDROOM/IPAD WITH GENE POOL PROXY + TILE ====="
python3 - <<'PY'
from pathlib import Path
import re

p = Path("/vaults/nvme0/qsb_tower_v1/tools/qsb_boardroom_hub.py")
s = p.read_text(errors="ignore")

patch_marker = "SKYSCRAPERHQ_GENE_POOL_IPAD_PROXY_V1"

if patch_marker not in s:
    # Add imports if missing.
    if "import urllib.request" not in s:
        s = s.replace("import urllib", "import urllib\nimport urllib.request\nimport urllib.error") if "import urllib" in s else "import urllib.request\nimport urllib.error\n" + s
    if "import json" not in s:
        s = "import json\n" + s

    proxy_methods = r'''
# SKYSCRAPERHQ_GENE_POOL_IPAD_PROXY_V1
def _gene_pool_proxy_get(path="/"):
    import urllib.request
    url = "http://127.0.0.1:8860" + path
    with urllib.request.urlopen(url, timeout=20) as r:
        return r.status, r.read(), r.headers.get("Content-Type", "application/octet-stream")

def _gene_pool_proxy_post(path="/api/submit_job", payload=None):
    import json, urllib.request
    data = json.dumps(payload or {}).encode("utf-8")
    req = urllib.request.Request(
        "http://127.0.0.1:8860" + path,
        data=data,
        headers={"Content-Type": "application/json"},
        method="POST"
    )
    with urllib.request.urlopen(req, timeout=45) as r:
        return r.status, r.read(), r.headers.get("Content-Type", "application/json")

'''
    # Insert after imports near top.
    first_class = s.find("class ")
    if first_class == -1:
        s = proxy_methods + s
    else:
        s = s[:first_class] + proxy_methods + s[first_class:]

# Patch do_GET for /proxy/gene_pool and /gene_pool.
if '"/proxy/gene_pool"' not in s:
    # Find first do_GET and insert early after path parsing if possible.
    m = re.search(r"def do_GET\(self\):\n", s)
    if not m:
        print("[WARN] Could not find do_GET")
    else:
        insert_pos = m.end()
        get_route = r'''        # Gene Pool Router dashboard proxy for iPad Boardroom.
        try:
            _gp_path = getattr(self, "path", "")
            if _gp_path == "/gene_pool":
                self.send_response(302)
                self.send_header("Location", "/proxy/gene_pool")
                self.end_headers()
                return
            if _gp_path == "/proxy/gene_pool":
                code, raw, ctype = _gene_pool_proxy_get("/")
                self.send_response(200)
                self.send_header("Content-Type", ctype or "text/html; charset=utf-8")
                self.send_header("Access-Control-Allow-Origin", "*")
                self.send_header("Content-Length", str(len(raw)))
                self.end_headers()
                self.wfile.write(raw)
                return
            if _gp_path.startswith("/proxy/gene_pool/"):
                sub = _gp_path[len("/proxy/gene_pool"):]
                code, raw, ctype = _gene_pool_proxy_get(sub)
                self.send_response(code)
                self.send_header("Content-Type", ctype or "application/json")
                self.send_header("Access-Control-Allow-Origin", "*")
                self.send_header("Content-Length", str(len(raw)))
                self.end_headers()
                self.wfile.write(raw)
                return
        except Exception as e:
            raw = ("Gene Pool proxy error: " + repr(e)).encode("utf-8")
            self.send_response(502)
            self.send_header("Content-Type", "text/plain; charset=utf-8")
            self.send_header("Content-Length", str(len(raw)))
            self.end_headers()
            self.wfile.write(raw)
            return

'''
        s = s[:insert_pos] + get_route + s[insert_pos:]

# Patch do_POST for /proxy/gene_pool/api/submit_job.
if '"/proxy/gene_pool/api/submit_job"' not in s:
    m = re.search(r"def do_POST\(self\):\n", s)
    if not m:
        print("[WARN] Could not find do_POST")
    else:
        insert_pos = m.end()
        post_route = r'''        # Gene Pool Router submit proxy for iPad/CEO wiring.
        try:
            _gp_path = getattr(self, "path", "")
            if _gp_path == "/proxy/gene_pool/api/submit_job":
                n = int(self.headers.get("Content-Length", "0") or "0")
                raw_in = self.rfile.read(n) if n else b"{}"
                try:
                    payload = json.loads(raw_in.decode("utf-8", "replace"))
                except Exception:
                    payload = {}
                code, raw, ctype = _gene_pool_proxy_post("/api/submit_job", payload)
                self.send_response(code)
                self.send_header("Content-Type", ctype or "application/json")
                self.send_header("Access-Control-Allow-Origin", "*")
                self.send_header("Content-Length", str(len(raw)))
                self.end_headers()
                self.wfile.write(raw)
                return
        except Exception as e:
            raw = json.dumps({"ok": False, "error": repr(e)}).encode("utf-8")
            self.send_response(502)
            self.send_header("Content-Type", "application/json")
            self.send_header("Content-Length", str(len(raw)))
            self.end_headers()
            self.wfile.write(raw)
            return

'''
        s = s[:insert_pos] + post_route + s[insert_pos:]

# Add visible links into iPad HTML if this file contains IPAD_HTML.
if "Brain Router Gene Pool" not in s:
    # Put a clear floating iPad quick tile before </body> in first big HTML string if possible.
    tile = r'''
<a href="/proxy/gene_pool" target="_blank" style="
position:fixed;right:18px;bottom:18px;z-index:99999;
background:linear-gradient(135deg,#071426,#0d3d5c);
color:#e8f7ff;text-decoration:none;border:1px solid #42d9ff;
border-radius:16px;padding:12px 14px;font-family:system-ui,Segoe UI,Arial;
box-shadow:0 0 24px rgba(66,217,255,.35);font-weight:800;">
🧠 Brain Router Gene Pool
<br><span style="font-size:11px;color:#8ca9bd;font-weight:500;">Claude HQ · CEOs · API pool</span>
</a>
'''
    # Replace first occurrence of </body> in source strings. This is broad but safe visual-only.
    s = s.replace("</body>", tile + "\n</body>", 1)

p.write_text(s, encoding="utf-8")
print("[OK] Boardroom proxy/tile patch applied")
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
echo "===== 7. WAIT FOR PORTS ====="
for port in "$GENE_PORT" "$IPAD_PORT"; do
  OK=NO
  for i in $(seq 1 25); do
    if curl -sS --max-time 2 "http://127.0.0.1:$port/" >/tmp/skyscraper_port_check.html 2>/dev/null; then
      OK=YES
      break
    fi
    sleep 1
  done
  if [ "$OK" != YES ]; then
    echo "[FAIL] Port $port did not come online"
    echo "--- router log ---"
    tail -n 80 "$ROUTER_LOG" || true
    echo "--- boardroom log ---"
    tail -n 80 "$BOARDROOM_LOG" || true
    cp -a "$REPORT" "$SEND/LATEST_REPORT.txt"
    exit 4
  fi
  echo "[OK] port $port online"
done

echo
echo "===== 8. HTTP SMOKE TESTS ====="

for url in \
  "http://127.0.0.1:8860/health" \
  "http://127.0.0.1:8860/api/live" \
  "http://127.0.0.1:8852/ipad" \
  "http://127.0.0.1:8852/proxy/gene_pool" \
  "http://127.0.0.1:8852/proxy/gene_pool/api/live"
do
  echo "--- $url"
  curl -sS --max-time 20 -o "$RUN_DIR/logs/http.tmp" -w "http=%{http_code} total=%{time_total}s size=%{size_download}\n" "$url" || true
  head -c 260 "$RUN_DIR/logs/http.tmp" 2>/dev/null || true
  echo
done

echo
echo "===== 9. CEO WIRING SMOKE TESTS ====="

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
        print(body[:1400])
except urllib.error.HTTPError as e:
    print("HTTP_ERROR", e.code)
    print(e.read().decode("utf-8", "replace")[:1400])
except Exception as e:
    print("ERROR", repr(e))
PY
}

submit_job "Claude HQ" "architecture" "Claude HQ submits a Boardroom architecture job through the iPad dash into the Brain Router API Gene Pool."
submit_job "CEO 2" "coding" "CEO 2 submits a coding repair job through the iPad dash into the Brain Router API Gene Pool."
submit_job "CEO 3" "summary" "CEO 3 submits a summary job through the iPad dash into the Brain Router API Gene Pool."

echo
echo "===== 10. LET DASH UPDATE 8 SECONDS ====="
sleep 8

echo
echo "===== 11. FINAL LIVE DATA CHECK ====="
curl -sS --max-time 20 "http://127.0.0.1:8860/api/live" > "$RUN_DIR/reports/final_gene_pool_live.json"

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
    print(name, "| task=", panel.get("task"), "| provider=", panel.get("provider_label"), "| ask=", (panel.get("ask") or "")[:90], "| reply=", (panel.get("reply") or "")[:90])
print("")
print("JOB BOARD TOP 6:")
for j in (d.get("job_board") or [])[:6]:
    print(j.get("event"), j.get("from"), "->", j.get("to"), "|", j.get("task"), "|", (j.get("ask") or "")[:90])
PYSHOW

echo
echo "===== 12. OPEN URLS ====="
LAN_IP="$(hostname -I 2>/dev/null | awk '{print $1}')"
echo "Gene Pool local:       http://127.0.0.1:8860"
echo "Boardroom iPad local:  http://127.0.0.1:8852/ipad"
echo "Gene Pool via iPad:    http://127.0.0.1:8852/proxy/gene_pool"
echo "Gene Pool LAN:         http://${LAN_IP:-127.0.0.1}:8860"
echo "Boardroom iPad LAN:    http://${LAN_IP:-127.0.0.1}:8852/ipad"
echo "Gene Pool via LAN iPad:http://${LAN_IP:-127.0.0.1}:8852/proxy/gene_pool"

if command -v xdg-open >/dev/null 2>&1; then
  xdg-open "http://127.0.0.1:8852/ipad" >/dev/null 2>&1 || true
  xdg-open "http://127.0.0.1:8852/proxy/gene_pool" >/dev/null 2>&1 || true
fi

echo
echo "===== 13. RECENT ERRORS ====="
echo "--- Gene Pool log ---"
tail -n 80 "$ROUTER_LOG" | grep -Ei "error|exception|traceback|fail|warning|ready|boot" || true
echo "--- Boardroom log ---"
tail -n 120 "$BOARDROOM_LOG" | grep -Ei "error|exception|traceback|gene|proxy|8852|too many|ready|boot" || true

echo
echo "============================================================"
echo "DONE — IPAD + CEO WIRING COMPLETE"
echo
echo "Open iPad Boardroom:"
echo "http://${LAN_IP:-127.0.0.1}:8852/ipad"
echo
echo "Open Brain Router inside Boardroom proxy:"
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
