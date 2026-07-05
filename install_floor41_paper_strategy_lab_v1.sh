#!/usr/bin/env bash
set -euo pipefail

cd /vaults/nvme0/qsb_tower_v1
export PYTHONPATH=/vaults/nvme0/qsb_tower_v1/src

TS="$(date -u +%Y%m%dT%H%M%SZ)"

echo "======================================================"
echo "  QSB Tower V1.3 — Floor 41 Paper Strategy Lab V1"
echo "======================================================"
echo "Mode: OANDA practice data + paper-only strategy analysis"
echo "No real orders. No practice orders. No workers. No autonomous dispatch."

mkdir -p data/registries data/runtime data/logs data/backups scripts tests src/tower

echo
echo "=== BACKUPS ==="
for f in src/dashboard/server.py src/tower/oanda_trading_floor.py src/tower/oanda_gateway.py; do
  [ -f "$f" ] && cp -f "$f" "data/backups/$(basename "$f").backup_before_floor41_paper_lab_${TS}" || true
done

echo
echo "=== WRITE PAPER STRATEGY POLICY ==="
cat > data/registries/oanda_paper_strategy_policy.json <<'JSON'
{
  "policy": "floor_41_oanda_paper_strategy_lab_v1",
  "version": "1.0",
  "floor": "floor_41",
  "department": "OANDA Trading Floor",
  "mode": "paper_strategy_lab",
  "environment": "practice",
  "default_instruments": ["EUR_USD", "GBP_USD", "USD_JPY"],
  "signal_modes": ["observe", "long_bias", "short_bias", "no_trade"],
  "paper_trading_enabled": true,
  "paper_signal_generation_enabled": true,
  "local_model_commentary_enabled": true,
  "live_trading_enabled": false,
  "order_execution_enabled": false,
  "practice_order_execution_enabled": false,
  "worker_execution_enabled": false,
  "provider_execution_enabled": false,
  "external_provider_execution_enabled": false,
  "openclaw_execution_enabled": false,
  "autonomous_dispatch_enabled": false,
  "live_dispatch_enabled": false,
  "direct_provider_access": false,
  "risk_mode": "observe_and_simulate_only",
  "max_paper_risk_per_signal_pct": 0.25,
  "notes": "Paper Strategy Lab generates observations and simulated signals only. It must not place live or practice orders."
}
JSON

echo
echo "=== CREATE PAPER STRATEGY LAB MODULE ==="
cat > src/tower/oanda_paper_strategy_lab.py <<'PY'
#!/usr/bin/env python3
"""
QSB Tower V1.3 — Floor 41 OANDA Paper Strategy Lab V1

Creates paper-only market metrics and simulated signal candidates from OANDA
practice pricing snapshots.

No order placement.
No live trading.
No worker dispatch.
No external provider execution.
"""

from pathlib import Path
from datetime import datetime, timezone
import json
import os
import statistics

from tower.oanda_trading_floor import OANDATradingFloor

ROOT = Path("/vaults/nvme0/qsb_tower_v1")
REG = ROOT / "data/registries"
RUNTIME = ROOT / "data/runtime"
LOG = ROOT / "data/logs/oanda_paper_strategy_lab.jsonl"

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
    "direct_provider_access": False,
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
        if not k:
            continue
        os.environ.setdefault(k.strip(), v.strip().strip("'").strip('"'))


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


def append_log(record):
    LOG.parent.mkdir(parents=True, exist_ok=True)
    with LOG.open("a", encoding="utf-8") as f:
        f.write(json.dumps(record) + "\n")


def first_float(items, key="price"):
    try:
        return float(items[0][key])
    except Exception:
        return None


def pip_size(instrument):
    return 0.01 if instrument and instrument.endswith("_JPY") else 0.0001


def classify_signal(metric):
    """
    Conservative paper-only heuristic.
    This is not a trade recommendation; it is a simulated research label.
    """
    spread_pips = metric.get("spread_pips")
    depth_bid = metric.get("top_bid_liquidity") or 0
    depth_ask = metric.get("top_ask_liquidity") or 0
    imbalance = metric.get("top_liquidity_imbalance") or 0

    if spread_pips is None:
        return "no_trade", "missing spread"

    if spread_pips > 2.0:
        return "no_trade", "spread too wide"

    if depth_bid + depth_ask <= 0:
        return "observe", "insufficient top-book liquidity"

    if imbalance > 0.25 and spread_pips <= 1.5:
        return "long_bias", "top-book bid liquidity exceeds ask liquidity"

    if imbalance < -0.25 and spread_pips <= 1.5:
        return "short_bias", "top-book ask liquidity exceeds bid liquidity"

    return "observe", "balanced book / no clear paper edge"


def metric_from_price(p):
    instrument = p.get("instrument")
    bids = p.get("bids") or []
    asks = p.get("asks") or []

    bid = first_float(bids)
    ask = first_float(asks)
    mid = (bid + ask) / 2 if bid is not None and ask is not None else None
    spread = ask - bid if bid is not None and ask is not None else None
    ps = pip_size(instrument)
    spread_pips = spread / ps if spread is not None and ps else None

    top_bid_liquidity = bids[0].get("liquidity", 0) if bids else 0
    top_ask_liquidity = asks[0].get("liquidity", 0) if asks else 0
    total_top = top_bid_liquidity + top_ask_liquidity
    imbalance = ((top_bid_liquidity - top_ask_liquidity) / total_top) if total_top else 0

    metric = {
        "instrument": instrument,
        "time": p.get("time"),
        "status": p.get("status"),
        "tradeable": p.get("tradeable"),
        "bid": bid,
        "ask": ask,
        "mid": mid,
        "spread": spread,
        "spread_pips": spread_pips,
        "top_bid_liquidity": top_bid_liquidity,
        "top_ask_liquidity": top_ask_liquidity,
        "top_liquidity_imbalance": imbalance,
        "depth_levels_bid": len(bids),
        "depth_levels_ask": len(asks)
    }

    signal, reason = classify_signal(metric)
    metric["paper_signal"] = signal
    metric["paper_reason"] = reason
    return metric


class OANDAPaperStrategyLab:
    def __init__(self):
        load_local_env_file()
        self.policy = load_json(REG / "oanda_paper_strategy_policy.json", {})

    def run(self, instruments=None):
        if instruments is None:
            instruments = self.policy.get("default_instruments") or ["EUR_USD", "GBP_USD", "USD_JPY"]

        if isinstance(instruments, str):
            instruments = [x.strip() for x in instruments.split(",") if x.strip()]

        snapshot = OANDATradingFloor().snapshot(",".join(instruments))
        account = snapshot.get("account_summary", {}).get("account", {})
        prices = snapshot.get("pricing", {}).get("prices", []) if isinstance(snapshot.get("pricing"), dict) else []

        metrics = [metric_from_price(p) for p in prices]
        spreads = [m["spread_pips"] for m in metrics if isinstance(m.get("spread_pips"), (int, float))]

        counts = {}
        for m in metrics:
            counts[m["paper_signal"]] = counts.get(m["paper_signal"], 0) + 1

        lab = {
            "ts": datetime.now(timezone.utc).isoformat(),
            "floor": "floor_41",
            "department": "OANDA Trading Floor",
            "lab": "Paper Strategy Lab V1",
            "mode": "practice_read_only_paper_simulation",
            "account": {
                "id": account.get("id"),
                "currency": account.get("currency"),
                "NAV": account.get("NAV"),
                "balance": account.get("balance"),
                "openTradeCount": account.get("openTradeCount"),
                "openPositionCount": account.get("openPositionCount"),
                "marginAvailable": account.get("marginAvailable")
            },
            "instruments": metrics,
            "summary": {
                "instrument_count": len(metrics),
                "tradeable_count": sum(1 for m in metrics if m.get("tradeable") is True),
                "avg_spread_pips": statistics.mean(spreads) if spreads else None,
                "signal_counts": counts,
                "errors": snapshot.get("errors", [])
            },
            "locks": LOCKS,
            "paper_only": True,
            "not_financial_advice": True
        }

        write_json(REG / "oanda_paper_strategy_latest.json", lab)
        write_json(RUNTIME / "oanda_paper_strategy_latest.json", lab)
        append_log(lab)
        return lab

    def dashboard(self):
        latest = load_json(REG / "oanda_paper_strategy_latest.json", {})
        status = load_json(REG / "oanda_trading_floor_status.json", {})

        return {
            "floor": "floor_41",
            "department": "OANDA Trading Floor",
            "panel": "Paper Strategy Lab",
            "status": "healthy" if latest and not latest.get("summary", {}).get("errors") else "waiting",
            "latest_ts": latest.get("ts"),
            "mode": "practice_read_only_paper_simulation",
            "paper_trading_enabled": True,
            "paper_signal_generation_enabled": True,
            "local_model_commentary_enabled": True,
            "summary": latest.get("summary", {}),
            "instruments": latest.get("instruments", []),
            "locks": LOCKS,
            "not_financial_advice": True
        }


def run(instruments=None):
    return OANDAPaperStrategyLab().run(instruments)


def dashboard():
    return OANDAPaperStrategyLab().dashboard()


if __name__ == "__main__":
    print(json.dumps(run(), indent=2))
PY

echo
echo "=== CREATE PAPER LAB SCRIPTS ==="
cat > scripts/oanda_paper_strategy_lab.sh <<'SH2'
#!/usr/bin/env bash
set -euo pipefail
cd /vaults/nvme0/qsb_tower_v1
export PYTHONPATH=/vaults/nvme0/qsb_tower_v1/src

if [ -f .env.oanda_practice ]; then
  source .env.oanda_practice
fi

INSTRUMENTS="${1:-EUR_USD,GBP_USD,USD_JPY}"

python3 - <<PY
from tower.oanda_paper_strategy_lab import OANDAPaperStrategyLab
import json
print(json.dumps(OANDAPaperStrategyLab().run("$INSTRUMENTS"), indent=2))
PY
SH2
chmod +x scripts/oanda_paper_strategy_lab.sh

cat > scripts/oanda_paper_strategy_status.sh <<'SH2'
#!/usr/bin/env bash
set -euo pipefail
cd /vaults/nvme0/qsb_tower_v1
export PYTHONPATH=/vaults/nvme0/qsb_tower_v1/src

python3 - <<'PY'
from tower.oanda_paper_strategy_lab import OANDAPaperStrategyLab
import json
print(json.dumps(OANDAPaperStrategyLab().dashboard(), indent=2))
PY
SH2
chmod +x scripts/oanda_paper_strategy_status.sh

cat > scripts/oanda_paper_strategy_kernel_commentary.sh <<'SH2'
#!/usr/bin/env bash
set -euo pipefail
cd /vaults/nvme0/qsb_tower_v1
export PYTHONPATH=/vaults/nvme0/qsb_tower_v1/src

if [ -f .env.oanda_practice ]; then
  source .env.oanda_practice
fi

INSTRUMENTS="${1:-EUR_USD,GBP_USD,USD_JPY}"

./scripts/oanda_paper_strategy_lab.sh "$INSTRUMENTS" > data/runtime/oanda_paper_strategy_lab_output.json

PROMPT="$(cat data/runtime/oanda_paper_strategy_lab_output.json)

Kernel, review this Floor 41 OANDA Paper Strategy Lab output.
This is paper research only.
Do not place orders.
Do not enable live trading.
Do not enable practice order execution.
Do not enable workers.
Do not enable OpenClaw.
Do not enable autonomous dispatch.
Give a concise tactical read, risk warning, and what to observe next."

./scripts/qsb_kernel_chat.sh "$PROMPT"
SH2
chmod +x scripts/oanda_paper_strategy_kernel_commentary.sh

echo
echo "=== CREATE OANDA FLOOR 41 SIDECAR ==="
cat > src/tower/oanda_floor41_sidecar.py <<'PY'
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
PORT = 8767


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
        q = urllib.parse.parse_qs(parsed.query)
        instruments = q.get("instruments", ["EUR_USD,GBP_USD,USD_JPY"])[0]

        try:
            if parsed.path == "/api/floor41/status":
                from tower.oanda_paper_strategy_lab import OANDAPaperStrategyLab
                json_response(self, OANDAPaperStrategyLab().dashboard())
                return

            if parsed.path == "/api/floor41/run":
                from tower.oanda_paper_strategy_lab import OANDAPaperStrategyLab
                json_response(self, OANDAPaperStrategyLab().run(instruments))
                return

            json_response(self, {"ok": False, "error": "not found", "path": parsed.path}, 404)
        except Exception as exc:
            json_response(self, {"ok": False, "error": str(exc)}, 500)

    def do_POST(self):
        load_local_env_file()
        parsed = urllib.parse.urlparse(self.path)

        if parsed.path != "/api/floor41/commentary":
            json_response(self, {"ok": False, "error": "not found", "path": parsed.path}, 404)
            return

        try:
            length = int(self.headers.get("Content-Length", "0"))
            body = json.loads(self.rfile.read(length).decode("utf-8") or "{}")
            instruments = body.get("instruments") or "EUR_USD,GBP_USD,USD_JPY"

            from tower.oanda_paper_strategy_lab import OANDAPaperStrategyLab
            from tower.kernel_dialogue_adapter import ask_kernel

            lab = OANDAPaperStrategyLab().run(instruments)
            prompt = json.dumps(lab, indent=2) + """

Kernel, review this Floor 41 OANDA Paper Strategy Lab output.
This is paper research only.
Do not place orders.
Do not enable live trading.
Do not enable practice order execution.
Do not enable workers.
Do not enable OpenClaw.
Do not enable autonomous dispatch.
Give a concise tactical read, risk warning, and what to observe next.
"""
            result = ask_kernel(prompt, prefer_local_model=True)
            json_response(self, {
                "ok": True,
                "ts": datetime.now(timezone.utc).isoformat(),
                "lab": lab,
                "commentary": result,
                "locks": lab.get("locks", {})
            })
        except Exception as exc:
            json_response(self, {"ok": False, "error": str(exc)}, 500)


def main():
    print(f"Floor 41 OANDA sidecar running at http://{HOST}:{PORT}")
    ThreadingHTTPServer((HOST, PORT), Handler).serve_forever()


if __name__ == "__main__":
    main()
PY

python3 -m py_compile src/tower/oanda_floor41_sidecar.py

cat > scripts/run_oanda_floor41_sidecar.sh <<'SH2'
#!/usr/bin/env bash
set -euo pipefail
cd /vaults/nvme0/qsb_tower_v1
export PYTHONPATH=/vaults/nvme0/qsb_tower_v1/src

PIDFILE="data/runtime/oanda_floor41_sidecar.pid"
LOGFILE="data/logs/oanda_floor41_sidecar.out"

if [ -f "$PIDFILE" ] && kill -0 "$(cat "$PIDFILE")" 2>/dev/null; then
  echo "Floor 41 OANDA sidecar already running: PID $(cat "$PIDFILE")"
  exit 0
fi

nohup python3 src/tower/oanda_floor41_sidecar.py > "$LOGFILE" 2>&1 &
echo $! > "$PIDFILE"
sleep 1

echo "Floor 41 OANDA sidecar started: PID $(cat "$PIDFILE")"
echo "Status: http://127.0.0.1:8767/api/floor41/status"
SH2
chmod +x scripts/run_oanda_floor41_sidecar.sh

cat > scripts/stop_oanda_floor41_sidecar.sh <<'SH2'
#!/usr/bin/env bash
set -euo pipefail
cd /vaults/nvme0/qsb_tower_v1

PIDFILE="data/runtime/oanda_floor41_sidecar.pid"

if [ -f "$PIDFILE" ]; then
  PID="$(cat "$PIDFILE")"
  if kill -0 "$PID" 2>/dev/null; then
    kill "$PID" || true
    sleep 1
  fi
  rm -f "$PIDFILE"
fi

echo "Floor 41 OANDA sidecar stopped."
SH2
chmod +x scripts/stop_oanda_floor41_sidecar.sh

echo
echo "=== INJECT DASHBOARD FLOOR 41 PANEL ==="
python3 - <<'PY'
from pathlib import Path
from datetime import datetime, timezone
import re
import py_compile

ROOT = Path("/vaults/nvme0/qsb_tower_v1")
SERVER = ROOT / "src/dashboard/server.py"

ts = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
backup = SERVER.with_suffix(f".py.backup_before_floor41_dashboard_panel_{ts}")
text = SERVER.read_text(encoding="utf-8")
backup.write_text(text, encoding="utf-8")
print("Backup:", backup)

snippet = r'''
<script id="qsb-floor41-oanda-panel">
(function(){
  const API = 'http://127.0.0.1:8767';

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

  function priceRows(items){
    if(!items || !items.length) return '<div style="color:#ffaa50">No paper metrics yet.</div>';
    return items.map(m => `
      <div style="display:grid;grid-template-columns:80px 1fr 1fr 1fr;gap:6px;padding:5px 0;border-bottom:1px solid rgba(77,255,176,.12)">
        <div style="color:#4dffb0;font-weight:800">${m.instrument || ''}</div>
        <div>mid: <b>${m.mid ?? '-'}</b></div>
        <div>spread: <b>${m.spread_pips != null ? m.spread_pips.toFixed(2) + ' pips' : '-'}</b></div>
        <div style="color:#ffc940">${m.paper_signal || 'observe'}</div>
      </div>
    `).join('');
  }

  async function refreshFloor41(run=false){
    const status = document.getElementById('floor41Status');
    const body = document.getElementById('floor41Body');
    if(!status || !body) return;

    try{
      const url = API + (run ? '/api/floor41/run' : '/api/floor41/status') + '?instruments=EUR_USD,GBP_USD,USD_JPY&t=' + Date.now();
      const res = await fetch(url, {cache:'no-store'});
      const data = await res.json();

      if(data.ok === false){
        status.textContent = 'error';
        status.style.color = '#ff6060';
        body.textContent = data.error || 'unknown error';
        return;
      }

      const instruments = data.instruments || [];
      const summary = data.summary || {};
      status.textContent = `${data.status || 'healthy'} — paper only — ${summary.instrument_count || instruments.length || 0} pairs`;
      status.style.color = '#4dffb0';

      body.innerHTML = `
        <div style="font-size:11px;color:#6ab8ff;margin-bottom:6px">
          Floor 41 · OANDA Practice · Paper Strategy Lab · no orders · locks closed
        </div>
        <div style="display:grid;grid-template-columns:repeat(3,1fr);gap:6px;margin-bottom:8px">
          <div class="f41-card">Avg spread<br><b>${summary.avg_spread_pips != null ? summary.avg_spread_pips.toFixed(2) + ' pips' : '-'}</b></div>
          <div class="f41-card">Tradeable<br><b>${summary.tradeable_count ?? '-'}</b></div>
          <div class="f41-card">Signals<br><b>${JSON.stringify(summary.signal_counts || {})}</b></div>
        </div>
        ${priceRows(instruments)}
      `;
    }catch(e){
      status.textContent = 'sidecar offline';
      status.style.color = '#ffaa50';
      body.textContent = 'Run: ./scripts/run_oanda_floor41_sidecar.sh';
    }
  }

  async function askCommentary(){
    const out = document.getElementById('floor41Commentary');
    const btn = document.getElementById('floor41CommentaryBtn');
    if(!out || !btn) return;

    btn.disabled = true;
    btn.textContent = 'Thinking…';
    out.textContent = 'Kernel reviewing Floor 41 paper metrics…';

    try{
      const res = await fetch(API + '/api/floor41/commentary', {
        method:'POST',
        headers:{'Content-Type':'application/json'},
        body:JSON.stringify({instruments:'EUR_USD,GBP_USD,USD_JPY'})
      });
      const data = await res.json();
      if(data.ok){
        out.textContent = data.commentary?.reply || JSON.stringify(data.commentary, null, 2);
        refreshFloor41(false);
      }else{
        out.textContent = 'Error: ' + (data.error || JSON.stringify(data));
      }
    }catch(e){
      out.textContent = 'Floor 41 sidecar offline. Run: ./scripts/run_oanda_floor41_sidecar.sh';
    }finally{
      btn.disabled = false;
      btn.textContent = 'Kernel Commentary';
    }
  }

  function createPanel(){
    if(document.getElementById('floor41OandaPanel')) return;

    const style = document.createElement('style');
    style.textContent = `
      .f41-card{padding:6px 8px;border:1px solid rgba(92,224,255,.18);border-radius:8px;background:rgba(6,17,32,.85);color:#7faacc;font-size:11px}
      .f41-card b{color:#4dffb0;font-size:12px}
    `;
    document.head.appendChild(style);

    const panel = el('div', {
      id:'floor41OandaPanel',
      style:[
        'position:fixed',
        'left:72px',
        'bottom:58px',
        'width:520px',
        'height:390px',
        'z-index:99997',
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
    title.innerHTML = '<div style="font-weight:900;color:#ffc940">Floor 41 — OANDA Paper Strategy Lab</div><div id="floor41Status" style="font-size:11px;color:#ffaa50">checking…</div>';

    const controls = el('div', {style:'display:flex;gap:6px'});
    const refresh = el('button', {style:'padding:5px 8px;border-radius:8px;background:#071528;color:#d8eaff;border:1px solid #1a3a5c;cursor:pointer'}, 'Refresh');
    const run = el('button', {style:'padding:5px 8px;border-radius:8px;background:#0a5032;color:#4dffb0;border:1px solid rgba(77,255,176,.5);cursor:pointer'}, 'Run');
    const hide = el('button', {style:'padding:5px 8px;border-radius:8px;background:#071528;color:#d8eaff;border:1px solid #1a3a5c;cursor:pointer'}, 'Hide');

    refresh.onclick = () => refreshFloor41(false);
    run.onclick = () => refreshFloor41(true);
    hide.onclick = () => {
      const b = document.getElementById('floor41PanelBody');
      const hidden = b.style.display === 'none';
      b.style.display = hidden ? 'flex' : 'none';
      panel.style.height = hidden ? '390px' : '52px';
      hide.textContent = hidden ? 'Hide' : 'Show';
    };

    controls.appendChild(refresh);
    controls.appendChild(run);
    controls.appendChild(hide);
    header.appendChild(title);
    header.appendChild(controls);

    const bodyWrap = el('div', {id:'floor41PanelBody', style:'display:flex;flex-direction:column;flex:1;min-height:0'});
    const body = el('div', {id:'floor41Body', style:'padding:10px;overflow:auto;flex:1;color:#d8eaff'});
    const commentary = el('div', {
      id:'floor41Commentary',
      style:'height:95px;overflow:auto;margin:0 10px 10px 10px;padding:8px;border:1px solid rgba(77,255,176,.25);border-radius:9px;background:rgba(5,35,25,.55);color:#d8eaff;white-space:pre-wrap'
    }, 'Kernel commentary will appear here.');

    const footer = el('div', {style:'display:flex;justify-content:space-between;align-items:center;padding:0 10px 10px 10px'});
    const lock = el('div', {style:'color:#4dffb0;font-weight:800;font-size:11px'}, 'PAPER ONLY · ORDERS OFF · WORKERS OFF');
    const commentBtn = el('button', {
      id:'floor41CommentaryBtn',
      style:'padding:7px 10px;border-radius:9px;background:rgba(10,80,50,.8);color:#4dffb0;border:1px solid rgba(77,255,176,.5);font-weight:900;cursor:pointer'
    }, 'Kernel Commentary');
    commentBtn.onclick = askCommentary;

    footer.appendChild(lock);
    footer.appendChild(commentBtn);

    bodyWrap.appendChild(body);
    bodyWrap.appendChild(commentary);
    bodyWrap.appendChild(footer);
    panel.appendChild(header);
    panel.appendChild(bodyWrap);
    document.body.appendChild(panel);

    refreshFloor41(false);
  }

  if(document.readyState === 'loading') document.addEventListener('DOMContentLoaded', createPanel);
  else createPanel();

  setInterval(() => refreshFloor41(false), 10000);
})();
</script>
'''

text = re.sub(r'\n?<script id="qsb-floor41-oanda-panel">.*?</script>\n?', '\n', text, flags=re.S)

if "</body>" in text:
    text = text.replace("</body>", snippet + "\n</body>", 1)
elif "</html>" in text:
    text = text.replace("</html>", snippet + "\n</html>", 1)
else:
    raise SystemExit("No </body> or </html> found.")

SERVER.write_text(text, encoding="utf-8")
py_compile.compile(str(SERVER), doraise=True)
print("Installed Floor 41 dashboard panel.")
PY

echo
echo "=== TEST PAPER STRATEGY LAB ==="
python3 -m py_compile src/tower/oanda_paper_strategy_lab.py
python3 -m py_compile src/tower/oanda_floor41_sidecar.py

cat > tests/test_oanda_paper_strategy_lab_v1.py <<'PY'
import sys
import py_compile
from pathlib import Path

ROOT = Path("/vaults/nvme0/qsb_tower_v1")
sys.path.insert(0, str(ROOT / "src"))

py_compile.compile(str(ROOT / "src/tower/oanda_paper_strategy_lab.py"), doraise=True)

from tower.oanda_paper_strategy_lab import OANDAPaperStrategyLab

d = OANDAPaperStrategyLab().dashboard()

assert d["floor"] == "floor_41"
assert d["department"] == "OANDA Trading Floor"
assert d["paper_trading_enabled"] is True
assert d["paper_signal_generation_enabled"] is True
assert d["locks"]["live_trading_enabled"] is False
assert d["locks"]["order_execution_enabled"] is False
assert d["locks"]["practice_order_execution_enabled"] is False
assert d["locks"]["worker_execution_enabled"] is False
assert d["locks"]["provider_execution_enabled"] is False
assert d["locks"]["openclaw_execution_enabled"] is False
assert d["locks"]["autonomous_dispatch_enabled"] is False

print("OANDA PAPER STRATEGY LAB V1 TEST PASSED")
print("  Status:", d["status"])
print("  Latest:", d["latest_ts"])
PY

python3 tests/test_oanda_paper_strategy_lab_v1.py

echo
echo "=== START SIDECAR AND RUN FIRST LAB ==="
./scripts/stop_oanda_floor41_sidecar.sh || true
./scripts/run_oanda_floor41_sidecar.sh

./scripts/oanda_paper_strategy_lab.sh EUR_USD,GBP_USD,USD_JPY | head -120
./scripts/oanda_paper_strategy_kernel_commentary.sh EUR_USD,GBP_USD,USD_JPY

echo
echo "=== RESTART DASHBOARD ==="
./stop.sh
./run.sh
./status.sh

echo
echo "Open:"
echo "  http://127.0.0.1:8765/?v=floor41-paper-lab"
