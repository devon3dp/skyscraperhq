#!/usr/bin/env bash
set -euo pipefail

cd /vaults/nvme0/qsb_tower_v1
export PYTHONPATH=/vaults/nvme0/qsb_tower_v1/src

TS="$(date -u +%Y%m%dT%H%M%SZ)"

echo "======================================================"
echo "  QSB Tower V1.3 — Worker Sandbox Dashboard Panel V1"
echo "======================================================"
echo "Mode: dashboard panel + sandbox tick sidecar only"
echo "No live orders. No practice orders. No OpenClaw execution."
echo "No autonomous dispatch. No external providers."

mkdir -p data/registries data/runtime data/logs data/backups scripts tests src/tower

echo
echo "=== BACKUPS ==="
for f in \
  src/dashboard/server.py \
  src/tower/worker_sandbox_sidecar.py
do
  [ -f "$f" ] && cp -f "$f" "data/backups/$(basename "$f").backup_before_worker_dashboard_${TS}" || true
done

echo
echo "=== CREATE WORKER SANDBOX SIDECAR ==="
cat > src/tower/worker_sandbox_sidecar.py <<'PY'
#!/usr/bin/env python3
"""
QSB Tower V1.3 — Worker Sandbox Sidecar API

Dashboard browser -> localhost:8768 -> worker_sandbox.py

Safety:
- Sandbox workers only.
- No live OANDA orders.
- No practice OANDA orders.
- No OpenClaw execution.
- No autonomous dispatch.
- No external providers.
"""

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
PORT = 8768

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


def short_worker_status():
    latest = load_json(ROOT / "data/registries/worker_sandbox_latest_tick.json", {})
    ledger = load_json(ROOT / "data/registries/floor41_paper_ledger.json", {})
    packets = load_json(ROOT / "data/registries/worker_sandbox_lift_packets_latest.json", {})
    paper = load_json(ROOT / "data/registries/oanda_paper_strategy_latest.json", {})
    registry = load_json(ROOT / "data/registries/worker_sandbox_registry.json", {})

    return {
        "ok": True,
        "service": "worker_sandbox_sidecar",
        "ts": datetime.now(timezone.utc).isoformat(),
        "sandbox": "worker_sandbox_v1",
        "status": "healthy" if latest else "ready",
        "sandbox_workers_enabled": True,
        "worker_execution_enabled": False,
        "openclaw_execution_enabled": False,
        "autonomous_dispatch_enabled": False,
        "worker_count": len(registry.get("workers", [])),
        "workers": registry.get("workers", []),
        "latest_tick_ts": latest.get("ts"),
        "latest_packet_count": len(latest.get("lift_packets", [])),
        "latest_packets": latest.get("lift_packets", [])[-10:],
        "ledger": {
            "entry_count": ledger.get("entry_count", 0),
            "latest_entry_count": ledger.get("latest_entry_count", 0),
            "latest_entries": ledger.get("latest_entries", [])[-10:],
            "simulated_observation_delta_pips_total": load_json(ROOT / "data/runtime/floor41_paper_ledger_latest.json", {}).get("simulated_observation_delta_pips_total")
        },
        "paper_lab": {
            "latest_ts": paper.get("ts"),
            "summary": paper.get("summary", {}),
            "instruments": paper.get("instruments", [])
        },
        "kernel_commentary": {
            "ok": latest.get("kernel_commentary", {}).get("ok"),
            "reply": latest.get("kernel_commentary", {}).get("reply", "")[:1200] if latest else ""
        },
        "locks": LOCKS,
        "paper_only": True,
        "not_financial_advice": True
    }


def json_response(handler, payload, code=200):
    handler.send_response(code)
    handler.send_header("Content-Type", "application/json")
    handler.send_header("Access-Control-Allow-Origin", "http://127.0.0.1:8765")
    handler.send_header("Access-Control-Allow-Methods", "GET, POST, OPTIONS")
    handler.send_header("Access-Control-Allow-Headers", "Content-Type")
    handler.send_header("Cache-Control", "no-store")
    handler.end_headers()
    handler.wfile.write(json.dumps(payload, indent=2, default=str).encode("utf-8"))


class Handler(BaseHTTPRequestHandler):
    def log_message(self, fmt, *args):
        return

    def do_OPTIONS(self):
        json_response(self, {}, 204)

    def do_GET(self):
        load_local_env_file()
        parsed = urllib.parse.urlparse(self.path)

        try:
            if parsed.path == "/api/worker_sandbox/status":
                json_response(self, short_worker_status())
                return

            if parsed.path == "/api/worker_sandbox/tick":
                q = urllib.parse.parse_qs(parsed.query)
                instruments = q.get("instruments", ["EUR_USD,GBP_USD,USD_JPY"])[0]
                from tower.worker_sandbox import WorkerSandbox
                tick = WorkerSandbox().tick(instruments)
                json_response(self, {
                    "ok": True,
                    "tick": tick,
                    "status": short_worker_status(),
                    "locks": LOCKS
                })
                return

            json_response(self, {"ok": False, "error": "not found", "path": parsed.path}, 404)
        except Exception as exc:
            json_response(self, {"ok": False, "error": str(exc), "locks": LOCKS}, 500)

    def do_POST(self):
        load_local_env_file()
        parsed = urllib.parse.urlparse(self.path)

        if parsed.path != "/api/worker_sandbox/tick":
            json_response(self, {"ok": False, "error": "not found", "path": parsed.path}, 404)
            return

        try:
            length = int(self.headers.get("Content-Length", "0"))
            body = json.loads(self.rfile.read(length).decode("utf-8") or "{}")
            instruments = body.get("instruments") or "EUR_USD,GBP_USD,USD_JPY"

            from tower.worker_sandbox import WorkerSandbox
            tick = WorkerSandbox().tick(instruments)

            json_response(self, {
                "ok": True,
                "tick": tick,
                "status": short_worker_status(),
                "locks": LOCKS
            })
        except Exception as exc:
            json_response(self, {"ok": False, "error": str(exc), "locks": LOCKS}, 500)


def main():
    print(f"Worker Sandbox sidecar running at http://{HOST}:{PORT}")
    ThreadingHTTPServer((HOST, PORT), Handler).serve_forever()


if __name__ == "__main__":
    main()
PY

python3 -m py_compile src/tower/worker_sandbox_sidecar.py

echo
echo "=== CREATE SIDECAR SCRIPTS ==="
cat > scripts/run_worker_sandbox_sidecar.sh <<'SH'
#!/usr/bin/env bash
set -euo pipefail
cd /vaults/nvme0/qsb_tower_v1
export PYTHONPATH=/vaults/nvme0/qsb_tower_v1/src

PIDFILE="data/runtime/worker_sandbox_sidecar.pid"
LOGFILE="data/logs/worker_sandbox_sidecar.out"

if [ -f "$PIDFILE" ] && kill -0 "$(cat "$PIDFILE")" 2>/dev/null; then
  echo "Worker Sandbox sidecar already running: PID $(cat "$PIDFILE")"
  exit 0
fi

nohup python3 src/tower/worker_sandbox_sidecar.py > "$LOGFILE" 2>&1 &
echo $! > "$PIDFILE"
sleep 1

echo "Worker Sandbox sidecar started: PID $(cat "$PIDFILE")"
echo "Status: http://127.0.0.1:8768/api/worker_sandbox/status"
SH
chmod +x scripts/run_worker_sandbox_sidecar.sh

cat > scripts/stop_worker_sandbox_sidecar.sh <<'SH'
#!/usr/bin/env bash
set -euo pipefail
cd /vaults/nvme0/qsb_tower_v1

PIDFILE="data/runtime/worker_sandbox_sidecar.pid"

if [ -f "$PIDFILE" ]; then
  PID="$(cat "$PIDFILE")"
  if kill -0 "$PID" 2>/dev/null; then
    kill "$PID" || true
    sleep 1
  fi
  rm -f "$PIDFILE"
fi

echo "Worker Sandbox sidecar stopped."
SH
chmod +x scripts/stop_worker_sandbox_sidecar.sh

cat > scripts/worker_sandbox_sidecar_status.sh <<'SH'
#!/usr/bin/env bash
set -euo pipefail
cd /vaults/nvme0/qsb_tower_v1

PIDFILE="data/runtime/worker_sandbox_sidecar.pid"

if [ -f "$PIDFILE" ] && kill -0 "$(cat "$PIDFILE")" 2>/dev/null; then
  echo "Worker Sandbox sidecar running: PID $(cat "$PIDFILE")"
else
  echo "Worker Sandbox sidecar not running"
fi

curl -s http://127.0.0.1:8768/api/worker_sandbox/status | python3 -m json.tool || true
SH
chmod +x scripts/worker_sandbox_sidecar_status.sh

echo
echo "=== INJECT WORKER SANDBOX DASHBOARD PANEL ==="
python3 - <<'PY'
from pathlib import Path
from datetime import datetime, timezone
import re
import py_compile

ROOT = Path("/vaults/nvme0/qsb_tower_v1")
SERVER = ROOT / "src/dashboard/server.py"

ts = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
backup = SERVER.with_suffix(f".py.backup_before_worker_sandbox_dashboard_panel_{ts}")
text = SERVER.read_text(encoding="utf-8")
backup.write_text(text, encoding="utf-8")
print("Backup:", backup)

snippet = r'''
<script id="qsb-worker-sandbox-panel">
(function(){
  const API = 'http://127.0.0.1:8768';

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

  function safe(v, fallback='-'){
    return v === null || v === undefined || v === '' ? fallback : v;
  }

  function workerRows(workers){
    if(!workers || !workers.length) return '<div style="color:#ffaa50">No sandbox workers registered.</div>';
    return workers.map(w => `
      <div style="display:grid;grid-template-columns:135px 1fr;gap:6px;padding:5px 0;border-bottom:1px solid rgba(176,138,255,.14)">
        <div style="color:#b08aff;font-weight:900">${w.name || w.id}</div>
        <div style="color:#d8eaff">${w.role || ''}</div>
      </div>
    `).join('');
  }

  function packetRows(packets){
    if(!packets || !packets.length) return '<div style="color:#ffaa50">No lift packets yet.</div>';
    return packets.slice(-6).map(p => `
      <div style="padding:5px 0;border-bottom:1px solid rgba(92,224,255,.12)">
        <span style="color:#5ce0ff;font-weight:900">${p.worker_name || p.worker_id}</span>
        <span style="color:#7faacc"> · ${p.source_floor} → ${p.target_floor}</span>
        <div style="font-size:10px;color:#ffaa50">${p.task || ''}</div>
      </div>
    `).join('');
  }

  function ledgerRows(entries){
    if(!entries || !entries.length) return '<div style="color:#ffaa50">No paper ledger entries yet.</div>';
    return entries.slice(-5).map(e => `
      <div style="display:grid;grid-template-columns:75px 90px 1fr;gap:6px;padding:5px 0;border-bottom:1px solid rgba(77,255,176,.12)">
        <div style="color:#4dffb0;font-weight:900">${e.instrument || ''}</div>
        <div>${e.paper_signal || 'observe'}</div>
        <div style="color:#ffc940">${e.simulated_delta_pips_since_prior_observation != null ? Number(e.simulated_delta_pips_since_prior_observation).toFixed(3) + ' pips' : '-'}</div>
      </div>
    `).join('');
  }

  async function refreshWorkerSandbox(){
    const status = document.getElementById('workerSandboxStatus');
    const body = document.getElementById('workerSandboxBody');
    if(!status || !body) return;

    try{
      const res = await fetch(API + '/api/worker_sandbox/status?t=' + Date.now(), {cache:'no-store'});
      const data = await res.json();

      if(!data.ok){
        status.textContent = 'error';
        status.style.color = '#ff6060';
        body.textContent = data.error || 'unknown error';
        return;
      }

      const ledger = data.ledger || {};
      const lab = data.paper_lab || {};
      const summary = lab.summary || {};
      const locks = data.locks || {};

      status.textContent = `${data.status} — ${data.worker_count} sandbox workers — packets ${data.latest_packet_count}`;
      status.style.color = '#4dffb0';

      body.innerHTML = `
        <div style="font-size:11px;color:#6ab8ff;margin-bottom:7px">
          Floor 25 → Floor 41 → Floor 37 → Floor 38 lift loop · paper only · no execution
        </div>

        <div style="display:grid;grid-template-columns:repeat(4,1fr);gap:6px;margin-bottom:8px">
          <div class="ws-card">Workers<br><b>${data.worker_count}</b></div>
          <div class="ws-card">Packets<br><b>${data.latest_packet_count}</b></div>
          <div class="ws-card">Ledger<br><b>${ledger.entry_count || 0}</b></div>
          <div class="ws-card">Δ pips<br><b>${ledger.simulated_observation_delta_pips_total != null ? Number(ledger.simulated_observation_delta_pips_total).toFixed(3) : '0.000'}</b></div>
        </div>

        <div class="ws-section-title">Latest Paper Signals</div>
        ${ledgerRows(ledger.latest_entries || [])}

        <div class="ws-section-title">Latest Lift Packets</div>
        ${packetRows(data.latest_packets || [])}

        <div class="ws-section-title">Sandbox Workers</div>
        ${workerRows(data.workers || [])}

        <div class="ws-section-title">Locks</div>
        <div style="color:#4dffb0;font-weight:900">
          live orders: ${locks.order_execution_enabled === false ? 'OFF' : 'CHECK'} ·
          practice orders: ${locks.practice_order_execution_enabled === false ? 'OFF' : 'CHECK'} ·
          OpenClaw: ${locks.openclaw_execution_enabled === false ? 'OFF' : 'CHECK'} ·
          dispatch: ${locks.autonomous_dispatch_enabled === false ? 'OFF' : 'CHECK'}
        </div>

        <div class="ws-section-title">Kernel Commentary</div>
        <div style="white-space:pre-wrap;color:#d8eaff;background:rgba(5,35,25,.45);border:1px solid rgba(77,255,176,.18);border-radius:8px;padding:7px;max-height:95px;overflow:auto">
          ${safe(data.kernel_commentary?.reply, 'No commentary yet.')}
        </div>
      `;
    }catch(e){
      status.textContent = 'sidecar offline';
      status.style.color = '#ffaa50';
      body.textContent = 'Run: ./scripts/run_worker_sandbox_sidecar.sh';
    }
  }

  async function runWorkerSandboxTick(){
    const btn = document.getElementById('workerSandboxTickBtn');
    const status = document.getElementById('workerSandboxStatus');
    if(!btn) return;

    btn.disabled = true;
    btn.textContent = 'Running…';
    if(status) status.textContent = 'running sandbox tick…';

    try{
      const res = await fetch(API + '/api/worker_sandbox/tick', {
        method:'POST',
        headers:{'Content-Type':'application/json'},
        body:JSON.stringify({instruments:'EUR_USD,GBP_USD,USD_JPY'})
      });
      const data = await res.json();
      if(!data.ok){
        alert('Worker sandbox tick error: ' + (data.error || JSON.stringify(data)));
      }
      await refreshWorkerSandbox();
    }catch(e){
      alert('Worker Sandbox sidecar offline. Run: ./scripts/run_worker_sandbox_sidecar.sh');
    }finally{
      btn.disabled = false;
      btn.textContent = 'Run Tick';
    }
  }

  function createPanel(){
    if(document.getElementById('workerSandboxPanel')) return;

    const style = document.createElement('style');
    style.textContent = `
      .ws-card{padding:6px 8px;border:1px solid rgba(176,138,255,.22);border-radius:8px;background:rgba(8,12,32,.86);color:#9fb0cc;font-size:11px}
      .ws-card b{color:#b08aff;font-size:13px}
      .ws-section-title{color:#ffc940;font-weight:900;font-size:11px;margin:9px 0 4px 0;letter-spacing:.3px}
    `;
    document.head.appendChild(style);

    const panel = el('div', {
      id:'workerSandboxPanel',
      style:[
        'position:fixed',
        'left:610px',
        'bottom:58px',
        'width:570px',
        'height:430px',
        'z-index:99996',
        'display:flex',
        'flex-direction:column',
        'background:rgba(4,12,24,.96)',
        'border:1px solid rgba(176,138,255,.45)',
        'box-shadow:0 0 24px rgba(176,138,255,.16)',
        'border-radius:14px',
        'overflow:hidden',
        'font-family:Segoe UI,system-ui,Arial,sans-serif',
        'font-size:12px'
      ].join(';')
    });

    const header = el('div', {
      style:'display:flex;justify-content:space-between;align-items:center;padding:10px 12px;background:rgba(24,15,50,.95);border-bottom:1px solid rgba(176,138,255,.35)'
    });

    const title = el('div');
    title.innerHTML = '<div style="font-weight:900;color:#b08aff">Worker Sandbox — Lift Operations</div><div id="workerSandboxStatus" style="font-size:11px;color:#ffaa50">checking…</div>';

    const controls = el('div', {style:'display:flex;gap:6px'});
    const refresh = el('button', {style:'padding:5px 8px;border-radius:8px;background:#071528;color:#d8eaff;border:1px solid #1a3a5c;cursor:pointer'}, 'Refresh');
    const tick = el('button', {id:'workerSandboxTickBtn', style:'padding:5px 8px;border-radius:8px;background:#321a58;color:#d8c4ff;border:1px solid rgba(176,138,255,.5);font-weight:900;cursor:pointer'}, 'Run Tick');
    const hide = el('button', {style:'padding:5px 8px;border-radius:8px;background:#071528;color:#d8eaff;border:1px solid #1a3a5c;cursor:pointer'}, 'Hide');

    refresh.onclick = refreshWorkerSandbox;
    tick.onclick = runWorkerSandboxTick;
    hide.onclick = () => {
      const b = document.getElementById('workerSandboxBody');
      const hidden = b.style.display === 'none';
      b.style.display = hidden ? 'block' : 'none';
      panel.style.height = hidden ? '430px' : '52px';
      hide.textContent = hidden ? 'Hide' : 'Show';
    };

    controls.appendChild(refresh);
    controls.appendChild(tick);
    controls.appendChild(hide);
    header.appendChild(title);
    header.appendChild(controls);

    const body = el('div', {
      id:'workerSandboxBody',
      style:'padding:10px;overflow:auto;flex:1;color:#d8eaff;background:linear-gradient(180deg,rgba(8,12,32,.82),rgba(4,12,24,.92))'
    });

    panel.appendChild(header);
    panel.appendChild(body);
    document.body.appendChild(panel);

    refreshWorkerSandbox();
  }

  if(document.readyState === 'loading') document.addEventListener('DOMContentLoaded', createPanel);
  else createPanel();

  setInterval(refreshWorkerSandbox, 10000);
})();
</script>
'''

text = re.sub(r'\n?<script id="qsb-worker-sandbox-panel">.*?</script>\n?', '\n', text, flags=re.S)

if "</body>" in text:
    text = text.replace("</body>", snippet + "\n</body>", 1)
elif "</html>" in text:
    text = text.replace("</html>", snippet + "\n</html>", 1)
else:
    raise SystemExit("No </body> or </html> found.")

SERVER.write_text(text, encoding="utf-8")
py_compile.compile(str(SERVER), doraise=True)
print("Installed Worker Sandbox dashboard panel.")
PY

echo
echo "=== CREATE TEST ==="
cat > tests/test_worker_sandbox_dashboard_panel_v1.py <<'PY'
import sys
import py_compile
from pathlib import Path

ROOT = Path("/vaults/nvme0/qsb_tower_v1")
sys.path.insert(0, str(ROOT / "src"))

py_compile.compile(str(ROOT / "src/tower/worker_sandbox_sidecar.py"), doraise=True)
py_compile.compile(str(ROOT / "src/dashboard/server.py"), doraise=True)

server = (ROOT / "src/dashboard/server.py").read_text(encoding="utf-8")
assert "qsb-worker-sandbox-panel" in server
assert "workerSandboxPanel" in server
assert "api/worker_sandbox/status" in server
assert "api/worker_sandbox/tick" in server

print("WORKER SANDBOX DASHBOARD PANEL V1 TEST PASSED")
PY

python3 tests/test_worker_sandbox_dashboard_panel_v1.py

echo
echo "=== START SIDECAR ==="
./scripts/stop_worker_sandbox_sidecar.sh || true
./scripts/run_worker_sandbox_sidecar.sh

echo
echo "=== TEST SIDECAR STATUS ==="
curl -s http://127.0.0.1:8768/api/worker_sandbox/status | python3 -m json.tool | head -160

echo
echo "=== RESTART DASHBOARD ==="
./stop.sh
./run.sh
./status.sh

echo
echo "======================================================"
echo "  WORKER SANDBOX DASHBOARD PANEL V1 COMPLETE"
echo "======================================================"
echo "Open:"
echo "  http://127.0.0.1:8765/?v=worker-sandbox"
echo
echo "Hard refresh with Ctrl+Shift+R."
echo "======================================================"
