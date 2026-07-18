#!/usr/bin/env python3
"""
QSB Node Registry (Ross/ChatGPT 2026-07-09 Priority F).
Probes every tower node for REAL current status and writes
data/registries/qsb_node_registry.json. No hardcoded stale addresses:
TP/Acer candidate addresses are probed and the first LIVE one wins.

Each node reports: name, role, ip, port, dashboard_url, last_seen,
model_status, task_status, http, latency_ms, ok, error.

Run: python3 tools/qsb_node_registry.py   (writes registry, prints summary)
"""
import json, time, urllib.request, socket
from datetime import datetime, timezone
from pathlib import Path

REG = Path("/vaults/nvme0/qsb_tower_v1/data/registries")
OUT = REG / "qsb_node_registry.json"

def _now():
    return datetime.now(timezone.utc).isoformat()

def _probe(url, timeout=3.0):
    t0 = time.time()
    try:
        with urllib.request.urlopen(url, timeout=timeout) as r:
            r.read(256)
            return {"ok": 200 <= r.status < 400, "http": r.status,
                    "latency_ms": round((time.time() - t0) * 1000), "error": ""}
    except urllib.error.HTTPError as e:
        return {"ok": 200 <= e.code < 400, "http": e.code,
                "latency_ms": round((time.time() - t0) * 1000), "error": f"HTTP {e.code}"}
    except Exception as e:
        return {"ok": False, "http": 0, "latency_ms": round((time.time() - t0) * 1000),
                "error": type(e).__name__ + ": " + str(e)[:100]}

# node definitions — for TP/Acer we list CANDIDATE addresses (probed in order, first live wins)
NODES = [
    {"name": "Claude HQ",  "role": "Orchestrator",            "candidates": ["127.0.0.1:8850"], "health": "/"},
    {"name": "Wren",       "role": "Designer / kernel mind",  "candidates": ["127.0.0.1:8851"], "health": "/"},
    {"name": "Wren metrics","role": "Wren metrics sidecar",   "candidates": ["127.0.0.1:8853"], "health": "/health"},
    {"name": "Boardroom",  "role": "Task Council hub",        "candidates": ["127.0.0.1:8852"], "health": "/"},
    {"name": "Gene Pool",  "role": "Brain Router V4",         "candidates": ["127.0.0.1:8860"], "health": "/health"},
    # 2026-07-11 S4A hardware-true: physical worker endpoints first. TP-Pip=Lenovo ThinkPad
    # DESKTOP-9RBVKSM 192.168.1.74:8871 ; Acer-Cass=Acer Aspire DESKTOP-1E2FB5N 192.168.1.41:8872.
    {"name": "TP-Pip",     "role": "Research / verification", "candidates": ["192.168.1.74:8871"], "health": "/"},
    {"name": "Acer-Cass",  "role": "Data Foundry",            "candidates": ["192.168.1.41:8872"], "health": "/"},
]

def build():
    nodes = []
    for spec in NODES:
        chosen = None
        for addr in spec["candidates"]:
            res = _probe(f"http://{addr}{spec['health']}")
            if res["ok"]:
                ip, port = addr.split(":")
                chosen = {"addr": addr, "ip": ip, "port": int(port), **res}
                break
        if not chosen:  # none live — report the first candidate as down
            addr = spec["candidates"][0]; ip, port = addr.split(":")
            res = _probe(f"http://{addr}{spec['health']}")
            chosen = {"addr": addr, "ip": ip, "port": int(port), **res}
        nodes.append({
            "name": spec["name"], "role": spec["role"],
            "ip": chosen["ip"], "port": chosen["port"],
            "dashboard_url": f"http://{chosen['addr']}/",
            "last_seen": _now() if chosen["ok"] else None,
            "model_status": "reachable" if chosen["ok"] else "unreachable",
            "task_status": "available" if chosen["ok"] else "down",
            "http": chosen["http"], "latency_ms": chosen["latency_ms"],
            "ok": chosen["ok"], "error": chosen["error"],
        })
    reg = {"ts": _now(), "nodes": nodes,
           "up": sum(1 for n in nodes if n["ok"]), "total": len(nodes)}
    OUT.write_text(json.dumps(reg, indent=2))
    return reg

if __name__ == "__main__":
    reg = build()
    print(f"[registry] {reg['up']}/{reg['total']} nodes up -> {OUT}")
    for n in reg["nodes"]:
        flag = "OK " if n["ok"] else "DOWN"
        print(f"  {flag} {n['name']:14} {n['ip']}:{n['port']:<5} {n['http']} {n['latency_ms']}ms {n['error']}")
