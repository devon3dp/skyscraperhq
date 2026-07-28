#!/usr/bin/env python3
"""
qsb_floor_directory_dash.py — INTERACTIVE floor directory + reorganisation planner.

2026-07-28, Ross: "redo the dashboard for the floor directories, make it more
informative so I can see exactly what's going on and we can both work out how to
rearrange things ... a tick box ... keep / swap / which floor I want to put them
to ... do a complete audit ... one complete structure ... don't lose the shops."

It MERGES every source so nothing is hidden:
  - living registry   : data/registries/floors.json
  - canonical registry : data/registries/qsb_canonical_floor_registry_1_170.json
  - floor cards on disk : floors/floor_*/floor_card.json
  - shop worker rosters : data/registries/qsb_shop_floors_workers_v2_154_163.json (+v1)
For each floor it shows: number · living name · canonical name · card name · which
registries back it · CONFLICT flag · SHOP flag · worker count.

PLANNING is non-destructive: your keep/swap/reassign/retire choices are saved to
data/registries/qsb_floor_plan_decisions.json — a PLAN file only. It NEVER edits
floors.json or the canonical registry. We execute the plan later, on your approval.

Additive service on :8871.  Run: python3 tools/qsb_floor_directory_dash.py --port 8871
"""
import json, argparse, glob, re, unicodedata
from datetime import datetime, timezone
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
import time as _time

ROOT = Path(__file__).resolve().parent.parent
REG = ROOT / "data" / "registries"
FLOORS = REG / "floors.json"
CANON = REG / "qsb_canonical_floor_registry_1_170.json"
PLAN = REG / "qsb_floor_plan_decisions.json"          # PLAN ONLY — never a registry
SHOP_V2 = REG / "qsb_shop_floors_workers_v2_154_163.json"
SHOP_V1 = REG / "qsb_shop_floors_workers_v1.json"

SHOPS_15 = ["Lumière Beauty", "Pinwheel Toys", "Pawsworth", "Hearthstone Kitchen",
            "Vector Tech", "Trailhead Outdoor", "Stretch Fitness", "Quilltree Office",
            "Voyage & Co", "Greenhouse Lane", "Little Robin", "Inkwell & Co",
            "Twilight Wellness", "Living Light Eco", "Maker Lane"]

SHOP_KW = re.compile(r'shop|store|etsy|shopify|storefront|commerce|seed|beauty|'
                     r'boutique|market|fulfil|print[- ]?on[- ]?demand|dropship|'
                     r'tiktok|listing|refund|dispute|checkout|merch|retail', re.I)


def _norm(s):
    s = unicodedata.normalize("NFKD", s or "").encode("ascii", "ignore").decode().lower()
    return re.sub(r'[^a-z0-9]+', ' ', s).strip()


def _load(p, default):
    try:
        return json.loads(Path(p).read_text(encoding="utf-8"))
    except Exception:
        return default


def _shop_worker_counts():
    counts = {}
    for f in (SHOP_V2, SHOP_V1):
        d = _load(f, {})
        for w in (d.get("workers", []) if isinstance(d, dict) else []):
            fl = str(w.get("floor", "")).lstrip("Ff")
            try:
                counts[int(fl)] = counts.get(int(fl), 0) + 1
            except Exception:
                pass
    return counts


_VER = str(int(_time.time()))


def build_data():
    liv = {}
    for e in _load(FLOORS, []) or []:
        if isinstance(e, dict) and e.get("number") is not None:
            liv.setdefault(e["number"], e)
    can = {int(k): v for k, v in ((_load(CANON, {}) or {}).get("floors", {}) or {}).items()}
    cards = {}
    for p in glob.glob(str(ROOT / "floors" / "floor_*" / "floor_card.json")):
        c = _load(p, {})
        n = c.get("floor_number")
        if n is not None:
            cards[int(n)] = c.get("floor_name") or c.get("department")
    workers = _shop_worker_counts()
    plan = _load(PLAN, {}) or {}
    decisions = plan.get("decisions", {})

    nums = sorted(set(liv) | set(can) | set(cards))
    rows = []
    conflicts = shops = decided = realloc = 0
    for n in nums:
        ln = (liv.get(n) or {}).get("floor_name")
        cl = (can.get(n) or {}).get("label")
        cd = cards.get(n)
        names = [x for x in (ln, cl, cd) if x]
        conflict = bool(ln and cl and _norm(ln) != _norm(cl))
        is_shop = any(SHOP_KW.search(x) for x in names) or any(_norm(s) in [_norm(x) for x in names] for s in SHOPS_15)
        wk = workers.get(n, 0)
        desc = (liv.get(n) or {}).get("description", "") or ""
        vacant = (liv.get(n) or {}).get("vacant", None)
        # "not really doing anything": generic boilerplate fit-out OR flagged vacant,
        # with no shop identity and no hired workers -> safe to reallocate.
        reallocatable = (not is_shop) and wk == 0 and (
            "standard tower office layout" in desc.lower() or vacant is True
            or _norm(ln or "") in ("", "future systems vacant"))
        dec = decisions.get(str(n), {})
        if conflict:
            conflicts += 1
        if is_shop:
            shops += 1
        if reallocatable:
            realloc += 1
        if dec.get("decision"):
            decided += 1
        rows.append({
            "n": n,
            "living": ln or "",
            "canonical": cl or "",
            "card": cd or "",
            "dept": (liv.get(n) or {}).get("department", ""),
            "zone": (liv.get(n) or {}).get("zone", ""),
            "vacant": vacant,
            "sources": "".join(["L" if n in liv else "-", "C" if n in can else "-", "F" if n in cards else "-"]),
            "conflict": conflict,
            "shop": is_shop,
            "reallocatable": reallocatable,
            "workers": wk,
            "decision": dec.get("decision", ""),
            "target": dec.get("target", ""),
            "note": dec.get("note", ""),
        })

    # 15-shop allocation status
    allname = {n: [x for x in [(liv.get(n) or {}).get("floor_name"), (can.get(n) or {}).get("label"), cards.get(n)] if x]
               for n in nums}
    shop_status = []
    for s in SHOPS_15:
        floor = next((n for n in nums if _norm(s) in [_norm(x) for x in allname[n]]), None)
        shop_status.append({"shop": s, "floor": floor})
    allocated = sum(1 for x in shop_status if x["floor"] is not None)

    return {
        "ver": _VER,
        "ts": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
        "total": len(rows),
        "conflicts": conflicts,
        "shops": shops,
        "reallocatable": realloc,
        "decided": decided,
        "shop_status": shop_status,
        "shops_allocated": allocated,
        "shops_total": len(SHOPS_15),
        "rows": rows,
    }


FLOOR_DASHES = {
    24: {"label": "Gene Pool", "port": 8873, "path": "/"},
    40: {"label": "Codex", "port": 8870, "path": "/"},
    48: {"label": "Lumen AI", "port": 8848, "path": "/"},
    53: {"label": "Tower Command", "port": 8874, "path": "/"},
    74: {"label": "Town Square", "port": 8852, "path": "/town_square"},
    77: {"label": "Task Council", "port": 8864, "path": "/"},
}


def floor_detail(n):
    """Everything about one floor: card, rooms, workers, registry entries, and its
    own dashboard link if it has one. Read-only."""
    dirs = glob.glob(str(ROOT / "floors" / f"floor_{n}_*"))
    card, rooms = {}, []
    if dirs:
        card = _load(Path(dirs[0]) / "floor_card.json", {}) or {}
        for rp in sorted(glob.glob(str(Path(dirs[0]) / "rooms" / "*.json"))):
            rc = _load(rp, {})
            rooms.append((rc.get("name") or rc.get("room") or Path(rp).stem) if isinstance(rc, dict) else Path(rp).stem)
    liv = {e["number"]: e for e in (_load(FLOORS, []) or []) if isinstance(e, dict) and e.get("number") is not None}
    can = (_load(CANON, {}) or {}).get("floors", {}) or {}
    workers = []
    sw = _load(SHOP_V2, {})
    for w in (sw.get("workers", []) if isinstance(sw, dict) else []):
        if str(w.get("floor", "")).lstrip("Ff") == str(n):
            workers.append({"role": w.get("role"), "id": w.get("worker_id")})
    for t in (card.get("team_roster", []) if isinstance(card, dict) else []):
        if isinstance(t, dict):
            workers.append({"role": t.get("category") or t.get("role"), "id": t.get("id")})
    return {
        "n": n, "dir": (Path(dirs[0]).name if dirs else None),
        "living": liv.get(n), "canonical": can.get(str(n)),
        "card": card, "rooms": rooms,
        "workers": workers[:60], "worker_count": len(workers),
        "dash": FLOOR_DASHES.get(n),
    }


def save_plan(decisions):
    """Persist keep/swap/reassign/retire choices to the PLAN file only."""
    if not isinstance(decisions, dict):
        return {"ok": False, "error": "bad payload"}
    clean = {}
    for k, v in decisions.items():
        if not isinstance(v, dict):
            continue
        d = {"decision": str(v.get("decision", ""))[:20],
             "target": str(v.get("target", ""))[:8],
             "note": str(v.get("note", ""))[:400]}
        if d["decision"] or d["target"] or d["note"]:
            clean[str(k)] = d
    payload = {"updated_ts": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
               "note": "PLAN ONLY — reorganisation intentions. Not applied to any registry until Ross approves.",
               "decisions": clean}
    PLAN.write_text(json.dumps(payload, indent=2, ensure_ascii=False), encoding="utf-8")
    return {"ok": True, "saved": len(clean)}


PAGE = r"""<!doctype html><html><head><meta charset=utf-8><title>Floor Planner · Skyscraper HQ</title>
<meta name=viewport content="width=device-width,initial-scale=1">
<style>
:root{--bg:#0b0f17;--card:#131a26;--line:#233146;--txt:#dce6f5;--dim:#7d8da6;--accent:#5aa9ff;--shop:#f5a742;--warn:#f5c451;--ok:#39d98a;--bad:#ff6b6b;--codex:#10a37f}
*{box-sizing:border-box}body{margin:0;background:var(--bg);color:var(--txt);font:13px/1.4 -apple-system,Segoe UI,Roboto,sans-serif}
.wrap{max-width:1400px;margin:0 auto;padding:18px}
h1{margin:0;font-size:20px}.sub{color:var(--dim);margin:2px 0 12px}
.chips{display:flex;gap:8px;flex-wrap:wrap;margin-bottom:10px}
.chip{background:var(--card);border:1px solid var(--line);border-radius:999px;padding:5px 11px;color:var(--dim);font-size:12px}
.chip b{color:var(--txt)}
.bars{display:grid;grid-template-columns:1fr 1fr;gap:10px;margin-bottom:12px}
.bar{background:var(--card);border:1px solid var(--line);border-radius:10px;padding:10px 12px}
.bar .lab{display:flex;justify-content:space-between;font-size:12px;color:var(--dim);margin-bottom:6px}
.track{height:9px;background:#0d1420;border-radius:999px;overflow:hidden}.fill{height:100%;border-radius:999px}
.bar1 .fill{background:var(--ok)}.bar2 .fill{background:var(--shop)}
.tools{display:flex;gap:8px;flex-wrap:wrap;align-items:center;margin-bottom:10px}
input,select{background:var(--card);border:1px solid var(--line);border-radius:8px;color:var(--txt);padding:7px 10px;font-size:13px}
#q{flex:1;min-width:200px}
button{background:var(--accent);color:#04101f;border:0;border-radius:8px;padding:8px 14px;font-weight:700;cursor:pointer}
button.ghost{background:transparent;color:var(--dim);border:1px solid var(--line);font-weight:400}
button.ghost.on{color:var(--txt);border-color:var(--accent)}
button.save{background:var(--ok);color:#04120d}
.shopsbar{display:flex;gap:6px;flex-wrap:wrap;margin-bottom:12px}
.spill{font-size:11px;padding:3px 9px;border-radius:999px;border:1px solid var(--line)}
.spill.ok{color:var(--ok);border-color:var(--ok)}.spill.no{color:var(--bad);border-color:var(--bad)}
table{width:100%;border-collapse:collapse;background:var(--card);border:1px solid var(--line);border-radius:10px;overflow:hidden}
th,td{text-align:left;padding:6px 9px;border-bottom:1px solid var(--line);font-size:12px;vertical-align:middle}
th{color:var(--dim);text-transform:uppercase;letter-spacing:.04em;font-size:10px;position:sticky;top:0;background:#0f1622;cursor:pointer}
tr:last-child td{border-bottom:0}
td.n{font-family:ui-monospace,Menlo,monospace;color:var(--accent);font-weight:700;width:46px}
tr.conflict td.n{color:var(--warn)}tr.shop{background:rgba(245,167,66,.06)}
.tag{font-size:9px;padding:1px 6px;border-radius:999px;border:1px solid var(--line);color:var(--dim)}
.tag.shop{color:var(--shop);border-color:var(--shop)}.tag.conf{color:var(--warn);border-color:var(--warn)}
.tag.realloc{color:var(--accent);border-color:var(--accent)}
button.mini{background:transparent;border:1px solid var(--line);color:var(--dim);border-radius:6px;padding:1px 6px;font-size:10px;cursor:pointer;margin-left:3px}
button.mini:hover{color:var(--txt);border-color:var(--accent)}
tr.realloc td.n{color:var(--accent)}
.src{font-family:ui-monospace,monospace;color:var(--dim);font-size:11px}
.dim{color:var(--dim)}.wk{color:var(--shop)}
select.dec{padding:4px 6px;font-size:11px}
input.tgt{width:52px;padding:4px 6px;font-size:11px}input.nt{width:100%;padding:4px 6px;font-size:11px}
tr.dirty td.n::after{content:"●";color:var(--ok);margin-left:3px}
footer{color:var(--dim);margin-top:14px;font-size:11px}
</style></head><body><div class=wrap>
<h1>Floor Planner <span style="color:var(--dim);font-weight:400;font-size:14px">· complete audit + reorganisation board</span></h1>
<div class=sub>Every floor, every source. Plan changes here — nothing touches the real registries until you approve.</div>
<div class=chips>
  <span class=chip>floors <b id=cTotal>—</b></span>
  <span class=chip>conflicts <b id=cConf>—</b></span>
  <span class=chip>shop floors <b id=cShop>—</b></span>
  <span class=chip>reallocatable <b id=cReal>—</b></span>
  <span class=chip>decisions made <b id=cDec>—</b></span>
  <span class=chip>unsaved <b id=cDirty>0</b></span>
</div>
<div class=bars>
  <div class="bar bar1"><div class=lab><span>Conflicts with a decision</span><span id=lConf>—</span></div><div class=track><div class=fill id=fConf style=width:0%></div></div></div>
  <div class="bar bar2"><div class=lab><span>Shops allocated to a floor</span><span id=lShop>—</span></div><div class=track><div class=fill id=fShop style=width:0%></div></div></div>
</div>
<div class=shopsbar id=shopsbar></div>
<div class=tools>
  <input id=q placeholder="filter by number / name / department…" oninput=render()>
  <button class="ghost on" data-f=all onclick=setF(this,'all')>all</button>
  <button class=ghost data-f=conflict onclick=setF(this,'conflict')>conflicts</button>
  <button class=ghost data-f=shop onclick=setF(this,'shop')>shops</button>
  <button class=ghost data-f=reallocatable onclick=setF(this,'reallocatable')>reallocatable</button>
  <button class=ghost data-f=decided onclick=setF(this,'decided')>decided</button>
  <button class=save onclick=savePlan()>Save Plan</button>
</div>
<table><thead><tr>
  <th onclick="sortBy('n')">#</th><th onclick="sortBy('living')">Living name</th>
  <th onclick="sortBy('canonical')">Canonical name</th><th>Card</th>
  <th onclick="sortBy('sources')">Src</th><th onclick="sortBy('workers')">Wkrs</th><th>Flags</th>
  <th>Decision</th><th>→Floor</th><th>Note</th>
</tr></thead><tbody id=tb></tbody></table>
<footer>plan-only · click a floor # to open it · saves to qsb_floor_plan_decisions.json · <span id=ts></span> · :8871</footer>
<div id=fmodal style="display:none;position:fixed;inset:0;background:rgba(0,0,0,.65);z-index:50" onclick="if(event.target===this)this.style.display='none'">
  <div style="max-width:780px;margin:36px auto;background:var(--card);border:1px solid var(--line);border-radius:14px;padding:20px;max-height:86vh;overflow:auto">
    <div style="display:flex;justify-content:space-between;align-items:center;margin-bottom:8px">
      <h2 id=fmTitle style="margin:0;font-size:20px;color:var(--txt);text-transform:none;letter-spacing:0"></h2>
      <span onclick="document.getElementById('fmodal').style.display='none'" style="cursor:pointer;color:var(--dim);font-size:24px">×</span></div>
    <div id=fmBody></div>
  </div>
</div>
</div><script>
async function openFloor(n){
  const m=document.getElementById('fmodal'),b=document.getElementById('fmBody');
  document.getElementById('fmTitle').textContent='Floor #'+n;b.innerHTML='loading…';m.style.display='block';
  let d;try{d=await (await fetch('/api/floor?n='+n)).json()}catch(e){b.innerHTML='error';return}
  const c=d.card||{},esc=s=>(''+(s==null?'':s)).replace(/</g,'&lt;');
  document.getElementById('fmTitle').textContent='#'+n+' · '+esc(c.floor_name||(d.living&&d.living.floor_name)||'—');
  let h='';
  if(d.dash){const host=location.hostname;h+=`<a href="http://${host}:${d.dash.port}${d.dash.path}" target="_blank" style="display:inline-block;background:var(--accent);color:#04101f;padding:9px 15px;border-radius:8px;font-weight:700;text-decoration:none;margin-bottom:12px">▶ Open ${esc(d.dash.label)} dash</a>`;}
  const rows=[['department',c.department||(d.living&&d.living.department)],['zone',c.zone||(d.living&&d.living.zone)],['staff lead',c.staff_lead],['established',c.established_by],['status',(d.living&&d.living.status)]];
  h+='<table style="width:100%;font-size:12px;margin-bottom:8px">'+rows.filter(r=>r[1]).map(r=>`<tr><td style="color:var(--dim);width:120px;padding:3px 0;border:0">${r[0]}</td><td style="border:0">${esc(r[1])}</td></tr>`).join('')+'</table>';
  if(c.tour_blurb)h+=`<p style="color:#b9c8dd;font-style:italic;font-size:13px">${esc(c.tour_blurb)}</p>`;
  h+=`<div style="margin-top:8px"><b class=pill>ROOMS (${d.rooms.length})</b><br>${d.rooms.map(r=>`<span class=chip style="margin:2px;display:inline-block">${esc(r)}</span>`).join('')||'<span class=dim>none listed</span>'}</div>`;
  h+=`<div style="margin-top:10px"><b class=pill>WORKERS (${d.worker_count})</b><br>${d.workers.map(w=>`<span class=chip style="margin:2px;display:inline-block">${esc(w.role||'?')}</span>`).join('')||'<span class=dim>none listed</span>'}</div>`;
  h+=`<details style="margin-top:10px"><summary class=pill>raw registry entries</summary><pre style="background:#0d1420;border:1px solid var(--line);border-radius:8px;padding:8px;font-size:11px;overflow:auto">living: ${esc(JSON.stringify(d.living,null,1))}\n\ncanonical: ${esc(JSON.stringify(d.canonical,null,1))}</pre></details>`;
  b.innerHTML=h;
}
let DATA=[],FILTER='all',sortKey='n',sortDir=1,DIRTY={};
function setF(btn,f){FILTER=f;document.querySelectorAll('.ghost').forEach(b=>b.classList.toggle('on',b===btn));render()}
function sortBy(k){sortDir=(sortKey===k)?-sortDir:1;sortKey=k;render()}
function mark(n,field,val){DIRTY[n]=DIRTY[n]||{};DIRTY[n][field]=val;const r=DATA.find(x=>x.n===n);if(r)r[field]=val;document.getElementById('cDirty').textContent=Object.keys(DIRTY).length;const tr=document.querySelector('tr[data-n="'+n+'"]');if(tr)tr.classList.add('dirty')}
function resolve(n,which){const r=DATA.find(x=>x.n===n);if(!r)return;mark(n,'decision',which==='living'?'use_living':'use_canonical');mark(n,'note',(which==='living'?'keep living name: '+r.living:'adopt canonical name: '+r.canonical));render()}
function render(){
  const q=document.getElementById('q').value.toLowerCase();
  let r=DATA.filter(x=>{
    if(FILTER==='conflict'&&!x.conflict)return false;
    if(FILTER==='shop'&&!x.shop)return false;
    if(FILTER==='reallocatable'&&!x.reallocatable)return false;
    if(FILTER==='decided'&&!x.decision)return false;
    return !q||[x.n,x.living,x.canonical,x.card,x.dept].join(' ').toLowerCase().includes(q);
  });
  r.sort((a,b)=>{let x=a[sortKey],y=b[sortKey];if(typeof x==='string'){x=x.toLowerCase();y=(''+y).toLowerCase()}return (x>y?1:x<y?-1:0)*sortDir});
  const opt=v=>['','keep','swap','reassign','retire','use_living','use_canonical'].map(o=>`<option ${o===v?'selected':''}>${o}</option>`).join('');
  document.getElementById('tb').innerHTML=r.map(x=>`<tr data-n="${x.n}" class="${x.conflict?'conflict':''} ${x.shop?'shop':''} ${x.reallocatable?'realloc':''} ${DIRTY[x.n]?'dirty':''}">
    <td class=n onclick="openFloor(${x.n})" style="cursor:pointer" title="open floor #${x.n}">${x.n} ⧉</td>
    <td>${x.living||'<span class=dim>—</span>'}</td>
    <td class="${x.conflict?'':'dim'}">${x.canonical||'<span class=dim>—</span>'}</td>
    <td class=dim>${x.card||''}</td>
    <td class=src>${x.sources}</td>
    <td class=wk>${x.workers||''}</td>
    <td>${x.shop?'<span class="tag shop">shop</span> ':''}${x.reallocatable?'<span class="tag realloc">reallocatable</span> ':''}${x.conflict?'<span class="tag conf">conflict</span>':''}${x.conflict?` <button class=mini onclick="resolve(${x.n},'living')">use L</button><button class=mini onclick="resolve(${x.n},'canonical')">use C</button>`:''}</td>
    <td><select class=dec onchange="mark(${x.n},'decision',this.value)">${opt(x.decision)}</select></td>
    <td><input class=tgt value="${x.target||''}" placeholder=# onchange="mark(${x.n},'target',this.value)"></td>
    <td><input class=nt value="${(x.note||'').replace(/"/g,'&quot;')}" placeholder="why / what" onchange="mark(${x.n},'note',this.value)"></td>
  </tr>`).join('');
}
async function load(){
  let d;try{d=await (await fetch('/api/data')).json()}catch(e){return}
  if(window.__v&&window.__v!==d.ver){location.reload();return}window.__v=d.ver;
  DATA=d.rows;
  cTotal.textContent=d.total;cConf.textContent=d.conflicts;cShop.textContent=d.shops;cReal.textContent=d.reallocatable;cDec.textContent=d.decided;
  const pc=d.conflicts?Math.round(100*d.decided/d.conflicts):0;
  fConf.style.width=Math.min(100,pc)+'%';lConf.textContent=d.decided+' / '+d.conflicts;
  const ps=Math.round(100*d.shops_allocated/d.shops_total);
  fShop.style.width=ps+'%';lShop.textContent=d.shops_allocated+' / '+d.shops_total;
  shopsbar.innerHTML=d.shop_status.map(s=>`<span class="spill ${s.floor!=null?'ok':'no'}">${s.shop}${s.floor!=null?' · #'+s.floor:' · NEEDS FLOOR'}</span>`).join('');
  ts.textContent=(d.ts||'').replace('T',' ');
  render();
}
async function savePlan(){
  const merged={};DATA.forEach(x=>{if(x.decision||x.target||x.note)merged[x.n]={decision:x.decision,target:x.target,note:x.note}});
  const r=await (await fetch('/api/plan',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({decisions:merged})})).json();
  if(r.ok){DIRTY={};document.getElementById('cDirty').textContent=0;document.querySelectorAll('tr.dirty').forEach(t=>t.classList.remove('dirty'));alert('Plan saved: '+r.saved+' floor decisions. Registries untouched.')}
  else alert('save failed: '+(r.error||'?'));
}
load();
</script></body></html>"""


class H(BaseHTTPRequestHandler):
    def log_message(self, *a):
        pass

    def do_GET(self):
        if self.path.startswith("/api/data"):
            body = json.dumps(build_data()).encode()
            self.send_response(200); self.send_header("Content-Type", "application/json")
            self.send_header("Content-Length", str(len(body))); self.end_headers(); self.wfile.write(body)
        elif self.path.startswith("/api/floor"):
            from urllib.parse import urlparse, parse_qs
            try:
                n = int(parse_qs(urlparse(self.path).query).get("n", ["0"])[0])
            except Exception:
                n = 0
            body = json.dumps(floor_detail(n)).encode()
            self.send_response(200); self.send_header("Content-Type", "application/json")
            self.send_header("Content-Length", str(len(body))); self.end_headers(); self.wfile.write(body)
        else:
            body = PAGE.encode()
            self.send_response(200); self.send_header("Content-Type", "text/html; charset=utf-8")
            self.send_header("Content-Length", str(len(body))); self.end_headers(); self.wfile.write(body)

    def do_POST(self):
        if self.path.startswith("/api/plan"):
            try:
                n = int(self.headers.get("Content-Length", 0) or 0)
                payload = json.loads(self.rfile.read(n) or b"{}")
            except Exception:
                payload = {}
            res = save_plan(payload.get("decisions", {}))
            body = json.dumps(res).encode()
            self.send_response(200); self.send_header("Content-Type", "application/json")
            self.send_header("Content-Length", str(len(body))); self.end_headers(); self.wfile.write(body)
        else:
            self.send_response(404); self.end_headers()


if __name__ == "__main__":
    ap = argparse.ArgumentParser(); ap.add_argument("--port", type=int, default=8871)
    a = ap.parse_args()
    print(f"floor planner dash on http://0.0.0.0:{a.port}")
    ThreadingHTTPServer(("0.0.0.0", a.port), H).serve_forever()
