#!/usr/bin/env python3
"""qsb_node_listener.py — HQ-node HTTP listener.

Matches the ThinkPad-node's skyscraper.py protocol shape (best-effort, no code
shared yet). Endpoints:
  GET  /          → {"ok": true, "node": "hq", "name": "HQ-Node", "ts": iso}
  GET  /status    → fleet + dashboard summary
  GET  /health    → liveness
  GET  /peers     → known peers
  GET  /tasks     → tail of shared_task_board.json
  POST /msg       → accept a message, append to inbox
  POST /task      → accept a task spec, append to board
  POST /result    → accept a result, append to results.jsonl
  POST /file      → accept arbitrary file (multipart/form-data OR raw body + ?name=)

Listens on 0.0.0.0:9100 by default. Drop incoming messages into
data/team_memory/shared/node_inbox/<ts>_<from>.json
"""
from __future__ import annotations
import argparse
import json
import os
import time
from datetime import datetime, timezone
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

ROOT = Path("/vaults/nvme0/qsb_tower_v1")
INBOX = ROOT / "data/team_memory/shared/node_inbox"
RESULTS = ROOT / "data/team_memory/shared/node_results.jsonl"
TASKS = ROOT / "data/team_memory/shared/shared_task_board.json"
ARTIFACTS = ROOT / "data/team_memory/shared/node_artifacts"
INBOX.mkdir(parents=True, exist_ok=True)
ARTIFACTS.mkdir(parents=True, exist_ok=True)

NODE_ID = "hq"
NODE_NAME = "HQ-Node"
PEER_URL = "http://192.168.0.10:9100"

def utc_iso() -> str:
    return datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")


def fleet_summary() -> dict:
    import subprocess
    try:
        r = subprocess.run(["ps", "-eo", "args", "ww"], capture_output=True, text=True, timeout=4)
        lines = r.stdout.splitlines()
    except Exception:
        lines = []
    n = lambda s: sum(1 for ln in lines if s in ln)
    return {
        "belief_traders": n("qsb_belief_driven_trader.py"),
        "ensembles": n("qsb_ensemble_coordinator.py"),
        "bus": n("qsb_event_bus.py"),
        "aggregator": n("qsb_trader_pnl_aggregator_bus.py"),
        "ue_editor": sum(1 for ln in lines if "UnrealEditor" in ln and "QSB_Skyscraper" in ln),
    }


def pot_summary() -> dict:
    p = ROOT / "data/registries/qsb_portfolio_pot.json"
    try:
        d = json.loads(p.read_text())
        return {
            "open": len(d.get("open_positions", {})),
            "committed_gbp": round(d.get("committed_gbp", 0), 2),
            "cap_gbp": d.get("cap_gbp", 5000),
            "age_seconds": round(time.time() - p.stat().st_mtime, 1),
        }
    except Exception as e:
        return {"error": str(e)[:80]}


class H(BaseHTTPRequestHandler):
    def log_message(self, *args, **kwargs):
        pass

    def _send(self, code: int, body: dict | bytes, content_type: str = "application/json"):
        if isinstance(body, dict):
            data = json.dumps(body).encode()
        else:
            data = body
        self.send_response(code)
        self.send_header("Content-Type", content_type)
        self.send_header("Content-Length", str(len(data)))
        self.send_header("Cache-Control", "no-store")
        self.end_headers()
        self.wfile.write(data)

    def _read_body(self) -> bytes:
        # Robust body reader: handles short socket reads (Content-Length) and
        # chunked transfer-encoding. Loops until the full body is received.
        n = int(self.headers.get("Content-Length", 0) or 0)
        if n > 0:
            chunks = []
            remaining = n
            while remaining > 0:
                chunk = self.rfile.read(remaining)
                if not chunk:
                    break  # peer closed early; return what we have
                chunks.append(chunk)
                remaining -= len(chunk)
            return b"".join(chunks)
        te = (self.headers.get("Transfer-Encoding", "") or "").lower()
        if "chunked" in te:
            chunks = []
            while True:
                size_line = self.rfile.readline().strip()
                if not size_line:
                    continue
                try:
                    size = int(size_line.split(b";", 1)[0], 16)
                except ValueError:
                    break
                if size == 0:
                    # consume trailing headers / final CRLF
                    while True:
                        trailer = self.rfile.readline()
                        if trailer in (b"\r\n", b"\n", b""):
                            break
                    break
                data = b""
                while len(data) < size:
                    part = self.rfile.read(size - len(data))
                    if not part:
                        break
                    data += part
                chunks.append(data)
                self.rfile.read(2)  # consume CRLF after each chunk
            return b"".join(chunks)
        return b""

    def do_GET(self):
        if self.path == "/":
            self._send(200, {"ok": True, "node": NODE_ID, "name": NODE_NAME, "ts": utc_iso()}); return
        if self.path == "/health":
            self._send(200, {"ok": True, "node": NODE_ID, "ts": utc_iso()}); return
        if self.path == "/status":
            self._send(200, {
                "node": NODE_ID, "ts": utc_iso(),
                "fleet": fleet_summary(),
                "pot": pot_summary(),
                "dashboards": {
                    "truth_8848": "http://172.20.10.2:8848/",
                    "old_8847": "http://172.20.10.2:8847/",
                    "studio_8849": "http://172.20.10.2:8849/",
                },
            }); return
        if self.path == "/peers":
            self._send(200, {"peers": [{"id": "thinkpad", "url": PEER_URL}]}); return
        if self.path == "/tasks":
            try:
                tb = json.loads(TASKS.read_text()) if TASKS.exists() else {"tasks": []}
            except Exception:
                tb = {"tasks": []}
            self._send(200, tb); return
        self._send(404, {"error": "not_found", "path": self.path})

    def do_POST(self):
        body = self._read_body()
        if self.path == "/msg":
            try:
                msg = json.loads(body.decode()) if body else {}
            except Exception:
                msg = {"raw": body.decode("utf-8", errors="replace")}
            msg["received_at"] = utc_iso()
            mid = msg.get("id", f"in-{int(time.time()*1000)}")
            sender = msg.get("from", "unknown")
            (INBOX / f"{utc_iso().replace(':', '').replace('-', '')}_{sender}_{mid}.json").write_text(json.dumps(msg, indent=2))
            self._send(200, {"ack": True, "node": NODE_ID, "ts": utc_iso(), "msg_id": mid}); return
        if self.path == "/task":
            try:
                task = json.loads(body.decode()) if body else {}
            except Exception:
                task = {"raw": body.decode("utf-8", errors="replace")}
            task["received_at"] = utc_iso()
            try:
                tb = json.loads(TASKS.read_text()) if TASKS.exists() else {"tasks": []}
            except Exception:
                tb = {"tasks": []}
            tb["tasks"].append(task)
            TASKS.write_text(json.dumps(tb, indent=2))
            self._send(200, {"ack": True, "node": NODE_ID, "ts": utc_iso()}); return
        if self.path == "/result":
            try:
                res = json.loads(body.decode()) if body else {}
            except Exception:
                res = {"raw": body.decode("utf-8", errors="replace")}
            with RESULTS.open("a") as f:
                f.write(json.dumps({"ts": utc_iso(), **res}) + "\n")
            self._send(200, {"ack": True, "node": NODE_ID, "ts": utc_iso()}); return
        if self.path.startswith("/file"):
            # accept either ?name=foo.py with raw body, OR multipart (basic)
            from urllib.parse import urlparse, parse_qs
            qs = parse_qs(urlparse(self.path).query)
            name = (qs.get("name") or ["incoming_" + utc_iso().replace(":", "")])[0]
            (ARTIFACTS / name).write_bytes(body)
            self._send(200, {"ack": True, "node": NODE_ID, "ts": utc_iso(), "saved_as": str(ARTIFACTS / name)}); return
        self._send(404, {"error": "not_found", "path": self.path})


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--host", default="0.0.0.0")
    ap.add_argument("--port", type=int, default=9100)
    args = ap.parse_args()
    srv = ThreadingHTTPServer((args.host, args.port), H)
    print(f"qsb_node_listener (HQ) on {args.host}:{args.port}  peer={PEER_URL}")
    try:
        srv.serve_forever()
    except KeyboardInterrupt:
        pass


if __name__ == "__main__":
    main()
