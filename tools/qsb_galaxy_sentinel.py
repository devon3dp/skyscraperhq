"""
qsb_galaxy_sentinel.py — QSB Tower V1.5 first-gateway bouncer (phone node)

Lineage:
  Skyscraper owns the infrastructure. Models are temporary external tenants.
  Workers are external. The Galaxy phone is a worker HOST, not a worker.
  The phone is a remote node of the tower, reachable via `adb reverse` from
  the fortress side and via 127.0.0.1 from the receptionist daemon
  (~/qsb_galaxy_receptionist.sh).

Safety stance (per CLAUDE.md, V1.3 + 2026-06-08 + 2026-06-10 + 2026-06-13):
  - This sentinel is a BOUNCER, not a decision-maker.
  - It does NOT execute payloads.
  - It does NOT call out to the tower for verdicts (no provider_execution,
    no live_dispatch, no autonomous worker behaviour).
  - It does NOT unwrap sealed lift packets — it inspects shape only.
  - Allowed action set: ACCEPT (write to inbox) or DROP (write to audit).
  - On any ambiguity: DROP, log reason, keep listening.

Inputs:  POST /ingest  (loopback / adb reverse only)
Outputs: append-only JSONL inbox + append-only JSONL audit
Process: single-threaded http.server, no deps beyond stdlib.
"""

from __future__ import annotations

import json
import os
import signal
import sys
import time
import uuid
from collections import deque
from http.server import BaseHTTPRequestHandler, HTTPServer
from pathlib import Path
from threading import Lock

BIND_HOST = "127.0.0.1"
BIND_PORT = 8866

MAX_BODY_BYTES = 64 * 1024
NONCE_RING_SIZE = 1024
REQUIRED_KEYS = ("intent", "ts", "nonce", "payload")

DEFAULT_ALLOW_IPS = "127.0.0.1"
DEFAULT_INTENTS = "health.pulse,call.ingest,announce.tannoy"
DEFAULT_RPM = 60

HOME = Path(os.path.expanduser("~"))
DEFAULT_SD_ROOT = HOME / "skyscraperhqphone"
DEFAULT_AUDIT = DEFAULT_SD_ROOT / "qsb_sentinel_audit.jsonl"
DEFAULT_INBOX = DEFAULT_SD_ROOT / "sentinel_inbox.jsonl"

SENTINEL_VERSION = "1.5.0"
SENTINEL_NODE = "galaxy_phone"


def _csv_env(name: str, default: str) -> list[str]:
    raw = os.environ.get(name, default)
    return [x.strip() for x in raw.split(",") if x.strip()]


ALLOW_IPS = set(_csv_env("QSB_SENTINEL_ALLOW", DEFAULT_ALLOW_IPS))
ALLOW_INTENTS = set(_csv_env("QSB_SENTINEL_INTENTS", DEFAULT_INTENTS))
RPM = int(os.environ.get("QSB_SENTINEL_RPM", str(DEFAULT_RPM)))
AUDIT_PATH = Path(os.environ.get("QSB_SENTINEL_AUDIT", str(DEFAULT_AUDIT)))
INBOX_PATH = Path(os.environ.get("QSB_SENTINEL_INBOX", str(DEFAULT_INBOX)))

START_TS = time.time()
COUNTERS = {
    "allows": 0,
    "drops_by_reason": {},
    "last_event_ts": None,
}
NONCE_RING: deque[str] = deque(maxlen=NONCE_RING_SIZE)
NONCE_SET: set[str] = set()
BUCKETS: dict[str, dict[str, float]] = {}

_io_lock = Lock()


def _ensure_dirs() -> None:
    for p in (AUDIT_PATH.parent, INBOX_PATH.parent):
        try:
            p.mkdir(parents=True, exist_ok=True)
        except OSError as e:
            sys.stderr.write(f"[sentinel] cannot create {p}: {e}\n")
            raise


def _now_iso() -> str:
    return time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())


def _audit(event: str, source: str, intent: str | None, reason: str | None,
           extra: dict | None = None) -> None:
    row = {
        "ts": _now_iso(),
        "node": SENTINEL_NODE,
        "version": SENTINEL_VERSION,
        "event": event,
        "source": source,
        "intent": intent,
        "reason": reason,
        "audit_id": uuid.uuid4().hex,
    }
    if extra:
        row.update(extra)
    line = json.dumps(row, separators=(",", ":")) + "\n"
    with _io_lock:
        try:
            with AUDIT_PATH.open("a", encoding="utf-8") as f:
                f.write(line)
                f.flush()
        except OSError as e:
            sys.stderr.write(f"[sentinel] audit write failed: {e}\n")
    COUNTERS["last_event_ts"] = row["ts"]
    if event == "allow":
        COUNTERS["allows"] += 1
    elif event == "drop":
        COUNTERS["drops_by_reason"][reason or "unknown"] = (
            COUNTERS["drops_by_reason"].get(reason or "unknown", 0) + 1
        )


def _fanout(packet: dict, source: str) -> None:
    row = {
        "ts_received": _now_iso(),
        "source": source,
        "packet": packet,
    }
    line = json.dumps(row, separators=(",", ":")) + "\n"
    with _io_lock:
        try:
            with INBOX_PATH.open("a", encoding="utf-8") as f:
                f.write(line)
                f.flush()
        except OSError as e:
            sys.stderr.write(f"[sentinel] inbox write failed: {e}\n")
            raise


def _take_token(ip: str) -> bool:
    now = time.time()
    b = BUCKETS.get(ip)
    if b is None:
        BUCKETS[ip] = {"tokens": float(RPM - 1), "last_refill": now}
        return True
    elapsed = now - b["last_refill"]
    refill = elapsed * (RPM / 60.0)
    b["tokens"] = min(float(RPM), b["tokens"] + refill)
    b["last_refill"] = now
    if b["tokens"] >= 1.0:
        b["tokens"] -= 1.0
        return True
    return False


def _shape_ok(obj: object) -> tuple[bool, str | None]:
    if not isinstance(obj, dict):
        return False, "body_not_object"
    for k in REQUIRED_KEYS:
        if k not in obj:
            return False, f"missing_key:{k}"
    if not isinstance(obj["intent"], str):
        return False, "intent_not_string"
    if not isinstance(obj["ts"], str):
        return False, "ts_not_string"
    if not isinstance(obj["nonce"], str) or not obj["nonce"]:
        return False, "nonce_not_string"
    if not isinstance(obj["payload"], dict):
        return False, "payload_not_object"
    return True, None


class SentinelHandler(BaseHTTPRequestHandler):
    server_version = f"QSBSentinel/{SENTINEL_VERSION}"

    def log_message(self, fmt: str, *args) -> None:
        return

    def _respond(self, code: int, body: dict) -> None:
        raw = json.dumps(body, separators=(",", ":")).encode("utf-8")
        self.send_response(code)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(raw)))
        self.send_header("Cache-Control", "no-store")
        self.end_headers()
        self.wfile.write(raw)

    def do_GET(self) -> None:
        if self.path != "/health":
            self._respond(404, {"error": "not_found"})
            return
        self._respond(200, {
            "ok": True,
            "node": SENTINEL_NODE,
            "version": SENTINEL_VERSION,
            "uptime_s": int(time.time() - START_TS),
            "allows": COUNTERS["allows"],
            "drops_by_reason": dict(COUNTERS["drops_by_reason"]),
            "last_event_ts": COUNTERS["last_event_ts"],
            "allow_ips": sorted(ALLOW_IPS),
            "allow_intents": sorted(ALLOW_INTENTS),
            "rpm": RPM,
        })

    def do_POST(self) -> None:
        src = self.client_address[0]
        if self.path != "/ingest":
            _audit("drop", src, None, "unknown_path", {"path": self.path})
            self._respond(404, {"error": "not_found"})
            return

        if src not in ALLOW_IPS:
            _audit("drop", src, None, "source_not_allowed")
            self._respond(403, {"error": "source_not_allowed"})
            return

        if not _take_token(src):
            _audit("drop", src, None, "rate_limited")
            self._respond(429, {"error": "rate_limited"})
            return

        length_raw = self.headers.get("Content-Length")
        try:
            length = int(length_raw) if length_raw is not None else -1
        except ValueError:
            _audit("drop", src, None, "bad_content_length")
            self._respond(400, {"error": "bad_content_length"})
            return
        if length < 0:
            _audit("drop", src, None, "missing_content_length")
            self._respond(411, {"error": "length_required"})
            return
        if length > MAX_BODY_BYTES:
            _audit("drop", src, None, "body_too_large",
                   {"declared_len": length})
            self._respond(413, {"error": "body_too_large"})
            return

        raw = self.rfile.read(length)
        if len(raw) > MAX_BODY_BYTES:
            _audit("drop", src, None, "body_too_large_actual")
            self._respond(413, {"error": "body_too_large"})
            return

        try:
            obj = json.loads(raw.decode("utf-8"))
        except (UnicodeDecodeError, json.JSONDecodeError) as e:
            _audit("drop", src, None, "bad_json", {"err": str(e)[:120]})
            self._respond(400, {"error": "bad_json"})
            return

        ok, why = _shape_ok(obj)
        if not ok:
            _audit("drop", src, None, f"bad_shape:{why}")
            self._respond(400, {"error": "bad_shape", "reason": why})
            return

        intent = obj["intent"]
        nonce = obj["nonce"]

        if intent not in ALLOW_INTENTS:
            _audit("drop", src, intent, "intent_not_allowed")
            self._respond(403, {"error": "intent_not_allowed"})
            return

        if nonce in NONCE_SET:
            _audit("drop", src, intent, "replay_nonce", {"nonce": nonce})
            self._respond(409, {"error": "replay_nonce"})
            return
        if len(NONCE_RING) == NONCE_RING.maxlen:
            evicted = NONCE_RING[0]
            NONCE_SET.discard(evicted)
        NONCE_RING.append(nonce)
        NONCE_SET.add(nonce)

        try:
            _fanout(obj, src)
        except OSError:
            _audit("drop", src, intent, "fanout_io_error")
            self._respond(500, {"error": "fanout_io_error"})
            return

        _audit("allow", src, intent, None, {"nonce": nonce})
        self._respond(202, {"ok": True, "queued": True})


_server: HTTPServer | None = None


def _graceful_shutdown(signum, frame):
    sys.stderr.write(f"[sentinel] signal {signum} — shutting down\n")
    _audit("drop", "self", None, "shutdown_signal",
           {"signum": int(signum)})
    if _server is not None:
        try:
            _server.shutdown()
        except OSError as e:
            sys.stderr.write(f"[sentinel] shutdown error: {e}\n")


def main() -> int:
    _ensure_dirs()
    _audit("allow", "self", None, "boot",
           {"bind": f"{BIND_HOST}:{BIND_PORT}",
            "allow_ips": sorted(ALLOW_IPS),
            "allow_intents": sorted(ALLOW_INTENTS),
            "rpm": RPM,
            "audit_path": str(AUDIT_PATH),
            "inbox_path": str(INBOX_PATH)})

    signal.signal(signal.SIGTERM, _graceful_shutdown)
    signal.signal(signal.SIGINT, _graceful_shutdown)

    global _server
    _server = HTTPServer((BIND_HOST, BIND_PORT), SentinelHandler)
    sys.stderr.write(
        f"[sentinel] listening on {BIND_HOST}:{BIND_PORT} "
        f"(version {SENTINEL_VERSION})\n"
    )
    try:
        _server.serve_forever(poll_interval=0.5)
    except OSError as e:
        sys.stderr.write(f"[sentinel] serve error: {e}\n")
        return 1
    finally:
        try:
            _server.server_close()
        except OSError:
            pass
    return 0


if __name__ == "__main__":
    sys.exit(main())
