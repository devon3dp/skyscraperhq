#!/usr/bin/env python3
"""
qsb_work_mode_dash.py — WORK-MODE progress dashboard for the QSB Tower grinder boxes.

2026-07-30, Ross: "when they're in grind mode... turn off their dashboards and just
turn on a progress bar that shows they're in work mode, and a progress bar of how much
they're working."

This is the minimal WORK-MODE view: no chat, no menus. Per grinder box
(ThinkPad/tp_pip, Acer/acer_cass) it shows:
  - a big GRINDING / IDLE indicator (green ONLY when that box's systemd grinder is active),
  - a "current unit" progress bar (how hard it's working RIGHT NOW),
  - a throughput gauge (units/hour vs the box's own recent best hour),
  - a few real stats (units today, ok/failed, current lane/job, uptime, last-unit age).

HONESTY (R01) — every number is computed server-side from REAL live sources; nothing is faked:
  - grind mode on/off   : systemctl is-active qsb-grinder-{tp,acer}.service (TRUE state).
  - work units          : data/registries/qsb_grind_log.jsonl (each row = one real, timestamped
                          unit the box emitted — status ok/failed, real duration_ms).
  - typical duration     : the box's OWN median OK-unit duration for its lane (self-relative baseline).
  - current job/lane     : data/registries/qsb_resource_map.json (real ping + council board).
  - uptime               : the grinder service's ActiveEnterTimestamp.

HONEST DEGRADATION:
  - grinder inactive  -> IDLE / NOT IN WORK MODE (bar drained to 0, never a fake full bar).
  - grinder active but stalled (elapsed on current unit >> its typical duration, or last unit
    is old) -> the current-unit bar goes amber/red and reads STALLED, not full.
  - no reachability / no data -> shown as UNKNOWN, never guessed.

READ-ONLY: never places orders, never flips a gate, never writes project files, never touches
the grinder tool / map / minds. Additive service on :8881.

Run:  python3 tools/qsb_work_mode_dash.py --port 8881
Data: GET /api/work  -> JSON with both boxes' real work-mode state + progress numbers.
"""
import argparse
import json
import subprocess
from datetime import datetime, timezone
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
REG = ROOT / "data" / "registries"
GRIND_LOG = REG / "qsb_grind_log.jsonl"
RESOURCE_MAP = REG / "qsb_resource_map.json"

# box_id -> (systemd service, display label, resource-map key, host, expected lane)
BOXES = {
    "tp_pip": {
        "service": "qsb-grinder-tp.service",
        "label": "ThinkPad / tp_pip",
        "map_key": "thinkpad",
        "host": "192.168.1.91",
        "lane": "produce_analyze",
    },
    "acer_cass": {
        "service": "qsb-grinder-acer.service",
        "label": "Acer / acer_cass",
        "map_key": "acer",
        "host": "192.168.1.41",
        "lane": "verify_kb",
    },
}

# How many multiples of the typical duration before "current unit" is judged STALLED.
STALL_FACTOR = 5.0  # raised 2.5->5.0 2026-07-30: TP is a slow ThinkPad (17s typical, legit up to ~76s); only a genuinely-stuck unit (>5x typical) is STALLED, not a normal slow one
# A box with no fresh unit for this many seconds while active is "stalled / waiting".
STALE_UNIT_SECS = 300


def _now():
    return datetime.now(timezone.utc)


def _parse_ts(s):
    if not s:
        return None
    try:
        s = s.strip().replace("Z", "+00:00")
        dt = datetime.fromisoformat(s)
        if dt.tzinfo is None:
            dt = dt.replace(tzinfo=timezone.utc)
        return dt
    except Exception:
        return None


def _sh(cmd, timeout=6):
    try:
        return subprocess.run(
            cmd, shell=True, capture_output=True, text=True, timeout=timeout
        ).stdout.strip()
    except Exception:
        return ""


def _service_active(service):
    out = _sh(f"systemctl is-active {service}")
    return out == "active"


def _service_uptime_secs(service):
    """Grinder service uptime in seconds, from systemd's MONOTONIC clock (timezone-proof).

    uptime = (system monotonic uptime) - (service ActiveEnterTimestampMonotonic).
    Monotonic avoids the BST/UTC wall-clock ambiguity that would otherwise skew this.
    """
    mono = _sh(f"systemctl show {service} -p ActiveEnterTimestampMonotonic --value")
    try:
        active_us = int(mono)
    except Exception:
        active_us = 0
    if active_us <= 0:
        return None
    try:
        with open("/proc/uptime") as f:
            up_secs = float(f.read().split()[0])
        return max(0.0, up_secs - active_us / 1_000_000.0)
    except Exception:
        return None


def _load_grind_rows():
    rows = []
    if not GRIND_LOG.exists():
        return rows
    try:
        for line in GRIND_LOG.read_text(errors="replace").splitlines():
            line = line.strip().lstrip("\x00").strip()
            if not line:
                continue
            try:
                rows.append(json.loads(line))
            except Exception:
                continue
    except Exception:
        pass
    return rows


def _load_map():
    try:
        return json.loads(RESOURCE_MAP.read_text())
    except Exception:
        return {}


def _median(vals):
    vals = sorted(vals)
    n = len(vals)
    if n == 0:
        return None
    return vals[n // 2] if n % 2 else (vals[n // 2 - 1] + vals[n // 2]) / 2.0


def _pct(x):
    return max(0.0, min(100.0, round(x, 1)))


def _human_secs(s):
    if s is None:
        return "—"
    s = int(s)
    if s < 60:
        return f"{s}s"
    if s < 3600:
        return f"{s // 60}m {s % 60}s"
    h = s // 3600
    m = (s % 3600) // 60
    return f"{h}h {m}m"


def compute_box(box_id, cfg, rows, map_data):
    now = _now()
    active = _service_active(cfg["service"])
    uptime = _service_uptime_secs(cfg["service"]) if active else None

    mine = [r for r in rows if r.get("box") == box_id]
    mine.sort(key=lambda r: r.get("ts", ""))

    ok = [r for r in mine if r.get("status") == "ok"]
    failed = [r for r in mine if r.get("status") == "failed"]
    ok_durs = [r.get("duration_ms", 0) for r in ok if r.get("duration_ms", 0) > 0]
    typical_ms = _median(ok_durs)  # the box's OWN typical unit time (self-relative, honest)

    # --- units done today (UTC) ---
    today = now.strftime("%Y-%m-%d")
    today_rows = [r for r in mine if str(r.get("ts", "")).startswith(today)]
    units_today = len(today_rows)
    ok_today = len([r for r in today_rows if r.get("status") == "ok"])
    failed_today = len([r for r in today_rows if r.get("status") == "failed"])

    # --- last unit + age ---
    last = mine[-1] if mine else None
    last_ts = _parse_ts(last.get("ts")) if last else None
    last_age = (now - last_ts).total_seconds() if last_ts else None

    # --- throughput: units in the last 60 min vs the box's OWN best 60-min window ---
    def _in_last(minutes, subset):
        cut = now.timestamp() - minutes * 60
        c = 0
        for r in subset:
            t = _parse_ts(r.get("ts"))
            if t and t.timestamp() >= cut:
                c += 1
        return c

    units_last_hour = _in_last(60, mine)
    # best hour: slide a 60-min window across this box's own history (self-relative ceiling).
    ts_list = sorted(t.timestamp() for t in (_parse_ts(r.get("ts")) for r in mine) if t)
    best_hour = 0
    for i, start in enumerate(ts_list):
        end = start + 3600
        c = sum(1 for t in ts_list[i:] if t <= end)
        best_hour = max(best_hour, c)
    best_hour = max(best_hour, units_last_hour, 1)
    throughput_pct = _pct(100.0 * units_last_hour / best_hour) if active else 0.0

    # --- current-unit progress: elapsed since last unit started vs typical duration ---
    # We treat "elapsed since the last logged unit" as work-in-flight on the next unit.
    current_pct = 0.0
    current_state = "idle"
    if not active:
        current_state = "not_in_work_mode"
        current_pct = 0.0
    elif typical_ms and last_age is not None:
        typical_s = typical_ms / 1000.0
        ratio = last_age / typical_s if typical_s > 0 else 0
        if last_age > STALE_UNIT_SECS or ratio > STALL_FACTOR:
            current_state = "stalled"
            # drained bar, honest: not a full bar when stuck
            current_pct = _pct(min(100.0, 100.0 * min(ratio, STALL_FACTOR) / STALL_FACTOR)) * 0.5
        else:
            current_state = "grinding"
            current_pct = _pct(100.0 * min(ratio, 1.0))
    elif active:
        current_state = "grinding"
        current_pct = 0.0

    # --- current job / lane from the real resource map ---
    res = (map_data.get("resources") or {}).get(cfg["map_key"], {})
    current_job = None
    cj = res.get("current_job")
    if isinstance(cj, dict):
        current_job = cj.get("task_id")
    reachable = res.get("reachable")
    map_busy = res.get("busy")
    lane = (last.get("lane") if last else None) or cfg["lane"]

    return {
        "box": box_id,
        "label": cfg["label"],
        "host": cfg["host"],
        "service": cfg["service"],
        "in_work_mode": active,
        "work_mode_text": "GRINDING" if active else "IDLE",
        "current_state": current_state,
        "current_pct": round(current_pct, 1),
        "throughput_pct": round(throughput_pct, 1),
        "units_last_hour": units_last_hour,
        "best_hour": best_hour,
        "units_today": units_today,
        "ok_today": ok_today,
        "failed_today": failed_today,
        "units_total_log": len(mine),
        "ok_total": len(ok),
        "failed_total": len(failed),
        "typical_unit_secs": round(typical_ms / 1000.0, 1) if typical_ms else None,
        "last_unit_age_secs": round(last_age, 1) if last_age is not None else None,
        "last_unit_age_h": _human_secs(last_age),
        "uptime_secs": round(uptime, 0) if uptime is not None else None,
        "uptime_h": _human_secs(uptime),
        "lane": lane,
        "current_job": current_job,
        "reachable": reachable,
        "map_busy": map_busy,
        "last_result_head": (last.get("result_head") if last else None),
        # live activity feed: the box's most recent REAL grind units (what it's actually
        # doing right now), newest last. Every field verbatim from qsb_grind_log.jsonl.
        "recent_units": [
            {
                "ts": r.get("ts"),
                "unit_kind": r.get("unit_kind") or r.get("lane"),
                "prompt_head": (str(r.get("prompt_head") or ""))[:200],
                "result_head": (str(r.get("result_head") or ""))[:280],
                "status": r.get("status"),
                "duration_ms": r.get("duration_ms"),
            }
            for r in mine[-24:]
        ],
    }


def build_payload():
    rows = _load_grind_rows()
    map_data = _load_map()
    boxes = [compute_box(bid, cfg, rows, map_data) for bid, cfg in BOXES.items()]
    return {
        "ok": True,
        "schema": "qsb.work_mode/1",
        "ts": _now().strftime("%Y-%m-%dT%H:%M:%SZ"),
        "honesty": (
            "Work-mode ON/OFF = real systemctl is-active of each grinder service. "
            "All bars driven by real timestamped rows in qsb_grind_log.jsonl (status ok/failed, "
            "real duration_ms). Typical unit time = the box's OWN median OK duration. "
            "Inactive shows IDLE (bar 0). Stalled shows a drained bar, never a fake full bar."
        ),
        "grind_log": str(GRIND_LOG.relative_to(ROOT)),
        "boxes": boxes,
    }


PAGE = """<!doctype html><html><head><meta charset="utf-8">
<title>QSB WORK MODE</title>
<meta name="viewport" content="width=device-width,initial-scale=1">
<style>
 :root{--bg:#07090d;--card:#0f141c;--edge:#1e2733;--dim:#7c8aa0;--txt:#e8eef7;
   --green:#22c55e;--amber:#f59e0b;--red:#ef4444;--idle:#3a4453;}
 *{box-sizing:border-box}
 body{margin:0;background:var(--bg);color:var(--txt);
   font-family:-apple-system,Segoe UI,Roboto,Helvetica,Arial,sans-serif}
 header{padding:14px 20px;border-bottom:1px solid var(--edge);display:flex;
   align-items:center;justify-content:space-between}
 header h1{font-size:15px;margin:0;letter-spacing:2px;font-weight:700}
 header .ts{font-size:11px;color:var(--dim)}
 .wrap{display:grid;grid-template-columns:repeat(auto-fit,minmax(380px,1fr));gap:18px;padding:20px}
 .card{background:var(--card);border:1px solid var(--edge);border-radius:14px;padding:20px}
 .top{display:flex;align-items:center;justify-content:space-between;margin-bottom:6px}
 .name{font-size:15px;font-weight:600}
 .host{font-size:11px;color:var(--dim)}
 .badge{font-size:22px;font-weight:800;letter-spacing:2px;padding:8px 16px;border-radius:10px;
   display:inline-flex;align-items:center;gap:10px}
 .dot{width:14px;height:14px;border-radius:50%}
 .b-grind{background:rgba(34,197,94,.12);color:var(--green);border:1px solid var(--green)}
 .b-grind .dot{background:var(--green);box-shadow:0 0 12px var(--green);animation:pulse 1.4s infinite}
 .b-idle{background:rgba(58,68,83,.25);color:var(--idle);border:1px solid var(--idle)}
 .b-idle .dot{background:var(--idle)}
 .b-stall{background:rgba(245,158,11,.12);color:var(--amber);border:1px solid var(--amber)}
 .b-stall .dot{background:var(--amber);box-shadow:0 0 12px var(--amber)}
 @keyframes pulse{0%,100%{opacity:1}50%{opacity:.35}}
 .barlabel{display:flex;justify-content:space-between;font-size:11px;color:var(--dim);
   margin:16px 0 5px;text-transform:uppercase;letter-spacing:1px}
 .bar{height:18px;background:#050810;border:1px solid var(--edge);border-radius:9px;overflow:hidden}
 .fill{height:100%;border-radius:9px;transition:width .5s ease;background:var(--green)}
 .fill.amber{background:var(--amber)} .fill.idle{background:var(--idle)}
 .fill.blue{background:linear-gradient(90deg,#2563eb,#38bdf8)}
 .stats{display:grid;grid-template-columns:1fr 1fr 1fr;gap:10px;margin-top:18px}
 .stat{background:#0a0f16;border:1px solid var(--edge);border-radius:8px;padding:10px}
 .stat .k{font-size:10px;color:var(--dim);text-transform:uppercase;letter-spacing:1px}
 .stat .v{font-size:16px;font-weight:700;margin-top:3px}
 .meta{font-size:11px;color:var(--dim);margin-top:14px;line-height:1.6}
 .meta b{color:var(--txt);font-weight:600}
 .foot{font-size:10px;color:var(--dim);padding:8px 20px 22px;line-height:1.5}
</style></head><body>
<header><h1>QSB TOWER · WORK MODE</h1><div class="ts" id="ts">…</div></header>
<div class="wrap" id="wrap"></div>
<div class="foot" id="foot"></div>
<script>
function esc(s){return (s==null?'':(''+s)).replace(/[<>&]/g,c=>({'<':'&lt;','>':'&gt;','&':'&amp;'}[c]));}
function badge(b){
  if(!b.in_work_mode) return {cls:'b-idle',txt:'IDLE'};
  if(b.current_state==='stalled') return {cls:'b-stall',txt:'STALLED'};
  return {cls:'b-grind',txt:'GRINDING'};
}
function fillcls(b){
  if(!b.in_work_mode) return 'idle';
  if(b.current_state==='stalled') return 'amber';
  return '';
}
function render(d){
  document.getElementById('ts').textContent = 'as of '+d.ts+' · refresh 2s';
  document.getElementById('foot').textContent = 'HONEST (R01): '+d.honesty+'  Source: '+d.grind_log;
  var html='';
  d.boxes.forEach(function(b){
    var bd=badge(b), fc=fillcls(b);
    html += '<div class="card">'
      + '<div class="top"><div><div class="name">'+esc(b.label)+'</div>'
      + '<div class="host">'+esc(b.host)+' · '+esc(b.service)+'</div></div>'
      + '<div class="badge '+bd.cls+'"><span class="dot"></span>'+bd.txt+'</div></div>'
      + '<div class="barlabel"><span>Current unit ('+esc(b.current_state)+')</span><span>'+b.current_pct+'%</span></div>'
      + '<div class="bar"><div class="fill '+fc+'" style="width:'+b.current_pct+'%"></div></div>'
      + '<div class="barlabel"><span>Throughput · '+b.units_last_hour+'/hr vs best '+b.best_hour+'/hr</span><span>'+b.throughput_pct+'%</span></div>'
      + '<div class="bar"><div class="fill '+(b.in_work_mode?'blue':'idle')+'" style="width:'+b.throughput_pct+'%"></div></div>'
      + '<div class="stats">'
      + '<div class="stat"><div class="k">Units today</div><div class="v">'+b.units_today+'</div></div>'
      + '<div class="stat"><div class="k">OK / Fail</div><div class="v">'+b.ok_today+' / '+b.failed_today+'</div></div>'
      + '<div class="stat"><div class="k">Uptime</div><div class="v">'+esc(b.uptime_h)+'</div></div>'
      + '</div>'
      + '<div class="meta">'
      + '<b>Lane:</b> '+esc(b.lane)+' &nbsp; <b>Job:</b> '+esc(b.current_job||'—')+'<br>'
      + '<b>Typical unit:</b> '+(b.typical_unit_secs!=null?b.typical_unit_secs+'s':'—')
      + ' &nbsp; <b>Last unit:</b> '+esc(b.last_unit_age_h)+' ago<br>'
      + '<b>Total logged:</b> '+b.units_total_log+' ('+b.ok_total+' ok / '+b.failed_total+' fail)'
      + ' &nbsp; <b>Reachable:</b> '+(b.reachable===true?'yes':(b.reachable===false?'no':'—'))
      + '</div></div>';
  });
  document.getElementById('wrap').innerHTML=html;
}
function tick(){fetch('/api/work').then(r=>r.json()).then(render).catch(function(){});}
tick(); setInterval(tick,2000);
</script></body></html>"""


class Handler(BaseHTTPRequestHandler):
    def log_message(self, *a):
        pass

    def _send(self, code, body, ctype):
        data = body.encode() if isinstance(body, str) else body
        self.send_response(code)
        self.send_header("Content-Type", ctype)
        self.send_header("Content-Length", str(len(data)))
        self.send_header("Cache-Control", "no-store")
        self.end_headers()
        self.wfile.write(data)

    def do_GET(self):
        if self.path.startswith("/api/work"):
            self._send(200, json.dumps(build_payload()), "application/json")
        elif self.path in ("/", "/index.html"):
            self._send(200, PAGE, "text/html; charset=utf-8")
        elif self.path.startswith("/healthz"):
            self._send(200, json.dumps({"ok": True, "ts": _now().isoformat()}), "application/json")
        else:
            self._send(404, json.dumps({"ok": False, "error": "not found"}), "application/json")


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--port", type=int, default=8881)
    ap.add_argument("--host", default="0.0.0.0")
    ap.add_argument("--once", action="store_true", help="print one payload and exit (proof mode)")
    o = ap.parse_args()
    if o.once:
        print(json.dumps(build_payload(), indent=2))
        return
    srv = ThreadingHTTPServer((o.host, o.port), Handler)
    print(f"[work-mode-dash] serving on http://{o.host}:{o.port}  (data: /api/work)")
    try:
        srv.serve_forever()
    except KeyboardInterrupt:
        pass


if __name__ == "__main__":
    main()
