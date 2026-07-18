#!/usr/bin/env python3
"""Lumen AI local HTTP server.

Serves /vaults/nvme0/qsb_tower_v1/web/lumen_ai/ as static, plus:
  POST /api/chat              { message, conversation_id? } → { reply, conversation_id, matched_topics }
  GET  /api/conversation/<id> chat history (last 12 turns)
  GET  /api/tiers             pricing tiers
  GET  /api/state             Lumen floor state

Defaults to port 8848.
"""

from __future__ import annotations
from http.server import HTTPServer, BaseHTTPRequestHandler
from pathlib import Path
import argparse
import json
import os
import signal
import sys

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from tower.floors.floor_48_lumen_ai.state import (
    lumen_state_snapshot, persist_lumen_state,
)
from tower.floors.floor_48_lumen_ai.tiers import tiers_snapshot, persist_tiers
from tower.floors.floor_48_lumen_ai.chat import (
    chat_completion, conversation_history, load_conversations,
    persist_conversations,
)


WEB_ROOT = Path("/vaults/nvme0/qsb_tower_v1/web/lumen_ai")
PIDFILE = Path("/vaults/nvme0/qsb_tower_v1/data/run/qsb_lumen_serve.pid")


class Handler(BaseHTTPRequestHandler):
    def log_message(self, format, *args):
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
            ".json": "application/json; charset=utf-8",
        }.get(ext, "application/octet-stream")

    def do_GET(self):
        path = self.path.split("?", 1)[0]
        if path == "/api/tiers":
            return self._send_json(tiers_snapshot())
        if path == "/api/state":
            return self._send_json(lumen_state_snapshot())
        if path.startswith("/api/conversation/"):
            cid = path.rsplit("/", 1)[-1]
            hist = conversation_history(cid)
            if hist is None:
                return self._send_json({"ok": False,
                                         "error": "not found"}, status=404)
            return self._send_json({"ok": True,
                                     "conversation_id": cid,
                                     "turns": hist})
        if path == "/healthz":
            return self._send_json({"ok": True, "service": "lumen_ai"})
        rel = path.lstrip("/")
        if not rel:
            rel = "index.html"
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
        if self.path == "/api/chat":
            return self._handle_chat(payload)
        self.send_error(404, "not found")

    def _handle_chat(self, payload):
        message = (payload.get("message") or "").strip()
        conversation_id = payload.get("conversation_id")
        user_label = payload.get("user_label") or "guest"
        if not message:
            return self._send_json({"ok": False,
                                     "error": "message required"}, status=400)
        result = chat_completion(message,
                                  conversation_id=conversation_id,
                                  user_label=user_label)
        return self._send_json(result)


def run(port: int, host: str = "0.0.0.0") -> int:
    PIDFILE.parent.mkdir(parents=True, exist_ok=True)
    persist_lumen_state()
    persist_tiers()
    load_conversations()
    persist_conversations()

    PIDFILE.write_text(str(os.getpid()))
    server = HTTPServer((host, port), Handler)

    def _stop(signum, frame):
        server.shutdown()
    signal.signal(signal.SIGTERM, _stop)
    signal.signal(signal.SIGINT, _stop)

    print(f"[lumen_ai] serving http://{host}:{port}  pid={os.getpid()}")
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
    parser = argparse.ArgumentParser(description="Lumen AI HTTP server.")
    parser.add_argument("--port", type=int, default=8848)
    args = parser.parse_args()
    sys.exit(run(args.port))


if __name__ == "__main__":
    main()
