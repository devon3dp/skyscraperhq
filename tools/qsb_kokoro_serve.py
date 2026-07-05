"""
qsb_kokoro_serve.py — local TTS sidecar for the QSB Tower.

Serves Kokoro ONNX text-to-speech on :8851. Used by worker narration,
F0 Iris voice replies, and the colonel observer.

  POST /tts        body {"text": str, "voice": str?} -> audio/wav
  GET  /health     -> {"ok": true, "voices": [...]}
  GET  /voices     -> {"voices": [...]}

Bound to loopback. No real-money / external-execution authority.
"""

from __future__ import annotations

import io
import json
import logging
import wave
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

import numpy as np
from kokoro_onnx import Kokoro

ROOT = Path("/vaults/nvme0/qsb_tower_v1")
MODEL_PATH = ROOT / "data/models/kokoro/kokoro-v1.0.onnx"
VOICES_PATH = ROOT / "data/models/kokoro/voices-v1.0.bin"
DEFAULT_VOICE = "af_heart"
HOST = "127.0.0.1"
PORT = 8851

logging.basicConfig(level=logging.INFO,
                    format="[%(asctime)s] %(levelname)s qsb.kokoro - %(message)s")
log = logging.getLogger("qsb.kokoro")

_kokoro: Kokoro | None = None
_voices: list[str] = []


def _load() -> tuple[Kokoro | None, list[str], str | None]:
    if not MODEL_PATH.exists() or not VOICES_PATH.exists():
        return None, [], f"missing model files at {MODEL_PATH.parent}"
    try:
        k = Kokoro(str(MODEL_PATH), str(VOICES_PATH))
        voices = sorted(k.get_voices()) if hasattr(k, "get_voices") else []
        return k, voices, None
    except Exception as e:
        return None, [], f"kokoro init failed: {e!r}"


def _wav_bytes(samples: np.ndarray, sample_rate: int) -> bytes:
    samples = np.clip(samples, -1.0, 1.0)
    pcm = (samples * 32767).astype(np.int16).tobytes()
    buf = io.BytesIO()
    with wave.open(buf, "wb") as w:
        w.setnchannels(1)
        w.setsampwidth(2)
        w.setframerate(sample_rate)
        w.writeframes(pcm)
    return buf.getvalue()


class Handler(BaseHTTPRequestHandler):
    def log_message(self, fmt, *a):
        log.info("%s - %s", self.address_string(), fmt % a)

    def _json(self, status: int, payload: dict) -> None:
        body = json.dumps(payload).encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def _wav(self, data: bytes) -> None:
        self.send_response(200)
        self.send_header("Content-Type", "audio/wav")
        self.send_header("Content-Length", str(len(data)))
        self.end_headers()
        self.wfile.write(data)

    def do_GET(self):
        if self.path == "/health":
            self._json(200, {"ok": _kokoro is not None,
                              "voices_count": len(_voices),
                              "model_path": str(MODEL_PATH),
                              "model_ready": MODEL_PATH.exists()})
            return
        if self.path == "/voices":
            self._json(200, {"voices": _voices})
            return
        self._json(404, {"ok": False, "error": "not_found"})

    def do_POST(self):
        if self.path != "/tts":
            self._json(404, {"ok": False, "error": "not_found"})
            return
        if _kokoro is None:
            self._json(503, {"ok": False, "error": "model_not_loaded"})
            return
        length = int(self.headers.get("Content-Length") or 0)
        try:
            payload = json.loads(self.rfile.read(length) or b"{}")
        except ValueError:
            self._json(400, {"ok": False, "error": "bad_json"})
            return
        text = (payload.get("text") or "").strip()
        if not text:
            self._json(400, {"ok": False, "error": "empty_text"})
            return
        voice = payload.get("voice") or DEFAULT_VOICE
        if _voices and voice not in _voices:
            self._json(400, {"ok": False, "error": "unknown_voice",
                              "default": DEFAULT_VOICE,
                              "voices_sample": _voices[:6]})
            return
        try:
            samples, sample_rate = _kokoro.create(text, voice=voice, speed=1.0,
                                                    lang="en-us")
        except Exception as e:
            log.error("synth failed: %r", e)
            self._json(500, {"ok": False, "error": f"synth_failed: {e!r}"})
            return
        self._wav(_wav_bytes(samples, sample_rate))


def main() -> int:
    global _kokoro, _voices
    _kokoro, _voices, err = _load()
    if err:
        log.warning("starting in degraded mode: %s", err)
    else:
        log.info("kokoro ready, %d voices, default=%s", len(_voices), DEFAULT_VOICE)
    httpd = ThreadingHTTPServer((HOST, PORT), Handler)
    log.info("serving on http://%s:%d", HOST, PORT)
    try:
        httpd.serve_forever()
    except KeyboardInterrupt:
        log.info("shutting down")
    finally:
        httpd.server_close()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
