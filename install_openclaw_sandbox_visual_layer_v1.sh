#!/usr/bin/env bash
set -euo pipefail

cd /vaults/nvme0/qsb_tower_v1
export PYTHONPATH=/vaults/nvme0/qsb_tower_v1/src

TS="$(date -u +%Y%m%dT%H%M%SZ)"

echo "======================================================"
echo "  QSB Tower V1.3 — OpenClaw Sandbox Visual Layer V1"
echo "======================================================"
echo "Mode: OpenClaw sandbox candidates + animated dashboard only"
echo "No real OpenClaw execution. No autonomous dispatch. No orders."

mkdir -p data/registries data/runtime data/logs data/backups scripts tests src/tower

echo
echo "=== BACKUPS ==="
for f in \
  src/dashboard/server.py \
  src/tower/openclaw_sandbox_layer.py \
  src/tower/openclaw_visual_sidecar.py \
  data/registries/openclaw_sandbox_policy.json \
  data/registries/openclaw_sandbox_registry.json
do
  [ -f "$f" ] && cp -f "$f" "data/backups/$(basename "$f").backup_before_openclaw_visual_${TS}" || true
done

echo
echo "=== WRITE OPENCLAW SANDBOX POLICY ==="
cat > data/registries/openclaw_sandbox_policy.json <<'JSON'
{
  "policy": "openclaw_sandbox_visual_layer_v1",
  "version": "1.0",
  "mode": "sandbox_visual_only",
  "openclaw_sandbox_enabled": true,
  "openclaw_visualization_enabled": true,
  "openclaw_execution_enabled": false,
  "openclaw_real_tool_execution_enabled": false,
  "autonomous_dispatch_enabled": false,
  "live_dispatch_enabled": false,
  "worker_execution_enabled": false,
  "provider_execution_enabled": false,
  "external_provider_execution_enabled": false,
  "direct_provider_access": false,
  "live_trading_enabled": false,
  "order_execution_enabled": false,
  "practice_order_execution_enabled": false,
  "allowed": [
    "display OpenClaw sandbox workers",
    "read paper strategy summaries",
    "read sandbox performance summaries",
    "generate sandbox-only recommendations",
    "animate lift packets and worker motion in dashboard"
  ],
  "forbidden": [
    "execute OpenClaw tools",
    "place OANDA orders",
    "enable autonomous dispatch",
    "enable external providers",
    "enable real worker execution"
  ]
}
JSON

echo
echo "=== WRITE OPENCLAW SANDBOX REGISTRY ==="
cat > data/registries/openclaw_sandbox_registry.json <<'JSON'
{
  "registry": "openclaw_sandbox_registry_v1",
  "openclaw_sandbox_enabled": true,
  "openclaw_execution_enabled": false,
  "workers": [
    {
      "id": "openclaw_market_probe",
      "name": "OpenClaw Market Probe",
      "role": "Sandbox-only inspection of Floor 41 paper market state.",
      "home_floor": "floor_41",
      "sandbox_only": true,
      "execution_enabled": false
    },
    {
      "id": "openclaw_strategy_mapper",
      "name": "OpenClaw Strategy Mapper",
      "role": "Maps paper signals into candidate strategy notes.",
      "home_floor": "floor_37",
      "sandbox_only": true,
      "execution_enabled": false
    },
    {
      "id": "openclaw_risk_guard",
      "name": "OpenClaw Risk Guard",
      "role": "Checks that all execution locks remain closed.",
      "home_floor": "floor_30",
      "sandbox_only": true,
      "execution_enabled": false
    },
    {
      "id": "openclaw_lift_observer",
      "name": "OpenClaw Lift Observer",
      "role": "Watches sandbox packets move through the tower lift system.",
      "home_floor": "floor_25",
      "sandbox_only": true,
      "execution_enabled": false
    }
  ]
}
JSON

echo
echo "=== CREATE OPENCLAW SANDBOX MODULE ==="
cat > src/tower/openclaw_sandbox_layer.py <<'PY'
#!/usr/bin/env python3
"""
QSB Tower V1.3 — OpenClaw Sandbox Visual Layer V1

This is NOT real OpenClaw execution.
It makes OpenClaw candidates visible as sandbox observers and dashboard actors.

No orders.
No autonomous dispatch.
No external providers.
No real tool execution.
"""

from pathlib import Path
from datetime import datetime, timezone
import json
import random
import uuid

ROOT = Path("/vaults/nvme0/qsb_tower_v1")
REG = ROOT / "data/registries"
RUNTIME = ROOT / "data/runtime"
LOG = ROOT / "data/logs/openclaw_sandbox_layer.jsonl"

LOCKS = {
    "live_trading_enabled": False,
    "order_execution_enabled": False,
    "practice_order_execution_enabled": False,
    "worker_execution_enabled": False,
    "provider_execution_enabled": False,
    "external_provider_execution_enabled": False,
    "openclaw_execution_enabled": False,
    "openclaw_real_tool_execution_enabled": False,
    "autonomous_dispatch_enabled": False,
    "live_dispatch_enabled": False,
    "direct_provider_access": False
}


def load_json(path, fallback=None):
    if fallback is None:
        fallback = {}
    try:
        return json.loads(Path(path).read_text(encoding="utf-8"))
    except Exception:
        return fallback


def write_json(path, data):
    Path(path).parent.mkdir(parents=True, exist_ok=True)
    Path(path).write_text(json.dumps(data, indent=2), encoding="utf-8")


def append_jsonl(path, record):
    Path(path).parent.mkdir(parents=True, exist_ok=True)
    with Path(path).open("a", encoding="utf-8") as f:
        f.write(json.dumps(record) + "\n")


def registry_workers():
    reg = load_json(REG / "openclaw_sandbox_registry.json", {})
    return reg.get("workers", [])


class OpenClawSandboxLayer:
    def status(self):
        latest = load_json(REG / "openclaw_sandbox_latest.json", {})
        perf = load_json(REG / "sandbox_performance_latest.json", {})
        worker = load_json(REG / "worker_sandbox_latest_tick.json", {})
        paper = load_json(REG / "oanda_paper_strategy_latest.json", {})

        return {
            "layer": "openclaw_sandbox_visual_layer_v1",
            "status": "healthy" if latest else "ready",
            "openclaw_sandbox_enabled": True,
            "openclaw_visualization_enabled": True,
            "openclaw_execution_enabled": False,
            "worker_count": len(registry_workers()),
            "workers": registry_workers(),
            "latest_ts": latest.get("ts"),
            "latest_packets": latest.get("packets", []),
            "latest_recommendations": latest.get("recommendations", []),
            "performance_summary": perf.get("performance", {}),
            "worker_tick_ts": worker.get("ts"),
            "paper_lab_ts": paper.get("ts"),
            "locks": LOCKS,
            "sandbox_only": True,
            "not_financial_advice": True
        }

    def tick(self):
        ts = datetime.now(timezone.utc).isoformat()
        perf = load_json(REG / "sandbox_performance_latest.json", {})
        paper = load_json(REG / "oanda_paper_strategy_latest.json", {})
        workers = registry_workers()

        perf_summary = perf.get("performance", {})
        instruments = perf_summary.get("by_instrument", [])
        paper_instruments = paper.get("instruments", [])

        recommendations = []
        for item in instruments:
            inst = item.get("instrument")
            score = item.get("paper_score_total", 0) or 0
            delta = item.get("delta_pips_total", 0) or 0
            spread = item.get("avg_spread_pips")

            if score > 0.5 and delta > 0:
                rec = "continue_observation_positive_bias"
            elif delta < -2:
                rec = "tighten_filter_or_pause_pair"
            else:
                rec = "observe_only"

            recommendations.append({
                "instrument": inst,
                "sandbox_recommendation": rec,
                "paper_score_total": score,
                "delta_pips_total": delta,
                "avg_spread_pips": spread,
                "execution_allowed": False
            })

        routes = [
            ("floor_25", "floor_41", "OpenClaw sandbox probe checks paper market state"),
            ("floor_41", "floor_37", "OpenClaw maps paper signals into simulation notes"),
            ("floor_37", "floor_38", "OpenClaw sends strategy notes into sandbox containment"),
            ("floor_38", "floor_30", "OpenClaw risk guard verifies locks"),
            ("floor_30", "floor_25", "OpenClaw returns lock report to worker coordination")
        ]

        packets = []
        for idx, worker in enumerate(workers):
            src, dst, task = routes[idx % len(routes)]
            packets.append({
                "packet_id": f"oc_pkt_{uuid.uuid4().hex[:12]}",
                "ts": ts,
                "worker_id": worker.get("id"),
                "worker_name": worker.get("name"),
                "source_floor": src,
                "target_floor": dst,
                "task": task,
                "status": "delivered",
                "sandbox_only": True,
                "execution_enabled": False,
                "lift_lane": random.randint(1, 9),
                "locks": LOCKS
            })

        state = {
            "ts": ts,
            "layer": "openclaw_sandbox_visual_layer_v1",
            "status": "healthy",
            "openclaw_sandbox_enabled": True,
            "openclaw_visualization_enabled": True,
            "openclaw_execution_enabled": False,
            "worker_count": len(workers),
            "workers": workers,
            "packets": packets,
            "recommendations": recommendations,
            "paper_lab_instruments": paper_instruments,
            "performance_summary": perf_summary,
            "locks": LOCKS,
            "sandbox_only": True,
            "not_financial_advice": True
        }

        write_json(REG / "openclaw_sandbox_latest.json", state)
        write_json(RUNTIME / "openclaw_sandbox_latest.json", state)
        append_jsonl(LOG, state)
        return state


def status():
    return OpenClawSandboxLayer().status()


def tick():
    return OpenClawSandboxLayer().tick()


if __name__ == "__main__":
    print(json.dumps(status(), indent=2))
PY

echo
echo "=== CREATE OPENCLAW VISUAL SIDECAR ==="
cat > src/tower/openclaw_visual_sidecar.py <<'PY'
#!/usr/bin/env python3
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from datetime import datetime, timezone
import json
import sys
import urllib.parse

ROOT = Path("/vaults/nvme0/qsb_tower_v1")
SRC = ROOT / "src"
sys.path.insert(0, str(SRC))

HOST = "127.0.0.1"
PORT = 8770

LOCKS = {
    "live_trading_enabled": False,
    "order_execution_enabled": False,
    "practice_order_execution_enabled": False,
    "worker_execution_enabled": False,
    "provider_execution_enabled": False,
    "external_provider_execution_enabled": False,
    "openclaw_execution_enabled": False,
    "openclaw_real_tool_execution_enabled": False,
    "autonomous_dispatch_enabled": False,
    "live_dispatch_enabled": False,
    "direct_provider_access": False
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
        parsed = urllib.parse.urlparse(self.path)

        try:
            from tower.openclaw_sandbox_layer import OpenClawSandboxLayer
            layer = OpenClawSandboxLayer()

            if parsed.path == "/api/openclaw/status":
                json_response(self, layer.status())
                return

            if parsed.path == "/api/openclaw/tick":
                json_response(self, {
                    "ok": True,
                    "tick": layer.tick(),
                    "status": layer.status(),
                    "locks": LOCKS
                })
                return

            json_response(self, {"ok": False, "error": "not found", "path": parsed.path}, 404)
        except Exception as exc:
            json_response(self, {"ok": False, "error": str(exc), "locks": LOCKS}, 500)

    def do_POST(self):
        parsed = urllib.parse.urlparse(self.path)
        if parsed.path != "/api/openclaw/tick":
            json_response(self, {"ok": False, "error": "not found", "path": parsed.path}, 404)
            return

        try:
            from tower.openclaw_sandbox_layer import OpenClawSandboxLayer
            layer = OpenClawSandboxLayer()
            json_response(self, {
                "ok": True,
                "tick": layer.tick(),
                "status": layer.status(),
                "locks": LOCKS
            })
        except Exception as exc:
            json_response(self, {"ok": False, "error": str(exc), "locks": LOCKS}, 500)


def main():
    print(f"OpenClaw Visual sidecar running at http://{HOST}:{PORT}")
    ThreadingHTTPServer((HOST, PORT), Handler).serve_forever()


if __name__ == "__main__":
    main()
PY

python3 -m py_compile src/tower/openclaw_sandbox_layer.py
python3 -m py_compile src/tower/openclaw_visual_sidecar.py

echo
echo "=== CREATE OPENCLAW SIDECAR SCRIPTS ==="
cat > scripts/run_openclaw_visual_sidecar.sh <<'SH'
#!/usr/bin/env bash
set -euo pipefail
cd /vaults/nvme0/qsb_tower_v1
export PYTHONPATH=/vaults/nvme0/qsb_tower_v1/src

PIDFILE="data/runtime/openclaw_visual_sidecar.pid"
LOGFILE="data/logs/openclaw_visual_sidecar.out"

if [ -f "$PIDFILE" ] && kill -0 "$(cat "$PIDFILE")" 2>/dev/null; then
  echo "OpenClaw Visual sidecar already running: PID $(cat "$PIDFILE")"
  exit 0
fi

nohup python3 src/tower/openclaw_visual_sidecar.py > "$LOGFILE" 2>&1 &
echo $! > "$PIDFILE"
sleep 1

echo "OpenClaw Visual sidecar started: PID $(cat "$PIDFILE")"
echo "Status: http://127.0.0.1:8770/api/openclaw/status"
SH
chmod +x scripts/run_openclaw_visual_sidecar.sh

cat > scripts/stop_openclaw_visual_sidecar.sh <<'SH'
#!/usr/bin/env bash
set -euo pipefail
cd /vaults/nvme0/qsb_tower_v1

PIDFILE="data/runtime/openclaw_visual_sidecar.pid"

if [ -f "$PIDFILE" ]; then
  PID="$(cat "$PIDFILE")"
  if kill -0 "$PID" 2>/dev/null; then
    kill "$PID" || true
    sleep 1
  fi
  rm -f "$PIDFILE"
fi

echo "OpenClaw Visual sidecar stopped."
SH
chmod +x scripts/stop_openclaw_visual_sidecar.sh

echo
echo "=== INJECT ANIMATED OPENCLAW DASHBOARD PANEL ==="
python3 - <<'PY'
from pathlib import Path
from datetime import datetime, timezone
import re
import py_compile

ROOT = Path("/vaults/nvme0/qsb_tower_v1")
SERVER = ROOT / "src/dashboard/server.py"

ts = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
backup = SERVER.with_suffix(f".py.backup_before_openclaw_visual_panel_{ts}")
text = SERVER.read_text(encoding="utf-8")
backup.write_text(text, encoding="utf-8")
print("Backup:", backup)

snippet = r'''
<script id="qsb-openclaw-visual-panel">
(function(){
  const API = 'http://127.0.0.1:8770';
  let ocState = null;
  let animFrame = 0;

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

  async function refreshOpenClaw(){
    const status = document.getElementById('openclawStatus');
    const body = document.getElementById('openclawBody');
    if(!status || !body) return;

    try{
      const res = await fetch(API + '/api/openclaw/status?t=' + Date.now(), {cache:'no-store'});
      const data = await res.json();
      ocState = data;

      if(data.ok === false){
        status.textContent = 'error';
        status.style.color = '#ff6060';
        body.textContent = data.error || 'unknown error';
        return;
      }

      status.textContent = `${data.status} — ${data.worker_count || 0} OpenClaw sandbox observers — execution OFF`;
      status.style.color = '#4dffb0';

      const recs = data.latest_recommendations || [];
      const packets = data.latest_packets || [];
      const workers = data.workers || [];

      body.innerHTML = `
        <div style="font-size:11px;color:#6ab8ff;margin-bottom:7px">
          OpenClaw sandbox layer · visualization only · no tool execution
        </div>

        <div style="display:grid;grid-template-columns:repeat(4,1fr);gap:6px;margin-bottom:8px">
          <div class="oc-card">Observers<br><b>${data.worker_count || 0}</b></div>
          <div class="oc-card">Packets<br><b>${packets.length}</b></div>
          <div class="oc-card">Exec<br><b>OFF</b></div>
          <div class="oc-card">Dispatch<br><b>OFF</b></div>
        </div>

        <canvas id="openclawCanvas" width="480" height="135" style="width:100%;height:135px;border:1px solid rgba(255,96,96,.25);border-radius:10px;background:radial-gradient(circle at center,rgba(60,5,20,.65),rgba(4,12,24,.95));margin-bottom:8px"></canvas>

        <div class="oc-section-title">Sandbox Recommendations</div>
        ${recs.length ? recs.map(r => `
          <div style="display:grid;grid-template-columns:80px 1fr;gap:6px;padding:4px 0;border-bottom:1px solid rgba(255,96,96,.13)">
            <div style="color:#ff8080;font-weight:900">${r.instrument || ''}</div>
            <div>${r.sandbox_recommendation || 'observe_only'}</div>
          </div>
        `).join('') : '<div style="color:#ffaa50">No OpenClaw recommendations yet.</div>'}

        <div class="oc-section-title">OpenClaw Sandbox Observers</div>
        ${workers.map(w => `
          <div style="padding:4px 0;border-bottom:1px solid rgba(255,96,96,.12)">
            <span style="color:#ff8080;font-weight:900">${w.name}</span>
            <span style="color:#7faacc"> · ${w.home_floor}</span>
          </div>
        `).join('')}

        <div class="oc-section-title">Locks</div>
        <div style="color:#4dffb0;font-weight:900">
          OpenClaw execution OFF · real workers OFF · orders OFF · dispatch OFF
        </div>
      `;

      drawOpenClawCanvas();
    }catch(e){
      status.textContent = 'sidecar offline';
      status.style.color = '#ffaa50';
      body.textContent = 'Run: ./scripts/run_openclaw_visual_sidecar.sh';
    }
  }

  async function runOpenClawTick(){
    const btn = document.getElementById('openclawTickBtn');
    const status = document.getElementById('openclawStatus');
    if(!btn) return;

    btn.disabled = true;
    btn.textContent = 'Ticking…';
    if(status) status.textContent = 'running OpenClaw sandbox tick…';

    try{
      const res = await fetch(API + '/api/openclaw/tick', {method:'POST'});
      const data = await res.json();
      if(!data.ok){
        alert('OpenClaw sandbox tick error: ' + (data.error || JSON.stringify(data)));
      }
      await refreshOpenClaw();
    }catch(e){
      alert('OpenClaw sidecar offline. Run: ./scripts/run_openclaw_visual_sidecar.sh');
    }finally{
      btn.disabled = false;
      btn.textContent = 'OpenClaw Tick';
    }
  }

  function drawOpenClawCanvas(){
    const c = document.getElementById('openclawCanvas');
    if(!c) return;
    const ctx = c.getContext('2d');
    const w = c.width, h = c.height;
    ctx.clearRect(0,0,w,h);

    const floors = [
      {name:'F25', y:105},
      {name:'F30', y:82},
      {name:'F37', y:58},
      {name:'F38', y:42},
      {name:'F41', y:24}
    ];

    ctx.font = '11px monospace';
    floors.forEach(f => {
      ctx.strokeStyle = 'rgba(92,224,255,.22)';
      ctx.beginPath();
      ctx.moveTo(42, f.y);
      ctx.lineTo(w-20, f.y);
      ctx.stroke();
      ctx.fillStyle = '#6ab8ff';
      ctx.fillText(f.name, 8, f.y+4);
    });

    const lanes = [90,150,210,270,330,390,450];
    lanes.forEach(x => {
      ctx.strokeStyle = 'rgba(255,96,96,.15)';
      ctx.beginPath();
      ctx.moveTo(x, 15);
      ctx.lineTo(x, h-18);
      ctx.stroke();
    });

    const packets = (ocState && ocState.latest_packets) ? ocState.latest_packets : [];
    const t = animFrame / 60;

    packets.forEach((p, i) => {
      const lane = lanes[i % lanes.length];
      const y = 20 + ((Math.sin(t + i) + 1) / 2) * 86;
      const glow = 0.5 + ((Math.sin(t*2 + i) + 1) / 2) * 0.5;

      ctx.beginPath();
      ctx.arc(lane, y, 5 + glow*2, 0, Math.PI*2);
      ctx.fillStyle = `rgba(255,96,96,${0.55 + glow*0.35})`;
      ctx.fill();

      ctx.beginPath();
      ctx.arc(lane, y, 12, 0, Math.PI*2);
      ctx.strokeStyle = `rgba(255,96,96,${0.18 + glow*0.22})`;
      ctx.stroke();
    });

    ctx.fillStyle = '#ff8080';
    ctx.fillText('OpenClaw sandbox observers moving through lift lanes — execution locked', 62, h-8);
  }

  function animate(){
    animFrame++;
    drawOpenClawCanvas();
    requestAnimationFrame(animate);
  }

  function createPanel(){
    if(document.getElementById('openclawVisualPanel')) return;

    const style = document.createElement('style');
    style.textContent = `
      .oc-card{padding:6px 8px;border:1px solid rgba(255,96,96,.22);border-radius:8px;background:rgba(45,5,15,.70);color:#d8eaff;font-size:11px}
      .oc-card b{color:#ff8080;font-size:13px}
      .oc-section-title{color:#ff8080;font-weight:900;font-size:11px;margin:9px 0 4px 0;letter-spacing:.3px}
    `;
    document.head.appendChild(style);

    const panel = el('div', {
      id:'openclawVisualPanel',
      style:[
        'position:fixed',
        'right:20px',
        'top:86px',
        'width:500px',
        'height:430px',
        'z-index:99994',
        'display:flex',
        'flex-direction:column',
        'background:rgba(4,12,24,.96)',
        'border:1px solid rgba(255,96,96,.45)',
        'box-shadow:0 0 24px rgba(255,96,96,.16)',
        'border-radius:14px',
        'overflow:hidden',
        'font-family:Segoe UI,system-ui,Arial,sans-serif',
        'font-size:12px'
      ].join(';')
    });

    const header = el('div', {
      style:'display:flex;justify-content:space-between;align-items:center;padding:10px 12px;background:rgba(50,5,15,.95);border-bottom:1px solid rgba(255,96,96,.35)'
    });

    const title = el('div');
    title.innerHTML = '<div style="font-weight:900;color:#ff8080">OpenClaw Sandbox Visual Layer</div><div id="openclawStatus" style="font-size:11px;color:#ffaa50">checking…</div>';

    const controls = el('div', {style:'display:flex;gap:6px'});
    const refresh = el('button', {style:'padding:5px 8px;border-radius:8px;background:#071528;color:#d8eaff;border:1px solid #1a3a5c;cursor:pointer'}, 'Refresh');
    const tick = el('button', {id:'openclawTickBtn', style:'padding:5px 8px;border-radius:8px;background:#581a22;color:#ffb0b0;border:1px solid rgba(255,96,96,.5);font-weight:900;cursor:pointer'}, 'OpenClaw Tick');
    const hide = el('button', {style:'padding:5px 8px;border-radius:8px;background:#071528;color:#d8eaff;border:1px solid #1a3a5c;cursor:pointer'}, 'Hide');

    refresh.onclick = refreshOpenClaw;
    tick.onclick = runOpenClawTick;
    hide.onclick = () => {
      const b = document.getElementById('openclawBody');
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
      id:'openclawBody',
      style:'padding:10px;overflow:auto;flex:1;color:#d8eaff;background:linear-gradient(180deg,rgba(50,5,15,.45),rgba(4,12,24,.92))'
    });

    panel.appendChild(header);
    panel.appendChild(body);
    document.body.appendChild(panel);

    refreshOpenClaw();
    animate();
  }

  if(document.readyState === 'loading') document.addEventListener('DOMContentLoaded', createPanel);
  else createPanel();

  setInterval(refreshOpenClaw, 10000);
})();
</script>
'''

text = re.sub(r'\n?<script id="qsb-openclaw-visual-panel">.*?</script>\n?', '\n', text, flags=re.S)

if "</body>" in text:
    text = text.replace("</body>", snippet + "\n</body>", 1)
elif "</html>" in text:
    text = text.replace("</html>", snippet + "\n</html>", 1)
else:
    raise SystemExit("No </body> or </html> found.")

SERVER.write_text(text, encoding="utf-8")
py_compile.compile(str(SERVER), doraise=True)
print("Installed OpenClaw animated dashboard panel.")
PY

echo
echo "=== CREATE TEST ==="
cat > tests/test_openclaw_sandbox_visual_layer_v1.py <<'PY'
import sys
import py_compile
from pathlib import Path

ROOT = Path("/vaults/nvme0/qsb_tower_v1")
sys.path.insert(0, str(ROOT / "src"))

for rel in [
    "src/tower/openclaw_sandbox_layer.py",
    "src/tower/openclaw_visual_sidecar.py",
    "src/dashboard/server.py"
]:
    py_compile.compile(str(ROOT / rel), doraise=True)

from tower.openclaw_sandbox_layer import OpenClawSandboxLayer

s = OpenClawSandboxLayer().status()

assert s["layer"] == "openclaw_sandbox_visual_layer_v1"
assert s["openclaw_sandbox_enabled"] is True
assert s["openclaw_visualization_enabled"] is True
assert s["openclaw_execution_enabled"] is False
assert s["locks"]["openclaw_execution_enabled"] is False
assert s["locks"]["worker_execution_enabled"] is False
assert s["locks"]["autonomous_dispatch_enabled"] is False
assert s["locks"]["order_execution_enabled"] is False
assert s["locks"]["practice_order_execution_enabled"] is False
assert s["locks"]["direct_provider_access"] is False

server = (ROOT / "src/dashboard/server.py").read_text(encoding="utf-8")
assert "qsb-openclaw-visual-panel" in server
assert "openclawVisualPanel" in server
assert "api/openclaw/status" in server
assert "api/openclaw/tick" in server

print("OPENCLAW SANDBOX VISUAL LAYER V1 TEST PASSED")
print("  OpenClaw sandbox enabled:", s["openclaw_sandbox_enabled"])
print("  OpenClaw execution:", s["openclaw_execution_enabled"])
print("  Worker count:", s["worker_count"])
PY

python3 tests/test_openclaw_sandbox_visual_layer_v1.py

echo
echo "=== START OPENCLAW VISUAL SIDECAR ==="
./scripts/stop_openclaw_visual_sidecar.sh || true
./scripts/run_openclaw_visual_sidecar.sh

echo
echo "=== RUN FIRST OPENCLAW SANDBOX TICK ==="
curl -s -X POST http://127.0.0.1:8770/api/openclaw/tick | python3 -m json.tool | head -180

echo
echo "=== RESTART DASHBOARD ==="
./stop.sh
./run.sh
./status.sh

echo
echo "======================================================"
echo "  OPENCLAW SANDBOX VISUAL LAYER V1 COMPLETE"
echo "======================================================"
echo "Open:"
echo "  http://127.0.0.1:8765/?v=openclaw-sandbox"
echo
echo "Hard refresh with Ctrl+Shift+R."
echo "======================================================"
