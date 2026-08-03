#!/usr/bin/env python3
"""
QSB Living Skyscraper Dashboard  (READ-ONLY)  ::8878

Visually proves the QSB Tower is ALIVE — every floor buzzing with REAL worker
activity — while obeying R01 honesty: every number/message shown is read fresh
from a real on-disk source; a quiet floor is shown quiet (never invented).

This is a passive VIEW. It never writes any tower state, never flips a gate,
never edits a sibling engine. It only READS:

  - data/registries/qsb_floor_worker_activity.jsonl        (aggregate worker log)
  - data/registries/qsb_floor_<N>_worker_activity.jsonl    (per-floor worker log)
  - data/registries/qsb_bus_journal.jsonl                  (event bus journal)
  - data/registries/qsb_event_bus.jsonl                    (event bus)
  - data/registries/qsb_floor_intercom_state.json          (floor intercom)
  - data/registries/qsb_floor_activity_index.json          (floor liveness index)
  - data/registries/qsb_floor_zones.json                   (floor -> zone/colour)
  - data/registries/*roster*.json / worker_slots           (worker rosters)

Sibling engines (NOT touched by this tool) produce the data:
  qsb_worker_activation_engine.py, qsb_worker_chain_reporting.py,
  qsb_floor_activity_index.py, qsb_tower_transit_map.py.

Usage:  python3 tools/qsb_living_skyscraper_dash.py --port 8878
Data:   GET /api/state   -> JSON snapshot of everything shown, timestamped + sourced
        GET /api/health  -> tiny liveness probe
        GET /            -> the living building view (auto-refreshes)
"""
from __future__ import annotations

import argparse
import json
import os
import re
import time
from datetime import datetime, timezone
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
REG = ROOT / "data" / "registries"

# ---- real sources (read-only) ------------------------------------------------
AGG_ACTIVITY   = REG / "qsb_floor_worker_activity.jsonl"
PERFLOOR_GLOB  = "qsb_floor_*_worker_activity.jsonl"
BUS_JOURNAL    = REG / "qsb_bus_journal.jsonl"
EVENT_BUS      = REG / "qsb_event_bus.jsonl"
INTERCOM_STATE = REG / "qsb_floor_intercom_state.json"
ACTIVITY_INDEX = REG / "qsb_floor_activity_index.json"
FLOOR_ZONES    = REG / "qsb_floor_zones.json"

# Worker-report event name the activation engine emits onto the bus journal.
WORKER_REPORT_NAME = "worker.floor.report"

# how "active in the last N minutes" is defined for headline counts
ACTIVE_WINDOW_MIN = 15

SOURCES_SHOWN = [
    "data/registries/qsb_floor_worker_activity.jsonl",
    "data/registries/qsb_floor_<N>_worker_activity.jsonl",
    "data/registries/qsb_bus_journal.jsonl",
    "data/registries/qsb_floor_intercom_state.json",
    "data/registries/qsb_floor_activity_index.json",
    "data/registries/qsb_floor_zones.json",
    "data/registries/*roster*.json",
]

# ---- tiny cache so we don't re-read the whole world every request ------------
_CACHE: dict = {"state": None, "ts": 0.0}
_CACHE_TTL = 2.0  # seconds


def _now_epoch() -> float:
    return time.time()


def _parse_ts(s: str) -> float | None:
    """Parse an ISO-8601 timestamp (with or without Z / offset) to epoch."""
    if not s or not isinstance(s, str):
        return None
    t = s.strip()
    if t.endswith("Z"):
        t = t[:-1] + "+00:00"
    try:
        dt = datetime.fromisoformat(t)
        if dt.tzinfo is None:
            dt = dt.replace(tzinfo=timezone.utc)
        return dt.timestamp()
    except Exception:
        return None


def _tail_lines(path: Path, max_lines: int, max_bytes: int = 2_000_000) -> list[str]:
    """Read the last max_lines JSONL lines efficiently (tail from EOF)."""
    try:
        size = path.stat().st_size
    except OSError:
        return []
    if size == 0:
        return []
    read = min(size, max_bytes)
    try:
        with open(path, "rb") as f:
            f.seek(size - read)
            chunk = f.read(read)
    except OSError:
        return []
    # strip any leading NUL corruption (boat power-loss artefact) defensively
    text = chunk.replace(b"\x00", b"").decode("utf-8", "replace")
    lines = [ln for ln in text.splitlines() if ln.strip()]
    return lines[-max_lines:]


def _iter_json_rows(path: Path, max_lines: int):
    for ln in _tail_lines(path, max_lines):
        try:
            yield json.loads(ln)
        except Exception:
            continue


def _load_json(path: Path):
    try:
        raw = path.read_bytes().replace(b"\x00", b"")
        return json.loads(raw.decode("utf-8", "replace"))
    except Exception:
        return None


# ---- zones -------------------------------------------------------------------
def load_zones() -> dict:
    z = _load_json(FLOOR_ZONES) or {}
    floors = z.get("floors", {})
    zone_colors = {zz["name"]: zz.get("color", "#64748b") for zz in z.get("zones", [])}
    return {
        "floors": floors,          # floor_<n> -> {number,label,zone,color}
        "zone_colors": zone_colors,
        "generated_ts": z.get("generated_ts"),
    }


# ---- roster totals (honest: counts real employed workers on record) ----------
def load_roster_total() -> dict:
    """Sum assigned/employed workers across real roster registries."""
    total = 0
    files_counted = []
    # canonical workers headline (authoritative single count if present)
    canon = _load_json(REG / "qsb_canonical_workers.json")
    canon_total = None
    if isinstance(canon, dict):
        canon_total = canon.get("total_canonical_workers") or canon.get("total_active_workers")
        if canon_total:
            files_counted.append("qsb_canonical_workers.json")
    # sum floor rosters (qsb_f*_roster.json + *_workers.json with a workers list)
    roster_sum = 0
    for p in sorted(REG.glob("qsb_f*_roster.json")):
        d = _load_json(p)
        if isinstance(d, dict) and isinstance(d.get("workers"), list):
            roster_sum += len(d["workers"])
            files_counted.append(p.name)
    return {
        "canonical_total": canon_total,
        "roster_file_sum": roster_sum,
        "files_counted": files_counted[:40],
    }


# ---- worker messages: aggregate log + per-floor logs + bus journal -----------
def _msg_from_perfloor_row(r: dict) -> dict | None:
    if r.get("kind") != "worker_floor_report":
        return None
    return {
        "ts": r.get("ts"),
        "epoch": _parse_ts(r.get("ts", "")),
        "worker_id": r.get("worker_id"),
        "floor": r.get("floor"),
        "message": r.get("message"),
        "need": r.get("need"),
        "src": "perfloor",
    }


def _msg_from_bus_row(r: dict) -> dict | None:
    if r.get("name") != WORKER_REPORT_NAME:
        return None
    p = r.get("payload", {}) or {}
    return {
        "ts": r.get("ts") or p.get("ts"),
        "epoch": _parse_ts(r.get("ts") or p.get("ts") or ""),
        "worker_id": p.get("worker_id"),
        "floor": p.get("floor"),
        "message": p.get("message"),
        "need": p.get("need"),
        "src": "bus_journal",
    }


def collect_worker_messages(limit: int = 60) -> dict:
    """Gather recent REAL worker messages from every worker source."""
    msgs: list[dict] = []
    saw_perfloor_files = []

    # (1) aggregate log
    for r in _iter_json_rows(AGG_ACTIVITY, 400):
        m = _msg_from_perfloor_row(r) or _msg_from_bus_row(r)
        if m and m.get("message"):
            m["src"] = m.get("src", "aggregate")
            msgs.append(m)

    # (2) per-floor logs
    for p in sorted(REG.glob(PERFLOOR_GLOB)):
        # skip the aggregate itself if the glob catches it
        if p.name == AGG_ACTIVITY.name:
            continue
        rows = list(_iter_json_rows(p, 60))
        if rows:
            saw_perfloor_files.append(p.name)
        for r in rows:
            m = _msg_from_perfloor_row(r)
            if m and m.get("message"):
                msgs.append(m)

    # (3) bus journal worker.floor.report events
    for r in _iter_json_rows(BUS_JOURNAL, 800):
        m = _msg_from_bus_row(r)
        if m and m.get("message"):
            msgs.append(m)

    # de-dupe by (worker_id, ts, message); keep newest
    seen = set()
    uniq = []
    msgs.sort(key=lambda m: m.get("epoch") or 0, reverse=True)
    for m in msgs:
        key = (m.get("worker_id"), m.get("ts"), m.get("message"))
        if key in seen:
            continue
        seen.add(key)
        uniq.append(m)

    ticker = uniq[:limit]
    # per-floor active-worker counts + needs, within active window
    now = _now_epoch()
    win = ACTIVE_WINDOW_MIN * 60
    floor_workers: dict[int, set] = {}
    needs: list[dict] = []
    active_workers = set()
    for m in uniq:
        e = m.get("epoch")
        if e is None:
            continue
        fresh = (now - e) <= win
        fl = m.get("floor")
        if isinstance(fl, int):
            floor_workers.setdefault(fl, set())
            if fresh:
                floor_workers[fl].add(m.get("worker_id"))
        if fresh and m.get("worker_id"):
            active_workers.add(m.get("worker_id"))
        nd = m.get("need")
        if nd:
            needs.append({
                "floor": fl, "worker_id": m.get("worker_id"),
                "need": nd, "ts": m.get("ts"),
            })

    # message rate over the last minute (real)
    one_min_ago = now - 60
    msgs_last_min = sum(1 for m in uniq if (m.get("epoch") or 0) >= one_min_ago)

    return {
        "ticker": ticker,
        "total_seen": len(uniq),
        "floor_active_worker_counts": {str(k): len(v) for k, v in floor_workers.items() if v},
        "active_worker_ids_count": len(active_workers),
        "needs": needs[:40],
        "msgs_last_min": msgs_last_min,
        "perfloor_files_with_data": saw_perfloor_files[:60],
    }


# ---- floor liveness from the activity index (the transit-map's own source) ---
def load_floor_liveness() -> dict:
    idx = _load_json(ACTIVITY_INDEX) or {}
    floors = idx.get("floors", {}) or {}
    return {
        "floors": floors,
        "generated_ts": idx.get("generated_ts"),
        "threshold_s": idx.get("threshold_s"),
        "active_floors": idx.get("active_floors"),
        "total_floors": idx.get("total_floors"),
    }


# ---- intercom (real per-floor sent/received) ---------------------------------
def load_intercom() -> dict:
    d = _load_json(INTERCOM_STATE) or {}
    return {
        "per_floor": d.get("per_floor", {}),
        "generated_ts": d.get("generated_ts"),
    }


# ---- assemble the full building --------------------------------------------
def build_state() -> dict:
    now = _now_epoch()
    zones = load_zones()
    liveness = load_floor_liveness()
    workers = collect_worker_messages()
    intercom = load_intercom()
    roster = load_roster_total()

    zfloors = zones["floors"]
    idx_floors = liveness["floors"]
    worker_counts = workers["floor_active_worker_counts"]

    # kernel-reserved / penthouse floors stay honestly dark (never faked lit)
    KERNEL_RESERVED = {153, 168}

    floors_out = []
    live_floor_count = 0
    for key, meta in sorted(zfloors.items(), key=lambda kv: kv[1].get("number", 0)):
        num = meta.get("number")
        idx_e = idx_floors.get(key, {})
        wc = worker_counts.get(str(num), 0)
        # A floor is LIT if the real activity index says active OR real worker
        # traffic landed on it this window. Kernel floors never light.
        index_active = bool(idx_e.get("active"))
        lit = (index_active or wc > 0) and (num not in KERNEL_RESERVED)
        if lit:
            live_floor_count += 1
        floors_out.append({
            "key": key,
            "number": num,
            "label": meta.get("label"),
            "zone": meta.get("zone"),
            "color": meta.get("color", "#64748b"),
            "lit": lit,
            "worker_count": wc,               # REAL fresh worker traffic count
            "index_active": index_active,     # from qsb_floor_activity_index
            "last_ts": idx_e.get("last_ts"),
            "age_s": idx_e.get("age_s"),
            "source": idx_e.get("source"),
            "signal": idx_e.get("signal"),
            "kernel_reserved": num in KERNEL_RESERVED,
        })

    total_floors = len(floors_out)
    dark_floors = total_floors - live_floor_count

    # headline worker counts — honest
    canonical_total = roster["canonical_total"]
    roster_sum = roster["roster_file_sum"]

    return {
        "ok": True,
        "generated_ts": datetime.now(timezone.utc).isoformat(),
        "generated_epoch": now,
        "headline": {
            "total_workers_canonical": canonical_total,
            "total_workers_roster_sum": roster_sum,
            "workers_active_last_window": workers["active_worker_ids_count"],
            "active_window_min": ACTIVE_WINDOW_MIN,
            "floors_total": total_floors,
            "floors_live": live_floor_count,
            "floors_dark": dark_floors,
            "messages_last_min": workers["msgs_last_min"],
            "worker_messages_seen": workers["total_seen"],
        },
        "floors": floors_out,
        "zone_colors": zones["zone_colors"],
        "ticker": workers["ticker"],
        "needs": workers["needs"],
        "intercom": intercom,
        "provenance": {
            "sources": SOURCES_SHOWN,
            "activity_index_generated_ts": liveness["generated_ts"],
            "activity_index_active_floors": liveness["active_floors"],
            "zones_generated_ts": zones["generated_ts"],
            "intercom_generated_ts": intercom["generated_ts"],
            "worker_activity_log_present": AGG_ACTIVITY.exists() and AGG_ACTIVITY.stat().st_size > 0,
            "perfloor_worker_files_with_data": workers["perfloor_files_with_data"],
            "roster_files_counted": roster["files_counted"],
            "note": ("R01: quiet floors shown quiet. Floor 'lit' = real activity-index "
                     "active OR fresh real worker traffic this window. Kernel-reserved "
                     "floors 153/168 stay dark by rule. No number here is invented."),
        },
    }


def get_state() -> dict:
    now = _now_epoch()
    if _CACHE["state"] is not None and (now - _CACHE["ts"]) < _CACHE_TTL:
        return _CACHE["state"]
    st = build_state()
    _CACHE["state"] = st
    _CACHE["ts"] = now
    return st


# ---- HTML view --------------------------------------------------------------
PAGE = r"""<!doctype html>
<html lang="en"><head>
<meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1">
<title>QSB Living Skyscraper</title>
<style>
:root{--bg:#05070d;--panel:#0b1220;--edge:#1c2740;--ink:#e6edf7;--dim:#7c8aa5;--lit:#ffe08a}
*{box-sizing:border-box}
body{margin:0;background:radial-gradient(1200px 800px at 70% -10%,#0d1830,#05070d 60%);
 color:var(--ink);font:14px/1.4 ui-sans-serif,system-ui,Segoe UI,Roboto,Arial}
header{display:flex;align-items:baseline;gap:16px;padding:14px 20px;border-bottom:1px solid var(--edge);
 position:sticky;top:0;background:rgba(5,7,13,.9);backdrop-filter:blur(6px);z-index:5}
header h1{font-size:18px;margin:0;letter-spacing:.5px}
header .sub{color:var(--dim);font-size:12px}
.wrap{display:grid;grid-template-columns:340px 1fr 360px;gap:14px;padding:14px 18px;align-items:start}
.card{background:var(--panel);border:1px solid var(--edge);border-radius:10px;padding:12px}
.card h2{font-size:12px;text-transform:uppercase;letter-spacing:.12em;color:var(--dim);margin:0 0 10px}
.kpis{display:grid;grid-template-columns:1fr 1fr;gap:8px}
.kpi{background:#0a1526;border:1px solid var(--edge);border-radius:8px;padding:8px 10px}
.kpi .n{font-size:22px;font-weight:700}
.kpi .l{font-size:11px;color:var(--dim)}
.building{display:flex;flex-direction:column-reverse;gap:2px;max-height:74vh;overflow:auto;
 padding:8px;border-radius:8px;background:linear-gradient(180deg,#070c17,#0a1120)}
.floor{display:flex;align-items:center;gap:8px;padding:2px 8px;border-radius:5px;
 border-left:4px solid var(--edge);opacity:.34;transition:opacity .3s}
.floor.lit{opacity:1;box-shadow:0 0 14px -4px currentColor}
.floor .fn{width:44px;color:var(--dim);font-variant-numeric:tabular-nums;font-size:11px}
.floor .lbl{flex:1;white-space:nowrap;overflow:hidden;text-overflow:ellipsis;font-size:12px}
.floor .wc{font-variant-numeric:tabular-nums;font-size:12px;color:var(--lit);min-width:34px;text-align:right}
.floor .dot{width:8px;height:8px;border-radius:50%;background:#2a3550}
.floor.lit .dot{background:currentColor;box-shadow:0 0 8px currentColor;animation:pulse 1.8s infinite}
@keyframes pulse{0%,100%{opacity:1}50%{opacity:.45}}
.floor.kernel{opacity:.5;border-left-color:#d4af37}
.ticker{max-height:44vh;overflow:auto;font-size:12px}
.tk{padding:6px 8px;border-bottom:1px solid #10192b}
.tk .w{color:#7dd3fc;font-weight:600}
.tk .f{color:var(--dim)}
.tk .m{color:var(--ink)}
.tk .need{color:#fbbf24}
.empty{color:var(--dim);font-style:italic;padding:10px}
.needs .nrow{padding:5px 8px;border-bottom:1px solid #10192b;font-size:12px}
.legend{display:flex;flex-wrap:wrap;gap:6px;margin-top:8px}
.lg{display:flex;align-items:center;gap:4px;font-size:10px;color:var(--dim)}
.lg i{width:9px;height:9px;border-radius:2px;display:inline-block}
footer{color:var(--dim);font-size:11px;padding:10px 20px;border-top:1px solid var(--edge);
 word-break:break-word}
.pill{display:inline-block;padding:1px 7px;border-radius:99px;background:#0a1526;border:1px solid var(--edge);
 font-size:11px;color:var(--dim)}
.live{color:#34d399}
a{color:#7dd3fc}
</style></head>
<body>
<header>
 <h1>QSB LIVING SKYSCRAPER</h1>
 <span class="sub" id="sub">connecting…</span>
 <span class="sub" style="margin-left:auto" id="clock"></span>
</header>
<div class="wrap">
 <div>
  <div class="card"><h2>Headline (real)</h2><div class="kpis" id="kpis"></div></div>
  <div class="card" style="margin-top:12px"><h2>What the floors need</h2>
   <div class="needs" id="needs"></div></div>
  <div class="card" style="margin-top:12px"><h2>Zones</h2>
   <div class="legend" id="legend"></div></div>
 </div>
 <div class="card"><h2>Building elevation — lit = real fresh traffic</h2>
  <div class="building" id="building"></div></div>
 <div class="card"><h2>Live worker ticker (real messages)</h2>
  <div class="ticker" id="ticker"></div></div>
</div>
<footer id="foot">source: …</footer>
<script>
const $=id=>document.getElementById(id);
function esc(s){return (s==null?'':String(s)).replace(/[&<>]/g,c=>({'&':'&amp;','<':'&lt;','>':'&gt;'}[c]));}
async function tick(){
 try{
  const r=await fetch('/api/state',{cache:'no-store'}); const s=await r.json();
  const h=s.headline;
  $('sub').innerHTML='<span class="live">● LIVE</span> '+h.floors_live+'/'+h.floors_total+' floors lit · '+h.messages_last_min+' msgs/min';
  $('clock').textContent=new Date(s.generated_ts).toLocaleTimeString();
  // KPIs
  const kp=[
   ['total_workers_canonical'in h&&h.total_workers_canonical!=null?h.total_workers_canonical:(h.total_workers_roster_sum||0),'workers on record'],
   [h.workers_active_last_window,'active / last '+h.active_window_min+'m'],
   [h.floors_live,'floors live'],
   [h.floors_dark,'floors dark'],
   [h.messages_last_min,'messages / min'],
   [h.worker_messages_seen,'worker msgs seen'],
  ];
  $('kpis').innerHTML=kp.map(k=>'<div class="kpi"><div class="n">'+esc(k[0])+'</div><div class="l">'+esc(k[1])+'</div></div>').join('');
  // building
  $('building').innerHTML=s.floors.map(f=>{
   const cls='floor'+(f.lit?' lit':'')+(f.kernel_reserved?' kernel':'');
   const age=f.age_s!=null?('· '+fmtAge(f.age_s)):'';
   return '<div class="'+cls+'" style="color:'+f.color+';border-left-color:'+f.color+'" title="'+esc(f.zone)+' — '+esc(f.signal||'')+' '+esc(age)+'">'
    +'<span class="dot"></span>'
    +'<span class="fn">F'+f.number+'</span>'
    +'<span class="lbl">'+esc((f.label||'').replace(/^F\d+\s*·\s*/,''))+'</span>'
    +'<span class="wc">'+(f.worker_count>0?('👤'+f.worker_count):(f.lit?'●':''))+'</span></div>';
  }).join('');
  // ticker
  const tk=s.ticker||[];
  $('ticker').innerHTML= tk.length? tk.map(m=>
    '<div class="tk"><span class="w">'+esc(m.worker_id||'worker')+'</span> '
    +'<span class="f">· F'+esc(m.floor)+' ·</span> '
    +'<span class="m">'+esc(m.message)+'</span>'
    +(m.need?' <span class="need">[need: '+esc(m.need)+']</span>':'')+'</div>'
   ).join('')
   : '<div class="empty">No worker messages on record yet. When the activation engine wakes the ~2000 workers, their REAL reports appear here. Shown honestly empty — nothing invented.</div>';
  // needs
  const nd=s.needs||[];
  $('needs').innerHTML= nd.length? nd.map(n=>
    '<div class="nrow">F'+esc(n.floor)+' · <b>'+esc(n.need)+'</b> <span class="f" style="color:var(--dim)">('+esc(n.worker_id)+')</span></div>'
   ).join('') : '<div class="empty">No open floor needs surfaced by workers right now.</div>';
  // legend
  const zc=s.zone_colors||{};
  $('legend').innerHTML=Object.entries(zc).map(([n,c])=>'<span class="lg"><i style="background:'+c+'"></i>'+esc(n)+'</span>').join('');
  // footer
  const p=s.provenance;
  $('foot').innerHTML='<span class="pill">READ-ONLY</span> sources: '+p.sources.map(esc).join(' · ')
   +' — activity-index @ '+esc(p.activity_index_generated_ts)+' ('+esc(p.activity_index_active_floors)+' active) · '
   +'worker log '+(p.worker_activity_log_present?'present':'EMPTY (honest)')+' · '
   +(p.perfloor_worker_files_with_data.length?('per-floor logs: '+p.perfloor_worker_files_with_data.length):'no per-floor worker logs yet')
   +' — '+esc(p.note);
 }catch(e){ $('sub').textContent='fetch error: '+e; }
}
function fmtAge(s){s=+s;if(s<90)return s+'s';if(s<5400)return Math.round(s/60)+'m';if(s<172800)return Math.round(s/3600)+'h';return Math.round(s/86400)+'d';}
tick(); setInterval(tick,3000);
</script>
</body></html>"""


class Handler(BaseHTTPRequestHandler):
    protocol_version = "HTTP/1.1"

    def log_message(self, *a):  # quiet
        pass

    def _send(self, code, body: bytes, ctype: str):
        self.send_response(code)
        self.send_header("Content-Type", ctype)
        self.send_header("Content-Length", str(len(body)))
        self.send_header("Cache-Control", "no-store")
        self.end_headers()
        try:
            self.wfile.write(body)
        except Exception:
            pass

    def do_GET(self):
        path = self.path.split("?", 1)[0]
        if path in ("/", "/index.html"):
            self._send(200, PAGE.encode("utf-8"), "text/html; charset=utf-8")
        elif path == "/api/state":
            body = json.dumps(get_state()).encode("utf-8")
            self._send(200, body, "application/json")
        elif path == "/api/health":
            body = json.dumps({"ok": True, "ts": datetime.now(timezone.utc).isoformat()}).encode()
            self._send(200, body, "application/json")
        else:
            self._send(404, b'{"ok":false,"error":"not found"}', "application/json")


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--port", type=int, default=8878)
    ap.add_argument("--host", default="0.0.0.0")
    args = ap.parse_args()
    srv = ThreadingHTTPServer((args.host, args.port), Handler)
    print(f"QSB Living Skyscraper (read-only) on http://{args.host}:{args.port}  (root {ROOT})")
    try:
        srv.serve_forever()
    except KeyboardInterrupt:
        pass


if __name__ == "__main__":
    main()
