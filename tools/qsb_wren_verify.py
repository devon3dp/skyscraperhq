#!/usr/bin/env python3
"""
qsb_wren_verify.py — Wren's VERIFY / test-runner tool (Bill's-Claude spec #2, 2026-07-18).

The ABSOLUTE TRUTH RULE requires a REAL check before any 'done/live/online'. This tool runs
that check and returns the REAL result — so Wren can back a claim with evidence instead of
inventing one. Read-only / probe-only by default.

Verbs:
  endpoint <url>          GET an HTTP endpoint -> status + body snippet
  service  <unit>         systemctl is-active <unit>
  presence <id>           relay :8855 /presence for wren|tp|asa|bill
  file     <path>         exists? + size + sha256
  test     <pyfile>       run a python test file -> exit code + tail of output
  ollama   <model>        is a model present + a 1-token generation probe
"""
import sys, os, json, subprocess, hashlib, urllib.request

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


def endpoint(url):
    try:
        with urllib.request.urlopen(url, timeout=6) as r:
            body = r.read(400).decode(errors="ignore")
            return {"check": "endpoint", "url": url, "status": r.status, "ok": 200 <= r.status < 400, "body": body}
    except Exception as e:
        return {"check": "endpoint", "url": url, "ok": False, "error": str(e)}


def service(unit):
    out = subprocess.run(["systemctl", "is-active", unit], capture_output=True, text=True).stdout.strip()
    return {"check": "service", "unit": unit, "state": out, "ok": out == "active"}


def presence(cid):
    try:
        d = json.loads(urllib.request.urlopen("http://127.0.0.1:8855/status", timeout=5).read())["presence"]
        p = d.get(cid, {})
        return {"check": "presence", "id": cid, "online": bool(p.get("online")), "hb_age_s": p.get("age_s"), "ok": bool(p.get("online"))}
    except Exception as e:
        return {"check": "presence", "id": cid, "ok": False, "error": str(e)}


def file_check(path):
    p = path if os.path.isabs(path) else os.path.join(ROOT, path)
    if not os.path.exists(p):
        return {"check": "file", "path": path, "exists": False, "ok": False}
    b = open(p, "rb").read()
    return {"check": "file", "path": path, "exists": True, "size": len(b), "sha256": hashlib.sha256(b).hexdigest(), "ok": True}


def test(pyfile):
    p = pyfile if os.path.isabs(pyfile) else os.path.join(ROOT, pyfile)
    r = subprocess.run(["python3", p], capture_output=True, text=True, timeout=120)
    tail = (r.stdout + r.stderr).strip().splitlines()[-8:]
    return {"check": "test", "file": pyfile, "exit_code": r.returncode, "ok": r.returncode == 0, "tail": tail}


def ollama(model):
    try:
        tags = json.loads(urllib.request.urlopen("http://127.0.0.1:11434/api/tags", timeout=6).read())
        present = any(m["name"] == model for m in tags.get("models", []))
        gen = None
        if present:
            req = urllib.request.Request("http://127.0.0.1:11434/api/generate",
                data=json.dumps({"model": model, "prompt": "say OK", "stream": False, "options": {"num_predict": 5}}).encode(),
                headers={"Content-Type": "application/json"})
            gen = json.loads(urllib.request.urlopen(req, timeout=60).read()).get("response", "").strip()
        return {"check": "ollama", "model": model, "present": present, "gen": gen, "ok": present and bool(gen)}
    except Exception as e:
        return {"check": "ollama", "model": model, "ok": False, "error": str(e)}


VERBS = {"endpoint": endpoint, "service": service, "presence": presence, "file": file_check, "test": test, "ollama": ollama}

if __name__ == "__main__":
    if len(sys.argv) < 2 or sys.argv[1] not in VERBS:
        print(json.dumps({"error": "usage: qsb_wren_verify.py <verb> <arg>", "verbs": list(VERBS)})); sys.exit(2)
    if sys.argv[1] == "selftest":
        pass
    res = VERBS[sys.argv[1]](sys.argv[2] if len(sys.argv) > 2 else "")
    print(json.dumps(res, indent=2))
    sys.exit(0 if res.get("ok") else 1)
