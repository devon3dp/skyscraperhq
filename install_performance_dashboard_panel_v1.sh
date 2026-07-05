#!/usr/bin/env bash
set -euo pipefail

cd /vaults/nvme0/qsb_tower_v1
export PYTHONPATH=/vaults/nvme0/qsb_tower_v1/src

TS="$(date -u +%Y%m%dT%H%M%SZ)"

echo "======================================================"
echo "  QSB Tower V1.3 — Performance Dashboard Panel V1"
echo "======================================================"
echo "Mode: display/run sandbox performance loop only"
echo "No live orders. No practice orders. No OpenClaw execution."
echo "No autonomous dispatch. No external providers."

mkdir -p data/registries data/runtime data/logs data/backups scripts tests src/tower

echo
echo "=== BACKUPS ==="
for f in src/dashboard/server.py src/tower/sandbox_performance_sidecar.py; do
  [ -f "$f" ] && cp -f "$f" "data/backups/$(basename "$f").backup_before_performance_panel_${TS}" || true
done

echo
echo "=== CREATE PERFORMANCE SIDECAR ==="
cat > src/tower/sandbox_performance_sidecar.py <<'PY'
#!/usr/bin/env python3
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from datetime import datetime, timezone
import json
import os
import sys
import urllib.parse

ROOT = Path("/vaults/nvme0/qsb_tower_v1")
SRC = ROOT / "src"
sys.path.insert(0, str(SRC))

HOST = "127.0.0.1"
PORT = 8769

LOCKS = {
    "live_trading_enabled": False,
    "order_execution_enabled": False,
    "practice_order_execution_enabled": False,
    "worker_execution_enabled": False,
    "provider_execution_enabled": False,
    "external_provider_execution_enabled": False,
    "openclaw_execution_enabled": False,
    "autonomous_dispatch_enabled": False,
    "live_dispatch_enabled": False,
    "direct_provider_access": False
}


def load_local_env_file():
    env = ROOT / ".env.oanda_practice"
    if not env.exists():
        return
    for line in env.read_text(encoding="utf-8", errors="ignore").splitlines():
        line = line.strip()
        if not line.startswith("export "):
            continue
        k, _, v = line.replace("export ", "", 1).partition("=")
        os.environ.setdefault(k.strip(), v.strip().strip("'").strip('"'))


def load_json(path, fallback=None):
    if fallback is None:
        fallback = {}
    try:
        return json.loads(Path(path).read_text(encoding="utf-8"))
    except Exception:
        return fallback


def json_response(handler, payload, code=200):
    handler.send_response(code)
    handler.send_header("Content-Type", "application/json")
    handler.send_header("Access-Control-Allow-Origin", "http://127.0.0.1:8765")
    handler.send_header("Access-Control-Allow-Methods", "GET, POST, OPTIONS")
    handler.send_header("Access-Control-Allow-Headers", "Content-Type")
    handler.send_header("Cache-Control", "no-store")
    handler.end_headers()
    handler.wfile.write(json.dumps(payload, indent=2, default=str).encode("utf-8"))


def compact_status():
    latest = load_json(ROOT / "data/registries/sandbox_performance_latest.json", {})
    worker = load_json(ROOT / "data/registries/worker_sandbox_latest_tick.json", {})
    ledger = load_json(ROOT / "data/registries/floor41_paper_ledger.json", {})

    perf = latest.get("performance", {})
    return {
        "ok": True,
        "service": "sandbox_performance_sidecar",
        "ts": datetime.now(timezone.utc).isoformat(),
        "phase": "SANDBOX_PERFORMANCE_LOOP_V1",
        "status": "healthy" if latest else "ready",
        "latest_ts": latest.get("ts"),
        "ticks_completed": latest.get("ticks_completed"),
        "worker_count": latest.get("worker_count"),
        "entries_analyzed": perf.get("entries_analyzed"),
        "total_paper_score": perf.get("total_paper_score"),
        "total_observation_delta_pips": perf.get("total_observation_delta_pips"),
        "by_instrument": perf.get("by_instrument", []),
        "kernel_commentary_ok": latest.get("kernel_commentary", {}).get("ok"),
        "kernel_commentary_reply": latest.get("kernel_commentary", {}).get("reply", "")[:1500],
        "latest_worker_tick": worker.get("ts"),
        "ledger_entry_count": ledger.get("entry_count", 0),
        "locks": LOCKS,
        "paper_only": True,
        "not_financial_advice": True
    }


class Handler(BaseHTTPRequestHandler):
    def log_message(self, fmt, *args):
        return

    def do_OPTIONS(self):
        json_response(self, {}, 204)

    def do_GET(self):
        load_local_env_file()
        parsed = urllib.parse.urlparse(self.path)

        try:
            if parsed.path == "/api/performance/status":
                json_response(self, compact_status())
                return

            if parsed.path == "/api/performance/run":
                q = urllib.parse.parse_qs(parsed.query)
                ticks = int(q.get("ticks", ["3"])[0])
                delay = int(q.get("delay", ["5"])[0])
                instruments = q.get("instruments", ["EUR_USD,GBP_USD,USD_JPY"])[0]

                from tower.sandbox_performance_loop import SandboxPerformanceLoop
                report = SandboxPerformanceLoop().run(
                    ticks=ticks,
                    delay_seconds=delay,
                    instruments=instruments,
                    kernel_commentary=True
                )
                json_response(self, {
                    "ok": True,
                    "report": report,
                    "status": compact_status(),
                    "locks": LOCKS
                })
                return

            json_response(self, {"ok": False, "error": "not found", "path": parsed.path}, 404)
        except Exception as exc:
            json_response(self, {"ok": False, "error": str(exc), "locks": LOCKS}, 500)

    def do_POST(self):
        load_local_env_file()
        parsed = urllib.parse.urlparse(self.path)

        if parsed.path != "/api/performance/run":
            json_response(self, {"ok": False, "error": "not found", "path": parsed.path}, 404)
            return

        try:
            length = int(self.headers.get("Content-Length", "0"))
            body = json.loads(self.rfile.read(length).decode("utf-8") or "{}")
            ticks = int(body.get("ticks", 3))
            delay = int(body.get("delay", 5))
            instruments = body.get("instruments") or "EUR_USD,GBP_USD,USD_JPY"

            from tower.sandbox_performance_loop import SandboxPerformanceLoop
            report = SandboxPerformanceLoop().run(
                ticks=ticks,
                delay_seconds=delay,
                instruments=instruments,
                kernel_commentary=True
            )

            json_response(self, {
                "ok": True,
                "report": report,
                "status": compact_status(),
                "locks": LOCKS
            })
        except Exception as exc:
            json_response(self, {"ok": False, "error": str(exc), "locks": LOCKS}, 500)


def main():
    print(f"Sandbox Performance sidecar running at http://{HOST}:{PORT}")
    ThreadingHTTPServer((HOST, PORT), Handler).serve_forever()


if __name__ == "__main__":
    main()
PY

python3 -m py_compile src/tower/sandbox_performance_sidecar.py

echo
echo "=== CREATE SIDECAR SCRIPTS ==="
cat > scripts/run_sandbox_performance_sidecar.sh <<'SH'
#!/usr/bin/env bash
set -euo pipefail
cd /vaults/nvme0/qsb_tower_v1
export PYTHONPATH=/vaults/nvme0/qsb_tower_v1/src

PIDFILE="data/runtime/sandbox_performance_sidecar.pid"
LOGFILE="data/logs/sandbox_performance_sidecar.out"

if [ -f "$PIDFILE" ] && kill -0 "$(cat "$PIDFILE")" 2>/dev/null; then
  echo "Sandbox Performance sidecar already running: PID $(cat "$PIDFILE")"
  exit 0
fi

nohup python3 src/tower/sandbox_performance_sidecar.py > "$LOGFILE" 2>&1 &
echo $! > "$PIDFILE"
sleep 1

echo "Sandbox Performance sidecar started: PID $(cat "$PIDFILE")"
echo "Status: http://127.0.0.1:8769/api/performance/status"
SH
chmod +x scripts/run_sandbox_performance_sidecar.sh

cat > scripts/stop_sandbox_performance_sidecar.sh <<'SH'
#!/usr/bin/env bash
set -euo pipefail
cd /vaults/nvme0/qsb_tower_v1

PIDFILE="data/runtime/sandbox_performance_sidecar.pid"

if [ -f "$PIDFILE" ]; then
  PID="$(cat "$PIDFILE")"
  if kill -0 "$PID" 2>/dev/null; then
    kill "$PID" || true
    sleep 1
  fi
  rm -f "$PIDFILE"
fi

echo "Sandbox Performance sidecar stopped."
SH
chmod +x scripts/stop_sandbox_performance_sidecar.sh

echo
echo "=== INJECT PERFORMANCE DASHBOARD PANEL ==="
python3 - <<'PY'
from pathlib import Path
from datetime import datetime, timezone
import re
import py_compile

ROOT = Path("/vaults/nvme0/qsb_tower_v1")
SERVER = ROOT / "src/dashboard/server.py"

ts = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
backup = SERVER.with_suffix(f".py.backup_before_performance_dashboard_panel_{ts}")
text = SERVER.read_text(encoding="utf-8")
backup.write_text(text, encoding="utf-8")
print("Backup:", backup)

snippet = r'''
<script id="qsb-performance-dashboard-panel">
(function(){
  const API = 'http://127.0.0.1:8769';

  function el(tag, attrs={}, text=''){
    const n = document.createElement(tag);
    for(const [k,v] of Object.entries(attrs)){
      if(k === 'style') n.style.cssText = v;
      else if(k === 'class') n.className = v;
      else n.setAttribute(k,v);
    }
    if(text) n.textContent = text;
    return n;
  }

  function fmt(n, d=3){
    if(n === null || n === undefined || Number.isNaN(Number(n))) return '-';
    return Number(n).toFixed(d);
  }

  function instrumentRows(items){
    if(!items || !items.length) return '<div style="color:#ffaa50">No performance data yet.</div>';
    return items.map(x => `
      <div style="display:grid;grid-template-columns:80px 70px 85px 85px 1fr;gap:6px;padding:5px 0;border-bottom:1px solid rgba(255,201,64,.14)">
        <div style="color:#ffc940;font-weight:900">${x.instrument || ''}</div>
        <div>${x.entries || 0} obs</div>
        <div>Δ ${fmt(x.delta_pips_total,3)} pips</div>
        <div>score ${fmt(x.paper_score_total,3)}</div>
        <div style="color:#7faacc">spread ${fmt(x.avg_spread_pips,2)}</div>
      </div>
    `).join('');
  }

  async function refreshPerformance(){
    const status = document.getElementById('performancePanelStatus');
    const body = document.getElementById('performancePanelBody');
    if(!status || !body) return;

    try{
      const res = await fetch(API + '/api/performance/status?t=' + Date.now(), {cache:'no-store'});
      const data = await res.json();

      if(!data.ok){
        status.textContent = 'error';
        status.style.color = '#ff6060';
        body.textContent = data.error || 'unknown error';
        return;
      }

      status.textContent = `${data.status} — ticks ${data.ticks_completed || 0} — entries ${data.entries_analyzed || 0}`;
      status.style.color = '#4dffb0';

      const locks = data.locks || {};

      body.innerHTML = `
        <div style="font-size:11px;color:#6ab8ff;margin-bottom:7px">
          Sandbox Performance Loop · paper-only scoring · no order execution
        </div>

        <div style="display:grid;grid-template-columns:repeat(4,1fr);gap:6px;margin-bottom:8px">
          <div class="perf-card">Ticks<br><b>${data.ticks_completed || 0}</b></div>
          <div class="perf-card">Entries<br><b>${data.entries_analyzed || 0}</b></div>
          <div class="perf-card">Score<br><b>${fmt(data.total_paper_score,3)}</b></div>
          <div class="perf-card">Δ Pips<br><b>${fmt(data.total_observation_delta_pips,3)}</b></div>
        </div>

        <div class="perf-section-title">Per-Instrument Performance</div>
        ${instrumentRows(data.by_instrument || [])}

        <div class="perf-section-title">Kernel Review</div>
        <div style="white-space:pre-wrap;color:#d8eaff;background:rgba(5,35,25,.45);border:1px solid rgba(77,255,176,.18);border-radius:8px;padding:7px;max-height:110px;overflow:auto">
          ${data.kernel_commentary_reply || 'No kernel review yet.'}
        </div>

        <div class="perf-section-title">Locks</div>
        <div style="color:#4dffb0;font-weight:900">
          live orders: ${locks.order_execution_enabled === false ? 'OFF' : 'CHECK'} ·
          practice orders: ${locks.practice_order_execution_enabled === false ? 'OFF' : 'CHECK'} ·
          OpenClaw: ${locks.openclaw_execution_enabled === false ? 'OFF' : 'CHECK'} ·
          dispatch: ${locks.autonomous_dispatch_enabled === false ? 'OFF' : 'CHECK'}
        </div>
      `;
    }catch(e){
      status.textContent = 'sidecar offline';
      status.style.color = '#ffaa50';
      body.textContent = 'Run: ./scripts/run_sandbox_performance_sidecar.sh';
    }
  }

  async function runPerformanceLoop(){
    const btn = document.getElementById('performanceRunBtn');
    const status = document.getElementById('performancePanelStatus');
    if(!btn) return;

    btn.disabled = true;
    btn.textContent = 'Running…';
    if(status) status.textContent = 'running 3 tick loop…';

    try{
      const res = await fetch(API + '/api/performance/run', {
        method:'POST',
        headers:{'Content-Type':'application/json'},
        body:JSON.stringify({ticks:3, delay:5, instruments:'EUR_USD,GBP_USD,USD_JPY'})
      });
      const data = await res.json();
      if(!data.ok){
        alert('Performance loop error: ' + (data.error || JSON.stringify(data)));
      }
      await refreshPerformance();
    }catch(e){
      alert('Performance sidecar offline. Run: ./scripts/run_sandbox_performance_sidecar.sh');
    }finally{
      btn.disabled = false;
      btn.textContent = 'Run 3 Tick Loop';
    }
  }

  function createPanel(){
    if(document.getElementById('performanceDashboardPanel')) return;

    const style = document.createElement('style');
    style.textContent = `
      .perf-card{padding:6px 8px;border:1px solid rgba(255,201,64,.22);border-radius:8px;background:rgba(45,32,5,.70);color:#d8eaff;font-size:11px}
      .perf-card b{color:#ffc940;font-size:13px}
      .perf-section-title{color:#ffc940;font-weight:900;font-size:11px;margin:9px 0 4px 0;letter-spacing:.3px}
    `;
    document.head.appendChild(style);

    const panel = el('div', {
      id:'performanceDashboardPanel',
      style:[
        'position:fixed',
        'left:1188px',
        'bottom:58px',
        'width:430px',
        'height:430px',
        'z-index:99995',
        'display:flex',
        'flex-direction:column',
        'background:rgba(4,12,24,.96)',
        'border:1px solid rgba(255,201,64,.45)',
        'box-shadow:0 0 24px rgba(255,201,64,.15)',
        'border-radius:14px',
        'overflow:hidden',
        'font-family:Segoe UI,system-ui,Arial,sans-serif',
        'font-size:12px'
      ].join(';')
    });

    const header = el('div', {
      style:'display:flex;justify-content:space-between;align-items:center;padding:10px 12px;background:rgba(45,32,5,.95);border-bottom:1px solid rgba(255,201,64,.35)'
    });

    const title = el('div');
    title.innerHTML = '<div style="font-weight:900;color:#ffc940">Sandbox Performance Loop</div><div id="performancePanelStatus" style="font-size:11px;color:#ffaa50">checking…</div>';

    const controls = el('div', {style:'display:flex;gap:6px'});
    const refresh = el('button', {style:'padding:5px 8px;border-radius:8px;background:#071528;color:#d8eaff;border:1px solid #1a3a5c;cursor:pointer'}, 'Refresh');
    const run = el('button', {id:'performanceRunBtn', style:'padding:5px 8px;border-radius:8px;background:#5a3a05;color:#ffc940;border:1px solid rgba(255,201,64,.5);font-weight:900;cursor:pointer'}, 'Run 3 Tick Loop');
    const hide = el('button', {style:'padding:5px 8px;border-radius:8px;background:#071528;color:#d8eaff;border:1px solid #1a3a5c;cursor:pointer'}, 'Hide');

    refresh.onclick = refreshPerformance;
    run.onclick = runPerformanceLoop;
    hide.onclick = () => {
      const b = document.getElementById('performancePanelBody');
      const hidden = b.style.display === 'none';
      b.style.display = hidden ? 'block' : 'none';
      panel.style.height = hidden ? '430px' : '52px';
      hide.textContent = hidden ? 'Hide' : 'Show';
    };

    controls.appendChild(refresh);
    controls.appendChild(run);
    controls.appendChild(hide);
    header.appendChild(title);
    header.appendChild(controls);

    const body = el('div', {
      id:'performancePanelBody',
      style:'padding:10px;overflow:auto;flex:1;color:#d8eaff;background:linear-gradient(180deg,rgba(45,32,5,.45),rgba(4,12,24,.92))'
    });

    panel.appendChild(header);
    panel.appendChild(body);
    document.body.appendChild(panel);

    refreshPerformance();
  }

  if(document.readyState === 'loading') document.addEventListener('DOMContentLoaded', createPanel);
  else createPanel();

  setInterval(refreshPerformance, 10000);
})();
</script>
'''

text = re.sub(r'\n?<script id="qsb-performance-dashboard-panel">.*?</script>\n?', '\n', text, flags=re.S)

if "</body>" in text:
    text = text.replace("</body>", snippet + "\n</body>", 1)
elif "</html>" in text:
    text = text.replace("</html>", snippet + "\n</html>", 1)
else:
    raise SystemExit("No </body> or </html> found.")

SERVER.write_text(text, encoding="utf-8")
py_compile.compile(str(SERVER), doraise=True)
print("Installed Performance Dashboard panel.")
PY

echo
echo "=== CREATE TEST ==="
cat > tests/test_performance_dashboard_panel_v1.py <<'PY'
import sys
import py_compile
from pathlib import Path

ROOT = Path("/vaults/nvme0/qsb_tower_v1")
sys.path.insert(0, str(ROOT / "src"))

py_compile.compile(str(ROOT / "src/tower/sandbox_performance_sidecar.py"), doraise=True)
py_compile.compile(str(ROOT / "src/dashboard/server.py"), doraise=True)

server = (ROOT / "src/dashboard/server.py").read_text(encoding="utf-8")
assert "qsb-performance-dashboard-panel" in server
assert "performanceDashboardPanel" in server
assert "api/performance/status" in server
assert "api/performance/run" in server

print("PERFORMANCE DASHBOARD PANEL V1 TEST PASSED")
PY

python3 tests/test_performance_dashboard_panel_v1.py

echo
echo "=== START PERFORMANCE SIDECAR ==="
./scripts/stop_sandbox_performance_sidecar.sh || true
./scripts/run_sandbox_performance_sidecar.sh

echo
echo "=== TEST PERFORMANCE SIDECAR STATUS ==="
curl -s http://127.0.0.1:8769/api/performance/status | python3 -m json.tool | head -120

echo
echo "=== RESTART DASHBOARD ==="
./stop.sh
./run.sh
./status.sh

echo
echo "======================================================"
echo "  PERFORMANCE DASHBOARD PANEL V1 COMPLETE"
echo "======================================================"
echo "Open:"
echo "  http://127.0.0.1:8765/?v=performance-dashboard"
echo
echo "Hard refresh with Ctrl+Shift+R."
echo "======================================================"
