#!/usr/bin/env python3
"""
QSB Tower V1.3 — Worker Sandbox Sidecar API

Dashboard browser -> localhost:8768 -> worker_sandbox.py

Safety:
- Sandbox workers only.
- No live OANDA orders.
- No practice OANDA orders.
- No OpenClaw execution.
- No autonomous dispatch.
- No external providers.
"""

from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from datetime import datetime, timezone
import json
import os
import sys
import urllib.parse

ROOT = Path("/vaults/nvme0/qsb_tower_v1")
SRC = ROOT / "src"
sys.path.insert(0, str(SRC))

HOST = "127.0.0.1"
PORT = 8768

LOCKS = {
    "live_trading_enabled": False,
    "order_execution_enabled": False,
    "practice_order_execution_enabled": False,
    "worker_execution_enabled": False,
    "provider_execution_enabled": False,
    "external_provider_execution_enabled": False,
    "openclaw_execution_enabled": False,
    "autonomous_dispatch_enabled": False,
    "live_dispatch_enabled": False,
    "direct_provider_access": False
}


def load_local_env_file():
    env = ROOT / ".env.oanda_practice"
    if not env.exists():
        return
    for line in env.read_text(encoding="utf-8", errors="ignore").splitlines():
        line = line.strip()
        if not line.startswith("export "):
            continue
        k, _, v = line.replace("export ", "", 1).partition("=")
        os.environ.setdefault(k.strip(), v.strip().strip("'").strip('"'))


def load_json(path, fallback=None):
    if fallback is None:
        fallback = {}
    try:
        return json.loads(Path(path).read_text(encoding="utf-8"))
    except Exception:
        return fallback


def short_worker_status():
    latest = load_json(ROOT / "data/registries/worker_sandbox_latest_tick.json", {})
    ledger = load_json(ROOT / "data/registries/floor41_paper_ledger.json", {})
    packets = load_json(ROOT / "data/registries/worker_sandbox_lift_packets_latest.json", {})
    paper = load_json(ROOT / "data/registries/oanda_paper_strategy_latest.json", {})
    registry = load_json(ROOT / "data/registries/worker_sandbox_registry.json", {})

    return {
        "ok": True,
        "service": "worker_sandbox_sidecar",
        "ts": datetime.now(timezone.utc).isoformat(),
        "sandbox": "worker_sandbox_v1",
        "status": "healthy" if latest else "ready",
        "sandbox_workers_enabled": True,
        "worker_execution_enabled": False,
        "openclaw_execution_enabled": False,
        "autonomous_dispatch_enabled": False,
        "worker_count": len(registry.get("workers", [])),
        "workers": registry.get("workers", []),
        "latest_tick_ts": latest.get("ts"),
        "latest_packet_count": len(latest.get("lift_packets", [])),
        "latest_packets": latest.get("lift_packets", [])[-10:],
        "ledger": {
            "entry_count": ledger.get("entry_count", 0),
            "latest_entry_count": ledger.get("latest_entry_count", 0),
            "latest_entries": ledger.get("latest_entries", [])[-10:],
            "simulated_observation_delta_pips_total": load_json(ROOT / "data/runtime/floor41_paper_ledger_latest.json", {}).get("simulated_observation_delta_pips_total")
        },
        "paper_lab": {
            "latest_ts": paper.get("ts"),
            "summary": paper.get("summary", {}),
            "instruments": paper.get("instruments", [])
        },
        "kernel_commentary": {
            "ok": latest.get("kernel_commentary", {}).get("ok"),
            "reply": latest.get("kernel_commentary", {}).get("reply", "")[:1200] if latest else ""
        },
        "locks": LOCKS,
        "paper_only": True,
        "not_financial_advice": True
    }


def json_response(handler, payload, code=200):
    handler.send_response(code)
    handler.send_header("Content-Type", "application/json")
    handler.send_header("Access-Control-Allow-Origin", "http://127.0.0.1:8765")
    handler.send_header("Access-Control-Allow-Methods", "GET, POST, OPTIONS")
    handler.send_header("Access-Control-Allow-Headers", "Content-Type")
    handler.send_header("Cache-Control", "no-store")
    handler.end_headers()
    handler.wfile.write(json.dumps(payload, indent=2, default=str).encode("utf-8"))


class Handler(BaseHTTPRequestHandler):
    def log_message(self, fmt, *args):
        return

    def do_OPTIONS(self):
        json_response(self, {}, 204)

    def do_GET(self):
        load_local_env_file()
        parsed = urllib.parse.urlparse(self.path)

        try:
            if parsed.path == "/api/worker_sandbox/status":
                json_response(self, short_worker_status())
                return

            if parsed.path == "/api/worker_sandbox/tick":
                q = urllib.parse.parse_qs(parsed.query)
                instruments = q.get("instruments", ["EUR_USD,GBP_USD,USD_JPY"])[0]
                from tower.worker_sandbox import WorkerSandbox
                tick = WorkerSandbox().tick(instruments)
                json_response(self, {
                    "ok": True,
                    "tick": tick,
                    "status": short_worker_status(),
                    "locks": LOCKS
                })
                return

            json_response(self, {"ok": False, "error": "not found", "path": parsed.path}, 404)
        except Exception as exc:
            json_response(self, {"ok": False, "error": str(exc), "locks": LOCKS}, 500)

    def do_POST(self):
        load_local_env_file()
        parsed = urllib.parse.urlparse(self.path)

        if parsed.path != "/api/worker_sandbox/tick":
            json_response(self, {"ok": False, "error": "not found", "path": parsed.path}, 404)
            return

        try:
            length = int(self.headers.get("Content-Length", "0"))
            body = json.loads(self.rfile.read(length).decode("utf-8") or "{}")
            instruments = body.get("instruments") or "EUR_USD,GBP_USD,USD_JPY"

            from tower.worker_sandbox import WorkerSandbox
            tick = WorkerSandbox().tick(instruments)

            json_response(self, {
                "ok": True,
                "tick": tick,
                "status": short_worker_status(),
                "locks": LOCKS
            })
        except Exception as exc:
            json_response(self, {"ok": False, "error": str(exc), "locks": LOCKS}, 500)


def main():
    print(f"Worker Sandbox sidecar running at http://{HOST}:{PORT}")
    ThreadingHTTPServer((HOST, PORT), Handler).serve_forever()


if __name__ == "__main__":
    main()
