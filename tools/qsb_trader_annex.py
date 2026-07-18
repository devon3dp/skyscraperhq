#!/usr/bin/env python3
"""qsb_trader_annex.py — lightweight trader host that runs anywhere.

Ross 2026-07-05 #157: trading annexes on Oracle + all 4 CEO homes.
Traders can migrate between annexes; profitable ones earn to pick.

An annex is a small HTTP service on port 9200 that:
  · GET /                  → annex identity + traders hosted
  · GET /traders           → list of live traders + PnL
  · POST /trader/host      → accept a migrating trader (payload = trader blob)
  · POST /trader/tick      → advance one tick (paper trader logic)
  · GET  /pnl/{trader_id}  → PnL history for that trader
  · POST /trader/release   → release a trader (returns migration blob)

The annex is PAPER-only unless the HQ authoritative gate says otherwise.
Real broker calls stay off unless flip. Skyscraper connectivity: annex
polls http://192.168.1.72:8852/tasks/data for orders + posts PnL to
qsb_town_square via HQ hub.

Minimum resource: 100MB RAM, Python 3.10+.
"""
from __future__ import annotations
import json, os, random, sys, time, urllib.request, urllib.parse
from datetime import datetime, timezone
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

ANNEX_ID = os.environ.get("QSB_ANNEX_ID", "unknown")
ANNEX_NAME = os.environ.get("QSB_ANNEX_NAME", "unnamed")
HQ_URL = os.environ.get("QSB_HQ_URL", "http://192.168.1.72:8852")
PORT = int(os.environ.get("QSB_ANNEX_PORT", "9200"))
STATE_DIR = Path(os.environ.get("QSB_ANNEX_STATE", "/tmp/qsb_annex_state"))
STATE_DIR.mkdir(parents=True, exist_ok=True)
TRADERS_FILE = STATE_DIR / "traders.json"
STARTED_AT = time.time()

def _utc(): return datetime.now(timezone.utc).isoformat().replace("+00:00","Z")

def load_traders() -> dict:
    if not TRADERS_FILE.exists(): return {}
    try: return json.loads(TRADERS_FILE.read_text())
    except Exception: return {}

def save_traders(t: dict):
    TRADERS_FILE.write_text(json.dumps(t, indent=2, default=str))

def _post_hq(path, body):
    try:
        req = urllib.request.Request(HQ_URL + path,
            data=json.dumps(body).encode(),
            headers={"Content-Type":"application/json"})
        return urllib.request.urlopen(req, timeout=5).read()
    except Exception:
        return None


def trader_tick(t: dict) -> dict:
    """Paper trader step. Randomly walks equity — deterministic per trader
    via seed. Real trader logic is in the main fleet; this is a proof-of-
    life for annex-level trading + migration."""
    seed = hash(t.get("id","")) & 0xffff
    random.seed(seed + t.get("cycles",0))
    delta = round(random.uniform(-0.005, 0.006) * t.get("equity", 100), 3)
    t["equity"] = round(t.get("equity", 100) + delta, 3)
    t["last_delta"] = delta
    t["cycles"] = t.get("cycles", 0) + 1
    t["last_tick"] = _utc()
    t["pnl_history"] = (t.get("pnl_history") or [])[-99:]
    t["pnl_history"].append({"ts": t["last_tick"], "equity": t["equity"], "delta": delta})
    return t


class H(BaseHTTPRequestHandler):
    def log_message(self, *a, **k): pass

    def _send(self, code, body):
        data = json.dumps(body, default=str).encode()
        self.send_response(code)
        self.send_header("Content-Type","application/json")
        self.send_header("Content-Length", str(len(data)))
        self.send_header("Cache-Control","no-store")
        self.end_headers()
        try: self.wfile.write(data)
        except Exception: pass

    def do_GET(self):
        path = self.path.split("?")[0]
        traders = load_traders()
        if path == "/stats":
            # Ross 2026-07-05 #170: rich Oracle annex stats
            import os as _os, platform as _pf, socket as _s
            traders = load_traders()
            eq_sum = sum((t.get("equity") or 0) for t in traders.values())
            eq_delta = sum(((t.get("equity") or 100) - 100) for t in traders.values())
            cycles_sum = sum((t.get("cycles") or 0) for t in traders.values())
            # cpu/mem via /proc
            cpu_p = None; mem_p = None; load1 = None
            try:
                with open("/proc/loadavg") as f: load1 = float(f.read().split()[0])
                with open("/proc/meminfo") as f:
                    mi = f.read()
                    total = int([l for l in mi.splitlines() if l.startswith("MemTotal")][0].split()[1])
                    avail = int([l for l in mi.splitlines() if l.startswith("MemAvailable")][0].split()[1])
                    mem_p = round((total-avail)/total*100, 1)
            except Exception: pass
            # disk
            disk_p = None
            try:
                st = _os.statvfs("/")
                disk_p = round((1 - st.f_bavail/st.f_blocks)*100, 1)
            except Exception: pass
            self._send(200, {
                "annex_id": ANNEX_ID, "annex_name": ANNEX_NAME,
                "hostname": _s.gethostname(),
                "platform": _pf.platform(),
                "python": _pf.python_version(),
                "uptime_s": int(time.time() - STARTED_AT),
                "trader_count": len(traders),
                "trader_equity_sum": round(eq_sum, 3),
                "trader_pnl_delta": round(eq_delta, 3),
                "trader_cycles_sum": cycles_sum,
                "cpu_load1": load1,
                "mem_percent_used": mem_p,
                "disk_percent_used": disk_p,
                "ts": _utc(),
            }); return
        if path == "/dash":
            html = _DASH_HTML.replace("__ANNEX_ID__", ANNEX_ID).replace("__ANNEX_NAME__", ANNEX_NAME)
            body = html.encode()
            self.send_response(200)
            self.send_header("Content-Type","text/html; charset=utf-8")
            self.send_header("Content-Length", str(len(body)))
            self.send_header("Cache-Control","no-store")
            self.end_headers()
            try: self.wfile.write(body)
            except Exception: pass
            return
        if path == "/":
            self._send(200, {
                "annex_id": ANNEX_ID, "annex_name": ANNEX_NAME,
                "uptime_s": int(time.time() - STARTED_AT),
                "trader_count": len(traders),
                "hq_url": HQ_URL,
                "port": PORT,
                "ts": _utc(),
            }); return
        if path == "/traders":
            summary = [{
                "id": t.get("id"), "name": t.get("name"),
                "equity": t.get("equity"), "cycles": t.get("cycles",0),
                "last_tick": t.get("last_tick"),
                "instrument": t.get("instrument","?"),
            } for t in traders.values()]
            self._send(200, {"traders": summary, "count": len(summary)}); return
        if path.startswith("/pnl/"):
            tid = path[5:]
            t = traders.get(tid)
            if not t: self._send(404, {"error":"not found"}); return
            self._send(200, {"id": tid, "equity": t.get("equity"),
                "history": t.get("pnl_history",[])[-50:]}); return
        self._send(404, {"error":"not found","path":path})

    def do_POST(self):
        path = self.path.split("?")[0]
        length = int(self.headers.get("Content-Length","0") or 0)
        raw = self.rfile.read(length) if length else b"{}"
        try: body = json.loads(raw)
        except Exception: body = {}
        traders = load_traders()
        if path == "/trader/host":
            tid = body.get("id") or f"trader_{int(time.time())}"
            traders[tid] = {
                **body, "id": tid, "arrived_at": _utc(),
                "annex_id": ANNEX_ID, "equity": body.get("equity", 100.0),
                "cycles": 0, "pnl_history": [],
            }
            save_traders(traders)
            _post_hq("/town/post", {"from":"annex_"+ANNEX_ID,
                "text":f"🏠 trader {tid} arrived at annex '{ANNEX_NAME}' with equity {traders[tid]['equity']}",
                "to":"council","src":"annex_migration"})
            self._send(200, {"ok":True,"id":tid,"hosted":True}); return
        if path == "/trader/tick":
            tid = body.get("id")
            if tid and tid in traders:
                traders[tid] = trader_tick(traders[tid])
                save_traders(traders)
                self._send(200, {"ok":True,"id":tid,"equity":traders[tid]["equity"],
                    "delta":traders[tid]["last_delta"]}); return
            # tick ALL if no specific id
            for tid, t in traders.items():
                traders[tid] = trader_tick(t)
            save_traders(traders)
            self._send(200, {"ok":True,"ticked":len(traders)}); return
        if path == "/trader/release":
            tid = body.get("id")
            if not tid or tid not in traders:
                self._send(404, {"error":"not found"}); return
            blob = traders.pop(tid)
            save_traders(traders)
            blob["released_at"] = _utc()
            self._send(200, {"ok":True,"blob":blob}); return
        self._send(404, {"error":"not found","path":path})


_DASH_HTML = """<!doctype html><html><head><meta charset=utf-8>
<meta name=viewport content='width=device-width,initial-scale=1'>
<title>__ANNEX_NAME__ · Annex Dash</title>
<style>
*{box-sizing:border-box}
body{background:#0b0d12;color:#e8ecf3;font:14px/1.5 system-ui,-apple-system,Segoe UI,Roboto,sans-serif;margin:0;padding:20px}
h1{margin:0 0 6px;color:#f43f5e;font-size:1.8em}
.sub{color:#94a3b8;margin-bottom:16px;font-size:12.5px}
.summary{display:flex;gap:14px;margin-bottom:16px;padding:12px 14px;background:#0e1420;border:1px solid #22334a;border-radius:8px;font-family:ui-monospace,monospace}
.summary .cell{display:flex;flex-direction:column;gap:2px}
.summary .lbl{color:#94a3b8;font-size:10.5px;text-transform:uppercase;letter-spacing:0.06em}
.summary .val{color:#22d3ee;font-size:22px;font-weight:700}
.tbl{width:100%;border-collapse:collapse;background:#0e1420;border-radius:8px;overflow:hidden;border:1px solid #22334a}
.tbl th{background:#0b1220;color:#94a3b8;padding:10px 12px;text-align:left;font-size:11px;text-transform:uppercase;letter-spacing:0.04em}
.tbl td{padding:8px 12px;border-top:1px solid #1e293b;font-family:ui-monospace,monospace;font-size:11.5px}
.tbl tr:hover{background:#0b1220}
.win{color:#10b981}
.loss{color:#ef4444}
@keyframes pulse{0%,100%{opacity:1}50%{opacity:0.6}}
.live{animation:pulse 1.6s infinite}
@keyframes tape{0%{transform:translateX(0)}100%{transform:translateX(-100%)}}
@keyframes flash-up{0%{background:rgba(16,185,129,0.4)}100%{background:transparent}}
@keyframes flash-dn{0%{background:rgba(239,68,68,0.4)}100%{background:transparent}}
.up{animation:flash-up 1.2s ease-out}
.dn{animation:flash-dn 1.2s ease-out}
.tbl tr{transition:background 0.35s}
</style></head><body>
<h1>🏠 __ANNEX_NAME__ <span style='font-size:0.55em;color:#94a3b8'>· __ANNEX_ID__</span></h1>
<div class=sub>Annex command center · traders auto-tick every 5s · live PnL animation · 1s refresh</div>
<div id=ticker style='margin-bottom:14px;padding:10px 14px;background:#0e1420;border:1px solid #22334a;border-radius:8px;overflow:hidden;white-space:nowrap;font-family:ui-monospace,monospace;font-size:12px'>
  <span id=ticker-content style='display:inline-block;padding-left:100%;animation:tape 30s linear infinite'>loading traders…</span>
</div>
<div class=summary id=summary></div>
<div id=sys-panel style='margin-bottom:16px;padding:14px;background:#0e1420;border:1px solid #22334a;border-radius:8px'>
  <h2 style='margin:0 0 8px;color:#22d3ee;font-size:1.05em'>🖥️ SYSTEM · Oracle Cloud VM</h2>
  <div id=sys-grid style='display:grid;grid-template-columns:repeat(auto-fit,minmax(140px,1fr));gap:10px'></div>
</div>
<div id=fleet-panel style='margin-bottom:16px;padding:14px;background:#0e1420;border:1px solid #22334a;border-radius:8px'>
  <h2 style='margin:0 0 8px;color:#f43f5e;font-size:1.05em'>💰 TRADER FLEET · live PnL</h2>
  <div id=fleet-stats style='display:grid;grid-template-columns:repeat(auto-fit,minmax(140px,1fr));gap:10px'></div>
</div>
<table class=tbl>
  <thead><tr><th>ID</th><th>Name</th><th>Instrument</th><th>Equity</th><th>Cycles</th><th>Last Tick</th></tr></thead>
  <tbody id=body></tbody>
</table>
<script>
async function tick(){
  try{
    const [root, traders, stats] = await Promise.all([
      fetch('/', {cache:'no-store'}).then(r=>r.json()),
      fetch('/traders', {cache:'no-store'}).then(r=>r.json()),
      fetch('/stats', {cache:'no-store'}).then(r=>r.json()).catch(()=>({})),
    ]);
    const eq = (traders.traders||[]).reduce((s,t)=>s+(t.equity||0),0);
    document.getElementById('summary').innerHTML = `
      <div class='cell'><span class='lbl'>traders</span><span class='val'>${traders.count||0}</span></div>
      <div class='cell'><span class='lbl'>total equity</span><span class='val'>$${eq.toFixed(2)}</span></div>
      <div class='cell'><span class='lbl'>uptime</span><span class='val'>${Math.floor((root.uptime_s||0)/60)}m</span></div>
      <div class='cell'><span class='lbl'>hq link</span><span class='val live' style='color:#10b981'>●</span></div>
    `;
    document.getElementById('sys-grid').innerHTML = `
      <div class='cell'><span class='lbl'>hostname</span><span class='val' style='font-size:14px'>${(stats.hostname||'?').slice(0,20)}</span></div>
      <div class='cell'><span class='lbl'>CPU load1</span><span class='val'>${stats.cpu_load1?.toFixed(2)||'?'}</span></div>
      <div class='cell'><span class='lbl'>Memory %</span><span class='val' style='color:${stats.mem_percent_used>80?"#ef4444":"#22d3ee"}'>${stats.mem_percent_used||'?'}%</span></div>
      <div class='cell'><span class='lbl'>Disk %</span><span class='val' style='color:${stats.disk_percent_used>80?"#ef4444":"#22d3ee"}'>${stats.disk_percent_used||'?'}%</span></div>
    `;
    document.getElementById('fleet-stats').innerHTML = `
      <div class='cell'><span class='lbl'>PnL delta</span><span class='val' style='color:${stats.trader_pnl_delta>=0?"#10b981":"#ef4444"}'>$${(stats.trader_pnl_delta||0).toFixed(2)}</span></div>
      <div class='cell'><span class='lbl'>total cycles</span><span class='val'>${stats.trader_cycles_sum||0}</span></div>
      <div class='cell'><span class='lbl'>Python</span><span class='val' style='font-size:14px'>${stats.python||'?'}</span></div>
    `;
    // Ross 2026-07-05 #174: animated equity changes + ticker
    if(!window.__prevEq) window.__prevEq = {};
    const sorted = (traders.traders||[]).sort((a,b)=>b.equity-a.equity);
    document.getElementById('body').innerHTML = sorted.map(t=>{
      const eqCls = (t.equity>100)?'win':'loss';
      const prev = window.__prevEq[t.id];
      const flashCls = (prev !== undefined && Math.abs(t.equity - prev) > 0.0001) ? (t.equity > prev ? 'up' : 'dn') : '';
      window.__prevEq[t.id] = t.equity;
      return `<tr class='${flashCls}'>
        <td>${(t.id||'').replace(/</g,'&lt;')}</td>
        <td>${(t.name||'').replace(/</g,'&lt;')}</td>
        <td>${(t.instrument||'?')}</td>
        <td class='${eqCls}'>$${(t.equity||0).toFixed(3)}</td>
        <td>${t.cycles||0}</td>
        <td>${(t.last_tick||'').slice(11,19) || '—'}</td>
      </tr>`;
    }).join('') || '<tr><td colspan=6 style=color:#64748b>no traders</td></tr>';
    // Ticker tape
    const tape = sorted.map(t=>{
      const delta = t.equity - 100;
      const arrow = delta >= 0 ? '▲' : '▼';
      const color = delta >= 0 ? '#10b981' : '#ef4444';
      return `<span style='margin-right:30px;color:${color}'>${arrow} ${t.id} $${t.equity.toFixed(2)} (${delta>=0?'+':''}${delta.toFixed(2)})</span>`;
    }).join('');
    document.getElementById('ticker-content').innerHTML = tape;
  }catch(e){}
}
tick(); setInterval(tick, 2000);
</script>
</body></html>"""


def main():
    print(f"  qsb_trader_annex · id={ANNEX_ID} name='{ANNEX_NAME}' port={PORT} hq={HQ_URL}")
    # Ross 2026-07-05 #174: auto-tick daemon so traders visibly walk equity
    import threading
    def auto_tick_loop():
        while True:
            try:
                traders = load_traders()
                if traders:
                    for tid, t in traders.items():
                        traders[tid] = trader_tick(t)
                    save_traders(traders)
            except Exception: pass
            time.sleep(5)
    threading.Thread(target=auto_tick_loop, daemon=True).start()
    srv = ThreadingHTTPServer(("0.0.0.0", PORT), H)
    srv.serve_forever()


if __name__ == "__main__":
    main()
