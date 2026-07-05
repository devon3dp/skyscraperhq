#!/usr/bin/env bash
set -euo pipefail

cd /vaults/nvme0/qsb_tower_v1
export PYTHONPATH=/vaults/nvme0/qsb_tower_v1/src

TS="$(date -u +%Y%m%dT%H%M%SZ)"

echo "======================================================"
echo "  QSB Tower V1.3 — Strategy Intelligence Panel Only"
echo "======================================================"
echo "Dashboard panel only. No worker patch. No AutoLoop patch. No orders."

mkdir -p data/backups

echo
echo "=== BACKUP DASHBOARD SERVER ==="
cp -f src/dashboard/server.py "data/backups/server.py.backup_before_strategy_panel_only_${TS}"

echo
echo "=== VERIFY STRATEGY SIDECAR WORKS ==="
./scripts/run_strategy_intelligence_sidecar.sh || true
curl -s http://127.0.0.1:8771/api/strategy/status | python3 -m json.tool | head -80

echo
echo "=== INJECT STRATEGY PANEL ONLY ==="
python3 - <<'PY'
from pathlib import Path
from datetime import datetime, timezone
import re
import py_compile

p = Path("src/dashboard/server.py")
text = p.read_text(encoding="utf-8")

backup = p.with_suffix(
    f".py.backup_before_strategy_panel_only_{datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%SZ')}"
)
backup.write_text(text, encoding="utf-8")
print("Backup:", backup)

# Remove any previous/partial strategy panel block.
text = re.sub(
    r'\n?<script id="qsb-strategy-intelligence-panel">.*?</script>\n?',
    '\n',
    text,
    flags=re.S
)

snippet = r'''
<script id="qsb-strategy-intelligence-panel">
(function(){
  const API = 'http://127.0.0.1:8771';

  function fmt(v, d=2){
    if(v === null || v === undefined || Number.isNaN(Number(v))) return '-';
    return Number(v).toFixed(d);
  }

  function sigColor(sig){
    if(sig === 'long_bias') return '#4dffb0';
    if(sig === 'short_bias') return '#ff8080';
    if(sig === 'no_trade') return '#ffaa50';
    return '#6ab8ff';
  }

  function makePanel(){
    if(document.getElementById('strategyIntelligencePanel')) return;

    const panel = document.createElement('div');
    panel.id = 'strategyIntelligencePanel';
    panel.style.cssText = [
      'position:fixed',
      'left:72px',
      'top:86px',
      'width:610px',
      'height:320px',
      'z-index:100008',
      'display:flex',
      'flex-direction:column',
      'background:rgba(4,12,24,.97)',
      'border:1px solid rgba(92,224,255,.55)',
      'box-shadow:0 0 24px rgba(92,224,255,.18)',
      'border-radius:14px',
      'overflow:hidden',
      'font-family:Segoe UI,system-ui,Arial,sans-serif',
      'font-size:12px',
      'color:#d8eaff'
    ].join(';');

    panel.innerHTML = `
      <div style="display:flex;justify-content:space-between;align-items:center;padding:10px 12px;background:rgba(5,35,45,.95);border-bottom:1px solid rgba(92,224,255,.35)">
        <div>
          <div style="font-weight:900;color:#5ce0ff">Strategy Intelligence</div>
          <div id="siPanelStatus" style="font-size:11px;color:#ffaa50">checking...</div>
        </div>
        <div style="display:flex;gap:6px">
          <button id="siPanelRefresh" style="padding:5px 8px;border-radius:8px;background:#071528;color:#d8eaff;border:1px solid #1a3a5c;cursor:pointer">Refresh</button>
          <button id="siPanelRun" style="padding:5px 8px;border-radius:8px;background:#053a45;color:#aaf5ff;border:1px solid rgba(92,224,255,.5);font-weight:900;cursor:pointer">Run Intelligence</button>
          <button id="siPanelHide" style="padding:5px 8px;border-radius:8px;background:#071528;color:#d8eaff;border:1px solid #1a3a5c;cursor:pointer">Hide</button>
        </div>
      </div>
      <div id="siPanelBody" style="padding:10px;overflow:auto;flex:1;background:linear-gradient(180deg,rgba(5,35,45,.45),rgba(4,12,24,.92))">
        Waiting for strategy sidecar...
      </div>
    `;

    document.body.appendChild(panel);

    document.getElementById('siPanelRefresh').onclick = refreshStrategy;
    document.getElementById('siPanelRun').onclick = runStrategy;
    document.getElementById('siPanelHide').onclick = function(){
      const body = document.getElementById('siPanelBody');
      const hidden = body.style.display === 'none';
      body.style.display = hidden ? 'block' : 'none';
      panel.style.height = hidden ? '320px' : '52px';
      this.textContent = hidden ? 'Hide' : 'Show';
    };

    refreshStrategy();
  }

  async function refreshStrategy(){
    const status = document.getElementById('siPanelStatus');
    const body = document.getElementById('siPanelBody');
    if(!status || !body) return;

    try{
      const res = await fetch(API + '/api/strategy/status?t=' + Date.now(), {cache:'no-store'});
      const data = await res.json();

      if(data.ok === false){
        status.textContent = 'error';
        status.style.color = '#ff6060';
        body.textContent = data.error || 'unknown error';
        return;
      }

      const counts = data.signal_counts || {};
      status.textContent = `${data.status} — long ${counts.long_bias || 0} / short ${counts.short_bias || 0} / observe ${counts.observe || 0} / no_trade ${counts.no_trade || 0}`;
      status.style.color = '#4dffb0';

      const rows = (data.results || []).map(r => `
        <div style="display:grid;grid-template-columns:75px 85px 70px 85px 1fr;gap:6px;padding:5px 0;border-bottom:1px solid rgba(92,224,255,.12)">
          <div style="font-weight:900;color:#5ce0ff">${r.instrument || ''}</div>
          <div style="font-weight:900;color:${sigColor(r.paper_signal)}">${r.paper_signal || 'observe'}</div>
          <div>${fmt(r.confidence,2)}</div>
          <div>${fmt(r.momentum_10_pips,2)} pips</div>
          <div style="color:#9fb0cc">${r.reason || ''}</div>
        </div>
      `).join('');

      const locks = data.locks || {};

      body.innerHTML = `
        <div style="font-size:11px;color:#6ab8ff;margin-bottom:7px">
          Candle/history intelligence · standalone sidecar · paper-only · no execution
        </div>

        <div style="display:grid;grid-template-columns:repeat(4,1fr);gap:6px;margin-bottom:8px">
          <div style="padding:6px;border:1px solid rgba(92,224,255,.25);border-radius:8px;background:rgba(5,35,45,.65)">Long<br><b style="color:#4dffb0">${counts.long_bias || 0}</b></div>
          <div style="padding:6px;border:1px solid rgba(92,224,255,.25);border-radius:8px;background:rgba(5,35,45,.65)">Short<br><b style="color:#ff8080">${counts.short_bias || 0}</b></div>
          <div style="padding:6px;border:1px solid rgba(92,224,255,.25);border-radius:8px;background:rgba(5,35,45,.65)">Observe<br><b style="color:#6ab8ff">${counts.observe || 0}</b></div>
          <div style="padding:6px;border:1px solid rgba(92,224,255,.25);border-radius:8px;background:rgba(5,35,45,.65)">No Trade<br><b style="color:#ffaa50">${counts.no_trade || 0}</b></div>
        </div>

        ${rows || '<div style="color:#ffaa50">No intelligence run yet.</div>'}

        <div style="margin-top:8px;color:#4dffb0;font-weight:900">
          orders ${locks.order_execution_enabled === false ? 'OFF' : 'CHECK'} ·
          practice orders ${locks.practice_order_execution_enabled === false ? 'OFF' : 'CHECK'} ·
          OpenClaw execution ${locks.openclaw_execution_enabled === false ? 'OFF' : 'CHECK'} ·
          dispatch ${locks.autonomous_dispatch_enabled === false ? 'OFF' : 'CHECK'}
        </div>
      `;
    }catch(e){
      status.textContent = 'sidecar offline';
      status.style.color = '#ffaa50';
      body.textContent = 'Run: ./scripts/run_strategy_intelligence_sidecar.sh';
    }
  }

  async function runStrategy(){
    const btn = document.getElementById('siPanelRun');
    if(!btn) return;

    btn.disabled = true;
    btn.textContent = 'Running...';

    try{
      const res = await fetch(API + '/api/strategy/run', {method:'POST'});
      const data = await res.json();
      if(data.ok === false){
        alert('Strategy error: ' + (data.error || JSON.stringify(data)));
      }
      await refreshStrategy();
    }catch(e){
      alert('Strategy sidecar offline. Run: ./scripts/run_strategy_intelligence_sidecar.sh');
    }finally{
      btn.disabled = false;
      btn.textContent = 'Run Intelligence';
    }
  }

  if(document.readyState === 'loading') document.addEventListener('DOMContentLoaded', makePanel);
  else makePanel();

  setInterval(refreshStrategy, 15000);
})();
</script>
'''

if "</body>" in text:
    text = text.replace("</body>", snippet + "\n</body>", 1)
elif "</html>" in text:
    text = text.replace("</html>", snippet + "\n</html>", 1)
else:
    raise SystemExit("No </body> or </html> marker found in dashboard server.")

p.write_text(text, encoding="utf-8")
py_compile.compile(str(p), doraise=True)
print("Strategy Intelligence panel installed.")
PY

echo
echo "=== COMPILE CHECK ==="
python3 -m py_compile src/dashboard/server.py
python3 -m py_compile src/tower/strategy_intelligence.py
python3 -m py_compile src/tower/strategy_intelligence_sidecar.py
python3 -m py_compile src/tower/worker_sandbox.py

echo
echo "=== RESTART DASHBOARD ==="
./stop.sh
./run.sh
./status.sh

echo
echo "======================================================"
echo "  STRATEGY INTELLIGENCE PANEL ONLY COMPLETE"
echo "======================================================"
echo "Open:"
echo "  http://127.0.0.1:8765/?v=strategy-panel-only"
echo
echo "Hard refresh with Ctrl+Shift+R."
echo "======================================================"
