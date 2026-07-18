#!/usr/bin/env python3
"""qsb_node_listener_acer.py — Acer-node HTTP listener.

Cross-platform variant of tools/qsb_node_listener.py for the Acer laptop.
Endpoints:
  GET  /          -> {"ok": true, "node": "acer", "name": "Acer-Node", "ts": iso}
  GET  /status    -> host + process summary
  GET  /health    -> liveness
  GET  /peers     -> known peers (HQ + ThinkPad)
  POST /msg       -> accept message, append to local inbox
  POST /result    -> accept result, append to results.jsonl
  POST /file      -> accept file (?name=... with raw body)

ROOT is the folder this script lives in (or set QSB_ACER_ROOT env var).
Node identity read from qsb_acer_identity.json in the same folder if present,
otherwise defaults to acer / Acer-Node.

Run:  python qsb_node_listener_acer.py --host 0.0.0.0 --port 9100
"""
from __future__ import annotations
import argparse
import json
import os
import platform
import socket
import time
from datetime import datetime, timezone
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

ROOT = Path(os.environ.get("QSB_ACER_ROOT", Path(__file__).resolve().parent))
INBOX = ROOT / "inbox"
RESULTS = ROOT / "results.jsonl"
ARTIFACTS = ROOT / "artifacts"
IDENTITY = ROOT / "qsb_acer_identity.json"
INBOX.mkdir(parents=True, exist_ok=True)
ARTIFACTS.mkdir(parents=True, exist_ok=True)

NODE_ID = "acer"
NODE_NAME = "Acer-Node"
PEERS = [
    {"id": "hq", "url": "http://172.20.10.2:9100"},
    {"id": "thinkpad", "url": "http://192.168.0.10:9100"},
]
if IDENTITY.exists():
    try:
        _d = json.loads(IDENTITY.read_text())
        NODE_ID = _d.get("node_id", NODE_ID)
        NODE_NAME = _d.get("node_name", NODE_NAME)
        if isinstance(_d.get("peers"), list):
            PEERS = _d["peers"]
    except Exception:
        pass


def utc_iso() -> str:
    return datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")


def host_summary() -> dict:
    return {
        "hostname": socket.gethostname(),
        "platform": platform.platform(),
        "python": platform.python_version(),
        "pid": os.getpid(),
        "cwd": str(ROOT),
    }


class H(BaseHTTPRequestHandler):
    def log_message(self, *args, **kwargs):
        pass

    def _send(self, code: int, body):
        data = json.dumps(body).encode() if isinstance(body, dict) else body
        self.send_response(code)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(data)))
        self.send_header("Cache-Control", "no-store")
        self.end_headers()
        self.wfile.write(data)

    def _read_body(self) -> bytes:
        n = int(self.headers.get("Content-Length", 0) or 0)
        if n <= 0:
            return b""
        chunks, remaining = [], n
        while remaining > 0:
            part = self.rfile.read(remaining)
            if not part:
                break
            chunks.append(part)
            remaining -= len(part)
        return b"".join(chunks)

    def do_GET(self):
        if self.path == "/" or self.path == "/health":
            self._send(200, {"ok": True, "node": NODE_ID, "name": NODE_NAME, "ts": utc_iso()}); return
        if self.path == "/status":
            self._send(200, {"node": NODE_ID, "ts": utc_iso(), "host": host_summary()}); return
        if self.path == "/peers":
            self._send(200, {"peers": PEERS, "self": {"id": NODE_ID, "name": NODE_NAME}}); return
        self._send(404, {"error": "not_found", "path": self.path})

    def do_POST(self):
        body = self._read_body()
        try:
            payload = json.loads(body.decode()) if body else {}
        except Exception:
            payload = {"raw": body.decode("utf-8", errors="replace")}
        if self.path == "/msg":
            payload["received_at"] = utc_iso()
            mid = payload.get("id", f"in-{int(time.time()*1000)}")
            sender = payload.get("from", "unknown")
            ts_slug = utc_iso().replace(":", "").replace("-", "")
            (INBOX / f"{ts_slug}_{sender}_{mid}.json").write_text(json.dumps(payload, indent=2))
            self._send(200, {"ack": True, "node": NODE_ID, "ts": utc_iso(), "msg_id": mid}); return
        if self.path == "/result":
            with RESULTS.open("a") as f:
                f.write(json.dumps({"ts": utc_iso(), **payload}) + "\n")
            self._send(200, {"ack": True, "node": NODE_ID, "ts": utc_iso()}); return
        if self.path.startswith("/file"):
            from urllib.parse import urlparse, parse_qs
            qs = parse_qs(urlparse(self.path).query)
            name = (qs.get("name") or [f"incoming_{utc_iso().replace(':', '')}"])[0]
            (ARTIFACTS / name).write_bytes(body)
            self._send(200, {"ack": True, "node": NODE_ID, "saved_as": name, "ts": utc_iso()}); return
        self._send(404, {"error": "not_found", "path": self.path})


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--host", default="0.0.0.0")
    ap.add_argument("--port", type=int, default=9100)
    args = ap.parse_args()
    srv = ThreadingHTTPServer((args.host, args.port), H)
    print(f"qsb_node_listener ({NODE_NAME}) on {args.host}:{args.port}")
    print(f"  ROOT={ROOT}")
    print(f"  peers={[p['url'] for p in PEERS]}")
    try:
        srv.serve_forever()
    except KeyboardInterrupt:
        pass


if __name__ == "__main__":
    main()
