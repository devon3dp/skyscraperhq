#!/usr/bin/env bash
set -u

ROOT="/vaults/nvme0/qsb_tower_v1"
STAMP="$(date +%Y%m%d_%H%M%S)"
REPORT="/home/ross/Desktop/qsb_control_reconnect_phase1_$STAMP.txt"
HQ_DASH="$ROOT/tools/qsb_hq_claude_dash_8850.py"

exec > >(tee "$REPORT") 2>&1

PASS=0
WARN=0
FAIL=0

ok(){ echo "[PASS] $*"; PASS=$((PASS+1)); }
warn(){ echo "[WARN] $*"; WARN=$((WARN+1)); }
bad(){ echo "[FAIL] $*"; FAIL=$((FAIL+1)); }
sec(){ echo; echo "============================================================"; echo "$*"; echo "============================================================"; }

http_test(){
  local name="$1"
  local url="$2"
  local required="${3:-warn}"
  local max="${4:-8}"
  local tmp
  tmp="$(mktemp /tmp/qsb_link_XXXXXX)"

  local line
  line="$(curl -L -sS --max-time "$max" -o "$tmp" -w "http=%{http_code} total=%{time_total}s size=%{size_download}" "$url" 2>&1)"
  local code
  code="$(echo "$line" | sed -n 's/.*http=\([0-9][0-9][0-9]\).*/\1/p' | tail -1)"
  [ -z "$code" ] && code="000"

  if [ "$code" = "200" ] || [ "$code" = "204" ] || [ "$code" = "301" ] || [ "$code" = "302" ]; then
    ok "$name -> $line -> $url"
    head -c 160 "$tmp" 2>/dev/null | tr '\n' ' '
    echo
  else
    if [ "$required" = "fail" ]; then
      bad "$name -> $line -> $url"
    else
      warn "$name -> $line -> $url"
    fi
  fi

  rm -f "$tmp"
}

port_test(){
  local port="$1"
  local name="$2"
  local required="${3:-warn}"
  if ss -ltnp 2>/dev/null | grep -q ":$port\b"; then
    ok "$name listening on $port"
    ss -ltnp 2>/dev/null | grep ":$port\b" | head -2
  else
    if [ "$required" = "fail" ]; then
      bad "$name not listening on $port"
    else
      warn "$name not listening on $port"
    fi
  fi
}

sec "QSB CONTROL RECONNECT PHASE 1"
echo "Generated: $(date -Is)"
echo "Root: $ROOT"
echo "Report: $REPORT"
echo
echo "Goal:"
echo " - reconnect iPad control dashboard to HQ, Wren, Task Council, Team Live, chats, counters, and visual dashboards"
echo " - identify every dead link honestly"
echo " - do not press dangerous controls"
echo " - do not enable live trading"

cd "$ROOT" || exit 1
mkdir -p logs tools

sec "1. PRE-FLIGHT CURRENT SYSTEM STATE"

[ -d "$ROOT" ] && ok "QSB root exists" || bad "QSB root missing"
[ -f tools/qsb_boardroom_hub.py ] && ok "Boardroom hub exists" || bad "Boardroom hub missing"

echo
echo "Current Boardroom / iPad process:"
ps aux | grep -E "qsb_boardroom_hub.py --port 8852|tmux new-session -d -s br" | grep -v grep || true

echo
echo "Current listening ports:"
ss -ltnp | grep -E ':(8852|8851|8850|8765|9100|9110|11434|8795|8796|9000|9200|9201|9202)\b' || true

sec "2. START OR REPAIR CLAUDE HQ DASHBOARD 8850"

cat > "$HQ_DASH" <<'PY'
#!/usr/bin/env python3
from http.server import ThreadingHTTPServer, BaseHTTPRequestHandler
from urllib.parse import urlparse
import urllib.request
import json
import datetime

BOARDROOM = "http://127.0.0.1:8852"

def utc():
    return datetime.datetime.utcnow().replace(microsecond=0).isoformat() + "Z"

def fetch(path, timeout=2.5):
    try:
        with urllib.request.urlopen(BOARDROOM + path, timeout=timeout) as r:
            raw = r.read()
            text = raw.decode("utf-8", "replace")
            try:
                return {"ok": True, "json": json.loads(text), "bytes": len(raw)}
            except Exception:
                return {"ok": True, "text": text[:1000], "bytes": len(raw)}
    except Exception as e:
        return {"ok": False, "error": str(e)}

HTML = r"""<!doctype html>
<html>
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
<title>HQ-Claude Dashboard · 8850</title>
<style>
*{box-sizing:border-box}
body{margin:0;background:#08080e;color:#e8ecf3;font:14px/1.45 system-ui,-apple-system,Segoe UI,Roboto,sans-serif}
header{position:sticky;top:0;z-index:20;background:#0b0d12;border-bottom:1px solid #334155;padding:12px}
h1{margin:0;color:#eab308;font-size:20px}
.sub{color:#94a3b8;font-size:12px;margin:4px 0 10px}
.btn{display:inline-block;background:#1e293b;color:#eab308;border:1px solid #334155;border-radius:8px;padding:8px 10px;margin:3px;text-decoration:none;font-weight:800}
.grid{display:grid;grid-template-columns:repeat(auto-fit,minmax(310px,1fr));gap:12px;padding:12px}
.card{background:#111827;border:1px solid #1f2937;border-radius:12px;padding:12px;min-height:130px}
.card h2{margin:0 0 8px;color:#eab308;font-size:15px}
pre{white-space:pre-wrap;word-break:break-word;background:#05070a;border:1px solid #1f2937;border-radius:8px;padding:8px;max-height:250px;overflow:auto;font-size:11px}
.good{color:#22c55e}.bad{color:#ef4444}.warn{color:#f59e0b}
.chat{display:flex;gap:8px;padding:0 12px 12px}
input{flex:1;background:#0b1220;color:#e8ecf3;border:1px solid #334155;border-radius:8px;padding:12px}
button{background:#eab308;color:#000;border:none;border-radius:8px;padding:12px 18px;font-weight:900;cursor:pointer}
.pill{display:inline-block;border-radius:999px;padding:2px 8px;background:#1e293b;color:#94a3b8;font-size:11px}
</style>
</head>
<body>
<header>
<h1>🟨 HQ-Claude Dashboard · 8850 <span id="state" class="pill">starting</span></h1>
<div class="sub">Visible HQ control dashboard. Reads Boardroom 8852. Posts chat to Town Square. This is the missing Claude HQ dashboard link for the iPad.</div>
<a class="btn" href="http://127.0.0.1:8852/ipad">📱 iPad</a>
<a class="btn" href="http://127.0.0.1:8852/">🏛 Boardroom</a>
<a class="btn" href="http://127.0.0.1:8852/tasks">📋 Task Council</a>
<a class="btn" href="http://127.0.0.1:8852/team_live">🟨 Team Live</a>
<a class="btn" href="http://127.0.0.1:8852/town_square">🗣 Town</a>
<a class="btn" href="http://127.0.0.1:8852/brain/usage">🧠 Brain Usage</a>
<a class="btn" href="http://127.0.0.1:8851/">🟪 Wren</a>
</header>

<div class="grid">
  <div class="card"><h2>HQ Stats</h2><pre id="hq">loading</pre></div>
  <div class="card"><h2>Task Council</h2><pre id="tasks">loading</pre></div>
  <div class="card"><h2>Team Live</h2><pre id="team">loading</pre></div>
  <div class="card"><h2>Brain Usage</h2><pre id="brain">loading</pre></div>
  <div class="card"><h2>Link Health</h2><pre id="links">loading</pre></div>
  <div class="card"><h2>Town Square</h2><pre id="town">loading</pre></div>
</div>

<div class="chat">
<input id="msg" placeholder="message to Town Square as Ross from HQ dashboard">
<button onclick="send()">SEND</button>
</div>

<script>
function small(x){ return JSON.stringify(x,null,2).slice(0,2200); }
async function j(path){ const r=await fetch(path,{cache:'no-store'}); return await r.json(); }
async function tick(){
  try{
    const d=await j('/state.json');
    document.getElementById('state').textContent=d.ok?'LIVE':'DEGRADED';
    document.getElementById('state').className=d.ok?'good':'bad';
    document.getElementById('hq').textContent=small(d.hq);
    document.getElementById('tasks').textContent=small(d.tasks);
    document.getElementById('team').textContent=small(d.team);
    document.getElementById('brain').textContent=small(d.brain);
    document.getElementById('links').textContent=small(d.links);
    document.getElementById('town').textContent=small(d.town);
  }catch(e){
    document.getElementById('state').textContent='ERR';
    document.getElementById('state').className='bad';
  }
}
async function send(){
  const el=document.getElementById('msg');
  const text=el.value.trim();
  if(!text) return;
  el.value='';
  await fetch('/api/post',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({from:'ross',to:'council',text,src:'hq_dash_8850'})});
  setTimeout(tick,250);
}
tick();
setInterval(tick,1000);
</script>
</body>
</html>
"""

class H(BaseHTTPRequestHandler):
    def log_message(self, fmt, *args):
        return

    def send(self, code, body, ctype):
        if isinstance(body, str):
            body = body.encode("utf-8")
        self.send_response(code)
        self.send_header("Content-Type", ctype)
        self.send_header("Content-Length", str(len(body)))
        self.send_header("Cache-Control", "no-store")
        self.end_headers()
        self.wfile.write(body)

    def do_GET(self):
        path = urlparse(self.path).path
        if path in ("/", "/index.html"):
            return self.send(200, HTML, "text/html; charset=utf-8")
        if path in ("/health.json", "/state.json"):
            hq = fetch("/hq/stats", 2.5)
            tasks = fetch("/tasks/data", 2.5)
            team = fetch("/team_live/data", 4.5)
            brain = fetch("/brain/usage", 2.5)
            links = fetch("/link_health", 4)
            town = fetch("/town_square_feed", 3)
            out = {
                "ok": hq.get("ok") and tasks.get("ok"),
                "ts": utc(),
                "hq": hq,
                "tasks": tasks,
                "team": team,
                "brain": brain,
                "links": links,
                "town": town,
            }
            return self.send(200, json.dumps(out), "application/json")
        return self.send(404, "not found", "text/plain")

    def do_POST(self):
        path = urlparse(self.path).path
        n = int(self.headers.get("Content-Length", "0") or "0")
        raw = self.rfile.read(n)
        if path == "/api/post":
            try:
                data = json.loads(raw.decode("utf-8", "replace"))
            except Exception:
                data = {}
            payload = {
                "from": data.get("from", "ross"),
                "to": data.get("to", "council"),
                "text": data.get("text", ""),
                "src": data.get("src", "hq_dash_8850"),
            }
            req = urllib.request.Request(
                BOARDROOM + "/town/post",
                data=json.dumps(payload).encode(),
                headers={"Content-Type": "application/json"},
                method="POST",
            )
            try:
                with urllib.request.urlopen(req, timeout=4) as r:
                    body = r.read()
                return self.send(200, body, "application/json")
            except Exception as e:
                return self.send(502, json.dumps({"ok": False, "error": str(e)}), "application/json")
        return self.send(404, "not found", "text/plain")

if __name__ == "__main__":
    print("HQ-Claude dashboard on http://0.0.0.0:8850/")
    ThreadingHTTPServer(("0.0.0.0", 8850), H).serve_forever()
PY

chmod +x "$HQ_DASH"
python3 -m py_compile "$HQ_DASH" && ok "HQ dashboard script compiles" || bad "HQ dashboard script compile failed"

tmux kill-session -t hqdash 2>/dev/null || true
pkill -f "qsb_hq_claude_dash_8850.py" 2>/dev/null || true
sleep 1
tmux new-session -d -s hqdash "cd '$ROOT' && python3 -u tools/qsb_hq_claude_dash_8850.py >> logs/hq_claude_dash_8850.log 2>&1"
sleep 2

port_test 8850 "Claude HQ dashboard" fail
http_test "Claude HQ dashboard page" "http://127.0.0.1:8850/" fail 8
http_test "Claude HQ dashboard state" "http://127.0.0.1:8850/state.json" warn 8

sec "3. TRY TO START FULL ANIMATED SKYSCRAPER DASHBOARD 8765"

if [ -f src/dashboard/server.py ]; then
  ok "Found src/dashboard/server.py"

  python3 -m py_compile src/dashboard/server.py && ok "src/dashboard/server.py compiles" || warn "src/dashboard/server.py compile problem"

  if [ -f src/tower/database.py ]; then
    echo "Checking known floor workers-key bug before starting 8765..."
    if grep -q "f\['workers'\]" src/tower/database.py; then
      BK="src/tower/database.py.bak_before_workers_fix_$STAMP"
      cp -a src/tower/database.py "$BK"
      echo "[INFO] Backup made: $BK"
      python3 - <<'PY'
from pathlib import Path
p = Path("src/tower/database.py")
txt = p.read_text()
old = "conn.execute('INSERT OR IGNORE INTO floor_state VALUES (?,?,?,?,?)',(f['id'],f['status'],100,0 if f['vacant'] else len(f['workers']),now()))"
new = """workers = f.get('workers')
        if workers is None:
            workers = f.get('team_roster', [])
        if workers is None:
            workers = []
        floor_id = f.get('id') or f.get('floor_id') or f.get('name') or 'unknown_floor'
        floor_status = f.get('status') or f.get('execution_mode') or f.get('current_status') or 'unknown'
        vacant = bool(f.get('vacant', False))
        conn.execute('INSERT OR IGNORE INTO floor_state VALUES (?,?,?,?,?)',(floor_id,floor_status,100,0 if vacant else len(workers),now()))"""
if old in txt:
    txt = txt.replace(old, new)
    p.write_text(txt)
    print("[OK] patched exact known workers-key line")
else:
    print("[SKIP] exact old workers-key line not found")
PY
      python3 -m py_compile src/tower/database.py && ok "src/tower/database.py compiles" || warn "src/tower/database.py compile issue"
    else
      ok "Known workers-key pattern not present"
    fi
  fi

  tmux kill-session -t dash8765 2>/dev/null || true
  pkill -f "src/dashboard/server.py" 2>/dev/null || true
  sleep 1
  tmux new-session -d -s dash8765 "cd '$ROOT' && PYTHONPATH='$ROOT/src' python3 -u src/dashboard/server.py >> logs/dashboard_8765.log 2>&1"
  sleep 5

  port_test 8765 "Full animated Skyscraper dashboard" warn
  http_test "Full animated Skyscraper dashboard page" "http://127.0.0.1:8765/" warn 8
  http_test "Full animated Skyscraper dashboard unified API" "http://127.0.0.1:8765/api/unified" warn 8
else
  warn "src/dashboard/server.py missing"
fi

sec "4. REQUIRED PORT CHECKS AFTER STARTUP"

port_test 8852 "Boardroom / iPad cockpit" fail
port_test 8850 "Claude HQ dashboard" fail
port_test 8851 "Wren dashboard" fail
port_test 9100 "HQ node listener" fail
port_test 11434 "Ollama" fail
port_test 8765 "Full animated dashboard" warn
port_test 9110 "TP-Pip" warn
port_test 9000 "Acer-Cass" warn
port_test 8795 "Voice server" warn
port_test 8796 "Voice helper" warn

sec "5. CORE ROUTE TESTS"

http_test "Boardroom root" "http://127.0.0.1:8852/" fail 8
http_test "iPad cockpit" "http://127.0.0.1:8852/ipad" fail 8
http_test "Task Council page" "http://127.0.0.1:8852/tasks" fail 8
http_test "Task Council data" "http://127.0.0.1:8852/tasks/data" fail 8
http_test "Team Live page" "http://127.0.0.1:8852/team_live" fail 8
http_test "Team Live data" "http://127.0.0.1:8852/team_live/data" warn 12
http_test "Town Square page" "http://127.0.0.1:8852/town_square" warn 8
http_test "Town Square feed" "http://127.0.0.1:8852/town_square_feed" warn 8
http_test "Trading page" "http://127.0.0.1:8852/trading" warn 8
http_test "Trading data" "http://127.0.0.1:8852/trading/data" warn 8
http_test "Trader scoreboard / rev counter" "http://127.0.0.1:8852/trader_scoreboard" warn 8
http_test "Brain usage" "http://127.0.0.1:8852/brain/usage" warn 8
http_test "Brain page" "http://127.0.0.1:8852/brain" warn 8
http_test "Diagnostics" "http://127.0.0.1:8852/diagnostics" warn 12
http_test "Link health" "http://127.0.0.1:8852/link_health" warn 10
http_test "iPad button diagnostics tail" "http://127.0.0.1:8852/ipad_button_diag/tail" warn 8
http_test "Wren direct" "http://127.0.0.1:8851/" fail 8
http_test "Wren proxy" "http://127.0.0.1:8852/proxy/wren" fail 8
http_test "Claude HQ direct" "http://127.0.0.1:8850/" fail 8
http_test "TP direct LAN" "http://192.168.1.91:9110/" warn 6
http_test "TP proxy" "http://127.0.0.1:8852/proxy/tp" warn 8
http_test "HQ node" "http://127.0.0.1:9100/" fail 8
http_test "Ollama tags" "http://127.0.0.1:11434/api/tags" fail 8

sec "6. CHAT PATH TESTS"

echo "Testing Town Square post path..."
curl -sS --max-time 8 \
  -X POST "http://127.0.0.1:8852/town/post" \
  -H "Content-Type: application/json" \
  --data "{\"from\":\"ross\",\"to\":\"council\",\"text\":\"🧪 reconnect phase1 Town Square chat test $(date -Is)\",\"src\":\"phase1_town_chat_test\"}" \
  -w "\ntown_post http=%{http_code} total=%{time_total}s size=%{size_download}\n" || true

echo
echo "Testing Claude HQ dashboard chat relay..."
curl -sS --max-time 8 \
  -X POST "http://127.0.0.1:8850/api/post" \
  -H "Content-Type: application/json" \
  --data "{\"from\":\"ross\",\"to\":\"council\",\"text\":\"🧪 reconnect phase1 Claude HQ chat relay test $(date -Is)\",\"src\":\"phase1_hq_chat_test\"}" \
  -w "\nhq_chat http=%{http_code} total=%{time_total}s size=%{size_download}\n" || true

http_test "Town Square feed after chat tests" "http://127.0.0.1:8852/town_square_feed" warn 8

sec "7. iPAD HTML LINK MAP"

HTML="/tmp/qsb_ipad_phase1_$STAMP.html"
LINKS="/tmp/qsb_ipad_links_phase1_$STAMP.txt"

curl -sS --max-time 8 "http://127.0.0.1:8852/ipad" -o "$HTML" || true

python3 - "$HTML" "$LINKS" <<'PY'
import re, sys
html_path, out_path = sys.argv[1], sys.argv[2]
try:
    html = open(html_path, encoding="utf-8", errors="ignore").read()
except Exception as e:
    print("[FAIL] cannot read iPad HTML:", e)
    raise SystemExit(0)

patterns = [
    r"""href=['"]([^'"]+)['"]""",
    r"""src=['"]([^'"]+)['"]""",
    r"""fetch\(['"]([^'"]+)['"]""",
    r"""window\.open\(['"]([^'"]+)['"]""",
]
links = []
for pat in patterns:
    links.extend(re.findall(pat, html))

clean = []
for x in links:
    if not x or x.startswith("#") or x.startswith("javascript:") or x.startswith("mailto:"):
        continue
    if x not in clean:
        clean.append(x)

open(out_path, "w").write("\n".join(clean) + "\n")

print("Found links/actions:", len(clean))
for x in clean:
    print(" -", x)

print()
print("Static iPad feature checks:")
checks = {
    "live polling setInterval": "setInterval" in html,
    "speech synthesis": "speechSynthesis" in html,
    "speech recognition": ("SpeechRecognition" in html or "webkitSpeechRecognition" in html),
    "button diagnostics": "ipad_button_diag" in html,
    "task council": "/tasks" in html,
    "town square": "town_square" in html,
    "trading/rev counters": ("trader_scoreboard" in html or "trading/data" in html or "trading" in html),
    "Wren proxy": "/proxy/wren" in html,
    "TP proxy": "/proxy/tp" in html,
    "emergency controls present": ("emergencyPause" in html and ("kill-switch" in html or "killswitch" in html)),
}
for k, v in checks.items():
    print(("PASS" if v else "WARN"), "-", k)
PY

sec "8. TEST EVERY LOCAL/LAN LINK FROM iPAD HTML"

while IFS= read -r link; do
  [ -z "$link" ] && continue

  case "$link" in
    http://*|https://*)
      url="$link"
      ;;
    /*)
      url="http://127.0.0.1:8852$link"
      ;;
    *)
      continue
      ;;
  esac

  case "$url" in
    https://fonts.googleapis.com/*|https://x.com/*|https://skyscraperhq.com/*|https://trade.oanda.com/*|https://app.alpaca.markets/*)
      echo "[SKIP external/browser] $url"
      continue
      ;;
  esac

  line="$(curl -L -sS --max-time 5 -o /tmp/qsb_phase1_link_body -w "http=%{http_code} total=%{time_total}s size=%{size_download}" "$url" 2>&1)"
  code="$(echo "$line" | sed -n 's/.*http=\([0-9][0-9][0-9]\).*/\1/p' | tail -1)"
  [ -z "$code" ] && code="000"

  if [ "$code" = "200" ] || [ "$code" = "204" ] || [ "$code" = "301" ] || [ "$code" = "302" ]; then
    echo "[OK]   $url -> $line"
  else
    echo "[DEAD] $url -> $line"
  fi
done < "$LINKS"

sec "9. TASK / TEAM / LINK SUMMARY SNAPSHOTS"

echo "--- Task Council snapshot"
python3 - <<'PY'
import urllib.request, json
try:
    d=json.loads(urllib.request.urlopen("http://127.0.0.1:8852/tasks/data", timeout=8).read())
    print("total:", d.get("total"), "open:", d.get("open"), "in_progress:", d.get("in_progress"), "blocked:", d.get("blocked"), "done:", d.get("done"))
    for t in d.get("tasks", [])[:8]:
        print(" -", t.get("id"), "|", t.get("state"), "|", t.get("owner"), "|", (t.get("title") or t.get("description") or "")[:90])
except Exception as e:
    print("task snapshot error:", e)
PY

echo
echo "--- Team Live snapshot"
python3 - <<'PY'
import urllib.request, json
try:
    d=json.loads(urllib.request.urlopen("http://127.0.0.1:8852/team_live/data", timeout=12).read())
    q=d.get("quorum") or {}
    print("online_count:", q.get("online_count"), "quorum_met:", q.get("quorum_met"))
    for c in q.get("ceos", []):
        print(" -", c.get("ceo"), "online=", c.get("online"), "err=", (c.get("error") or "")[:100])
    print("town messages:", len(d.get("town_square", [])))
    print("cards:", list((d.get("cards") or {}).keys()))
except Exception as e:
    print("team snapshot error:", e)
PY

echo
echo "--- Link health snapshot"
python3 - <<'PY'
import urllib.request, json
try:
    d=json.loads(urllib.request.urlopen("http://127.0.0.1:8852/link_health", timeout=10).read())
    for item in d.get("links", []):
        print(" -", item.get("name"), "| ok=", item.get("ok"), "|", item.get("url"), "|", item.get("err","")[:100])
except Exception as e:
    print("link health error:", e)
PY

sec "10. LOG TAILS"

echo "--- HQ 8850 log"
tail -50 logs/hq_claude_dash_8850.log 2>/dev/null || true

echo
echo "--- Dashboard 8765 log"
tail -100 logs/dashboard_8765.log 2>/dev/null || true

echo
echo "--- Boardroom 8852 log"
tail -80 logs/boardroom_hub_8852.log 2>/dev/null || true

sec "11. FINAL VERDICT"

echo "PASS=$PASS"
echo "WARN=$WARN"
echo "FAIL=$FAIL"
echo
echo "Open on iPad/LAN:"
echo " - iPad cockpit:       http://192.168.1.71:8852/ipad"
echo " - Boardroom:          http://192.168.1.71:8852/"
echo " - Claude HQ dash:     http://192.168.1.71:8850/"
echo " - Wren dash:          http://192.168.1.71:8851/"
echo " - Full skyscraper:    http://192.168.1.71:8765/"
echo
echo "Golden-ticket status:"
if [ "$FAIL" -eq 0 ] && [ "$WARN" -eq 0 ]; then
  echo "YES: 100% connected."
elif [ "$FAIL" -eq 0 ]; then
  echo "NOT YET: core is alive, but warnings/dead links remain."
else
  echo "NO: hard failures remain."
fi
echo
echo "Report saved:"
echo "$REPORT"
