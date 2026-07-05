"""
qsb_voice_server.py — self-contained HQ voice engine for the QSB Tower council.

Server-side STT + TTS (same shape as ChatGPT voice mode): the iPad just records
and plays audio; all speech recognition + synthesis happen here on the HQ GPU box.

  POST /stt   body = raw audio bytes (webm/ogg/mp4/wav from MediaRecorder)
              -> {"ok": true, "text": "..."}
  POST /tts   JSON {"text": str, "member": str, "voice"?: str, "lang"?: "en"}
              -> audio/wav bytes  (each council member = a distinct voice)
  GET  /health -> {"ok", "stt": bool, "tts": bool, "voices": [...], "members": {...}}

Engines (all offline, no cloud):
  TTS = SuperTonic on-device ONNX (runs in this .venv).
  STT = whisper tiny.en (GGML weights re-homed into transformers) via a loopback
        sidecar on 127.0.0.1:8796 running the neuralnexus venv (torch cu128 + CUDA).
        This server auto-spawns that sidecar on startup.

Bind 0.0.0.0:8795.
"""
from __future__ import annotations
import json, logging, os, subprocess, tempfile, time, urllib.request, urllib.error
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

ROOT = "/vaults/nvme0/qsb_tower_v1"
HOST, PORT = "0.0.0.0", int(os.environ.get("QSB_VOICE_PORT", "8795"))
STT_PY = "/home/ross/Desktop/neuralnexus_cosmic/venv/bin/python"   # torch+transformers+CUDA
STT_SCRIPT = f"{ROOT}/tools/qsb_stt_whisper.py"
STT_URL = "http://127.0.0.1:8796"
LOG = f"{ROOT}/data/logs/voice_server.log"

# Council member -> SuperTonic voice style. wren/hermes/claude confirmed from the
# 2026-06-20 voice samples (wren_F1, hermes_M2, claude_M1); others assigned distinct.
MEMBER_VOICE = {
    # 2026-07-03 Ross Council expansion — 15 members mapped into 10 voice slots.
    "ross": "M5", "claude": "M1", "hq": "M1", "hq-claude": "M1",
    "helm": "M4", "auger": "F2",
    "wren": "F3", "hermes": "M2",
    "forge": "M3", "sage": "F1",
    "pip": "F4", "mira": "F5",
    "iris": "F4", "receptionist": "F2",
    "iquest": "M3", "tp": "M1", "thinkpad": "M1",
    "acer": "M4", "colonel": "M4",
    "default": "F1",
}
VALID_STYLES = {"M1", "M2", "M3", "M4", "M5", "F1", "F2", "F3", "F4", "F5"}

os.makedirs(os.path.dirname(LOG), exist_ok=True)
logging.basicConfig(level=logging.INFO, filename=LOG,
                    format="[%(asctime)s] %(levelname)s qsb.voice - %(message)s")
log = logging.getLogger("qsb.voice")

_TTS = None            # SuperTonic singleton
_TTS_ERR = None


def tts_engine():
    global _TTS, _TTS_ERR
    if _TTS is None and _TTS_ERR is None:
        try:
            from supertonic import TTS
            _TTS = TTS()
            log.info("SuperTonic TTS loaded")
        except Exception as e:
            _TTS_ERR = str(e)
            log.exception("TTS load failed")
    return _TTS


def resolve_voice(member: str, voice: str | None) -> str:
    if voice and voice.upper() in VALID_STYLES:
        return voice.upper()
    m = (member or "default").strip().lower()
    if m.upper() in VALID_STYLES:      # allow passing a raw style as member
        return m.upper()
    return MEMBER_VOICE.get(m, MEMBER_VOICE["default"])


def synth_wav(text: str, style: str, lang: str = "en") -> bytes:
    tts = tts_engine()
    if tts is None:
        raise RuntimeError(f"tts_unavailable: {_TTS_ERR}")
    wav, _dur = tts.synthesize(text, voice_style=tts.get_voice_style(style), lang=lang)
    with tempfile.NamedTemporaryFile(suffix=".wav", delete=False) as tmp:
        name = tmp.name
    try:
        tts.save_audio(wav, name)
        with open(name, "rb") as fh:
            return fh.read()
    finally:
        try: os.unlink(name)
        except OSError: pass


def to_16k_wav(raw: bytes) -> bytes:
    """Any browser audio container -> 16kHz mono PCM WAV via ffmpeg."""
    with tempfile.NamedTemporaryFile(delete=False) as fin:
        fin.write(raw)
        inp = fin.name
    out = inp + ".16k.wav"
    try:
        r = subprocess.run(
            ["ffmpeg", "-y", "-nostdin", "-i", inp, "-ar", "16000", "-ac", "1",
             "-f", "wav", out],
            stdout=subprocess.DEVNULL, stderr=subprocess.PIPE, timeout=60)
        if r.returncode != 0:
            raise RuntimeError("ffmpeg: " + r.stderr.decode("utf-8", "replace")[-300:])
        with open(out, "rb") as fh:
            return fh.read()
    finally:
        for p in (inp, out):
            try: os.unlink(p)
            except OSError: pass


def stt_sidecar_up() -> bool:
    try:
        with urllib.request.urlopen(STT_URL + "/health", timeout=3) as r:
            return json.loads(r.read()).get("ok", False)
    except Exception:
        return False


def stt_transcribe(wav16k: bytes) -> dict:
    req = urllib.request.Request(STT_URL + "/stt", data=wav16k,
                                 headers={"Content-Type": "audio/wav"}, method="POST")
    with urllib.request.urlopen(req, timeout=120) as r:
        return json.loads(r.read())


def ensure_sidecar():
    if stt_sidecar_up():
        log.info("STT sidecar already up")
        return
    if not os.path.exists(STT_PY):
        log.error("STT python not found: %s", STT_PY)
        return
    slog = open(f"{ROOT}/data/logs/voice_stt.spawn.log", "ab")
    log.info("spawning STT sidecar: %s %s", STT_PY, STT_SCRIPT)
    subprocess.Popen([STT_PY, STT_SCRIPT], stdout=slog, stderr=slog,
                     start_new_session=True, cwd=ROOT)
    for _ in range(90):                 # allow torch import + model load
        if stt_sidecar_up():
            log.info("STT sidecar became ready")
            return
        time.sleep(1)
    log.error("STT sidecar did not become ready in time")


class Handler(BaseHTTPRequestHandler):
    protocol_version = "HTTP/1.1"

    def log_message(self, fmt, *a):
        log.info("%s - %s", self.address_string(), fmt % a)

    def _json(self, status, payload):
        body = json.dumps(payload).encode()
        self.send_response(status)
        self.send_header("Content-Type", "application/json")
        self.send_header("Access-Control-Allow-Origin", "*")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def _wav(self, data: bytes):
        self.send_response(200)
        self.send_header("Content-Type", "audio/wav")
        self.send_header("Access-Control-Allow-Origin", "*")
        self.send_header("Cache-Control", "no-store")
        self.send_header("Content-Length", str(len(data)))
        self.end_headers()
        self.wfile.write(data)

    def _body(self) -> bytes:
        return self.rfile.read(int(self.headers.get("Content-Length") or 0))

    def do_OPTIONS(self):
        self.send_response(204)
        self.send_header("Access-Control-Allow-Origin", "*")
        self.send_header("Access-Control-Allow-Methods", "POST, GET, OPTIONS")
        self.send_header("Access-Control-Allow-Headers", "Content-Type")
        self.send_header("Content-Length", "0")
        self.end_headers()

    def do_GET(self):
        if self.path == "/health":
            tts = tts_engine()
            voices = sorted(VALID_STYLES) if tts is not None else []
            self._json(200, {"ok": True,
                             "stt": stt_sidecar_up(),
                             "tts": tts is not None,
                             "voices": voices,
                             "members": MEMBER_VOICE})
        else:
            self._json(404, {"ok": False, "error": "not_found"})

    def do_POST(self):
        if self.path == "/stt":
            raw = self._body()
            if not raw:
                return self._json(400, {"ok": False, "error": "empty_body"})
            try:
                t = time.time()
                wav16k = to_16k_wav(raw)
                res = stt_transcribe(wav16k)
                res["total_sec"] = round(time.time() - t, 3)
                return self._json(200, res)
            except Exception as e:
                log.exception("stt failed")
                return self._json(502, {"ok": False, "error": str(e)[:300]})
        if self.path == "/tts":
            try:
                payload = json.loads(self._body() or b"{}")
            except ValueError:
                return self._json(400, {"ok": False, "error": "bad_json"})
            text = str(payload.get("text") or "").strip()[:1500]
            if not text:
                return self._json(400, {"ok": False, "error": "empty_text"})
            style = resolve_voice(payload.get("member"), payload.get("voice"))
            lang = str(payload.get("lang") or "en")
            try:
                t = time.time()
                data = synth_wav(text, style, lang)
                log.info("tts member=%s style=%s %d chars -> %d bytes (%.2fs)",
                         payload.get("member"), style, len(text), len(data), time.time() - t)
                return self._wav(data)
            except Exception as e:
                log.exception("tts failed")
                return self._json(500, {"ok": False, "error": str(e)[:300]})
        self._json(404, {"ok": False, "error": "not_found"})


def main():
    log.info("QSB voice server starting on %s:%d", HOST, PORT)
    tts_engine()          # warm TTS
    ensure_sidecar()      # warm STT
    print(f"[qsb_voice_server] listening on {HOST}:{PORT}", flush=True)
    ThreadingHTTPServer((HOST, PORT), Handler).serve_forever()


if __name__ == "__main__":
    main()
