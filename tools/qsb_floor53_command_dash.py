#!/usr/bin/env python3
"""
qsb_floor53_command_dash.py — Floor 53 · Tower Command dashboard.

2026-07-28, Ross: "update the floor 53 dash so i can see new floors."
Floor 53 (Tower Command) had no dashboard — this is it: a live command-center view
of the WHOLE tower structure, with new / recently-changed floors highlighted.

REAL DATA ONLY:
  - full structure : data/registries/floors.json (grouped by zone)
  - what changed    : data/registries/qsb_reorg_audit.jsonl (moves, allocations, resolves)
READ-ONLY. Additive service on :8874.
Run: python3 tools/qsb_floor53_command_dash.py --port 8874
"""
import json, argparse, re, unicodedata
from datetime import datetime, timezone
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
import time as _time

ROOT = Path(__file__).resolve().parent.parent
REG = ROOT / "data" / "registries"
FLOORS = REG / "floors.json"
AUDIT = REG / "qsb_reorg_audit.jsonl"

SHOP_KW = re.compile(r'shop|store|etsy|shopify|storefront|commerce|beauty|boutique|'
                     r'market|fulfil|print-on-demand|listing|refund|customer service|'
                     r'promotion|voice commerce', re.I)


def _load(p, d):
    try:
        return json.loads(Path(p).read_text(encoding="utf-8"))
    except Exception:
        return d


def _audit_rows():
    rows = []
    try:
        for ln in AUDIT.read_text(encoding="utf-8").splitlines():
            ln = ln.strip()
            if ln:
                try:
                    rows.append(json.loads(ln))
                except Exception:
                    pass
    except Exception:
        pass
    return rows


_VER = str(int(_time.time()))


def build_data():
    liv = [e for e in (_load(FLOORS, []) or []) if isinstance(e, dict) and e.get("number") is not None]
    liv.sort(key=lambda e: e["number"])

    audit = _audit_rows()
    # latest change per floor (for the "changed" badge)
    changed = {}
    # floors that are genuinely NEW here (moved-in or allocated) — from ANY such op,
    # not just the latest, so a later gene-pool-wire row can't hide a move.
    new_set = {}
    for r in audit:
        op = r.get("op")
        fl = r.get("to") if op == "move" else r.get("floor")
        if fl is None:
            continue
        fl = int(fl)
        changed[fl] = {"op": op, "name": r.get("name"), "ts": r.get("ts"), "from": r.get("from")}
        if op in ("move", "allocate"):
            new_set[fl] = {"op": op, "name": r.get("name"), "ts": r.get("ts"), "from": r.get("from")}
    new_floors = sorted(new_set)

    # group by zone
    zones = {}
    shops = 0
    for e in liv:
        z = e.get("zone") or "—"
        nm = e.get("floor_name") or ""
        is_shop = bool(SHOP_KW.search(nm))
        if is_shop:
            shops += 1
        zones.setdefault(z, []).append({
            "n": e["number"], "name": nm, "dept": e.get("department", ""),
            "shop": is_shop, "changed": e["number"] in changed,
            "change": changed.get(e["number"]),
        })

    # recent changes feed (last 25, newest first)
    feed = []
    for r in reversed(audit):
        fl = r.get("to") if r.get("op") == "move" else r.get("floor")
        feed.append({"op": r.get("op"), "floor": fl, "name": r.get("name"),
                     "from": r.get("from"), "ts": r.get("ts")})
        if len(feed) >= 25:
            break

    return {
        "ver": _VER,
        "ts": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
        "total": len(liv),
        "shops": shops,
        "changed_count": len(changed),
        "new_floors": [{"n": n, "name": next((f["name"] for zz in zones.values() for f in zz if f["n"] == n), ""),
                        "change": new_set[n]} for n in new_floors],
        "zones": [{"zone": z, "floors": fs} for z, fs in
                  sorted(zones.items(), key=lambda kv: kv[1][0]["n"])],
        "feed": feed,
    }


PAGE = r"""<!doctype html><html><head><meta charset=utf-8><title>Floor 53 · Tower Command</title>
<meta name=viewport content="width=device-width,initial-scale=1">
<style>
:root{--bg:#0b0f17;--card:#131a26;--line:#233146;--txt:#dce6f5;--dim:#7d8da6;--accent:#5aa9ff;--new:#39d98a;--shop:#f5a742;--cmd:#e0546b}
*{box-sizing:border-box}body{margin:0;background:var(--bg);color:var(--txt);font:13px/1.45 -apple-system,Segoe UI,Roboto,sans-serif}
.wrap{max-width:1200px;margin:0 auto;padding:20px}
h1{margin:0;font-size:21px}h1 .n{color:var(--cmd)}
.sub{color:var(--dim);margin:2px 0 14px}
.kpis{display:flex;gap:12px;flex-wrap:wrap;margin-bottom:14px}
.kpi{background:var(--card);border:1px solid var(--line);border-radius:12px;padding:12px 16px}
.kpi .v{font-size:24px;font-weight:700}.kpi .l{color:var(--dim);font-size:11px;text-transform:uppercase}
.cols{display:grid;grid-template-columns:1fr 320px;gap:14px}
@media(max-width:820px){.cols{grid-template-columns:1fr}}
.card{background:var(--card);border:1px solid var(--line);border-radius:12px;padding:14px}
.card h2{margin:0 0 10px;font-size:12px;letter-spacing:.06em;text-transform:uppercase;color:var(--dim)}
.newstrip{display:flex;gap:8px;flex-wrap:wrap;margin-bottom:14px}
.newpill{background:rgba(57,217,138,.12);border:1px solid var(--new);color:var(--new);border-radius:999px;padding:5px 11px;font-size:12px;font-weight:600}
.zone{margin-bottom:14px}.zone h3{margin:0 0 6px;font-size:12px;color:var(--accent);text-transform:uppercase;letter-spacing:.05em}
.floors{display:grid;grid-template-columns:repeat(auto-fill,minmax(200px,1fr));gap:6px}
.fl{display:flex;gap:8px;align-items:center;padding:5px 8px;border:1px solid var(--line);border-radius:8px;background:#0d1420}
.fl .num{font-family:ui-monospace,monospace;color:var(--accent);font-weight:700;width:34px}
.fl.new{border-color:var(--new);background:rgba(57,217,138,.08)}
.fl.shop .num{color:var(--shop)}
.badge{font-size:9px;padding:1px 5px;border-radius:999px;border:1px solid var(--new);color:var(--new);margin-left:auto}
.feed .row{padding:6px 0;border-bottom:1px solid var(--line);font-size:12px}.feed .row:last-child{border:0}
.op{font-weight:700}.op.move{color:var(--accent)}.op.allocate{color:var(--new)}.op.resolve{color:var(--dim)}.op.gene_pool_wire{color:#8a5cf6}
.mono{font-family:ui-monospace,monospace}.dim{color:var(--dim)}
footer{color:var(--dim);margin-top:14px;font-size:11px}
</style></head><body><div class=wrap>
<h1>Floor 53 <span class=n>· Tower Command</span></h1>
<div class=sub>Live view of the whole tower. New &amp; recently-changed floors highlighted.</div>
<div class=kpis>
  <div class=kpi><div class=v id=kTotal>—</div><div class=l>floors</div></div>
  <div class=kpi><div class=v id=kShops>—</div><div class=l>shop floors</div></div>
  <div class=kpi><div class=v id=kNew>—</div><div class=l>changed</div></div>
</div>
<div class=card style="margin-bottom:14px"><h2>✨ New floors</h2><div class=newstrip id=newstrip></div></div>
<div class=cols>
  <div class=card><h2>Structure (by zone)</h2><div id=zones></div></div>
  <div class=card><h2>Recent changes</h2><div class=feed id=feed></div></div>
</div>
<footer>read-only · auto-refresh 5s · <span id=ts></span> · :8874</footer>
</div><script>
function esc(s){return (''+(s==null?'':s)).replace(/</g,'&lt;')}
async function tick(){
  let d;try{d=await (await fetch('/api/data')).json()}catch(e){return}
  if(window.__v&&window.__v!==d.ver){location.reload();return}window.__v=d.ver;
  kTotal.textContent=d.total;kShops.textContent=d.shops;kNew.textContent=d.changed_count;
  newstrip.innerHTML=d.new_floors.map(f=>`<span class=newpill>#${f.n} ${esc(f.name)} <span class=dim>· ${esc(f.change.op)}${f.change.from!=null?' from #'+f.change.from:''}</span></span>`).join('')||'<span class=dim>none</span>';
  zones.innerHTML=d.zones.map(z=>`<div class=zone><h3>${esc(z.zone)}</h3><div class=floors>${
    z.floors.map(f=>`<div class="fl ${f.changed?'new':''} ${f.shop?'shop':''}"><span class=num>${f.n}</span><span>${esc(f.name)}</span>${f.changed?'<span class=badge>new</span>':''}</div>`).join('')
  }</div></div>`).join('');
  feed.innerHTML=d.feed.map(r=>`<div class=row><span class="op ${esc(r.op)}">${esc(r.op)}</span> <span class=mono>#${esc(r.floor)}</span> ${esc(r.name)||''} ${r.from!=null?`<span class=dim>(from #${esc(r.from)})</span>`:''}<div class=dim style="font-size:10px">${esc((r.ts||'').replace('T',' ').replace('Z',''))}</div></div>`).join('');
  ts.textContent=(d.ts||'').replace('T',' ');
}
tick();setInterval(tick,5000);
</script></body></html>"""


class H(BaseHTTPRequestHandler):
    def log_message(self, *a):
        pass

    def do_GET(self):
        if self.path.startswith("/api/data"):
            b = json.dumps(build_data()).encode()
            self.send_response(200); self.send_header("Content-Type", "application/json")
            self.send_header("Content-Length", str(len(b))); self.end_headers(); self.wfile.write(b)
        else:
            b = PAGE.encode()
            self.send_response(200); self.send_header("Content-Type", "text/html; charset=utf-8")
            self.send_header("Content-Length", str(len(b))); self.end_headers(); self.wfile.write(b)


if __name__ == "__main__":
    ap = argparse.ArgumentParser(); ap.add_argument("--port", type=int, default=8874)
    a = ap.parse_args()
    print(f"floor 53 tower command dash on http://0.0.0.0:{a.port}")
    ThreadingHTTPServer(("0.0.0.0", a.port), H).serve_forever()
