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
PORT = 8767


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
        q = urllib.parse.parse_qs(parsed.query)
        instruments = q.get("instruments", ["EUR_USD,GBP_USD,USD_JPY"])[0]

        try:
            if parsed.path == "/api/floor41/status":
                from tower.oanda_paper_strategy_lab import OANDAPaperStrategyLab
                json_response(self, OANDAPaperStrategyLab().dashboard())
                return

            if parsed.path == "/api/floor41/run":
                from tower.oanda_paper_strategy_lab import OANDAPaperStrategyLab
                json_response(self, OANDAPaperStrategyLab().run(instruments))
                return

            json_response(self, {"ok": False, "error": "not found", "path": parsed.path}, 404)
        except Exception as exc:
            json_response(self, {"ok": False, "error": str(exc)}, 500)

    def do_POST(self):
        load_local_env_file()
        parsed = urllib.parse.urlparse(self.path)

        if parsed.path != "/api/floor41/commentary":
            json_response(self, {"ok": False, "error": "not found", "path": parsed.path}, 404)
            return

        try:
            length = int(self.headers.get("Content-Length", "0"))
            body = json.loads(self.rfile.read(length).decode("utf-8") or "{}")
            instruments = body.get("instruments") or "EUR_USD,GBP_USD,USD_JPY"

            from tower.oanda_paper_strategy_lab import OANDAPaperStrategyLab
            from tower.kernel_dialogue_adapter import ask_kernel

            lab = OANDAPaperStrategyLab().run(instruments)
            prompt = json.dumps(lab, indent=2) + """

Kernel, review this Floor 41 OANDA Paper Strategy Lab output.
This is paper research only.
Do not place orders.
Do not enable live trading.
Do not enable practice order execution.
Do not enable workers.
Do not enable OpenClaw.
Do not enable autonomous dispatch.
Give a concise tactical read, risk warning, and what to observe next.
"""
            result = ask_kernel(prompt, prefer_local_model=True)
            json_response(self, {
                "ok": True,
                "ts": datetime.now(timezone.utc).isoformat(),
                "lab": lab,
                "commentary": result,
                "locks": lab.get("locks", {})
            })
        except Exception as exc:
            json_response(self, {"ok": False, "error": str(exc)}, 500)


def main():
    print(f"Floor 41 OANDA sidecar running at http://{HOST}:{PORT}")
    ThreadingHTTPServer((HOST, PORT), Handler).serve_forever()


if __name__ == "__main__":
    main()
