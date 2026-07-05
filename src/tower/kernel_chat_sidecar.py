#!/usr/bin/env python3
"""
QSB Tower V1.3 — Kernel Chat Sidecar API

Local-only browser bridge:
Dashboard browser -> localhost:8766 -> kernel_dialogue_adapter -> active QSB Kernel

Safety:
- No external providers.
- No OpenClaw execution.
- No worker dispatch.
- No autonomous dispatch.
- Local Ollama only through existing kernel dialogue adapter.
"""

from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from datetime import datetime, timezone
import json
import sys
import urllib.parse

ROOT = Path("/vaults/nvme0/qsb_tower_v1")
SRC = ROOT / "src"
LOG = ROOT / "data/logs/kernel_dialogue.jsonl"

sys.path.insert(0, str(SRC))

HOST = "127.0.0.1"
PORT = 8766


def load_json(path, fallback=None):
    if fallback is None:
        fallback = {}
    try:
        return json.loads(Path(path).read_text(encoding="utf-8"))
    except Exception:
        return fallback


def tail_jsonl(path, limit=20):
    p = Path(path)
    if not p.exists():
        return []
    lines = p.read_text(encoding="utf-8", errors="ignore").splitlines()[-limit:]
    out = []
    for line in lines:
        try:
            out.append(json.loads(line))
        except Exception:
            out.append({"raw": line})
    return out


def health_payload():
    activation = load_json(ROOT / "data/registries/kernel_activation_report.json")
    local_model = load_json(ROOT / "data/registries/local_model_inference_status.json")
    policy = load_json(ROOT / "data/registries/local_model_inference_policy.json")

    return {
        "ok": True,
        "service": "qsb_kernel_chat_sidecar",
        "ts": datetime.now(timezone.utc).isoformat(),
        "host": HOST,
        "port": PORT,
        "kernel_installed": activation.get("kernel_installed"),
        "QSBKernelCore_instantiated": activation.get("QSBKernelCore_instantiated"),
        "activation_status": activation.get("activation_status"),
        "active_kernel_source": activation.get("active_kernel_source"),
        "selected_model": policy.get("selected_model") or local_model.get("selected_model"),
        "local_model_inference_enabled": local_model.get("local_model_inference_enabled"),
        "ollama_detected": local_model.get("ollama_detected"),
        "worker_execution_enabled": False,
        "provider_execution_enabled": False,
        "external_provider_execution_enabled": False,
        "openclaw_execution_enabled": False,
        "live_dispatch_enabled": False,
        "autonomous_workers_enabled": False,
    }


class Handler(BaseHTTPRequestHandler):
    server_version = "QSBKernelChatSidecar/1.0"

    def log_message(self, fmt, *args):
        # Keep terminal clean; requests are already logged by kernel_dialogue_adapter.
        return

    def _headers(self, code=200, content_type="application/json"):
        self.send_response(code)
        self.send_header("Content-Type", content_type)
        self.send_header("Access-Control-Allow-Origin", "http://127.0.0.1:8765")
        self.send_header("Access-Control-Allow-Methods", "GET, POST, OPTIONS")
        self.send_header("Access-Control-Allow-Headers", "Content-Type")
        self.send_header("Cache-Control", "no-store")
        self.end_headers()

    def _json(self, payload, code=200):
        self._headers(code)
        self.wfile.write(json.dumps(payload, indent=2, default=str).encode("utf-8"))

    def do_OPTIONS(self):
        self._headers(204)

    def do_GET(self):
        parsed = urllib.parse.urlparse(self.path)

        if parsed.path == "/api/kernel_chat_health":
            self._json(health_payload())
            return

        if parsed.path == "/api/kernel_chat_history":
            self._json({
                "ok": True,
                "history": tail_jsonl(LOG, 30),
            })
            return

        self._json({"ok": False, "error": "not found", "path": parsed.path}, 404)

    def do_POST(self):
        parsed = urllib.parse.urlparse(self.path)

        if parsed.path != "/api/kernel_chat":
            self._json({"ok": False, "error": "not found", "path": parsed.path}, 404)
            return

        try:
            length = int(self.headers.get("Content-Length", "0"))
            raw = self.rfile.read(length).decode("utf-8")
            body = json.loads(raw or "{}")
            message = str(body.get("message", "")).strip()
            symbolic_only = bool(body.get("symbolic_only", False))

            if not message:
                self._json({"ok": False, "error": "empty message"}, 400)
                return

            from tower.kernel_dialogue_adapter import ask_kernel

            result = ask_kernel(message, prefer_local_model=not symbolic_only)

            # Add explicit sidecar safety confirmation.
            result["sidecar"] = {
                "service": "qsb_kernel_chat_sidecar",
                "local_only": True,
                "worker_execution_enabled": False,
                "provider_execution_enabled": False,
                "external_provider_execution_enabled": False,
                "openclaw_execution_enabled": False,
                "live_dispatch_enabled": False,
                "autonomous_workers_enabled": False,
            }

            self._json(result)
        except Exception as exc:
            self._json({
                "ok": False,
                "error": str(exc),
                "sidecar": "qsb_kernel_chat_sidecar",
            }, 500)


def main():
    print(f"QSB Kernel Chat Sidecar running at http://{HOST}:{PORT}")
    server = ThreadingHTTPServer((HOST, PORT), Handler)
    server.serve_forever()


if __name__ == "__main__":
    main()
