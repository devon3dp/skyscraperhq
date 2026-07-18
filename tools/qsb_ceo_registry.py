#!/usr/bin/env python3
"""qsb_ceo_registry.py — CEO beacon registry + relay hub.

Runs on Oracle (145.241.225.163:9210). Every CEO (HQ, Wren, TP, Acer) POSTs a
beacon every ~30s with its current URL. Every CEO can lookup peers by name.
Every CEO can enqueue a relay message for a peer that's unreachable directly.

Endpoints:
  POST /beacon    body: {ceo, url, mac?, ts?}     → appends beacon.jsonl
  GET  /lookup?ceo=X                              → {ceo,url,ts,age_s} or 404
  GET  /roster                                    → {ceo: {url,ts,age_s}, ...}
  POST /relay     body: {to, frm, kind, body}     → queues to inbox_<to>.jsonl
  GET  /inbox?ceo=X&since=<iso>                   → array of unread messages

Storage: JSONL append-only. Latest-per-ceo held in memory + rebuilt on start.
"""
from __future__ import annotations
import argparse, datetime, json, os, threading
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import parse_qs, urlparse

STATE_DIR = Path(os.environ.get("QSB_CEO_REGISTRY_DIR", "/home/ubuntu/ceo_registry"))
STATE_DIR.mkdir(parents=True, exist_ok=True)
BEACON_LOG = STATE_DIR / "beacon.jsonl"
INBOX_DIR = STATE_DIR / "inbox"
INBOX_DIR.mkdir(exist_ok=True)

_lock = threading.Lock()
_latest: dict[str, dict] = {}


def now_iso() -> str:
    return datetime.datetime.now(datetime.timezone.utc).isoformat()


def age_s(ts_iso: str) -> float:
    try:
        t = datetime.datetime.fromisoformat(ts_iso.replace("Z", "+00:00"))
        return (datetime.datetime.now(datetime.timezone.utc) - t).total_seconds()
    except Exception:
        return -1.0


def _rebuild_latest() -> None:
    if not BEACON_LOG.exists():
        return
    with _lock:
        _latest.clear()
        for line in BEACON_LOG.read_text().splitlines():
            try:
                o = json.loads(line)
                ceo = o.get("ceo")
                if ceo:
                    _latest[ceo] = o
            except Exception:
                continue


class Handler(BaseHTTPRequestHandler):
    def _send(self, code: int, obj) -> None:
        payload = json.dumps(obj).encode()
        self.send_response(code)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(payload)))
        self.end_headers()
        self.wfile.write(payload)

    def _body(self) -> dict:
        n = int(self.headers.get("Content-Length", "0") or 0)
        if not n:
            return {}
        try:
            return json.loads(self.rfile.read(n))
        except Exception:
            return {}

    def log_message(self, fmt: str, *args) -> None:
        return

    def do_GET(self) -> None:
        u = urlparse(self.path)
        q = parse_qs(u.query)
        if u.path == "/lookup":
            ceo = (q.get("ceo") or [""])[0]
            with _lock:
                rec = _latest.get(ceo)
            if not rec:
                return self._send(404, {"error": "not_found", "ceo": ceo})
            out = dict(rec)
            out["age_s"] = round(age_s(rec.get("ts", "")), 2)
            return self._send(200, out)
        if u.path == "/roster":
            with _lock:
                out = {}
                for k, v in _latest.items():
                    out[k] = {"url": v.get("url"), "ts": v.get("ts"), "age_s": round(age_s(v.get("ts", "")), 2)}
            return self._send(200, out)
        if u.path == "/inbox":
            ceo = (q.get("ceo") or [""])[0]
            since = (q.get("since") or [""])[0]
            path = INBOX_DIR / f"inbox_{ceo}.jsonl"
            if not path.exists():
                return self._send(200, [])
            out = []
            for line in path.read_text().splitlines():
                try:
                    o = json.loads(line)
                    if since and o.get("ts", "") <= since:
                        continue
                    out.append(o)
                except Exception:
                    continue
            return self._send(200, out)
        if u.path in ("/", "/state"):
            with _lock:
                return self._send(200, {"service": "qsb_ceo_registry", "ceos": list(_latest.keys()), "ts": now_iso()})
        return self._send(404, {"error": "not_found", "path": u.path})

    def do_POST(self) -> None:
        u = urlparse(self.path)
        b = self._body()
        if u.path == "/beacon":
            ceo = b.get("ceo")
            url = b.get("url")
            if not ceo or not url:
                return self._send(400, {"error": "need ceo+url"})
            row = {"ceo": ceo, "url": url, "mac": b.get("mac"), "ts": b.get("ts") or now_iso()}
            with _lock:
                with BEACON_LOG.open("a") as f:
                    f.write(json.dumps(row) + "\n")
                _latest[ceo] = row
            return self._send(200, {"ok": True, "ceo": ceo, "url": url})
        if u.path == "/relay":
            to = b.get("to")
            if not to:
                return self._send(400, {"error": "need to"})
            row = {"ts": now_iso(), "to": to, "frm": b.get("frm"), "kind": b.get("kind", "msg"), "body": b.get("body")}
            path = INBOX_DIR / f"inbox_{to}.jsonl"
            with _lock:
                with path.open("a") as f:
                    f.write(json.dumps(row) + "\n")
            return self._send(200, {"ok": True, "queued_to": to, "ts": row["ts"]})
        return self._send(404, {"error": "not_found", "path": u.path})


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--port", type=int, default=int(os.environ.get("QSB_CEO_REGISTRY_PORT", "9210")))
    ap.add_argument("--host", default="0.0.0.0")
    args = ap.parse_args()
    _rebuild_latest()
    srv = ThreadingHTTPServer((args.host, args.port), Handler)
    print(f"[qsb_ceo_registry] listening on {args.host}:{args.port} · state={STATE_DIR}", flush=True)
    try:
        srv.serve_forever()
    except KeyboardInterrupt:
        pass


if __name__ == "__main__":
    main()
