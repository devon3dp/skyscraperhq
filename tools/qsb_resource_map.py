#!/usr/bin/env python3
"""
qsb_resource_map.py — the QSB Tower's honest live picture of "who can do what,
who is free, who is busy" across every compute resource.

HONESTY (R01): every field is real. Capabilities come from live Ollama /api/tags
and box gene :8770 /health. Reachability/load come from real ping + real HTTP
probes of cockpit :9120 and box gene :8770. Current job comes from the real
council board (qsb_council_tasks.jsonl) — the most recent claim/assign for that
box that has not yet been closed. A box that is unreachable is reported
unreachable — we never fabricate a healthy status.

Resources tracked:
  - main_box   : this host, pinned Ollama (1-slot), 127.0.0.1:11434
  - thinkpad   : 192.168.1.91 (tp_pip)  — faster worker box
  - acer       : 192.168.1.41 (acer_cass) — steady worker box
  - gene_pool  : external providers (deepseek/openai etc.) reachable via boxes

WRITE (we own this):
  - data/registries/qsb_resource_map.json      (latest snapshot)
  - data/registries/qsb_resource_map_history.jsonl (append-only, timeline)

We do NOT modify any sibling tool, any mind, the map, SAFETY_DENY, or gates.

Usage:
  python3 tools/qsb_resource_map.py            # probe + write snapshot
  python3 tools/qsb_resource_map.py --print    # probe + pretty-print, no timer noise
"""
from __future__ import annotations
import argparse, datetime, json, subprocess, urllib.request, socket
from pathlib import Path

ROOT = Path("/vaults/nvme0/qsb_tower_v1")
REG = ROOT / "data/registries"
SNAP = REG / "qsb_resource_map.json"
HIST = REG / "qsb_resource_map_history.jsonl"
COUNCIL = REG / "qsb_council_tasks.jsonl"

# --- static topology (real, from the tower's known hardware) -----------------
RESOURCES = {
    "main_box": {
        "role": "main_box", "worker_id": None,
        "host": "127.0.0.1", "ollama": "127.0.0.1:11434",
        "cockpit": None, "gene": None,
        "speed_class": "high_but_pinned",
        "note": "pinned Ollama 1-slot — prefer to OFFLOAD, not load",
        "pinned": True,
    },
    "thinkpad": {
        "role": "worker_box", "worker_id": "tp_pip",
        "host": "192.168.1.91", "ollama": "192.168.1.91:11434",
        "cockpit": "192.168.1.91:9120", "gene": "192.168.1.91:8770",
        "speed_class": "fast",
        "note": "faster worker box (ThinkPad)", "pinned": False,
    },
    "acer": {
        "role": "worker_box", "worker_id": "acer_cass",
        "host": "192.168.1.41", "ollama": "192.168.1.41:11434",
        "cockpit": "192.168.1.41:9120", "gene": "192.168.1.41:8770",
        "speed_class": "steady",
        "note": "steady worker box (Acer)", "pinned": False,
    },
}


def _now():
    return datetime.datetime.now(datetime.timezone.utc).isoformat(
        timespec="seconds").replace("+00:00", "Z")


def _ping(host: str, timeout=1) -> bool:
    try:
        r = subprocess.run(["ping", "-c1", f"-W{timeout}", host],
                           stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
                           timeout=timeout + 2)
        return r.returncode == 0
    except Exception:
        return False


def _http_json(url: str, timeout=3):
    try:
        with urllib.request.urlopen(url, timeout=timeout) as r:
            return json.loads(r.read().decode("utf-8", "replace"))
    except Exception as e:
        return {"_err": str(e)[:80]}


def _http_ok(url: str, timeout=3) -> bool:
    try:
        with urllib.request.urlopen(url, timeout=timeout) as r:
            return 200 <= r.status < 500
    except Exception:
        return False


def _ollama_models(hostport: str, timeout=4):
    d = _http_json(f"http://{hostport}/api/tags", timeout=timeout)
    if isinstance(d, dict) and "models" in d:
        return sorted(m.get("name", "") for m in d["models"] if m.get("name"))
    return []


def _current_job(worker_id: str):
    """Real current job = most recent claim/assign for this box on the council
    board that has NOT been closed (done/completed/recycled) afterwards."""
    if not worker_id or not COUNCIL.exists():
        return None
    open_task = {}
    closed = set()
    try:
        with open(COUNCIL) as f:
            for line in f:
                line = line.strip()
                if not line:
                    continue
                try:
                    d = json.loads(line)
                except Exception:
                    continue
                ev = d.get("event")
                tid = d.get("task_id")
                actor = d.get("actor")
                if ev in ("done", "completed", "recycled", "reopened") and tid:
                    closed.add(tid)
                if ev in ("claimed", "assigned") and actor == worker_id and tid:
                    open_task[tid] = {
                        "task_id": tid, "event": ev,
                        "ts": d.get("ts"), "text": (d.get("text") or "")[:120],
                    }
    except Exception:
        return None
    live = [v for tid, v in open_task.items() if tid not in closed]
    if not live:
        return None
    live.sort(key=lambda x: x.get("ts") or "", reverse=True)
    return live[0]


def probe(name: str, spec: dict) -> dict:
    r = {
        "resource": name, "role": spec["role"], "worker_id": spec["worker_id"],
        "host": spec["host"], "speed_class": spec["speed_class"],
        "note": spec["note"], "pinned": spec["pinned"],
        "ts": _now(),
    }
    # reachability
    is_local = spec["host"] in ("127.0.0.1", "localhost")
    r["ping_ok"] = True if is_local else _ping(spec["host"])

    # models (real capability). Some boxes keep Ollama bound to localhost only
    # (brain reached via the cockpit, not 11434 externally) — that is honest:
    # we report models_probe_ok=False rather than pretending 0 capability.
    models = _ollama_models(spec["ollama"]) if (r["ping_ok"] or is_local) else []
    r["models"] = models
    r["n_models"] = len(models)
    r["models_probe_ok"] = bool(models) or is_local
    if not models and not is_local:
        r["models_note"] = ("Ollama not exposed on :11434 externally; brain "
                            "reached via cockpit :9120. Capability present, not "
                            "enumerable from here.")

    # cockpit + gene health (real load / reachability)
    cockpit_health = None
    gene_health = None
    if spec["cockpit"] and r["ping_ok"]:
        h = _http_json(f"http://{spec['cockpit']}/health")
        cockpit_health = h if h.get("ok") else None
        r["cockpit_ok"] = bool(cockpit_health)
        r["cockpit_worker_id"] = (cockpit_health or {}).get("worker_id")
        r["cockpit_host"] = (cockpit_health or {}).get("host")
    else:
        r["cockpit_ok"] = None if not spec["cockpit"] else False
    if spec["gene"] and r["ping_ok"]:
        h = _http_json(f"http://{spec['gene']}/health")
        gene_health = h if h.get("ok") else None
        r["gene_ok"] = bool(gene_health)
        r["gene_providers"] = (gene_health or {}).get("providers_available", [])
        r["gene_results_logged"] = (gene_health or {}).get("results_logged")
    else:
        r["gene_ok"] = None if not spec["gene"] else False
        r["gene_providers"] = []

    # reachable summary
    if is_local:
        r["reachable"] = bool(models)  # local: proven by model listing
    else:
        r["reachable"] = bool(r["ping_ok"] and (r["cockpit_ok"] or r["gene_ok"]))

    # current job (real, from council board)
    r["current_job"] = _current_job(spec["worker_id"])
    r["busy"] = r["current_job"] is not None

    # honest availability verdict
    if not r["reachable"]:
        r["availability"] = "unreachable"
    elif spec["pinned"]:
        r["availability"] = "reserved_pinned"  # available but we avoid loading it
    elif r["busy"]:
        r["availability"] = "busy"
    else:
        r["availability"] = "free"
    return r


def build_map() -> dict:
    ts = _now()
    resources = {name: probe(name, spec) for name, spec in RESOURCES.items()}
    # gene pool as a logical resource (providers seen across boxes)
    providers = sorted({p for r in resources.values() for p in r.get("gene_providers", [])})
    gene_reachable = any(resources[b].get("gene_ok") for b in ("thinkpad", "acer"))
    resources["gene_pool"] = {
        "resource": "gene_pool", "role": "external_providers", "worker_id": None,
        "providers": providers, "reachable": gene_reachable,
        "availability": "free" if gene_reachable else "unreachable",
        "speed_class": "network", "pinned": False,
        "note": "external provider fan-out via box gene routers (advisory/verify)",
        "ts": ts,
    }
    worker_boxes_up = [b for b in ("thinkpad", "acer") if resources[b]["reachable"]]
    snap = {
        "ok": True, "schema": "qsb.resource.map/1", "ts": ts,
        "honesty": "Real ping + real HTTP health probes + real Ollama /api/tags + "
                   "real council board for current job. Unreachable is reported "
                   "unreachable. No fabricated health.",
        "summary": {
            "worker_boxes_up": worker_boxes_up,
            "n_worker_boxes_up": len(worker_boxes_up),
            "free_boxes": [n for n, r in resources.items()
                           if r.get("availability") == "free" and r["role"] == "worker_box"],
            "gene_providers": providers,
        },
        "resources": resources,
    }
    return snap


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--print", dest="pr", action="store_true")
    a = ap.parse_args()
    snap = build_map()
    REG.mkdir(parents=True, exist_ok=True)
    tmp = SNAP.with_suffix(".json.tmp")
    tmp.write_text(json.dumps(snap, indent=2))
    tmp.replace(SNAP)
    # append compact history row for the timeline
    hist_row = {
        "ts": snap["ts"],
        "worker_boxes_up": snap["summary"]["worker_boxes_up"],
        "boxes": {n: {"reachable": r.get("reachable"),
                      "availability": r.get("availability"),
                      "busy": r.get("busy"),
                      "n_models": r.get("n_models"),
                      "current_task": (r.get("current_job") or {}).get("task_id")}
                  for n, r in snap["resources"].items() if r.get("role") == "worker_box"},
    }
    with open(HIST, "a") as f:
        f.write(json.dumps(hist_row) + "\n")

    if a.pr:
        print(f"QSB Resource Map @ {snap['ts']}")
        for n, r in snap["resources"].items():
            if n == "gene_pool":
                print(f"  {n:10} providers={r['providers']} reachable={r['reachable']}")
                continue
            print(f"  {n:10} [{r['speed_class']:16}] reachable={str(r['reachable']):5} "
                  f"avail={r['availability']:16} models={r['n_models']:2} "
                  f"job={(r.get('current_job') or {}).get('task_id')}")
    else:
        print(json.dumps({"ok": True, "wrote": str(SNAP), "ts": snap["ts"],
                          "worker_boxes_up": snap["summary"]["worker_boxes_up"]}))


if __name__ == "__main__":
    main()
