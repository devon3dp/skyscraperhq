#!/usr/bin/env python3
"""
qsb_ollama_wedge_healer.py — auto-heals the recurring MAIN-BOX Ollama SOFTWARE wedge.

The MSI box's Ollama periodically wedges under inference load: the model stays loaded
but every generate returns EMPTY, silencing Wren + the Wren<->Bill dialogue. This is a
SOFTWARE wedge (GPU stays healthy), not the GPU falling off the bus.

Runs as a ROOT systemd oneshot on a short timer. Each tick:
  1. Trivial generate test. If inference works -> log "ok", done.
  2. If inference is empty/hung, check the GPU: nvidia-smi responsive?
     - GPU HEALTHY (responds)  -> SOFTWARE wedge -> `systemctl restart ollama.service`
       (software only; GPU untouched; qwen reloads in ~4s). Verify recovery.
     - GPU UNRESPONSIVE        -> possible off-bus -> DO NOT auto-restart (that needs a
       cold cycle, a Ross call). Log an ALERT only.
Every action is logged honestly to qsb_ollama_wedge_healer.jsonl. Safe: it only ever
restarts Ollama (a local, already-authorized service) when the GPU is provably fine.
"""
import subprocess, json, time, urllib.request, sys
from pathlib import Path

ROOT = Path("/vaults/nvme0/qsb_tower_v1")
LOG = ROOT / "data" / "registries" / "qsb_ollama_wedge_healer.jsonl"
MODEL = "qwen2.5:14b"


def _log(action, detail=""):
    row = {"ts": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
           "action": action, "detail": str(detail)[:200]}
    try:
        with open(LOG, "a") as f:
            f.write(json.dumps(row) + "\n")
    except Exception:
        pass
    print(f"[ollama-healer] {action} {detail}", flush=True)


def _gpu_ok():
    try:
        r = subprocess.run(["nvidia-smi", "--query-gpu=temperature.gpu", "--format=csv,noheader"],
                           capture_output=True, text=True, timeout=10)
        return r.returncode == 0 and r.stdout.strip() != ""
    except Exception:
        return False


def _inference_ok(timeout=30):
    try:
        req = urllib.request.Request(
            "http://127.0.0.1:11434/api/generate",
            data=json.dumps({"model": MODEL, "prompt": "say ok", "stream": False}).encode(),
            headers={"Content-Type": "application/json"})
        with urllib.request.urlopen(req, timeout=timeout) as r:
            d = json.loads(r.read() or b"{}")
        return bool((d.get("response") or "").strip())
    except Exception:
        return False


def main():
    if _inference_ok(30):
        _log("ok", "inference healthy")
        return 0
    if not _gpu_ok():
        _log("ALERT_gpu_unresponsive",
             "nvidia-smi failed while inference wedged — possible GPU off-bus; NOT auto-restarting (needs cold cycle / Ross)")
        return 0
    # GPU healthy + inference wedged -> software restart Ollama only
    r = subprocess.run(["systemctl", "restart", "ollama.service"], capture_output=True, text=True)
    if r.returncode != 0:
        _log("restart_FAILED", r.stderr.strip()[:140])
        return 1
    time.sleep(8)
    back = _inference_ok(95)   # cold reload can take a while
    _log("restarted_ollama_software", "inference recovered" if back else "still empty after restart")
    return 0


if __name__ == "__main__":
    sys.exit(main())
