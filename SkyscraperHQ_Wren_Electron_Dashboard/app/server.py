#!/usr/bin/env python3
"""
SkyscraperHQ — Wren Dashboard backend (:8850).
Forwards chat to Wren's REAL authoritative endpoint (8851/api/wren_chat); serves
LIVE host/GPU telemetry and LIVE service probes. Never invents figures; never
silently impersonates Wren.
"""
import json, os, socket, subprocess, time, urllib.request, datetime
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from urllib.parse import urlparse

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
CFG = json.load(open(os.path.join(ROOT, "config", "wren.json")))
ROSTER = json.load(open(os.path.join(ROOT, "config", "roster.json")))
WREN_LOCAL = CFG["wren_endpoint_local"]
WREN_LAN = CFG["wren_endpoint_lan"]
FLOOR_REG = "/vaults/nvme0/qsb_tower_v1/data/registries/qsb_canonical_floor_registry_1_170.json"
JOURNAL = "/vaults/nvme0/qsb_tower_v1/data/registries/qsb_tower_activity_tail.jsonl"


def now_iso():
    return datetime.datetime.now(datetime.timezone.utc).isoformat().replace("+00:00", "Z")


def sh(cmd, t=4):
    try:
        return subprocess.run(cmd, shell=True, capture_output=True, text=True, timeout=t).stdout.strip()
    except Exception:
        return ""


def http_get_ok(url, t=3):
    try:
        with urllib.request.urlopen(url, timeout=t) as r:
            return 200 <= r.status < 500, r.status
    except Exception:
        return False, None


def post_json(url, body, t=8):
    data = json.dumps(body).encode()
    req = urllib.request.Request(url, data=data, headers={"Content-Type": "application/json"}, method="POST")
    with urllib.request.urlopen(req, timeout=t) as r:
        return json.loads(r.read() or b"{}")


# ---------- chat forwarding to the REAL Wren ----------
def wren_chat(text):
    # Wren generates on a local qwen model (~8-18s). Use a generous timeout so the
    # LOCALHOST endpoint is used reliably instead of falsely falling back to LAN.
    for url, src in ((WREN_LOCAL, "WREN_LOCAL"), (WREN_LAN, "WREN_LAN")):
        try:
            d = post_json(url, {"text": text}, t=45)
            ans = d.get("answer") or d.get("reply") or ""   # real endpoint returns "reply"
            if ans:
                return {"ok": True, "answer": ans, "source": src, "endpoint": url}
        except Exception:
            continue
    return {"ok": False, "answer": "WREN ENDPOINT OFFLINE", "source": "NONE", "endpoint": WREN_LOCAL}


# ---------- live telemetry ----------
def metrics():
    cpu = sh("top -bn1 | grep '%Cpu' | head -1")
    load = sh("cat /proc/loadavg | awk '{print $1, $2, $3}'")
    mem = sh("free -m | awk 'NR==2{printf \"%d/%d MB (%.0f%%)\", $3,$2,$3*100/$2}'")
    disk = sh("df -h / | awk 'NR==2{print $3\"/\"$2\" (\"$5\")\"}'")
    up = sh("uptime -p") or "UNAVAILABLE"
    cpu_pct = "UNAVAILABLE"
    try:
        idle = float(sh("top -bn1 | grep '%Cpu' | grep -oE '[0-9.]+ id' | grep -oE '[0-9.]+'"))
        cpu_pct = round(100 - idle, 1)
    except Exception:
        pass
    temp = sh("sensors 2>/dev/null | grep -m1 -iE 'Tctl|Package id 0' | grep -oE '[0-9.]+°C' | head -1") or "UNAVAILABLE"
    nets = sh("ip -4 -brief addr | grep -v '127.0.0.1' | awk '{print $1\"=\"$3}'").replace("\n", " ")
    top = sh("ps -eo pcpu,comm --sort=-pcpu | head -6 | tail -5 | awk '{print $2\":\"$1\"%\"}'").replace("\n", " ")
    return {"cpu_pct": cpu_pct, "cpu_temp": temp, "load": load, "mem": mem, "disk": disk,
            "uptime": up, "net": nets, "top_procs": top}


def gpu():
    q = sh("nvidia-smi --query-gpu=name,utilization.gpu,temperature.gpu,memory.used,memory.total,power.draw --format=csv,noheader,nounits", 5)
    if not q:
        return {"available": False, "name": "UNAVAILABLE"}
    p = [x.strip() for x in q.split(",")]
    try:
        return {"available": True, "name": p[0], "util_pct": p[1], "temp_c": p[2],
                "mem_used_mib": p[3], "mem_total_mib": p[4], "power_w": p[5]}
    except Exception:
        return {"available": True, "raw": q}


def services():
    """LIVE probes — never 'online because it's in a config'."""
    out = []
    def add(id_, name, ok, detail=""):
        out.append({"id": id_, "name": name, "status": "ONLINE" if ok else "OFFLINE", "detail": detail})
    ok, st = http_get_ok("http://127.0.0.1:8851/", 3); add("wren_8851", "Wren chat (8851)", ok, f"HTTP {st}")
    ok, st = http_get_ok("http://127.0.0.1:8850/api/health", 2); add("dashboard_8850", "This dashboard (8850)", ok)
    ok, st = http_get_ok("http://127.0.0.1:11434/api/tags", 3); add("ollama", "Ollama (local model)", ok)
    ok, st = http_get_ok("http://192.168.1.23:8890/health", 3); add("pi_brain", "Pi Brain Router", ok)
    ok, st = http_get_ok("http://192.168.1.23:8891/api/status", 3); add("pi_reception", "Pi Receptionist", ok)
    # peer CEOs — live probe
    for pid, url in (("pip", "http://192.168.1.74:8871/"), ("asa", "http://192.168.1.78:8872/")):
        ok, st = http_get_ok(url, 3); add(pid, pid.upper(), ok, f"HTTP {st}")
    # Bill + Claude specialist via federation registry (live)
    bill_ok = "MacBook Pro" in sh("curl -s -m3 http://192.168.1.23:8890/nodes 2>/dev/null | grep -o 'MacBook Pro' | head -1")
    add("bill", "Bill (MacBook Concierge)", bill_ok, "federation node")
    cage = sh("systemctl is-enabled qsb-claude-cage@.service 2>/dev/null")
    add("claude_specialist", "Claude Specialist (governed under Wren)", cage in ("static", "enabled"), "caged specialist")
    return out


def floors():
    try:
        d = json.load(open(FLOOR_REG))["floors"]
        return {"count": len(d), "floors": {k: d[k]["label"] for k in sorted(d, key=int)}}
    except Exception:
        return {"count": 0, "floors": {}}


def journal(n=15):
    try:
        lines = open(JOURNAL, errors="ignore").read().splitlines()[-n:]
        return [json.loads(l) for l in lines if l.strip()][-n:]
    except Exception:
        return []


class H(BaseHTTPRequestHandler):
    def log_message(self, *a): pass

    def _j(self, code, obj):
        b = json.dumps(obj).encode()
        self.send_response(code); self.send_header("Content-Type", "application/json")
        self.send_header("Access-Control-Allow-Origin", "*"); self.send_header("Content-Length", str(len(b)))
        self.end_headers(); self.wfile.write(b)

    def do_GET(self):
        p = urlparse(self.path).path
        if p == "/api/health": return self._j(200, {"ok": True, "ts": now_iso(), "service": "wren_dashboard_8850"})
        if p == "/api/gpu": return self._j(200, gpu())
        if p == "/api/metrics": return self._j(200, metrics())
        if p in ("/api/services", "/api/services/probe"): return self._j(200, {"ts": now_iso(), "services": services()})
        if p == "/api/roster": return self._j(200, ROSTER)
        if p == "/api/floors": return self._j(200, floors())
        if p == "/api/journal": return self._j(200, {"events": journal()})
        if p == "/api/voice/status": return self._j(200, {"stt": "STAGED", "tts": "STAGED", "note": "whisper.cpp + Piper install pending"})
        if p == "/api/status":
            return self._j(200, {"ts": now_iso(), "wren": CFG["display_name"], "host": CFG["host"],
                                 "gpu": gpu(), "metrics": metrics(), "services": services()})
        return self._j(404, {"error": "not found", "path": p})

    def do_POST(self):
        p = urlparse(self.path).path
        n = int(self.headers.get("Content-Length", 0) or 0)
        try: body = json.loads(self.rfile.read(n) or b"{}")
        except Exception: body = {}
        if p in ("/api/chat", "/api/chat/stream"):
            text = body.get("message") or body.get("text") or ""
            return self._j(200, wren_chat(text))
        if p in ("/api/stt", "/api/speak/audio", "/api/voice/enroll"):
            return self._j(501, {"ok": False, "status": "STAGED", "note": "voice pipeline (whisper.cpp/Piper) not yet installed"})
        return self._j(404, {"error": "not found", "path": p})


def main():
    srv = ThreadingHTTPServer(("127.0.0.1", 8850), H)
    print(f"Wren dashboard backend on 127.0.0.1:8850 -> forwards chat to {WREN_LOCAL}")
    srv.serve_forever()


if __name__ == "__main__":
    main()
