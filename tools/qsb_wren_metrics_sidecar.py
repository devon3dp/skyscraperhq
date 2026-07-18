#!/usr/bin/env python3
from http.server import ThreadingHTTPServer, BaseHTTPRequestHandler
from pathlib import Path
from datetime import datetime, timezone, timedelta
import json, re
from urllib.parse import urlparse

PROJECT = Path("/vaults/nvme0/qsb_tower_v1")
REG = PROJECT / "data" / "registries"
TOOLS = PROJECT / "tools"
ART = PROJECT / "data" / "worker_artifacts"

def now():
    return datetime.now(timezone.utc).isoformat()

def tail(path, max_bytes=524288):
    try:
        p=Path(path)
        if not p.exists(): return []
        size=p.stat().st_size
        with p.open("rb") as f:
            if size > max_bytes:
                f.seek(size-max_bytes)
            raw=f.read()
        return raw.decode("utf-8","ignore").splitlines()
    except Exception as e:
        return [json.dumps({"tail_error":repr(e), "path":str(path)})]

def jsonl(path):
    out=[]
    for line in tail(path):
        try: out.append(json.loads(line))
        except Exception:
            if line.strip(): out.append({"raw": line[:500]})
    return out

def parse_ts(x):
    if not isinstance(x, dict): return None
    v=x.get("ts")
    if not v: return None
    try: return datetime.fromisoformat(str(v).replace("Z","+00:00"))
    except Exception: return None

def recent_count(items, hours=1):
    cutoff=datetime.now(timezone.utc)-timedelta(hours=hours)
    c=0
    for x in items:
        ts=parse_ts(x)
        if ts and ts >= cutoff:
            c += 1
    return c

def metrics():
    files = {
        "evolution": REG/"qsb_wren_evolution_cycles.jsonl",
        "bugs": REG/"qsb_wren_bug_catches.jsonl",
        "lessons": REG/"qsb_wren_lessons.jsonl",
        "jobs_done": REG/"qsb_wren_jobs_done.jsonl",
        "task_auto": REG/"qsb_task_council_auto_dispatcher_events.jsonl",
        "worker": REG/"qsb_worker_executor_verifier_events.jsonl",
        "dashboard_repair": REG/"qsb_dashboard_repair_worker_events.jsonl",
    }
    data={k: jsonl(v) for k,v in files.items()}
    tools_built=len(list(TOOLS.glob("qsb_*.py"))) + len(list(TOOLS.glob("skyscraper_*.py")))
    artifacts=len(list(ART.glob("*.json"))) if ART.exists() else 0
    rule_hits=0
    for f in files.values():
        rule_hits += len(re.findall(r"\bR\d{1,3}\b|rulebook|cited[-_ ]?rules?", "\n".join(tail(f)), flags=re.I))

    recent=sum(recent_count(v) for v in data.values())
    gauge=min(100, recent*10 + min(30, artifacts))

    return {
        "ok": True,
        "service": "Wren Metrics Sidecar",
        "ts": now(),
        "metrics": {
            "learnings_per_hour": recent,
            "tools_built": tools_built,
            "notes_cited_rules_count": rule_hits,
            "activity_gauge": gauge,
            "evolution_cycles_total": len(data["evolution"]),
            "evolution_cycles_per_hour": recent_count(data["evolution"]),
            "bug_catches_total": len(data["bugs"]),
            "bug_catches_per_hour": recent_count(data["bugs"]),
            "lessons_total": len(data["lessons"]),
            "jobs_done_total": len(data["jobs_done"]),
            "worker_artifacts": artifacts
        },
        "recent": {k: v[-6:] for k,v in data.items()},
        "doctrine": {
            "wren": "protected GPU guardian",
            "ceos": "API Gene Pool only",
            "no_key_changes": True,
            "no_trading": True
        }
    }

def html():
    return """<!doctype html><html><head><meta charset="utf-8">
<meta name=viewport content="width=device-width,initial-scale=1">
<title>Wren Metrics</title>
<style>
body{margin:0;background:#06110d;color:#eafff2;font:14px system-ui}
header{padding:18px 20px;background:#0b2518;border-bottom:1px solid #1f6b49}
h1{margin:0}.grid{display:grid;grid-template-columns:repeat(auto-fit,minmax(210px,1fr));gap:12px;padding:14px}
.card{background:#0b1c15;border:1px solid #1e5f43;border-radius:16px;padding:14px}
.k{opacity:.7;font-size:12px;text-transform:uppercase}.v{font-size:30px;font-weight:900;margin-top:8px}
pre{white-space:pre-wrap;background:#020805;border:1px solid #17432f;border-radius:14px;padding:12px;max-height:420px;overflow:auto}
</style></head><body>
<header><h1>🛡️ Wren Metrics · Live</h1><div>learnings/hour · tools built · notes cited-rules count · activity gauge · evolution cycles · bug catches</div></header>
<section class=grid>
<div class=card><div class=k>learnings/hour</div><div class=v id=a>…</div></div>
<div class=card><div class=k>tools built</div><div class=v id=b>…</div></div>
<div class=card><div class=k>notes cited-rules count</div><div class=v id=c>…</div></div>
<div class=card><div class=k>activity gauge</div><div class=v id=d>…</div></div>
<div class=card><div class=k>evolution cycles</div><div class=v id=e>…</div></div>
<div class=card><div class=k>bug catches</div><div class=v id=f>…</div></div>
</section>
<section class=grid><div class=card style="grid-column:1/-1"><pre id=raw>loading</pre></div></section>
<script>
async function tick(){
 const r=await fetch('/api/metrics',{cache:'no-store'}); const j=await r.json(); const m=j.metrics||{};
 a.textContent=m.learnings_per_hour??0; b.textContent=m.tools_built??0; c.textContent=m.notes_cited_rules_count??0;
 d.textContent=(m.activity_gauge??0)+'%'; e.textContent=m.evolution_cycles_total??0; f.textContent=m.bug_catches_total??0;
 raw.textContent=JSON.stringify(j,null,2);
}
tick(); setInterval(tick,1500);
</script></body></html>"""

class H(BaseHTTPRequestHandler):
    def sendit(self, code, body, ctype="application/json; charset=utf-8"):
        raw = body.encode() if isinstance(body,str) else json.dumps(body, indent=2, ensure_ascii=False).encode()
        self.send_response(code)
        self.send_header("Content-Type", ctype)
        self.send_header("Content-Length", str(len(raw)))
        self.send_header("Cache-Control", "no-store")
        self.end_headers()
        try: self.wfile.write(raw)
        except BrokenPipeError: pass
    def do_GET(self):
        p=urlparse(self.path).path
        if p in ("/","/metrics","/wren_metrics"):
            return self.sendit(200, html(), "text/html; charset=utf-8")
        if p in ("/health","/api/metrics","/api/wren_metrics"):
            return self.sendit(200, metrics())
        return self.sendit(404, {"ok":False,"path":p})

if __name__=="__main__":
    print("[BOOT] Wren Metrics Sidecar on 0.0.0.0:8853", flush=True)
    ThreadingHTTPServer(("0.0.0.0",8853),H).serve_forever()
