"""
qsb_stt_whisper.py — STT sidecar for the QSB HQ voice server.

Runs in the neuralnexus venv (torch cu128 + transformers + CUDA). Loads the
whisper tiny.en GGML weights (re-homed into transformers by ggml_whisper.py)
once, then serves loopback HTTP so the main voice server (.venv) can proxy to it.

  POST /stt     body = 16kHz mono PCM WAV bytes -> {"text": "..."}
  GET  /health  -> {"ok": true, "device": "cuda", "model": "whisper-tiny.en(ggml)"}

Bound to 127.0.0.1:8796. Loopback only. No external authority.
"""
from __future__ import annotations
import io, json, logging, os, sys, time, wave
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

sys.path.insert(0, "/vaults/nvme0/qsb_tower_v1/tools")
import numpy as np
from ggml_whisper import GgmlWhisper

MODEL = os.environ.get("QSB_WHISPER_GGML", "/vaults/nvme0/qsb_tower_v1/data/whisper/ggml-tiny.en.bin")
HOST, PORT = "127.0.0.1", int(os.environ.get("QSB_STT_PORT", "8796"))
LOG = "/vaults/nvme0/qsb_tower_v1/data/logs/voice_stt.log"

os.makedirs(os.path.dirname(LOG), exist_ok=True)
logging.basicConfig(level=logging.INFO, filename=LOG,
                    format="[%(asctime)s] %(levelname)s qsb.stt - %(message)s")
log = logging.getLogger("qsb.stt")

_ENGINE = None


def engine():
    global _ENGINE
    if _ENGINE is None:
        t = time.time()
        _ENGINE = GgmlWhisper(MODEL)
        log.info("model loaded device=%s in %.2fs", _ENGINE.device, time.time() - t)
    return _ENGINE


def wav_bytes_to_audio(data: bytes):
    w = wave.open(io.BytesIO(data), "rb")
    sr, ch, sw = w.getframerate(), w.getnchannels(), w.getsampwidth()
    raw = w.readframes(w.getnframes())
    w.close()
    if sw != 2:
        raise ValueError(f"need 16-bit wav, got sampwidth={sw}")
    a = np.frombuffer(raw, dtype=np.int16).astype(np.float32) / 32768.0
    if ch > 1:
        a = a.reshape(-1, ch).mean(axis=1)
    if sr != 16000:
        raise ValueError(f"need 16kHz wav, got {sr}")
    return a


class Handler(BaseHTTPRequestHandler):
    def log_message(self, fmt, *a):
        log.info("%s - %s", self.address_string(), fmt % a)

    def _json(self, status, payload):
        body = json.dumps(payload).encode()
        self.send_response(status)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def do_GET(self):
        if self.path == "/health":
            eng = _ENGINE
            self._json(200, {"ok": eng is not None,
                             "device": getattr(eng, "device", None),
                             "model": "whisper-tiny.en(ggml)"})
        else:
            self._json(404, {"ok": False, "error": "not_found"})

    def do_POST(self):
        if self.path != "/stt":
            self._json(404, {"ok": False, "error": "not_found"})
            return
        length = int(self.headers.get("Content-Length") or 0)
        data = self.rfile.read(length)
        if not data:
            self._json(400, {"ok": False, "error": "empty_body"})
            return
        try:
            audio = wav_bytes_to_audio(data)
            t = time.time()
            text = engine().transcribe(audio)
            dt = time.time() - t
            log.info("stt %d samples -> %r (%.2fs)", len(audio), text[:80], dt)
            self._json(200, {"ok": True, "text": text,
                             "audio_sec": round(len(audio) / 16000, 2),
                             "stt_sec": round(dt, 3)})
        except Exception as e:
            log.exception("stt failed")
            self._json(500, {"ok": False, "error": str(e)[:200]})


if __name__ == "__main__":
    engine()  # eager-load so /health is honest and first request is fast
    log.info("STT sidecar listening on %s:%d", HOST, PORT)
    print(f"[qsb_stt_whisper] ready on {HOST}:{PORT}", flush=True)
    ThreadingHTTPServer((HOST, PORT), Handler).serve_forever()
