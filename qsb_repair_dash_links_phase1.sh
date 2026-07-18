#!/usr/bin/env bash
set -u

ROOT="/vaults/nvme0/qsb_tower_v1"
STAMP="$(date +%Y%m%d_%H%M%S)"
REPORT="/home/ross/Desktop/qsb_dash_links_phase1_$STAMP.txt"
HQ_DASH="$ROOT/tools/qsb_hq_claude_dash_8850.py"

exec > >(tee "$REPORT") 2>&1

echo "============================================================"
echo "QSB DASHBOARD / LINK REPAIR PHASE 1"
echo "Generated: $(date -Is)"
echo "Root: $ROOT"
echo "Report: $REPORT"
echo "============================================================"

cd "$ROOT" || exit 1
mkdir -p logs tools

echo
echo "===== 1. BUILD CLAUDE HQ DASHBOARD ON 8850 ====="

cat > "$HQ_DASH" <<'PY'
#!/usr/bin/env python3
from http.server import ThreadingHTTPServer, BaseHTTPRequestHandler
from urllib.parse import urlparse
import urllib.request, json, time, datetime

HQ = "http://127.0.0.1:8852"

def now():
    return datetime.datetime.utcnow().replace(microsecond=0).isoformat() + "Z"

def fetch(path, timeout=2.5):
    try:
        with urllib.request.urlopen(HQ + path, timeout=timeout) as r:
            raw = r.read()
            txt = raw.decode("utf-8", "replace")
            try:
                return {"ok": True, "json": json.loads(txt), "text": txt[:500], "bytes": len(raw)}
            except Exception:
                return {"ok": True, "json": None, "text": txt[:500], "bytes": len(raw)}
    except Exception as e:
        return {"ok": False, "error": str(e)}

def page():
    return """<!doctype html>
<html>
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
<title>HQ-Claude Dashboard · 8850</title>
<style>
body{margin:0;background:#08080e;color:#e8ecf3;font:14px system-ui,-apple-system,Segoe UI,Roboto,sans-serif}
header{position:sticky;top:0;background:#111827;border-bottom:1px solid #334155;padding:12px 14px;z-index:10}
h1{margin:0;color:#eab308;font-size:20px}
.sub{color:#94a3b8;font-size:12px;margin-top:3px}
.grid{display:grid;grid-template-columns:repeat(auto-fit,minmax(280px,1fr));gap:12px;padding:12px}
.card{background:#111827;border:1px solid #1f2937;border-radius:12px;padding:12px;min-height:110px}
.card h2{margin:0 0 8px;color:#eab308;font-size:15px}
pre{white-space:pre-wrap;word-break:break-word;background:#05070a;border:1px solid #1f2937;border-radius:8px;padding:8px;max-height:220px;overflow:auto;font-size:11px}
.good{color:#22c55e}.bad{color:#ef4444}.warn{color:#f59e0b}
.btn{display:inline-block;background:#1e293b;color:#eab308;border:1px solid #334155;border-radius:8px;padding:8px 10px;margin:3px;text-decoration:none;font-weight:700}
.chat{display:flex;gap:6px;padding:0 12px 12px}
input{flex:1;background:#0b1220;color:#e8ecf3;border:1px solid #334155;border-radius:8px;padding:12px}
button{background:#eab308;color:#000;border:none;border-radius:8px;padding:12px 16px;font-weight:900}
</style>
</head>
<body>
<header>
<h1>🟨 HQ-Claude Dashboard · Port 8850 <span id="state" class="warn">starting</span></h1>
<div class="sub">HQ visible dashboard for iPad links. Reads Boardroom 8852. Posts chat to Town Square as Ross/HQ-visible command surface.</div>
<div>
<a class=btn href="http://127.0.0.1:8852/ipad">📱 iPad</a>
<a class=btn href="http://127.0.0.1:8852/tasks">📋 Task Council</a>
<a class=btn href="http://127.0.0.1:8852/team_live">🟨 Team Live</a>
<a class=btn href="http://127.0.0.1:8852/town_square">🗣 Town</a>
<a class=btn href="http://127.0.0.1:8852/brain/usage">🧠 Brain Usage</a>
<a class=btn href="http://127.0.0.1:8851/">🟪 Wren</a>
</div>
</header>

<div class=grid>
  <div class=card><h2>HQ stats</h2><pre id=hq>loading…</pre></div>
  <div class=card><h2>Tasks</h2><pre id=tasks>loading…</pre></div>
  <div class=card><h2>Team Live</h2><pre id=team>loading…</pre></div>
  <div class=card><h2>Brain usage</h2><pre id=brain>loading…</pre></div>
  <div class=card><h2>Link health</h2><pre id=links>loading…</pre></div>
  <div class=card><h2>Latest Town Square</h2><pre id=town>loading…</pre></div>
</div>

<div class=chat>
<input id=msg placeholder="message to Town Square as Ross from HQ dashboard">
<button onclick="send()">SEND</button>
</div>

<script>
async function j(path){
  const r = await fetch(path,{cache:'no-store'});
  return await r.json();
}
function small(o){
  return JSON.stringify(o,null,2).slice(0,1800);
}
async function tick(){
  try{
    const d = await j('/state.json');
    document.getElementById('state').textContent = d.ok ? 'LIVE' : 'DEGRADED';
    document.getElementById('state').className = d.ok ? 'good' : 'bad';
    document.getElementById('hq').textContent = small(d.hq);
    document.getElementById('tasks').textContent = small(d.tasks);
    document.getElementById('team').textContent = small(d.team);
    document.getElementById('brain').textContent = small(d.brain);
    document.getElementById('links').textContent = small(d.links);
    document.getElementById('town').textContent = small(d.town);
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
</html>"""

class H(BaseHTTPRequestHandler):
    def log_message(self, fmt, *args):
        return

    def send_bytes(self, code, body, ctype):
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
            return self.send_bytes(200, page(), "text/html; charset=utf-8")
        if path in ("/health.json", "/state.json"):
            hq = fetch("/hq/stats")
            tasks = fetch("/tasks/data")
            team = fetch("/team_live/data", timeout=4)
            brain = fetch("/brain/usage")
            links = fetch("/link_health")
            town = fetch("/town_square_feed")
            out = {
                "ok": hq["ok"] and tasks["ok"],
                "ts": now(),
                "hq": hq,
                "tasks": tasks,
                "team": team,
                "brain": brain,
                "links": links,
                "town": town,
            }
            return self.send_bytes(200, json.dumps(out), "application/json")
        return self.send_bytes(404, "not found", "text/plain")

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
                HQ + "/town/post",
                data=json.dumps(payload).encode(),
                headers={"Content-Type":"application/json"},
                method="POST",
            )
            try:
                with urllib.request.urlopen(req, timeout=4) as r:
                    body = r.read()
                return self.send_bytes(200, body, "application/json")
            except Exception as e:
                return self.send_bytes(502, json.dumps({"ok":False,"error":str(e)}), "application/json")
        return self.send_bytes(404, "not found", "text/plain")

if __name__ == "__main__":
    ThreadingHTTPServer(("0.0.0.0", 8850), H).serve_forever()
PY

chmod +x "$HQ_DASH"

echo "[OK] HQ dashboard file built:"
echo "$HQ_DASH"

echo
echo "===== 2. START CLAUDE HQ DASHBOARD 8850 ====="
tmux kill-session -t hqdash 2>/dev/null || true
pkill -f "qsb_hq_claude_dash_8850.py" 2>/dev/null || true
sleep 1
tmux new-session -d -s hqdash "cd '$ROOT' && python3 -u tools/qsb_hq_claude_dash_8850.py >> logs/hq_claude_dash_8850.log 2>&1"
sleep 2

ss -ltnp | grep ':8850' || true
curl -sS --max-time 6 -o /tmp/hq8850.html -w "HQ8850 http=%{http_code} total=%{time_total}s size=%{size_download}\n" http://127.0.0.1:8850/ || true

echo
echo "===== 3. TRY START FULL ANIMATED DASHBOARD 8765 ====="

if [ -f src/dashboard/server.py ]; then
  echo "[OK] Found src/dashboard/server.py"
  python3 -m py_compile src/dashboard/server.py && echo "[OK] server.py compiles" || echo "[WARN] server.py compile failed"

  if [ -f src/tower/database.py ]; then
    echo "[CHECK] Inspecting src/tower/database.py for known workers-key bug"
    if grep -q "len(f\['workers'\])" src/tower/database.py; then
      BK="src/tower/database.py.bak_workers_key_$(date +%Y%m%d_%H%M%S)"
      cp -a src/tower/database.py "$BK"
      python3 - <<'PY'
from pathlib import Path
p=Path("src/tower/database.py")
txt=p.read_text()
old="conn.execute('INSERT OR IGNORE INTO floor_state VALUES (?,?,?,?,?)',(f['id'],f['status'],100,0 if f['vacant'] else len(f['workers']),now()))"
new="""workers = f.get('workers')
        if workers is None:
            workers = f.get('team_roster', [])
        if workers is None:
            workers = []
        floor_id = f.get('id') or f.get('floor_id') or f.get('name') or 'unknown_floor'
        floor_status = f.get('status') or f.get('execution_mode') or f.get('current_status') or 'unknown'
        vacant = bool(f.get('vacant', False))
        conn.execute('INSERT OR IGNORE INTO floor_state VALUES (?,?,?,?,?)',(floor_id,floor_status,100,0 if vacant else len(workers),now()))"""
if old in txt:
    txt=txt.replace(old,new)
    p.write_text(txt)
    print("[OK] Patched known workers-key bug")
else:
    print("[SKIP] exact workers-key line not found")
PY
      python3 -m py_compile src/tower/database.py && echo "[OK] database.py compiles after check" || echo "[WARN] database.py compile issue after check"
    else
      echo "[OK] Known workers-key bug not present"
    fi
  fi

  tmux kill-session -t dash8765 2>/dev/null || true
  pkill -f "src/dashboard/server.py" 2>/dev/null || true
  sleep 1
  tmux new-session -d -s dash8765 "cd '$ROOT' && PYTHONPATH='$ROOT/src' python3 -u src/dashboard/server.py >> logs/dashboard_8765.log 2>&1"
  sleep 4
  ss -ltnp | grep ':8765' || true
  curl -sS --max-time 8 -o /tmp/dash8765.html -w "DASH8765 http=%{http_code} total=%{time_total}s size=%{size_download}\n" http://127.0.0.1:8765/ || true
  curl -sS --max-time 8 -o /tmp/dash8765api.json -w "DASH8765_API http=%{http_code} total=%{time_total}s size=%{size_download}\n" http://127.0.0.1:8765/api/unified || true
else
  echo "[WARN] src/dashboard/server.py missing"
fi

echo
echo "===== 4. DEAD LINK MAP FROM iPAD HTML ====="

HTML="/tmp/qsb_ipad_phase1.html"
curl -sS --max-time 8 http://127.0.0.1:8852/ipad -o "$HTML" || true

python3 - "$HTML" > "/tmp/qsb_ipad_links_to_test.txt" <<'PY'
import re, sys
html=open(sys.argv[1],encoding="utf-8",errors="ignore").read()
links=[]
for pat in [
    r"""href=['"]([^'"]+)['"]""",
    r"""src=['"]([^'"]+)['"]""",
    r"""fetch\(['"]([^'"]+)['"]""",
    r"""window\.open\(['"]([^'"]+)['"]""",
]:
    links += re.findall(pat, html)
out=[]
for x in links:
    if not x or x.startswith("#") or x.startswith("javascript:") or x.startswith("mailto:"):
        continue
    if x not in out:
        out.append(x)
for x in out:
    print(x)
PY

echo "Links/actions found:"
cat /tmp/qsb_ipad_links_to_test.txt

echo
echo "===== 5. TEST LOCAL/LAN LINKS ====="

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
    https://fonts.googleapis.com/*|https://x.com/*|https://skyscraperhq.com/*)
      echo "[SKIP external/browser] $url"
      continue
      ;;
  esac

  line="$(curl -L -sS --max-time 5 -o /tmp/qsb_link_body -w "http=%{http_code} total=%{time_total}s size=%{size_download}" "$url" 2>&1)"
  code="$(echo "$line" | sed -n 's/.*http=\([0-9][0-9][0-9]\).*/\1/p' | tail -1)"
  [ -z "$code" ] && code="000"

  if [ "$code" = "200" ] || [ "$code" = "204" ] || [ "$code" = "301" ] || [ "$code" = "302" ]; then
    echo "[OK]   $url -> $line"
  else
    echo "[DEAD] $url -> $line"
  fi
done < /tmp/qsb_ipad_links_to_test.txt

echo
echo "===== 6. CHAT PATH TESTS ====="

echo "--- town/post"
curl -sS --max-time 8 -X POST http://127.0.0.1:8852/town/post \
  -H "Content-Type: application/json" \
  --data "{\"from\":\"ross\",\"to\":\"council\",\"text\":\"🧪 golden-ticket chat path test from phase1 at $(date -Is)\",\"src\":\"phase1_chat_test\"}" \
  -w "\ntown_post http=%{http_code} total=%{time_total}s size=%{size_download}\n" || true

echo "--- HQ dash /api/post"
curl -sS --max-time 8 -X POST http://127.0.0.1:8850/api/post \
  -H "Content-Type: application/json" \
  --data "{\"from\":\"ross\",\"to\":\"council\",\"text\":\"🧪 HQ dash chat path test at $(date -Is)\",\"src\":\"hq_dash_phase1_test\"}" \
  -w "\nhq_post http=%{http_code} total=%{time_total}s size=%{size_download}\n" || true

echo
echo "===== 7. FINAL SERVICE CHECK ====="

for url in \
  "http://127.0.0.1:8852/ipad" \
  "http://127.0.0.1:8850/" \
  "http://127.0.0.1:8851/" \
  "http://127.0.0.1:9100/" \
  "http://127.0.0.1:11434/api/tags" \
  "http://127.0.0.1:8765/" \
  "http://127.0.0.1:8765/api/unified" \
  "http://192.168.1.91:9110/"
do
  echo "--- $url"
  curl -sS --max-time 8 -o /tmp/qsb_final_body \
    -w "http=%{http_code} total=%{time_total}s size=%{size_download}\n" \
    "$url" 2>&1 || true
done

echo
echo "===== 8. LOG TAILS ====="
echo "--- HQ 8850 log"
tail -40 logs/hq_claude_dash_8850.log 2>/dev/null || true
echo "--- dashboard 8765 log"
tail -80 logs/dashboard_8765.log 2>/dev/null || true
echo "--- boardroom 8852 log"
tail -40 logs/boardroom_hub_8852.log 2>/dev/null || true

echo
echo "============================================================"
echo "PHASE 1 DONE"
echo "Report:"
echo "$REPORT"
echo
echo "Open these on the iPad/LAN:"
echo "HQ Claude:  http://192.168.1.71:8850/"
echo "Boardroom:  http://192.168.1.71:8852/"
echo "iPad:       http://192.168.1.71:8852/ipad"
echo "Wren:       http://192.168.1.71:8851/"
echo
echo "Still cannot be 100% until every [DEAD] link is either repaired, replaced, or deliberately marked offline."
echo "============================================================"
