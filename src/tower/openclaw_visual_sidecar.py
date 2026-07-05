#!/usr/bin/env python3
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from datetime import datetime, timezone
import json
import sys
import urllib.parse

ROOT = Path("/vaults/nvme0/qsb_tower_v1")
SRC = ROOT / "src"
sys.path.insert(0, str(SRC))

HOST = "127.0.0.1"
PORT = 8770

LOCKS = {
    "live_trading_enabled": False,
    "order_execution_enabled": False,
    "practice_order_execution_enabled": False,
    "worker_execution_enabled": False,
    "provider_execution_enabled": False,
    "external_provider_execution_enabled": False,
    "openclaw_execution_enabled": False,
    "openclaw_real_tool_execution_enabled": False,
    "autonomous_dispatch_enabled": False,
    "live_dispatch_enabled": False,
    "direct_provider_access": False
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
        parsed = urllib.parse.urlparse(self.path)

        try:
            from tower.openclaw_sandbox_layer import OpenClawSandboxLayer
            layer = OpenClawSandboxLayer()

            if parsed.path == "/api/openclaw/status":
                json_response(self, layer.status())
                return

            if parsed.path == "/api/openclaw/tick":
                json_response(self, {
                    "ok": True,
                    "tick": layer.tick(),
                    "status": layer.status(),
                    "locks": LOCKS
                })
                return

            json_response(self, {"ok": False, "error": "not found", "path": parsed.path}, 404)
        except Exception as exc:
            json_response(self, {"ok": False, "error": str(exc), "locks": LOCKS}, 500)

    def do_POST(self):
        parsed = urllib.parse.urlparse(self.path)
        if parsed.path != "/api/openclaw/tick":
            json_response(self, {"ok": False, "error": "not found", "path": parsed.path}, 404)
            return

        try:
            from tower.openclaw_sandbox_layer import OpenClawSandboxLayer
            layer = OpenClawSandboxLayer()
            json_response(self, {
                "ok": True,
                "tick": layer.tick(),
                "status": layer.status(),
                "locks": LOCKS
            })
        except Exception as exc:
            json_response(self, {"ok": False, "error": str(exc), "locks": LOCKS}, 500)


def main():
    print(f"OpenClaw Visual sidecar running at http://{HOST}:{PORT}")
    ThreadingHTTPServer((HOST, PORT), Handler).serve_forever()


if __name__ == "__main__":
    main()
