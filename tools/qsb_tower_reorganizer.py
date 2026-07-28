#!/usr/bin/env python3
"""
qsb_tower_reorganizer.py — INTERACTIVE, guided tower reorganisation wizard.

2026-07-28, Ross: "bring up a box ... help me rearrange the floors ... a checklist
we work through live ... give me choices ... we make the change ... 10 minutes later
a complete structured floor of all the floors ... like the window for the API key
but to reorganize the tower."

Auto-builds a task queue from the live audit (Codex off #170, the name-conflicts,
free-floor fills), shows CHOICES + a recommendation, and APPLIES each change LIVE.

SAFETY (every apply):
  · timestamped backup of floors.json + canonical BEFORE the change
  · surgical edit, then JSON re-validate (rollback-able from the backup)
  · append audit row to data/registries/qsb_reorg_audit.jsonl
  · occupied targets are ARCHIVED (never destroyed) under archive/floors_replaced/
It edits ONLY the two floor registries + floor-card dirs. Never a gate, vault,
CLAUDE.md, or provider. Additive service on :8872.
Run: python3 tools/qsb_tower_reorganizer.py --port 8872
"""
import json, argparse, glob, re, shutil, os, unicodedata
from datetime import datetime, timezone
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
import time as _time

ROOT = Path(__file__).resolve().parent.parent
REG = ROOT / "data" / "registries"
FLOORS = REG / "floors.json"
CANON = REG / "qsb_canonical_floor_registry_1_170.json"
AUDIT = REG / "qsb_reorg_audit.jsonl"
SHOP_V2 = REG / "qsb_shop_floors_workers_v2_154_163.json"
ARCH = ROOT / "archive" / "floors_replaced"


def _now():
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def _ts():
    return datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")


def _norm(s):
    s = unicodedata.normalize("NFKD", s or "").encode("ascii", "ignore").decode().lower()
    return re.sub(r'[^a-z0-9]+', ' ', s).strip()


def _load(p, d):
    try:
        return json.loads(Path(p).read_text(encoding="utf-8"))
    except Exception:
        return d


def _living():
    m = {}
    for e in _load(FLOORS, []) or []:
        if isinstance(e, dict) and e.get("number") is not None:
            m.setdefault(e["number"], e)
    return m


def _canon():
    return {int(k): v for k, v in ((_load(CANON, {}) or {}).get("floors", {}) or {}).items()}


def _workers():
    c = {}
    d = _load(SHOP_V2, {})
    for w in (d.get("workers", []) if isinstance(d, dict) else []):
        try:
            c[int(str(w.get("floor", "")).lstrip("Ff"))] = c.get(int(str(w.get("floor", "")).lstrip("Ff")), 0) + 1
        except Exception:
            pass
    return c


def _audit(row):
    row["ts"] = _now()
    with open(AUDIT, "a", encoding="utf-8") as f:
        f.write(json.dumps(row, ensure_ascii=False) + "\n")


def _backup(op):
    ts = _ts()
    shutil.copy(FLOORS, f"{FLOORS}.bak_{op}_{ts}")
    shutil.copy(CANON, f"{CANON}.bak_{op}_{ts}")
    return ts


# ── task queue (auto-derived from live state; self-updating) ──────────────────
def build_tasks():
    liv, can, wk = _living(), _canon(), _workers()
    nums = sorted(set(liv) | set(can))

    def reallocatable(n):
        e = liv.get(n) or {}
        desc = (e.get("description") or "").lower()
        nm = _norm(e.get("floor_name") or "")
        return wk.get(n, 0) == 0 and ("standard tower office layout" in desc
                                      or e.get("vacant") is True or nm in ("", "future systems vacant"))

    free = [n for n in nums if reallocatable(n)]
    tasks = []

    # 1) Codex off #170 (only while Codex is still at 170)
    codex_n = next((n for n in nums if _norm((liv.get(n) or {}).get("floor_name")) == "codex floor"
                    or _norm((can.get(n) or {}).get("label")) == "codex floor"), None)
    if codex_n == 170:
        # candidate destinations: reallocatable floors, tech-ish first
        techish = [n for n in free if n in (40, 39, 8, 9, 26, 27, 24, 21, 22, 20, 38)]
        picks = (techish + [n for n in free if n not in techish])[:10]
        tasks.append({
            "id": "codex_move", "type": "move", "title": "Move the Codex Floor off #170",
            "subject": 170, "current": "Codex Floor",
            "choices": [{"to": n, "label": (liv.get(n) or {}).get("floor_name") or (can.get(n) or {}).get("label") or "empty",
                         "reallocatable": True} for n in picks],
            "recommend": (techish[:1] or picks[:1] or [None])[0],
            "why": "Reallocatable floors (generic fit-out, 0 workers). Tech-band floors near Coding/Dev listed first.",
        })

    # 2) name-conflicts living vs canonical
    for n in nums:
        ln = (liv.get(n) or {}).get("floor_name")
        cl = (can.get(n) or {}).get("label")
        if ln and cl and _norm(ln) != _norm(cl):
            tasks.append({
                "id": f"conflict_{n}", "type": "resolve", "title": f"Resolve floor #{n}", "subject": n,
                "living": ln, "canonical": cl,
                "recommend": "canonical",
                "why": "Your OpenAI package says treat the canonical registry as source of truth; canonical carries the shop/commerce identity.",
                "workers": wk.get(n, 0),
            })
    return {"ts": _now(), "codex_at": codex_n, "free_floors": free,
            "tasks": tasks, "pending": len(tasks)}


# ── apply engine ──────────────────────────────────────────────────────────────
def _set_canon_label(text, n, label, provenance=None, authority="CANONICAL_CURRENT"):
    """Surgically set the label (and optionally provenance/authority) of canonical floor n."""
    def esc(s):
        return s.replace("\\", "\\\\").replace('"', '\\"')
    if provenance is None:
        # keep provenance/authority, swap only the label value
        pat = re.compile(r'("' + str(n) + r'":\s*\{\s*"label":\s*")[^"]*(")')
        new, c = pat.subn(lambda m: m.group(1) + esc(label) + m.group(2), text, count=1)
        return new, c
    prov = "null" if provenance is None else '"' + esc(provenance) + '"'
    block = '"%d": {\n   "label": "%s",\n   "provenance": %s,\n   "authority": "%s"\n  }' % (n, esc(label), prov, authority)
    pat = re.compile(r'"' + str(n) + r'":\s*\{[^}]*\}')
    new, c = pat.subn(lambda m: block, text, count=1)
    return new, c


def set_floor(n, name):
    """Rename floor n to `name` in BOTH registries so they agree."""
    ts = _backup("rename")
    liv = _load(FLOORS, [])
    found = False
    for e in liv:
        if e.get("number") == n:
            e["floor_name"] = name
            e["department"] = name
            found = True
    if not found:
        liv.append({"id": f"floor_{n}", "number": n, "zone": "", "department": name,
                    "description": "", "status": "active", "vacant": False,
                    "lift_access": "all", "floor_name": name, "archetype": "ops_floor"})
        liv.sort(key=lambda e: e.get("number", 0))
    txt = json.dumps(liv, indent=2, ensure_ascii=False)
    json.loads(txt)
    FLOORS.write_text(txt, encoding="utf-8")

    ct = CANON.read_text(encoding="utf-8")
    ct2, c = _set_canon_label(ct, n, name)
    if c == 0:  # floor absent in canonical -> nothing to patch (rare)
        pass
    else:
        json.loads(ct2)
        CANON.write_text(ct2, encoding="utf-8")
    _audit({"op": "rename", "floor": n, "name": name, "backup_ts": ts})
    return {"ok": True, "op": "rename", "floor": n, "name": name}


def move_floor(frm, to):
    """Relocate the floor identity at `frm` to `to`. Archives whatever is at `to`."""
    ts = _backup("move")
    liv = _load(FLOORS, [])
    src = next((e for e in liv if e.get("number") == frm), None)
    if not src:
        return {"ok": False, "error": f"no living floor #{frm}"}
    name = src.get("floor_name")
    can = _canon()

    # archive the destination if occupied
    dst = next((e for e in liv if e.get("number") == to), None)
    if dst or to in can:
        os.makedirs(ARCH, exist_ok=True)
        dst_name = (dst or {}).get("floor_name") or (can.get(to) or {}).get("label") or "unknown"
        slug = re.sub(r'[^a-z0-9]+', '_', _norm(dst_name)) or "floor"
        adir = ARCH / f"{slug}_{to}_replaced_by_{re.sub(r'[^a-z0-9]+','_',_norm(name))}_{ts}"
        os.makedirs(adir, exist_ok=True)
        json.dump({"archived_ts": _now(), "living_entry": dst, "canonical_entry": can.get(to)},
                  open(adir / "registry_entries.json", "w"), indent=2, ensure_ascii=False)
        # move its floor-card dir if present
        for p in glob.glob(str(ROOT / "floors" / f"floor_{to}_*")):
            if os.path.isdir(p):
                shutil.move(p, str(adir / os.path.basename(p)))

    # living: drop dest, move src -> to
    liv = [e for e in liv if e.get("number") != to]
    for e in liv:
        if e.get("number") == frm:
            e["number"] = to
            e["id"] = f"floor_{to}"
    liv.sort(key=lambda e: e.get("number", 0))
    txt = json.dumps(liv, indent=2, ensure_ascii=False)
    json.loads(txt)
    FLOORS.write_text(txt, encoding="utf-8")

    # canonical: free frm (UNKNOWN), set to = name with card provenance
    slug = re.sub(r'[^a-z0-9]+', '_', _norm(name))
    card_dir = f"floors/floor_{to}_{slug}"
    ct = CANON.read_text(encoding="utf-8")
    ct, c1 = _set_canon_label(ct, to, name, provenance=f"{card_dir}/floor_card.json")
    # free the source slot -> UNKNOWN placeholder (lambda replacement = escape-safe)
    frm_block = ('"%d": {\n   "label": "UNKNOWN \\u2014 AUTHORITATIVE LABEL NOT FOUND",\n'
                 '   "provenance": null,\n   "authority": "UNKNOWN"\n  }') % frm
    ct = re.sub(r'"' + str(frm) + r'":\s*\{[^}]*\}', lambda mm: frm_block, ct, count=1)
    json.loads(ct)
    CANON.write_text(ct, encoding="utf-8")

    # move the floor-card dir frm -> to and update its contents
    src_dirs = glob.glob(str(ROOT / "floors" / f"floor_{frm}_*"))
    if src_dirs:
        newdir = ROOT / card_dir
        shutil.move(src_dirs[0], str(newdir))
        cardp = newdir / "floor_card.json"
        if cardp.exists():
            c = _load(cardp, {})
            c["floor_id"] = f"floor_{to}"
            c["floor_number"] = to
            c.setdefault("relocation_history", []).append({"from": frm, "to": to, "ts": _now()})
            json.dump(c, open(cardp, "w", encoding="utf-8"), indent=2, ensure_ascii=False)
    _audit({"op": "move", "from": frm, "to": to, "name": name, "backup_ts": ts})
    return {"ok": True, "op": "move", "from": frm, "to": to, "name": name}


def apply(payload):
    t = payload.get("type")
    try:
        if t == "resolve":
            n = int(payload["floor"])
            name = payload["living"] if payload.get("choose") == "living" else payload["canonical"]
            return set_floor(n, name)
        if t == "rename":
            return set_floor(int(payload["floor"]), str(payload["name"])[:80])
        if t == "move":
            return move_floor(int(payload["frm"]), int(payload["to"]))
        return {"ok": False, "error": f"unknown op {t}"}
    except Exception as exc:
        return {"ok": False, "error": str(exc)[:300]}


PAGE = r"""<!doctype html><html><head><meta charset=utf-8><title>Tower Reorganizer</title>
<meta name=viewport content="width=device-width,initial-scale=1">
<style>
:root{--bg:#0b0f17;--card:#131a26;--line:#233146;--txt:#dce6f5;--dim:#7d8da6;--accent:#5aa9ff;--ok:#39d98a;--warn:#f5c451;--codex:#10a37f}
*{box-sizing:border-box}body{margin:0;background:var(--bg);color:var(--txt);font:14px/1.5 -apple-system,Segoe UI,Roboto,sans-serif}
.wrap{max-width:900px;margin:0 auto;padding:20px}
h1{margin:0;font-size:21px}.sub{color:var(--dim);margin:2px 0 14px}
.prog{background:var(--card);border:1px solid var(--line);border-radius:10px;padding:10px 12px;margin-bottom:14px}
.prog .lab{display:flex;justify-content:space-between;font-size:12px;color:var(--dim);margin-bottom:6px}
.track{height:10px;background:#0d1420;border-radius:999px;overflow:hidden}.fill{height:100%;background:var(--ok);width:0%;transition:width .3s}
.card{background:var(--card);border:1px solid var(--line);border-radius:14px;padding:18px;margin-bottom:14px}
.card h2{margin:0 0 4px;font-size:17px}.why{color:var(--dim);font-size:12px;margin:6px 0 14px}
.choices{display:flex;flex-wrap:wrap;gap:8px;margin-bottom:14px}
.choice{border:1px solid var(--line);background:#0d1420;border-radius:10px;padding:9px 13px;cursor:pointer;font-size:13px}
.choice:hover{border-color:var(--accent)}.choice.sel{border-color:var(--ok);background:rgba(57,217,138,.12)}
.choice.rec::after{content:" ★ recommended";color:var(--warn);font-size:11px}
.custom{display:flex;gap:8px;align-items:center;margin-bottom:14px;color:var(--dim);font-size:13px}
input{background:#0d1420;border:1px solid var(--line);border-radius:8px;color:var(--txt);padding:8px 10px;width:90px}
.act{display:flex;gap:10px;align-items:center}
button{border:0;border-radius:9px;padding:10px 18px;font-weight:700;cursor:pointer}
.apply{background:var(--ok);color:#04120d}.apply:disabled{opacity:.4;cursor:default}
.skip{background:transparent;border:1px solid var(--line);color:var(--dim);font-weight:400}
.done{text-align:center;padding:40px 20px}.done h2{color:var(--ok);font-size:24px}
.mini{color:var(--dim);font-size:12px}.queue{color:var(--dim);font-size:12px;margin-top:10px}
.log{background:#0d1420;border:1px solid var(--line);border-radius:8px;padding:8px;margin-top:12px;font-family:ui-monospace,monospace;font-size:11px;max-height:120px;overflow:auto;color:#9fb6d6}
</style></head><body><div class=wrap>
<h1>Tower Reorganizer <span style="color:var(--dim);font-weight:400;font-size:13px">· guided · every change backed up</span></h1>
<div class=sub>One decision at a time. Pick, apply, next. Registries backed up + audited on every step.</div>
<div class=prog><div class=lab><span>Structured</span><span id=plab>—</span></div><div class=track><div class=fill id=pfill></div></div></div>
<div id=stage></div>
<div class=log id=log></div>
</div><script>
let TASKS=[],CUR=0,SEL=null,STATE=null;
function logln(t){const l=document.getElementById('log');l.innerHTML=`<div>${t}</div>`+l.innerHTML}
async function load(){
  const d=await (await fetch('/api/tasks')).json();STATE=d;TASKS=d.tasks;
  const total=d.pending;
  render();
}
function setProg(){
  const total=(TASKS.length||0);const done=CUR;
  const pc=total?Math.round(100*done/total):100;
  document.getElementById('pfill').style.width=pc+'%';
  document.getElementById('plab').textContent=total?`${done} / ${total} done`:'nothing pending';
}
function pick(el,val){SEL=val;document.querySelectorAll('.choice').forEach(c=>c.classList.remove('sel'));if(el)el.classList.add('sel');document.getElementById('applyBtn').disabled=(SEL==null||SEL==='')}
function render(){
  setProg();
  const s=document.getElementById('stage');
  if(!TASKS.length){s.innerHTML=`<div class="card done"><h2>✓ Tower structured</h2><div class=mini>No conflicts, Codex placed. One clean model.</div></div>`;return}
  const t=TASKS[0];SEL=null;
  let html=`<div class=card><h2>${t.title}</h2><div class=why>${t.why||''}</div>`;
  if(t.type==='resolve'){
    html+=`<div class=choices>
      <div class="choice ${t.recommend==='living'?'rec':''}" onclick="pick(this,'living')">Living: <b>${t.living}</b></div>
      <div class="choice ${t.recommend==='canonical'?'rec':''}" onclick="pick(this,'canonical')">Canonical: <b>${t.canonical}</b></div>
    </div>${t.workers?`<div class=mini>⚠ ${t.workers} workers on this floor</div>`:''}`;
    html+=applyRow(`{type:'resolve',floor:${t.subject},choose:SEL,living:${JSON.stringify(t.living)},canonical:${JSON.stringify(t.canonical)}}`);
  } else if(t.type==='move'){
    html+=`<div class=mini>Currently: <b>${t.current}</b> on #${t.subject}. Choose a destination floor:</div><div class=choices>`;
    t.choices.forEach(c=>{html+=`<div class="choice ${t.recommend===c.to?'rec':''}" onclick="pick(this,${c.to})">#${c.to} <span class=mini>${c.label}</span></div>`});
    html+=`</div><div class=custom>or custom floor #: <input id=cust type=number oninput="SEL=this.value?+this.value:null;document.getElementById('applyBtn').disabled=(SEL==null)"></div>`;
    html+=applyRow(`{type:'move',frm:${t.subject},to:SEL}`);
  }
  html+=`</div>`;s.innerHTML=html;
}
function applyRow(payloadExpr){
  window.__payload=payloadExpr;
  return `<div class=act><button class=apply id=applyBtn disabled onclick="doApply()">Apply change</button>
    <button class=skip onclick="TASKS.shift();CUR++;render()">skip</button>
    <span class=queue>${TASKS.length-1} more after this</span></div>`;
}
async function doApply(){
  const payload=eval('('+window.__payload+')');
  document.getElementById('applyBtn').disabled=true;document.getElementById('applyBtn').textContent='applying…';
  const r=await (await fetch('/api/apply',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify(payload)})).json();
  if(r.ok){logln(`✓ ${r.op} ${JSON.stringify(r).slice(0,120)}`);CUR++;await load();/*reload derived tasks*/}
  else{logln(`✕ ${r.error}`);document.getElementById('applyBtn').textContent='Apply change';document.getElementById('applyBtn').disabled=false;alert('failed: '+r.error)}
}
load();
</script></body></html>"""


class H(BaseHTTPRequestHandler):
    def log_message(self, *a):
        pass

    def do_GET(self):
        if self.path.startswith("/api/tasks"):
            b = json.dumps(build_tasks()).encode()
            self.send_response(200); self.send_header("Content-Type", "application/json")
            self.send_header("Content-Length", str(len(b))); self.end_headers(); self.wfile.write(b)
        else:
            b = PAGE.encode()
            self.send_response(200); self.send_header("Content-Type", "text/html; charset=utf-8")
            self.send_header("Content-Length", str(len(b))); self.end_headers(); self.wfile.write(b)

    def do_POST(self):
        if self.path.startswith("/api/apply"):
            try:
                n = int(self.headers.get("Content-Length", 0) or 0)
                payload = json.loads(self.rfile.read(n) or b"{}")
            except Exception:
                payload = {}
            b = json.dumps(apply(payload)).encode()
            self.send_response(200); self.send_header("Content-Type", "application/json")
            self.send_header("Content-Length", str(len(b))); self.end_headers(); self.wfile.write(b)
        else:
            self.send_response(404); self.end_headers()


if __name__ == "__main__":
    ap = argparse.ArgumentParser(); ap.add_argument("--port", type=int, default=8872)
    a = ap.parse_args()
    print(f"tower reorganizer on http://0.0.0.0:{a.port}")
    ThreadingHTTPServer(("0.0.0.0", a.port), H).serve_forever()
