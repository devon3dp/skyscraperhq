#!/usr/bin/env python3
"""
QSB Tower V1.3 — Strategy <-> AutoLoop Correlation Sidecar V1
Read-only. No orders. No execution unlocks.
"""

from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
import json
import sys
import urllib.parse

ROOT = Path("/vaults/nvme0/qsb_tower_v1")
sys.path.insert(0, str(ROOT / "src"))

HOST = "127.0.0.1"
PORT = 8772


def send(handler, payload, code=200):
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
        send(self, {}, 204)

    def do_GET(self):
        parsed = urllib.parse.urlparse(self.path)
        q = urllib.parse.parse_qs(parsed.query)
        instruments = q.get("instruments", ["EUR_USD,GBP_USD,USD_JPY"])[0]

        try:
            from tower.strategy_autoloop_correlation import StrategyAutoloopCorrelation
            sac = StrategyAutoloopCorrelation()

            if parsed.path == "/api/correlation/status":
                send(self, sac.status())
            elif parsed.path == "/api/correlation/build":
                send(self, sac.build(instruments))
            else:
                send(self, {"ok": False, "error": "not found", "path": parsed.path}, 404)
        except Exception as exc:
            send(self, {"ok": False, "error": str(exc)}, 500)

    def do_POST(self):
        try:
            length = int(self.headers.get("Content-Length", "0") or "0")
            body = {}
            if length:
                body = json.loads(self.rfile.read(length).decode("utf-8") or "{}")
            instruments = body.get("instruments", "EUR_USD,GBP_USD,USD_JPY")

            from tower.strategy_autoloop_correlation import StrategyAutoloopCorrelation
            send(self, StrategyAutoloopCorrelation().build(instruments))
        except Exception as exc:
            send(self, {"ok": False, "error": str(exc)}, 500)


def main():
    print(f"Strategy <-> AutoLoop Correlation sidecar running at http://{HOST}:{PORT}")
    ThreadingHTTPServer((HOST, PORT), Handler).serve_forever()


if __name__ == "__main__":
    main()
