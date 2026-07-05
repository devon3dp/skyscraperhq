#!/usr/bin/env python3
"""Tower Studio local HTTP server.

Serves /vaults/nvme0/qsb_tower_v1/web/tower_studio/ as static, plus
backend endpoints:
  GET  /api/services         services catalog (live from registries)
  GET  /api/projects         project pipeline
  POST /api/contact          add a customer lead (writes to qsb_floor49_customers.json)

Defaults to port 8849.
"""

from __future__ import annotations
from http.server import HTTPServer, BaseHTTPRequestHandler
from pathlib import Path
import argparse
import json
import os
import signal
import sys
import threading

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from tower.floors.floor_49_tower_studio.services import services_snapshot, persist_services
from tower.floors.floor_49_tower_studio.customers import customers_db
from tower.floors.floor_49_tower_studio.projects import projects_db, persist_projects
from tower.floors.floor_49_tower_studio.state import persist_floor_state
from tower.floors.floor_49_tower_studio.workers import persist_workers
from tower.floors.floor_49_tower_studio.graphics import generate_all_assets


WEB_ROOT = Path("/vaults/nvme0/qsb_tower_v1/web/tower_studio")
PIDFILE = Path("/vaults/nvme0/qsb_tower_v1/data/run/qsb_studio_serve.pid")


class Handler(BaseHTTPRequestHandler):
    def log_message(self, format, *args):
        # Silence default stderr noise; log to file via the orchestrator
        pass

    def _send_json(self, payload, status=200):
        body = json.dumps(payload, default=str).encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(body)))
        self.send_header("Cache-Control", "no-store")
        self.end_headers()
        self.wfile.write(body)

    def _send_file(self, path: Path, content_type: str):
        try:
            data = path.read_bytes()
        except FileNotFoundError:
            self.send_error(404, "not found")
            return
        self.send_response(200)
        self.send_header("Content-Type", content_type)
        self.send_header("Content-Length", str(len(data)))
        self.send_header("Cache-Control", "no-store")
        self.end_headers()
        self.wfile.write(data)

    def _content_type(self, p: Path) -> str:
        ext = p.suffix.lower()
        return {
            ".html": "text/html; charset=utf-8",
            ".css":  "text/css; charset=utf-8",
            ".js":   "application/javascript; charset=utf-8",
            ".svg":  "image/svg+xml",
            ".png":  "image/png",
            ".jpg":  "image/jpeg",
            ".jpeg": "image/jpeg",
            ".ico":  "image/x-icon",
            ".json": "application/json; charset=utf-8",
            ".txt":  "text/plain; charset=utf-8",
        }.get(ext, "application/octet-stream")

    def do_GET(self):
        path = self.path.split("?", 1)[0]
        # Backend
        if path == "/api/services":
            return self._send_json(services_snapshot())
        if path == "/api/projects":
            return self._send_json(projects_db().snapshot())
        if path == "/api/customers":
            return self._send_json(customers_db().snapshot())
        if path == "/healthz":
            return self._send_json({"ok": True, "service": "tower_studio"})
        # Static
        rel = path.lstrip("/")
        if not rel:
            rel = "index.html"
        # Normalise + reject traversal
        target = (WEB_ROOT / rel).resolve()
        if not str(target).startswith(str(WEB_ROOT.resolve())):
            self.send_error(403, "forbidden")
            return
        if target.is_dir():
            target = target / "index.html"
        if not target.exists():
            self.send_error(404, "not found")
            return
        self._send_file(target, self._content_type(target))

    def do_POST(self):
        length = int(self.headers.get("Content-Length") or 0)
        body = self.rfile.read(length).decode("utf-8") if length > 0 else ""
        try:
            payload = json.loads(body) if body else {}
        except Exception:
            return self._send_json({"ok": False,
                                     "error": "invalid json"}, status=400)
        if self.path == "/api/contact":
            return self._handle_contact(payload)
        self.send_error(404, "not found")

    def _handle_contact(self, payload):
        name = (payload.get("name") or "").strip()
        email = (payload.get("email") or "").strip()
        company = (payload.get("company") or "").strip() or None
        budget = payload.get("budget")
        message = (payload.get("message") or "").strip()
        if not name or not email or not message:
            return self._send_json({"ok": False,
                                     "error": "name + email + message required"},
                                    status=400)
        notes = [message]
        if budget:
            notes.append(f"approx_budget_usd={budget}")
        c = customers_db().add(
            name=name, email=email, company=company,
            source="website_form",
            tags=["website_lead"],
            notes=notes,
        )
        return self._send_json({"ok": True, "customer_id": c.customer_id})


def run(port: int) -> int:
    # Pre-flight: regenerate assets + persist registries so the site is live
    PIDFILE.parent.mkdir(parents=True, exist_ok=True)
    persist_floor_state()
    persist_services()
    customers_db().persist()
    projects_db().persist()
    persist_workers()
    generate_all_assets()

    PIDFILE.write_text(str(os.getpid()))
    server = HTTPServer(("127.0.0.1", port), Handler)

    def _stop(signum, frame):
        server.shutdown()
    signal.signal(signal.SIGTERM, _stop)
    signal.signal(signal.SIGINT, _stop)

    print(f"[tower_studio] serving http://127.0.0.1:{port}  pid={os.getpid()}")
    try:
        server.serve_forever()
    finally:
        try:
            if PIDFILE.exists():
                PIDFILE.unlink()
        except Exception:
            pass
    return 0


def main():
    parser = argparse.ArgumentParser(description="Tower Studio HTTP server.")
    parser.add_argument("--port", type=int, default=8849)
    args = parser.parse_args()
    sys.exit(run(args.port))


if __name__ == "__main__":
    main()
