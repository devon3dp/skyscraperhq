#!/usr/bin/env python3
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
import json
import os
import sys
import urllib.parse

ROOT = Path("/vaults/nvme0/qsb_tower_v1")
sys.path.insert(0, str(ROOT / "src"))

HOST = "127.0.0.1"
PORT = 8771


def load_env_file():
    env = ROOT / ".env.oanda_practice"
    if not env.exists():
        return
    for line in env.read_text(encoding="utf-8", errors="ignore").splitlines():
        line = line.strip()
        if not line or line.startswith("#"):
            continue
        if line.startswith("export "):
            line = line[len("export "):]
        if "=" not in line:
            continue
        k, v = line.split("=", 1)
        k = k.strip()
        v = v.strip().strip("'").strip('"')
        if k and v and k not in os.environ:
            os.environ[k] = v


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
        load_env_file()
        parsed = urllib.parse.urlparse(self.path)
        q = urllib.parse.parse_qs(parsed.query)
        instruments = q.get("instruments", ["EUR_USD,GBP_USD,USD_JPY"])[0]

        try:
            from tower.strategy_intelligence import StrategyIntelligence
            si = StrategyIntelligence()

            if parsed.path == "/api/strategy/status":
                send(self, si.status())
            elif parsed.path == "/api/strategy/run":
                send(self, si.run(instruments))
            else:
                send(self, {"ok": False, "error": "not found", "path": parsed.path}, 404)
        except Exception as exc:
            send(self, {"ok": False, "error": str(exc)}, 500)

    def do_POST(self):
        load_env_file()
        try:
            length = int(self.headers.get("Content-Length", "0") or "0")
            body = {}
            if length:
                body = json.loads(self.rfile.read(length).decode("utf-8") or "{}")
            instruments = body.get("instruments", "EUR_USD,GBP_USD,USD_JPY")

            from tower.strategy_intelligence import StrategyIntelligence
            send(self, StrategyIntelligence().run(instruments))
        except Exception as exc:
            send(self, {"ok": False, "error": str(exc)}, 500)


def main():
    print(f"Strategy Intelligence sidecar running at http://{HOST}:{PORT}")
    ThreadingHTTPServer((HOST, PORT), Handler).serve_forever()


if __name__ == "__main__":
    main()
