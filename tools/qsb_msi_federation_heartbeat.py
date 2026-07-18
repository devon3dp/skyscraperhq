#!/usr/bin/env python3
"""QSB SkyscraperHQ — ONE canonical MSI federation heartbeat service.
Reports THREE logical nodes from this one physical MSI host, each as a separate
authenticated node payload, every 20s, with bounded exponential backoff when the
Pi is unavailable. Reports only safe, observable information. Never transmits
Wren mind contents, Claude OAuth, API keys, passwords, reasoning or fs paths.
  - skyscraper_msi     (physical_host)
  - wren               (resident_ai_service, Governor L1, governor_level_2=false)
  - claude_specialist  (governed_specialist_service)
This service only REPORTS liveness; it never gates or alters local work."""
import json, os, socket, subprocess, time, urllib.request, datetime

TOKEN_FILE = os.environ.get("SKY_FED_TOKEN_FILE", "/vaults/nvme0/qsb_tower_v1/data/runtime/federation.token")
PIS = ["http://skyscraper-pi.local:8890", "http://192.168.1.23:8890", "http://192.168.1.24:8890"]
INTERVAL = 20

def utc():
    return datetime.datetime.now(datetime.timezone.utc).isoformat().replace("+00:00", "Z")

def token():
    try:
        t = open(TOKEN_FILE).read().strip()
        if "=" in t:
            for line in t.splitlines():
                if line.startswith("SKY_SERVICE_TOKEN=") or line.startswith("SKY_FEDERATION_TOKEN="):
                    return line.split("=", 1)[1].strip()
        return t
    except Exception:
        return ""

def _get_ok(url, timeout=3):
    try:
        with urllib.request.urlopen(url, timeout=timeout) as r:
            return 200 <= r.status < 500
    except Exception:
        return False

def _sh(cmd):
    try:
        return subprocess.check_output(cmd, shell=True, text=True, timeout=4, stderr=subprocess.DEVNULL).strip()
    except Exception:
        return ""

def resolve_pi():
    for c in PIS:
        if _get_ok(c + "/health", 2):
            return c
    return None

def post(pi, path, body, tok, timeout=5):
    req = urllib.request.Request(pi + path, data=json.dumps(body).encode(),
        headers={"Content-Type": "application/json", "X-Service-Token": tok})
    try:
        with urllib.request.urlopen(req, timeout=timeout) as r:
            return 200 <= r.status < 300
    except Exception:
        return False

HOST = socket.gethostname()
IP = _sh("ip route get 1.1.1.1 2>/dev/null | awk '{print $7; exit}'") or "192.168.1.72"

def regs():
    return [
        {"node_id": "skyscraper_msi", "display_name": "Skyscraper MSI Host", "role": "physical host",
         "owner": "Ross", "os": " ".join(os.uname()), "hostname": HOST, "endpoint": "",
         "models": [], "kind": "physical_worker", "physical_host": "MSI GPU host"},
        {"node_id": "wren", "display_name": "Wren", "role": "Governor L1 / heavy local AI",
         "owner": "Ross", "os": " ".join(os.uname()), "hostname": HOST,
         "endpoint": "http://192.168.1.72:8851",
         "models": ["codellama:13b", "qwen2.5:14b", "llama3.2:latest", "neural-chat:7b"],
         "kind": "physical_worker", "physical_host": "MSI GPU host"},
        {"node_id": "claude_specialist", "display_name": "Claude Specialist Caged Service",
         "role": "governed specialist (separate from Wren)", "owner": "Ross",
         "os": " ".join(os.uname()), "hostname": HOST, "endpoint": "",
         "models": [], "kind": "physical_worker", "physical_host": "MSI"},
    ]

def msi_hb():
    return {"node_id": "skyscraper_msi", "classification": "physical_host", "hostname": HOST,
            "ip": IP, "cpu": _sh("nproc"), "ram": _sh("free -h | awk 'NR==2{print $3\"/\"$2}'"),
            "gpu": _sh("nvidia-smi --query-gpu=utilization.gpu --format=csv,noheader 2>/dev/null | head -1"),
            "storage": _sh("df -h / | awk 'NR==2{print $3\"/\"$2\" (\"$5\")\"}'"),
            "host_health": "ok", "current_task": "idle", "ts": utc()}

def wren_hb():
    wren_ok = _get_ok("http://127.0.0.1:8851/status", 3)
    return {"node_id": "wren", "classification": "resident_ai_service", "role": "Governor Level 1",
            "governor_level_2": False, "wren_service_health": "online" if wren_ok else "unreachable",
            "models": ["codellama:13b", "qwen2.5:14b", "llama3.2:latest", "neural-chat:7b"],
            "local_router_health": "online" if wren_ok else "unknown",
            "current_task": "governing (safe summary)", "queue_count": 0, "ts": utc()}

def claude_hb():
    cage = _sh("systemctl is-active qsb-claude-cage@probe.service 2>/dev/null") or "inactive"
    return {"node_id": "claude_specialist", "classification": "governed_specialist_service",
            "cage": cage, "provider": "unavailable_no_paid_fallback", "governed_task_id": None,
            "queue_count": 0, "last_completed_report": None, "verifier_state": "idle",
            "current_task": "idle", "ts": utc()}

def main():
    tok = token()
    if not tok:
        print("FATAL: no federation token at", TOKEN_FILE); raise SystemExit(2)
    registered = False
    backoff = INTERVAL
    while True:
        pi = resolve_pi()
        if not pi:
            time.sleep(min(backoff, 160)); backoff = min(backoff * 2, 160); continue
        backoff = INTERVAL
        if not registered:
            ok_all = all(post(pi, "/nodes/register", r, tok) for r in regs())
            registered = ok_all
            print("%s register all3 -> %s" % (utc(), "OK" if ok_all else "partial"), flush=True)
        sent = 0
        for hb in (msi_hb(), wren_hb(), claude_hb()):
            if post(pi, "/nodes/heartbeat", hb, tok):
                sent += 1
            else:
                registered = False
        print("%s heartbeat %d/3 via %s" % (utc(), sent, pi), flush=True)
        time.sleep(INTERVAL)

if __name__ == "__main__":
    main()
