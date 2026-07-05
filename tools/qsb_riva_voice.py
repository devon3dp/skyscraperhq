"""QSB · Wren's Riva voice client.

Synthesizes speech via NVIDIA Riva running locally (gRPC default :50051) and
returns a WAV-wrapped audio blob suitable for browser <audio> playback.

Design points:
- Importable even when neither riva.client nor a running server is present
  (returns a clean error so the dashboard endpoint can 503 and the cockpit
  can fall back to browser SpeechSynthesis).
- LINEAR_PCM out of Riva → WAV wrapped here. Riva does not return WAV
  headers; the browser <audio> element needs them.
- One synchronous round-trip. No streaming. No agents. Same operational
  envelope as the OpenAI/DeepSeek consult tool.
- Wren-initiated (or dashboard endpoint on Ross's behalf). Not used in any
  autonomous worker loop.

Default voice: English-US.Female-1 (Riva's default high-quality voice).
Can be overridden per call. The voice catalog depends on which Riva model
the user has pulled — `riva.client` will surface model-not-found errors
which the endpoint surfaces as 503.
"""

from __future__ import annotations
import io
import struct
import wave
from dataclasses import dataclass

DEFAULT_URI = "localhost:50051"
DEFAULT_VOICE = "English-US.Female-1"
DEFAULT_LANG = "en-US"
DEFAULT_SAMPLE_RATE = 44100


@dataclass
class RivaResult:
    ok: bool
    wav_bytes: bytes
    error: str
    voice: str
    sample_rate: int


def _pcm_to_wav(pcm: bytes, sample_rate: int, channels: int = 1, sample_width: int = 2) -> bytes:
    """Wrap raw LINEAR_PCM in a WAV header so browsers can play it."""
    buf = io.BytesIO()
    with wave.open(buf, "wb") as w:
        w.setnchannels(channels)
        w.setsampwidth(sample_width)
        w.setframerate(sample_rate)
        w.writeframes(pcm)
    return buf.getvalue()


def synthesize(
    text: str,
    voice: str = DEFAULT_VOICE,
    language: str = DEFAULT_LANG,
    sample_rate: int = DEFAULT_SAMPLE_RATE,
    uri: str = DEFAULT_URI,
    timeout_s: float = 10.0,
) -> RivaResult:
    """Synthesize text via Riva. Returns RivaResult; ok=False if anything fails."""
    if not text or not text.strip():
        return RivaResult(False, b"", "empty text", voice, sample_rate)

    try:
        import riva.client  # type: ignore
        from riva.client import AudioEncoding  # type: ignore
    except Exception as e:
        return RivaResult(
            False, b"",
            f"riva.client not installed ({e}). Install with: pip install nvidia-riva-client",
            voice, sample_rate,
        )

    try:
        auth = riva.client.Auth(uri=uri)
        tts = riva.client.SpeechSynthesisService(auth)
        resp = tts.synthesize(
            text=text,
            voice_name=voice,
            language_code=language,
            sample_rate_hz=sample_rate,
            encoding=AudioEncoding.LINEAR_PCM,
        )
        pcm = bytes(resp.audio)
        if not pcm:
            return RivaResult(False, b"", "riva returned empty audio", voice, sample_rate)
        wav = _pcm_to_wav(pcm, sample_rate)
        return RivaResult(True, wav, "", voice, sample_rate)
    except Exception as e:
        # gRPC errors, voice-not-found, server-down all land here
        msg = str(e)
        if len(msg) > 240:
            msg = msg[:240] + "…"
        return RivaResult(False, b"", f"riva call failed: {msg}", voice, sample_rate)


def reachable(uri: str = DEFAULT_URI, timeout_s: float = 2.0) -> dict:
    """Quick liveness probe — does the Riva gRPC port answer?"""
    import socket
    host, _, port = uri.partition(":")
    try:
        with socket.create_connection((host, int(port or 50051)), timeout=timeout_s):
            return {"ok": True, "uri": uri}
    except Exception as e:
        return {"ok": False, "uri": uri, "error": str(e)}


if __name__ == "__main__":
    # Tiny smoke harness: prints result + writes /tmp/wren_riva_smoke.wav if ok.
    import sys, pathlib
    text = " ".join(sys.argv[1:]) or "Wren is the resident of floor forty-seven."
    print(f"[riva] reachable check: {reachable()}")
    r = synthesize(text)
    print(f"[riva] ok={r.ok} voice={r.voice} sr={r.sample_rate} bytes={len(r.wav_bytes)} err={r.error}")
    if r.ok:
        out = pathlib.Path("/tmp/wren_riva_smoke.wav")
        out.write_bytes(r.wav_bytes)
        print(f"[riva] wav written: {out}")
