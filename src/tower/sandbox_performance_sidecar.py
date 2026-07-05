#!/usr/bin/env python3
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
PORT = 8769

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


def json_response(handler, payload, code=200):
    handler.send_response(code)
    handler.send_header("Content-Type", "application/json")
    handler.send_header("Access-Control-Allow-Origin", "http://127.0.0.1:8765")
    handler.send_header("Access-Control-Allow-Methods", "GET, POST, OPTIONS")
    handler.send_header("Access-Control-Allow-Headers", "Content-Type")
    handler.send_header("Cache-Control", "no-store")
    handler.end_headers()
    handler.wfile.write(json.dumps(payload, indent=2, default=str).encode("utf-8"))


def compact_status():
    latest = load_json(ROOT / "data/registries/sandbox_performance_latest.json", {})
    worker = load_json(ROOT / "data/registries/worker_sandbox_latest_tick.json", {})
    ledger = load_json(ROOT / "data/registries/floor41_paper_ledger.json", {})

    perf = latest.get("performance", {})
    return {
        "ok": True,
        "service": "sandbox_performance_sidecar",
        "ts": datetime.now(timezone.utc).isoformat(),
        "phase": "SANDBOX_PERFORMANCE_LOOP_V1",
        "status": "healthy" if latest else "ready",
        "latest_ts": latest.get("ts"),
        "ticks_completed": latest.get("ticks_completed"),
        "worker_count": latest.get("worker_count"),
        "entries_analyzed": perf.get("entries_analyzed"),
        "total_paper_score": perf.get("total_paper_score"),
        "total_observation_delta_pips": perf.get("total_observation_delta_pips"),
        "by_instrument": perf.get("by_instrument", []),
        "kernel_commentary_ok": latest.get("kernel_commentary", {}).get("ok"),
        "kernel_commentary_reply": latest.get("kernel_commentary", {}).get("reply", "")[:1500],
        "latest_worker_tick": worker.get("ts"),
        "ledger_entry_count": ledger.get("entry_count", 0),
        "locks": LOCKS,
        "paper_only": True,
        "not_financial_advice": True
    }


class Handler(BaseHTTPRequestHandler):
    def log_message(self, fmt, *args):
        return

    def do_OPTIONS(self):
        json_response(self, {}, 204)

    def do_GET(self):
        load_local_env_file()
        parsed = urllib.parse.urlparse(self.path)

        try:
            if parsed.path == "/api/performance/status":
                json_response(self, compact_status())
                return

            if parsed.path == "/api/performance/run":
                q = urllib.parse.parse_qs(parsed.query)
                ticks = int(q.get("ticks", ["3"])[0])
                delay = int(q.get("delay", ["5"])[0])
                instruments = q.get("instruments", ["EUR_USD,GBP_USD,USD_JPY"])[0]

                from tower.sandbox_performance_loop import SandboxPerformanceLoop
                report = SandboxPerformanceLoop().run(
                    ticks=ticks,
                    delay_seconds=delay,
                    instruments=instruments,
                    kernel_commentary=True
                )
                json_response(self, {
                    "ok": True,
                    "report": report,
                    "status": compact_status(),
                    "locks": LOCKS
                })
                return

            json_response(self, {"ok": False, "error": "not found", "path": parsed.path}, 404)
        except Exception as exc:
            json_response(self, {"ok": False, "error": str(exc), "locks": LOCKS}, 500)

    def do_POST(self):
        load_local_env_file()
        parsed = urllib.parse.urlparse(self.path)

        if parsed.path != "/api/performance/run":
            json_response(self, {"ok": False, "error": "not found", "path": parsed.path}, 404)
            return

        try:
            length = int(self.headers.get("Content-Length", "0"))
            body = json.loads(self.rfile.read(length).decode("utf-8") or "{}")
            ticks = int(body.get("ticks", 3))
            delay = int(body.get("delay", 5))
            instruments = body.get("instruments") or "EUR_USD,GBP_USD,USD_JPY"

            from tower.sandbox_performance_loop import SandboxPerformanceLoop
            report = SandboxPerformanceLoop().run(
                ticks=ticks,
                delay_seconds=delay,
                instruments=instruments,
                kernel_commentary=True
            )

            json_response(self, {
                "ok": True,
                "report": report,
                "status": compact_status(),
                "locks": LOCKS
            })
        except Exception as exc:
            json_response(self, {"ok": False, "error": str(exc), "locks": LOCKS}, 500)


def main():
    print(f"Sandbox Performance sidecar running at http://{HOST}:{PORT}")
    ThreadingHTTPServer((HOST, PORT), Handler).serve_forever()


if __name__ == "__main__":
    main()
