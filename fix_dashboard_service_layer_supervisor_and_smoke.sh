#!/usr/bin/env bash
set -u

PROJECT="/vaults/nvme0/qsb_tower_v1"
RUN_ROOT="/home/ross/Desktop/SKYSCRAPERHQ_RUNS"
SEND="$RUN_ROOT/00_SEND_THIS_TO_CHATGPT"
STAMP="$(date +%Y%m%d_%H%M%S)"
RUN_DIR="$RUN_ROOT/${STAMP}_fix_dashboard_service_layer_supervisor"
REPORT="$RUN_DIR/reports/fix_dashboard_service_layer_supervisor_report.txt"

mkdir -p "$RUN_DIR/reports" "$RUN_DIR/backups" "$RUN_DIR/logs" "$SEND" "$PROJECT/runtime" "$PROJECT/logs" "$PROJECT/tools" "$PROJECT/data/registries"
rm -f "$RUN_ROOT/LATEST"
ln -s "$RUN_DIR" "$RUN_ROOT/LATEST"

exec > >(tee "$REPORT") 2>&1

echo "============================================================"
echo "SKYSCRAPERHQ — FIX DASHBOARD SERVICE LAYER + STOP LOOP"
echo "Generated: $(date -Is)"
echo "Project: $PROJECT"
echo "============================================================"
echo "Purpose:"
echo " - Stop repetitive Task Council routing loop."
echo " - Bring Claude HQ dashboard up on 8850."
echo " - Keep Wren dashboard up on 8851."
echo " - Bring Wren Metrics sidecar up on 8853."
echo " - Verify Boardroom 8852 and Gene Pool 8860."
echo " - Verify Acer and TP truthfully."
echo " - Do not mark tasks done."
echo " - Do not touch keys."
echo " - Do not touch trading."
echo "============================================================"

cd "$PROJECT" || exit 1

echo
echo "===== 1. HARD PAUSE ROUTING / EXECUTION LOOPS ====="

touch "$PROJECT/runtime/AUTONOMY_PAUSED_DASHBOARD_SERVICE_REPAIR"

stop_pidfile() {
  local label="$1"
  local pidfile="$2"
  if [ -f "$pidfile" ]; then
    local pid
    pid="$(cat "$pidfile" 2>/dev/null || true)"
    if [ -n "$pid" ] && kill -0 "$pid" 2>/dev/null; then
      kill "$pid" 2>/dev/null || true
      echo "[STOPPED] $label pid=$pid"
    else
      echo "[OK] $label not running from pidfile"
    fi
  else
    echo "[OK] $label pidfile missing"
  fi
}

stop_pidfile "Task Council Auto Dispatcher" "$PROJECT/runtime/task_council_auto_dispatcher.pid"
stop_pidfile "Worker Executor Verifier" "$PROJECT/runtime/worker_executor_verifier.pid"

pkill -f "qsb_task_council_auto_dispatcher.py" 2>/dev/null || true
pkill -f "qsb_worker_executor_verifier.py" 2>/dev/null || true

echo "[OK] loops paused"
sleep 2

echo
echo "===== 2. PATCH AUTO DISPATCHER SO IT CANNOT REPEAT SAME ROUTED TASK ====="

AUTO="$PROJECT/tools/qsb_task_council_auto_dispatcher.py"
if [ -f "$AUTO" ]; then
  cp -a "$AUTO" "$RUN_DIR/backups/qsb_task_council_auto_dispatcher.py.before_loop_guard_$STAMP"

  python3 - <<'PY'
from pathlib import Path
import re

p = Path("/vaults/nvme0/qsb_tower_v1/tools/qsb_task_council_auto_dispatcher.py")
s = p.read_text(errors="ignore")

if "QSB_ROUTE_LOOP_GUARD_V1" not in s:
    insert = r'''
# QSB_ROUTE_LOOP_GUARD_V1
ROUTED_LEDGER = REG / "qsb_task_council_auto_dispatcher_routed_ids.json"
PAUSE_FILE = RUNTIME / "AUTONOMY_PAUSED_DASHBOARD_SERVICE_REPAIR"

def _load_routed_ids():
    try:
        if ROUTED_LEDGER.exists():
            data = json.loads(ROUTED_LEDGER.read_text(encoding="utf-8"))
            if isinstance(data, list):
                return set(str(x) for x in data)
    except Exception:
        pass
    return set()

def _mark_routed_id(tid):
    try:
        ids = _load_routed_ids()
        ids.add(str(tid))
        ROUTED_LEDGER.parent.mkdir(parents=True, exist_ok=True)
        ROUTED_LEDGER.write_text(json.dumps(sorted(ids), indent=2), encoding="utf-8")
    except Exception:
        pass

'''
    marker = "def now():"
    if marker in s:
        s = s.replace(marker, insert + "\n" + marker)
    else:
        s = insert + "\n" + s

    # Pause gate inside cycle_once.
    s = s.replace(
        "def cycle_once():\n",
        "def cycle_once():\n"
        "    if PAUSE_FILE.exists():\n"
        "        state = {\"ts\": now(), \"ok\": True, \"paused\": True, \"reason\": str(PAUSE_FILE), \"processed\": [], \"errors\": []}\n"
        "        write_json(STATE_JSON, state)\n"
        "        log_event(\"cycle_paused\", reason=str(PAUSE_FILE))\n"
        "        return state\n",
        1
    )

    # Ledger gate inside is_dispatchable after text checks.
    s = s.replace(
        "    if not tid or not text:\n        return False\n",
        "    if not tid or not text:\n        return False\n\n"
        "    if tid in _load_routed_ids():\n"
        "        return False\n",
        1
    )

    # Mark routed IDs before returning successful routed events.
    s = s.replace(
        '    log_event("dispatch_routed_for_work", **out)\n    return out',
        '    _mark_routed_id(tid)\n    log_event("dispatch_routed_for_work", **out)\n    return out'
    )
    s = s.replace(
        '    log_event("dispatch_complete", **out)\n    return out',
        '    _mark_routed_id(tid)\n    log_event("dispatch_complete", **out)\n    return out'
    )

    print("[OK] inserted loop guard + pause gate")
else:
    print("[OK] loop guard already present")

p.write_text(s, encoding="utf-8")
PY

  python3 -m py_compile "$AUTO" && echo "[OK] auto dispatcher compiles after loop guard" || echo "[WARN] auto dispatcher compile failed"
else
  echo "[WARN] auto dispatcher file missing"
fi

echo
echo "===== 3. INSTALL CLAUDE HQ RESCUE DASHBOARD ON 8850 ====="

HQ="$PROJECT/tools/qsb_claude_hq_rescue_dashboard.py"
cp -a "$HQ" "$RUN_DIR/backups/qsb_claude_hq_rescue_dashboard.py.bak_$STAMP" 2>/dev/null || true

cat > "$HQ" <<'PY'
#!/usr/bin/env python3
from http.server import ThreadingHTTPServer, BaseHTTPRequestHandler
from pathlib import Path
from datetime import datetime, timezone
import json
import urllib.request
import urllib.error
from urllib.parse import urlparse

PROJECT = Path("/vaults/nvme0/qsb_tower_v1")
REG = PROJECT / "data" / "registries"

def now():
    return datetime.now(timezone.utc).isoformat()

def get_json(url, timeout=4):
    try:
        with urllib.request.urlopen(url, timeout=timeout) as r:
            raw = r.read().decode("utf-8", "replace")
            try:
                return {"ok": True, "http": r.status, "data": json.loads(raw)}
            except Exception:
                return {"ok": True, "http": r.status, "raw": raw[:2000]}
    except Exception as e:
        return {"ok": False, "error": repr(e)}

def status():
    return {
        "ok": True,
        "service": "Claude HQ Rescue Dashboard",
        "name": "Claude HQ",
        "port": 8850,
        "ts": now(),
        "role": "HQ dashboard shell and service health view. This is not a Claude API fallback brain.",
        "doctrine": {
            "claude_hq_name": "Claude HQ",
            "ceos_use": "API Gene Pool only",
            "wren_fallback": "blocked",
            "no_key_changes": True,
            "no_trading": True,
        },
        "links": {
            "boardroom": "http://127.0.0.1:8852/ipad",
            "gene_pool": "http://127.0.0.1:8860/",
            "tasks": "http://127.0.0.1:8852/tasks",
            "town_square": "http://127.0.0.1:8852/town_square",
        },
        "boardroom_link_health": get_json("http://127.0.0.1:8852/link_health"),
        "gene_pool_live": get_json("http://127.0.0.1:8860/api/live"),
    }

def html():
    return """<!doctype html>
<html><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
<title>Claude HQ · Rescue Dashboard</title>
<style>
body{margin:0;background:#07111f;color:#e8f7ff;font:14px system-ui,-apple-system,Segoe UI,sans-serif}
header{padding:18px 20px;background:#0d213a;border-bottom:1px solid #25527e}
h1{margin:0;font-size:25px}.sub{opacity:.75;margin-top:4px}
.grid{display:grid;grid-template-columns:repeat(auto-fit,minmax(240px,1fr));gap:12px;padding:14px}
.card{background:#0b1728;border:1px solid #244766;border-radius:16px;padding:14px}
.k{opacity:.7;text-transform:uppercase;font-size:12px;letter-spacing:.08em}.v{font-size:26px;font-weight:800;margin-top:6px}
a{color:#67e8f9}pre{white-space:pre-wrap;background:#020712;border:1px solid #1d3552;border-radius:14px;padding:12px;max-height:460px;overflow:auto}
</style></head>
<body>
<header><h1>🧠 Claude HQ · Rescue Dashboard</h1>
<div class=sub>HQ dashboard service on 8850 · Brain Router remains API Gene Pool only · no Wren fallback</div></header>
<section class=grid>
<div class=card><div class=k>service</div><div class=v>LIVE</div></div>
<div class=card><div class=k>Brain Router</div><div class=v id=router>…</div></div>
<div class=card><div class=k>Boardroom</div><div class=v id=boardroom>…</div></div>
<div class=card><div class=k>Doctrine</div><div class=v>LOCKED</div></div>
</section>
<section class=grid>
<div class=card><b>Links</b><br>
<a href="http://127.0.0.1:8852/ipad">Boardroom iPad</a><br>
<a href="http://127.0.0.1:8852/tasks">Task Council</a><br>
<a href="http://127.0.0.1:8852/town_square">Town Square</a><br>
<a href="http://127.0.0.1:8860/">Gene Pool Router</a>
</div>
<div class=card style="grid-column:1/-1"><b>Live status</b><pre id=raw>loading…</pre></div>
</section>
<script>
async function tick(){
  try{
    const r=await fetch('/api/status',{cache:'no-store'});
    const d=await r.json();
    router.textContent = d.gene_pool_live?.ok ? 'LIVE' : 'DOWN';
    boardroom.textContent = d.boardroom_link_health?.ok ? 'LIVE' : 'CHECK';
    raw.textContent=JSON.stringify(d,null,2);
  }catch(e){raw.textContent='status error: '+e}
}
tick(); setInterval(tick,2000);
</script>
</body></html>"""

class H(BaseHTTPRequestHandler):
    server_version = "ClaudeHQRescue/1.0"

    def send_body(self, code, body, ctype="application/json; charset=utf-8"):
        raw = body.encode("utf-8") if isinstance(body, str) else json.dumps(body, indent=2, ensure_ascii=False).encode("utf-8")
        self.send_response(code)
        self.send_header("Content-Type", ctype)
        self.send_header("Content-Length", str(len(raw)))
        self.send_header("Cache-Control", "no-store")
        self.end_headers()
        try:
            self.wfile.write(raw)
        except BrokenPipeError:
            pass

    def do_GET(self):
        p = urlparse(self.path).path
        if p in ("/", "/dashboard", "/hq"):
            return self.send_body(200, html(), "text/html; charset=utf-8")
        if p in ("/health", "/api/status"):
            return self.send_body(200, status())
        return self.send_body(404, {"ok": False, "error": "not found", "path": p}, "application/json; charset=utf-8")

if __name__ == "__main__":
    print("[BOOT] Claude HQ Rescue Dashboard on 0.0.0.0:8850", flush=True)
    ThreadingHTTPServer(("0.0.0.0", 8850), H).serve_forever()
PY

chmod +x "$HQ"
python3 -m py_compile "$HQ" && echo "[OK] Claude HQ rescue dashboard compiles"

echo
echo "===== 4. INSTALL WREN METRICS SIDECAR ON 8853 ====="

WM="$PROJECT/tools/qsb_wren_metrics_sidecar.py"
cp -a "$WM" "$RUN_DIR/backups/qsb_wren_metrics_sidecar.py.bak_$STAMP" 2>/dev/null || true

cat > "$WM" <<'PY'
#!/usr/bin/env python3
from http.server import ThreadingHTTPServer, BaseHTTPRequestHandler
from pathlib import Path
from datetime import datetime, timezone, timedelta
import json, re
from urllib.parse import urlparse

PROJECT = Path("/vaults/nvme0/qsb_tower_v1")
REG = PROJECT / "data" / "registries"
TOOLS = PROJECT / "tools"
ART = PROJECT / "data" / "worker_artifacts"

def now():
    return datetime.now(timezone.utc).isoformat()

def tail(path, max_bytes=524288):
    try:
        p=Path(path)
        if not p.exists(): return []
        size=p.stat().st_size
        with p.open("rb") as f:
            if size > max_bytes:
                f.seek(size-max_bytes)
            raw=f.read()
        return raw.decode("utf-8","ignore").splitlines()
    except Exception as e:
        return [json.dumps({"tail_error":repr(e), "path":str(path)})]

def jsonl(path):
    out=[]
    for line in tail(path):
        try: out.append(json.loads(line))
        except Exception:
            if line.strip(): out.append({"raw": line[:500]})
    return out

def parse_ts(x):
    if not isinstance(x, dict): return None
    v=x.get("ts")
    if not v: return None
    try: return datetime.fromisoformat(str(v).replace("Z","+00:00"))
    except Exception: return None

def recent_count(items, hours=1):
    cutoff=datetime.now(timezone.utc)-timedelta(hours=hours)
    c=0
    for x in items:
        ts=parse_ts(x)
        if ts and ts >= cutoff:
            c += 1
    return c

def metrics():
    files = {
        "evolution": REG/"qsb_wren_evolution_cycles.jsonl",
        "bugs": REG/"qsb_wren_bug_catches.jsonl",
        "lessons": REG/"qsb_wren_lessons.jsonl",
        "jobs_done": REG/"qsb_wren_jobs_done.jsonl",
        "task_auto": REG/"qsb_task_council_auto_dispatcher_events.jsonl",
        "worker": REG/"qsb_worker_executor_verifier_events.jsonl",
        "dashboard_repair": REG/"qsb_dashboard_repair_worker_events.jsonl",
    }
    data={k: jsonl(v) for k,v in files.items()}
    tools_built=len(list(TOOLS.glob("qsb_*.py"))) + len(list(TOOLS.glob("skyscraper_*.py")))
    artifacts=len(list(ART.glob("*.json"))) if ART.exists() else 0
    rule_hits=0
    for f in files.values():
        rule_hits += len(re.findall(r"\bR\d{1,3}\b|rulebook|cited[-_ ]?rules?", "\n".join(tail(f)), flags=re.I))

    recent=sum(recent_count(v) for v in data.values())
    gauge=min(100, recent*10 + min(30, artifacts))

    return {
        "ok": True,
        "service": "Wren Metrics Sidecar",
        "ts": now(),
        "metrics": {
            "learnings_per_hour": recent,
            "tools_built": tools_built,
            "notes_cited_rules_count": rule_hits,
            "activity_gauge": gauge,
            "evolution_cycles_total": len(data["evolution"]),
            "evolution_cycles_per_hour": recent_count(data["evolution"]),
            "bug_catches_total": len(data["bugs"]),
            "bug_catches_per_hour": recent_count(data["bugs"]),
            "lessons_total": len(data["lessons"]),
            "jobs_done_total": len(data["jobs_done"]),
            "worker_artifacts": artifacts
        },
        "recent": {k: v[-6:] for k,v in data.items()},
        "doctrine": {
            "wren": "protected GPU guardian",
            "ceos": "API Gene Pool only",
            "no_key_changes": True,
            "no_trading": True
        }
    }

def html():
    return """<!doctype html><html><head><meta charset="utf-8">
<meta name=viewport content="width=device-width,initial-scale=1">
<title>Wren Metrics</title>
<style>
body{margin:0;background:#06110d;color:#eafff2;font:14px system-ui}
header{padding:18px 20px;background:#0b2518;border-bottom:1px solid #1f6b49}
h1{margin:0}.grid{display:grid;grid-template-columns:repeat(auto-fit,minmax(210px,1fr));gap:12px;padding:14px}
.card{background:#0b1c15;border:1px solid #1e5f43;border-radius:16px;padding:14px}
.k{opacity:.7;font-size:12px;text-transform:uppercase}.v{font-size:30px;font-weight:900;margin-top:8px}
pre{white-space:pre-wrap;background:#020805;border:1px solid #17432f;border-radius:14px;padding:12px;max-height:420px;overflow:auto}
</style></head><body>
<header><h1>🛡️ Wren Metrics · Live</h1><div>learnings/hour · tools built · notes cited-rules count · activity gauge · evolution cycles · bug catches</div></header>
<section class=grid>
<div class=card><div class=k>learnings/hour</div><div class=v id=a>…</div></div>
<div class=card><div class=k>tools built</div><div class=v id=b>…</div></div>
<div class=card><div class=k>notes cited-rules count</div><div class=v id=c>…</div></div>
<div class=card><div class=k>activity gauge</div><div class=v id=d>…</div></div>
<div class=card><div class=k>evolution cycles</div><div class=v id=e>…</div></div>
<div class=card><div class=k>bug catches</div><div class=v id=f>…</div></div>
</section>
<section class=grid><div class=card style="grid-column:1/-1"><pre id=raw>loading</pre></div></section>
<script>
async function tick(){
 const r=await fetch('/api/metrics',{cache:'no-store'}); const j=await r.json(); const m=j.metrics||{};
 a.textContent=m.learnings_per_hour??0; b.textContent=m.tools_built??0; c.textContent=m.notes_cited_rules_count??0;
 d.textContent=(m.activity_gauge??0)+'%'; e.textContent=m.evolution_cycles_total??0; f.textContent=m.bug_catches_total??0;
 raw.textContent=JSON.stringify(j,null,2);
}
tick(); setInterval(tick,1500);
</script></body></html>"""

class H(BaseHTTPRequestHandler):
    def sendit(self, code, body, ctype="application/json; charset=utf-8"):
        raw = body.encode() if isinstance(body,str) else json.dumps(body, indent=2, ensure_ascii=False).encode()
        self.send_response(code)
        self.send_header("Content-Type", ctype)
        self.send_header("Content-Length", str(len(raw)))
        self.send_header("Cache-Control", "no-store")
        self.end_headers()
        try: self.wfile.write(raw)
        except BrokenPipeError: pass
    def do_GET(self):
        p=urlparse(self.path).path
        if p in ("/","/metrics","/wren_metrics"):
            return self.sendit(200, html(), "text/html; charset=utf-8")
        if p in ("/health","/api/metrics","/api/wren_metrics"):
            return self.sendit(200, metrics())
        return self.sendit(404, {"ok":False,"path":p})

if __name__=="__main__":
    print("[BOOT] Wren Metrics Sidecar on 0.0.0.0:8853", flush=True)
    ThreadingHTTPServer(("0.0.0.0",8853),H).serve_forever()
PY

chmod +x "$WM"
python3 -m py_compile "$WM" && echo "[OK] Wren metrics sidecar compiles"

echo
echo "===== 5. START / RESTART CRITICAL DASHBOARD SERVICES ====="

start_if_down() {
  local label="$1"
  local url="$2"
  local start_cmd="$3"
  if curl -sS --max-time 3 "$url" >/dev/null 2>&1; then
    echo "[OK] $label already up: $url"
  else
    echo "[START] $label"
    bash -lc "$start_cmd"
    sleep 2
    if curl -sS --max-time 5 "$url" >/dev/null 2>&1; then
      echo "[OK] $label started"
    else
      echo "[FAIL] $label still down after start"
    fi
  fi
}

# Claude HQ rescue.
pkill -f "qsb_claude_hq_rescue_dashboard.py" 2>/dev/null || true
bash -lc "cd '$PROJECT' && ulimit -n 65535 && nohup python3 -u tools/qsb_claude_hq_rescue_dashboard.py >> logs/hq_claude_8850.log 2>&1 & echo \$! > runtime/hq_claude_8850.pid"
sleep 2

# Wren metrics sidecar.
pkill -f "qsb_wren_metrics_sidecar.py" 2>/dev/null || true
bash -lc "cd '$PROJECT' && ulimit -n 65535 && nohup python3 -u tools/qsb_wren_metrics_sidecar.py >> logs/wren_metrics_sidecar_8853.log 2>&1 & echo \$! > runtime/wren_metrics_sidecar_8853.pid"
sleep 2

# Boardroom.
start_if_down "Boardroom" "http://127.0.0.1:8852/ipad" "cd '$PROJECT' && ulimit -n 65535 && nohup python3 -u tools/qsb_boardroom_hub.py --port 8852 >> logs/boardroom_hub_8852.log 2>&1 & echo \$! > runtime/boardroom_hub_8852.pid"

# Gene Pool.
start_if_down "Gene Pool" "http://127.0.0.1:8860/api/live" "cd '$PROJECT' && ulimit -n 65535 && ./run_gene_pool_router.sh >> logs/gene_pool_router_8860.log 2>&1 & echo \$! > runtime/gene_pool_router_8860.pid"

# Wren if down.
if ! curl -sS --max-time 3 "http://127.0.0.1:8851/" >/dev/null 2>&1; then
  if [ -f "$PROJECT/tools/qsb_wren_local_agent.py" ]; then
    echo "[START] Wren 8851"
    bash -lc "cd '$PROJECT' && ulimit -n 65535 && nohup python3 -u tools/qsb_wren_local_agent.py --port 8851 >> logs/wren_local_agent_8851.log 2>&1 & echo \$! > runtime/wren_local_agent_8851.pid"
    sleep 3
  else
    echo "[FAIL] Wren file missing"
  fi
else
  echo "[OK] Wren already up on 8851"
fi

echo
echo "===== 6. SERVICE LAYER SMOKE TEST ====="

smoke_url() {
  local label="$1"
  local url="$2"
  local out="$RUN_DIR/logs/$(echo "$label" | tr ' /:' '____').body"
  echo "--- $label"
  echo "URL: $url"
  curl -sS --max-time 25 -o "$out" -w "http=%{http_code} total=%{time_total}s size=%{size_download}\n" "$url" || true
  head -c 380 "$out" 2>/dev/null || true
  echo
}

smoke_url "Claude HQ direct 8850" "http://127.0.0.1:8850/"
smoke_url "Claude HQ status 8850" "http://127.0.0.1:8850/api/status"
smoke_url "Wren direct 8851" "http://127.0.0.1:8851/"
smoke_url "Wren metrics sidecar 8853" "http://127.0.0.1:8853/"
smoke_url "Wren metrics API 8853" "http://127.0.0.1:8853/api/metrics"
smoke_url "Boardroom iPad 8852" "http://127.0.0.1:8852/ipad"
smoke_url "Gene Pool direct 8860" "http://127.0.0.1:8860/"
smoke_url "Gene Pool API 8860" "http://127.0.0.1:8860/api/live"
smoke_url "Boardroom proxy HQ" "http://127.0.0.1:8852/proxy/hq"
smoke_url "Boardroom proxy Wren" "http://127.0.0.1:8852/proxy/wren"
smoke_url "Boardroom proxy Acer" "http://127.0.0.1:8852/proxy/acer"
smoke_url "Boardroom proxy TP" "http://127.0.0.1:8852/proxy/tp"
smoke_url "Team Live" "http://127.0.0.1:8852/team_live"
smoke_url "Team Live data" "http://127.0.0.1:8852/team_live/data"
smoke_url "Tasks data" "http://127.0.0.1:8852/tasks/data"
smoke_url "Town feed" "http://127.0.0.1:8852/town_square_feed"
smoke_url "Acer LAN" "http://192.168.1.41:9000/"
smoke_url "TP LAN" "http://192.168.1.91:9110/"

echo
echo "===== 7. MACHINE-READABLE STATUS ====="

python3 - <<'PY'
import json, urllib.request, urllib.error, socket, pathlib, subprocess

tests = [
    ("claude_hq", "http://127.0.0.1:8850/"),
    ("claude_hq_api", "http://127.0.0.1:8850/api/status"),
    ("wren", "http://127.0.0.1:8851/"),
    ("wren_metrics", "http://127.0.0.1:8853/api/metrics"),
    ("boardroom", "http://127.0.0.1:8852/ipad"),
    ("gene_pool", "http://127.0.0.1:8860/api/live"),
    ("proxy_hq", "http://127.0.0.1:8852/proxy/hq"),
    ("proxy_wren", "http://127.0.0.1:8852/proxy/wren"),
    ("proxy_acer", "http://127.0.0.1:8852/proxy/acer"),
    ("proxy_tp", "http://127.0.0.1:8852/proxy/tp"),
    ("acer_lan", "http://192.168.1.41:9000/"),
    ("tp_lan", "http://192.168.1.91:9110/"),
]

def check(url):
    try:
        with urllib.request.urlopen(url, timeout=8) as r:
            return {"ok": 200 <= r.status < 300, "http": r.status}
    except Exception as e:
        return {"ok": False, "error": repr(e)}

status = {name: {"url": url, **check(url)} for name, url in tests}

critical_local = ["claude_hq", "wren", "wren_metrics", "boardroom", "gene_pool", "proxy_hq", "proxy_wren"]
status["summary"] = {
    "critical_local_ok": all(status[k]["ok"] for k in critical_local),
    "acer_ok": status["acer_lan"]["ok"] or status["proxy_acer"]["ok"],
    "tp_ok": status["tp_lan"]["ok"] or status["proxy_tp"]["ok"],
    "tp_resolution": "If TP is still false with No route to host, TP-Pip is not reachable on LAN. Power it on, connect it to same Wi-Fi/LAN, or update Boardroom TP URL/IP.",
    "loops_paused": pathlib.Path("/vaults/nvme0/qsb_tower_v1/runtime/AUTONOMY_PAUSED_DASHBOARD_SERVICE_REPAIR").exists(),
}

out = pathlib.Path("/vaults/nvme0/qsb_tower_v1/data/registries/qsb_dashboard_service_layer_status.json")
out.write_text(json.dumps(status, indent=2), encoding="utf-8")
print(json.dumps(status, indent=2))
PY

cp -a "$PROJECT/data/registries/qsb_dashboard_service_layer_status.json" "$RUN_DIR/reports/qsb_dashboard_service_layer_status.json" 2>/dev/null || true
cp -a "$PROJECT/data/registries/qsb_dashboard_service_layer_status.json" "$SEND/qsb_dashboard_service_layer_status.json" 2>/dev/null || true

echo
echo "===== 8. PROCESS / PORT SNAPSHOT ====="
ps -eo pid,ppid,etime,cmd | grep -E "qsb_claude_hq_rescue|qsb_wren_local_agent|qsb_wren_metrics_sidecar|qsb_boardroom_hub|skyscraper_gene_pool_router|8850|8851|8852|8853|8860" | grep -v grep || true
echo
ss -ltnp 2>/dev/null | grep -E ":(8850|8851|8852|8853|8860)\b" || true

echo
echo "===== 9. IMPORTANT RESULT ====="
echo "Autonomous loops are STILL PAUSED."
echo "Do not restart Task Council Auto Dispatcher until dashboard services are green."
echo
echo "Pause marker:"
echo "$PROJECT/runtime/AUTONOMY_PAUSED_DASHBOARD_SERVICE_REPAIR"
echo
echo "To resume later, after you approve:"
echo "rm -f $PROJECT/runtime/AUTONOMY_PAUSED_DASHBOARD_SERVICE_REPAIR"
echo "$PROJECT/run_task_council_auto_dispatcher.sh"

echo
echo "===== 10. URLS ====="
LAN_IP="$(hostname -I 2>/dev/null | awk '{print $1}')"
echo "iPad:"
echo "http://${LAN_IP:-127.0.0.1}:8852/ipad"
echo
echo "Claude HQ:"
echo "http://${LAN_IP:-127.0.0.1}:8850/"
echo
echo "Wren:"
echo "http://${LAN_IP:-127.0.0.1}:8851/"
echo
echo "Wren Metrics:"
echo "http://${LAN_IP:-127.0.0.1}:8853/"
echo
echo "Gene Pool:"
echo "http://${LAN_IP:-127.0.0.1}:8852/proxy/gene_pool"
echo
echo "Acer:"
echo "http://192.168.1.41:9000/"
echo
echo "TP expected:"
echo "http://192.168.1.91:9110/"

echo
echo "============================================================"
echo "DONE — DASHBOARD SERVICE LAYER FIX + SMOKE COMPLETE"
echo "Report:"
echo "$REPORT"
echo "Send-back:"
echo "$SEND/LATEST_REPORT.txt"
echo "============================================================"

cp -a "$REPORT" "$SEND/LATEST_REPORT.txt"
