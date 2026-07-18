#!/usr/bin/env python3
"""
SKYSCRAPERHQ HEARTBEAT CLIENT
action_id=PI-FEDERATION-DASHBOARD-V2

Runs ON each node (Bill/MacBook, Wren@MSI, TP-Pip, Acer-Cass, Claude-Specialist). Discovers
the Pi Brain Router, registers ONCE (authenticated), then heartbeats every 20s reporting local
service + model + current task + queue. Reconnects automatically after Pi or node restart.
Continues local operation regardless — this client only REPORTS, it never gates local work.

Auth: the shared federation service token (X-Service-Token) is read from a local env/arg. It is
NOT a cloud credential — it is the LAN federation secret. No cloud keys are used or stored here.

Usage:
  skyscraper_heartbeat_client.py --node-id bill --display "Bill" \
     --role "MacBook Executive Concierge" --floor 47 --host "MacBook Pro M1 Max" \
     --model qwen2.5:14b --local-health http://127.0.0.1:<concierge>/health \
     --ollama http://127.0.0.1:11434 --pi http://skyscraper-pi.local:8890 \
     --token-file /etc/skyscraperhq/federation.token
"""
import argparse, json, os, socket, time, urllib.request, urllib.error


def utc():
    import datetime
    return datetime.datetime.now(datetime.timezone.utc).isoformat().replace("+00:00", "Z")


def get(url, timeout=2):
    try:
        with urllib.request.urlopen(url, timeout=timeout) as r:
            return json.loads(r.read().decode()), True
    except Exception:
        return None, False


def post(url, body, token, timeout=5):
    data = json.dumps(body).encode()
    req = urllib.request.Request(url, data=data, headers={
        "Content-Type": "application/json", "X-Service-Token": token})
    try:
        with urllib.request.urlopen(req, timeout=timeout) as r:
            return json.loads(r.read().decode()), True
    except Exception as e:
        return {"error": type(e).__name__}, False


def resolve_pi(pi_arg):
    """Prefer skyscraper-pi.local; fall back to the given URL."""
    candidates = []
    if pi_arg:
        candidates.append(pi_arg)
    candidates.append("http://skyscraper-pi.local:8890")
    for c in candidates:
        h, ok = get(c + "/health", timeout=2)
        if ok:
            return c
    return pi_arg or candidates[-1]


def load_token(a):
    if a.token:
        return a.token
    if a.token_file and os.path.exists(a.token_file):
        txt = open(a.token_file).read().strip()
        if "=" in txt:  # accept KEY=VALUE env lines
            for line in txt.splitlines():
                if line.startswith("SKY_SERVICE_TOKEN=") or line.startswith("SKY_FEDERATION_TOKEN="):
                    return line.split("=", 1)[1].strip()
        return txt
    return os.environ.get("SKY_SERVICE_TOKEN", "")


def local_health(a):
    ok_c = get(a.local_health)[1] if a.local_health else None
    ok_o = get(a.ollama.rstrip("/") + "/api/tags")[1] if a.ollama else None
    return {"concierge_health": ok_c, "ollama_health": ok_o}


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--node-id", required=True)
    ap.add_argument("--display", default="")
    ap.add_argument("--role", default="")
    ap.add_argument("--floor", default="")
    ap.add_argument("--host", default="")
    ap.add_argument("--model", default="")
    ap.add_argument("--local-health", default="")
    ap.add_argument("--ollama", default="")
    ap.add_argument("--local-router", default="")
    ap.add_argument("--pi", default="http://skyscraper-pi.local:8890")
    ap.add_argument("--token", default="")
    ap.add_argument("--token-file", default="/etc/skyscraperhq/federation.token")
    ap.add_argument("--interval", type=int, default=20)
    a = ap.parse_args()

    token = load_token(a)
    if not token:
        print("FATAL: no federation token (need --token / --token-file / SKY_SERVICE_TOKEN)")
        raise SystemExit(2)

    reg = {"node_id": a.node_id, "display_name": a.display or a.node_id, "role": a.role,
           "owner": "Ross", "os": " ".join(os.uname()), "hostname": socket.gethostname(),
           "endpoint": a.local_router or a.local_health,
           "models": [a.model] if a.model else [], "kind": "physical_worker",
           "floor": a.floor, "physical_host": a.host}

    registered = False
    while True:
        pi = resolve_pi(a.pi)
        if not registered:
            r, ok = post(pi + "/nodes/register", reg, token)
            registered = ok
            print("%s register %s -> %s" % (utc(), a.node_id, "OK" if ok else r))
        hb = {"node_id": a.node_id, "ts": utc(), **local_health(a),
              "current_task": os.environ.get("SKY_CURRENT_TASK", ""),
              "queue_count": 0, "model": a.model}
        r, ok = post(pi + "/nodes/heartbeat", hb, token)
        if not ok:
            registered = False  # Pi restarted or unreachable -> re-register next loop
        time.sleep(a.interval)


if __name__ == "__main__":
    main()
