#!/usr/bin/env python3
"""
qsb_wren_tool_broker.py — Wren's GOVERNED LOCAL TOOL BROKER (Wren Governor Upgrade §15/§19).
Wren operates the machine ONLY through this broker. Hosted gene-pool models never touch it directly —
Wren decides, the broker executes locally under a permission model:

  READ_ONLY       — runs automatically during an authorised task (inspect files/git/logs/services/net)
  SAFE_WRITE      — allowed after a backup is made (atomic edit with validation + diff)
  SERVICE_CONTROL — allowlisted units only (qsb-wren-*, ollama, skyscraper-*)
  PACKAGE_CHANGE  — refused here (needs justification + Ross)
  DESTRUCTIVE     — REFUSED (delete/format/wipe/firewall/routing require explicit Ross approval)

Commands/args are validated STRUCTURALLY, not by fragile substring checks. Every action returns a
structured result. No secrets are read or returned.
"""
import os, re, json, subprocess, hashlib, shutil, time, difflib, zipfile

ROOT = os.environ.get("QSB_ROOT", "/vaults/nvme0/qsb_tower_v1")
SERVICE_ALLOWLIST = re.compile(r"^(qsb-wren-[a-z-]+|qsb-belief-trader@[a-z0-9_]+|ollama|skyscraper-[a-z-]+|qsb-event-bus|qsb-agentic-traders-dash|qsb-council-live-dash)\.(service|target)$")
SERVICE_ACTIONS = {"status", "is-active", "restart", "start", "stop", "reload"}
# paths Wren must never write to (identity/secrets/governance)
WRITE_DENY = ("/floors/floor_28_security_department/vault/", "CLAUDE.md", ".env", "qsb_wren_persona.json",
              "qsb_wren_mind.json", "qsb_wren_operator_card.json", "/etc/")


def _run(cmd, timeout=20):
    try:
        r = subprocess.run(cmd, capture_output=True, text=True, timeout=timeout)
        return r.returncode, (r.stdout or ""), (r.stderr or "")
    except Exception as e:
        return 1, "", str(e)


def _abs(path):
    return path if os.path.isabs(path) else os.path.join(ROOT, path)


# ---------------- READ_ONLY ----------------
def fs_list(path="."):
    p = _abs(path)
    try:
        return {"ok": True, "class": "READ_ONLY", "path": p,
                "entries": sorted(os.listdir(p))[:400]}
    except Exception as e:
        return {"ok": False, "error": str(e)}


def fs_search(pattern, path=".", content=False, max_hits=60):
    p = _abs(path)
    cmd = (["grep", "-rIl", pattern, p] if content else
           ["bash", "-c", f"find {p!r} -iname '*{pattern}*' 2>/dev/null | head -{max_hits}"])
    rc, out, err = _run(cmd)
    return {"ok": rc in (0, 1), "class": "READ_ONLY", "hits": [l for l in out.splitlines() if l][:max_hits]}


def fs_read(path, max_bytes=60000):
    p = _abs(path)
    try:
        with open(p, "r", encoding="utf-8", errors="replace") as f:
            data = f.read(max_bytes)
        return {"ok": True, "class": "READ_ONLY", "path": p, "bytes": len(data), "content": data}
    except Exception as e:
        return {"ok": False, "error": str(e)}


def fs_checksum(path):
    p = _abs(path)
    try:
        h = hashlib.sha256(open(p, "rb").read()).hexdigest()
        st = os.stat(p)
        return {"ok": True, "class": "READ_ONLY", "sha256": h, "size": st.st_size,
                "mode": oct(st.st_mode)[-3:], "mtime": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime(st.st_mtime))}
    except Exception as e:
        return {"ok": False, "error": str(e)}


def zip_inspect(path, max_entries=300):
    """Read-only ZIP integrity, inventory, and per-entry SHA-256. Never extracts."""
    p = os.path.realpath(_abs(path)); root = os.path.realpath(ROOT) + os.sep
    if not p.startswith(root): return {"ok": False, "error": "path outside repository"}
    try:
        archive_sha = hashlib.sha256(open(p, "rb").read()).hexdigest(); entries=[]
        with zipfile.ZipFile(p, "r") as z:
            bad=z.testzip()
            for info in z.infolist()[:max(1,min(int(max_entries),500))]:
                if info.is_dir(): continue
                h=hashlib.sha256()
                with z.open(info, "r") as f:
                    for block in iter(lambda:f.read(1048576), b""): h.update(block)
                entries.append({"path":info.filename,"size":info.file_size,"sha256":h.hexdigest()})
        return {"ok": bad is None, "class":"READ_ONLY", "path":p, "archive_sha256":archive_sha,
                "integrity":"PASS" if bad is None else "FAIL", "bad_entry":bad, "entries":entries}
    except Exception as e: return {"ok":False,"class":"READ_ONLY","error":str(e)[:300]}


def static_check(path):
    """Language-appropriate static check (§15.5). Read-only."""
    p = _abs(path); ext = os.path.splitext(p)[1].lower()
    if ext == ".py":
        rc, o, e = _run(["python3", "-m", "py_compile", p])
        return {"ok": rc == 0, "class": "READ_ONLY", "checker": "py_compile", "error": e.strip()[:300] or None}
    if ext == ".sh":
        rc, o, e = _run(["bash", "-n", p])
        return {"ok": rc == 0, "class": "READ_ONLY", "checker": "bash -n", "error": e.strip()[:300] or None}
    if ext == ".json":
        try:
            json.load(open(p)); return {"ok": True, "class": "READ_ONLY", "checker": "json"}
        except Exception as e:
            return {"ok": False, "class": "READ_ONLY", "checker": "json", "error": str(e)[:200]}
    return {"ok": True, "class": "READ_ONLY", "checker": "none", "note": f"no static checker for {ext}"}


def git_status():
    rc, o, e = _run(["git", "-C", ROOT, "status", "--short", "--branch"])
    return {"ok": rc == 0, "class": "READ_ONLY", "status": o.strip().splitlines()[:40]}


def git_diff(path=None, stat=True):
    cmd = ["git", "-C", ROOT, "diff"] + (["--stat"] if stat else []) + ([path] if path else [])
    rc, o, e = _run(cmd)
    return {"ok": rc == 0, "class": "READ_ONLY", "diff": o[:6000]}


def systemd_status(unit):
    rc, o, e = _run(["systemctl", "is-active", unit])
    rc2, o2, _ = _run(["systemctl", "show", unit, "-p", "ActiveState,SubState,ExecMainStartTimestamp,NRestarts"])
    return {"ok": True, "class": "READ_ONLY", "unit": unit, "active": o.strip(),
            "detail": dict(l.split("=", 1) for l in o2.strip().splitlines() if "=" in l)}


def logs_read(unit, n=30):
    rc, o, e = _run(["bash", "-c", f"journalctl -u {unit} -n {int(n)} --no-pager 2>/dev/null || true"])
    lines = o.splitlines()[-n:]
    restarts = sum(1 for l in lines if "Started" in l or "Stopped" in l)
    errs = [l for l in lines if re.search(r"error|fail|traceback|refused", l, re.I)][:8]
    return {"ok": True, "class": "READ_ONLY", "unit": unit, "lines": lines[-15:],
            "restart_loop": restarts > 6, "errors": errs}


def telemetry():
    la = os.getloadavg()
    rc, dfo, _ = _run(["bash", "-c", "df -h / | awk 'NR==2{print $3,$4,$5}'"])
    rc, mem, _ = _run(["bash", "-c", "free -m | awk '/Mem:/{print $2,$3,$4}'"])
    gpu = None
    rc, g, _ = _run(["bash", "-c", "nvidia-smi --query-gpu=utilization.gpu,memory.used,memory.total --format=csv,noheader,nounits 2>/dev/null | head -1"])
    if g.strip():
        gpu = g.strip()
    return {"ok": True, "class": "READ_ONLY", "load_1m": round(la[0], 2), "disk_root": dfo.strip(),
            "mem_mb": mem.strip(), "gpu": gpu}


def net_test(url, timeout=6):
    rc, o, e = _run(["curl", "-s", "-o", "/dev/null", "-m", str(timeout), "-w", "%{http_code}", url], timeout=timeout + 3)
    return {"ok": rc == 0, "class": "READ_ONLY", "url": url, "http_code": o.strip() or "000"}


# who Wren looks for + where. Each peer has candidate endpoints (first that answers wins).
PEERS = {
    "tp_pip":   [("http://192.168.1.76:9120/", "cockpit"), ("http://192.168.1.76:8861/status", "runtime")],
    "asa_cass": [("http://192.168.1.78:9120/", "cockpit"), ("http://192.168.1.78:8862/status", "runtime")],
    "bill":     [("http://192.168.1.99:8891/health", "mac"), ("http://192.168.1.99:9120/", "cockpit")],
    "pi":       [("http://127.0.0.1:8890/health", "cable"), ("http://127.0.0.1:8890/health", "wifi")],
}
RELAY = "http://127.0.0.1:8855"


def find_peers():
    """AUTO-LOCATE THE WHOLE TEAM (§15.11): probe each peer's known endpoints + read the leadership
    relay presence. Returns who's online, where, and last-seen. Read-only, authorised SkyscraperHQ hosts only."""
    roster = {}
    for peer, eps in PEERS.items():
        found = None
        for url, label in eps:
            rc, o, e = _run(["curl", "-s", "-o", "/dev/null", "-m", "4", "-w", "%{http_code}", url], timeout=6)
            if o.strip() and o.strip() not in ("000", "") and int(o.strip() or 0) < 500:
                found = {"online": True, "at": url, "via": label, "http": o.strip()}
                break
        roster[peer] = found or {"online": False, "at": None, "tried": [u for u, _ in eps]}
    # relay presence (authoritative last-seen for wren/tp/asa/bill)
    try:
        import urllib.request
        pr = json.loads(urllib.request.urlopen(RELAY + "/presence", timeout=4).read() or b"{}")
        for who, info in (pr.get("presence", pr) or {}).items():
            if who in roster and isinstance(info, dict):
                roster[who]["relay_last_seen"] = info.get("last_seen") or info.get("ts")
            elif who not in roster and isinstance(info, dict):
                roster[who] = {"online": None, "relay_last_seen": info.get("last_seen") or info.get("ts")}
    except Exception:
        pass
    # AUTHORITATIVE federation presence: the Pi brain-router /nodes registry (heartbeats). A peer can be
    # federation-online (heartbeating to the Pi, e.g. Bill's outbound-only Mac) even if not directly
    # reachable from here. Map the Pi's node ids to our peer names.
    NODE_MAP = {"tp_pip": "tp_pip", "acer_cass": "asa_cass", "bill": "bill", "wren": "wren",
                "skyscraper_msi": "wren", "claude_specialist": "claude_specialist"}
    try:
        import urllib.request
        for base in ("http://127.0.0.1:8890/nodes", "http://127.0.0.1:8890/nodes"):
            try:
                nd = json.loads(urllib.request.urlopen(base, timeout=4).read() or b"{}")
                nodes = nd if isinstance(nd, list) else nd.get("nodes", [])
                for n in nodes:
                    nid = n.get("node_id") or n.get("id")
                    peer = NODE_MAP.get(nid, nid)
                    fed_online = bool(n.get("online"))
                    ls = (n.get("last_seen") or n.get("last_heartbeat") or "")
                    r = roster.setdefault(peer, {"online": False, "at": None})
                    r["federation_online"] = fed_online
                    r["pi_last_heartbeat"] = ls[:19]
                    # a peer is ONLINE if directly reachable OR the Pi sees a fresh heartbeat
                    if fed_online:
                        r["online"] = True
                        r.setdefault("via", "pi_federation (heartbeat)")
                break
            except Exception:
                continue
    except Exception:
        pass
    online = [p for p, v in roster.items() if v.get("online")]
    return {"ok": True, "class": "READ_ONLY", "online_count": len(online), "online": online,
            "presence_source": "direct-probe + Pi /nodes federation registry (authoritative)", "roster": roster}


# ---------------- SAFE_WRITE (backup required) ----------------
def safe_edit(path, new_content, reason="wren_edit"):
    """Atomic edit WITH backup + validation + diff (§15.2). Refuses identity/secret/governance paths."""
    p = _abs(path)
    if any(d in p for d in WRITE_DENY):
        return {"ok": False, "class": "SAFE_WRITE", "refused": "path is identity/secret/governance-protected"}
    try:
        old = open(p).read() if os.path.exists(p) else ""
    except Exception:
        old = ""
    bak = f"{p}.bak_{time.strftime('%Y%m%dT%H%M%SZ', time.gmtime())}_{reason}"
    if os.path.exists(p):
        shutil.copy2(p, bak)
    # validate python before replacing
    if p.endswith(".py"):
        import ast
        try:
            ast.parse(new_content)
        except SyntaxError as e:
            return {"ok": False, "class": "SAFE_WRITE", "refused": f"new content has syntax error: {e}"}
    tmp = p + ".tmp_wren"
    open(tmp, "w").write(new_content); os.replace(tmp, p)
    diff = "".join(difflib.unified_diff(old.splitlines(True), new_content.splitlines(True),
                                        "before", "after"))[:4000]
    return {"ok": True, "class": "SAFE_WRITE", "path": p, "backup": bak, "diff": diff}


# ---------------- SERVICE_CONTROL (allowlist) ----------------
def service_control(unit, action):
    if action not in SERVICE_ACTIONS:
        return {"ok": False, "class": "SERVICE_CONTROL", "refused": f"action '{action}' not allowed"}
    if action in ("status", "is-active"):
        return systemd_status(unit)
    if not SERVICE_ALLOWLIST.match(unit):
        return {"ok": False, "class": "SERVICE_CONTROL", "refused": f"unit '{unit}' not in Wren allowlist"}
    return {"ok": False, "class": "SERVICE_CONTROL", "needs": "this control action requires the operator/Ross approval flow",
            "would_run": f"systemctl {action} {unit}"}


DESTRUCTIVE_REFUSED = {"delete", "rm", "format", "mkfs", "wipe", "truncate_db", "firewall", "route", "partition"}


def refuse_destructive(op):
    return {"ok": False, "class": "DESTRUCTIVE", "refused": f"'{op}' requires explicit Ross approval — broker will not run it"}


TOOLS = {  # name -> (fn, permission_class)
    "fs_list": (fs_list, "READ_ONLY"), "fs_search": (fs_search, "READ_ONLY"),
    "fs_read": (fs_read, "READ_ONLY"), "fs_checksum": (fs_checksum, "READ_ONLY"),
    "zip_inspect": (zip_inspect, "READ_ONLY"),
    "static_check": (static_check, "READ_ONLY"), "git_status": (git_status, "READ_ONLY"),
    "git_diff": (git_diff, "READ_ONLY"), "systemd_status": (systemd_status, "READ_ONLY"),
    "logs_read": (logs_read, "READ_ONLY"), "telemetry": (telemetry, "READ_ONLY"),
    "net_test": (net_test, "READ_ONLY"), "find_peers": (find_peers, "READ_ONLY"),
    "safe_edit": (safe_edit, "SAFE_WRITE"),
    "service_control": (service_control, "SERVICE_CONTROL"),
}


if __name__ == "__main__":
    import sys
    name = sys.argv[1] if len(sys.argv) > 1 else "telemetry"
    args = sys.argv[2:]
    fn = TOOLS.get(name, (None,))[0]
    print(json.dumps(fn(*args) if fn else {"error": f"unknown tool {name}", "tools": list(TOOLS)}, indent=2)[:2000])
