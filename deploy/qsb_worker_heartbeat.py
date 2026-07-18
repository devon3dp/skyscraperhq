#!/usr/bin/env python3
"""
QSB Worker Heartbeat Client — MASTER PHASE 2 (deploy to TP-Pip / Acer-Cass boxes).

Runs ON a physical worker (Windows). Registers the worker's CURRENT address + ports
with HQ's physical-worker registry and heartbeats, so HQ tracks the box across DHCP
moves WITHOUT any hardcoded IP. Reports the active network path (Ethernet vs Wi-Fi).

HARD CONSTRAINTS (by design — this client intentionally cannot do more):
  - NO Claude / OpenAI / any external AI API call.
  - NO Gene Pool traffic.
  - NO Task Council claim, NO repairs, NO shell exec.
  - Sends NO secrets (no Wi-Fi password, no API key, no env values).
  - Never blocks the main worker runtime (separate process; safe backoff).
  - Confirms it found the REAL HQ (GET /api/hq_identity) before registering.

Deploy:
  copy to the worker box, run alongside the runtime, e.g.:
    python qsb_worker_heartbeat.py --worker-id tp_pip --runtime-port 8871 --dashboard-port 9110
  (Acer: --worker-id acer_cass --runtime-port 8872 --dashboard-port 9000)

HQ discovery order (see --hq): explicit URL -> hostname -> known-LAN candidates ->
tight :8852 identity probe -> else HQ_ENDPOINT_UNRESOLVED and keep retrying.
"""
import argparse
import json
import socket
import subprocess
import sys
import time
import urllib.request

# Known-good HQ candidates (private LAN only). Discovery confirms identity before use.
HQ_CANDIDATES = [
    "http://192.168.1.92:8852", "http://192.168.1.72:8852", "http://192.168.1.84:8852",
    "http://skyscraperhq:8852", "http://24.04ubuntu:8852",
]
HQ_IDENTITY_PATH = "/api/hq_identity"


def _get_json(url, timeout=3):
    req = urllib.request.Request(url, headers={"Accept": "application/json"})
    with urllib.request.urlopen(req, timeout=timeout) as r:
        return json.loads(r.read(4096).decode("utf-8", "replace"))


def _post_json(url, payload, timeout=4):
    data = json.dumps(payload).encode()
    req = urllib.request.Request(url, data=data, method="POST",
                                 headers={"Content-Type": "application/json"})
    with urllib.request.urlopen(req, timeout=timeout) as r:
        return json.loads(r.read(4096).decode("utf-8", "replace"))


def discover_hq(explicit=None):
    """Return a base URL whose /api/hq_identity confirms the real Boardroom, else None."""
    order = ([explicit] if explicit else []) + HQ_CANDIDATES
    for base in order:
        if not base:
            continue
        try:
            ident = _get_json(base.rstrip("/") + HQ_IDENTITY_PATH)
            if ident.get("service") == "qsb_boardroom" and ident.get("physical_worker_registry"):
                return base.rstrip("/")
        except Exception:
            continue
    return None


def active_path():
    """Best-effort read-only detection of the active adapter + connection type.
    No secrets. Falls back to UNKNOWN. (Windows: uses 'route print' / 'netsh'.)"""
    conn_type, adapter = "UNKNOWN", "UNKNOWN"
    try:
        # Windows: which interface owns the default route (lowest metric that's up)
        out = subprocess.run(["powershell", "-NoProfile", "-Command",
                              "(Get-NetIPConfiguration | Where-Object {$_.IPv4DefaultGateway} | "
                              "Sort-Object {$_.NetAdapter.InterfaceMetric} | Select-Object -First 1 "
                              "-ExpandProperty InterfaceAlias)"],
                             capture_output=True, text=True, timeout=6)
        adapter = (out.stdout or "").strip() or "UNKNOWN"
        low = adapter.lower()
        if "ethernet" in low or "lan" in low:
            conn_type = "Ethernet"
        elif "wi-fi" in low or "wifi" in low or "wlan" in low or "wireless" in low:
            conn_type = "Wi-Fi"
    except Exception:
        pass
    return adapter, conn_type


def local_ip(hq_host):
    """The source IP HQ will actually see — the address on the route toward HQ."""
    try:
        s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        s.connect((hq_host, 8852))
        ip = s.getsockname()[0]
        s.close()
        return ip
    except Exception:
        return ""


def build_payload(args):
    adapter, conn_type = active_path()
    return {
        "worker_id": args.worker_id,
        "name": args.name or args.worker_id,
        "hostname": socket.gethostname().upper(),
        "runtime_port": args.runtime_port,
        "dashboard_port": args.dashboard_port,
        "dashboard_scope": args.dashboard_scope,
        "physical_independent": True,
        "hq_hosted": False,
        "capabilities": ["can_receive_task", "can_run_readonly", "can_write_report"],
        "active_adapter": adapter,
        "connection_type": conn_type,
    }


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--worker-id", required=True, choices=["tp_pip", "acer_cass"])
    ap.add_argument("--name", default="")
    ap.add_argument("--runtime-port", type=int, required=True)
    ap.add_argument("--dashboard-port", default=None)
    ap.add_argument("--dashboard-scope", default="LAN")
    ap.add_argument("--hq", default="", help="explicit HQ base URL (optional)")
    ap.add_argument("--interval", type=int, default=60, help="heartbeat seconds")
    ap.add_argument("--once", action="store_true", help="register a single time then exit (test mode)")
    args = ap.parse_args()

    if args.once:
        base = discover_hq(args.hq or None)
        if not base:
            print(json.dumps({"state": "HQ_ENDPOINT_UNRESOLVED"})); return 3
        payload = build_payload(args)
        try:
            out = _post_json(base + "/api/physical_workers/register", payload)
            print(json.dumps({"hq": base, "ok": out.get("ok"), "err": out.get("error"),
                              "worker_id": payload["worker_id"], "hostname": payload["hostname"],
                              "adapter": payload["active_adapter"], "conn": payload["connection_type"]}))
            return 0 if out.get("ok") else 1
        except Exception as e:
            print(json.dumps({"hq": base, "error": type(e).__name__ + ":" + str(e)[:100]})); return 2

    backoff = args.interval
    first = True
    while True:
        base = discover_hq(args.hq or None)
        if not base:
            print(json.dumps({"ts": time.time(), "state": "HQ_ENDPOINT_UNRESOLVED"}))
            time.sleep(min(backoff, 300)); backoff = min(backoff * 2, 300); continue
        backoff = args.interval
        payload = build_payload(args)
        try:
            path = "/api/physical_workers/register" if first else "/api/physical_workers/heartbeat"
            out = _post_json(base + path, payload)
            print(json.dumps({"ts": time.time(), "hq": base, "path": path,
                              "ok": out.get("ok"), "err": out.get("error"),
                              "adapter": payload["active_adapter"], "conn": payload["connection_type"]}))
            if out.get("ok"):
                first = False
        except Exception as e:
            print(json.dumps({"ts": time.time(), "hq": base, "error": type(e).__name__ + ":" + str(e)[:80]}))
        time.sleep(args.interval)


if __name__ == "__main__":
    sys.exit(main())
