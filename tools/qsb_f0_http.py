#!/usr/bin/env python3
"""qsb_f0_http.py — HTTP front for qsb_f0_receptionist.

Serves the receptionist as an always-on HTTP microservice on 127.0.0.1:8765
so channel bridges (WhatsApp, Telegram, Twilio voice, cockpit chat) can all
POST inbound messages to a single endpoint and get the receptionist's reply.

Endpoints:
  GET  /status                   → {ok, ts, uptime_s, calls_seen}
  POST /api/f0/greet             → {reply, route_hint}
  POST /api/f0/converse          → {reply, route_hint, downstream}
                                    body: {caller_id, text}
  POST /api/f0/close             → {ok}
                                    body: {caller_id, summary}

No auth (bound to localhost). Every request stamped to
data/registries/qsb_f0_http_audit.jsonl.
"""
from __future__ import annotations
import argparse, json, sys, time
from datetime import datetime, timezone
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

ROOT = Path("/vaults/nvme0/qsb_tower_v1")
AUDIT = ROOT / "data/registries/qsb_f0_http_audit.jsonl"
sys.path.insert(0, str(ROOT / "tools"))
import qsb_f0_receptionist as f0

STARTED = time.time()
SEEN = 0

def utc() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds").replace("+00:00","Z")

def audit(row: dict) -> None:
    try:
        AUDIT.parent.mkdir(parents=True, exist_ok=True)
        with AUDIT.open("a") as fp:
            fp.write(json.dumps(row) + "\n")
    except Exception:
        pass

class F0Handler(BaseHTTPRequestHandler):
    def log_message(self, fmt, *a): return  # quiet

    def _send(self, code: int, obj: dict) -> None:
        data = json.dumps(obj).encode()
        self.send_response(code)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(data)))
        self.end_headers()
        self.wfile.write(data)

    def _read(self) -> dict:
        try:
            n = int(self.headers.get("Content-Length") or 0)
            if n <= 0: return {}
            return json.loads(self.rfile.read(n).decode() or "{}")
        except Exception:
            return {}

    def do_GET(self):
        global SEEN
        if self.path in ("/", "/status", "/health"):
            self._send(200, {"ok": True, "service": "f0_receptionist",
                             "ts": utc(),
                             "uptime_s": int(time.time() - STARTED),
                             "calls_seen": SEEN})
            return
        self._send(404, {"error": "not_found", "path": self.path})

    def do_POST(self):
        global SEEN
        body = self._read()
        SEEN += 1
        try:
            if self.path == "/api/f0/greet":
                r = f0.greet(body.get("caller_id"))
                audit({"ts": utc(), "route": "greet", "caller_id": body.get("caller_id")})
                self._send(200, r)
                return
            if self.path == "/api/f0/converse":
                caller = body.get("caller_id") or "unknown"
                text = body.get("text") or ""
                r = f0.converse(caller, text)
                audit({"ts": utc(), "route": "converse", "caller_id": caller,
                       "text_head": text[:80], "reply_head": (r.get("reply") or "")[:80]})
                self._send(200, r)
                return
            if self.path == "/api/f0/close":
                r = f0.close_call(body.get("caller_id") or "unknown",
                                  body.get("summary",""))
                audit({"ts": utc(), "route": "close", "caller_id": body.get("caller_id")})
                self._send(200, r)
                return
        except Exception as e:
            audit({"ts": utc(), "route": self.path, "err": str(e)[:200]})
            self._send(500, {"error": "internal", "detail": str(e)[:200]})
            return
        self._send(404, {"error": "not_found", "path": self.path})


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--host", default="127.0.0.1")
    ap.add_argument("--port", type=int, default=8765)
    args = ap.parse_args()
    srv = ThreadingHTTPServer((args.host, args.port), F0Handler)
    print(f"[f0_http] listening on {args.host}:{args.port}", flush=True)
    try:
        srv.serve_forever()
    except KeyboardInterrupt:
        srv.shutdown()

if __name__ == "__main__":
    main()
